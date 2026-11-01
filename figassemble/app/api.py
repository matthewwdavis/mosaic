"""JSON-RPC methods the editor calls. The editor owns the document; these are stateless
apart from the asset cache, preferences and the native window (dialogs)."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import threading
import time
import zipfile

from .. import __version__, connect, docfile, model, presets, themes
from ..assets import KIND_EXT, get_cache, new_asset, new_asset_from_bytes, refresh_asset
from ..fonts import config_dir, get_font_index
from ..resolve import Resolver
from . import clipboard, powerpoint

DECK_EXTENSIONS = (".pptx", ".pptm", ".potx")
DECKS_KEPT = 4   # decks kept imported for the slide picker (the slides chosen then come from them)

PREFS_DEFAULTS = {
    # Positions and sizes of objects in centimetres, page sizes in millimetres; font sizes and
    # line widths are always points
    "units": "cm", "page_units": "mm", "ui_scale": 1.0, "show_tool_labels": True,
    # Interface theme (themes.py): one theme, or "system" for the day and night themes by the system's mode
    "theme": "system", "theme_day": "light", "theme_night": "dark",
    "reduced_motion": False, "snap": True, "default_dpi": 600, "default_formats": ["pdf", "png"],
    "transparent": True, "panel_label": {"size": 8.0, "bold": True, "font": "Helvetica", "case": "lower"},
    "text": {"font": "Helvetica", "size": 6.0}, "stroke_width": 1.0, "recent": [],
    # Layout aids: the grid is graph paper, 1 cm squares of 1 mm lines (spacing in points); things
    # snap to the grid and guides only while they're shown
    "show_rulers": True, "show_grid": False, "show_guides": True, "grid": {"spacing": 72 / 2.54, "subdivisions": 10},
    # Arrow keys move a round amount that shrinks as you zoom in (False: always 1 pt)
    "nudge_zoom": True,
    # Interface state: the ribbon's tab, the properties panel's tab for each kind of object, the
    # panel's folded sections, and the side panels' widths (rem; only those changed)
    "ribbon_tab": "home", "inspector_tabs": {}, "inspector_closed": [], "panel_widths": {},
    # The journal Check last compared a page's size with (a page with a journal size uses its own)
    "check_journal": "",
}
PREFS_VERSION = 2


def _prefs_path() -> str:
    return os.path.join(config_dir(), "prefs.json")


def _read_prefs_file() -> dict:
    try:
        with open(_prefs_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _write_prefs_file(stored: dict) -> None:
    """Written whole to a temporary file that then takes the file's place, so nothing ever reads
    it half written, and a crash can't leave it empty."""
    path = _prefs_path()
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(stored, fh, indent=1)
    for _ in range(25):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:   # Windows: another program has the file open for a moment
            time.sleep(0.02)
    os.replace(tmp, path)


def _choices_only(stored: dict) -> dict:
    """Keep only settings that differ from the defaults, so changing a default reaches everyone."""
    return {k: v for k, v in stored.items() if k == "prefs_version" or PREFS_DEFAULTS.get(k, ...) != v}


class Api:
    def __init__(self):
        self.window = None          # set by the app window; None in browser mode
        self._lock = threading.Lock()
        self._decks: dict[str, dict] = {}     # imported decks, by path or by the key of copied slides
        self._deck_lock = threading.Lock()
        self._thumb_lock = threading.Lock()
        self._index: tuple | None = None      # (folders, when, figure files in them) to relink pictures to
        self._dropped: dict[str, dict] = {}   # slides or shapes dragged in from PowerPoint, until taken

    # Utilities ------------------------------------------------------------------------

    def _asset_view(self, assets: dict) -> dict:
        return {aid: {"size_pt": a.get("size_pt"), "page_sizes": a.get("page_sizes")} for aid, a in assets.items()}

    # App ------------------------------------------------------------------------------

    def app_info(self) -> dict:
        from ..journals import JOURNALS, STANDARD_SIZES
        return {"version": __version__, "platform": sys.platform, "native": self.window is not None,
                "prefs": self.prefs_get(), "standard_sizes": STANDARD_SIZES, "journals": JOURNALS,
                "machine": platform.node(), "shapes": presets.catalog(), "clipboard": clipboard.backend() is not None,
                "themes": themes.catalog()}

    def theme_css(self, theme: str | None = None, day: str | None = None, night: str | None = None) -> str:
        """The interface colours for a theme (by default the one chosen in Settings)."""
        p = self.prefs_get()
        return themes.css(theme or p.get("theme", "system"), day or p.get("theme_day", "light"),
                          night or p.get("theme_night", "dark"))

    def fonts(self) -> list[str]:
        return get_font_index().families()

    # Settings are read and written under one lock: requests arrive on several threads at once
    # (a tab remembered while a toggle saves), and a read must never meet a write half done

    def prefs_get(self) -> dict:
        with self._lock:
            return self._prefs()

    def _prefs(self) -> dict:
        stored = _read_prefs_file()
        if stored and stored.get("prefs_version") != PREFS_VERSION:
            # Version 1 saved every default alongside real choices, which froze positions in
            # points; keep only real choices so the centimetre default applies
            stored = {k: v for k, v in stored.items() if not (k == "units" and v == "pt")}
            stored = _choices_only(stored)
            stored["prefs_version"] = PREFS_VERSION
            _write_prefs_file(stored)
        prefs = dict(PREFS_DEFAULTS)
        prefs.update({k: v for k, v in stored.items() if k != "prefs_version"})
        return prefs

    def prefs_set(self, prefs: dict) -> dict:
        with self._lock:
            self._prefs()   # brings an older settings file up to date first
            stored = _read_prefs_file()
            stored.update(prefs or {})
            stored["prefs_version"] = PREFS_VERSION
            _write_prefs_file(_choices_only(stored))
            return self._prefs()

    def _remember(self, path: str) -> None:
        prefs = self.prefs_get()
        recent = ([path] + [p for p in prefs.get("recent", []) if p != path])[:12]
        self.prefs_set({"recent": recent})
        self._on_mac_menus("set_recent", recent)   # File > Open Recent

    # The Mac menu bar (macmenu.py) --------------------------------------------------------------

    def _on_mac_menus(self, name: str, *args) -> bool:
        """Run a macmenu function on the main thread, in the app window on a Mac."""
        if self.window is None or sys.platform != "darwin":
            return False
        from PyObjCTools import AppHelper

        from . import macmenu
        AppHelper.callAfter(getattr(macmenu, name), *args)
        return True

    def set_menus(self, spec: list) -> bool:
        """The editor's menus, for the menu bar on a Mac (macmenu.build); nothing elsewhere."""
        return self._on_mac_menus("build", self.window, self, spec, self.prefs_get().get("recent", []))

    def menu_checks(self, checks: dict) -> bool:
        """Ticks on the Mac menu bar's items: {action: on}."""
        return self._on_mac_menus("set_checks", checks)

    # Documents -------------------------------------------------------------------------

    def new_document(self) -> dict:
        return model.new_document()

    def open_document(self, path: str, slides: list[int] | None = None) -> dict:
        """A document, or a PowerPoint deck's slides (the numbers chosen; default all) as a new
        unsaved one."""
        path = os.path.abspath(os.path.expanduser(path))
        if path.lower().endswith(DECK_EXTENSIONS):
            got = self.deck_pages(path, slides or list(range(1, len(self._deck(path)["importer"].slides) + 1)))
            doc = model.new_document(got["name"])
            doc["pages"], doc["assets"] = got["pages"], got["assets"]
            doc["meta"]["imported_from"] = path
            return {"doc": doc, "path": None, "report": got["report"],
                    "suggested": os.path.splitext(path)[0] + docfile.EXTENSION}
        doc = docfile.load(path)
        self._remember(path)
        return {"doc": doc, "path": path, "report": []}

    # PowerPoint slides: decks opened or dropped (through the slide picker), slides and shapes
    # copied or dragged out of PowerPoint ---------------------------------------------------------

    def _keep_deck(self, key: str, entry: dict) -> None:
        self._decks.pop(key, None)
        self._decks[key] = entry
        while len(self._decks) > DECKS_KEPT:
            self._decks.pop(next(iter(self._decks)))

    def _deck(self, key: str) -> dict:
        """A deck imported whole: `key` is its path (imported again once the file changes), or
        the key of copied, dragged or uploaded slides (_deck_bytes)."""
        with self._deck_lock:
            d = self._decks.get(key)
            if d and d["path"]:
                st = os.stat(d["path"])
                if (st.st_mtime, st.st_size) != d["stamp"]:
                    d = None
            if d is None:
                if not os.path.isfile(key):
                    raise FileNotFoundError(f"{key} isn't there any more")
                from ..importers.pptx import DeckImporter
                st = os.stat(key)
                imp = DeckImporter(key, None, True, None)
                imp.run(None)
                d = {"key": key, "path": key, "stamp": (st.st_mtime, st.st_size), "importer": imp,
                     "name": os.path.splitext(os.path.basename(key))[0], "thumbs": {}}
                self._keep_deck(key, d)
            return d

    def _deck_bytes(self, data: bytes, name: str, dirs: list[str]) -> str:
        """Slides as bytes (copied, dragged in, or a deck dropped in the browser), imported whole;
        their key. Pictures are relinked to figure files in `dirs`."""
        key = "copied:" + hashlib.sha256(data).hexdigest()[:20]
        with self._deck_lock:
            if key not in self._decks:
                from ..importers.pptx import DeckImporter
                imp = DeckImporter(data, None, True, None, name=name, index=self._relink_index(dirs))
                imp.run(None)
                self._keep_deck(key, {"key": key, "path": None, "importer": imp, "name": name, "thumbs": {}})
        return key

    def _relink_index(self, dirs: list[str]):
        """The figure files in some folders, to relink pictures to; kept a minute for the next
        paste (with the files' hashes worked out meanwhile)."""
        from ..importers.relink import CandidateIndex
        if self._index and self._index[0] == tuple(dirs) and time.time() - self._index[1] < 60:
            return self._index[2]
        index = CandidateIndex(list(dirs))
        self._index = (tuple(dirs), time.time(), index)
        return index

    def _paste_dirs(self, source: str | None, doc_path: str | None) -> list[str]:
        """Where the original figure files of pictures from PowerPoint may be: near the deck they
        came from; for copied slides, which don't say, near each deck PowerPoint has open; and
        near the figure being worked on."""
        from ..importers.relink import default_search_dirs
        decks = [source] if source and os.path.isfile(source) else powerpoint.open_decks()
        dirs = [d for deck in decks for d in default_search_dirs(deck)]
        if doc_path:
            dirs += default_search_dirs(doc_path)
        return [d for d in dict.fromkeys(dirs) if os.path.isdir(d)]

    def deck_slides(self, key: str) -> dict:
        """A deck's slides for the slide picker: {"key", "name", "width", "height", "slides":
        [{"n", "title", "hidden"}]}. Imported whole now, so the pictures of the slides and the
        slides chosen come quickly."""
        if not key.startswith("copied:"):
            key = os.path.abspath(os.path.expanduser(key))
        d = self._deck(key)
        imp = d["importer"]
        return {"key": key, "name": d["name"], "width": imp.width, "height": imp.height, "slides": imp.slide_info()}

    def deck_thumbnail(self, key: str, n: int, width_px: int = 320) -> str:
        """Slide n drawn small, as a PNG data URL."""
        d = self._deck(key)
        if n not in d["thumbs"]:
            from ..export.run import page_thumbnail
            with self._thumb_lock:
                im = page_thumbnail(d["importer"].doc, int(n) - 1, int(width_px), fonts=get_font_index())
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            d["thumbs"][n] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        return d["thumbs"][n]

    def deck_pages(self, key: str, numbers: list[int]) -> dict:
        """Slides as pages (copies), with the pictures they use and what importing them found:
        {"name", "pages", "assets", "report"}."""
        if not key.startswith("copied:"):
            key = os.path.abspath(os.path.expanduser(key))
        d = self._deck(key)
        imp = d["importer"]
        numbers = [int(n) for n in numbers if 1 <= int(n) <= len(imp.slides)]
        pages = json.loads(json.dumps([imp.doc["pages"][n - 1] for n in numbers]))
        used: set[str] = set()

        def walk(o):
            if isinstance(o, dict):
                if isinstance(o.get("asset"), str):
                    used.add(o["asset"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(pages)
        assets = json.loads(json.dumps({aid: a for aid, a in imp.doc["assets"].items() if aid in used}))
        return {"name": d["name"], "pages": pages, "assets": assets, "report": imp.report_for(numbers)}

    def deck_upload(self, name: str, data_b64: str) -> str:
        """A deck dropped in the browser (its bytes, with no path to it): its key for the picker."""
        return self._deck_bytes(base64.b64decode(data_b64), os.path.splitext(os.path.basename(name))[0], [])

    def _office_paste(self, kind: str, got: dict, doc_path: str | None) -> dict:
        """Slides or shapes from PowerPoint, as Paste puts them on the page: {"kind": "slides",
        "key", "name", "pages", "assets", "report"} or {"kind": "shapes", "items", "assets", "report"}."""
        dirs = self._paste_dirs(got.get("source"), doc_path)
        if kind == "slides":
            key = self._deck_bytes(got["data"], "Copied slides", dirs)
            return {"kind": kind, "key": key, **self.deck_pages(key, list(range(1, len(self._decks[key]["importer"].slides) + 1)))}
        from ..importers.gvml import import_shapes
        items, assets, report = import_shapes(got["data"], index=self._relink_index(dirs))
        return {"kind": kind, "items": items, "assets": assets, "report": report}

    def powerpoint_slides(self, refs: list[dict], decks: list[str] | None = None) -> dict:
        """Slides dragged out of PowerPoint (their references): the decks PowerPoint has open
        that have them, as last saved: {"found": [{"path", "name", "numbers"}]}. `decks`: the
        ones to look in instead (the editor self-test's)."""
        found = powerpoint.find_slides(refs, decks)
        for f in found:
            f["name"] = os.path.basename(f["path"])
        return {"found": found}

    def take_dropped(self, token: str, doc_path: str | None = None) -> dict:
        """Slides or shapes dragged in from PowerPoint with their contents, as a paste of them."""
        got = self._dropped.pop(token, None)
        return self._office_paste(got["kind"], got, doc_path) if got else {"kind": "none"}

    def dropped_package(self, kind: str, data_b64: str, doc_path: str | None = None) -> dict:
        """Slides dropped on the page with their contents as PowerPoint's web data (what a
        Chromium web view is handed, if PowerPoint for Windows offers it), as a paste of them."""
        return self._office_paste(kind, {"data": base64.b64decode(data_b64), "source": None}, doc_path)

    def save_document(self, doc: dict, path: str) -> dict:
        path = os.path.abspath(os.path.expanduser(path))
        if not path.lower().endswith(docfile.EXTENSION):
            path += docfile.EXTENSION
        warnings = docfile.save(doc, path)
        self._remember(path)
        return {"path": path, "warnings": warnings}

    def autosave(self, doc: dict, key: str) -> dict:
        d = os.path.join(config_dir(), "autosave")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{key}{docfile.EXTENSION}")
        docfile.save(doc, path, prune=False)
        return {"path": path}

    def autosaved(self, exclude_key: str | None = None) -> list[dict]:
        """Recovery copies of unsaved documents, newest first (the current session's left out),
        with what's in each so they can be told apart."""
        d = os.path.join(config_dir(), "autosave")
        if not os.path.isdir(d):
            return []
        out = []
        for n in os.listdir(d):
            if not n.endswith(docfile.EXTENSION) or (exclude_key and n == f"{exclude_key}{docfile.EXTENSION}"):
                continue
            p = os.path.join(d, n)
            entry = {"path": p, "modified": os.path.getmtime(p), "bytes": os.path.getsize(p)}
            try:
                with zipfile.ZipFile(p) as z:
                    doc = json.loads(z.read(docfile.DOC_NAME))
                pages = doc.get("pages", [])
                entry.update(title=(doc.get("meta") or {}).get("title") or "Untitled figure", pages=len(pages),
                             objects=sum(len(pg.get("items", [])) for pg in pages))
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                entry.update(title="Unreadable copy", pages=0, objects=0)
            out.append(entry)
        return sorted(out, key=lambda e: -e["modified"])

    def delete_autosaves(self, paths: list[str], exclude_key: str | None = None) -> list[dict]:
        """Delete recovery copies (only ever files in FigAssemble's own autosave folder); returns
        the ones left."""
        d = os.path.realpath(os.path.join(config_dir(), "autosave"))
        for p in paths or []:
            real = os.path.realpath(p)
            if os.path.dirname(real) == d and real.endswith(docfile.EXTENSION) and os.path.isfile(real):
                os.remove(real)   # FigAssemble's own autosave file
        return self.autosaved(exclude_key)

    def discard_autosave(self, key: str) -> bool:
        p = os.path.join(config_dir(), "autosave", f"{key}{docfile.EXTENSION}")
        if os.path.exists(p):
            os.remove(p)   # FigAssemble's own autosave file
        return True

    # Assets ----------------------------------------------------------------------------

    def add_files(self, paths: list[str], embed_only: bool = False) -> list[dict]:
        out = []
        for p in paths:
            try:
                aid, asset, warnings = new_asset(p, get_cache(), link=not embed_only)
                out.append({"asset_id": aid, "asset": asset, "warnings": warnings})
            except Exception as exc:
                out.append({"error": f"{os.path.basename(p)}: {exc}"})
        return out

    def add_upload(self, name: str, data_b64: str) -> dict:
        data = base64.b64decode(data_b64)
        aid, asset = new_asset_from_bytes(data, name, get_cache())
        return {"asset_id": aid, "asset": asset, "warnings": []}

    # The system clipboard (see clipboard.py) ----------------------------------------------------

    def clipboard_copied(self, text: str) -> int | None:
        """The editor put text on the clipboard: its change count now, to know a later paste's
        clipboard still holds that copy (the test clipboard takes the text itself)."""
        cb = clipboard.backend()
        if isinstance(cb, clipboard.FakeClipboard):
            return cb.put({"text": text})
        return cb.count() if cb else None

    def clipboard_kinds(self, own_count: int | None = None) -> dict:
        return clipboard.kinds(clipboard.backend(), own_count)

    def clipboard_paste(self, mode: str = "auto", own_count: int | None = None, doc_path: str | None = None) -> dict:
        """What Paste puts on the page: {"kind": "own"} (the editor's own copy), "objects"
        (FigAssemble objects from another document), "files" (placed linked), "slides" or
        "shapes" (copied in PowerPoint, see _office_paste), "picture" (stored in the document),
        "text" (paragraphs), "none" or "unavailable". `doc_path`: the figure's file, near which
        pictures from PowerPoint may find their originals."""
        kind, data = clipboard.plan(clipboard.backend(), mode, own_count)
        if kind == "objects":
            return {"kind": kind, "clip": json.loads(data)}
        if kind in ("slides", "shapes"):
            return self._office_paste(kind, data, doc_path)
        if kind == "files":
            return {"kind": kind, "results": self.add_files(data)}
        if kind == "picture":
            raw, ext = data
            aid, asset = new_asset_from_bytes(raw, f"Pasted picture{ext}", get_cache())
            return {"kind": kind, "asset_id": aid, "asset": asset, "warnings": []}
        if kind == "text":
            return {"kind": kind, "paragraphs": data}
        return {"kind": kind}

    def clipboard_fake(self, contents: dict) -> int:
        """Set the test clipboard's contents (only with FIGASSEMBLE_FAKE_CLIPBOARD)."""
        cb = clipboard.backend()
        if not isinstance(cb, clipboard.FakeClipboard):
            raise PermissionError("only the test clipboard can be set")
        return cb.put(contents)

    def selftest_read(self, path: str) -> str:
        """A test file's bytes as base64, for the editor self-test to drop as data (only while
        testing, with FIGASSEMBLE_FAKE_CLIPBOARD)."""
        if not isinstance(clipboard.backend(), clipboard.FakeClipboard):
            raise PermissionError("only while testing")
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")

    def refresh_assets(self, assets: dict, doc_path: str | None = None) -> dict:
        """Re-read linked files that changed on disk; returns the updated asset records."""
        doc_dir = os.path.dirname(doc_path) if doc_path else None
        changed = {}
        for aid, asset in assets.items():
            asset = json.loads(json.dumps(asset))
            try:
                kinds = refresh_asset(asset, get_cache(), doc_dir)
            except Exception:
                continue
            if kinds:
                changed[aid] = asset
        return {"changed": changed}

    def link_status(self, assets: dict, doc_path: str | None = None) -> dict:
        from ..assets import resolve_link
        doc_dir = os.path.dirname(doc_path) if doc_path else None
        out = {}
        for aid, asset in assets.items():
            prim = asset["variants"].get(asset.get("primary")) or next(iter(asset["variants"].values()))
            if not prim.get("src"):
                out[aid] = "embedded"
            else:
                out[aid] = "linked" if resolve_link(prim, doc_dir) else "missing"
        return out

    # Editor ----------------------------------------------------------------------------

    def resolve(self, assets: dict, items: list[dict], context: list[dict] | None = None,
                symbols: list[dict] | None = None) -> list[dict]:
        """Draw items for the editor. `context`: other items on the page that area fills among
        `items` need (the lines and shapes round them); `symbols`: the figure's symbols, for copies."""
        from ..export.svgwriter import fragment
        resolver = Resolver({"assets": assets, "symbols": symbols or []}, get_font_index())
        resolver.use_page([*(context or []), *items])
        out = []
        for it in items:
            try:
                r = resolver.resolve(it)
                res = {"id": it.get("id"), "svg": fragment(r, it.get("id", "x")), "bbox": r.bbox,
                       "autofit_frame": r.autofit_frame, "warnings": r.warnings}
                if r.region:
                    res["region"] = r.region
                if it.get("type") == "shape" and not it.get("textbox") and presets.is_preset(it.get("geom", "")):
                    # Where the shape's adjust handles sit, in frame coordinates
                    res["handles"] = presets.handles(it["geom"], it["frame"][2], it["frame"][3], it.get("adj"))
                # Where line ends can attach: shapes as fractions of their frame, lines' dashes on the page
                if it.get("type") == "shape":
                    res["sites"] = connect.shape_sites(it)
                elif it.get("type") == "line":
                    res["sites"] = connect.line_sites(r.prims)
                out.append(res)
            except Exception as exc:
                out.append({"id": it.get("id"), "svg": "", "bbox": None, "warnings": [str(exc)]})
        return out

    def region_at(self, items: list[dict], point: list[float]) -> dict | None:
        """The area the page's lines and shapes enclose round a point, for a new area fill:
        {items, seed, frame} (regions.area_at), or None."""
        from .. import regions
        return regions.area_at(items, point)

    def area_path(self, item: dict, local: bool = False) -> dict | None:
        """What clips by an item (a picture's crop shape, a clipping mask's shape) as SVG path
        data, on the page or in the item's own frame (local), for the editor: {d, even_odd}."""
        from ..resolve import clip_path, item_area
        area = item_area(item, local=bool(local))
        if not area:
            return None
        path, even_odd = clip_path(area)
        return {"d": path.to_svg(3), "even_odd": bool(even_odd)}

    def pathfinder(self, items: list[dict], how: str) -> dict:
        """Shapes (bottom to top) combined into one freeform shape (pathfinder.combine)."""
        from ..pathfinder import combine
        return combine(items, how)

    def drag_handle(self, item: dict, index: int, point: list[float]) -> dict:
        """Adjust values that put a shape's handle `index` nearest a frame point."""
        return presets.drag_handle(item["geom"], item["frame"][2], item["frame"][3], item.get("adj"),
                                   int(index), float(point[0]), float(point[1]))

    def adjust_shape(self, assets: dict, item: dict, index: int, point: list[float]) -> dict:
        """Drag a yellow handle: the new adjust values and the shape drawn with them, in one round
        trip so the shape keeps up with the pointer."""
        adj = self.drag_handle(item, index, point)
        return {"adj": adj, "drawn": self.resolve(assets, [{**item, "adj": adj}])[0]}

    def clamp_adjust(self, item: dict, name: str, value: float) -> float:
        return presets.clamp_adjust(item["geom"], item["frame"][2], item["frame"][3], item.get("adj"),
                                    name, float(value))

    def shape_to_curve(self, assets: dict, item: dict) -> dict:
        from ..resolve import shape_to_curve
        return shape_to_curve(item, assets)

    def export(self, doc: dict, options: dict) -> dict:
        from ..export.run import export_document
        base = options["base"]
        doc_dir = os.path.dirname(options["doc_path"]) if options.get("doc_path") else None
        res = export_document(doc, base, options.get("formats", ["pdf"]), pages=options.get("pages"),
                              dpi=float(options.get("dpi", 600)), transparent=options.get("transparent", True),
                              cmyk=options.get("cmyk", False), cmyk_profile=options.get("icc") or None,
                              doc_dir=doc_dir, embed_fonts=options.get("embed_fonts", True))
        return res

    def preflight(self, doc: dict, options: dict | None = None) -> dict:
        from ..export.preflight import preflight
        return preflight(doc, options or {})

    def figure_report(self, doc: dict, options: dict) -> dict:
        """Write the figure report (report.py) in the chosen formats: {"files": [...]}."""
        from .. import report
        files = report.write(doc, options["base"], options.get("formats", []), options.get("pages"),
                             options.get("units", "cm"), options.get("doc_path"))
        return {"files": files}

    def shape_to_custom(self, item: dict) -> dict:
        """A ready-made shape as a freeform shape of the same outline (resolve.shape_to_custom)."""
        from ..resolve import shape_to_custom
        return shape_to_custom(item)

    def make_equation(self, spec: dict) -> dict:
        """An equation (equations.py) as a picture's asset, its PDF and SVG copies stored in the
        figure: {"id", "asset"}, or {"error"} when the maths can't be read."""
        import shutil

        from .. import equations
        tex = (spec or {}).get("tex", "").strip()
        if not tex:
            return {"error": "type some maths first"}
        try:
            pdf, _ = equations.render(tex, float(spec.get("size") or 6), spec.get("font", "figure"),
                                      spec.get("family") or "Helvetica", spec.get("color") or "#000000")
        except ValueError as exc:
            return {"error": str(exc)}
        try:
            aid, asset, _ = new_asset(pdf, get_cache(), link=False)
        finally:
            shutil.rmtree(os.path.dirname(pdf), ignore_errors=True)
        asset["name"] = f"Equation {tex[:40]}"
        return {"id": aid, "asset": asset}

    def plot_lines(self, asset: dict, page_index: int = 0) -> dict | None:
        """A placed plot's axis and frame lines and the box round its ink, to snap to
        (vectors.plot_lines), from its PDF copy or else its SVG; None for a photo."""
        from .. import vectors
        variants = (asset or {}).get("variants", {})
        kind = next((k for k in ("pdf", "svg") if k in variants), None)
        if kind is None:
            return None
        try:
            path = get_cache().path(variants[kind]["sha256"], kind)
            return vectors.plot_lines(path, kind, int(page_index or 0) if kind == "pdf" else 0)
        except Exception:
            return None

    # Native helpers --------------------------------------------------------------------

    def open_dialog(self, kind: str = "document") -> list[str] | None:
        if self.window is None:
            return None
        import webview
        types = {
            "document": ("FigAssemble or PowerPoint (*.figasm;*.pptx;*.pptm;*.potx)", "All files (*.*)"),
            "figures": ("Figures (*.pdf;*.svg;*.png;*.jpg;*.jpeg;*.tif;*.tiff)", "All files (*.*)"),
            "icc": ("ICC profiles (*.icc;*.icm)", "All files (*.*)"),
        }[kind]
        res = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=(kind == "figures"),
                                             file_types=types)
        return list(res) if res else None

    def save_dialog(self, suggested: str = "Untitled.figasm", directory: str = "") -> str | None:
        if self.window is None:
            return None
        import webview
        res = self.window.create_file_dialog(webview.FileDialog.SAVE, directory=directory or "",
                                             save_filename=os.path.basename(suggested))
        if not res:
            return None
        return res if isinstance(res, str) else res[0]

    def reveal(self, path: str) -> bool:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        elif os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
        return True

    def set_title(self, title: str) -> bool:
        if self.window is not None:
            self.window.set_title(title)
        return True

    def confirm_close(self, dirty: bool) -> bool:
        """Ask before closing only while there are unsaved changes."""
        self._dirty = bool(dirty)
        if self.window is not None:
            self.window.confirm_close = self._dirty
        return True


def asset_preview_key(sha: str, kind: str) -> str:
    return sha + KIND_EXT.get(kind, "." + kind)

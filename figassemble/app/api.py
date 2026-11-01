"""JSON-RPC methods the editor calls. The editor owns the document; these are stateless
apart from the asset cache, preferences and the native window (dialogs)."""
from __future__ import annotations

import base64
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
from . import clipboard

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
        recent = [p for p in prefs.get("recent", []) if p != path]
        self.prefs_set({"recent": ([path] + recent)[:12]})

    # Documents -------------------------------------------------------------------------

    def new_document(self) -> dict:
        return model.new_document()

    def open_document(self, path: str) -> dict:
        path = os.path.abspath(os.path.expanduser(path))
        if path.lower().endswith((".pptx", ".potx")):
            from ..importers.pptx import import_pptx
            doc, report = import_pptx(path)
            return {"doc": doc, "path": None, "report": report,
                    "suggested": os.path.splitext(path)[0] + docfile.EXTENSION}
        doc = docfile.load(path)
        self._remember(path)
        return {"doc": doc, "path": path, "report": []}

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

    def clipboard_paste(self, mode: str = "auto", own_count: int | None = None) -> dict:
        """What Paste puts on the page: {"kind": "own"} (the editor's own copy), "objects"
        (FigAssemble objects from another document), "files" (placed linked), "picture" (stored
        in the document), "text" (paragraphs), "none" or "unavailable"."""
        kind, data = clipboard.plan(clipboard.backend(), mode, own_count)
        if kind == "objects":
            return {"kind": kind, "clip": json.loads(data)}
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

    def resolve(self, assets: dict, items: list[dict], context: list[dict] | None = None) -> list[dict]:
        """Draw items for the editor. `context`: other items on the page that area fills among
        `items` need (the lines and shapes round them)."""
        from ..export.svgwriter import fragment
        resolver = Resolver({"assets": assets}, get_font_index())
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
            "document": ("FigAssemble or PowerPoint (*.figasm;*.pptx)", "All files (*.*)"),
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

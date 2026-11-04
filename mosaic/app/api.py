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
import tempfile
import threading
import time
import zipfile

from .. import __version__, connect, docfile, model, presets, themes
from ..assets import KIND_EXT, get_cache, new_asset, new_asset_from_bytes, refresh_asset
from ..fonts import config_dir, get_font_index
from ..journals import DEFAULT_SIZE
from ..resolve import Resolver, shape_outline
from ..updates import parse_version
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
    # Updates (updates.py): "auto" downloads a new version and installs it when mosaic quits,
    # "ask" says so and waits for a click, "off" doesn't look; "test" takes test versions too
    "updates": "auto", "update_channel": "stable",
    # Interface state: the ribbon's tab, the properties panel's tab for each kind of object, the
    # panel's folded sections, and the side panels' widths (rem; only those changed)
    "ribbon_tab": "home", "inspector_tabs": {}, "inspector_closed": [], "panel_widths": {},
    # The journal Check last compared a page's size with (a page with a journal size uses its own)
    "check_journal": "",
    # The page size new documents start at: {"standard": name} or {"journal": name, "type": figure type}
    "new_page": {"standard": DEFAULT_SIZE},
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


def _same_file(path: str) -> str:
    """A path as compared with others: the same file however it's written."""
    return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))


def _try_lock(fh) -> bool:
    """Lock an open file for this process alone, without waiting: False if something else has it."""
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fh) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class Api:
    def __init__(self):
        # The app's windows, by number (pywebview's Window objects; none in browser mode), and
        # what each has open: {path, dirty} (doc_state). Each editor sends its window's number
        # with every request (server.py), so `window` is the one asking
        self._windows: dict[str, object] = {}
        self._page_over: str | None = None      # the window showing where a dragged page would go
        self._win_state: dict[str, dict] = {}
        self._caller = threading.local()
        self._next_win = 1
        self._new_window = None               # window.py's: opens a window (document, slides)
        self.hidden_windows = False           # the smoke test's: windows are never shown
        # Documents macOS opened mosaic with (macopen.py) wait here for the first editor, which
        # takes them once the app has finished launching (launch_documents)
        self._launched = threading.Event()
        self._launched.set()                  # (macopen.install clears it until then)
        self._launch_docs: list[str] = []
        self._launch_taken = False
        self._ready: set[str] = set()         # windows whose editor has started
        self._win_lock = threading.Lock()
        # Recovery copies this process is writing: a lock on each, so another mosaic running
        # at the same time doesn't offer them back as lost work. {key: (lock file, window)}
        self._autosave_locks: dict[str, tuple] = {}
        self._autosaved_at: dict[str, float] = {}   # window -> when it last kept a copy
        self._lock = threading.Lock()
        self._decks: dict[str, dict] = {}     # imported decks, by path or by the key of copied slides
        self._deck_lock = threading.Lock()
        self._thumb_lock = threading.Lock()
        self._index: tuple | None = None      # (folders, when, figure files in them) to relink pictures to
        self._dropped: dict[str, dict] = {}   # slides or shapes dragged in from PowerPoint, until taken
        self._scratch: str | None = None      # the editor self-test's own folder of figure files
        self._updater = None                  # updates.Updater, made when first needed
        self.restart_asked = False            # Restart now chosen (the self-test's window stays open)

    # Windows ----------------------------------------------------------------------------

    @property
    def window(self):
        """The window the current request came from (outside a request, the first one); None in
        browser mode."""
        win = getattr(self._caller, "win", None)
        windows = dict(self._windows)   # (a window can close meanwhile)
        if win in windows:
            return windows[win]
        return next(iter(windows.values()), None)

    @window.setter
    def window(self, w) -> None:
        """One window, as window 1 (or none)."""
        self._windows.clear()
        if w is not None:
            self._windows["1"] = w

    def _caller_win(self) -> str | None:
        win, windows = getattr(self._caller, "win", None), list(self._windows)
        return win if win in windows else next(iter(windows), None)

    def _reserve_window(self) -> str:
        """The number for a window about to open (its editor's URL carries it)."""
        with self._win_lock:
            win = str(self._next_win)
            self._next_win += 1
            return win

    def _add_window(self, win: str, w) -> None:
        self._windows[win] = w

    def _remove_window(self, win: str) -> None:
        """A window closed: forget it, and let go of its recovery copies (still offered back the
        next time mosaic opens, as when it quits)."""
        self._windows.pop(win, None)
        self._win_state.pop(win, None)
        self._ready.discard(win)
        for key, (_, owner) in list(self._autosave_locks.items()):
            if owner == win:
                self._unlock_autosave(key)

    def _show(self, w) -> None:
        if not self.hidden_windows:
            w.show()
        if sys.platform == "darwin":
            from . import macmenu
            macmenu.note_front(w.uid)   # the Mac menu bar's commands go to it (even while hidden)

    def doc_state(self, path: str | None, dirty: bool, name: str | None = None) -> bool:
        """What the calling window has open (its file: opening it again brings this window to
        the front; its name, for the question closing it asks) and whether there are unsaved
        changes (closing it asks first, closing.py; restarting to update keeps a copy)."""
        win = self._caller_win()
        if win is not None:
            self._win_state[win] = {"path": _same_file(path) if path else None, "dirty": bool(dirty), "name": name}
        return self.confirm_close(dirty)

    def _doc_of(self, window) -> dict:
        """What a window has open, as its editor last said ({} before it has)."""
        win = next((k for k, w in list(self._windows.items()) if w is window), None)
        return self._win_state.get(win, {}) if win is not None else {}

    def show_document(self, path: str) -> bool:
        """Bring the window that has this document open to the front; False if none has."""
        key = _same_file(path)
        for win, state in list(self._win_state.items()):
            w = self._windows.get(win)
            if w is not None and state.get("path") == key:
                self._show(w)
                return True
        return False

    def open_window(self, path: str | None = None, slides: list[int] | None = None) -> dict:
        """A new window with this document (a deck's slides chosen: `slides`), or a new blank
        figure; a document open already comes to the front instead. {"opened": False} in
        browser mode, where the editor replaces its figure instead."""
        if self._new_window is None or not self._windows:
            return {"opened": False}
        if path and not path.lower().endswith(DECK_EXTENSIONS) and self.show_document(path):
            return {"shown": True}
        self._new_window(os.path.abspath(os.path.expanduser(path)) if path else None, slides)
        return {"opened": True}

    def close_window(self) -> bool:
        """Close the calling window (one opened for a deck whose slide picker was cancelled), unless
        it's the last."""
        win = self._caller_win()
        if win is None or len(self._windows) < 2:
            return False
        w = self._windows[win]
        w.confirm_close = False
        threading.Timer(0.1, w.destroy).start()   # once this answer is back with the editor
        return True

    def launch_documents(self) -> list[str]:
        """The documents mosaic was opened with by double-clicking them (or Open With, or a
        drop on its Dock icon), for the first editor to open; [] for the others. Waits for the
        app to finish launching, when macOS has handed them over."""
        self._launched.wait(5)
        with self._win_lock:
            win = self._caller_win()
            if win is not None:
                self._ready.add(win)
            if self._launch_taken:
                return []
            self._launch_taken = True
            docs, self._launch_docs = self._launch_docs, []
        return docs

    def _system_open(self, paths: list[str]) -> list[str]:
        """Documents macOS asks mosaic to open while it runs: one open already comes to the
        front, and before any editor has started they wait for the first. Returns the rest, for
        the editor in front to open (macopen.py)."""
        rest = [p for p in paths if p.lower().endswith(DECK_EXTENSIONS) or not self.show_document(p)]
        with self._win_lock:
            if rest and not self._launch_taken:
                self._launch_docs.extend(rest)
                return []
        return rest

    def _ready_uids(self) -> list[str]:
        """The pywebview ids of the windows whose editor has started."""
        return [w.uid for win, w in list(self._windows.items()) if win in self._ready]

    # Utilities ------------------------------------------------------------------------

    def _asset_view(self, assets: dict) -> dict:
        return {aid: {"size_pt": a.get("size_pt"), "page_sizes": a.get("page_sizes")} for aid, a in assets.items()}

    # App ------------------------------------------------------------------------------

    def app_info(self) -> dict:
        from ..journals import JOURNALS, STANDARD_SIZES
        win = self._caller_win()
        return {"version": __version__, "platform": sys.platform, "native": self.window is not None,
                # Opening documents in windows of their own (else the editor replaces its figure),
                # and whether this is the window mosaic opened with (it offers back unsaved work)
                "windows": self._new_window is not None and self.window is not None,
                "first_window": win in (None, "1"),
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

    # A page dragged from one window's Pages list into another (Mac) ------------------------------

    def _page_target(self, at=None):
        """The other window under the pointer, and where the pointer is in it (macdrag.page_target)."""
        if sys.platform != "darwin" or len(self._windows) < 2:
            return None
        from webview.platforms.cocoa import BrowserView

        from . import macdrag
        from .keycheck import on_main
        me, views = self._caller_win(), {}
        for win, w in list(self._windows.items()):
            inst = BrowserView.instances.get(getattr(w, "uid", None))
            if win != me and inst is not None and inst.webview is not None:
                views[win] = inst.webview
        return on_main(lambda: macdrag.page_target(views, at)) if views else None

    def _tell(self, win: str, script: str):
        w = self._windows.get(win)
        return w.evaluate_js(script) if w is not None else None

    def page_drag_over(self, on: bool, at: list | None = None) -> str | None:
        """A page from the calling window's Pages list dragged outside it: the mosaic window under
        the pointer shows where a copy would go, and its document's name comes back; on=False (or
        no window under the pointer any more) takes that away."""
        target = self._page_target(at) if on else None
        last, self._page_over = self._page_over, target[0] if target else None
        if last and last != self._page_over:
            self._tell(last, "window.FA && window.FA.pageDragOver(null, null)")
        if not target:
            return None
        win, x, y = target
        return self._tell(win, f"window.FA && window.FA.pageDragOver({x}, {y})")

    def page_drop(self, got: dict, at: list | None = None) -> dict:
        """Letting go of a page dragged out of the calling window's Pages list (got: it as a
        one-page figure, as figure_pages gives): the mosaic window under the pointer adds a copy
        where it's dropped and comes to the front. {"to": its document's name}, else {}."""
        target = self._page_target(at)
        self.page_drag_over(False)
        if not target:
            return {}
        win, x, y = target
        name = self._tell(win, f"window.FA && window.FA.pageDrop({json.dumps(got)}, {x}, {y})")
        if not name:
            return {}
        self._show(self._windows[win])
        return {"to": name}

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
        """The editor's menus, for the menu bar on a Mac (macmenu.build; once, by the first window
        to ask: they're the same in every window); nothing elsewhere."""
        return self._on_mac_menus("build", self.window, self, spec, self.prefs_get().get("recent", []))

    def menu_checks(self, checks: dict) -> bool:
        """Ticks on the Mac menu bar's items: {action: on}, from the window in front (another
        window's ticks wait until it comes to the front, when it sends them again)."""
        w = self.window
        return self._on_mac_menus("set_checks", checks, w.uid if w is not None else None)

    # Documents -------------------------------------------------------------------------

    def new_document(self) -> dict:
        """A blank figure, its page the size Settings gives new documents."""
        return model.new_document(page=self.prefs_get().get("new_page"))

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
        # Saved by a newer mosaic: saving it here could drop what this version doesn't know
        saved_by = (doc.get("meta") or {}).get("saved_by")
        newer = saved_by if parse_version(saved_by) > parse_version(__version__) else None
        return {"doc": doc, "path": path, "report": [], "newer": newer}

    def figure_pages(self, path: str) -> dict:
        """Another document's pages, to add to the one open (a .mosaic dropped on the window), with
        what they use from that document: pictures, symbols, swatches, text and object styles."""
        path = os.path.abspath(os.path.expanduser(path))
        doc = docfile.load(path)
        return {"name": os.path.splitext(os.path.basename(path))[0], "pages": doc.get("pages", []),
                **{k: doc.get(k) or ({} if k == "assets" else []) for k in
                   ("assets", "symbols", "swatches", "text_styles", "object_styles")}}

    def figure_upload(self, name: str, data_b64: str) -> dict:
        """A .mosaic dropped in the browser (its bytes, with no path to it): its pages, as
        figure_pages."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, os.path.basename(name) or "figure.mosaic")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(data_b64))
            return self.figure_pages(path)

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
        if not path.lower().endswith(docfile.EXTENSIONS):   # (a FigAssemble document saves as itself)
            path += docfile.EXTENSION
        warnings = docfile.save(doc, path)
        self._remember(path)
        return {"path": path, "warnings": warnings}

    def autosave(self, doc: dict, key: str) -> dict:
        d = os.path.join(config_dir(), "autosave")
        os.makedirs(d, exist_ok=True)
        self.claim_autosave(key)
        path = os.path.join(d, f"{key}{docfile.EXTENSION}")
        docfile.save(doc, path, prune=False)
        win = self._caller_win()
        if win is not None:
            self._autosaved_at[win] = time.time()
        return {"path": path}

    def claim_autosave(self, key: str) -> bool:
        """This window is keeping this recovery copy (one it writes, or one recovered): locked,
        so another mosaic running at the same time leaves it alone. The lock goes when the
        window closes or mosaic quits, however it quits."""
        if key in self._autosave_locks:
            return True
        if not key.replace("-", "").isalnum():   # (only mosaic's own names)
            return False
        d = os.path.join(config_dir(), "autosave")
        os.makedirs(d, exist_ok=True)
        fh = open(os.path.join(d, f"{key}.lock"), "a+")
        if not _try_lock(fh):
            fh.close()
            return False
        self._autosave_locks[key] = (fh, self._caller_win())
        return True

    def _unlock_autosave(self, key: str) -> None:
        fh, _ = self._autosave_locks.pop(key, (None, None))
        if fh is None:
            return
        _unlock(fh)
        fh.close()
        try:
            os.remove(fh.name)   # mosaic's own lock file
        except OSError:
            pass   # (Windows: another mosaic is looking at it just then)

    def _kept_elsewhere(self, key: str) -> bool:
        """A recovery copy another window or another mosaic is keeping (locked). The asking
        window's own count as left behind (a document it replaced), as before there were locks."""
        if key in self._autosave_locks:
            owner = self._autosave_locks[key][1]
            return owner is not None and owner != self._caller_win() and owner in self._windows
        path = os.path.join(config_dir(), "autosave", f"{key}.lock")
        if not os.path.exists(path):
            return False
        try:
            fh = open(path, "a+")
        except OSError:
            return False
        with fh:
            if not _try_lock(fh):
                return True
            _unlock(fh)
        return False

    def autosaved(self, exclude_key: str | None = None) -> list[dict]:
        """Recovery copies of unsaved documents, newest first (the current session's left out,
        and any another window or mosaic is still keeping), with what's in each so they can
        be told apart."""
        d = os.path.join(config_dir(), "autosave")
        if not os.path.isdir(d):
            return []
        out = []
        for n in os.listdir(d):
            if not n.endswith(docfile.EXTENSION) or (exclude_key and n == f"{exclude_key}{docfile.EXTENSION}"):
                continue
            if self._kept_elsewhere(n[:-len(docfile.EXTENSION)]):
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
        """Delete recovery copies (only ever files in mosaic's own autosave folder); returns
        the ones left."""
        d = os.path.realpath(os.path.join(config_dir(), "autosave"))
        for p in paths or []:
            real = os.path.realpath(p)
            if os.path.dirname(real) == d and real.endswith(docfile.EXTENSION) and os.path.isfile(real) \
                    and not self._kept_elsewhere(os.path.basename(real)[:-len(docfile.EXTENSION)]):
                os.remove(real)   # mosaic's own autosave file
        return self.autosaved(exclude_key)

    def discard_autosave(self, key: str) -> bool:
        p = os.path.join(config_dir(), "autosave", f"{key}{docfile.EXTENSION}")
        if os.path.exists(p):
            os.remove(p)   # mosaic's own autosave file
        self._unlock_autosave(key)
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
        (mosaic objects from another document), "files" (placed linked), "slides" or
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
        """Set the test clipboard's contents (only with MOSAIC_FAKE_CLIPBOARD)."""
        cb = clipboard.backend()
        if not isinstance(cb, clipboard.FakeClipboard):
            raise PermissionError("only the test clipboard can be set")
        return cb.put(contents)

    def selftest_read(self, path: str) -> str:
        """A test file's bytes as base64, for the editor self-test to drop as data (only while
        testing, with MOSAIC_FAKE_CLIPBOARD)."""
        if not isinstance(clipboard.backend(), clipboard.FakeClipboard):
            raise PermissionError("only while testing")
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")

    def selftest_scratch(self, name: str, data_b64: str) -> str:
        """Write a figure file for the editor self-test into a folder of its own and return its
        path; writing the same name again re-saves it, as R would (only while testing, with
        MOSAIC_FAKE_CLIPBOARD, and only plain file names)."""
        if not isinstance(clipboard.backend(), clipboard.FakeClipboard):
            raise PermissionError("only while testing")
        if not name or os.path.basename(name) != name or name in (".", ".."):
            raise ValueError("a file name, without folders")
        if self._scratch is None:
            self._scratch = tempfile.mkdtemp(prefix="mosaic-selftest-files-")
        path = os.path.join(self._scratch, name)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data_b64))
        return path

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
                    res["outline"] = shape_outline(it)   # (what a click picks it by)
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
            "document": ("mosaic or PowerPoint (*.mosaic;*.figasm;*.pptx;*.pptm;*.potx)", "All files (*.*)"),
            "figures": ("Figures (*.pdf;*.svg;*.png;*.jpg;*.jpeg;*.tif;*.tiff)", "All files (*.*)"),
            "icc": ("ICC profiles (*.icc;*.icm)", "All files (*.*)"),
        }[kind]
        res = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=(kind == "figures"),
                                             file_types=types)
        return list(res) if res else None

    def save_dialog(self, suggested: str = "Untitled.mosaic", directory: str = "") -> str | None:
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
        if self.window is not None:
            self.window.confirm_close = bool(dirty)
        return True

    def open_url(self, url: str) -> bool:
        """A web page in the browser (GitHub's sign-in page, the releases)."""
        if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            return False
        import webbrowser
        return webbrowser.open(url)

    # Updates (updates.py): looked for in the background; the editor asks how it's going ---------

    @property
    def updater(self):
        if self._updater is None:
            from ..updates import Updater
            self._updater = Updater(self.prefs_get)
        return self._updater

    def update_status(self) -> dict:
        return self.updater.status()

    def update_check(self) -> dict:
        """Check now (it looks even with updates switched off)."""
        return self.updater.check(manual=True)

    def update_get(self, which: str = "update") -> dict:
        """Download the update ("update") or the version before this one ("previous"), checked
        and ready to install; then update_restart."""
        from ..updates import UpdateError
        try:
            self.updater.get("previous" if which == "previous" else "update")
        except UpdateError as exc:
            raise RuntimeError(str(exc)) from None
        return self.updater.status()

    def update_restart(self) -> bool:
        """Close mosaic, install the downloaded update and open it again (the editor has dealt
        with unsaved changes first)."""
        if not self.updater.restart_now():
            return False
        self.restart_asked = True
        if self.window is not None and not os.environ.get("MOSAIC_FAKE_CLIPBOARD"):
            self._keep_copies(exclude=self._caller_win())
            windows = list(self._windows.values())
            for w in windows:
                w.confirm_close = False
            threading.Timer(0.3, lambda: [w.destroy() for w in windows]).start()   # once this answer is back with the editor
        return True

    def _keep_copies(self, exclude: str | None = None, wait: float = 10.0) -> None:
        """The other windows' unsaved work kept as recovery copies (offered back when mosaic
        opens again), before they close without asking."""
        asked = {}
        for win, w in list(self._windows.items()):
            if win != exclude and self._win_state.get(win, {}).get("dirty"):
                asked[win] = time.time()
                try:
                    w.evaluate_js("window.FA && window.FA.app.keepCopy()")
                except Exception:   # noqa: BLE001 (a window closing meanwhile)
                    asked.pop(win)
        end = time.time() + wait
        while asked and time.time() < end:
            asked = {win: t for win, t in asked.items() if self._autosaved_at.get(win, 0) < t and win in self._windows}
            time.sleep(0.05)

    def update_skip(self, version: str | None) -> dict:
        """Skip this version (None: install the one skipped after all)."""
        return self.updater.skip(version)

    def update_seen(self) -> dict:
        return self.updater.seen()

    def update_log(self) -> bool:
        """Show the last update's installer log in Finder or Explorer."""
        path = self.updater.status().get("log")
        return bool(path) and self.reveal(path)

    def github_signin_start(self) -> dict:
        from ..updates import UpdateError
        try:
            return self.updater.signin_start()
        except UpdateError as exc:
            raise RuntimeError(str(exc)) from None

    def github_signin_status(self) -> dict | None:
        return self.updater.status().get("signin")

    def github_signin_cancel(self) -> bool:
        self.updater.signin_cancel()
        return True

    def github_signout(self) -> dict:
        self.updater.signout()
        return self.updater.status()

    def selftest_update(self, fake: dict | None) -> dict:
        """Have the updater say what the editor self-test needs (only while testing, with
        MOSAIC_FAKE_CLIPBOARD); None puts it back."""
        if not os.environ.get("MOSAIC_FAKE_CLIPBOARD"):
            raise PermissionError("only for the editor self-test")
        self.updater.fake = fake
        self.updater.restart = False
        self.restart_asked = False
        return self.updater.status()


def asset_preview_key(sha: str, kind: str) -> str:
    return sha + KIND_EXT.get(kind, "." + kind)

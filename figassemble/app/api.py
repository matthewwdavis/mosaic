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

from .. import __version__, docfile, model
from ..assets import KIND_EXT, get_cache, new_asset, new_asset_from_bytes, refresh_asset
from ..fonts import config_dir, get_font_index
from ..resolve import Resolver

PREFS_DEFAULTS = {
    "units": "pt", "page_units": "mm", "ui_scale": 1.0, "theme": "system", "show_tool_labels": True,
    "reduced_motion": False, "snap": True, "default_dpi": 600, "default_formats": ["pdf", "png"],
    "transparent": True, "panel_label": {"size": 8.0, "bold": True, "font": "Helvetica", "case": "lower"},
    "text": {"font": "Helvetica", "size": 6.0}, "stroke_width": 1.0, "recent": [],
}


def _prefs_path() -> str:
    return os.path.join(config_dir(), "prefs.json")


class Api:
    def __init__(self):
        self.window = None          # set by the app window; None in browser mode
        self._lock = threading.Lock()

    # Utilities ------------------------------------------------------------------------

    def _asset_view(self, assets: dict) -> dict:
        return {aid: {"size_pt": a.get("size_pt"), "page_sizes": a.get("page_sizes")} for aid, a in assets.items()}

    # App ------------------------------------------------------------------------------

    def app_info(self) -> dict:
        return {"version": __version__, "platform": sys.platform, "native": self.window is not None,
                "prefs": self.prefs_get(), "page_presets": model.PAGE_PRESETS,
                "machine": platform.node()}

    def fonts(self) -> list[str]:
        return get_font_index().families()

    def prefs_get(self) -> dict:
        prefs = dict(PREFS_DEFAULTS)
        try:
            with open(_prefs_path(), encoding="utf-8") as fh:
                prefs.update(json.load(fh))
        except (OSError, ValueError):
            pass
        return prefs

    def prefs_set(self, prefs: dict) -> dict:
        merged = self.prefs_get()
        merged.update(prefs or {})
        with self._lock, open(_prefs_path(), "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=1)
        return merged

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

    def autosaved(self) -> list[dict]:
        d = os.path.join(config_dir(), "autosave")
        if not os.path.isdir(d):
            return []
        out = []
        for n in sorted(os.listdir(d)):
            if n.endswith(docfile.EXTENSION):
                p = os.path.join(d, n)
                out.append({"path": p, "modified": os.path.getmtime(p)})
        return out

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

    def resolve(self, assets: dict, items: list[dict]) -> list[dict]:
        from ..export.svgwriter import fragment
        resolver = Resolver({"assets": assets}, get_font_index())
        out = []
        for it in items:
            try:
                r = resolver.resolve(it)
                out.append({"id": it.get("id"), "svg": fragment(r, it.get("id", "x")), "bbox": r.bbox,
                            "autofit_frame": r.autofit_frame, "warnings": r.warnings})
            except Exception as exc:
                out.append({"id": it.get("id"), "svg": "", "bbox": None, "warnings": [str(exc)]})
        return out

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
        self._dirty = bool(dirty)
        return True


def asset_preview_key(sha: str, kind: str) -> str:
    return sha + KIND_EXT.get(kind, "." + kind)

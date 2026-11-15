"""Local HTTP server: the editor UI, asset previews and JSON-RPC, on 127.0.0.1 only.

Every URL carries a random token so other programs on the machine can't read through it.
The server itself (the token, the editor's files, the calls) is the shared library's
(_labapp/server.py); this adds what is mosaic's: previews of placed files and the theme.
"""
from __future__ import annotations

import os
import threading

from .._labapp import server as _shared
from ..assets import PDFIUM_LOCK, get_cache

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")
_preview_lock = threading.Lock()


def render_pdf_preview(path: str, page: int, scale: float, out: str) -> None:
    import pypdfium2 as pdfium
    with PDFIUM_LOCK:
        doc = pdfium.PdfDocument(path)
        try:
            im = doc[page].render(scale=scale, fill_color=(0, 0, 0, 0), may_draw_forms=False).to_pil()
            im.save(out + ".tmp.png", "PNG", compress_level=1)
        finally:
            doc.close()
    os.replace(out + ".tmp.png", out)


class Handler(_shared.Handler):
    server_version = "mosaic"
    ui_dir = UI_DIR

    def ui_body(self, path: str, body: bytes) -> bytes:
        if path == os.path.join(UI_DIR, "index.html"):
            # The chosen theme's colours, there from the first paint (no flash of another theme)
            body = body.replace(b'<style id="theme-vars"></style>',
                                f'<style id="theme-vars">{self.server.api.theme_css()}</style>'.encode("utf-8"))
        return body

    def get(self, rest: str, query: dict) -> bool:
        if rest.startswith("asset/"):
            self._asset(rest[6:], query)
            return True
        return False

    def _asset(self, name: str, query: dict) -> None:
        cache = get_cache()
        sha, _, ext = name.partition(".")
        if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
            return self._send(400, b"bad asset", "text/plain")
        kind = {"pdf": "pdf", "svg": "svg", "png": "png", "jpg": "jpeg", "tif": "tiff"}.get(ext)
        src = cache.path(sha, kind) if kind else None
        if not src or not os.path.exists(src):
            return self._send(404, b"missing", "text/plain")
        if kind == "pdf":
            try:
                page = int(query.get("page", ["0"])[0])
                scale = min(max(float(query.get("scale", ["2"])[0]), 0.25), 16.0)
            except ValueError:
                return self._send(400, b"bad page or scale", "text/plain")
            if not 0 <= page < 100000 or scale != scale:   # (scale != scale: not a number)
                return self._send(400, b"bad page or scale", "text/plain")
            out = cache.derived(f"{sha}.p{page}.s{scale:g}", ".png")
            with _preview_lock:
                if not os.path.exists(out):
                    render_pdf_preview(src, page, scale, out)
            with open(out, "rb") as fh:
                return self._send(200, fh.read(), "image/png", cache=True)
        if kind == "tiff":
            out = cache.derived(sha + ".view", ".png")
            with _preview_lock:   # (two requests for one picture at once: made once)
                if not os.path.exists(out):
                    from PIL import Image
                    with Image.open(src) as im:
                        im.save(out + ".tmp.png", "PNG")
                    os.replace(out + ".tmp.png", out)
            with open(out, "rb") as fh:
                return self._send(200, fh.read(), "image/png", cache=True)
        ctype = {"svg": "image/svg+xml", "png": "image/png", "jpeg": "image/jpeg"}[kind]
        with open(src, "rb") as fh:
            self._send(200, fh.read(), ctype, cache=True)


class AppServer(_shared.AppServer):
    def __init__(self, api, port: int = 0):
        # (the self-test's helpers, selftest_*, answer only while testing, as they check themselves)
        super().__init__(api, Handler, port, testing=bool(os.environ.get("MOSAIC_FAKE_CLIPBOARD")))


def start_server(api, port: int = 0) -> AppServer:
    srv = AppServer(api, port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

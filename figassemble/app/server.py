"""Local HTTP server: the editor UI, asset previews and JSON-RPC, on 127.0.0.1 only.

Every URL carries a random token so other programs on the machine can't read through it.
"""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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


class Handler(BaseHTTPRequestHandler):
    server_version = "FigAssemble"

    def log_message(self, fmt, *args):   # keep the terminal quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str, cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=31536000, immutable" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _check(self) -> str | None:
        parts = urlparse(self.path).path.split("/", 2)
        if len(parts) < 2 or parts[1] != self.server.token:
            self._send(403, b"forbidden", "text/plain")
            return None
        return parts[2] if len(parts) > 2 else ""

    def do_GET(self):
        rest = self._check()
        if rest is None:
            return
        url = urlparse(self.path)
        if rest in ("", "index.html"):
            rest = "ui/index.html"
        if rest.startswith("ui/"):
            path = os.path.normpath(os.path.join(UI_DIR, rest[3:]))
            if not path.startswith(UI_DIR) or not os.path.isfile(path):
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if path.endswith(".js"):
                ctype = "text/javascript"
            with open(path, "rb") as fh:
                body = fh.read()
            if path == os.path.join(UI_DIR, "index.html"):
                # The chosen theme's colours, there from the first paint (no flash of another theme)
                body = body.replace(b'<style id="theme-vars"></style>',
                                    f'<style id="theme-vars">{self.server.api.theme_css()}</style>'.encode("utf-8"))
            return self._send(200, body, ctype)
        if rest.startswith("asset/"):
            return self._asset(rest[6:], parse_qs(url.query))
        self._send(404, b"not found", "text/plain")

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
            page = int(query.get("page", ["0"])[0])
            scale = min(max(float(query.get("scale", ["2"])[0]), 0.25), 16.0)
            out = cache.derived(f"{sha}.p{page}.s{scale:g}", ".png")
            with _preview_lock:
                if not os.path.exists(out):
                    render_pdf_preview(src, page, scale, out)
            with open(out, "rb") as fh:
                return self._send(200, fh.read(), "image/png", cache=True)
        if kind == "tiff":
            out = cache.derived(sha + ".view", ".png")
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

    def do_POST(self):
        rest = self._check()
        if rest is None:
            return
        if rest != "rpc":
            return self._send(404, b"not found", "text/plain")
        length = int(self.headers.get("Content-Length", "0"))
        caller = getattr(self.server.api, "_caller", None)   # the window asking (each request has its own thread)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
            method = req.get("method", "")
            fn = getattr(self.server.api, method, None)
            if method.startswith("_") or not callable(fn):
                raise ValueError(f"unknown method {method}")
            if caller is not None:
                caller.win = req.get("win")
            result = fn(*req.get("args", []), **req.get("kwargs", {}))
            body = json.dumps({"result": result}).encode("utf-8")
        except Exception as exc:
            body = json.dumps({"error": f"{type(exc).__name__}: {exc}",
                               "trace": traceback.format_exc()[-2000:]}).encode("utf-8")
        finally:
            if caller is not None:
                caller.win = None
        self._send(200, body, "application/json")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, api, port: int = 0):
        super().__init__(("127.0.0.1", port), Handler)
        self.api = api
        self.token = secrets.token_urlsafe(16)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/{self.token}/"


def start_server(api, port: int = 0) -> AppServer:
    srv = AppServer(api, port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

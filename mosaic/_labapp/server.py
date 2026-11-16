"""The local server between an app's Python and its editor (a web page): the editor's files, and
its calls into Python as JSON over POST, on 127.0.0.1 only. Every URL carries a random token, so
other programs on the computer can't read or call through it.

An app subclasses Handler for what else it serves (previews of placed files, pictures of pages):

    class Handler(server.Handler):
        ui_dir = UI_DIR
        def get(self, rest, query):          # rest: the path after the token; True when answered
            if rest.startswith("asset/"): ...

    srv = server.start_server(api, Handler)  # srv.url is what the window opens

Calls: POST <url>rpc {"method", "args", "kwargs", "win"} -> {"result"} or {"error", "trace"}.
A method is callable when it's public (no leading underscore), not in the handler's `hidden`
names, and the server's allowed(method) agrees.
"""
from __future__ import annotations

import errno
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

MAX_BODY = 512 * 1024 * 1024   # (a call's size: a pasted picture comes through here)
CHUNK = 64 * 1024              # (what's handed to the network at a time)
# macOS answers "No buffer space available" (ENOBUFS) when many answers go out at once (a window
# opening: its files, previews and pages together); the answer is sent again a moment later
RETRY = (errno.ENOBUFS, errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR)
RETRY_FOR = 5.0                # seconds, before giving up on one answer


class Handler(BaseHTTPRequestHandler):
    server_version = "app"
    ui_dir = ""                    # the folder of the editor's files, served under ui/
    hidden: tuple = ()             # public methods of the api the editor may not call
    csp: str | None = None         # a Content-Security-Policy for the editor's page, if any

    def log_message(self, fmt, *args):   # keep the terminal quiet
        pass

    def send(self, code: int, body: bytes, ctype: str, cache: bool = False, headers: dict | None = None) -> bool:
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=31536000, immutable" if cache else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.write_all(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):   # (its window closed meanwhile)
            pass
        return True

    _send = send   # (the name the apps' handlers used before)

    def write_all(self, data: bytes) -> None:
        """Send data in pieces, each again after a short wait when the system is out of buffer
        space for a moment (ENOBUFS), so a busy start-up doesn't lose an answer."""
        view = memoryview(data)
        give_up = None
        while view:
            try:
                n = self.connection.send(view[:CHUNK])
            except OSError as exc:
                if exc.errno not in RETRY:
                    raise
                give_up = give_up or time.monotonic() + RETRY_FOR
                if time.monotonic() > give_up:
                    raise
                time.sleep(0.005)
                continue
            view = view[n:]
            give_up = None

    def flush_headers(self):   # (the headers, sent the same way)
        if hasattr(self, "_headers_buffer"):
            data = b"".join(self._headers_buffer)
            self._headers_buffer = []
            self.write_all(data)

    def rest(self) -> str | None:
        """The path after the token; None (and a 403 sent) without the right token."""
        parts = urlparse(self.path).path.split("/", 2)
        if len(parts) < 2 or not secrets.compare_digest(parts[1].encode("utf-8", "replace"), self.server.token.encode()):
            self.send(403, b"forbidden", "text/plain")
            return None
        return unquote(parts[2]) if len(parts) > 2 else ""

    # What an app changes ----------------------------------------------------------------------

    def get(self, rest: str, query: dict) -> bool:
        """Anything else the app serves; True when it answered."""
        return False

    def ui_file(self, rel: str) -> str:
        """The file to serve for ui/<rel> (an app may give another: a test build of the editor)."""
        return rel

    def ui_body(self, path: str, body: bytes) -> bytes:
        """A file of the editor's as it's sent (an app may fill in the first page)."""
        return body

    def error_text(self, exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"

    # GET ---------------------------------------------------------------------------------------

    def do_GET(self):
        rest = self.rest()
        if rest is None:
            return
        query = parse_qs(urlparse(self.path).query)
        if rest in ("", "index.html"):
            rest = "ui/index.html"
        try:
            if rest.startswith("ui/"):
                return self._ui(rest[3:])
            if self.get(rest, query):
                return
        except (KeyError, FileNotFoundError, ValueError):
            self.send(404, b"not found", "text/plain")
            return
        self.send(404, b"not found", "text/plain")

    def _ui(self, rel: str) -> None:
        root = os.path.abspath(self.ui_dir)
        path = os.path.normpath(os.path.join(root, self.ui_file(rel)))
        if not self.ui_dir or not path.startswith(root + os.sep) or not os.path.isfile(path):   # (only files inside the folder)
            self.send(404, b"not found", "text/plain")
            return
        ctype = "text/javascript" if path.endswith((".js", ".mjs")) else (mimetypes.guess_type(path)[0] or "application/octet-stream")
        with open(path, "rb") as fh:
            body = self.ui_body(path, fh.read())
        page = path == os.path.join(root, "index.html")
        self.send(200, body, ctype, headers={"Content-Security-Policy": self.csp} if page and self.csp else None)

    # POST: the editor's calls -------------------------------------------------------------------

    def do_POST(self):
        rest = self.rest()
        if rest is None:
            return
        if rest != "rpc":
            self.send(404, b"not found", "text/plain")
            return
        api = self.server.api
        caller = getattr(api, "_caller", None)   # the window asking (each request has its own thread)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= MAX_BODY:
                raise ValueError("the request is too large")
            req = json.loads(self.rfile.read(length) or b"{}")
            method = req.get("method", "")
            fn = getattr(api, method, None) if isinstance(method, str) else None
            if not isinstance(method, str) or method.startswith("_") or method in self.hidden or not callable(fn) \
                    or not self.server.allowed(method):
                raise ValueError(f"unknown method {method}")
            if caller is not None:
                caller.win = req.get("win")
            result = fn(*req.get("args", []), **req.get("kwargs", {}))
            body = json.dumps({"result": result}).encode("utf-8")
        except Exception as exc:   # noqa: BLE001 (the editor shows the message)
            body = json.dumps({"error": self.error_text(exc), "trace": traceback.format_exc()[-2000:]}).encode("utf-8")
        finally:
            if caller is not None:
                caller.win = None
        self.send(200, body, "application/json")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    # Connections waiting to be taken: the editor opens one per request, in bursts (a page of
    # previews, several windows), and Windows refuses those past this number outright, which the
    # editor sees as a request that failed. Python's own 5 was met by mosaic's self-test on Windows
    request_queue_size = 128

    def __init__(self, api, handler=Handler, port: int = 0, testing: bool = False, test_prefix: str = "selftest_"):
        super().__init__(("127.0.0.1", port), handler)
        self.api = api
        self.token = secrets.token_urlsafe(16)
        self.testing, self.test_prefix = testing, test_prefix

    def handle_error(self, request, client_address):
        """A request that failed, written to the log as one piece (threads answering at once
        otherwise mix their tracebacks line by line)."""
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return   # (the window went away mid-answer)
        text = f"---- a request from {client_address} failed\n{traceback.format_exc()}"
        try:
            sys.stderr.write(text if text.endswith("\n") else text + "\n")
        except Exception:   # noqa: BLE001 (nowhere to write it)
            pass

    def allowed(self, method: str) -> bool:
        """The self-test's helpers (which may write files where they're told) answer only during
        the self-test."""
        return self.testing or not (self.test_prefix and method.startswith(self.test_prefix))

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/{self.token}/"


def start_server(api, handler=Handler, port: int = 0, testing: bool = False, test_prefix: str = "selftest_") -> AppServer:
    srv = AppServer(api, handler, port, testing, test_prefix)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

"""The app window (pywebview: WebKit on macOS, Edge WebView2 on Windows), with native file
drag and drop so dropped figures can stay linked to their files."""
from __future__ import annotations

import json
import os
import sys
import time
import webbrowser
from urllib.parse import quote

from .api import Api
from .server import start_server


def run_app(document: str | None = None, browser: bool = False, port: int = 0) -> int:
    api = Api()
    srv = start_server(api, port)
    url = srv.url + "ui/index.html"
    if document:
        url += "?open=" + quote(os.path.abspath(document))
    if browser:
        print(f"FigAssemble is running at {url}\nPress Ctrl+C to stop.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    import webview
    from webview.dom import DOMEventHandler

    window = webview.create_window("FigAssemble", url, width=1440, height=920, min_size=(960, 640),
                                   background_color="#F4F4F2", text_select=False)
    api.window = window
    api._dirty = False

    def on_drop(event):
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if not paths:
            return
        payload = {"paths": paths, "x": event.get("clientX", 0), "y": event.get("clientY", 0),
                   "embed": bool(event.get("altKey"))}
        window.evaluate_js(f"window.FA && window.FA.onNativeDrop({json.dumps(payload)})")

    def on_loaded():
        doc = window.dom.document
        doc.events.dragover += DOMEventHandler(lambda e: None, prevent_default=True)
        doc.events.drop += DOMEventHandler(on_drop, prevent_default=True, stop_propagation=True)

    def on_closing():
        if not getattr(api, "_dirty", False):
            return True
        return window.create_confirmation_dialog(
            "Close FigAssemble?", "This document has unsaved changes. Close anyway?")

    window.events.loaded += on_loaded
    window.events.closing += on_closing
    webview.start(debug=bool(os.environ.get("FIGASSEMBLE_DEBUG")))
    return 0


if __name__ == "__main__":
    sys.exit(run_app(sys.argv[1] if len(sys.argv) > 1 else None))

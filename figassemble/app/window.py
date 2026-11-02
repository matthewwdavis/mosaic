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
    extra = os.environ.get("FIGASSEMBLE_SMOKE_QUERY")   # e.g. the editor self-test, for testing
    if extra:
        url += ("&" if "?" in url else "?") + extra
        if "selftest" in extra:
            os.environ["FIGASSEMBLE_FAKE_CLIPBOARD"] = "1"   # the self-test's own clipboard, not the system's
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

    if sys.platform == "darwin":
        # The menu bar's name: macOS would call an app started from a terminal "python"
        try:
            from . import macmenu
            macmenu.name_app()
        except Exception as exc:   # noqa: BLE001 (it just keeps Python's name)
            print(f"Couldn't name the app: {exc}", file=sys.stderr, flush=True)
    smoke = bool(os.environ.get("FIGASSEMBLE_SMOKETEST"))
    # Updates: looked for shortly after starting and every few hours (not while testing); one
    # downloaded installs when this window closes (updates.py)
    updater = api.updater
    updater.register()
    if not smoke and not os.environ.get("FIGASSEMBLE_NO_UPDATES"):
        updater.start()
    window = webview.create_window("FigAssemble", url, width=1440, height=920, min_size=(960, 640),
                                   background_color="#F4F4F2", text_select=False, hidden=smoke)
    api.window = window
    api._dirty = False

    def on_drop(event):
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if not paths:
            return
        payload = {"paths": paths, "x": event.get("clientX", 0), "y": event.get("clientY", 0),
                   "embed": bool(event.get("altKey")), "shift": bool(event.get("shiftKey"))}
        window.evaluate_js(f"window.FA && window.FA.onNativeDrop({json.dumps(payload)})")

    def on_loaded():
        # The page itself allows drops (dragover); this handler receives the full file paths
        window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True, stop_propagation=True)
        if sys.platform == "darwin":
            # Slides and shapes dragged out of PowerPoint, which the web view wouldn't take
            from PyObjCTools import AppHelper

            from . import macdrag

            def install():
                try:
                    macdrag.install(window, api)
                except Exception as exc:   # noqa: BLE001 (drags from PowerPoint just aren't taken)
                    print(f"PowerPoint drags unavailable: {exc}", file=sys.stderr, flush=True)
            AppHelper.callAfter(install)

    def smoke_check():
        """Hidden-window check that the editor starts in this platform's web view."""
        ready = False
        for _ in range(150):
            time.sleep(0.2)
            try:
                ready = window.evaluate_js("document.body.classList.contains('ready')")
            except Exception:
                ready = False
            if ready:
                break
        if ready and "selftest" in (extra or ""):
            # A hidden window's timers run slowly, and the self-test has many short waits (it took
            # 400 s in November 2026): up to 15 minutes
            for _ in range(4500):
                time.sleep(0.2)
                if window.evaluate_js("document.body.dataset.selftest || ''"):
                    break
            print("SELFTEST " + str(window.evaluate_js("JSON.stringify(window.__selftest || null)")), flush=True)
        errors = window.evaluate_js("JSON.stringify(window.__faErrors || [])") if ready is not None else "[]"
        print(f"SMOKE {'ready' if ready else 'NOT READY'} errors={errors}", flush=True)
        if ready and "selftest" not in (extra or ""):
            # An edit must switch on the close confirmation (and saving would switch it off)
            before = window.confirm_close
            window.evaluate_js("window.FA.app.run('addPage')")
            for _ in range(50):
                time.sleep(0.1)
                if window.confirm_close:
                    break
            print(f"SMOKE close confirmation: {before} before an edit, {window.confirm_close} after", flush=True)
            if sys.platform == "darwin":
                # Real key presses, through AppKit and pywebview, must reach the editor's shortcuts
                from webview.platforms.cocoa import BrowserView
                from . import keycheck
                keys = keycheck.run(window, BrowserView.instances[window.uid].window)
                print(f"SMOKE keys: {keys['passed']} of {keys['total']} passed"
                      + (f"; failed: {json.dumps(keys['failed'])}" if keys["failed"] else ""), flush=True)
                # Slides and shapes dragged out of PowerPoint (with the repository's test files)
                data = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "data", "powerpoint")
                if os.path.isdir(data):
                    from . import macdrag
                    drags = macdrag.smoke(window, data)
                    print(f"SMOKE PowerPoint drags: {drags['passed']} of {drags['total']} passed"
                          + (f"; failed: {json.dumps(drags['failed'])}" if drags["failed"] else ""), flush=True)
                # The menu bar: its menus, name and shortcuts, and an item doing its command
                from . import macmenu
                menus = macmenu.smoke(window)
                print(f"SMOKE menus: {menus['passed']} of {menus['total']} passed"
                      + (f"; failed: {json.dumps(menus['failed'])}" if menus["failed"] else ""), flush=True)
        closing_started[0] = time.time()
        window.destroy()

    window.events.loaded += on_loaded
    # Unsaved changes: pywebview's own close confirmation (Api.confirm_close switches it on).
    # It runs on the main thread itself; asking for a dialog from a closing handler instead
    # deadlocks, because that handler already holds the main thread.
    wording = {"global.quitConfirmation": "This figure has unsaved changes. Close without saving?",
               "global.quit": "Close without saving"}
    if smoke:
        closing_started = [0.0]
        webview.start(smoke_check, localization=wording)
        print(f"SMOKE window closed in {time.time() - closing_started[0]:.2f} s", flush=True)
    else:
        webview.start(debug=bool(os.environ.get("FIGASSEMBLE_DEBUG")), localization=wording)
    updater.stop()
    try:
        updater.on_quit()
    except Exception as exc:   # noqa: BLE001 (it tries again at the next quit)
        print(f"The update couldn't start installing: {exc}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_app(sys.argv[1] if len(sys.argv) > 1 else None))

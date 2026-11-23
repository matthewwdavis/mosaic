"""The app's windows (pywebview: WebKit on macOS, Edge WebView2 on Windows), with native file
drag and drop so dropped figures can stay linked to their files.

Each document has a window of its own, all in one process sharing one engine (Api, server.py):
New and Open open another window unless the one in front is blank (main.js), a document open
already comes to the front, and closing the last window quits. On a Mac, documents
double-clicked in the Finder come as Apple events (macopen.py); on Windows each starts
mosaic with the document on the command line, in a process of its own.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import webbrowser
from urllib.parse import parse_qs, quote, urlencode

from ..assets import get_cache
from . import closing
from .api import Api
from .server import start_server


def run_app(document: str | None = None, browser: bool = False, port: int = 0) -> int:
    from .. import diagnostics
    diagnostics.start_log()   # what mosaic prints is kept too, for Help > Report a Problem
    api = Api()
    left = threading.Lock()

    def leaving():
        """mosaic is closing (once, however it closes): a downloaded update starts installing."""
        if not left.acquire(blocking=False):
            return
        api.updater.stop()
        try:
            api.updater.on_quit()
        except Exception as exc:   # noqa: BLE001 (it tries again at the next quit)
            print(f"The update couldn't start installing: {exc}", file=sys.stderr, flush=True)

    # Previews and conversions nothing has used for a month go (in the background; each is made again if wanted)
    threading.Thread(target=lambda: get_cache().prune_derived(), daemon=True).start()
    extra = os.environ.get("MOSAIC_SMOKE_QUERY")   # e.g. the editor self-test, for testing
    if extra and "selftest" in extra:
        # the self-test's own clipboard, not the system's (set before the server starts, which
        # lets the self-test's helpers answer only then)
        os.environ["MOSAIC_FAKE_CLIPBOARD"] = "1"
        if "out" not in parse_qs(extra):   # a folder for the files it saves (figures to drop, exports)
            extra += "&out=" + quote(tempfile.mkdtemp(prefix="mosaic-selftest-"))
    srv = start_server(api, port)
    base = srv.url + "ui/index.html"
    if browser:
        url = base + ("?open=" + quote(os.path.abspath(document)) if document else "")
        if extra:
            url += ("&" if "?" in url else "?") + extra
        print(f"mosaic is running at {url}\nPress Ctrl+C to stop.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    if sys.platform == "win32":
        from . import winruntime
        if not winruntime.ensure():   # (no WebView2: said so, with where to get it)
            return 1
    import webview
    from webview.dom import DOMEventHandler

    if sys.platform == "darwin":
        # The menu bar's name: macOS would call an app started from a terminal "python"
        try:
            from . import macmenu
            macmenu.name_app()
        except Exception as exc:   # noqa: BLE001 (it just keeps Python's name)
            print(f"Couldn't name the app: {exc}", file=sys.stderr, flush=True)
        # Documents double-clicked in the Finder, from the start
        try:
            from . import macopen
            macopen.install(api)
        except Exception as exc:   # noqa: BLE001 (they then don't open; File > Open still does)
            print(f"Documents from the Finder unavailable: {exc}", file=sys.stderr, flush=True)
        # The Mac's own writing help off in text boxes (macOS 27's underlines under words, spelling
        # corrected as you type, its smart quotes), before the first window: _labapp/mac/writinghelp.py
        try:
            from .._labapp.mac import writinghelp
            writinghelp.start(False)
        except Exception as exc:   # noqa: BLE001 (the Mac's own then)
            print(f"Couldn't turn off the Mac's writing help: {exc}", file=sys.stderr, flush=True)
        # Quitting with unsaved changes asks about each figure, with Save (macclose.py)
        try:
            from . import macclose
            macclose.install(api, leaving)   # (Quit ends the app there: nothing after webview.start() runs)
        except Exception as exc:   # noqa: BLE001 (pywebview's own question asks instead)
            print(f"Asking before quitting unavailable: {exc}", file=sys.stderr, flush=True)
    smoke = os.environ.get("MOSAIC_SMOKETEST", "")
    api.hidden_windows = bool(smoke) and not os.environ.get("MOSAIC_SMOKE_SHOW")   # (shown, where a hidden one won't load)
    # Updates: looked for shortly after starting and every few hours (not while testing); one
    # downloaded installs when the last window closes (updates.py)
    updater = api.updater
    updater.register()
    if not smoke and not os.environ.get("MOSAIC_NO_UPDATES"):
        updater.start()

    def on_drop(window, event):
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if not paths:
            return
        payload = {"paths": paths, "x": event.get("clientX", 0), "y": event.get("clientY", 0),
                   "embed": bool(event.get("altKey")), "shift": bool(event.get("shiftKey"))}
        window.evaluate_js(f"window.FA && window.FA.onNativeDrop({json.dumps(payload)})")

    def on_loaded(window):
        # The page itself allows drops (dragover); this handler receives the full file paths
        window.dom.document.events.drop += DOMEventHandler(lambda e: on_drop(window, e), prevent_default=True,
                                                           stop_propagation=True)
        if sys.platform == "darwin":
            # Slides and shapes dragged out of PowerPoint, which the web view wouldn't take
            from PyObjCTools import AppHelper

            from . import macdrag

            def install():
                try:
                    macdrag.install(window, api)
                except Exception as exc:   # noqa: BLE001 (drags from PowerPoint just aren't taken)
                    print(f"PowerPoint drags unavailable: {exc}", file=sys.stderr, flush=True)
                try:   # the Dock icon in the system's appearance: light, or dark in Dark mode
                    from .. import icon
                    from .._labapp.mac import dockicon
                    if "light" not in dockicon._state:
                        dockicon.follow(icon.png(512, "light"), icon.png(512, "dark"))
                except Exception as exc:   # noqa: BLE001 (the icon just stays the app's own)
                    print(f"The Dock icon couldn't follow the system's appearance: {exc}", file=sys.stderr, flush=True)
                try:   # the Mac's own writing help off in this window too (its Always-On Proofreading)
                    from webview.platforms.cocoa import BrowserView

                    from .._labapp.mac import writinghelp
                    inst = BrowserView.instances.get(window.uid)
                    if inst is not None and inst.webview is not None:
                        writinghelp.prepare(inst.webview, False)
                except Exception as exc:   # noqa: BLE001 (the Mac's own then)
                    print(f"Couldn't turn off the Mac's writing help in a window: {exc}", file=sys.stderr, flush=True)
                try:   # the file's name in the title bar: double-click to rename, right-click for its menu
                    from . import mactitle
                    mactitle.install(api)
                except Exception as exc:   # noqa: BLE001 (the title bar just stays macOS's own)
                    print(f"Title bar renaming unavailable: {exc}", file=sys.stderr, flush=True)
            AppHelper.callAfter(install)

    def make_window(doc: str | None = None, slides: list[int] | None = None, first: bool = False):
        """A window with its editor: this document (a deck's chosen slides), else a blank figure.
        Its number goes with the editor's every request."""
        win = api._reserve_window()
        query = {"win": win}
        if doc:
            query["open"] = os.path.abspath(doc)
        if slides:
            query["slides"] = ",".join(str(n) for n in slides)
        url = base + "?" + urlencode(query, quote_via=quote)
        if first and extra:
            url += "&" + extra
        window = webview.create_window("mosaic", url, width=1440, height=920, min_size=(960, 640),
                                       background_color="#F4F4F2", text_select=False, hidden=api.hidden_windows)
        api._add_window(win, window)
        window.events.loaded += lambda: on_loaded(window)
        window.events.closing += lambda: closing.on_closing(api, window)   # unsaved changes: Save, Don't Save or Cancel
        window.events.closed += lambda: api._remove_window(win)
        return window

    api._new_window = lambda doc, slides: make_window(doc, slides)
    window = make_window(document, first=True)

    def close_all():
        """The checks' windows closed without the question about unsaved changes (nobody's there to answer)."""
        for w in list(api._windows.values()):
            w.confirm_close = False
            w.destroy()

    def wait_ready(w, tries=150):
        for _ in range(tries):
            time.sleep(0.2)
            try:
                if w.evaluate_js("document.body.classList.contains('ready')"):
                    return True
            except Exception:   # noqa: BLE001 (still loading)
                pass
        return False

    def launch_check():
        """Hidden-window check that mosaic opened with documents (started by `open`, as a
        double-click starts it, for testing): which windows have which documents."""
        ready = wait_ready(window)
        for _ in range(50):   # the documents' windows open and load
            time.sleep(0.2)
            if api._launch_taken and len(api._ready) == len(api._windows):
                break
        time.sleep(1.0)
        docs = []
        for _, w in sorted(api._windows.items(), key=lambda kv: int(kv[0])):
            try:
                docs.append(w.evaluate_js("window.FA.store.path || window.FA.store.doc.meta.title"))
            except Exception:   # noqa: BLE001
                docs.append(None)
        print(f"SMOKE launch: {json.dumps({'ready': ready, 'windows': len(docs), 'documents': docs})}", flush=True)
        closing_started[0] = time.time()
        close_all()

    def title_smoke(window):
        """The title bar's name: double-click to rename, right-click for its menu (mactitle.py)."""
        import tempfile
        from . import mactitle
        with tempfile.TemporaryDirectory() as folder:
            got = mactitle.smoke(window, folder)
        print(f"SMOKE title bar: {got['passed']} of {got['total']} passed"
              + (f"; failed: {json.dumps(got['failed'])}" if got["failed"] else ""), flush=True)

    def smoke_check():
        """Hidden-window check that the editor starts in this platform's web view."""
        print("SMOKE the window's thread is running; waiting for the editor", flush=True)
        ready = wait_ready(window)
        if ready and "selftest" in (extra or ""):
            # A hidden window's timers run slowly, and the self-test has many short waits (it took
            # 400 s in November 2026, 16 min by 11-13 with autosave's and progress's real waits): up to 30 minutes
            for _ in range(9000):
                time.sleep(0.2)
                if window.evaluate_js("document.body.dataset.selftest || ''"):
                    break
            print("SELFTEST " + str(window.evaluate_js("JSON.stringify(window.__selftest || null)")), flush=True)
            if sys.platform == "darwin" and "titlecheck" in extra:   # (also in the full run below)
                title_smoke(window)
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
                from webview.platforms.cocoa import BrowserView
                # The Mac's own writing help off: no underlines under words, corrections, smart
                # quotes or predictions in the window and its text boxes (_labapp/mac/writinghelp.py)
                from .._labapp.mac import on_main, writinghelp
                native = on_main(lambda: writinghelp.state(BrowserView.instances[window.uid].webview))
                page = window.evaluate_js("[document.documentElement.getAttribute('writingsuggestions'), "
                                          "document.querySelector('.text-editor')?.getAttribute('writingsuggestions'), "
                                          "document.querySelector('.text-editor')?.getAttribute('autocorrect')].join('/')")
                off = all(v in (None, False) for v in native.values()) and "proofreading" in native
                print(f"SMOKE writing help: {'off' if off and page == 'false/false/off' else 'NOT off'} "
                      f"{json.dumps(native)} page={page}", flush=True)
                # Real key presses, through AppKit and pywebview, must reach the editor's shortcuts
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
                title_smoke(window)
                # Liquid Glass: the system's glass behind the page at each level, Off solid again (_labapp/mac/glass.py)
                from .._labapp.mac import glass as macglass
                got = macglass.smoke(window, window.evaluate_js("window.FA.glass.state?.effective || 'standard'"))
                print(f"SMOKE glass: {got['passed']} of {got['total']} passed"
                      + (f"; failed: {json.dumps(got['failed'])}" if got["failed"] else ""), flush=True)
                window.evaluate_js("window.FA.glass.apply()")   # (the page's own tint back on the title bar)
                # Documents from the Finder and windows: New, Open, menus, closing, dropping a mosaic document
                import tempfile

                from . import macopen
                with tempfile.TemporaryDirectory() as scratch:
                    wins = macopen.smoke(api, window, scratch)
                print(f"SMOKE windows: {wins['passed']} of {wins['total']} passed"
                      + (f"; failed: {json.dumps(wins['failed'])}" if wins["failed"] else ""), flush=True)
                # Closing and quitting with unsaved changes: the question and what its answers do
                from . import macclose
                with tempfile.TemporaryDirectory() as scratch:
                    closes = macclose.smoke(api, window, scratch)
                print(f"SMOKE closing: {closes['passed']} of {closes['total']} passed"
                      + (f"; failed: {json.dumps(closes['failed'])}" if closes["failed"] else ""), flush=True)
        closing_started[0] = time.time()
        close_all()

    # Unsaved changes: closing asks Save, Don't Save or Cancel (closing.py; Api.confirm_close
    # says when). pywebview's own two-button question, worded here, asks only should that fail.
    wording = {"global.quitConfirmation": "This figure has unsaved changes. Close without saving?",
               "global.quit": "Close without saving"}
    if smoke:
        print(f"SMOKE starting the window ({'hidden' if api.hidden_windows else 'shown'})", flush=True)
        closing_started = [0.0]
        webview.start(launch_check if smoke == "launch" else smoke_check, localization=wording)
        print(f"SMOKE window closed in {time.time() - closing_started[0]:.2f} s", flush=True)
    else:
        webview.start(debug=bool(os.environ.get("MOSAIC_DEBUG")), localization=wording)
    leaving()
    return 0


if __name__ == "__main__":
    sys.exit(run_app(sys.argv[1] if len(sys.argv) > 1 else None))

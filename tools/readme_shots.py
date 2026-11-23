"""The README's window pictures, light and dark, taken in the real Mac window (glass and all).

    python tools/readme_shots.py            (Mac only; writes docs/images/readme-window-{light,dark}.png)

doc_shots.py takes the guide's pictures in headless Chrome, which has no Mac window around the
editor and no glass. This opens mosaic itself twice (a scratch MOSAIC_HOME each time, so your own
settings and documents aren't touched), builds the tutorial figure with the "window" scene of
mosaic/ui/js/docshots.js in that theme, and takes the window as the screen shows it over a soft
backdrop, its shadow included. Only mosaic's own windows are in the picture (other apps' windows
and the desktop never are), but the window does come to the front for a few seconds while each
picture is taken, and the screen must be on and unlocked. The window is 1440 x 880 points: the
screen needs to be at least 1500 x 950 points.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images")
PAD = 30                     # points of backdrop around the window
FRAME = (36, 34, 1440, 880)  # the window's place and size on the screen, in points
WIDTH = 1600                 # the saved picture's width in pixels
BACKDROP = {
    "light": "linear-gradient(135deg, #d9e6f6 0%, #eef1f6 50%, #f3e3ec 100%)",
    "dark": "linear-gradient(135deg, #1c2638 0%, #23232b 50%, #33222e 100%)",
}


def _capture(window, path: str, behind: str) -> bool:
    """The window and a backdrop window of our own just behind it, PAD points around, as a PNG."""
    import AppKit
    import Quartz
    import WebKit
    from mosaic._labapp.mac import glass as macglass, on_main
    nswindow, _ = macglass._views(window)
    made = {}

    def put_behind():
        f = nswindow.frame()
        back = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(f.origin.x - 2 * PAD, f.origin.y - 2 * PAD, f.size.width + 4 * PAD, f.size.height + 4 * PAD),
            0, AppKit.NSBackingStoreBuffered, False)
        back.setReleasedWhenClosed_(False)
        view = WebKit.WKWebView.alloc().initWithFrame_configuration_(back.contentView().bounds(), WebKit.WKWebViewConfiguration.alloc().init())
        view.loadHTMLString_baseURL_(f"<body style='margin:0;height:100vh;background:{behind}'></body>", None)
        back.setContentView_(view)
        back.orderWindow_relativeTo_(AppKit.NSWindowBelow, nswindow.windowNumber())
        made["back"] = back

    def shoot():
        f = nswindow.frame()
        top = AppKit.NSScreen.screens()[0].frame().size.height
        rect = Quartz.CGRectMake(f.origin.x - PAD, top - f.origin.y - f.size.height - PAD, f.size.width + 2 * PAD, f.size.height + 2 * PAD)
        image = Quartz.CGWindowListCreateImageFromArray(rect, [nswindow.windowNumber(), made["back"].windowNumber()],
                                                        Quartz.kCGWindowImageBestResolution)
        made["ok"] = image is not None and bool(AppKit.NSBitmapImageRep.alloc().initWithCGImage_(image)
                                                .representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None)
                                                .writeToFile_atomically_(path, True))
        made["back"].orderOut_(None)

    on_main(put_behind)
    time.sleep(2.0)
    on_main(shoot)
    return bool(made.get("ok"))


def _drive(raw: str, behind: str) -> None:
    """In the app (a thread beside its main loop): wait for the scene, place the window, take it."""
    import AppKit
    import webview
    from PIL import Image
    from mosaic._labapp.mac import glass as macglass, on_main
    ok = False
    try:
        while not webview.windows:
            time.sleep(0.2)
        w = webview.windows[0]
        for _ in range(600):
            time.sleep(0.2)
            try:
                if w.evaluate_js("document.body.dataset.docshot === 'ready'"):
                    break
            except Exception:   # noqa: BLE001 (the page is still loading)
                pass
        time.sleep(3.0)
        nsw, _ = macglass._views(w)
        on_main(lambda: (nsw.setFrame_display_(AppKit.NSMakeRect(*FRAME), True),
                         AppKit.NSApp.activateIgnoringOtherApps_(True), nsw.makeKeyAndOrderFront_(None)))
        time.sleep(1.5)
        w.evaluate_js("window.FA.app.run('zoomFit')")
        time.sleep(1.5)
        for _ in range(3):   # (a capture can come back empty while the screen redraws: tried again)
            ok = _capture(w, raw, behind) and Image.open(raw).getextrema()[3][1] > 0
            if ok:
                break
            time.sleep(3)
    finally:
        print("SHOT", "ok" if ok else "failed", flush=True)
        os._exit(0)


def _app(theme: str, raw: str) -> None:
    """One run of mosaic (in a process of its own) for one theme."""
    sys.path.insert(0, ROOT)
    from mosaic.app import window
    threading.Thread(target=_drive, args=(raw, BACKDROP[theme]), daemon=True).start()
    window.run_app()


def main() -> int:
    if sys.platform != "darwin":
        print("The README's pictures are taken on a Mac.")
        return 1
    if len(sys.argv) == 4 and sys.argv[1] == "--app":   # (the child process)
        _app(sys.argv[2], sys.argv[3])
        return 0
    from PIL import Image
    failed = 0
    with tempfile.TemporaryDirectory(prefix="mosaic-readme-shots-") as tmp:
        examples = os.path.join(tmp, "examples")
        shutil.copytree(os.path.join(ROOT, "examples"), examples)   # (a copy: the scene only reads them)
        for theme in ("light", "dark"):
            home, raw = os.path.join(tmp, f"home-{theme}"), os.path.join(tmp, f"{theme}.png")
            os.makedirs(home)
            env = dict(os.environ, MOSAIC_HOME=home, MOSAIC_NO_UPDATES="1",
                       MOSAIC_SMOKE_QUERY=f"docshot=window&examples={examples}&theme={theme}")
            run = subprocess.run([sys.executable, os.path.abspath(__file__), "--app", theme, raw], env=env,
                                 capture_output=True, text=True, timeout=300)
            if "SHOT ok" not in run.stdout:
                print(f"{theme}: no picture\n{run.stderr[-2000:]}")
                failed += 1
                continue
            im = Image.open(raw).convert("RGB")   # (the backdrop fills it: no see-through parts)
            im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
            dest = os.path.join(OUT, f"readme-window-{theme}.png")
            im.save(dest, optimize=True)
            print(f"{theme}: {os.path.relpath(dest, ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

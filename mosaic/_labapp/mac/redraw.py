"""A window coming back on screen redraws all of itself, checks that it did, and says so in the log (Mac).

On 2026-11-25, after Matthew swiped between full-screen spaces, part of mosaic's full-screen window
(Liquid Glass on, on an external display) stayed blank, a flat colour, until a click. It wasn't
reproduced: a window covered for 20 to 90 s (with WebKit's low-memory signal too) came back drawn,
and SkyLight's call to switch a display's space didn't take a full-screen window off the screen. So
each return now redraws the window and records what happened:

- When a window comes back on screen (its occlusion state turns visible: another desktop or
  full-screen space left, the window uncovered or un-minimised), its page is made to paint itself
  again (REPAINT_JS: the body on a layer of its own for two frames) and the window's views are
  marked for drawing.
- CHECK_AFTER seconds later the window is captured (an app may capture its own windows without the
  screen-recording permission) and compared with its capture as it went away. Where most of the
  window was detailed and is now one flat colour (looks_blank), the web view is hidden and shown
  again, which makes WebKit draw all of it, and the window is captured once more.
- Each return writes a line to the app's log (what the app prints is kept there): the window's state
  and what the check found. The captures of the last RETURNS_KEPT returns are kept as small JPEGs in
  <folder>/returns, those that looked blank beyond that, so a return that still comes back blank can
  be looked at. They stay on this computer (a problem report takes only the log).
"""
from __future__ import annotations

import os
import sys
import threading
import time

CHECK_AFTER = 1.0       # s after a return, the window is captured and checked
RECHECK_AFTER = 1.0     # s after the stronger redraw, captured again
RETURNS_KEPT = 40       # returns whose captures are kept
BLANK_KEPT = 20         # and returns that looked blank, besides those
THUMB_WIDTH = 480       # px, the kept captures' width
GRID = (32, 18)         # cells the window is divided into for the check
FLAT = 2.5              # a cell whose pixels vary less than this (standard deviation, 0-255) is flat
DETAILED = 6.0          # and one varying more than this has something drawn in it
BLANK_SHARE = 0.10      # the share of the window that went from detailed to flat for it to look blank
REPAINT_JS = """(() => { const b = document.body; if (!b) return 0;
  const was = b.style.willChange; b.style.willChange = "opacity";
  requestAnimationFrame(() => requestAnimationFrame(() => { b.style.willChange = was; }));
  window.__labappRepaints = (window.__labappRepaints || 0) + 1; return window.__labappRepaints; })()"""

_state: dict = {"windows": {}, "observer": None, "lock": threading.Lock()}


# The check (no AppKit: tested on its own) ---------------------------------------------------------

def looks_blank(before, after) -> tuple[bool, float]:
    """Whether a window's capture after a return (a PIL image) looks blank next to the one taken
    as it went away: the share of GRID cells that had something drawn in them and are now one flat
    colour is BLANK_SHARE or more. (A picture changed while away isn't flat; empty parts of a page
    are flat both times.) Returns (blank, that share)."""
    from PIL import ImageStat
    size = (GRID[0] * 8, GRID[1] * 8)
    b, a = before.convert("L").resize(size), after.convert("L").resize(size)
    went = 0
    for gy in range(GRID[1]):
        for gx in range(GRID[0]):
            box = (gx * 8, gy * 8, gx * 8 + 8, gy * 8 + 8)
            if ImageStat.Stat(b.crop(box)).stddev[0] > DETAILED and ImageStat.Stat(a.crop(box)).stddev[0] < FLAT:
                went += 1
    share = went / (GRID[0] * GRID[1])
    return share >= BLANK_SHARE, share


def _keep(folder: str, stamp: str, images: dict, blank: bool) -> None:
    """The captures of one return as small JPEGs; the oldest beyond RETURNS_KEPT (BLANK_KEPT for
    those that looked blank) removed."""
    d = os.path.join(folder, "returns")
    os.makedirs(d, exist_ok=True)
    tag = "-blank" if blank else ""
    for name, im in images.items():
        if im is None:
            continue
        small = im.convert("RGB")
        small = small.resize((THUMB_WIDTH, max(1, round(small.height * THUMB_WIDTH / small.width))))
        small.save(os.path.join(d, f"{stamp}{tag}-{name}.jpg"), "JPEG", quality=70)
    for blank_ones, keep in ((False, RETURNS_KEPT), (True, BLANK_KEPT)):
        stamps = sorted({f.split("-", 2)[0] + "-" + f.split("-", 2)[1] for f in os.listdir(d)
                         if f.endswith(".jpg") and ("-blank-" in f) == blank_ones})
        for old in stamps[:-keep]:
            for f in os.listdir(d):
                if f.startswith(old + "-") and ("-blank-" in f) == blank_ones:
                    try:
                        os.remove(os.path.join(d, f))
                    except OSError:
                        pass


# The window ---------------------------------------------------------------------------------------

def capture(number: int):
    """A window of this app as the screen composites it (a PIL image, RGB over mid grey where the
    window is see-through), or None (not on screen, say)."""
    import Quartz
    from PIL import Image
    img = Quartz.CGWindowListCreateImageFromArray(Quartz.CGRectNull, [number],
                                                  Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageNominalResolution)
    if img is None or Quartz.CGImageGetWidth(img) < 2:
        return None
    w, h, row = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img), Quartz.CGImageGetBytesPerRow(img)
    data = bytes(Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img)))
    info = Quartz.CGImageGetBitmapInfo(img)
    little = (info & Quartz.kCGBitmapByteOrderMask) == Quartz.kCGBitmapByteOrder32Little
    im = Image.frombuffer("RGBA", (w, h), data, "raw", "BGRA" if little else "ARGB", row, 1)
    back = Image.new("RGBA", im.size, (128, 128, 128, 255))
    back.alpha_composite(im)
    return back.convert("RGB")


def describe(nswindow, webview) -> dict:
    """On the main thread: what the log says of a window on its return."""
    import AppKit
    f, web = nswindow.frame(), webview.frame()
    screen = nswindow.screen()
    holder = nswindow.contentView()
    return {
        "full screen": bool(nswindow.styleMask() & AppKit.NSWindowStyleMaskFullScreen),
        "key": bool(nswindow.isKeyWindow()), "app active": bool(AppKit.NSApp.isActive()),
        "on active space": bool(nswindow.isOnActiveSpace()),
        "glass": str(holder.identifier() or "") == "labapp.glass.content" if holder is not None else False,
        "window": [round(f.size.width), round(f.size.height)], "web view": [round(web.size.width), round(web.size.height)],
        "web view hidden": bool(webview.isHidden()), "in window": webview.window() == nswindow,
        "screen": f"{screen.localizedName()} x{screen.backingScaleFactor():g}" if screen is not None else None,
    }


def _repaint(rec: dict) -> None:
    """On the main thread: the window's views marked for drawing, the page painting itself again."""
    nswindow, webview = rec["nswindow"], rec["webview"]
    view = nswindow.contentView()
    for v in [view, *(view.subviews() or [])] if view is not None else []:
        v.setNeedsDisplay_(True)
    webview.evaluateJavaScript_completionHandler_(REPAINT_JS, None)
    nswindow.displayIfNeeded()


def _harder(rec: dict) -> None:
    """On the main thread: the web view hidden and shown again (WebKit then draws all of it)."""
    from PyObjCTools import AppHelper
    webview = rec["webview"]
    webview.setHidden_(True)
    AppHelper.callLater(0.05, lambda: (webview.setHidden_(False), _repaint(rec)))


def _left(rec: dict) -> None:
    """The window went off screen: when, and how it looked (captured off the main thread)."""
    rec["left"], rec["before"] = time.time(), None
    number = rec["number"]

    def take():
        try:
            rec["before"] = capture(number)
        except Exception as exc:   # noqa: BLE001 (the check then has nothing to compare with)
            rec["before_error"] = str(exc)
    threading.Thread(target=take, daemon=True).start()


def _returned(rec: dict) -> None:
    """On the main thread: the window is back. Redraw it now, check it CHECK_AFTER s later."""
    from PyObjCTools import AppHelper
    from . import on_main
    _repaint(rec)
    if not rec.get("left"):   # (its first time on screen, a window made hidden and then shown: nothing to check)
        return
    away = time.time() - rec["left"]
    state = describe(rec["nswindow"], rec["webview"])
    rec["returns"] = rec.get("returns", 0) + 1

    def check():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        try:
            before, after = rec.get("before"), capture(rec["number"])
            result, images = "", {"before": before, "after": after}
            blank = False
            if after is None:
                result = "no capture (not on screen)"
            elif before is None or before.size != after.size:
                result = "nothing to compare with" if before is None else f"size changed {before.size} -> {after.size}"
            else:
                blank, share = looks_blank(before, after)
                result = f"{share * 100:.0f}% of it went flat"
                if blank:
                    on_main(lambda: _harder(rec))
                    time.sleep(RECHECK_AFTER)
                    again = capture(rec["number"])
                    images["after-redrawn"] = again
                    cleared = again is not None and not looks_blank(before, again)[0]
                    result += f": LOOKED BLANK; redrawn again, {'drawn now' if cleared else 'STILL BLANK'}"
            print(f"Window back on screen (window {rec['number']}, away {away:.0f} s): {result}; {state}",
                  file=sys.stderr, flush=True)
            if rec.get("folder") and (after is not None):
                _keep(rec["folder"], f"{stamp}-w{rec['number']}", images, blank)
        except Exception as exc:   # noqa: BLE001 (the check is only a check)
            print(f"Window back on screen (window {rec['number']}): the check failed: {exc}", file=sys.stderr, flush=True)
    AppHelper.callLater(CHECK_AFTER, lambda: threading.Thread(target=check, daemon=True).start())


def _observer():
    """The one object told of every watched window's occlusion changes and closing."""
    if _state["observer"] is not None:
        return _state["observer"]
    import AppKit
    import Foundation

    class LabappReturnWatcher(Foundation.NSObject):
        def occlusionChanged_(self, note):
            win = note.object()
            rec = _state["windows"].get(int(win.windowNumber()))
            if rec is None:
                return
            visible = bool(win.occlusionState() & AppKit.NSWindowOcclusionStateVisible)
            if visible == rec["visible"]:
                return
            rec["visible"] = visible
            try:
                _returned(rec) if visible else _left(rec)
            except Exception as exc:   # noqa: BLE001 (the window just isn't redrawn this time)
                print(f"Window back on screen: couldn't redraw: {exc}", file=sys.stderr, flush=True)

        def windowClosing_(self, note):
            win = note.object()
            _state["windows"].pop(int(win.windowNumber()), None)
            center = Foundation.NSNotificationCenter.defaultCenter()
            center.removeObserver_name_object_(self, AppKit.NSWindowDidChangeOcclusionStateNotification, win)
            center.removeObserver_name_object_(self, AppKit.NSWindowWillCloseNotification, win)
    _state["observer"] = LabappReturnWatcher.alloc().init()
    return _state["observer"]


def install_native(nswindow, webview, folder: str | None = None) -> dict:
    """On the main thread: watch this window's returns (once per window). folder: where the
    captures are kept (the app's logs folder), None to keep none."""
    import AppKit
    import Foundation
    number = int(nswindow.windowNumber())
    if number in _state["windows"]:
        _state["windows"][number].update(webview=webview, folder=folder)
        return _state["windows"][number]
    rec = {"nswindow": nswindow, "webview": webview, "number": number, "folder": folder,
           "visible": bool(nswindow.occlusionState() & AppKit.NSWindowOcclusionStateVisible)}
    _state["windows"][number] = rec
    center = Foundation.NSNotificationCenter.defaultCenter()
    center.addObserver_selector_name_object_(_observer(), b"occlusionChanged:", AppKit.NSWindowDidChangeOcclusionStateNotification, nswindow)
    center.addObserver_selector_name_object_(_observer(), b"windowClosing:", AppKit.NSWindowWillCloseNotification, nswindow)
    return rec


def install(window, folder: str | None = None) -> None:
    """Watch a pywebview window's returns (from any thread, the main one too)."""
    from . import on_main
    from .glass import _views
    nswindow, webview = _views(window)
    if threading.current_thread() is threading.main_thread():
        install_native(nswindow, webview, folder)
    else:
        on_main(lambda: install_native(nswindow, webview, folder))


def smoke(window, folder: str) -> dict:
    """Checks for an app's smoke test, in its (hidden) window: watching a window twice keeps one
    watch; a return (as the occlusion notice brings it) has the page paint itself again and writes
    the log's line, and its check runs (a hidden window has nothing to capture). folder: scratch."""
    from . import on_main
    from .glass import _views
    results = []

    def check(ok, name):
        results.append((bool(ok), name))
    nswindow, webview = _views(window)
    rec = on_main(lambda: install_native(nswindow, webview, folder))
    again = on_main(lambda: install_native(nswindow, webview, folder))
    check(rec is again and len([r for r in _state["windows"].values() if r is rec]) == 1,
          "Return redraw: a window is watched once")
    before = window.evaluate_js("window.__labappRepaints || 0")
    lines: list = []
    real = sys.stderr

    class Catch:
        def write(self, s):
            lines.append(s)
            return real.write(s)

        def flush(self):
            real.flush()
    sys.stderr = Catch()
    try:
        rec["left"] = time.time() - 3
        on_main(lambda: _returned(rec))
        for _ in range(50):
            time.sleep(0.1)
            if any("Window back on screen" in s for s in lines):
                break
    finally:
        sys.stderr = real
    after = window.evaluate_js("window.__labappRepaints || 0")
    check(after == before + 1, "Return redraw: the page paints itself again on a return")
    line = next((s for s in lines if "Window back on screen" in s), "")
    check("away 3 s" in line and "'full screen'" in line and "'web view'" in line,
          "Return redraw: the log says when it came back and the window's state")
    failed = [name for ok, name in results if not ok]
    return {"passed": len(results) - len(failed), "total": len(results), "failed": failed}

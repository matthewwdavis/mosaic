"""Liquid Glass on a Mac: the system's own glass behind a window's web view, so the window's
ribbon, side panes and status bar show what's behind the window, blurred (labapp/glass.py says
which level, and what each system gets).

The window is made see-through and its web view stops painting a background of its own; a glass
view (NSGlassEffectView, macOS 26 and later; before that the frosted NSVisualEffectView) fills the
window behind the web view. The page decides what shows the glass: whatever it paints solid (the
document's page, mosaic's canvas) stays solid, and its chrome is painted in see-through colours.
The title bar has no web page in it, so it is tinted here with the colour the page gives for its
ribbon, and the two read as one bar. Off puts everything back as pywebview made it.
"""
from __future__ import annotations

import objc

GLASS_ID = "labapp.glass"
TINT_ID = "labapp.glass.titlebar"
_state: dict = {}   # saved window colours (by window number), the observer of the system's settings


def material() -> str:
    """"glass" where the system has Liquid Glass (macOS 26 and later), else "vibrancy"."""
    try:
        objc.lookUpClass("NSGlassEffectView")
        return "glass"
    except objc.error:
        return "vibrancy"


def system() -> dict:
    """The system's Accessibility ▸ Display settings that change how glass is drawn."""
    import AppKit
    ws = AppKit.NSWorkspace.sharedWorkspace()
    return {"reduceTransparency": bool(ws.accessibilityDisplayShouldReduceTransparency()),
            "increaseContrast": bool(ws.accessibilityDisplayShouldIncreaseContrast())}


def watch(callback) -> None:
    """Call callback(system()) whenever Reduce Transparency or Increase Contrast changes (once)."""
    if "observer" in _state:
        _state["callbacks"].append(callback)
        return
    import AppKit
    import Foundation
    _state["callbacks"] = [callback]

    class LabappGlassWatcher(Foundation.NSObject):
        def displayOptionsChanged_(self, note):
            now = system()
            for fn in list(_state["callbacks"]):
                try:
                    fn(now)
                except Exception as exc:   # noqa: BLE001 (one app's window gone: the others still told)
                    print(f"Glass: a window wasn't told of the system's change: {exc}", flush=True)
    _state["observer"] = LabappGlassWatcher.alloc().init()
    AppKit.NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
        _state["observer"], b"displayOptionsChanged:", AppKit.NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification, None)


def _views(window):
    """(NSWindow, WKWebView) of a pywebview window."""
    from webview.platforms.cocoa import BrowserView
    inst = BrowserView.instances[window.uid]
    return inst.window, inst.webview


def _effect(nswindow, ident: str = GLASS_ID):
    """The glass view this module put in a window (or its title bar's tint: TINT_ID), or None."""
    frame = nswindow.contentView().superview()
    for v in frame.subviews() or []:
        if str(v.identifier() or "") == ident:
            return v
    return None


def _place_tint(nswindow) -> None:
    """The title bar's tint over the part of the window above the web view (none in full screen,
    where the title bar is the system's own)."""
    import AppKit
    tint = _effect(nswindow, TINT_ID)
    if tint is None:
        return
    bounds, content = nswindow.contentView().superview().bounds(), nswindow.contentView().frame()
    top = content.origin.y + content.size.height
    height = max(0.0, bounds.size.height - top)
    tint.setFrame_(AppKit.NSMakeRect(0, top, bounds.size.width, height))
    tint.setHidden_(bool(nswindow.styleMask() & AppKit.NSWindowStyleMaskFullScreen) or height == 0)


def _follow_full_screen(nswindow) -> None:
    """Place the tint again as the window goes into or out of full screen (once a window)."""
    import AppKit
    import Foundation
    if "fs" not in _state:
        class LabappGlassFullScreen(Foundation.NSObject):
            def changed_(self, note):
                try:
                    _place_tint(note.object())
                except Exception:   # noqa: BLE001 (the window is closing)
                    pass
        _state["fs"] = LabappGlassFullScreen.alloc().init()
        _state["fs_windows"] = set()
    if id(nswindow) in _state["fs_windows"]:
        return
    _state["fs_windows"].add(id(nswindow))
    centre = Foundation.NSNotificationCenter.defaultCenter()
    for name in (AppKit.NSWindowDidEnterFullScreenNotification, AppKit.NSWindowDidExitFullScreenNotification):
        centre.addObserver_selector_name_object_(_state["fs"], b"changed:", name, nswindow)


def _titlebar(nswindow):
    """The title bar's own view (NSTitlebarContainerView), which pywebview paints opaque."""
    frame = nswindow.contentView().superview()
    for v in frame.subviews() or []:
        if "Titlebar" in str(v.className()) and v.respondsToSelector_(b"setBackgroundColor:"):
            return v
    return None


def _colour(rgba):
    """[r, g, b (0-255), a (0-1)] as an NSColor (sRGB)."""
    import AppKit
    r, g, b, a = (list(rgba) + [1.0])[:4]
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255, g / 255, b / 255, float(a))


def apply_native(nswindow, webview, level: str, titlebar=None) -> None:
    """On the main thread: glass at this level ("off", "subtle", "standard", "clear") behind the
    web view; titlebar: the title bar's tint, [r, g, b, a] (the page's ribbon colour)."""
    import AppKit
    key = int(nswindow.windowNumber())
    saved = _state.setdefault("windows", {})
    effect, bar, tint = _effect(nswindow), _titlebar(nswindow), _effect(nswindow, TINT_ID)
    if level == "off":
        for v in (effect, tint):
            if v is not None:
                v.removeFromSuperview()
        if key in saved:
            nswindow.setBackgroundColor_(saved[key]["background"])
            nswindow.setTitlebarAppearsTransparent_(saved[key]["transparent"])
            if bar is not None:
                bar.setBackgroundColor_(saved[key]["bar"] or AppKit.NSColor.windowBackgroundColor())
            del saved[key]
        nswindow.setOpaque_(True)
        webview.setValue_forKey_(True, "drawsBackground")
        return
    if key not in saved:
        saved[key] = {"background": nswindow.backgroundColor(), "transparent": bool(nswindow.titlebarAppearsTransparent()),
                      "bar": bar.backgroundColor() if bar is not None and bar.respondsToSelector_(b"backgroundColor") else None}
    frame = nswindow.contentView().superview()
    kind = material()
    if effect is None:
        if kind == "glass":
            effect = AppKit.NSGlassEffectView.alloc().initWithFrame_(frame.bounds())
            effect.setCornerRadius_(0)
        else:
            effect = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame.bounds())
            effect.setMaterial_(AppKit.NSVisualEffectMaterialUnderWindowBackground)
            effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
            effect.setState_(AppKit.NSVisualEffectStateActive)
        effect.setIdentifier_(GLASS_ID)
        effect.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        frame.addSubview_positioned_relativeTo_(effect, AppKit.NSWindowBelow, nswindow.contentView())
    effect.setFrame_(frame.bounds())
    if kind == "glass":
        # (every level is the frosted glass: the system's clear glass leaves what's behind sharp,
        # too busy under text; the levels differ in how much of the page's colour is over it)
        effect.setStyle_(AppKit.NSGlassEffectViewStyleRegular)
    nswindow.setOpaque_(False)
    nswindow.setBackgroundColor_(AppKit.NSColor.clearColor())
    nswindow.setTitlebarAppearsTransparent_(True)
    if bar is not None:   # (pywebview paints it solid)
        bar.setBackgroundColor_(AppKit.NSColor.clearColor())
    # The title bar's tint: a view of its own over the glass, as the page tints its ribbon
    if tint is None:
        tint = AppKit.NSBox.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 0, 0))   # (a box: a filled rectangle, no border)
        tint.setBoxType_(AppKit.NSBoxCustom)
        tint.setBorderWidth_(0)
        tint.setTitlePosition_(AppKit.NSNoTitle)
        tint.setIdentifier_(TINT_ID)
        tint.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
        frame.addSubview_positioned_relativeTo_(tint, AppKit.NSWindowAbove, effect)
        _follow_full_screen(nswindow)
    tint.setFillColor_(_colour(titlebar) if titlebar else AppKit.NSColor.clearColor())
    _place_tint(nswindow)
    webview.setValue_forKey_(False, "drawsBackground")


def apply(window, level: str, titlebar=None) -> None:
    """Glass at this level in a pywebview window (from any thread)."""
    from . import on_main
    nswindow, webview = _views(window)
    on_main(lambda: apply_native(nswindow, webview, level, titlebar))


def describe_native(nswindow, webview) -> dict:
    """On the main thread: what a window has now (for tests): the glass view's kind and place, the
    window's and the web view's backgrounds, the title bar's tint."""
    import AppKit
    effect, frame = _effect(nswindow), nswindow.contentView().superview()
    subs = list(frame.subviews() or [])
    strip, tint = _effect(nswindow, TINT_ID), None
    if strip is not None and not strip.isHidden():
        c = strip.fillColor().colorUsingColorSpace_(AppKit.NSColorSpace.sRGBColorSpace())
        if c is not None and c.alphaComponent() > 0:
            tint = [round(c.redComponent() * 255), round(c.greenComponent() * 255), round(c.blueComponent() * 255), round(c.alphaComponent(), 3)]
    return {"effect": str(effect.className()) if effect is not None else None,
            "behind": effect is not None and subs.index(effect) < subs.index(nswindow.contentView()),
            "fills": effect is not None and tuple(effect.frame().size) == tuple(frame.bounds().size),
            "opaque": bool(nswindow.isOpaque()), "drawsBackground": bool(webview.valueForKey_("drawsBackground")),
            "titlebarTint": tint, "tintPlaced": strip is not None and subs.index(strip) < subs.index(nswindow.contentView())
            and strip.frame().origin.y >= nswindow.contentView().frame().origin.y + nswindow.contentView().frame().size.height - 0.5}


def describe(window) -> dict:
    """describe_native() for a pywebview window (from any thread)."""
    from . import on_main
    nswindow, webview = _views(window)
    return on_main(lambda: describe_native(nswindow, webview))


def capture(window, path: str, behind: str | None = None, seconds: float = 1.0) -> bool:
    """A picture of the window as the screen shows it, glass and all (WebKit's own snapshot leaves
    the glass out), saved as a PNG. behind: a CSS background (a colour, a gradient) for a window of
    this app's own put just behind it while the picture is taken, so the picture shows the glass
    doing its work without showing anyone's other windows. The window must be on screen."""
    import threading
    import time

    import AppKit
    import Quartz
    import WebKit
    from PyObjCTools import AppHelper
    nswindow, _ = _views(window)
    made: dict = {}

    def put_behind():
        if not behind:
            return
        f = nswindow.frame()
        back = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(f.origin.x - 60, f.origin.y - 60, f.size.width + 120, f.size.height + 120), 0, AppKit.NSBackingStoreBuffered, False)
        back.setReleasedWhenClosed_(False)
        view = WebKit.WKWebView.alloc().initWithFrame_configuration_(back.contentView().bounds(), WebKit.WKWebViewConfiguration.alloc().init())
        view.loadHTMLString_baseURL_(f"<body style='margin:0;height:100vh;background:{behind}'></body>", None)
        back.setContentView_(view)
        back.orderWindow_relativeTo_(AppKit.NSWindowBelow, nswindow.windowNumber())
        made["back"] = back

    def shoot():
        f = nswindow.frame()
        top = AppKit.NSScreen.screens()[0].frame().size.height
        rect = Quartz.CGRectMake(f.origin.x, top - f.origin.y - f.size.height, f.size.width, f.size.height)
        # (just these windows, composited as the screen has them: other apps' windows aren't ours to take)
        ids = [nswindow.windowNumber()] + ([made["back"].windowNumber()] if "back" in made else [])
        image = Quartz.CGWindowListCreateImageFromArray(rect, ids, Quartz.kCGWindowImageBestResolution)
        ok = False
        if image is not None:
            rep = AppKit.NSBitmapImageRep.alloc().initWithCGImage_(image)
            ok = bool(rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None).writeToFile_atomically_(path, True))
        if "back" in made:
            made["back"].orderOut_(None)
        made["ok"] = ok
        made["done"].set()
    made["done"] = threading.Event()
    AppHelper.callAfter(put_behind)
    time.sleep(seconds)
    AppHelper.callAfter(shoot)
    made["done"].wait(10)
    return bool(made.get("ok"))


def smoke(window, level_now: str = "standard") -> dict:
    """Checks for an app's smoke test, in its (hidden) window: each level puts the glass behind the
    web view and makes the window see-through, the title bar takes the tint it's given, and Off
    puts the window back as it was; the window is left at level_now."""
    results = []

    def check(ok, name):
        results.append((bool(ok), name))
    try:
        apply(window, "standard", [240, 240, 242, 0.6])
        d = describe(window)
        check(d["effect"] == ("NSGlassEffectView" if material() == "glass" else "NSVisualEffectView") and d["behind"] and d["fills"],
              "Glass: the system's glass fills the window behind the page")
        check(not d["opaque"] and not d["drawsBackground"], "Glass: the window and the page are see-through where the page paints nothing")
        check(d["titlebarTint"] == [240, 240, 242, 0.6] and d["tintPlaced"], "Glass: the title bar takes the ribbon's tint")
        apply(window, "clear", [30, 30, 33, 0.5])
        d2 = describe(window)
        check(d2["effect"] == d["effect"] and d2["titlebarTint"] == [30, 30, 33, 0.5], "Glass: changing the level keeps one glass view, with the new tint")
        apply(window, "off")
        d = describe(window)
        check(d["effect"] is None and d["opaque"] and d["drawsBackground"], "Glass: Off takes the glass out and the window is solid again")
    finally:
        try:
            if level_now != "off":
                apply(window, level_now)
        except Exception:   # noqa: BLE001 (the window may be closing)
            pass
    failed = [name for ok, name in results if not ok]
    return {"passed": len(results) - len(failed), "total": len(results), "failed": failed}

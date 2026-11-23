"""Liquid Glass on a Mac: the system's own glass behind a window's web view, so the window's
ribbon, side panes and status bar show what's behind the window, blurred (labapp/glass.py says
which level, and what each system gets).

The window is made see-through and its web view stops painting a background of its own; a glass
view (NSGlassEffectView, macOS 26 and later; before that the frosted NSVisualEffectView) fills the
window behind the web view. The page decides what shows the glass: whatever it paints solid (the
document's page, mosaic's canvas) stays solid, and its chrome is painted in see-through colours.
The title bar has no web page in it, so it is tinted here with the colour the page gives for its
ribbon, and the two read as one bar; its title and the glass take the light or dark appearance
of that colour, so a dark theme on a light Mac has a light title on dark glass. Off puts
everything back as pywebview made it.

The glass, the tint and the web view go in a view of their own that becomes the window's content
view (as large as the whole window, under its title bar), never in the window's frame view:
AppKit draws the title bar of a window whose frame view has views of its own put in it without
its title bar view, and that title bar no longer zooms the window on a double-click (found
2026-11-23 on macOS 27; it stays that way even after the views are taken out).
"""
from __future__ import annotations

import objc

GLASS_ID = "labapp.glass"
TINT_ID = "labapp.glass.titlebar"
HOLDER_ID = "labapp.glass.content"
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


def _holder(nswindow):
    """The window's content view while it has glass (HOLDER_ID: the glass, the title bar's tint and
    the web view in it), else None."""
    view = nswindow.contentView()
    return view if view is not None and str(view.identifier() or "") == HOLDER_ID else None


def _effect(nswindow, ident: str = GLASS_ID):
    """The glass view this module put in a window (or its title bar's tint: TINT_ID), or None."""
    holder = _holder(nswindow)
    for v in (holder.subviews() if holder is not None else None) or []:
        if str(v.identifier() or "") == ident:
            return v
    return None


def _titlebar(nswindow):
    """The title bar's own view (NSTitlebarContainerView, which pywebview paints opaque), or None:
    a window whose frame view has had views of its own put in it draws its title bar without one,
    and then a double-click on it no longer zooms the window."""
    frame = nswindow.contentView().superview()
    for v in frame.subviews() or []:
        if "TitlebarContainer" in str(v.className()) and v.respondsToSelector_(b"setBackgroundColor:"):
            return v
    return None


def _colour(rgba):
    """[r, g, b (0-255), a (0-1)] as an NSColor (sRGB)."""
    import AppKit
    r, g, b, a = (list(rgba) + [1.0])[:4]
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255, g / 255, b / 255, float(a))


def _appearance(rgba):
    """The appearance the title bar's text and the glass take under a tint: Dark Aqua for a dark
    theme's colour, Aqua for a light one (None: no tint, the window's own). The page's theme can be
    dark while the Mac is light, or the other way round; the title and the glass follow the page,
    the web view itself keeps the system's (its pages' prefers-color-scheme)."""
    if not rgba:
        return None
    import AppKit

    from ..glass import contrast
    dark = contrast(rgba, "#ffffff") > contrast(rgba, "#000000")   # (white text reads better on it)
    return AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua if dark else AppKit.NSAppearanceNameAqua)


def _has_focus(nswindow, webview) -> bool:
    """Whether the web view (or a view in it) has the keyboard."""
    import AppKit
    fr = nswindow.firstResponder()
    return fr is not None and fr.isKindOfClass_(AppKit.NSView) and (fr == webview or fr.isDescendantOf_(webview))


def _hold(nswindow, webview) -> None:
    """Put the web view in a holder: the window's content view, as large as the whole window (its
    title bar over the top of it), with the glass filling it, the tint under the title bar and the
    web view below the title bar (held to the window's content layout guide, so it follows the
    title bar's height, none in full screen). Nothing is added to the window's frame view, so the
    title bar stays AppKit's own: its buttons, its drag, and (see apply_native) its double-click,
    which zooms, fills or minimises the window as System Settings says."""
    import AppKit
    # (a web view not in the window yet: pywebview puts it there, with the keyboard, once its page
    # has loaded, but not if it's in a window by then, so it gets the keyboard here instead)
    focused, frame = _has_focus(nswindow, webview) or webview.window() is None, nswindow.frame()
    holder = AppKit.NSView.alloc().initWithFrame_(nswindow.contentView().frame())
    holder.setIdentifier_(HOLDER_ID)
    if material() == "glass":
        effect = AppKit.NSGlassEffectView.alloc().initWithFrame_(holder.bounds())
        effect.setCornerRadius_(0)
    else:
        effect = AppKit.NSVisualEffectView.alloc().initWithFrame_(holder.bounds())
        effect.setMaterial_(AppKit.NSVisualEffectMaterialUnderWindowBackground)
        effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(AppKit.NSVisualEffectStateActive)
    effect.setIdentifier_(GLASS_ID)
    effect.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
    tint = AppKit.NSBox.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 0, 0))   # (a box: a filled rectangle, no border)
    tint.setBoxType_(AppKit.NSBoxCustom)
    tint.setBorderWidth_(0)
    tint.setTitlePosition_(AppKit.NSNoTitle)
    tint.setIdentifier_(TINT_ID)
    nswindow.setContentView_(holder)   # (which takes the web view out of the window, for a moment)
    nswindow.setStyleMask_(nswindow.styleMask() | AppKit.NSWindowStyleMaskFullSizeContentView)
    nswindow.setFrame_display_(frame, False)   # (AppKit keeps the content's size, which would shorten the window)
    for v in (effect, tint, webview):
        holder.addSubview_(v)
    effect.setFrame_(holder.bounds())   # (the holder is the whole window's size by now)
    guide = nswindow.contentLayoutGuide()
    for v in (tint, webview):
        v.setTranslatesAutoresizingMaskIntoConstraints_(False)
    AppKit.NSLayoutConstraint.activateConstraints_([
        tint.topAnchor().constraintEqualToAnchor_(holder.topAnchor()),
        tint.bottomAnchor().constraintEqualToAnchor_(guide.topAnchor()),
        tint.leadingAnchor().constraintEqualToAnchor_(holder.leadingAnchor()),
        tint.trailingAnchor().constraintEqualToAnchor_(holder.trailingAnchor()),
        webview.topAnchor().constraintEqualToAnchor_(guide.topAnchor()),
        webview.bottomAnchor().constraintEqualToAnchor_(guide.bottomAnchor()),
        webview.leadingAnchor().constraintEqualToAnchor_(guide.leadingAnchor()),
        webview.trailingAnchor().constraintEqualToAnchor_(guide.trailingAnchor())])
    holder.layoutSubtreeIfNeeded()
    if focused:
        nswindow.makeFirstResponder_(webview)


def _release(nswindow, webview, full_size: bool) -> None:
    """The web view back as the window's content view, as pywebview made it."""
    import AppKit
    focused, frame = _has_focus(nswindow, webview), nswindow.frame()
    webview.removeFromSuperview()   # (and the holder's constraints on it)
    webview.setTranslatesAutoresizingMaskIntoConstraints_(True)
    nswindow.setContentView_(webview)
    if not full_size:
        nswindow.setStyleMask_(nswindow.styleMask() & ~AppKit.NSWindowStyleMaskFullSizeContentView)
        nswindow.setFrame_display_(frame, False)
    if focused:
        nswindow.makeFirstResponder_(webview)


def apply_native(nswindow, webview, level: str, titlebar=None) -> None:
    """On the main thread: glass at this level ("off", "subtle", "standard", "clear") behind the
    web view; titlebar: the title bar's tint, [r, g, b, a] (the page's ribbon colour)."""
    import AppKit
    key = int(nswindow.windowNumber())
    saved = _state.setdefault("windows", {})
    if level == "off":
        if _holder(nswindow) is not None:
            _release(nswindow, webview, saved.get(key, {}).get("full_size", False))
        bar = _titlebar(nswindow)
        if key in saved:
            nswindow.setBackgroundColor_(saved[key]["background"])
            nswindow.setTitlebarAppearsTransparent_(saved[key]["transparent"])
            if saved[key]["double_click"] is not None:
                nswindow.setTitlebarHandlesDoubleClickWhenTransparent_(saved[key]["double_click"])
            if bar is not None:
                bar.setBackgroundColor_(saved[key]["bar"] or AppKit.NSColor.windowBackgroundColor())
                bar.setAppearance_(saved[key]["appearance"])
            del saved[key]
        nswindow.setOpaque_(True)
        webview.setValue_forKey_(True, "drawsBackground")
        return
    if key not in saved:
        bar = _titlebar(nswindow)
        saved[key] = {"background": nswindow.backgroundColor(), "transparent": bool(nswindow.titlebarAppearsTransparent()),
                      "bar": bar.backgroundColor() if bar is not None and bar.respondsToSelector_(b"backgroundColor") else None,
                      "appearance": bar.appearance() if bar is not None else None,
                      "full_size": bool(nswindow.styleMask() & AppKit.NSWindowStyleMaskFullSizeContentView),
                      "double_click": bool(nswindow.titlebarHandlesDoubleClickWhenTransparent())
                      if nswindow.respondsToSelector_(b"titlebarHandlesDoubleClickWhenTransparent") else None}
    if _holder(nswindow) is None:
        _hold(nswindow, webview)
    effect, tint, look = _effect(nswindow), _effect(nswindow, TINT_ID), _appearance(titlebar)
    if material() == "glass":
        # (every level is the frosted glass: the system's clear glass leaves what's behind sharp,
        # too busy under text; the levels differ in how much of the page's colour is over it)
        effect.setStyle_(AppKit.NSGlassEffectViewStyleRegular)
    effect.setAppearance_(look)
    nswindow.setOpaque_(False)
    nswindow.setBackgroundColor_(AppKit.NSColor.clearColor())
    nswindow.setTitlebarAppearsTransparent_(True)
    # A see-through title bar lets presses through to the view under it (AppKit's documentation),
    # so a double-click there would zoom nothing: AppKit's own title bar keeps taking it (zoom, fill
    # or minimise as System Settings says). The setting is AppKit's, unlisted (macOS 27); without
    # it the title bar's press watcher does the setting's action instead (mac/title.py)
    if nswindow.respondsToSelector_(b"setTitlebarHandlesDoubleClickWhenTransparent:"):
        nswindow.setTitlebarHandlesDoubleClickWhenTransparent_(True)
    bar = _titlebar(nswindow)
    if bar is not None:   # (pywebview paints it solid)
        bar.setBackgroundColor_(AppKit.NSColor.clearColor())
        bar.setAppearance_(look if look is not None else saved[key]["appearance"])
    # The title bar's tint: under the title bar, over the glass, as the page tints its ribbon
    tint.setFillColor_(_colour(titlebar) if titlebar else AppKit.NSColor.clearColor())
    webview.setValue_forKey_(False, "drawsBackground")


def apply(window, level: str, titlebar=None) -> None:
    """Glass at this level in a pywebview window (from any thread)."""
    from . import on_main
    nswindow, webview = _views(window)
    on_main(lambda: apply_native(nswindow, webview, level, titlebar))


def describe_native(nswindow, webview) -> dict:
    """On the main thread: what a window has now (for tests): the glass view's kind and place, the
    window's and the web view's backgrounds, the title bar's tint and whether the title bar is still
    AppKit's own (the traffic lights in its title bar view), the title bar's appearance."""
    import AppKit
    holder, effect = _holder(nswindow), _effect(nswindow)
    subs = list(holder.subviews() or []) if holder is not None else []
    strip, tint = _effect(nswindow, TINT_ID), None
    if strip is not None and not strip.isHidden():
        c = strip.fillColor().colorUsingColorSpace_(AppKit.NSColorSpace.sRGBColorSpace())
        if c is not None and c.alphaComponent() > 0:
            tint = [round(c.redComponent() * 255), round(c.greenComponent() * 255), round(c.blueComponent() * 255), round(c.alphaComponent(), 3)]
    frame = nswindow.contentView().superview()
    web = webview.frame()
    close = nswindow.standardWindowButton_(AppKit.NSWindowCloseButton)
    bar = _titlebar(nswindow)
    look = bar.effectiveAppearance().bestMatchFromAppearancesWithNames_(
        [AppKit.NSAppearanceNameAqua, AppKit.NSAppearanceNameDarkAqua]) if bar is not None else None
    return {"effect": str(effect.className()) if effect is not None else None,
            "behind": effect is not None and webview in subs and subs.index(effect) < subs.index(webview),
            "fills": effect is not None and tuple(effect.frame().size) == tuple(frame.bounds().size),
            "opaque": bool(nswindow.isOpaque()), "drawsBackground": bool(webview.valueForKey_("drawsBackground")),
            "titlebarTint": tint, "tintPlaced": strip is not None and webview in subs and subs.index(strip) < subs.index(webview)
            and strip.frame().origin.y >= web.origin.y + web.size.height - 0.5,
            "titlebar": bar is not None and close is not None and "Titlebar" in str(close.superview().className()),
            "frameUntouched": not any(str(v.identifier() or "") in (GLASS_ID, TINT_ID) for v in frame.subviews() or []),
            "webBelowTitlebar": abs((web.origin.y + web.size.height) - (lambda r: r.origin.y + r.size.height)(nswindow.contentLayoutRect())) < 0.5,
            "titlebarAppearance": {AppKit.NSAppearanceNameAqua: "light", AppKit.NSAppearanceNameDarkAqua: "dark"}.get(look)}


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
    web view and makes the window see-through, the title bar takes the tint it's given (its text
    light over a dark tint) and stays AppKit's own, and Off puts the window back as it was; the
    window is left at level_now."""
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
        check(d["titlebar"] and d["frameUntouched"] and d["webBelowTitlebar"],
              "Glass: the title bar stays AppKit's own (its double-click, drag and buttons), the page just below it")
        apply(window, "clear", [30, 30, 33, 0.5])
        d2 = describe(window)
        check(d2["effect"] == d["effect"] and d2["titlebarTint"] == [30, 30, 33, 0.5], "Glass: changing the level keeps one glass view, with the new tint")
        check(d["titlebarAppearance"] == "light" and d2["titlebarAppearance"] == "dark",
              "Glass: the title's text is dark over a light theme's tint, light over a dark one's")
        apply(window, "off")
        d = describe(window)
        check(d["effect"] is None and d["opaque"] and d["drawsBackground"] and d["titlebar"] and d["webBelowTitlebar"],
              "Glass: Off takes the glass out and the window is solid again")
    finally:
        try:
            if level_now != "off":
                apply(window, level_now)
        except Exception:   # noqa: BLE001 (the window may be closing)
            pass
    failed = [name for ok, name in results if not ok]
    return {"passed": len(results) - len(failed), "total": len(results), "failed": failed}

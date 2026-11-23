"""The document's name in a window's title bar, on a Mac: double-click it to rename the file
(the editor's Rename dialog), or right-click it (Control-click, ⌘-click)
for a menu: Rename…, Show in Finder, Copy File Path, then the file and the folders it's in, as
⌘-click on a document's title gives in Mac apps (choosing a folder shows it in Finder, with the
next one down selected). Everywhere else on the title bar, presses do what macOS does: a
double-click zooms, fills or minimises the window, as set in System Settings ▸ Desktop & Dock.

A local event monitor sees each press before the window does and takes only those on the
title's text. The title is the title bar's own text field (as wide as its text, centred), found
by its text; full screen, which hides the title bar, has none. A double-click elsewhere on the
title bar is AppKit's own, except where the title bar lets it through to the window's content
(a see-through title bar, as glass makes it, does unless AppKit is told otherwise: mac/glass.py):
then the monitor does what System Settings says itself.
"""
from __future__ import annotations

import json
import os
import sys

_state: dict = {}   # the monitor, the menu items' target, the api, and (smoke test) menus not shown


def install(api, path_of, menu_js, sample: tuple = ("Documents", "document_3.txt")) -> None:
    """Watch presses on the app's windows' titles (once; on the main thread).

    path_of(uid)       the file the window with that pywebview uid has open, or None
    menu_js(command)   the JavaScript that runs one of the editor's commands ("rename")
    sample             (folder, file name) the self-test makes, to look at a saved file's menu
    """
    if "monitor" in _state:
        return
    import AppKit
    _state.update(api=api, path_of=path_of, menu_js=menu_js, sample=sample)
    mask = AppKit.NSEventMaskLeftMouseDown | AppKit.NSEventMaskLeftMouseUp | AppKit.NSEventMaskRightMouseDown
    _state["monitor"] = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, on_press)


def _instance(nswindow):
    """pywebview's (uid, BrowserView) for an editor's window, else None."""
    from webview.platforms.cocoa import BrowserView
    for uid, i in list(BrowserView.instances.items()):
        if i.window == nswindow and i.webview is not None:
            return uid, i
    return None


def title_field(nswindow):
    """The title bar's text showing the window's title, or None (full screen hides it)."""
    import AppKit
    close = nswindow.standardWindowButton_(AppKit.NSWindowCloseButton)
    bar = close.superview() if close is not None else None
    title = str(nswindow.title() or "")
    if bar is None or not title:
        return None
    for v in bar.subviews() or []:
        if v.isKindOfClass_(AppKit.NSTextField) and str(v.stringValue()) == title:
            return None if v.isHiddenOrHasHiddenAncestor() else v
    return None


def title_rect(nswindow):
    """Where the title's text is, in window coordinates ((x, y), (w, h)), or None."""
    field = title_field(nswindow)
    return field.convertRect_toView_(field.bounds(), None) if field is not None else None


def on_title(nswindow, point) -> bool:
    """Whether a point (window coordinates) is on the title's text (2 pt above and below too)."""
    r = title_rect(nswindow)
    return r is not None and (r.origin.x <= point.x <= r.origin.x + r.size.width
                              and r.origin.y - 2 <= point.y <= r.origin.y + r.size.height + 2)


def double_click_action(prefs=None) -> str:
    """What a double-click on a window's title bar does, as System Settings ▸ Desktop & Dock ▸
    "Double-click a window's title bar to" has it: "zoom" (Zoom, Fill, or never set: the system's
    own default), "minimize" or "none". prefs: where it's read (the user's defaults; tests)."""
    if prefs is None:
        import Foundation
        prefs = Foundation.NSUserDefaults.standardUserDefaults()
    action = prefs.stringForKey_("AppleActionOnDoubleClick")
    if action is None:   # (never set: the older Minimize switch, else the default)
        return "minimize" if prefs.boolForKey_("AppleMiniaturizeOnDoubleClick") else "zoom"
    return {"Minimize": "minimize", "None": "none"}.get(str(action), "zoom")   # (Maximize, Fill)


def in_titlebar(nswindow, point) -> bool:
    """Whether a point (window coordinates) is on the title bar: above the window's content
    layout area (none in full screen, where the title bar is hidden)."""
    import AppKit
    if not nswindow.styleMask() & AppKit.NSWindowStyleMaskTitled or nswindow.styleMask() & AppKit.NSWindowStyleMaskFullScreen:
        return False
    top, size = nswindow.contentLayoutRect(), nswindow.frame().size
    return top.origin.y + top.size.height <= point.y <= size.height and 0 <= point.x <= size.width


def titlebar_takes(nswindow, point) -> bool:
    """Whether AppKit's own title bar takes a press at this point (window coordinates): the view
    under it is the title bar's, not the window's content under a see-through title bar."""
    frame = nswindow.contentView().superview()
    view = frame.hitTest_(point) if frame is not None else None   # (the frame view's coordinates are the window's)
    while view is not None:
        if "Titlebar" in str(view.className()):
            return True
        view = view.superview()
    return False


def double_click(nswindow, action: str | None = None) -> None:
    """Do what a double-click on the title bar does (when AppKit's own title bar doesn't take it)."""
    action = action or double_click_action()
    if action == "minimize":
        nswindow.miniaturize_(None)
    elif action == "zoom":
        nswindow.zoom_(None)


def on_press(event):
    """The event monitor: a double-click on the title renames the file, a right-click (or a
    Control- or ⌘-click) gives the title's menu; a double-click elsewhere on the title bar that
    AppKit's title bar lets through does what System Settings says; any other press goes on as
    it was."""
    try:
        import AppKit
        win = event.window()
        found = _instance(win) if win is not None else None
        if found is None:
            return event
        kind, flags = event.type(), event.modifierFlags()
        menu_keys = AppKit.NSEventModifierFlagControl | AppKit.NSEventModifierFlagCommand
        where = event.locationInWindow()
        if not on_title(win, where):
            if (kind == AppKit.NSEventTypeLeftMouseDown and event.clickCount() == 2 and not flags & menu_keys
                    and in_titlebar(win, where) and not titlebar_takes(win, where)):
                from PyObjCTools import AppHelper
                AppHelper.callAfter(double_click, win)
                return None
            return event
        uid, inst = found
        if kind == AppKit.NSEventTypeRightMouseDown or (kind == AppKit.NSEventTypeLeftMouseDown and flags & menu_keys):
            at = win.convertPointToScreen_(event.locationInWindow())
            from PyObjCTools import AppHelper
            AppHelper.callAfter(show_menu, uid, (at.x, at.y))   # (once this press has been taken)
            return None
        if event.clickCount() == 2:
            if kind == AppKit.NSEventTypeLeftMouseDown:
                run_in_editor(inst.webview, "rename")
            return None   # (its release too, so the title bar doesn't zoom the window either)
        return event
    except Exception as exc:   # noqa: BLE001 (the press goes on as macOS would take it)
        print(f"Title bar press: {exc}", file=sys.stderr, flush=True)
        return event


def run_in_editor(webview, command: str) -> None:
    """Run one of the editor's commands, as its menu item would (nothing while a dialog is open)."""
    webview.evaluateJavaScript_completionHandler_(_state["menu_js"](command), None)


def _path_of(uid: str) -> str | None:
    """The file a window has open (as its editor last said), or None: never saved."""
    fn = _state.get("path_of")
    return fn(uid) if fn else None


def _target():
    """The object the menu's items call: one, made the first time (an Objective-C class can't
    be defined twice)."""
    if "target" not in _state:
        import Foundation

        class LabappTitleTarget(Foundation.NSObject):
            def titleAction_(self, sender):
                act(json.loads(str(sender.representedObject())))
        _state["target"] = LabappTitleTarget.alloc().init()
    return _state["target"]


def path_chain(path: str) -> list[str]:
    """The file and each folder it's in, innermost first, ending at its disk."""
    chain, p = [], path
    while True:
        chain.append(p)
        parent = os.path.dirname(p)
        if parent == p or os.path.ismount(p):
            return chain
        p = parent


def build_menu(uid: str, path: str | None = None):
    """The title's menu for a window (pywebview's id); `path` stands in for its file (tests)."""
    import AppKit
    path = path if path is not None else _path_of(uid)
    menu = AppKit.NSMenu.alloc().initWithTitle_("")
    menu.setAutoenablesItems_(False)
    ws, fm = AppKit.NSWorkspace.sharedWorkspace(), AppKit.NSFileManager.defaultManager()

    def item(title, action, enabled=True, icon_of=None):
        it = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, b"titleAction:", "")
        it.setTarget_(_target())
        it.setRepresentedObject_(json.dumps(action))
        it.setEnabled_(enabled)
        if icon_of:
            icon = ws.iconForFile_(icon_of)
            icon.setSize_(AppKit.NSMakeSize(16, 16))
            it.setImage_(icon)
        menu.addItem_(it)
    item("Rename…", {"do": "rename", "uid": uid})
    item("Show in Finder", {"do": "show", "path": path}, enabled=bool(path))
    item("Copy File Path", {"do": "copy", "path": path}, enabled=bool(path))
    if path:
        menu.addItem_(AppKit.NSMenuItem.separatorItem())
        chain = path_chain(path)
        for i, p in enumerate(chain):
            # The file shows itself in its folder; a folder opens with the one below it selected
            item(str(fm.displayNameAtPath_(p)), {"do": "show", "path": chain[i - 1] if i else p}, icon_of=p)
    return menu


def show_menu(uid: str, at) -> None:
    """Pop the title's menu up at the pointer (screen coordinates)."""
    menu = build_menu(uid)
    if "shown" in _state:   # (the smoke test: noted, not shown, since a menu waits for a choice)
        _state["shown"].append([str(menu.itemAtIndex_(i).title()) for i in range(menu.numberOfItems())])
        return
    import AppKit
    menu.popUpMenuPositioningItem_atLocation_inView_(None, AppKit.NSMakePoint(*at), None)


def act(action: dict) -> None:
    """Do what one of the menu's items stands for (on the main thread)."""
    import AppKit
    from webview.platforms.cocoa import BrowserView
    if action["do"] == "rename":
        inst = BrowserView.instances.get(action["uid"])
        if inst is not None and inst.webview is not None:
            run_in_editor(inst.webview, "rename")
    elif action["do"] == "show" and action.get("path"):
        AppKit.NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([AppKit.NSURL.fileURLWithPath_(action["path"])])
    elif action["do"] == "copy" and action.get("path"):
        board = AppKit.NSPasteboard.generalPasteboard()
        board.clearContents()
        board.setString_forType_(action["path"], AppKit.NSPasteboardTypeString)


def smoke(window, folder: str) -> dict:
    """Checks for the smoke test (window.py), in its hidden window, with made-up presses handed
    to the monitor (nothing reaches the screen, the clipboard or Finder): the title is found; a
    double-click on it opens the Rename dialog and is taken, as is its release; a single click
    there, and a double-click elsewhere on the title bar, go on to macOS; a right-click is taken
    and gives the menu; the menu for a saved file lists it and its folders. Then real double-clicks
    through the app's event queue (the window on screen unseen for them): on the title, Rename and
    no zoom; elsewhere on the title bar, what System Settings says (zoom, and back with another;
    minimise; nothing), with the window as it is (glass on or off). `folder`: a scratch folder for
    that file."""
    import time

    import AppKit
    from webview.platforms.cocoa import BrowserView

    from . import on_main
    inst = BrowserView.instances[window.uid]
    nswin, results = inst.window, []

    def check(ok, name):
        results.append((bool(ok), name))

    def press(kind, point, clicks=1, flags=0):
        def make():
            ev = AppKit.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
                kind, point, flags, AppKit.NSProcessInfo.processInfo().systemUptime(), nswin.windowNumber(), None, 0, clicks,
                1.0 if kind != AppKit.NSEventTypeLeftMouseUp else 0.0)
            return on_press(ev) is None   # taken
        return on_main(make)

    def dialog_open():
        return bool(window.evaluate_js("!!document.querySelector('dialog[open] #rename-input')"))

    rect = on_main(lambda: title_rect(nswin))
    check(rect is not None and rect.size.width > 0, "the title's text is found in the title bar")
    if rect is None:
        return {"passed": 0, "total": 1, "failed": ["the title's text is found in the title bar"]}
    mid = AppKit.NSMakePoint(rect.origin.x + rect.size.width / 2, rect.origin.y + rect.size.height / 2)
    beside = AppKit.NSMakePoint(rect.origin.x + rect.size.width + 120, mid.y)
    down, up, right = AppKit.NSEventTypeLeftMouseDown, AppKit.NSEventTypeLeftMouseUp, AppKit.NSEventTypeRightMouseDown
    check(not press(down, mid, 1), "a single click on the title goes on to macOS (moving the window)")
    check(not press(down, beside, 2), "a double-click elsewhere on the title bar goes on to macOS (zoom)")
    took, took_up = press(down, mid, 2), press(up, mid, 2)
    opened = False
    for _ in range(50):
        if dialog_open():
            opened = True
            break
        time.sleep(0.1)
    check(took and took_up and opened, "a double-click on the title opens the Rename dialog, and isn't the title bar's")
    window.evaluate_js("document.querySelector('dialog[open]')?.close()")
    # Through the app's own event queue too, as a real double-click comes: the monitor is installed
    # and sees it there, and AppKit's title bar gets what it lets by (posted to this app alone; the
    # pointer and other apps never see it). A hidden window takes nothing from the queue, so it is
    # put on screen for this unseen: fully see-through, behind every window, real presses passing
    # through it to what's under it, and not brought forward or made active
    first = on_main(lambda: tuple(nswin.frame()))
    hidden = on_main(lambda: not nswin.isVisible())
    if hidden:
        was = on_main(lambda: (nswin.alphaValue(), nswin.ignoresMouseEvents()))

        def unseen():
            nswin.setAlphaValue_(0.0)
            nswin.setIgnoresMouseEvents_(True)
            nswin.orderWindow_relativeTo_(AppKit.NSWindowBelow, 0)
        on_main(unseen)
        time.sleep(0.3)
    frame = on_main(lambda: tuple(nswin.frame()))   # (on screen, macOS may have moved it onto one)

    def post(point_of, clicks=(2,)):
        def go():
            point = point_of()
            for n in clicks:
                for kind in (down, up):
                    AppKit.NSApp.postEvent_atStart_(
                        AppKit.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
                            kind, point, 0, AppKit.NSProcessInfo.processInfo().systemUptime(), nswin.windowNumber(), None, 0, n,
                            1.0 if kind == down else 0.0), False)
        on_main(go)

    def now():
        return on_main(lambda: (tuple(nswin.frame()), bool(nswin.isMiniaturized())))

    def wait_for(cond, seconds=5.0):
        for _ in range(int(seconds * 10)):
            if cond(now()):
                time.sleep(0.6)   # (the window's own animation done)
                return True
            time.sleep(0.1)
        return False

    def bar_point():
        """On the title bar between the window's buttons and the title, wherever the window is now."""
        r, top = title_rect(nswin), nswin.contentLayoutRect()
        zoom = nswin.standardWindowButton_(AppKit.NSWindowZoomButton)
        left = zoom.convertRect_toView_(zoom.bounds(), None) if zoom is not None else AppKit.NSMakeRect(0, 0, 60, 0)
        x = (left.origin.x + left.size.width + (r.origin.x if r is not None else 260)) / 2
        return AppKit.NSMakePoint(x, (top.origin.y + top.size.height + nswin.frame().size.height) / 2)

    def title_mid():
        """The middle of the title, where it is now (macOS may have moved the window)."""
        r = title_rect(nswin)
        return AppKit.NSMakePoint(r.origin.x + r.size.width / 2, r.origin.y + r.size.height / 2) if r is not None else mid
    try:
        post(title_mid)
        opened = False
        for _ in range(50):
            if dialog_open():
                opened = True
                break
            time.sleep(0.1)
        time.sleep(0.6)   # (a zoom would have started by now)
        check(opened and on_main(lambda: tuple(nswin.frame())) == frame,
              "a double-click from the event queue opens Rename too, and the window isn't zoomed")
        window.evaluate_js("document.querySelector('dialog[open]')?.close()")
        # Elsewhere on the title bar: what System Settings ▸ Desktop & Dock says a double-click does
        action = on_main(double_click_action)
        post(bar_point, clicks=(1, 2))
        if action == "zoom":
            zoomed = wait_for(lambda st: st[0] != frame)
            post(bar_point, clicks=(1, 2))
            back = wait_for(lambda st: st[0] == frame)
            check(zoomed and back, "a double-click elsewhere on the title bar zooms the window, and another puts it back")
        elif action == "minimize":
            check(wait_for(lambda st: st[1]), "a double-click elsewhere on the title bar minimises the window")
            on_main(lambda: nswin.deminiaturize_(None))
            wait_for(lambda st: not st[1])
        else:
            time.sleep(1.0)
            check(now() == (frame, False), "a double-click elsewhere on the title bar does nothing (System Settings: Do Nothing)")
    finally:
        def put_back():
            if nswin.isMiniaturized():
                nswin.deminiaturize_(None)
            if tuple(nswin.frame()) != first:
                nswin.setFrame_display_(first, False)
            if hidden:
                nswin.orderOut_(None)
                nswin.setAlphaValue_(was[0])
                nswin.setIgnoresMouseEvents_(was[1])
        on_main(put_back)
    _state["shown"] = []
    try:
        took = press(right, mid)
        for _ in range(30):
            if _state["shown"]:
                break
            time.sleep(0.1)
        shown = _state["shown"][0] if _state["shown"] else []
        check(took and shown[:3] == ["Rename…", "Show in Finder", "Copy File Path"], "a right-click on the title gives its menu")
    finally:
        _state.pop("shown", None)
    sample_folder, sample_file = _state.get("sample") or ("Documents", "document_3.txt")
    doc = os.path.join(folder, sample_folder, sample_file)
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    open(doc, "a").close()

    def saved_menu():
        m = build_menu(window.uid, path=doc)
        return [(str(m.itemAtIndex_(i).title()), m.itemAtIndex_(i).isEnabled(), m.itemAtIndex_(i).isSeparatorItem())
                for i in range(m.numberOfItems())]
    items = on_main(saved_menu)
    names = [t for t, _, sep in items if not sep]
    check([t for t, on, _ in items[:3] if on] == ["Rename…", "Show in Finder", "Copy File Path"] and items[3][2]
          and names[3] in (sample_file, os.path.splitext(sample_file)[0]) and names[4] == sample_folder and len(names) == 3 + len(path_chain(doc)),
          "a saved file's menu: Show in Finder and Copy File Path, then it and each folder it's in")
    failed = [name for ok, name in results if not ok]
    return {"passed": len(results) - len(failed), "total": len(results), "failed": failed}

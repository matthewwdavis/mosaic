"""The menu bar on a Mac: the app's own menu, then File, Edit, View… as the app lists them, Window
and Help, each command with its keyboard shortcut, as Mac apps have them (pywebview's own has only
Edit and View, without shortcuts).

The app says who it is once, before anything else here is used:

    menu.configure(name="mosaic", version=__version__, js="FA", app_items=[("Check for Updates…", "checkForUpdates")])

js is the editor's global object in its page: a menu item runs window.<js>.menu(command).

The editor describes its menus (app.menuSpec in main.js: titles, its commands' names and
shortcuts), so they always match its commands. Choosing one runs it in the editor of the window
in front (window.<js>.menu), which, as the keys do, does nothing while a dialog is open. Cut, Copy,
Paste, Undo, Redo, Select All and Delete ask the editor first (window.<js>.menuEdit): in a text
field they're the web view's own text editing, otherwise the editor's commands. The app's own
and Window menus are made here with AppKit's standard items; Help gets macOS's search box. The
ticks are the front window's: each window sends its own when it comes to the front.

macOS names an app from its bundle: a packaged app runs Python from inside itself. Started some
other way, name_app() tells macOS the name.
"""
from __future__ import annotations

import json
import os

# Who the app is (configure): its name and version, its editor's global object, the items its own
# menu has after About (title, command), and a function to call before a text action (paste…)
cfg: dict = {"name": "app", "version": "", "js": "APP", "app_items": [], "before_edit": None}


def configure(**values) -> None:
    unknown = set(values) - set(cfg)
    if unknown:
        raise TypeError(f"not a menu setting: {sorted(unknown)}")
    cfg.update(values)


def _js(call: str) -> str:
    """window.<the editor's object> && window.<it>.<call>"""
    return f"window.{cfg['js']} && window.{cfg['js']}.{call}"


# Menu actions that a text field does itself: AppKit's action for each (Undo and Redo are the
# window's undo manager's, where WebKit keeps a field's typing)
FIELD_ACTIONS = {"cut": "cut:", "copy": "copy:", "paste": "paste:", "selectAll": "selectAll:", "delete": "delete:",
                 "undo": None, "redo": None}
_state: dict = {}   # target, api, items by action, the Open Recent menu, the window last in front


def note_front(uid: str | None) -> None:
    """The window (pywebview's id) last in front: the menus' commands go to it while the app
    is in the background too (a document double-clicked in Finder meanwhile, say)."""
    _state["front"] = uid


def front_uid(uids=None) -> str | None:
    """The window in front (pywebview's id), of these (default: any): the key window, else the
    one last in front, else the frontmost on screen, else the first."""
    import AppKit
    from webview.platforms.cocoa import BrowserView
    insts = {uid: i for uid, i in list(BrowserView.instances.items()) if (uids is None or uid in uids) and i.webview is not None}
    if not insts:
        return None
    for win in (AppKit.NSApp.keyWindow(), AppKit.NSApp.mainWindow()):
        for uid, i in insts.items():
            if win is not None and i.window == win:
                return uid
    if _state.get("front") in insts:
        return _state["front"]
    for win in AppKit.NSApp.orderedWindows() or []:
        for uid, i in insts.items():
            if i.window == win:
                return uid
    return next(iter(insts))


def front_view(uids=None):
    """The web view of the window in front (see front_uid), or None."""
    from webview.platforms.cocoa import BrowserView
    uid = front_uid(uids)
    return BrowserView.instances[uid].webview if uid is not None else None


def _watch_front() -> None:
    """Note each window that comes to the front, and have its editor send its ticks (once)."""
    if "observer" in _state:
        return
    import AppKit
    import Foundation

    class LabappFrontWindow(Foundation.NSObject):
        def windowBecameKey_(self, note):
            from webview.platforms.cocoa import BrowserView
            for uid, i in list(BrowserView.instances.items()):
                if i.window == note.object() and i.webview is not None:
                    note_front(uid)
                    i.webview.evaluateJavaScript_completionHandler_(_js("app.syncMenus()"), None)
    _state["observer"] = LabappFrontWindow.alloc().init()
    Foundation.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
        _state["observer"], b"windowBecameKey:", AppKit.NSWindowDidBecomeKeyNotification, None)


def key_equivalent(keys: str | None) -> tuple[str, int] | None:
    """A menu's key and modifiers for a shortcut as the editor writes it ("⌘⇧S", "⌘+", "⌘−"),
    or None for one without ⌘ (plain keys stay the page's: a menu would take them from typing)."""
    if not keys or "⌘" not in keys:
        return None
    flags = {"⌘": 1 << 20, "⇧": 1 << 17, "⌥": 1 << 19, "⌃": 1 << 18}   # NSEventModifierFlag Command, Shift, Option, Control
    mask, rest = 0, ""
    for ch in keys:
        if ch in flags:
            mask |= flags[ch]
        else:
            rest += ch
    rest = {"−": "-"}.get(rest, rest)
    return (rest.lower(), mask) if len(rest) == 1 else None


def _target():
    """The object menu items call: one, made the first time (an Objective-C class can't be
    defined twice)."""
    if "target" not in _state:
        import AppKit
        import Foundation

        class LabappMenuTarget(Foundation.NSObject):
            def menuAction_(self, sender):
                act(str(sender.representedObject()))

            def validateMenuItem_(self, item):
                return True
        _state["target"] = LabappMenuTarget.alloc().init()
        _state["AppKit"] = AppKit
    return _state["target"]


def act(action: str) -> None:
    """Do what a menu item stands for, in the window in front (on the main thread)."""
    AppKit = _state["AppKit"]
    view = front_view() if action not in ("about", "clearRecent") and not action.startswith("url:") else None
    if action == "about":
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        AppKit.NSApp.orderFrontStandardAboutPanelWithOptions_(
            {"ApplicationName": cfg["name"], "ApplicationVersion": cfg["version"], "Version": ""})
    elif action.startswith("url:"):
        AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(action[4:]))
    elif action == "clearRecent":
        if _state.get("api") is not None:
            _state["api"].prefs_set({"recent": []})
        set_recent([])
    elif view is None:
        return
    elif action in FIELD_ACTIONS:
        if cfg["before_edit"]:
            cfg["before_edit"](action)

        def done(in_field, error):
            if not in_field:
                return
            if FIELD_ACTIONS[action] is None:
                undo = view.undoManager()
                if undo is not None and (undo.canUndo() if action == "undo" else undo.canRedo()):
                    undo.undo() if action == "undo" else undo.redo()
            else:   # the web view's own text editing, for the field it has (passed on if it hasn't one)
                view.tryToPerform_with_(FIELD_ACTIONS[action], None)
        view.evaluateJavaScript_completionHandler_("!!(" + _js(f"menuEdit({json.dumps(action)})") + ")", done)
    else:
        view.evaluateJavaScript_completionHandler_(_js(f"menu({json.dumps(action)})"), None)


def _item(title: str, action: str | None = None, keys=None, selector: str | None = None, check=None):
    """A menu item that runs an action of ours (`action`) or AppKit's (`selector`, sent along the
    responder chain); `keys` as the editor writes a shortcut, or (key, modifiers)."""
    AppKit = _state["AppKit"]
    key, mask = keys if isinstance(keys, tuple) else (key_equivalent(keys) or ("", 0))
    item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector or "menuAction:", key)
    if key:
        item.setKeyEquivalentModifierMask_(mask)
    if action is not None:
        item.setTarget_(_target())
        item.setRepresentedObject_(action)
        _state["items"].setdefault(action, []).append(item)
    if check is not None:
        item.setState_(1 if check else 0)
    return item


def _submenu(parent, title: str):
    AppKit = _state["AppKit"]
    menu = AppKit.NSMenu.alloc().initWithTitle_(title)
    holder = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
    holder.setSubmenu_(menu)
    parent.addItem_(holder)
    return menu


def _fill(menu, items: list) -> None:
    """A menu's items from the editor's description: "-" for a line; {title, items} a submenu;
    {title, recent} Open Recent; {title, url}; {title, selector, keys} AppKit's own action;
    {title, action, keys, check}."""
    AppKit = _state["AppKit"]
    for it in items:
        if it == "-":
            menu.addItem_(AppKit.NSMenuItem.separatorItem())
        elif "items" in it:
            _fill(_submenu(menu, it["title"]), it["items"])
        elif it.get("recent"):
            _state["recent"] = _submenu(menu, it["title"])
            _state["recent"].setAutoenablesItems_(False)
        elif it.get("url"):
            menu.addItem_(_item(it["title"], f"url:{it['url']}"))
        elif it.get("selector"):
            menu.addItem_(_item(it["title"], keys=it.get("keys"), selector=it["selector"]))
        else:
            menu.addItem_(_item(it["title"], it["action"], it.get("keys"), check=it.get("check")))


def build(window, api, spec: list, recent: list[str]) -> None:
    """The menu bar, from the editor's description of its menus (on the main thread)."""
    import AppKit
    _target()
    _watch_front()
    _state.update(api=api, items={}, recent=None)
    cmd, opt = 1 << 20, 1 << 19
    main = AppKit.NSMenu.alloc().initWithTitle_("Main menu")
    app = _submenu(main, cfg["name"])
    app.addItem_(_item(f"About {cfg["name"]}", "about"))
    for title, command in cfg["app_items"]:
        app.addItem_(_item(title, command))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    app.addItem_(_item("Settings…", "preferences", (",", cmd)))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    AppKit.NSApp.setServicesMenu_(_submenu(app, "Services"))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    app.addItem_(_item(f"Hide {cfg["name"]}", keys=("h", cmd), selector="hide:"))
    app.addItem_(_item("Hide Others", keys=("h", cmd | opt), selector="hideOtherApplications:"))
    app.addItem_(_item("Show All", selector="unhideAllApplications:"))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    app.addItem_(_item(f"Quit {cfg["name"]}", keys=("q", cmd), selector="terminate:"))
    for m in spec:
        menu = _submenu(main, m["title"])
        _fill(menu, m.get("items", []))
        if m.get("window"):
            # AppKit adds the window list (and Fill, Centre, Move & Resize) below these
            menu.addItem_(_item("Minimize", keys=("m", cmd), selector="performMiniaturize:"))
            menu.addItem_(_item("Zoom", selector="performZoom:"))
            menu.addItem_(AppKit.NSMenuItem.separatorItem())
            menu.addItem_(_item("Bring All to Front", selector="arrangeInFront:"))
            AppKit.NSApp.setWindowsMenu_(menu)
        if m.get("help"):
            AppKit.NSApp.setHelpMenu_(menu)
    AppKit.NSApp.setMainMenu_(main)
    set_recent(recent)


def set_checks(checks: dict, uid: str | None = None) -> None:
    """Ticks on the menu items for these actions (on the main thread), from the window `uid`:
    only if it's the one in front."""
    if uid is not None and front_uid() not in (None, uid):
        return
    for action, on in checks.items():
        for item in _state.get("items", {}).get(action, []):
            item.setState_(1 if on else 0)


def set_recent(paths: list[str]) -> None:
    """Open Recent: the documents opened or saved lately, then Clear Menu (on the main thread)."""
    menu = _state.get("recent")
    if menu is None:
        return
    AppKit = _state["AppKit"]
    menu.removeAllItems()
    for p in paths:
        item = _item(os.path.basename(p), f"open:{p}")
        item.setToolTip_(p)
        item.setEnabled_(os.path.exists(p))
        menu.addItem_(item)
    if paths:
        menu.addItem_(AppKit.NSMenuItem.separatorItem())
    clear = _item("Clear Menu", "clearRecent")
    clear.setEnabled_(bool(paths))
    menu.addItem_(clear)


def name_app() -> None:
    """Started other than from its .app (from a terminal, say), macOS would call the app
    after Python. Tell it the name instead (LaunchServices' display name, as Java's -Xdock:name
    does), and give the bundle that name for anything that asks it. Best effort."""
    import ctypes

    import AppKit
    import Foundation
    info = Foundation.NSBundle.mainBundle().infoDictionary()
    if info is not None and info.get("CFBundleName") == cfg["name"]:
        return   # a packaged app
    AppKit.NSApplication.sharedApplication()
    try:
        info["CFBundleName"] = cfg["name"]
    except Exception:   # noqa: BLE001 (a bundle whose information can't be changed)
        pass
    services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreServices.framework/CoreServices")
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    services._LSGetCurrentApplicationASN.restype = ctypes.c_void_p
    services._LSSetApplicationInformationItem.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                         ctypes.c_void_p]
    asn = services._LSGetCurrentApplicationASN()
    if asn:
        key = ctypes.c_void_p.in_dll(services, "_kLSDisplayNameKey")
        name = cf.CFStringCreateWithCString(None, cfg["name"].encode(), 0x08000100)   # UTF-8
        services._LSSetApplicationInformationItem(-2, asn, key, name, None)   # -2: this session


# For an app's own check of its menus (its smoke test) ------------------------------------------------

def find(path: list[str]):
    """The menu item at a path of titles (["View", "Rulers"]); on the main thread."""
    AppKit = _state["AppKit"]
    menu = AppKit.NSApp.mainMenu()
    for title in path[:-1]:
        menu = menu.itemWithTitle_(title).submenu()
    return menu.itemAtIndex_(menu.indexOfItemWithTitle_(path[-1]))


def shortcut(path: list[str]) -> tuple[str, int]:
    """A menu item's key and modifiers."""
    from . import on_main
    return on_main(lambda: (str(find(path).keyEquivalent()), int(find(path).keyEquivalentModifierMask())))


def choose(path: list[str]) -> None:
    """Choose a menu item, as a click would; on the main thread."""
    item = find(path)
    item.menu().performActionForItemAtIndex_(item.menu().indexOfItem_(item))


def titles() -> list[str]:
    """The menu bar's menus."""
    from . import on_main
    return on_main(lambda: [str(it.title()) for it in _state["AppKit"].NSApp.mainMenu().itemArray()])

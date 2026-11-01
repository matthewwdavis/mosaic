"""The menu bar on a Mac: FigAssemble, File, Edit, View, Window and Help, each command with its
keyboard shortcut, as Mac apps have them (pywebview's own has only Edit and View, without
shortcuts).

The editor describes its menus (app.menuSpec in main.js: titles, its commands' names and
shortcuts), so they always match its commands. Choosing one runs it in the editor
(window.FA.menu), which, as the keys do, does nothing while a dialog is open. Cut, Copy, Paste,
Undo, Redo, Select All and Delete ask the editor first (window.FA.menuEdit): in a text field
they're the web view's own text editing, otherwise the editor's commands. The FigAssemble and
Window menus are made here with AppKit's standard items; Help gets macOS's search box.

macOS names an app from its bundle: FigAssemble.app runs Python from inside itself
(packaging/macos/make_app.py). Started some other way, name_app() tells macOS the name.
"""
from __future__ import annotations

import json
import os

from .. import __version__

APP_NAME = "FigAssemble"
# Menu actions that a text field does itself: AppKit's action for each (Undo and Redo are the
# window's undo manager's, where WebKit keeps a field's typing)
FIELD_ACTIONS = {"cut": "cut:", "copy": "copy:", "paste": "paste:", "selectAll": "selectAll:", "delete": "delete:",
                 "undo": None, "redo": None}
_state: dict = {}   # target, view, api, items by action, the Open Recent menu


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

        class FigAssembleMenuTarget(Foundation.NSObject):
            def menuAction_(self, sender):
                act(str(sender.representedObject()))

            def validateMenuItem_(self, item):
                return True
        _state["target"] = FigAssembleMenuTarget.alloc().init()
        _state["AppKit"] = AppKit
    return _state["target"]


def act(action: str) -> None:
    """Do what a menu item stands for (on the main thread)."""
    AppKit = _state["AppKit"]
    view = _state.get("view")
    if action == "about":
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        AppKit.NSApp.orderFrontStandardAboutPanelWithOptions_(
            {"ApplicationName": APP_NAME, "ApplicationVersion": __version__, "Version": ""})
    elif action.startswith("url:"):
        AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(action[4:]))
    elif action == "clearRecent":
        if _state.get("api") is not None:
            _state["api"].prefs_set({"recent": []})
        set_recent([])
    elif view is None:
        return
    elif action in FIELD_ACTIONS:
        def done(in_field, error):
            if not in_field:
                return
            if FIELD_ACTIONS[action] is None:
                undo = view.undoManager()
                if undo is not None and (undo.canUndo() if action == "undo" else undo.canRedo()):
                    undo.undo() if action == "undo" else undo.redo()
            else:   # the web view's own text editing, for the field it has (passed on if it hasn't one)
                view.tryToPerform_with_(FIELD_ACTIONS[action], None)
        view.evaluateJavaScript_completionHandler_(f"!!(window.FA && window.FA.menuEdit({json.dumps(action)}))", done)
    else:
        view.evaluateJavaScript_completionHandler_(f"window.FA && window.FA.menu({json.dumps(action)})", None)


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
    from webview.platforms.cocoa import BrowserView
    _target()
    _state.update(view=BrowserView.instances[window.uid].webview, api=api, items={}, recent=None)
    cmd, opt = 1 << 20, 1 << 19
    main = AppKit.NSMenu.alloc().initWithTitle_("Main menu")
    app = _submenu(main, APP_NAME)
    app.addItem_(_item(f"About {APP_NAME}", "about"))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    app.addItem_(_item("Settings…", "preferences", (",", cmd)))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    AppKit.NSApp.setServicesMenu_(_submenu(app, "Services"))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    app.addItem_(_item(f"Hide {APP_NAME}", keys=("h", cmd), selector="hide:"))
    app.addItem_(_item("Hide Others", keys=("h", cmd | opt), selector="hideOtherApplications:"))
    app.addItem_(_item("Show All", selector="unhideAllApplications:"))
    app.addItem_(AppKit.NSMenuItem.separatorItem())
    app.addItem_(_item(f"Quit {APP_NAME}", keys=("q", cmd), selector="terminate:"))
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


def set_checks(checks: dict) -> None:
    """Ticks on the menu items for these actions (on the main thread)."""
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
    """Started other than from FigAssemble.app (from a terminal, say), macOS would call the app
    after Python. Tell it the name instead (LaunchServices' display name, as Java's -Xdock:name
    does), and give the bundle that name for anything that asks it. Best effort."""
    import ctypes

    import AppKit
    import Foundation
    info = Foundation.NSBundle.mainBundle().infoDictionary()
    if info is not None and info.get("CFBundleName") == APP_NAME:
        return   # FigAssemble.app
    AppKit.NSApplication.sharedApplication()
    try:
        info["CFBundleName"] = APP_NAME
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
        name = cf.CFStringCreateWithCString(None, APP_NAME.encode(), 0x08000100)   # UTF-8
        services._LSSetApplicationInformationItem(-2, asn, key, name, None)   # -2: this session


def smoke(window) -> dict:
    """The smoke test's check, in the app window: the menu bar's menus, its name and shortcuts,
    and a menu item doing what the editor's command does. {"passed", "total", "failed": [names]}."""
    import time

    import AppKit

    from .keycheck import on_main

    def find(path):
        menu = AppKit.NSApp.mainMenu()
        for title in path[:-1]:
            menu = menu.itemWithTitle_(title).submenu()
        return menu.itemAtIndex_(menu.indexOfItemWithTitle_(path[-1]))

    def shortcut(path):
        return on_main(lambda: (str(find(path).keyEquivalent()), int(find(path).keyEquivalentModifierMask())))

    def choose(path):
        item = find(path)
        item.menu().performActionForItemAtIndex_(item.menu().indexOfItem_(item))

    def wait(cond, seconds=5.0):
        for _ in range(int(seconds * 10)):
            if cond():
                return True
            time.sleep(0.1)
        return False

    titles = lambda: on_main(lambda: [str(it.title()) for it in AppKit.NSApp.mainMenu().itemArray()])   # noqa: E731
    results = {}
    results["the menu bar has FigAssemble, File, Edit, View, Window and Help"] = wait(
        lambda: titles() == [APP_NAME, "File", "Edit", "View", "Window", "Help"])
    results["macOS calls the app FigAssemble"] = on_main(
        lambda: str(AppKit.NSRunningApplication.currentApplication().localizedName())) == APP_NAME
    cmd, shift = 1 << 20, 1 << 17
    results["the menus show the shortcuts (Save ⌘S, Save As ⇧⌘S, Rulers ⌘R, Settings ⌘,)"] = (
        shortcut(["File", "Save"]) == ("s", cmd) and shortcut(["File", "Save As…"]) == ("s", cmd | shift)
        and shortcut(["View", "Rulers"]) == ("r", cmd) and shortcut([APP_NAME, "Settings…"]) == (",", cmd))
    # (macOS adds Dictation and Emoji & Symbols to Edit, with hidden copies for other shortcuts)
    edit = on_main(lambda: [str(it.title()) for it in AppKit.NSApp.mainMenu().itemWithTitle_("Edit").submenu().itemArray()
                            if not it.isHidden()])
    results["Edit has Undo to Paste Style, and macOS's own items once each"] = (
        edit[:3] == ["Undo", "Redo", ""] and all(edit.count(t) == 1 for t in edit if t))
    before = bool(window.evaluate_js("window.FA.app.prefs.show_rulers"))
    on_main(lambda: choose(["View", "Rulers"]))
    switched = wait(lambda: bool(window.evaluate_js("window.FA.app.prefs.show_rulers")) != before)
    ticked = wait(lambda: on_main(lambda: int(find(["View", "Rulers"]).state())) == (0 if before else 1))
    results["View > Rulers switches the rulers, and its tick follows"] = switched and ticked
    window.evaluate_js("window.FA.app.menu('toggleRulers')")   # back as they were
    # Edit > Select All: the page's objects, or a text field's text while one is typed in
    window.evaluate_js("""(() => { const s = window.FA.store, shape = (id, x) => ({ id, type: "shape", geom: "rect",
        frame: [x, 10, 20, 20], rot: 0, stroke: null, fill: { color: "#336699", opacity: 1 } });
      s.update("Two shapes", (d) => d.pages[s.pageIndex].items.push(shape("menuA", 10), shape("menuB", 40)));
      s.select([]); document.activeElement?.blur(); return true; })()""")
    on_main(lambda: choose(["Edit", "Select All"]))
    objects = wait(lambda: window.evaluate_js("""(() => { const s = window.FA.store, all = s.scopeItems().filter((i) => !i.locked);
      return all.length >= 2 && s.selection.length === all.length; })()"""))
    window.evaluate_js("""(() => { window.FA.store.select([]); window.FA.inspector.render();
      const f = document.querySelector("#inspector input[type=text]"); f.focus(); f.setSelectionRange(0, 0); return true; })()""")
    on_main(lambda: choose(["Edit", "Select All"]))
    text = wait(lambda: window.evaluate_js("""(() => { const f = document.activeElement;
      return !!f && f.value.length > 0 && f.selectionStart === 0 && f.selectionEnd === f.value.length
        && window.FA.store.selection.length === 0; })()"""))
    results["Edit > Select All selects the page's objects"] = objects
    results["and a text field's text while one is typed in"] = text
    results["Window and Help are macOS's own (the window list; Help's search box)"] = on_main(
        lambda: str(AppKit.NSApp.windowsMenu().title()) == "Window" and str(AppKit.NSApp.helpMenu().title()) == "Help")
    return {"passed": sum(results.values()), "total": len(results), "failed": [k for k, v in results.items() if not v]}

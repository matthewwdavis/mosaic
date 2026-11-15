"""The menu bar on a Mac: mosaic, File, Edit, View, Window and Help, each command with its
keyboard shortcut, as Mac apps have them. The menu bar itself is the shared library's
(_labapp/mac/menu.py: building it from the editor's list, ticks, Open Recent, the app's name);
this says what is mosaic's (its name, its editor's object window.FA, Check for Updates) and holds
the smoke test's check of mosaic's own menus.

macOS names an app from its bundle: mosaic.app runs Python from inside itself
(packaging/macos/make_app.py). Started some other way, name_app() tells macOS the name.
"""
from __future__ import annotations

from .. import __version__
from .._labapp.mac import menu as _shared
from .._labapp.mac.menu import (FIELD_ACTIONS, _fill, _item, _state, _submenu, _target, act, build, front_uid,   # noqa: F401
                                front_view, key_equivalent, name_app, note_front, set_checks, set_recent)

APP_NAME = "mosaic"
_shared.configure(name=APP_NAME, version=__version__, js="FA", app_items=[("Check for Updates…", "checkForUpdates")])


def smoke(window) -> dict:
    """The smoke test's check, in the app window: the menu bar's menus, its name and shortcuts,
    and a menu item doing what the editor's command does. {"passed", "total", "failed": [names]}."""
    import time

    import AppKit

    from .._labapp.mac import on_main
    find, shortcut, choose = _shared.find, _shared.shortcut, _shared.choose

    def wait(cond, seconds=5.0):
        for _ in range(int(seconds * 10)):
            if cond():
                return True
            time.sleep(0.1)
        return False

    titles = lambda: on_main(lambda: [str(it.title()) for it in AppKit.NSApp.mainMenu().itemArray()])   # noqa: E731
    results = {}
    results["the menu bar has mosaic, File, Edit, View, Window and Help"] = wait(
        lambda: titles() == [APP_NAME, "File", "Edit", "View", "Window", "Help"])
    results["macOS calls the app mosaic"] = on_main(
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
    # The arrow keys' switch, clicked in the status bar: the View menu's tick follows
    arrows = ["View", "Arrow Keys Follow the Zoom"]
    on = bool(window.evaluate_js("window.FA.app.prefs.nudge_zoom"))
    shown = on_main(lambda: AppKit.NSApp.mainMenu().itemWithTitle_("View").submenu().indexOfItemWithTitle_(arrows[1]) >= 0) and wait(
        lambda: on_main(lambda: int(find(arrows).state())) == (1 if on else 0))
    window.evaluate_js("document.querySelector('.nudge-step').click()")
    followed = wait(lambda: on_main(lambda: int(find(arrows).state())) == (0 if on else 1))
    window.evaluate_js("document.querySelector('.nudge-step').click()")   # back as it was
    results["View > Arrow Keys Follow the Zoom shows the status bar's switch"] = shown and followed and wait(
        lambda: bool(window.evaluate_js("window.FA.app.prefs.nudge_zoom")) == on)
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
    # Edit > Select Same > Fill Colour (a submenu): the shapes filled like the selected one
    window.evaluate_js("""(() => { const s = window.FA.store;
      s.update("Another colour", (d) => d.pages[s.pageIndex].items.push({ id: "menuC", type: "shape", geom: "rect",
        frame: [70, 10, 20, 20], rot: 0, stroke: null, fill: { color: "#993366", opacity: 1 } }), { select: ["menuA"] });
      document.activeElement?.blur(); return true; })()""")
    on_main(lambda: choose(["Edit", "Select Same", "Fill Colour"]))
    results["Edit > Select Same > Fill Colour selects the shapes filled the same"] = wait(
        lambda: window.evaluate_js("window.FA.store.selection.join() === 'menuA,menuB'"))
    # mosaic > Check for Updates…: says what there is (from a checkout, that it doesn't update itself)
    on_main(lambda: choose([APP_NAME, "Check for Updates…"]))
    said = wait(lambda: window.evaluate_js(
        "[...document.querySelectorAll('dialog[open] h2')].some((e) => e.textContent === 'Check for updates')"))
    window.evaluate_js("document.querySelectorAll('dialog[open]').forEach((d) => d.close())")
    results["mosaic > Check for Updates… looks and says what there is"] = said
    results["Window and Help are macOS's own (the window list; Help's search box)"] = on_main(
        lambda: str(AppKit.NSApp.windowsMenu().title()) == "Window" and str(AppKit.NSApp.helpMenu().title()) == "Help")
    return {"passed": sum(results.values()), "total": len(results), "failed": [k for k, v in results.items() if not v]}

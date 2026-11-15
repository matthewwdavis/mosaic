"""The Mac's close question (closing.py has what its answers do): a sheet on the figure's window,
with Save (Return), Cancel (Escape) and Don't Save (⌘D).

Quitting asks about each unsaved figure in turn, its window brought to the front, through
pywebview's application delegate (whose own question is an alert per window, nameless, with
no Save). mosaic quits once each is saved or answered Don't Save, and stays open at a Cancel or
a save that didn't happen.
"""
from __future__ import annotations

import os
import sys

CHOICES = {1000: "save", 1001: "cancel", 1002: "discard"}   # the sheet's buttons, as added
TERMINATE_CANCEL, TERMINATE_NOW = 0, 1   # NSApplicationTerminateReply
_state: dict = {"alerts": {}, "quitting": False, "leaving": False}


def ask(api, window, q: dict, reply) -> None:
    """The question as a sheet on the window (on the main thread); reply(choice) once answered,
    or "cancel" at once if the window is gone or asking already."""
    import AppKit
    from webview.platforms.cocoa import BrowserView
    view = BrowserView.instances.get(window.uid)
    if view is None or view.window.attachedSheet() is not None:
        reply("cancel")
        return
    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(q["message"])
    alert.setInformativeText_(q["detail"])
    alert.addButtonWithTitle_(q["save"])
    alert.addButtonWithTitle_("Cancel")
    dont = alert.addButtonWithTitle_("Don’t Save")
    dont.setKeyEquivalent_("d")
    dont.setKeyEquivalentModifierMask_(AppKit.NSEventModifierFlagCommand)
    if not api.hidden_windows:
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        view.window.makeKeyAndOrderFront_(None)
    _state["alerts"][window.uid] = alert

    def answered(code):
        _state["alerts"].pop(window.uid, None)
        reply(CHOICES.get(int(code), "cancel"))
    alert.beginSheetModalForWindow_completionHandler_(view.window, answered)


def should_quit(api) -> int:
    """mosaic is quitting: with nothing unsaved, now. Else not yet: each unsaved figure asks in
    turn, front window first, and once each is saved or answered Don't Save mosaic quits itself.
    A Cancel, or a save that doesn't happen, stops it; another quit meanwhile changes nothing.
    (Not NSTerminateLater: while that waits, a second quit ends the app without asking.)"""
    if _state["leaving"]:
        return TERMINATE_NOW   # (every figure answered)
    if _state["quitting"]:
        return TERMINATE_CANCEL   # (asking already)
    import AppKit
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    from .closing import ask as ask_about
    views = BrowserView.instances
    kept: set[str] = set()   # windows answered Don't Save, still unsaved

    def next_unsaved():
        """The figure to ask about next, front window first."""
        front = [w.windowNumber() for w in AppKit.NSApp.orderedWindows()]

        def place(w):
            n = views[w.uid].window.windowNumber()
            return front.index(n) if n in front else len(front)
        left = [w for w in list(api._windows.values()) if w.confirm_close and w.uid in views and w.uid not in kept]
        return min(left, key=place) if left else None
    if next_unsaved() is None:
        return TERMINATE_NOW
    _state["quitting"] = True

    def finish(ok):
        _state["quitting"] = False
        if ok:
            _state["leaving"] = True
            try:
                AppKit.NSApp.terminate_(None)
            finally:
                _state["leaving"] = False   # (reached only if the quit didn't happen after all)

    def step():
        try:
            w = next_unsaved()
            if w is None:
                finish(True)
                return

            def answered(ok):
                if ok and w.confirm_close:
                    kept.add(w.uid)   # (Don't Save: not asked again; a saved one is if edited again)
                if ok:
                    AppHelper.callAfter(step)
                else:
                    AppHelper.callAfter(finish, False)
            ask_about(api, w, answered)
        except Exception as exc:   # noqa: BLE001 (the quit stops rather than half happening)
            print(f"Asking about an unsaved figure before quitting failed: {exc!r}", file=sys.stderr, flush=True)
            finish(False)
    AppHelper.callAfter(step)
    return TERMINATE_CANCEL


def install(api, on_quit=None) -> None:
    """Quitting asks about each unsaved figure (before webview.start). `on_quit` is called once
    mosaic is really quitting: AppKit ends the app there and then, so nothing after
    webview.start() runs (a downloaded update is started from here)."""
    from webview.platforms.cocoa import BrowserView
    delegate = BrowserView.AppDelegate
    if "pywebview" not in _state:
        _state["pywebview"] = delegate.applicationShouldTerminate_
    _state["api"] = api
    _state["on_quit"] = on_quit

    def applicationShouldTerminate_(self, app):
        try:
            reply = should_quit(_state["api"])
            if reply == TERMINATE_NOW and _state.get("on_quit"):
                try:
                    _state["on_quit"]()
                except Exception as exc:   # noqa: BLE001 (quitting goes on)
                    print(f"Leaving mosaic: {exc!r}", file=sys.stderr, flush=True)
            return reply
        except Exception as exc:   # noqa: BLE001 (pywebview's own question asks instead)
            print(f"Asking about unsaved figures before quitting failed: {exc!r}", file=sys.stderr, flush=True)
            _state["quitting"] = False
            return _state["pywebview"](self, app)
    delegate.applicationShouldTerminate_ = applicationShouldTerminate_


def smoke(api, window, scratch: str) -> dict:
    """The smoke test's check of closing and quitting with unsaved changes, in windows of its own
    (hidden, though a sheet shows its window): the question, Cancel, Save, Don't Save keeping a
    copy, and a quit asking about each figure in turn, which a Cancel stops. The first window
    is left with nothing unsaved. {"passed", "total", "failed": [names]}."""
    import time

    import AppKit
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    from .. import docfile, model
    from ..fonts import config_dir
    from .keycheck import on_main

    def wait(cond, seconds=10.0):
        for _ in range(int(seconds * 10)):
            try:
                if cond():
                    return True
            except Exception:   # noqa: BLE001 (a window still opening or closing)
                pass
            time.sleep(0.1)
        return False

    def js(w, code):
        return w.evaluate_js(code)

    def open_window(path):
        before = set(api._windows.values())
        api._new_window(path, None)
        wait(lambda: len(api._windows) > len(before))
        w = next(w for w in list(api._windows.values()) if w not in before)
        wait(lambda: js(w, "document.body.classList.contains('ready') && !!window.FA.app.info"))
        return w

    def edit(w):
        pages = js(w, "window.FA.store.doc.pages.length")
        js(w, "window.FA.app.run('addPage')")
        return wait(lambda: w.confirm_close and js(w, "window.FA.store.doc.pages.length") == pages + 1)

    def window_of(w):
        return BrowserView.instances[w.uid].window

    def sheet(w):
        """The question showing on a window, if one is"""
        return _state["alerts"].get(w.uid) if on_main(lambda: window_of(w).attachedSheet() is not None) else None

    def press(w, title):
        alert = _state["alerts"].get(w.uid)
        if alert is not None:
            on_main(lambda: next(b for b in alert.buttons() if b.title() == title).performClick_(None))

    def pages_in(path):
        return len(docfile.load(path)["pages"])

    def gone(w):
        return wait(lambda: w not in api._windows.values())

    def copy_of(w):
        return os.path.join(config_dir(), "autosave", f"{js(w, 'window.FA.store.autosaveKey')}{docfile.EXTENSION}")

    results, copies = {}, []
    figs = {}
    for name in ("Close A", "Quit A", "Quit B"):
        figs[name] = os.path.join(scratch, f"{name}.mosaic")
        docfile.save(model.new_document(name), figs[name])
    # Nothing unsaved in the first window, so quitting asks only about this check's figures
    js(window, "window.FA.store.markSaved(window.FA.store.path), true")
    wait(lambda: not window.confirm_close)

    # Closing: the question, then Cancel and Save
    a = open_window(figs["Close A"])
    edit(a)
    on_main(lambda: window_of(a).performClose_(None))
    asked = wait(lambda: sheet(a) is not None) and sheet(a)
    buttons = [(b.title(), b.keyEquivalent(), int(b.keyEquivalentModifierMask())) for b in asked.buttons()] if asked else []
    default = bool(asked) and on_main(lambda: asked.window().defaultButtonCell() == asked.buttons()[0].cell())
    cmd = int(AppKit.NSEventModifierFlagCommand)
    results["closing a window with unsaved changes asks in a sheet on it, naming its figure"] = bool(asked) and (
        asked.messageText() == "Do you want to save the changes made to “Close A”?"
        and "keeps a copy" in asked.informativeText())
    results["with Save (Return), Cancel (Escape) and Don’t Save (⌘D)"] = len(buttons) == 3 and (
        buttons[0][0] == "Save" and default and buttons[1][:2] == ("Cancel", "\x1b")   # (Return: the default button)
        and buttons[2][:2] == ("Don’t Save", "d") and buttons[2][2] & cmd == cmd)
    press(a, "Cancel")
    results["Cancel leaves it open, still unsaved"] = wait(lambda: sheet(a) is None) and a in api._windows.values() and (
        a.confirm_close and js(a, "window.FA.store.dirty"))
    on_main(lambda: window_of(a).performClose_(None))
    wait(lambda: sheet(a) is not None)
    press(a, "Save")
    results["Save saves it, then it closes"] = gone(a) and pages_in(figs["Close A"]) == 2

    # A figure never saved: Save… (the Save dialog would ask where); Don't Save keeps a copy
    n = open_window(None)
    edit(n)
    edit(n)
    copies.append(copy_of(n))
    on_main(lambda: window_of(n).performClose_(None))
    asked = wait(lambda: sheet(n) is not None) and sheet(n)
    results["a figure never saved offers Save… (it asks where)"] = bool(asked) and asked.buttons()[0].title() == "Save…" and (
        "“Untitled figure”" in asked.messageText())
    press(n, "Don’t Save")
    results["Don’t Save closes it, keeping a copy with every change, offered back next time"] = gone(n) and (
        os.path.exists(copies[-1]) and pages_in(copies[-1]) == 3)

    # Quitting: each unsaved figure asks in turn, its first answer given and the second cancelled
    qa, qb = open_window(figs["Quit A"]), open_window(figs["Quit B"])
    path_of = {qa.uid: figs["Quit A"], qb.uid: figs["Quit B"]}
    edit(qa)
    edit(qb)

    def quit_asking(answer):
        """(the figure that asked first, the second, whether they asked one at a time)"""
        AppHelper.callAfter(AppKit.NSApp.terminate_, None)
        wait(lambda: sheet(qa) is not None or sheet(qb) is not None)
        first, second = (qa, qb) if sheet(qa) is not None else (qb, qa)
        alone = sheet(second) is None
        AppHelper.callAfter(AppKit.NSApp.terminate_, None)   # quitting again meanwhile: nothing changes
        time.sleep(0.5)
        again = "quitting again while it asks changes nothing"
        results[again] = results.get(again, True) and sheet(first) is not None and sheet(second) is None
        press(first, answer)
        wait(lambda: sheet(second) is not None)
        alone = alone and sheet(first) is None
        press(second, "Cancel")
        wait(lambda: not _state["quitting"])
        return first, second, alone
    first, second, alone = quit_asking("Save")
    open_both = qa in api._windows.values() and qb in api._windows.values()
    results["quitting asks about each unsaved figure in turn"] = alone and open_both
    results["Save saves that one and the next asks; Cancel there stops the quit"] = open_both and not _state["quitting"] and (
        not first.confirm_close and pages_in(path_of[first.uid]) == 2
        and second.confirm_close and js(second, "window.FA.store.dirty"))
    edit(first)
    first, second, alone = quit_asking("Don’t Save")
    copies.append(copy_of(first))
    results["Don’t Save then Cancel at the next leaves the first open, still asking, its copy kept"] = alone and (
        first in api._windows.values() and first.confirm_close and os.path.exists(copies[-1]))
    for w in (qa, qb):
        w.destroy()
    wait(lambda: qa not in api._windows.values() and qb not in api._windows.values())
    api.delete_autosaves(copies)   # (the check's own copies, let go of as their windows closed)
    return {"passed": sum(results.values()), "total": len(results), "failed": [k for k, v in results.items() if not v]}

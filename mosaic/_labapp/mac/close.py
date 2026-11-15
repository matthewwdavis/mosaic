"""The Mac's close question (closing.py has what its answers do): a sheet on the document's
window, with Save (Return), Cancel (Escape) and Don't Save (⌘D).

Quitting asks about each unsaved document in turn, its window brought to the front, through
pywebview's application delegate (whose own question is an alert per window, nameless, with
no Save). The app quits once each is saved or answered Don't Save, and stays open at a Cancel or
a save that didn't happen.

The api needs: _windows ({number: pywebview window}) and hidden_windows (true in a smoke test).
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
    """The app is quitting: with nothing unsaved, now. Else not yet: each unsaved document asks in
    turn, front window first, and once each is saved or answered Don't Save the app quits itself.
    A Cancel, or a save that doesn't happen, stops it; another quit meanwhile changes nothing.
    (Not NSTerminateLater: while that waits, a second quit ends the app without asking.)"""
    if _state["leaving"]:
        return TERMINATE_NOW   # (every document answered)
    if _state["quitting"]:
        return TERMINATE_CANCEL   # (asking already)
    import AppKit
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    from ..closing import ask as ask_about
    views = BrowserView.instances
    kept: set[str] = set()   # windows answered Don't Save, still unsaved

    def next_unsaved():
        """The document to ask about next, front window first."""
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
            print(f"Asking about an unsaved document before quitting failed: {exc!r}", file=sys.stderr, flush=True)
            finish(False)
    AppHelper.callAfter(step)
    return TERMINATE_CANCEL


def install(api, on_quit=None) -> None:
    """Quitting asks about each unsaved document (before webview.start). `on_quit` is called once
    the app is really quitting: AppKit ends the app there and then, so nothing after
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
                    print(f"Leaving the app: {exc!r}", file=sys.stderr, flush=True)
            return reply
        except Exception as exc:   # noqa: BLE001 (pywebview's own question asks instead)
            print(f"Asking about unsaved documents before quitting failed: {exc!r}", file=sys.stderr, flush=True)
            _state["quitting"] = False
            return _state["pywebview"](self, app)
    delegate.applicationShouldTerminate_ = applicationShouldTerminate_

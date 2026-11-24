"""Documents macOS hands the app to open: double-clicked in the Finder, chosen with Open With, or
dropped on its Dock icon. The app's bundle declares its document type, so macOS sends them here,
not on the command line but as an "open documents" Apple event, at launch and while the app runs.

The app takes that event itself rather than through pywebview's application delegate: it installs
its handler once AppKit has installed its own, as Apple has apps do in
applicationWillFinishLaunching. Events sent before any editor is ready are kept on the app's api
(api._system_open; api._launched says the launch's documents are in); later ones go to the editor
in front (window.<js>.app.openFromSystem, the object named in menu.configure), which opens them
in its window if that's blank, else in new windows.

The api needs: _system_open(paths) -> the ones for the editor in front; _ready_uids(); _launched
(a threading.Event).
"""
from __future__ import annotations

import json
import os
import sys

_state: dict = {}


def _code(s: str) -> int:
    """A four-letter Apple event code as a number."""
    return int.from_bytes(s.encode("ascii"), "big")


def paths_of(event) -> list[str]:
    """The files in an open-documents event (a list of file URLs, or one)."""
    docs = event.paramDescriptorForKeyword_(_code("----"))
    if docs is None:
        return []
    items = [docs.descriptorAtIndex_(i) for i in range(1, docs.numberOfItems() + 1)] if docs.numberOfItems() else [docs]
    out = []
    for d in items:
        url = d.fileURLValue() if d is not None else None
        if url is not None and url.path():
            out.append(str(url.path()))
    return out


def opened(api, paths: list[str]) -> None:
    """Open these documents (on the main thread): through the Api (one open already comes to the
    front; before any editor has started they wait), the rest in the editor in front."""
    rest = api._system_open(paths)
    if not rest:
        return
    from . import menu
    view = menu.front_view(api._ready_uids())
    if view is not None:
        view.evaluateJavaScript_completionHandler_(menu._js(f"app.openFromSystem({json.dumps(rest)})"), None)


def install(api) -> None:
    """Take open-documents events from the start (before webview.start)."""
    import AppKit
    import Foundation
    import objc

    if "class" not in _state:
        class LabappOpener(Foundation.NSObject):
            def willFinishLaunching_(self, note):
                AppKit.NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
                    self, b"openDocuments:withReplyEvent:", _code("aevt"), _code("odoc"))

            def didFinishLaunching_(self, note):
                _state["api"]._launched.set()   # any documents of the launch are in

            @objc.typedSelector(b"v@:@@")
            def openDocuments_withReplyEvent_(self, event, reply):
                paths = paths_of(event)

                def go():
                    try:
                        opened(_state["api"], paths)
                    except Exception as exc:   # noqa: BLE001 (an exception here would end the app)
                        print(f"Opening documents from the Finder failed: {exc!r}", file=sys.stderr, flush=True)
                # (the Finder's events come on the main thread; one sent from another thread, as
                # send_open does, is handled on that thread, and WebKit ends an app built for macOS 26
                # or later that calls a web view from there: so it's handed to the main thread)
                if Foundation.NSThread.isMainThread():
                    go()
                else:
                    from PyObjCTools import AppHelper
                    AppHelper.callAfter(go)
        _state["class"] = LabappOpener
    _state["api"] = api
    opener = _state["class"].alloc().init()
    center = Foundation.NSNotificationCenter.defaultCenter()
    center.addObserver_selector_name_object_(opener, b"willFinishLaunching:", AppKit.NSApplicationWillFinishLaunchingNotification, None)
    center.addObserver_selector_name_object_(opener, b"didFinishLaunching:", AppKit.NSApplicationDidFinishLaunchingNotification, None)
    _state["opener"] = opener
    api._launched.clear()


def send_open(paths: list[str]) -> bool:
    """Send this process an open-documents event, as the Finder does (for the smoke test)."""
    import Foundation
    target = Foundation.NSAppleEventDescriptor.descriptorWithProcessIdentifier_(os.getpid())
    event = Foundation.NSAppleEventDescriptor.appleEventWithEventClass_eventID_targetDescriptor_returnID_transactionID_(
        _code("aevt"), _code("odoc"), target, -1, 0)   # kAutoGenerateReturnID, kAnyTransactionID
    files = Foundation.NSAppleEventDescriptor.listDescriptor()
    for i, p in enumerate(paths, 1):
        files.insertDescriptor_atIndex_(Foundation.NSAppleEventDescriptor.descriptorWithFileURL_(Foundation.NSURL.fileURLWithPath_(p)), i)
    event.setParamDescriptor_forKeyword_(files, _code("----"))
    _reply, error = event.sendEventWithOptions_timeout_error_(1, 5.0, None)   # kAENoReply
    return error is None

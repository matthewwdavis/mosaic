"""Documents macOS hands mosaic to open: double-clicked in the Finder, chosen with Open With,
or dropped on its Dock icon. mosaic.app declares the .mosaic type and takes decks as an
alternative (packaging/macos/make_app.py), so macOS sends them here, not on the command line but
as an "open documents" Apple event, at launch and while the app runs.

mosaic takes that event itself rather than through pywebview's application delegate: it
installs its handler once AppKit has installed its own, as Apple has apps do in
applicationWillFinishLaunching (here from that notification), so it has it before the event of
a launch arrives. Documents that come before the first editor has started wait for it
(Api.launch_documents, which waits for the launch to finish); later ones go to the editor in
front, which opens them in its window if that's blank, else in new windows (main.js).
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
    from . import macmenu
    view = macmenu.front_view(api._ready_uids())
    if view is not None:
        view.evaluateJavaScript_completionHandler_(f"window.FA && window.FA.app.openFromSystem({json.dumps(rest)})", None)


def install(api) -> None:
    """Take open-documents events from the start (before webview.start)."""
    import AppKit
    import Foundation
    import objc

    if "class" not in _state:
        class mosaicOpener(Foundation.NSObject):
            def willFinishLaunching_(self, note):
                AppKit.NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
                    self, b"openDocuments:withReplyEvent:", _code("aevt"), _code("odoc"))

            def didFinishLaunching_(self, note):
                _state["api"]._launched.set()   # any documents of the launch are in

            @objc.typedSelector(b"v@:@@")
            def openDocuments_withReplyEvent_(self, event, reply):
                try:
                    opened(_state["api"], paths_of(event))
                except Exception as exc:   # noqa: BLE001 (an exception here would end the app)
                    print(f"Opening documents from the Finder failed: {exc!r}", file=sys.stderr, flush=True)
        _state["class"] = mosaicOpener
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


def smoke(api, window, scratch: str) -> dict:
    """The smoke test's check of documents and windows, in the hidden app window (left as it
    was found, alone): documents sent as the Finder sends them, File > New, the menus going to
    the window in front, closing a window, a page dragged into another window, and a .mosaic
    dropped on the page.
    {"passed", "total", "failed": [names]}."""
    import time

    from .. import docfile, model
    from . import macmenu
    from .api import _same_file
    from .keycheck import on_main

    def wait(cond, seconds=10.0):
        for _ in range(int(seconds * 10)):
            try:
                if cond():
                    return True
            except Exception:   # noqa: BLE001 (a window still opening)
                pass
            time.sleep(0.1)
        return False

    def js(w, code):
        return w.evaluate_js(code)

    def windows():
        return [w for _, w in sorted(api._windows.items(), key=lambda kv: int(kv[0]))]

    def ready(w):
        return wait(lambda: js(w, "document.body.classList.contains('ready')"))

    def path_of(w):
        p = js(w, "window.FA.store.path || ''")
        return _same_file(p) if p else None

    # Two figures with an object each, and a deck of one slide (no slide picker)
    figs = []
    for name in ("Smoke A", "Smoke B"):
        doc = model.new_document(name)
        doc["pages"][0]["items"].append(model.text_item(name, 72, 72))
        p = os.path.join(scratch, f"{name}.mosaic")
        docfile.save(doc, p)
        figs.append(p)
    deck = os.path.join(scratch, "One slide.pptx")
    from pptx import Presentation
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6]).shapes.add_textbox(914400, 914400, 914400, 457200).text_frame.text = "Slide"
    prs.save(deck)
    a, b = figs
    results = {}
    first = windows()[0]
    js(first, f"window.FA.store.setDoc({json.dumps(model.new_document())}), document.querySelectorAll('dialog[open]').forEach((d) => d.close()), true")
    sent = on_main(lambda: send_open([a]))
    results["a document double-clicked in the Finder opens in the blank window"] = sent and wait(
        lambda: path_of(first) == _same_file(a)) and len(windows()) == 1
    on_main(lambda: send_open([b]))
    results["another, while that window is in use, opens in a window of its own"] = wait(
        lambda: len(windows()) == 2 and ready(windows()[1]) and path_of(windows()[1]) == _same_file(b))
    second = windows()[1] if len(windows()) > 1 else first
    results["the second window doesn't offer back unsaved work (only the first does)"] = not js(
        second, "window.FA.app.info.first_window")
    macmenu.note_front(second.uid)
    on_main(lambda: send_open([a]))
    time.sleep(1.5)
    results["one open already comes to the front instead of opening again"] = len(windows()) == 2 and macmenu._state.get(
        "front") == first.uid
    # File > New, in the window in front: a new window, unless that one is blank
    macmenu.note_front(second.uid)
    on_main(lambda: macmenu.act("new"))
    results["File > New in a window in use opens a new window"] = wait(
        lambda: len(windows()) == 3 and ready(windows()[2]) and path_of(windows()[2]) is None)
    third = windows()[-1]
    macmenu.note_front(third.uid)
    on_main(lambda: macmenu.act("new"))
    time.sleep(1.5)
    results["and in a blank window replaces its figure"] = len(windows()) == 3
    # The menus' commands go to the window in front; the view switches are each window's own
    grid = [bool(js(w, "window.FA.app.prefs.show_grid")) for w in (first, second)]
    macmenu.note_front(second.uid)
    on_main(lambda: macmenu.act("toggleGrid"))
    switched = wait(lambda: bool(js(second, "window.FA.app.prefs.show_grid")) != grid[1])
    results["a menu command goes to the window in front, and its view switch stays its own"] = switched and bool(
        js(first, "window.FA.app.prefs.show_grid")) == grid[0]
    on_main(lambda: macmenu.act("toggleGrid"))   # back as it was
    third.destroy()
    results["closing a window leaves the others open"] = wait(lambda: len(windows()) == 2) and bool(
        js(first, "document.body.classList.contains('ready')"))
    # A page dragged out of the first window's Pages list over the second: the second shows where
    # a copy would go, and letting go puts one there (the point given, as the windows are hidden)
    to = next(k for k, w in api._windows.items() if w is second)
    row = json.loads(js(second, "JSON.stringify(document.querySelector('#pages li[data-index]').getBoundingClientRect())"))
    at = [to, row["left"] + 20, row["top"] + row["height"] * 0.75]   # (its first page's lower half: after it)
    pages_there = js(second, "window.FA.store.doc.pages.length")
    js(first, f"window.FA.app.pageAway(true, {json.dumps(at)}), true")
    results["a page dragged over another window's Pages list shows a line there where it would go"] = wait(
        lambda: js(second, "!!document.querySelector('#pages .slide-drop-line')"))
    js(first, f"window.FA.app.copyPageAway(0, {json.dumps(at)}), true")
    results["and letting go adds a copy there, after its first page; the first window keeps it"] = wait(
        lambda: js(second, "window.FA.store.doc.pages.length") == pages_there + 1
        and js(second, "window.FA.store.doc.pages[1].items[0].text.paragraphs[0].runs[0].t") == "Smoke A"
        and not js(second, "!!document.querySelector('#pages .slide-drop-line')")) and js(
        first, "window.FA.store.doc.pages.length") == 1
    # A deck double-clicked: its one slide in a window of its own (the front one is in use)
    macmenu.note_front(first.uid)
    on_main(lambda: send_open([deck]))
    results["a deck double-clicked opens its slides in a window of its own"] = wait(
        lambda: len(windows()) == 3 and ready(windows()[2]) and js(windows()[2], "window.FA.store.doc.pages.length") == 1
        and js(windows()[2], "window.FA.store.doc.meta.title") == "One slide")
    for w in windows()[1:]:
        w.destroy()
    wait(lambda: len(windows()) == 1)
    # A .mosaic dropped on a page in use: its pages after this one, with what they use
    pages = js(first, "window.FA.store.doc.pages.length")
    js(first, f"window.FA.onNativeDrop({json.dumps({'paths': [b], 'x': 700, 'y': 450})}), true")
    results["a .mosaic dropped on the page adds its pages after this one"] = wait(
        lambda: js(first, "window.FA.store.doc.pages.length") == pages + 1
        and js(first, "window.FA.store.pageIndex") == pages
        and js(first, "window.FA.store.page().items[0].text.paragraphs[0].runs[0].t") == "Smoke B")
    return {"passed": sum(results.values()), "total": len(results), "failed": [k for k, v in results.items() if not v]}

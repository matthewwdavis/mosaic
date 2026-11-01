"""Slides and shapes dragged out of PowerPoint onto the app window, on a Mac.

The web view only takes drags it knows (files, text, pictures), and PowerPoint hands over its
slides as nothing but its own reference to them (powerpoint.py). So the web view, pywebview's
WKWebView subclass, is registered for PowerPoint's types as well, and its drag methods are
wrapped: a drag holding them goes to the editor directly (window.FA.onNativeDrag with where it
is, so the Pages list or the page can show where the slides would go, then onNativeDrop), and
anything else to WebKit as before. A deck file being dragged is also told to the editor as it
moves, since a web page can't see a file's name until it's dropped; its drop then goes the
usual way (pywebview's file paths).

Shapes dragged with their contents (a DrawingML package) wait in Api._dropped for the editor to
take them, as Paste takes copied ones.
"""
from __future__ import annotations

import json
import uuid

from . import clipboard, powerpoint

SLIDES = "com.microsoft.PowerPoint-14.0-Slides-Package"
SHAPES = "com.microsoft.Art--GVML-ClipFormat"
OBJECT_DESCRIPTOR = "com.microsoft.Object-Descriptor"
TYPES = [powerpoint.SLIDE_REF, SLIDES, SHAPES]
COPY = 1   # NSDragOperationCopy


def kind_of(types) -> str | None:
    """What a drag holding these pasteboard types brings from PowerPoint, if anything."""
    types = {str(t) for t in types or []}
    if powerpoint.SLIDE_REF in types:
        return "slide-refs"
    if SLIDES in types:
        return "slides"
    if SHAPES in types:
        return "shapes"
    return None


def drop_payload(pb, api) -> dict:
    """What dropping a PowerPoint drag means, for the editor: {"pptSlides": [refs]} for slides
    (powerpoint.slide_refs), or {"dropped": token} for slides or shapes with their contents."""
    kind = kind_of(pb.types())
    if kind == "slide-refs":
        archives = []
        for item in pb.pasteboardItems() or []:
            data = item.dataForType_(powerpoint.SLIDE_REF)
            if data is not None:
                archives.append(bytes(data))
        return {"pptSlides": powerpoint.slide_refs(archives)}
    data = pb.dataForType_(SLIDES if kind == "slides" else SHAPES)
    if data is None:
        return {}
    descriptor = pb.dataForType_(OBJECT_DESCRIPTOR)
    token = uuid.uuid4().hex
    api._dropped[token] = {"kind": kind, "data": bytes(data),
                           "source": clipboard.source_of_copy(bytes(descriptor) if descriptor is not None else None)}
    return {"dropped": token}


def _decks_dragged(pb) -> bool:
    import AppKit
    urls = pb.readObjectsForClasses_options_([AppKit.NSURL], {AppKit.NSPasteboardURLReadingFileURLsOnlyKey: True}) or []
    return any(str(u.path() or "").lower().endswith(powerpoint.DECK_EXTENSIONS) for u in urls)


def install(window, api) -> None:
    """Wrap the web view's drag methods (once) and register it for PowerPoint's types. Call on
    the main thread once the window exists."""
    import objc
    from webview.platforms.cocoa import BrowserView

    host = BrowserView.WebKitHost
    view = BrowserView.instances[window.uid].webview
    view.registerForDraggedTypes_([str(t) for t in (view.registeredDraggedTypes() or [])] + TYPES)
    if getattr(host, "_figassemble_drags", False):
        return
    perform = host.performDragOperation_.callable   # pywebview's: notes dropped files' paths
    sessions: dict = {}   # drag number -> "deck" while a deck file is dragged (looked at once)

    def tell(self, name, value) -> None:
        self.evaluateJavaScript_completionHandler_(f"window.FA && window.FA.{name}({json.dumps(value)})", None)

    def where(self, sender) -> dict:
        p = self.convertPoint_fromView_(sender.draggingLocation(), None)
        return {"x": float(p.x), "y": float(p.y if self.isFlipped() else self.bounds().size.height - p.y)}

    def ppt(sender) -> str | None:
        return kind_of(sender.draggingPasteboard().types()) if sender.draggingSource() is None else None

    def moved(self, sender, entered):
        kind = ppt(sender)
        if kind:
            tell(self, "onNativeDrag", {"kind": "slides" if kind != "shapes" else "shapes", **where(self, sender)})
            return COPY
        n = sender.draggingSequenceNumber()
        if n not in sessions:
            sessions.clear()
            sessions[n] = "deck" if sender.draggingSource() is None and _decks_dragged(sender.draggingPasteboard()) else None
        if sessions[n]:
            tell(self, "onNativeDrag", {"kind": "deck", **where(self, sender)})
        sup = objc.super(host, self)
        return sup.draggingEntered_(sender) if entered else sup.draggingUpdated_(sender)

    def draggingEntered_(self, sender):
        return moved(self, sender, True)

    def draggingUpdated_(self, sender):
        return moved(self, sender, False)

    def draggingExited_(self, sender):
        tell(self, "onNativeDrag", None)
        if not ppt(sender):
            objc.super(host, self).draggingExited_(sender)

    def prepareForDragOperation_(self, sender):
        return True if ppt(sender) else objc.super(host, self).prepareForDragOperation_(sender)

    def performDragOperation_(self, sender):
        tell(self, "onNativeDrag", None)
        if not ppt(sender):
            return perform(self, sender)
        payload = drop_payload(sender.draggingPasteboard(), api)
        if not payload:
            return False
        tell(self, "onNativeDrop", {**payload, **where(self, sender)})
        return True

    def concludeDragOperation_(self, sender):
        if not ppt(sender):
            objc.super(host, self).concludeDragOperation_(sender)

    objc.classAddMethods(host, [
        objc.selector(draggingEntered_, selector=b"draggingEntered:", signature=b"Q@:@"),
        objc.selector(draggingUpdated_, selector=b"draggingUpdated:", signature=b"Q@:@"),
        objc.selector(draggingExited_, selector=b"draggingExited:", signature=b"v@:@"),
        objc.selector(prepareForDragOperation_, selector=b"prepareForDragOperation:", signature=b"Z@:@"),
        objc.selector(performDragOperation_, selector=b"performDragOperation:", signature=b"Z@:@"),
        objc.selector(concludeDragOperation_, selector=b"concludeDragOperation:", signature=b"v@:@"),
    ])
    host._figassemble_drags = True


def fake_drag(types_data: dict, x: float, y: float):
    """A drag from another app holding these types (name -> bytes, or a list of bytes for one
    pasteboard item each) at a point in the window, for the smoke test."""
    import AppKit
    import Foundation

    pb = AppKit.NSPasteboard.pasteboardWithUniqueName()
    pb.clearContents()
    items = []
    for t, data in types_data.items():
        for i, d in enumerate(data if isinstance(data, list) else [data]):
            while len(items) <= i:
                items.append(AppKit.NSPasteboardItem.alloc().init())
            items[i].setData_forType_(Foundation.NSData.dataWithBytes_length_(d, len(d)), t)
    pb.writeObjects_(items)
    global _FakeDrag
    if _FakeDrag is None:
        class FigAssembleFakeDrag(Foundation.NSObject):
            def draggingPasteboard(self):
                return self._pb

            def draggingSource(self):
                return None

            def draggingLocation(self):
                return self._at

            def draggingSourceOperationMask(self):
                return COPY

            def draggingSequenceNumber(self):
                return self._n
        _FakeDrag = FigAssembleFakeDrag
    d = _FakeDrag.alloc().init()
    d._pb, d._at, d._n = pb, Foundation.NSMakePoint(x, y), id(pb)
    return d


_FakeDrag = None


def smoke(window, data_dir: str) -> dict:
    """The smoke test's check, in the app window: drags from PowerPoint, faked (a hidden window
    can't be dragged onto) and handed to the web view's wrapped drag methods as AppKit would.
    `data_dir`: tests/data/powerpoint. {"passed", "total", "failed": [names]}."""
    import os
    import time

    import Foundation
    from webview.platforms.cocoa import BrowserView

    from .keycheck import on_main
    view = BrowserView.instances[window.uid].webview
    deck = os.path.join(data_dir, "example_deck.pptx")
    with open(os.path.join(data_dir, "copied_rect.gvml"), "rb") as fh:
        shapes = fh.read()
    js = window.evaluate_js
    js("""(() => { const app = window.FA.app; app.autoConfirm = true; app.testDecks = %s;
      for (const d of document.querySelectorAll("dialog[open]")) d.close(); app.newDocument(); return true; })()""" % json.dumps([deck]))
    time.sleep(1)
    results: dict[str, bool] = {}

    def at(expr: str):
        """A point in the window (AppKit's coordinates) from CSS pixels the page works out."""
        x, y = json.loads(js(f"JSON.stringify({expr})"))
        return on_main(lambda: view.convertPoint_toView_(Foundation.NSMakePoint(x, y if view.isFlipped() else view.bounds().size.height - y), None))

    def wait(cond: str, seconds: float = 20) -> bool:
        for _ in range(int(seconds * 10)):
            if js(f"!!({cond})"):
                return True
            time.sleep(0.1)
        return False

    page = """(() => { const r = window.FA.canvas.stage.getBoundingClientRect(), [x, y] = window.FA.canvas.toScreen(100, 150);
      return [x + r.left, y + r.top]; })()"""
    p = at(page)
    slides = fake_drag({powerpoint.SLIDE_REF: [powerpoint.slide_ref_archive(258)]}, p.x, p.y)
    entered = on_main(lambda: view.draggingEntered_(slides))
    on_main(lambda: view.draggingUpdated_(slides))
    results["a slide dragged out of PowerPoint is taken, and the page shows it would go there"] = entered == COPY and wait(
        "document.body.classList.contains('dropping') && document.querySelector('.drop-hint').textContent.includes('slides')", 5)
    ok = on_main(lambda: view.performDragOperation_(slides))
    results["dropped, its saved slide's objects come in at the drop point"] = bool(ok) and wait(
        "window.FA.store.items().length === 3 && !document.body.classList.contains('dropping')")
    js("""(() => { for (const d of document.querySelectorAll("dialog[open]")) d.close(); return true; })()""")
    row = at("""(() => { const r = document.querySelectorAll(".page-list li[data-index]")[0].getBoundingClientRect();
      return [r.left + 20, r.top + 3]; })()""")
    over = fake_drag({powerpoint.SLIDE_REF: [powerpoint.slide_ref_archive(258)]}, row.x, row.y)
    on_main(lambda: view.draggingEntered_(over))
    line = wait("document.querySelector('.page-list .slide-drop-line')", 5)
    on_main(lambda: view.draggingExited_(over))
    results["over the Pages list a line shows where it would go, gone when the drag leaves"] = line and wait(
        "!document.querySelector('.slide-drop-line')", 5)
    dropped = fake_drag({SHAPES: shapes}, p.x, p.y)
    ok = on_main(lambda: view.performDragOperation_(dropped))
    results["shapes dragged with their contents come in as editable shapes"] = bool(ok) and wait(
        "window.FA.store.items().length === 4 && window.FA.store.items()[3].geom === 'roundRect'")
    js("""(() => { delete window.FA.app.testDecks; window.FA.app.autoConfirm = false;
      for (const d of document.querySelectorAll("dialog[open]")) d.close(); return true; })()""")
    return {"passed": sum(results.values()), "total": len(results), "failed": [k for k, v in results.items() if not v]}

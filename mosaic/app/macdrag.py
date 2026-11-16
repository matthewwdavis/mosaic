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

Slide thumbnails dragged out of PowerPoint for Mac (16.114) never reach the web view, though:
PowerPoint lets only its own windows take them, so macOS sends other apps no drag calls at all
(a logging test window got none in November 2026). SlideWatch follows those drags itself.
"""
from __future__ import annotations

import json
import sys
import uuid

from .. import docfile
from . import clipboard, powerpoint

SLIDES = "com.microsoft.PowerPoint-14.0-Slides-Package"
SHAPES = "com.microsoft.Art--GVML-ClipFormat"
OBJECT_DESCRIPTOR = "com.microsoft.Object-Descriptor"
TYPES = [powerpoint.SLIDE_REF, SLIDES, SHAPES]
COPY = 1   # NSDragOperationCopy
TOP_LAYER = 100   # window layers from here up (pop-up menus, the drag image, the cursor) don't cover a drop


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


def _decks_dragged(pb) -> str | None:
    """"deck" while a deck file is dragged, "figure" for a mosaic document (both add pages),
    else None."""
    import AppKit
    urls = pb.readObjectsForClasses_options_([AppKit.NSURL], {AppKit.NSPasteboardURLReadingFileURLsOnlyKey: True}) or []
    paths = [str(u.path() or "").lower() for u in urls]
    if any(p.endswith(powerpoint.DECK_EXTENSIONS) for p in paths):
        return "deck"
    return "figure" if any(docfile.has_extension(p) for p in paths) else None


def tell(view, name: str, value) -> None:
    """Call window.FA[name](value) in the editor."""
    view.evaluateJavaScript_completionHandler_(f"window.FA && window.FA.{name}({json.dumps(value)})", None)


def front_window(windows, x: float, y: float):
    """The number of the frontmost window at a point (global display coordinates, y down), from
    CGWindowListCopyWindowInfo's list of windows on screen, front to back. Pop-up menus, the drag
    image and the cursor (TOP_LAYER and up) and invisible windows are looked through."""
    for w in windows:
        if not 0 <= w.get("kCGWindowLayer", 0) < TOP_LAYER or w.get("kCGWindowAlpha", 1) == 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        if b.get("X", 0) <= x < b.get("X", 0) + b.get("Width", 0) and b.get("Y", 0) <= y < b.get("Y", 0) + b.get("Height", 0):
            return w.get("kCGWindowNumber")
    return None


def page_target(views: dict, at=None):
    """For a page dragged out of one window's Pages list: the other window (of `views`, its number
    -> its web view) under the pointer with nothing covering it, and where the pointer is in it
    (CSS px): (number, x, y), or None. `at`: the smoke test's [number, x, y] instead, its windows
    being hidden. On the main thread."""
    if at:
        return tuple(at) if at[0] in views else None
    sense = Sense()
    for win, view in views.items():
        p = sense.where(view)
        if p is not None:
            return win, p[0], p[1]
    return None


class Sense:
    """What SlideWatch looks at: the drag pasteboard, the mouse and the windows on screen (none
    of which needs a permission). The smoke test hands it a fake."""

    def __init__(self):
        import AppKit
        self.pb = AppKit.NSPasteboard.pasteboardWithName_(AppKit.NSPasteboardNameDrag)

    def count(self) -> int:
        return int(self.pb.changeCount())

    def types(self) -> list[str]:
        return [str(t) for t in self.pb.types() or []]

    def archives(self) -> list[bytes]:
        found = [item.dataForType_(powerpoint.SLIDE_REF) for item in self.pb.pasteboardItems() or []]
        return [bytes(d) for d in found if d is not None]

    def button(self) -> bool:
        import AppKit
        return bool(AppKit.NSEvent.pressedMouseButtons() & 1)

    def where(self, view):
        """The pointer in the web view (CSS pixels) if it's over it with nothing covering it, else None."""
        import AppKit
        import Quartz
        win = view.window()
        if win is None:
            return None
        cg = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID) or []
        if front_window(windows, cg.x, cg.y) != win.windowNumber():
            return None
        p = view.convertPoint_fromView_(win.convertPointFromScreen_(AppKit.NSEvent.mouseLocation()), None)
        b = view.bounds()
        if not AppKit.NSPointInRect(p, b):
            return None
        return float(p.x), float(p.y if view.isFlipped() else b.size.height - p.y)


class SlideWatch:
    """Slides dragged out of PowerPoint, which macOS doesn't offer to the web view (see the top).
    From a mouse-down in another app until the button comes up, the drag pasteboard is looked at;
    once a drag has put PowerPoint's reference to slides there, the pointer is followed, the
    editor showing where the slides would go while it's over the window with nothing covering
    it, and letting go there counts as a drop. PowerPoint still shows the slides flying back, as
    for any drag it thinks was refused. A drag AppKit does hand the web view (`appkit`, its
    pasteboard's change count) is left to the usual drop."""

    TICK = 0.03   # seconds

    def __init__(self, view, sense=None, views=None):
        self.view = view
        # Every window's web view (mosaic can have several): the drag goes to the frontmost
        # one under the pointer
        self.views = views or (lambda: [view])
        self.sense = sense or Sense()
        self.seen = self.sense.count()   # the drag pasteboard as last looked at
        self.following = None   # {"count", "at", "view"} while following a slide drag
        self.appkit = None
        self.timer = None

    def start(self) -> None:
        """A mouse-down in another app: look until the button comes up."""
        if self.timer is not None:
            return
        import Foundation
        self.timer = Foundation.NSTimer.timerWithTimeInterval_repeats_block_(self.TICK, True, lambda timer: self.tick())
        Foundation.NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer, Foundation.NSRunLoopCommonModes)

    def stop(self) -> None:
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None

    def tick(self) -> None:
        try:
            self._tick()
        except Exception as exc:   # noqa: BLE001 (an exception here would end the app)
            print(f"Following a drag from PowerPoint failed: {exc!r}", file=sys.stderr, flush=True)
            self.following = None
            self.stop()

    def _tick(self) -> None:
        s, down = self.sense, self.sense.button()
        if self.following is None:
            n = s.count()
            if n != self.seen:
                self.seen = n
                if powerpoint.SLIDE_REF in s.types():
                    self.following = {"count": n, "at": None, "view": None}
            if self.following is None:
                if not down:
                    self.stop()
                return
        f = self.following
        mine = f["count"] != self.appkit
        if down:
            view, at = self.under_pointer() if mine else (f["view"], f["at"])
            if view is not f["view"] and f["view"] is not None and f["at"] is not None:
                tell(f["view"], "onNativeDrag", None)   # moved off that window
            if (view, at) != (f["view"], f["at"]):
                f["view"], f["at"] = view, at
                if view is not None:
                    tell(view, "onNativeDrag", {"kind": "slides", "x": at[0], "y": at[1]} if at else None)
            return
        self.following = None
        self.stop()
        if not mine or f["at"] is None:
            return
        tell(f["view"], "onNativeDrag", None)
        refs = powerpoint.slide_refs(s.archives())
        if refs:
            tell(f["view"], "onNativeDrop", {"pptSlides": refs, "x": f["at"][0], "y": f["at"][1]})

    def under_pointer(self):
        """The web view the pointer is over with nothing covering it, and where: (view, (x, y)),
        or (None, None)."""
        for view in self.views():
            at = self.sense.where(view)
            if at:
                return view, at
        return None, None


_watch: SlideWatch | None = None
_monitor = None


def install(window, api) -> None:
    """Wrap the web view's drag methods (once), register it for PowerPoint's types, and start
    watching for slide thumbnails dragged out of PowerPoint. Call on the main thread once the
    window exists."""
    global _watch, _monitor
    import AppKit
    import objc
    from webview.platforms.cocoa import BrowserView

    host = BrowserView.WebKitHost
    view = BrowserView.instances[window.uid].webview
    view.registerForDraggedTypes_([str(t) for t in (view.registeredDraggedTypes() or [])] + TYPES)
    if _watch is None:
        # Slide thumbnails dragged out of PowerPoint, which never reach the methods below (one
        # watch for every window's web view)
        def views():
            return [i.webview for i in list(BrowserView.instances.values()) if i.webview is not None]
        _watch = SlideWatch(view, views=views)
        if _monitor is None:
            _monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                AppKit.NSEventMaskLeftMouseDown, lambda event: _watch.start())
    if getattr(host, "_mosaic_drags", False):
        return
    perform = host.performDragOperation_.callable   # pywebview's: notes dropped files' paths
    sessions: dict = {}   # drag number -> "deck" or "figure" while one is dragged (looked at once)

    def where(self, sender) -> dict:
        p = self.convertPoint_fromView_(sender.draggingLocation(), None)
        return {"x": float(p.x), "y": float(p.y if self.isFlipped() else self.bounds().size.height - p.y)}

    def ppt(sender) -> str | None:
        return kind_of(sender.draggingPasteboard().types()) if sender.draggingSource() is None else None

    def moved(self, sender, entered):
        kind = ppt(sender)
        if kind:
            if kind == "slide-refs":
                _watch.appkit = int(sender.draggingPasteboard().changeCount())   # (so it isn't dropped twice)
            tell(self, "onNativeDrag", {"kind": "slides" if kind != "shapes" else "shapes", **where(self, sender)})
            return COPY
        n = sender.draggingSequenceNumber()
        if n not in sessions:
            sessions.clear()
            sessions[n] = _decks_dragged(sender.draggingPasteboard()) if sender.draggingSource() is None else None
        if sessions[n]:
            tell(self, "onNativeDrag", {"kind": sessions[n], **where(self, sender)})
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
    host._mosaic_drags = True


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
        class mosaicFakeDrag(Foundation.NSObject):
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
        _FakeDrag = mosaicFakeDrag
    d = _FakeDrag.alloc().init()
    d._pb, d._at, d._n = pb, Foundation.NSMakePoint(x, y), id(pb)
    return d


_FakeDrag = None


def smoke(window, data_dir: str) -> dict:
    """The smoke test's check, in the app window: drags from PowerPoint, faked (a hidden window
    can't be dragged onto) and handed to the web view's wrapped drag methods as AppKit would, or
    to a SlideWatch as it would see them.
    `data_dir`: tests/data/powerpoint. {"passed", "total", "failed": [names]}."""
    import os
    import time

    import Foundation
    from webview.platforms.cocoa import BrowserView

    from .. import model
    from .keycheck import on_main
    view = BrowserView.instances[window.uid].webview
    deck = os.path.join(data_dir, "example_deck.pptx")
    with open(os.path.join(data_dir, "copied_rect.gvml"), "rb") as fh:
        shapes = fh.read()
    js = window.evaluate_js
    # A blank figure in this window (New would open another window, this one being in use)
    blank = f"window.FA.store.setDoc({json.dumps(model.new_document())}); window.FA.canvas.fit();"
    js("""(() => { const app = window.FA.app; app.autoConfirm = true; app.testDecks = %s;
      for (const d of document.querySelectorAll("dialog[open]")) d.close(); %s return true; })()""" % (json.dumps([deck]), blank))
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
    shown = "document.body.classList.contains('dropping') && document.querySelector('.drop-hint').textContent.includes('blank page')"
    became = "window.FA.store.items().length === 3 && window.FA.store.page().width === 960 && !document.body.classList.contains('dropping')"
    results["a slide dragged out of PowerPoint is taken, and the page shows it would go there"] = entered == COPY and wait(shown, 5)
    ok = on_main(lambda: view.performDragOperation_(slides))
    results["dropped on a blank page, the page becomes its saved slide, at the slide's size"] = bool(ok) and wait(became)
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

    # Slide thumbnails as PowerPoint really drags them (macOS hands the web view nothing):
    # SlideWatch following the drag, with a scripted drag pasteboard, mouse button and pointer
    class Scripted:
        n, kinds, down, spot = 0, [], False, None

        def count(self):
            return self.n

        def types(self):
            return self.kinds

        def archives(self):
            return [powerpoint.slide_ref_archive(258)]

        def button(self):
            return self.down

        def where(self, view):
            return self.spot

    fake = Scripted()
    watch = SlideWatch(view, fake)
    js("""(() => { for (const d of document.querySelectorAll("dialog[open]")) d.close(); %s return true; })()""" % blank)
    time.sleep(1)
    spot = tuple(json.loads(js(f"JSON.stringify({page})")))
    fake.n, fake.kinds, fake.down, fake.spot = 1, [powerpoint.SLIDE_REF], True, spot
    on_main(watch.tick)
    results["a slide thumbnail followed out of PowerPoint shows where it would go"] = wait(shown, 5)
    fake.down = False
    on_main(watch.tick)
    results["let go over the window, the blank page becomes its saved slide"] = wait(became)
    js("""(() => { for (const d of document.querySelectorAll("dialog[open]")) d.close(); return true; })()""")
    fake.n, fake.down, fake.spot = 2, True, None   # let go elsewhere, or where a window covers mosaic's
    on_main(watch.tick)
    fake.down = False
    on_main(watch.tick)
    fake.n, fake.down, fake.spot = 3, True, spot   # handed to the web view by macOS after all
    on_main(watch.tick)
    watch.appkit = 3
    fake.down = False
    on_main(watch.tick)
    time.sleep(1)
    fake.down = False   # a click in another app: the button already up again
    on_main(watch.start)
    started = watch.timer is not None
    time.sleep(0.5)
    results["a mouse-down in another app starts the watch, which stops when the button is up"] = (
        started and watch.timer is None and _monitor is not None and _watch is not None and _watch.view is view)
    real = on_main(lambda: (lambda r: (r.count(), r.types(), r.button(), r.where(view)))(Sense()))
    results["the drag pasteboard, mouse and windows on screen can be read (the hidden window isn't among them)"] = (
        isinstance(real[0], int) and isinstance(real[1], list) and isinstance(real[2], bool) and real[3] is None)
    results["let go anywhere else, or taken the usual way, nothing more comes in"] = (
        js("window.FA.store.items().length") == 3 and watch.following is None and not js("!!document.querySelector('dialog[open]')"))
    js("""(() => { delete window.FA.app.testDecks; window.FA.app.autoConfirm = false; window.FA.onNativeDrag(null);
      for (const d of document.querySelectorAll("dialog[open]")) d.close(); return true; })()""")
    return {"passed": sum(results.values()), "total": len(results), "failed": [k for k, v in results.items() if not v]}

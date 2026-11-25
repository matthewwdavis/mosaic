"""The editor's window stays on the editor (Mac).

WebKit opens a file dropped on a page that hasn't taken the drag, in place of the page. A page
takes a drag in its dragenter or dragover handler, and the first message WebKit's page gets about
a drag brings only dragenter: on 2026-11-24 an SVG dragged in from the Finder and let go about
40 ms after it came over the window (no dragover yet, and the editor took drags only in dragover)
replaced the editor with the bare SVG in the top left, which couldn't be moved, and with the editor
gone nothing could be saved. The editor now takes file drags from dragenter on (main.js), and
here, whatever asks the window to go elsewhere (a drop the page didn't take, a script, a link),
the window stays on the editor: a file is put on the page as if dropped there, a web link opens in
the browser, anything else is refused.

pywebview's navigation delegate (BrowserView.BrowserDelegate) is replaced, before the first
window, by a subclass that decides first and hands the editor's own navigations on to it.
"""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import unquote, urlsplit

_guard = None    # the subclass, made once (an Objective-C class can't be made twice)
_drops: dict = {}   # a web view's id -> (time, point, embed, shift) of its last file drop (macdrag.py)
DROP_SECONDS = 5.0   # a file the window is sent to this soon after a drop is put where it was dropped
stayed: list = []   # what the guard did, [(what, url)], newest last (for the smoke test)
_QuickDrop = None   # the smoke test's drag (a class made once)


def decide(url: str, home: str, main_frame: bool = True, link: bool = False) -> str:
    """What the window does with a navigation to url: "allow" (the editor's own address, about:, a
    frame inside the page), "place" (a file: put on the page, the window staying on the editor),
    "browser" (a web link clicked: opened in the system's browser) or "refuse". home: the editor's
    address."""
    if not main_frame:
        return "allow"
    try:
        u, h = urlsplit(url), urlsplit(home)
        here = (u.scheme.lower(), (u.hostname or "").lower(), u.port)
        editor = (h.scheme.lower(), (h.hostname or "").lower(), h.port)
    except ValueError:   # (a port that isn't a number, and the like)
        return "refuse"
    if here[0] == "about" or here == editor:
        return "allow"
    if here[0] == "file":
        return "place"
    if here[0] in ("http", "https") and link:
        return "browser"
    return "refuse"


def file_path(url: str) -> str:
    """The path of a file: address."""
    return unquote(urlsplit(url).path)


def note_drop(view, point: dict, embed: bool, shift: bool) -> None:
    """A file drop on this web view, where (CSS pixels, {x, y}) and with which keys held, so a file
    the window is then sent to goes where it was dropped (macdrag.py, before WebKit takes the drop)."""
    _drops[id(view)] = (time.monotonic(), point, embed, shift)


def place(view, url: str) -> bool:
    """A file the window was sent to, put on the editor's page as a drop: where the last drop on
    this web view was, if it was just now, else in the middle of the window. Call on the main thread."""
    path = file_path(url)
    if not os.path.isfile(path):
        return False
    t, point, embed, shift = _drops.pop(id(view), (0.0, None, False, False))
    if point is None or time.monotonic() - t > DROP_SECONDS:
        size = view.bounds().size
        point, embed, shift = {"x": size.width / 2, "y": size.height / 2}, False, False
    from .macdrag import tell
    tell(view, "onNativeDrop", {"paths": [path], **point, "embed": embed, "shift": shift})
    return True


def install(home: str) -> None:
    """Before the first window: pywebview's web views get a navigation delegate that keeps them on
    the editor (home: its address). Once."""
    global _guard
    if _guard is not None:
        return
    import objc
    from webview.platforms.cocoa import BrowserView

    parent = BrowserView.BrowserDelegate

    class mosaicNavigationGuard(parent):
        def webView_decidePolicyForNavigationAction_decisionHandler_(self, webview, action, handler):
            url = ""
            try:
                frame = action.targetFrame()   # (none: a new window, which pywebview opens in the browser)
                url = str(action.request().URL().absoluteString() or "")
                what = decide(url, home, frame is not None and bool(frame.isMainFrame()),
                              int(action.navigationType()) == 0)   # (WKNavigationTypeLinkActivated)
            except Exception as exc:   # noqa: BLE001 (pywebview decides, as it did before)
                print(f"Couldn't check where the window was sent ({url}): {exc}", file=sys.stderr, flush=True)
                what = "allow"
            if what == "allow":
                return objc.super(mosaicNavigationGuard, self).webView_decidePolicyForNavigationAction_decisionHandler_(
                    webview, action, handler)
            handler(0)   # (WKNavigationActionPolicyCancel: the editor stays)
            if what == "place":
                placed = place(webview, url)
                what = "placed" if placed else "refused (no such file)"
            elif what == "browser":
                import webbrowser
                webbrowser.open(url)
            stayed.append((what, url))
            print(f"The window stayed on the editor ({what}): {url}", file=sys.stderr, flush=True)

    BrowserView.BrowserDelegate = mosaicNavigationGuard
    _guard = mosaicNavigationGuard


def smoke(api, scratch: str) -> dict:
    """The smoke test's check, in a (hidden) window of its own: a picture let go of the moment it
    comes over the window, as AppKit hands a quick drop to the web view (entered, then performed,
    with nothing between), is put on the page and the window stays on the editor; the window sent
    to a file (as WebKit sends it for a drop the page didn't take) stays on the editor with the file
    put on the page; sent to a web address, it stays and nothing comes in.
    {"passed", "total", "failed": [names]}."""
    import AppKit
    import Foundation
    import objc
    from webview.platforms.cocoa import BrowserView

    from .keycheck import on_main

    global _QuickDrop
    if _QuickDrop is None:
        # What AppKit hands a web view about a drag from the Finder, typed, as WebKit reads it
        # (macdrag.fake_drag's drags never reach WebKit, so its methods aren't typed)
        class mosaicQuickDrop(Foundation.NSObject):
            @objc.typedSelector(b"@@:")
            def draggingPasteboard(self):
                return self._pb

            @objc.typedSelector(b"@@:")
            def draggingSource(self):
                return None

            @objc.typedSelector(b"{CGPoint=dd}@:")
            def draggingLocation(self):
                return self._at

            @objc.typedSelector(b"{CGPoint=dd}@:")
            def draggedImageLocation(self):
                return self._at

            @objc.typedSelector(b"@@:")
            def draggedImage(self):
                return None

            @objc.typedSelector(b"Q@:")
            def draggingSourceOperationMask(self):
                return 1   # (NSDragOperationCopy)

            @objc.typedSelector(b"q@:")
            def draggingSequenceNumber(self):
                return self._n

            @objc.typedSelector(b"@@:")
            def draggingDestinationWindow(self):
                return self._win

            @objc.typedSelector(b"q@:")
            def numberOfValidItemsForDrop(self):
                return 1

            @objc.typedSelector(b"v@:q")
            def setNumberOfValidItemsForDrop_(self, n):
                pass

            @objc.typedSelector(b"q@:")
            def draggingFormation(self):
                return 0

            @objc.typedSelector(b"v@:q")
            def setDraggingFormation_(self, f):
                pass

            @objc.typedSelector(b"Z@:")
            def animatesToDestination(self):
                return False

            @objc.typedSelector(b"v@:Z")
            def setAnimatesToDestination_(self, flag):
                pass

            @objc.typedSelector(b"q@:")
            def springLoadingHighlight(self):
                return 0

            @objc.typedSelector(b"v@:")
            def resetSpringLoading(self):
                pass

            @objc.typedSelector(b"v@:{CGPoint=dd}")
            def slideDraggedImageTo_(self, point):
                pass

            @objc.typedSelector(b"v@:Q@@@@?")
            def enumerateDraggingItemsWithOptions_forView_classes_searchOptions_usingBlock_(self, opts, view, classes, search, block):
                pass   # (no drag images to set)
        _QuickDrop = mosaicQuickDrop

    def quick_drop(path: str, view):
        """A Finder drag of this file over the middle of the web view."""
        pb = AppKit.NSPasteboard.pasteboardWithUniqueName()
        pb.declareTypes_owner_(["NSFilenamesPboardType", "public.file-url"], None)   # (as the Finder gives them)
        pb.setPropertyList_forType_([path], "NSFilenamesPboardType")
        pb.setString_forType_(str(Foundation.NSURL.fileURLWithPath_(path).absoluteString()), "public.file-url")
        d = _QuickDrop.alloc().init()
        b = view.bounds()
        d._pb, d._n, d._win = pb, id(pb), view.window()
        d._at = view.convertPoint_toView_(Foundation.NSMakePoint(b.size.width / 2, b.size.height / 2), None)
        return d

    def wait(cond, seconds=10.0):
        for _ in range(int(seconds * 10)):
            try:
                if cond():
                    return True
            except Exception:   # noqa: BLE001 (a page still loading)
                pass
            time.sleep(0.1)
        return False

    svg = os.path.join(scratch, "dropped.svg")
    with open(svg, "w", encoding="utf-8") as fh:
        fh.write('<svg xmlns="http://www.w3.org/2000/svg" width="72pt" height="36pt" viewBox="0 0 72 36">'
                 '<rect x="4" y="4" width="64" height="28" fill="#3070b0"/></svg>')
    before = set(api._windows.values())
    api._new_window(None, None)
    wait(lambda: len(api._windows) > len(before))
    w = next(w for w in list(api._windows.values()) if w not in before)
    wait(lambda: w.evaluate_js("document.body.classList.contains('ready') && !!window.FA.app.info"), 30)
    view = BrowserView.instances[w.uid].webview
    home = w.evaluate_js("location.origin")

    def items():
        try:
            return w.evaluate_js("window.FA.store.items().length")
        except Exception:   # noqa: BLE001 (the editor gone from the window: what the checks look for)
            return None

    def on_editor():
        """The window still on the editor's page, with the editor running in it."""
        u = on_main(lambda: str(view.URL().absoluteString() or ""))
        return u.startswith(home) and bool(w.evaluate_js("!!(window.FA && window.FA.store)"))

    results: dict[str, bool] = {}
    # A drop straight after coming in: AppKit's draggingEntered, then the drop, nothing between
    url = Foundation.NSURL.fileURLWithPath_(svg)
    drag = on_main(lambda: quick_drop(svg, view))
    n, guarded = items(), len(stayed)
    on_main(lambda: view.draggingEntered_(drag))
    on_main(lambda: view.prepareForDragOperation_(drag))
    on_main(lambda: view.performDragOperation_(drag))
    on_main(lambda: view.concludeDragOperation_(drag))
    time.sleep(1.5)
    results["a picture let go of the moment it comes over the window is put on the page; the window stays on the editor"] = (
        wait(lambda: on_editor() and items() == n + 1, 10))
    results["the page takes that drop itself (the window isn't sent to the file)"] = len(stayed) == guarded
    # Sent to the file, as WebKit sends a window for a drop its page didn't take
    if not on_editor():   # (the first check failed: the editor back, for the rest)
        on_main(lambda: view.goBack_(None))
        wait(on_editor, 15)
    n = items()
    on_main(lambda: view.loadFileURL_allowingReadAccessToURL_(url, url))
    results["sent to a file, the window stays on the editor and the file is put on the page"] = (
        wait(lambda: on_editor() and items() == n + 1, 10) and bool(stayed) and stayed[-1][0] == "placed")
    # Sent to a web address: it stays, nothing comes in (.invalid: no such site, nothing asked of the network)
    n = items()
    web = Foundation.NSURL.URLWithString_("https://example.invalid/")
    on_main(lambda: view.loadRequest_(Foundation.NSURLRequest.requestWithURL_(web)))
    time.sleep(1.0)
    results["sent to a web address, the window stays on the editor and nothing comes in"] = (
        on_editor() and items() == n and bool(stayed) and stayed[-1] == ("refuse", "https://example.invalid/"))
    w.confirm_close = False
    w.destroy()
    return {"passed": sum(results.values()), "total": len(results), "failed": [k for k, v in results.items() if not v]}

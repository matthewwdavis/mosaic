"""Documents macOS hands mosaic to open: double-clicked in the Finder, chosen with Open With,
or dropped on its Dock icon. mosaic.app declares the .mosaic type and takes decks as an
alternative (packaging/macos/make_app.py), so macOS sends them as an "open documents" Apple event,
at launch and while the app runs. Taking that event is the shared library's
(_labapp/mac/finder.py); the smoke test's check of mosaic's documents and windows is here.
"""
from __future__ import annotations

import json
import os

from .._labapp.mac.finder import _code, _state, install, opened, paths_of, send_open   # noqa: F401


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
    from .._labapp.mac import on_main

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

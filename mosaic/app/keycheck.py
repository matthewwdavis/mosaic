"""Real key presses (and ⌘-clicks) in the app window on a Mac, for the smoke test.

The editor self-test fakes key presses inside the page, so it can't tell whether a real key
press gets to the editor through AppKit, WebKit and pywebview (which handles some ⌘ keys itself
and adds an Edit menu with ⌘X, ⌘C, ⌘V and ⌘A). This check builds real NSEvents and hands them
to the hidden window in AppKit's own order for a key press: with ⌘ held, the window's key
equivalents and then the menu bar; otherwise, and for anything they leave, the window's
keyDown. Only the choice of the key window is skipped, since a hidden window never becomes key.

Commands that would open a file dialog are recorded but not run. The system clipboard is put
back afterwards, since copying in the editor writes to it.
"""
from __future__ import annotations

import json
import threading
import time

KEY_CODES = {"a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
             "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
             "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31,
             "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, ",": 43,
             "/": 44, "n": 45, "m": 46, ".": 47}
SHIFTED = {"]": "}", "[": "{", ";": ":", "/": "?", "'": '"', "=": "+", "-": "_", ",": "<", ".": ">", "0": ")"}
ARROW = 0x200000 | 0x800000   # numeric pad + function: what AppKit sets on arrow keys
SPECIAL = {"return": ("\r", 36, 0), "tab": ("\t", 48, 0), "escape": ("\x1b", 53, 0),
           "backspace": ("\x7f", 51, 0), "left": ("", 123, ARROW), "right": ("", 124, ARROW),
           "down": ("", 125, ARROW), "up": ("", 126, ARROW)}

# The editor's commands that open a dialog: recorded, not run
STUBBED = ["new", "open", "save", "saveAs", "insertPicture", "replacePicture", "export", "preflight",
           "preferences"]

SETUP_JS = """(() => {
  const app = window.FA.app;
  if (!app.__keylog) {
    const run = app.run.bind(app), stub = new Set(%s);
    app.__keylog = [];
    app.run = (name) => { app.__keylog.push(name); return stub.has(name) ? Promise.resolve() : run(name); };
    window.__keys = [];
    window.addEventListener("keydown", (e) => window.__keys.push({ key: e.key, prevented: e.defaultPrevented }));
  }
  return true;
})()""" % json.dumps(STUBBED)

STATE_JS = """JSON.stringify((() => {
  const s = window.FA.store, sel = s.selected()[0];
  return { items: s.items().map((it) => it.type), selected: s.selection.length,
    frame: sel && sel.frame ? sel.frame.slice() : null, zoom: window.FA.canvas.zoom, step: window.FA.app.nudgeStep().pt,
    runs: sel && sel.text ? sel.text.paragraphs.flatMap((p) => p.runs.map((r) => [r.size ?? 6, !!r.bold])) : null,
    pages: s.doc.pages.length,
    dialog: !!document.querySelector("dialog[open]"), shapeMenu: !window.FA.panels.shapeMenu.hidden,
    editing: !!window.FA.canvas.editing, field: document.activeElement?.matches("#inspector input") || false,
    ran: window.FA.app.__keylog.slice(), keys: window.__keys.slice() };
})())"""

# A field in the right-hand panel, starting afresh (drawn now: a hidden window never runs
# animation frames)
FIELD_JS = """(() => {
  window.FA.canvas.commitEdit();
  window.FA.store.select([]);
  window.FA.inspector.render();
  const f = document.querySelector("#inspector input[type=number], #inspector input[type=text]");
  if (f) f.focus();
  return !!f;
})()"""


def parse(spec: str):
    """"cmd+shift+g", "shift+/", "return"... -> (characters, key code, modifier flags)."""
    import AppKit
    *mods, name = spec.split("+")
    flags = 0
    for m in mods:
        flags |= {"cmd": AppKit.NSEventModifierFlagCommand, "shift": AppKit.NSEventModifierFlagShift,
                  "alt": AppKit.NSEventModifierFlagOption, "ctrl": AppKit.NSEventModifierFlagControl}[m]
    if name in SPECIAL:
        chars, code, extra = SPECIAL[name]
        return chars, code, flags | extra
    chars = SHIFTED.get(name, name.upper()) if "shift" in mods else name
    return chars, KEY_CODES[name], flags


from .._labapp.mac import on_main   # noqa: E402,F401 (run on the main, AppKit, thread)


def press(win, spec: str) -> None:
    import AppKit
    import Foundation
    chars, code, flags = parse(spec)

    def event(kind):
        return AppKit.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            kind, Foundation.NSMakePoint(0, 0), flags, AppKit.NSProcessInfo.processInfo().systemUptime(),
            win.windowNumber(), None, chars, chars, False, code)

    def deliver():
        down = event(AppKit.NSEventTypeKeyDown)
        handled = False
        if flags & AppKit.NSEventModifierFlagCommand:
            handled = win.performKeyEquivalent_(down) or AppKit.NSApp.mainMenu().performKeyEquivalent_(down)
        if not handled:
            win.sendEvent_(down)
        win.sendEvent_(event(AppKit.NSEventTypeKeyUp))
    on_main(deliver)


def click(win, at, flags: int = 0) -> None:
    """A real left click at a point in the web view (CSS px from its top left, as the page
    measures), handed to the view under it as AppKit hands a click in a window in front (a hidden
    window would take it as a click to bring it to the front)."""
    import AppKit
    import Foundation

    def deliver():
        loc = Foundation.NSMakePoint(at[0], win.contentView().frame().size.height - at[1])   # (from the bottom)
        view = win.contentView().hitTest_(loc)
        for kind, pressure in ((AppKit.NSEventTypeLeftMouseDown, 1.0), (AppKit.NSEventTypeLeftMouseUp, 0.0)):
            event = AppKit.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
                kind, loc, flags, AppKit.NSProcessInfo.processInfo().systemUptime(), win.windowNumber(), None, 0, 1, pressure)
            (view.mouseDown_ if kind == AppKit.NSEventTypeLeftMouseDown else view.mouseUp_)(event)
        return str(view.className())
    return on_main(deliver)


# Two shapes to click at the page's top left, the first selected: where they are in the web view
CLICK_JS = """JSON.stringify((() => {
  const s = window.FA.store, c = window.FA.canvas, shape = (id, x) => ({ id, type: "shape", geom: "rect",
    frame: [x, 12, 40, 30], rot: 0, stroke: null, fill: { color: "#336699", opacity: 1 } });
  c.commitEdit();
  c.fit();
  s.update("Shapes to click", (d) => d.pages[s.pageIndex].items.push(shape("clickA", 12), shape("clickB", 70)), { select: ["clickA"] });
  const r = c.stage.getBoundingClientRect();
  return ["clickA", "clickB"].map((id) => {
    const f = s.item(id).frame, [x, y] = c.toScreen(f[0] + f[2] / 2, f[1] + f[3] / 2);
    return [x + r.left, y + r.top];
  });
})())"""

# A shape hanging half off the page's left edge, not selected: where its part outside the page is
# in the web view
OFF_PAGE_JS = """JSON.stringify((() => {
  const s = window.FA.store, c = window.FA.canvas;
  s.update("Off the page", (d) => d.pages[s.pageIndex].items.push({ id: "offPage", type: "shape", geom: "rect",
    frame: [-40, 60, 60, 30], rot: 0, stroke: null, fill: { color: "#cc79a7", opacity: 1 } }), { select: [] });
  const r = c.stage.getBoundingClientRect(), [x, y] = c.toScreen(-20, 75);
  return [x + r.left, y + r.top];
})())"""


def save_clipboard() -> list:
    import AppKit
    saved = []
    for item in AppKit.NSPasteboard.generalPasteboard().pasteboardItems() or []:
        kinds = {}
        for kind in item.types():
            data = item.dataForType_(kind)
            if data is not None:
                kinds[kind] = data
        saved.append(kinds)
    return saved


def restore_clipboard(saved: list) -> None:
    import AppKit
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    items = []
    for kinds in saved:
        item = AppKit.NSPasteboardItem.alloc().init()
        for kind, data in kinds.items():
            item.setData_forType_(data, kind)
        items.append(item)
    if items:
        pb.writeObjects_(items)


# Each step: the keys pressed and what has to follow. "ran" lists the editor commands the keys
# must run (none if left out); "check" looks at the editor before and after; "what" describes it.
STEPS = [
    ("b", {"ran": ["toolPen"]}), ("v", {"ran": ["toolSelect"]}), ("r", {"ran": ["toolRect"]}),
    ("return", {"check": lambda b, s: s["items"] == ["shape"] and s["selected"] == 1, "what": "Enter places a rectangle"}),
    ("cmd+c", {"ran": ["copy"]}),
    ("cmd+v", {"ran": ["paste"], "check": lambda b, s: len(s["items"]) == 2}),
    ("cmd+a", {"ran": ["selectAll"], "check": lambda b, s: s["selected"] == 2}),
    ("cmd+g", {"ran": ["group"], "check": lambda b, s: s["items"] == ["group"]}),
    ("cmd+shift+g", {"ran": ["ungroup"], "check": lambda b, s: s["items"] == ["shape", "shape"]}),
    ("cmd+z", {"ran": ["undo"], "check": lambda b, s: s["items"] == ["group"]}),
    ("cmd+shift+z", {"ran": ["redo"], "check": lambda b, s: s["items"] == ["shape", "shape"]}),
    ("cmd+a", {"ran": ["selectAll"]}),
    ("cmd+d", {"ran": ["duplicate"], "check": lambda b, s: len(s["items"]) == 4}),
    ("backspace", {"ran": ["delete"], "check": lambda b, s: len(s["items"]) == 2}),
    ("cmd+a", {"ran": ["selectAll"]}),
    ("cmd+x", {"ran": ["cut"], "check": lambda b, s: s["items"] == []}),
    ("cmd+v", {"ran": ["paste"], "check": lambda b, s: len(s["items"]) == 2}),
    ("tab", {"check": lambda b, s: s["selected"] == 1, "what": "Tab selects one object"}),
    # (one step: what the status bar shows, following the zoom)
    ("right", {"check": lambda b, s: moved(b, s, b["step"]), "what": "→ moves it one step"}),
    ("shift+right", {"check": lambda b, s: moved(b, s, 10 * b["step"]), "what": "⇧→ moves it 10 steps"}),
    ("cmd+shift+d", {"ran": ["transformAgain"], "check": lambda b, s: moved(b, s, 10 * b["step"]), "what": "⌘⇧D moves it 10 steps again"}),
    ("cmd+shift+c", {"ran": ["copyStyle"]}), ("cmd+shift+v", {"ran": ["pasteStyle"]}),
    ("cmd+7", {"ran": ["makeClipMask"], "check": lambda b, s: s["items"] == b["items"], "what": "⌘7 asks for a shape on top first"}),
    ("cmd+shift+]", {"ran": ["bringToFront"]}),
    ("cmd+]", {"ran": ["bringForward"]}),
    ("cmd+[", {"ran": ["sendBackward"]}),
    ("cmd+shift+[", {"ran": ["sendToBack"]}),
    ("escape", {"check": lambda b, s: s["selected"] == 0, "what": "Escape deselects"}),
    ("cmd+=", {"ran": ["zoomIn"], "check": lambda b, s: s["zoom"] > b["zoom"]}),
    ("cmd+-", {"ran": ["zoomOut"], "check": lambda b, s: s["zoom"] < b["zoom"]}),
    ("cmd+1", {"ran": ["zoom100"], "check": lambda b, s: abs(s["zoom"] - 1) < 1e-9}),
    ("cmd+0", {"ran": ["zoomFit"]}),
    ("cmd+shift+0", {"ran": ["centrePage"]}),
    ("cmd+r", {"ran": ["toggleRulers"]}), ("cmd+r", {"ran": ["toggleRulers"]}),
    ("cmd+'", {"ran": ["toggleGrid"]}), ("cmd+'", {"ran": ["toggleGrid"]}),
    ("cmd+;", {"ran": ["toggleGuides"]}), ("cmd+;", {"ran": ["toggleGuides"]}),
    ("cmd+shift+;", {"ran": ["toggleSnap"]}), ("cmd+shift+;", {"ran": ["toggleSnap"]}),
    ("v", {"ran": ["toolSelect"]}), ("t", {"ran": ["toolText"]}), ("p", {"ran": ["toolLabel"]}),
    ("l", {"ran": ["toolLine"]}), ("a", {"ran": ["toolArrow"]}), ("u", {"ran": ["toolRoundRect"]}),
    ("o", {"ran": ["toolEllipse"]}), ("f", {"ran": ["toolFill"]}), ("v", {"ran": ["toolSelect"]}),
    ("t", {"ran": ["toolText"]}),
    ("return", {"check": lambda b, s: s["editing"], "what": "Enter starts typing in a new text box"}),
    ("cmd+s", {"ran": ["save"], "check": lambda b, s: not s["editing"], "what": "⌘S while typing saves, text first"}),
    # The Home tab's Text section: bigger and smaller while typing (on the selected words), then bold
    # and bigger on the selected text box
    ("t", {"ran": ["toolText"]}), ("return", {"check": lambda b, s: s["editing"], "what": "Enter starts typing again"}),
    ("h", {"check": lambda b, s: s["editing"], "what": "a letter goes into the text"}),
    ("cmd+a", {"check": lambda b, s: s["editing"], "what": "⌘A while typing selects the text, not the objects"}),
    ("cmd+shift+.", {"ran": ["textBigger"], "check": lambda b, s: s["editing"] and s["runs"] == [[6.5, False]],
                     "what": "⌘⇧> while typing makes the selected text bigger, typing carrying on"}),
    ("cmd+shift+,", {"ran": ["textSmaller"], "check": lambda b, s: s["runs"] == [[6, False]],
                     "what": "⌘⇧< makes it smaller again"}),
    ("escape", {"check": lambda b, s: not s["editing"] and s["selected"] == 1, "what": "Escape ends typing, the box selected"}),
    ("cmd+b", {"ran": ["textBold"], "check": lambda b, s: s["runs"] == [[6, True]],
               "what": "⌘B makes a selected text box bold"}),
    ("cmd+shift+.", {"ran": ["textBigger"], "check": lambda b, s: s["runs"] == [[6.5, True]],
                     "what": "⌘⇧> makes a selected box bigger"}),
    ("backspace", {"ran": ["delete"], "check": lambda b, s: s["selected"] == 0}),
    ("s", {"ran": ["shapesMenu"], "check": lambda b, s: s["shapeMenu"], "what": "S opens the Shapes menu"}),
    ("escape", {"check": lambda b, s: not s["shapeMenu"], "what": "Escape closes the Shapes menu"}),
    ("w", {"ran": ["togglePreview"]}), ("w", {"ran": ["togglePreview"]}),   # (Preview on, and off again)
    ("i", {"ran": ["insertPicture"]}),
    ("cmd+n", {"ran": ["new"]}), ("cmd+o", {"ran": ["open"]}), ("cmd+s", {"ran": ["save"]}),
    ("cmd+shift+s", {"ran": ["saveAs"]}), ("cmd+e", {"ran": ["export"]}),
    ("cmd+shift+e", {"ran": ["preflight"]}), ("cmd+,", {"ran": ["preferences"]}),
    ("cmd+shift+n", {"ran": ["addPage"], "check": lambda b, s: s["pages"] == b["pages"] + 1}),
    ("cmd+z", {"ran": ["undo"], "check": lambda b, s: s["pages"] == b["pages"] - 1}),
    ("cmd+/", {"ran": ["commandSearch"], "check": lambda b, s: s["dialog"], "what": "⌘/ opens command search"}),
    ("escape", {"check": lambda b, s: not s["dialog"], "what": "Escape closes it"}),
    ("shift+/", {"ran": ["shortcuts"], "check": lambda b, s: s["dialog"], "what": "? opens the shortcuts list"}),
    ("escape", {"check": lambda b, s: not s["dialog"], "what": "Escape closes it"}),
]

# In a text field, ⌘A, ⌘C, ⌘V, ⌘Z and plain keys are the field's (macOS edits the text) and
# run nothing in the editor; ⌘S still saves, taking the typing out of the field first
FIELD_STEPS = [("cmd+a", False), ("cmd+c", False), ("cmd+v", False), ("cmd+z", False), ("v", False),
               ("cmd+s", True)]


# ⌘V with things other apps copy, put on the real clipboard: what each must paste as
ITEMS_JS = """JSON.stringify(window.FA.store.items().map((it) => {
  const a = it.asset && window.FA.store.doc.assets[it.asset], v = a && a.variants[a.primary];
  return { id: it.id, type: it.type, frame: it.frame,
    text: it.text ? it.text.paragraphs.map((p) => p.runs.map((r) => (r.bold ? `*${r.t}*` : r.t)).join("")).join("|") : null,
    asset: a ? { primary: a.primary, linked: Object.values(a.variants).some((x) => x.src), dpi: v.dpi || null } : null };
}))"""


def paste_samples(folder: str) -> list[tuple[str, dict, object]]:
    """(what, {pasteboard type: data}, check(new item)) for each kind of paste."""
    import AppKit
    import pikepdf
    from PIL import Image
    import io
    import os

    def rtf():
        s = AppKit.NSMutableAttributedString.alloc().initWithString_("Bold and plain")
        s.addAttribute_value_range_(AppKit.NSFontAttributeName, AppKit.NSFont.fontWithName_size_("Helvetica", 12), (0, 14))
        s.addAttribute_value_range_(AppKit.NSFontAttributeName, AppKit.NSFont.fontWithName_size_("Helvetica-Bold", 12), (0, 4))
        return bytes(s.RTFFromRange_documentAttributes_((0, s.length()), {}))
    pdf = io.BytesIO()
    doc = pikepdf.new()
    doc.add_blank_page(page_size=(100, 50))
    doc.save(pdf)
    path = os.path.join(folder, "copied plot.pdf")
    with open(path, "wb") as f:
        f.write(pdf.getvalue())
    png, tiff = io.BytesIO(), io.BytesIO()
    Image.new("RGB", (40, 20), (10, 120, 200)).save(png, "PNG")
    Image.new("RGB", (40, 20), (10, 120, 200)).save(tiff, "TIFF", dpi=(144, 144))
    return [
        ("text with bold (RTF)", {"public.rtf": on_main(rtf), "public.utf8-plain-text": "Bold and plain"},
         lambda it: it["type"] == "shape" and it["text"] == "*Bold* and plain"),
        ("a vector picture (PDF)", {"com.adobe.pdf": pdf.getvalue()},
         lambda it: it["asset"] and it["asset"]["primary"] == "pdf" and not it["asset"]["linked"]
         and abs(it["frame"][2] - 100) < 0.01),
        ("a file copied in the Finder", {"public.file-url": AppKit.NSURL.fileURLWithPath_(path).absoluteString()},
         lambda it: it["asset"] and it["asset"]["linked"]),
        ("a screenshot (PNG, and a TIFF that records 144 dpi)", {"public.png": png.getvalue(), "public.tiff": tiff.getvalue()},
         lambda it: it["asset"] and it["asset"]["primary"] == "png" and abs(it["frame"][2] - 20) < 0.01),
        ("text with a picture: the text", {"public.utf8-plain-text": "Caption", "com.adobe.pdf": pdf.getvalue()},
         lambda it: it["type"] == "shape" and it["text"] == "Caption"),
    ]


def put_clipboard(kinds: dict) -> None:
    import AppKit
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    item = AppKit.NSPasteboardItem.alloc().init()
    for kind, data in kinds.items():
        if isinstance(data, str):
            item.setString_forType_(data, kind)
        else:
            item.setData_forType_(AppKit.NSData.dataWithBytes_length_(data, len(data)), kind)
    pb.writeObjects_([item])


def moved(before: dict, after: dict, dx: float) -> bool:
    return (before["frame"] is not None and after["frame"] is not None
            and abs(after["frame"][0] - before["frame"][0] - dx) < 1e-6)


def run(window, ns_window) -> dict:
    """Press every step's keys in the editor; returns {"passed", "total", "failed": [...]}."""
    window.evaluate_js(SETUP_JS)
    # A dialog open at the start, such as the offer to recover unsaved work from earlier sessions,
    # is closed as Not now closes it: Return would choose Recover, and this window's edits would
    # then be saved over that work
    window.evaluate_js("document.querySelectorAll('dialog[open]').forEach((d) => d.close()); true")
    state = lambda: json.loads(window.evaluate_js(STATE_JS))
    clipboard = save_clipboard()
    passed, failed = 0, []
    try:
        for keys, want in STEPS:
            before = state()
            press(ns_window, keys)
            for _ in range(40):   # the web view handles key events in its own process: wait a little
                time.sleep(0.05)
                after = state()
                ran = after["ran"][len(before["ran"]):]
                ok = ran == want.get("ran", []) and want.get("check", lambda b, s: True)(before, after)
                if ok:
                    break
            passed += ok
            if not ok:
                failed.append({"keys": keys, "wanted": want.get("what") or want.get("ran"), "ran": ran,
                               "keydown": after["keys"][len(before["keys"]):]})
        # A text field keeps its own editing keys
        if not window.evaluate_js(FIELD_JS):
            failed.append({"keys": "(text field)", "wanted": "a field in the right-hand panel", "ran": [], "keydown": []})
        for keys, saves in FIELD_STEPS:
            before = state()
            press(ns_window, keys)
            time.sleep(0.3)
            after = state()
            ran, keydown = after["ran"][len(before["ran"]):], after["keys"][len(before["keys"]):]
            if saves:
                ok = ran == ["save"] and not after["field"]
            else:
                ok = ran == [] and after["field"] and not any(k["prevented"] for k in keydown)
            passed += ok
            if not ok:
                failed.append({"keys": f"{keys} in a text field", "wanted": "save" if saves else "left to the field",
                               "ran": ran, "keydown": keydown, "field focused": after["field"]})
        window.evaluate_js("document.activeElement.blur(); true")
        # Real clicks with ⌘ held: the first adds the other shape to the selection, the second
        # takes it away again
        import AppKit
        _, b = json.loads(window.evaluate_js(CLICK_JS))
        selection = lambda: window.evaluate_js("window.FA.store.selection.join()")   # noqa: E731
        for want, what in (("clickA,clickB", "a ⌘-click adds the object to the selection"),
                           ("clickA", "a ⌘-click on a selected object takes it away")):
            click(ns_window, b, AppKit.NSEventModifierFlagCommand)
            for _ in range(40):
                time.sleep(0.05)
                if selection() == want:
                    break
            got = selection()
            passed += got == want
            if got != want:
                failed.append({"keys": "cmd+click", "wanted": what, "ran": [], "keydown": [], "selection": got})
        # A plain click on the part of an object outside the page picks it
        view = click(ns_window, json.loads(window.evaluate_js(OFF_PAGE_JS)))
        for _ in range(40):
            time.sleep(0.05)
            if selection() == "offPage":
                break
        got = selection()
        passed += got == "offPage"
        if got != "offPage":
            failed.append({"keys": "click", "wanted": "a click on the part of an object outside the page selects it", "ran": [],
                           "keydown": [], "selection": got, "view": view})
        # ⌘V with what other apps copy
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            samples = paste_samples(folder)
            for what, kinds, ok_item in samples:
                put_clipboard(kinds)
                before = {it["id"] for it in json.loads(window.evaluate_js(ITEMS_JS))}
                press(ns_window, "cmd+v")
                new = []
                for _ in range(60):
                    time.sleep(0.05)
                    new = [it for it in json.loads(window.evaluate_js(ITEMS_JS)) if it["id"] not in before]
                    if new:
                        break
                ok = len(new) == 1 and bool(ok_item(new[0]))
                passed += ok
                if not ok:
                    failed.append({"keys": f"cmd+v with {what}", "wanted": what, "ran": [], "keydown": [], "pasted": new})
    finally:
        restore_clipboard(clipboard)
    return {"passed": passed, "total": len(STEPS) + len(FIELD_STEPS) + 3 + len(samples), "failed": failed}

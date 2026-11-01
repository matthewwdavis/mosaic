"""PowerPoint as a running app: the decks it has open, and which slides a drag out of it means.

Dragging slide thumbnails out of PowerPoint for Mac hands over no slide, only a reference to
each (com.microsoft.PowerPoint.internal.Slide: a keyed archive of the deck's session id, the
slide's id and a creation id that only lives in memory). The slide id is presentation.xml's
sldId, so the slide can be found in the decks PowerPoint has open, as they were last saved.
Slide ids start at 256 in every deck, so several open decks may have the dragged slides; the
editor then asks which deck they came from.

The decks PowerPoint has open are the files its process holds (lsof), which needs no
permission. On Windows none are found, so slides dragged out of PowerPoint aren't taken there.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys

SLIDE_REF = "com.microsoft.PowerPoint.internal.Slide"
DECK_EXTENSIONS = (".pptx", ".pptm", ".potx")


def parse_lsof(text: str) -> list[str]:
    """Decks among the files `lsof -Fn` lists (not PowerPoint's ~$ lock files)."""
    out = []
    for line in text.splitlines():
        if line.startswith("n"):
            path = line[1:]
            name = os.path.basename(path)
            if name.lower().endswith(DECK_EXTENSIONS) and not name.startswith("~$") and os.path.isfile(path):
                out.append(path)
    return list(dict.fromkeys(out))


def open_decks() -> list[str]:
    """The decks PowerPoint has open, as files on disk (none if it isn't running, or off a Mac)."""
    if sys.platform != "darwin":
        return []
    try:
        pids = subprocess.run(["pgrep", "-x", "Microsoft PowerPoint"], capture_output=True, text=True,
                              timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for pid in pids:
        try:
            res = subprocess.run(["lsof", "-n", "-P", "-Fn", "-p", pid], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        out += parse_lsof(res.stdout)
    return list(dict.fromkeys(out))


def slide_refs(archives: list[bytes]) -> list[dict]:
    """The dragged slides, from each internal reference: [{"doc", "slide"}] (a keyed archive of a
    dictionary, or of an array of them)."""
    refs = []
    for data in archives:
        try:
            arc = plistlib.loads(data)
            objects = arc["$objects"]
        except Exception:   # noqa: BLE001 (not a reference we can read)
            continue

        def obj(x):
            return objects[x.data] if isinstance(x, plistlib.UID) else x

        root = obj(arc.get("$top", {}).get("root"))
        found = [obj(x) for x in root.get("NS.objects", [])] if isinstance(root, dict) and "NS.keys" not in root else [root]
        for d in found:
            if not isinstance(d, dict) or "NS.keys" not in d:
                continue
            m = {obj(k): obj(v) for k, v in zip(d["NS.keys"], d["NS.objects"])}
            if isinstance(m.get("SlideID"), int):
                refs.append({"doc": str(m.get("DocID", "")), "slide": m["SlideID"]})
    return refs


def slide_ref_archive(slide_id: int, doc: str = "{00000000-0000-0000-0000-000000000000}") -> bytes:
    """PowerPoint's reference to a slide, as a drag out of it holds one (for tests)."""
    uid = plistlib.UID
    return plistlib.dumps({"$version": 100000, "$archiver": "NSKeyedArchiver", "$top": {"root": uid(1)},
                           "$objects": ["$null", {"NS.keys": [uid(2), uid(3), uid(4)], "NS.objects": [uid(5), uid(6), uid(7)],
                                                  "$class": uid(8)},
                                        "DocID", "SlideID", "SlideCreationID", doc, slide_id, 1,
                                        {"$classname": "NSDictionary", "$classes": ["NSDictionary", "NSObject"]}]},
                          fmt=plistlib.FMT_BINARY)


def find_slides(refs: list[dict], decks: list[str] | None = None) -> list[dict]:
    """The open decks (as last saved) that have every dragged slide: [{"path", "numbers"}], the
    slides' numbers in the order they were dragged."""
    from ..importers.pptx import slide_ids
    want = [r["slide"] for r in refs]
    out = []
    for path in open_decks() if decks is None else decks:
        try:
            ids = slide_ids(path)
        except Exception:   # noqa: BLE001 (being saved, or not a deck after all)
            continue
        if want and all(s in ids for s in want):
            out.append({"path": path, "numbers": [ids.index(s) + 1 for s in want]})
    return out

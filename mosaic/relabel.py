"""Panel labels in a journal's look, from the command line, for a figure going to another journal:
`mosaic export fig.mosaic --journal Nature` exports the figure with its labels as Nature draws them,
leaving the document and its own exports as they are (`--copy` saves the relabelled document too).

It does to every page what the app's Size ▸ journal does to one (ui/js/labels.js restyleLabels;
keep the two in step). A panel label is a text box made with the Label tool, or one that's just a
letter ("a", "(a)", "a."), as Check finds them (export/preflight.py is_label). Each takes the
journal's font, size and weight, and its letter the journal's case and form, where it still has the
look of the page's journal before, so what was changed by hand in a label stays; a page with no
journal before takes all of it. The page then has the new journal's preset (its size kept), so
Check judges it by that journal's rules."""
from __future__ import annotations

import json
import re

from .export.preflight import LETTER, is_label
from .export.preflight import _text as text_of
from .journals import JOURNALS, MM
from .model import iter_items

RUN_DEFAULT = {"font": "Helvetica", "size": 6, "bold": False}
SHORT = {"Molecular Biology and Evolution": "mbe"}


def slug(name: str) -> str:
    """A journal's name as it goes in a file name: "nature", "plos_genetics", "plant_journal", "mbe"."""
    if name in SHORT:
        return SHORT[name]
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s[4:] if s.startswith("the_") else s


def find_journal(name: str) -> dict | None:
    """A journal by its name ("Nature", "plos genetics") or as in a file name ("plos_genetics", "mbe")."""
    want, key = name.strip().lower(), slug(name.strip())
    return next((j for j in JOURNALS if j["name"].lower() == want or slug(j["name"]) == key), None)


def page_labels(page: dict) -> dict | None:
    """The labels' look of the page's journal (its size preset), or None."""
    jname = (page.get("preset") or {}).get("journal")
    return next((j.get("labels") for j in JOURNALS if j["name"] == jname), None)


def _cased(s: str, case: str | None) -> str:
    return s.upper() if case == "upper" else s.lower()


def as_label(letter: str, look: dict) -> str:
    """A letter as the look writes labels: in its case and form ("a", "(A)")."""
    return (look.get("form") or "a").replace("a", _cased(letter, look.get("case") or "lower"))


def restyle_label(item: dict, before: dict | None, look: dict) -> bool:
    """One label in the look (from the look before: what still matches it changes). Whether it changed."""
    was = json.dumps(item["text"], sort_keys=True)
    runs = [r for p in item["text"]["paragraphs"] for r in p.get("runs") or []]

    def value(r: dict, k: str):
        return RUN_DEFAULT[k] if r.get(k) is None else r[k]

    for r in runs:
        for k in ("font", "size", "bold"):
            # (as it shows: 8 and 8.0 are the same size, a missing value the default)
            if look.get(k) is not None and (not before or value(r, k) == before[k]) and value(r, k) != look[k]:
                r[k] = look[k]
    # The letter: its case and form; other text the Label tool made, just its case
    t = text_of(item)
    m = LETTER.match(t)
    paragraphs = item["text"]["paragraphs"]
    if m and len(paragraphs) == 1 and (not before or t == as_label(m.group(1), before)):
        if t != as_label(m.group(1), look):
            p = paragraphs[0]
            run = next((r for r in p.get("runs") or [] if (r.get("t") or "").strip()), (p.get("runs") or [{}])[0])
            p["runs"] = [{**run, "t": as_label(m.group(1), look)}]
    elif not m and look.get("case") and (not before or t == _cased(t, (before or {}).get("case"))):
        for r in runs:
            if r.get("t") and r["t"] != _cased(r["t"], look["case"]):
                r["t"] = _cased(r["t"], look["case"])
    return json.dumps(item["text"], sort_keys=True) != was


def figure_type(journal: dict, width_pt: float) -> str:
    """The journal's figure type a page of this width is: the one as wide, else the nearest."""
    w = width_pt / MM
    return min(journal["types"], key=lambda t: (abs(t["width_mm"] - w) > 0.05, abs(t["width_mm"] - w)))["name"]


def fit_label(resolver, item: dict, page_width: float) -> None:
    """A label's box once its text has changed: its text on one line, the box growing about the side
    the text is aligned to (so a centred letter stays where it was), as tall as the text where it
    fits its text (autofit), and the text kept on the page. (A box made in PowerPoint, 7.2 pt insets
    each side of a 9.3 pt box, would otherwise break "(a)" into three lines.)"""
    x, y, w, h = item["frame"]
    body = item["text"]
    probe = resolver.resolve({**item, "text": {**body, "wrap": False}}).autofit_frame
    need = probe[2] if probe else w                      # the box its text needs on one line
    align = (body.get("paragraphs") or [{}])[0].get("align") or "l"
    wrap = body.get("wrap", True)
    target = max(w, need + 0.05) if wrap else need       # (a hair over, so a wrapped line can't break)
    if abs(target - w) > 1e-6:
        x -= (target - w) / 2 if align == "ctr" else (target - w) if align == "r" else 0.0
        w = target
    lins, _, rins, _ = body.get("insets") or (7.2, 3.6, 7.2, 3.6)
    text_w = need - lins - rins
    start = x + lins + ((w - lins - rins - text_w) / 2 if align == "ctr" else (w - lins - rins - text_w) if align == "r" else 0.0)
    if start < 0:
        x -= start
    elif start + text_w > page_width:
        x -= start + text_w - page_width
    item["frame"] = [x, y, w, h]
    if body.get("autofit") == "shape":
        fitted = resolver.resolve(item).autofit_frame
        if fitted:
            item["frame"] = [x, y, fitted[2], fitted[3]] if wrap else fitted


def relabel(doc: dict, journal: dict, fonts=None) -> list[int]:
    """Every page's panel labels in the journal's look, and its preset the journal's (in place).
    Returns how many labels changed on each page. With a font index, each changed label's box is
    fitted to its new text (fit_label)."""
    look = journal.get("labels") or {}
    resolver = None
    if fonts is not None:
        from .resolve import Resolver
        resolver = Resolver(doc, fonts)
    counts = []
    for page in doc.get("pages", []):
        before = page_labels(page)
        changed = []
        if look:
            changed = [item for item in iter_items(page.get("items", [])) if is_label(item) and restyle_label(item, before, look)]
            if changed and resolver is not None:
                resolver.use_page(page.get("items", []))
                top = {id(it) for it in page.get("items", [])}   # (the page's own objects: a group's are in its frame)
                for item in changed:
                    if id(item) in top and not item.get("rot"):
                        fit_label(resolver, item, float(page["width"]))
        page["preset"] = {"journal": journal["name"], "type": figure_type(journal, float(page["width"]))}
        counts.append(len(changed))
    return counts

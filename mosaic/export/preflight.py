"""Pre-export check: what a journal (or a careful co-author) would flag before submission."""
from __future__ import annotations

import ctypes
import math
import os
import re

from .. import alphableed, picturekind, plottext, vectors
from ..assets import PDFIUM_LOCK, SourceResolver, get_cache, resolve_link
from ..geometry import DrawPath
from .._labapp import journals as _shared_journals
from ..journals import JOURNALS, MM
from ..model import iter_items
from ..progress import Progress
from ..resolve import DrawPicture, DrawText, Resolver, flat_prims

MIN_PHOTO_DPI = 300.0
MIN_LINE_PT = 0.25   # Nature asks for 0.25 to 1 pt, and many journals for at least 0.25 pt


def _pdf_text(path: str, page_index: int) -> list[tuple[float, str]]:
    """Effective size (points) and font family of every character on a PDF page."""
    with PDFIUM_LOCK:
        return _text_of(path, page_index)


def _text_of(path: str, page_index: int) -> list[tuple[float, str]]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    out = []
    doc = pdfium.PdfDocument(path)
    try:
        tp = doc[page_index].get_textpage()
        m = raw.FS_MATRIX()
        for i in range(tp.count_chars()):
            ch = tp.get_text_range(i, 1)
            if not ch.strip():
                continue
            fs = raw.FPDFText_GetFontSize(tp.raw, i)
            if raw.FPDFText_GetMatrix(tp.raw, i, ctypes.byref(m)):
                fs *= math.sqrt(abs(m.a * m.d - m.b * m.c))
            need = raw.FPDFText_GetFontInfo(tp.raw, i, None, 0, None)
            name = ctypes.create_string_buffer(max(int(need), 1))
            raw.FPDFText_GetFontInfo(tp.raw, i, name, len(name), None)
            out.append((fs, family(name.value.decode("utf-8", "replace"))))
    finally:
        doc.close()
    return out


def family(font: str) -> str:
    """A PDF font's family as journals name fonts: without a subset tag or style and foundry
    endings ("ABCDEF+Arial-BoldMT" -> "Arial", "Helvetica-Bold" -> "Helvetica")."""
    name = font.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", font) else font
    return re.sub(r"(PSMT|PS|MT)$", "", re.split(r"[-,]", name)[0]) or font


def accepts(fonts: list[str], fam: str) -> bool:
    """Whether a family is one of a journal's fonts (spaces and case aside: TimesNewRoman is
    Times New Roman)."""
    key = re.sub(r"[^a-z0-9]", "", fam.lower())
    return any(re.sub(r"[^a-z0-9]", "", f.lower()) == key for f in fonts)


# Panel labels (as ui/js/labels.js finds them): a text box made with the Label tool, or one that's
# just a letter, bracketed or with a full stop
LETTER = re.compile(r"^\(?([A-Za-z])[).]?$")


def _text(item: dict) -> str:
    return "\n".join("".join(r.get("t") or "" for r in p.get("runs") or []) for p in (item.get("text") or {}).get("paragraphs") or []).strip()


def is_label(item: dict) -> bool:
    return item.get("type") == "shape" and bool(item.get("textbox")) and (bool(item.get("panel_label")) or bool(LETTER.match(_text(item))))


def label_look(labels: dict) -> str:
    """A journal's labels in words: "a, b, c in bold 8 pt Helvetica"."""
    form, case = labels.get("form") or "a", labels.get("case") or "lower"
    letters = ", ".join(form.replace("a", c.upper() if case == "upper" else c) for c in "abc")
    weight = "bold " if labels.get("bold") else ""
    return f"{letters} in {weight}{labels.get('size', 8):g} pt {labels.get('font', 'Helvetica')}"


def _label_differs(item: dict, labels: dict) -> bool:
    runs = [r for p in item["text"]["paragraphs"] for r in p.get("runs") or [] if (r.get("t") or "").strip()]
    if any((r.get("font") or "Helvetica") != labels["font"] or abs(float(r.get("size", 6)) - labels["size"]) > 0.005
           or bool(r.get("bold")) != bool(labels["bold"]) for r in runs):
        return True
    t, m = _text(item), LETTER.match(_text(item))
    if m:
        letter = m.group(1).upper() if labels.get("case") == "upper" else m.group(1).lower()
        return t != (labels.get("form") or "a").replace("a", letter)
    return t != (t.upper() if labels.get("case") == "upper" else t.lower())


def _placed_lines(cache, prim: DrawPicture, variants: dict) -> list[float]:
    """Widths of the lines a placed PDF or SVG draws inside its crop, thinnest first, at the
    source's own size (from the copy that PDF export uses)."""
    if prim.source == "png":
        return []
    kind = prim.source if prim.source in ("pdf", "svg") and prim.source in variants else \
        next((k for k in ("pdf", "svg") if k in variants), None)
    if kind is None:
        return []
    try:
        found = vectors.strokes(cache.path(*_sha_kind(variants[kind])), kind, prim.page_index if kind == "pdf" else 0)
    except Exception:
        return []
    return vectors.visible_widths(found, prim.crop)


def _length(mm: float, unit: str) -> str:
    v = {"pt": mm * MM, "cm": mm / 10, "in": mm / 25.4}.get(unit, mm)
    s = f"{v:.{2 if unit in ('cm', 'in') else 1}f}".rstrip("0").rstrip(".")
    return f"{s} {unit if unit in ('pt', 'cm', 'in') else 'mm'}"


def _journal_fit(page: dict, journal: dict, unit: str) -> list[dict]:
    """The page's size against a journal's figure widths and greatest depth (a journal that takes
    any width, bioRxiv, only minds a page bigger than its text area)."""
    w, h, name = float(page["width"]) / MM, float(page["height"]) / MM, journal["name"]
    types = sorted(journal["types"], key=lambda t: t["width_mm"])
    fit = _shared_journals.size_fit(journal, w, h)
    fits = fit["type"]
    depth = _length(journal["depth_mm"], unit)
    out = []
    if fit["deep"]:
        out.append(("warning", f"The page is {_length(h, unit)} tall; {name} figures can be at most {depth} tall"))
    most = _shared_journals.widest(journal)
    if fit["wide"]:
        out.append(("warning", f"The page is {_length(w, unit)} wide; the widest {name} figures are "
                               + (f"{_length(most, unit)}" if journal.get("max_width_mm") else
                                  f"{_length(types[-1]['width_mm'], unit)} ({types[-1]['name'].lower()})")))
    elif fit["odd"]:
        sizes = [f"{_length(t['width_mm'], unit)} ({t['name'].lower()})" for t in types]
        out.append(("info", f"The page is {_length(w, unit)} wide; {name} figures are "
                            + (", ".join(sizes[:-1]) + " or " + sizes[-1] if len(sizes) > 1 else sizes[0]) + " wide"))
    if not out:
        size = f"{_length(w, unit).rsplit(' ', 1)[0]} × {_length(h, unit)}"
        if fits is None:   # (any width up to the widest: bioRxiv; one wider than its text width prints scaled to it)
            out.append(("ok", f"The page, {size}, fits {name}'s figures (any size up to "
                              f"{_length(most, unit).rsplit(' ', 1)[0]} × {depth})"
                              + (f"; prose prints it scaled to the {_length(types[-1]['width_mm'], unit)} text width"
                                 if w > types[-1]["width_mm"] + 0.05 else "")))
        else:
            out.append(("ok", f"The page, {size}, fits the {name} {fits['name'].lower()} size (at most {depth} tall)"))
    return [{"level": level, "page": page["id"], "message": message} for level, message in out]


def _visible_stroke(prim, fills: dict) -> bool:
    """A line that shows as a line: not see-through, and not a border in its fill's own colour
    (a shape's fill is drawn on its own, along the same path: fills maps id(path) -> fill)."""
    s, f = prim.stroke, prim.fill or fills.get(id(prim.path))
    return s.opacity > 0 and not (f is not None and f.gradient is None and f.color.lower() == s.color.lower()
                                  and f.opacity == s.opacity)


def preflight(doc: dict, options: dict, progress: Progress | None = None) -> dict:
    p = progress or Progress()
    cache = get_cache()
    doc = plottext.with_lifts(doc, cache)   # (plots as exported: without texts lifted out in dangerous mode)
    pages = options.get("pages")
    sel = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
    resolver = Resolver(doc)
    sources = SourceResolver(doc, cache)   # (as export reads the pictures: for see-through colour)
    found: list[dict] = []
    smallest = thinnest = None
    min_dpi = float(options.get("min_dpi", MIN_PHOTO_DPI))
    min_line = float(options.get("min_line_pt", MIN_LINE_PT))
    text_cache: dict = {}
    free_smallest = None   # the smallest text on pages whose journal doesn't set one
    free_thinnest = None   # and the thinnest line on pages whose journal sets no line width
    p.plan(sum(1 for page in sel for _ in iter_items(page.get("items", []))) or 1)
    checked = 0
    for page in sel:
        pw, ph = float(page["width"]), float(page["height"])
        # The page's size against a journal's: the one asked for, else the page's own journal size
        jname = options["journal"] if "journal" in options else (page.get("preset") or {}).get("journal")
        journal = next((j for j in JOURNALS if j["name"] == jname), None)
        if journal:
            found += _journal_fit(page, journal, options.get("units", "mm"))
        rules = (journal or {}).get("text") or {}
        # Line widths and resolution: the journal's (or its publisher's), else mosaic's own
        lrules, prules = (journal or {}).get("lines") or {}, (journal or {}).get("pictures") or {}
        line_min, line_max = lrules.get("min_pt"), lrules.get("max_pt")
        sizes, fonts = [], {}   # the page's text: (printed size, item, a panel label?); family -> first item
        resolver.use_page(page.get("items", []))
        for item in iter_items(page.get("items", [])):
            if checked:
                p.advance(1)   # (the one before: done)
            checked += 1
            p.step(f"Checking {item.get('name') or item.get('type') or 'an object'}")
            if item.get("type") == "group" or item.get("hidden"):
                continue
            r = resolver.resolve(item)
            bb = r.bbox
            name = item.get("name") or item.get("type")
            if bb and (bb[0] < -0.01 or bb[1] < -0.01 or bb[2] > pw + 0.01 or bb[3] > ph + 0.01) \
                    and bb[2] > 0 and bb[3] > 0 and bb[0] < pw and bb[1] < ph:
                found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                              "message": f"{name} runs past the page edge and will be cut off there"})
            lines, hairlines = [], False   # (printed width, what) of the lines the item draws
            prims = list(flat_prims(r.prims))   # pictures cropped to a shape are inside a group
            if any(isinstance(p, DrawPath) and p.meta.get("role") == "outline" for p in prims):
                lines.append((float((item.get("outline") or {}).get("width", 1.0)), "outline"))
            fills = {id(p.path): p.fill for p in prims if isinstance(p, DrawPath) and p.fill is not None}
            for prim in prims:
                if isinstance(prim, DrawPath):
                    if prim.stroke is not None and prim.meta.get("role") != "outline" and _visible_stroke(prim, fills):
                        lines.append((prim.stroke.width, "line"))
                elif isinstance(prim, DrawText):
                    for run in prim.runs:   # a symbol's copy scales its text (the text's matrix)
                        if run.text.strip():
                            size = run.size * prim.matrix.scale_factor
                            sizes.append((size, item, is_label(item)))
                            fonts.setdefault(run.face.ref.family, item)
                elif isinstance(prim, DrawPicture):
                    asset = doc["assets"][prim.asset_id]
                    variants = asset["variants"]
                    scale = prim.scale
                    printed = []   # what the scaling changes: its smallest text and thinnest line
                    widths = _placed_lines(cache, prim, variants)
                    hairlines = hairlines or (bool(widths) and widths[0] == 0)
                    placed = [w * vectors.thinnest_scale(prim.matrix) for w in widths if w > 0]
                    if placed:
                        lines += [(placed[0], "placed"), (placed[-1], "placed")]
                    if "pdf" in variants:
                        key = (variants["pdf"]["sha256"], prim.page_index)
                        if key not in text_cache:
                            try:
                                text_cache[key] = _pdf_text(cache.path(*_sha_kind(variants["pdf"])), prim.page_index)
                            except Exception:
                                text_cache[key] = []
                        if text_cache[key]:
                            s = min(size for size, _ in text_cache[key]) * scale
                            printed.append(f"its smallest text prints at {s:.2f} pt")
                            sizes += [(min(size for size, _ in text_cache[key]) * scale, item, False),
                                      (max(size for size, _ in text_cache[key]) * scale, item, False)]
                            for _, fam in text_cache[key]:
                                fonts.setdefault(fam, item)
                    else:
                        if "svg" in variants:
                            found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                          "message": f"{name}: no PDF copy, so PDF export converts its SVG"})
                    if "svg" not in variants and "pdf" in variants:
                        found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name}: no SVG copy, so SVG export converts its PDF"})
                    raster = next((variants[k] for k in ("png", "tiff", "jpeg") if k in variants), None)
                    if raster and not any(k in variants for k in ("pdf", "svg")):
                        px_w = raster["px"][0] * (prim.crop[2] - prim.crop[0]) / max(prim.src_size[0], 1e-9)
                        placed_in = (prim.crop[2] - prim.crop[0]) * scale / 72.0
                        dpi = px_w / placed_in if placed_in > 0 else 0
                        kind, guessed = picturekind.item_kind(item, asset, cache)
                        need = prules.get(kind) if kind else None
                        guess = " (kind guessed from the picture; its Picture tab can set it)" if guessed else ""
                        if kind and kind in prules.get("vector", ()):
                            # (a journal that wants graphs, and text and lines over photos, as vector artwork)
                            level = "warning"
                            message = f"{name}: {dpi:.0f} dpi at its placed size; " + (
                                f"{journal['name']} asks for line art as vector files (PDF, EPS or SVG), not pictures"
                                if kind == "line_art" else
                                f"{journal['name']} asks for text and lines over photos to stay editable, not drawn into "
                                f"the picture (add them in mosaic)") + guess
                        elif need:
                            level = "warning" if dpi < need - 0.5 else "ok"
                            message = (f"{name}: {dpi:.0f} dpi at its placed size; {journal['name']} asks for at least "
                                       f"{need:g} dpi for {picturekind.NAMES[kind]}" + guess)
                        else:
                            level = "warning" if dpi < min_dpi - 0.5 else "ok"
                            message = (f"{name}: {dpi:.0f} dpi at its placed size"
                                       + (f" (below {min_dpi:.0f})" if level == "warning" else ""))
                        found.append({"level": level, "item": item.get("id"), "page": page["id"], "message": message})
                    if placed:
                        printed.append(f"its thinnest line {'at' if printed else 'prints at'} {placed[0]:.2f} pt")
                    if printed and abs(scale - 1.0) > 0.005:
                        found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name} is scaled to {scale * 100:.1f}%: " + " and ".join(printed)})
                    # Stretched unevenly (a frame from PowerPoint can be): its text and curves come out distorted
                    across, down = math.hypot(prim.matrix.a, prim.matrix.b), math.hypot(prim.matrix.c, prim.matrix.d)
                    if abs(across - down) > 0.005 * max(across, down):
                        found.append({"level": "warning", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name} is stretched, {across * 100:.1f}% across and {down * 100:.1f}% "
                                                 f"down, so its text and curves are distorted (100% on its Picture tab "
                                                 f"puts it back)"})
                    for level, message in plottext.notes(name, item, asset):
                        found.append({"level": level, "item": item.get("id"), "page": page["id"], "message": message})
                    bleed = alphableed.check_note(sources, prim.asset_id, prim.source, name)
                    if bleed:
                        found.append({"level": "info", "item": item.get("id"), "page": page["id"], "message": bleed})
                    linked = doc["assets"].get(asset.get("lifted_from")) or asset   # (its own file, not the copy without lifted texts)
                    prim_var = linked["variants"].get(linked.get("primary")) or next(iter(linked["variants"].values()))
                    if prim_var.get("src") and not resolve_link(prim_var, None):
                        found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name}: linked file not found; using the copy stored "
                                                 f"in the document"})
            if lines:
                width, what = min(lines)
                thinnest = min(thinnest if thinnest is not None else 1e9, width)
                said = {"line": "its line is", "outline": "its outline is", "placed": "its thinnest line prints at"}[what]
                if line_min is None:
                    free_thinnest = min(free_thinnest if free_thinnest is not None else 1e9, width)
                    if width < min_line - 0.005:
                        found.append({"level": "warning", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name}: {said} {width:.2f} pt (below {min_line:g} pt)"})
                elif width < line_min - 0.005:
                    found.append({"level": "info" if lrules.get("about") else "warning", "item": item.get("id"),
                                  "page": page["id"], "message": f"{name}: {said} {width:.2f} pt; {journal['name']} "
                                                                 f"asks for at least {line_min:g} pt"})
                # (a line thicker than the journal asks for is only a note: it still prints)
                width, what = max(lines)
                if line_max is not None and width > line_max + 0.005:
                    said = {"line": "its line is", "outline": "its outline is",
                            "placed": "its thickest line prints at"}[what]
                    found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                  "message": f"{name}: {said} {width:.2f} pt; {journal['name']} asks for at most "
                                             f"{line_max:g} pt"})
            if hairlines:
                found.append({"level": "warning", "item": item.get("id"), "page": page["id"],
                              "message": f"{name} has hairlines (lines set to 0 pt wide), which print as thin as "
                                         f"the printer can make them, or not at all"})
        found += _journal_text(page, journal, rules, sizes, fonts)
        if sizes:
            low = min(size for size, _, _ in sizes)
            smallest = min(smallest or 1e9, low)
            # (a journal's own smallest size is checked with its rules; one it gives roughly, "about",
            # is only a note, so mosaic's smallest size for all pages still holds)
            if rules.get("min_pt") is None or rules.get("about"):
                free_smallest = min(free_smallest or 1e9, low)
    summary = {"smallest_text_pt": round(smallest, 2) if smallest else None,
               "thinnest_line_pt": round(thinnest, 2) if thinnest is not None else None}
    top = []
    if free_smallest is not None and free_smallest < float(options.get("min_text_pt", 5.0)) - 0.005:
        top.append({"level": "warning", "message": f"smallest text is {free_smallest:.2f} pt "
                                                   f"(below {options.get('min_text_pt', 5.0)} pt)"})
    if free_thinnest is not None and free_thinnest < min_line - 0.005:
        top.append({"level": "warning", "message": f"thinnest line is {free_thinnest:.2f} pt (below {min_line:g} pt)"})
    found = top + found
    # De-duplicate messages
    seen = set()
    found = [f for f in found if not (f["message"] in seen or seen.add(f["message"]))]
    return {"items": found, "summary": summary}


def _journal_text(page: dict, journal: dict | None, rules: dict, sizes: list, fonts: dict) -> list[dict]:
    """The page's text against its journal's rules: the smallest and largest sizes (panel labels
    have a size of their own), the fonts it accepts, and how its panel labels look."""
    if not journal:
        return []
    out, jname = [], journal["name"]
    def note(level, item, message):
        out.append({"level": level, "item": item.get("id") if item else None, "page": page["id"], "message": message})
    def named(item):
        text = _text(item) if item.get("textbox") else ""
        return item.get("name") or (f"“{text[:24]}”" if text else item.get("type"))
    lo, hi = rules.get("min_pt"), rules.get("max_pt")
    # (a journal that gives its sizes roughly, "about 6–8 pt", gets a note rather than a warning)
    level = "info" if rules.get("about") else "warning"
    rough = f"about {lo:g}–{hi:g} pt" if rules.get("about") and lo is not None and hi is not None else None
    if lo is not None and sizes:
        size, item, _ = min(sizes, key=lambda s: s[0])
        if size < lo - 0.005:
            note(level, item, f"{named(item)}: text at {size:.2f} pt; {jname} asks for {rough or f'at least {lo:g} pt'}")
    body = [s for s in sizes if not s[2]]
    if hi is not None and body:
        size, item, _ = max(body, key=lambda s: s[0])
        if size > hi + 0.005:
            note(level, item, f"{named(item)}: text at {size:.2f} pt; {jname} asks for {rough or f'at most {hi:g} pt'}")
    allowed = rules.get("fonts")
    if allowed:
        names = ", ".join(allowed[:-1]) + " or " + allowed[-1] if len(allowed) > 1 else allowed[0]
        for fam, item in sorted(fonts.items()):
            if not accepts(allowed, fam):
                if rules.get("fonts_only"):
                    note("warning", item, f"{named(item)}: text in {fam}; {jname} accepts only {names}")
                else:
                    note("info", item, f"{named(item)}: text in {fam}; {jname} prefers {names}")
    labels = journal.get("labels")
    if labels:
        how = " as measured in its published figures" if labels.get("measured") else ""
        for item in iter_items(page.get("items", [])):
            if not item.get("hidden") and is_label(item) and _label_differs(item, labels):
                note("info", item, f"Panel label “{_text(item)}” isn't in {jname}'s style ({label_look(labels)}{how})")
    return out


FORMAT_NAMES = {"pdf": "PDF", "svg": "SVG", "png": "PNG", "tiff": "TIFF", "jpeg": "JPEG", "eps": "EPS", "pptx": "PowerPoint"}
COLOUR_NAMES = {"rgb": "RGB", "rgb_preferred": "RGB (preferred) or CMYK", "either": "RGB or CMYK",
                "cmyk_preferred": "CMYK (preferred for print) or RGB", "cmyk": "CMYK"}


def _either(names: list[str]) -> str:
    return ", ".join(names[:-1]) + " or " + names[-1] if len(names) > 1 else names[0]


def page_kind(doc: dict, page: dict, cache=None) -> str:
    """What a whole page is as a picture (a PNG or TIFF of it): line art (graphs, text, drawings),
    a photo, or a photo with text or lines."""
    cache = cache or get_cache()
    kinds, other = set(), False
    for item in iter_items(page.get("items", [])):
        if item.get("type") == "group" or item.get("hidden"):
            continue
        asset = doc["assets"].get(item.get("asset")) if item.get("type") == "picture" else None
        kind = picturekind.item_kind(item, asset, cache)[0] if asset else None
        if kind:
            kinds.add(kind)
        else:
            other = True
    if not kinds & {"photo", "combination"}:
        return "line_art"
    return "photo" if kinds == {"photo"} and not other else "combination"


def export_check(doc: dict, options: dict) -> list[dict]:
    """The Export window's settings against the journals of the pages being exported: the formats,
    resolution, colour, fonts and transparency each takes (file sizes are checked once written).
    The first note for each journal says what it takes."""
    cache = get_cache()
    pages = options.get("pages")
    sel = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
    formats = [f.lower() for f in options.get("formats", [])]
    dpi = float(options.get("dpi", 600))
    out = []
    def note(level, journal, message):
        if not any(f["message"] == message for f in out):
            out.append({"level": level, "journal": journal["name"], "message": message})
    for page in sel:
        jname = (page.get("preset") or {}).get("journal")
        journal = next((j for j in JOURNALS if j["name"] == jname), None)
        rules = (journal or {}).get("export")
        if not rules:
            continue
        takes = rules["formats"]
        note("info", journal, f"{jname} takes {_either([FORMAT_NAMES[f] for f in takes])} files in "
                              f"{COLOUR_NAMES[rules.get('colour', 'either')]} colour"
                              + ((f", at most {rules['max_mb']:g} MB each" if rules.get("firm", True) else
                                  f", under {rules['max_mb']:g} MB each where possible") if rules.get("max_mb") else ""))
        for f in formats:
            if f not in takes:
                note("warning", journal, f"{jname} doesn't take {FORMAT_NAMES[f]} files for final figures")
        raster = [FORMAT_NAMES[f] for f in formats if f in ("png", "tiff", "jpeg") and f in takes]
        if raster:
            kind = page_kind(doc, page, cache)
            need = (journal.get("pictures") or {}).get(kind)
            if need and dpi < need - 0.5:
                note("warning", journal, f"{_either(raster)} at {dpi:g} dpi: {jname} asks for at least {need:g} dpi "
                                         f"for {picturekind.NAMES[kind]}" + (f" ({page['name']})" if len(sel) > 1 else ""))
            if rules.get("max_dpi") and dpi > rules["max_dpi"] + 0.5:
                note("warning", journal, f"{_either(raster)} at {dpi:g} dpi: {jname} takes at most {rules['max_dpi']:g} dpi")
        colour = rules.get("colour", "either")
        if options.get("cmyk") and colour == "rgb":
            note("warning", journal, f"CMYK colour is ticked; {jname} asks for RGB")
        elif options.get("cmyk") and colour == "rgb_preferred":
            note("info", journal, f"CMYK colour is ticked; {jname} takes it but recommends RGB")
        elif not options.get("cmyk") and colour == "cmyk":
            note("warning", journal, f"{jname} asks for CMYK colour (More options)")
        elif not options.get("cmyk") and colour == "cmyk_preferred":
            note("info", journal, f"{jname} asks for CMYK colour for print (More options)")
        if not options.get("embed_fonts", True) and rules.get("embed_fonts"):
            note("warning", journal, f"Fonts left out of placed PDFs won't be embedded; {jname} asks for embedded fonts")
        if options.get("transparent", True) and rules.get("no_alpha") and any(f in ("png", "tiff") for f in formats):
            note("warning", journal, f"{jname} takes no transparency (alpha channels): set Background to White")
    return out


def size_limits(doc: dict, pages: list[int] | None, files: list[str]) -> tuple[list[str], list[str]]:
    """Written files bigger than the exported pages' journals take: warnings for a firm limit,
    notes for one asked "where possible"."""
    sel = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
    limits = {}
    for page in sel:
        journal = next((j for j in JOURNALS if j["name"] == (page.get("preset") or {}).get("journal")), None)
        if journal and (journal.get("export") or {}).get("max_mb"):
            limits[journal["name"]] = journal["export"]
    warnings, notes = [], []
    for path in files:
        mb = os.path.getsize(path) / 1e6
        for jname, rules in sorted(limits.items()):
            if mb > rules["max_mb"]:
                if rules.get("firm", True):
                    warnings.append(f"{os.path.basename(path)} is {mb:.1f} MB; {jname} takes files of at most "
                                    f"{rules['max_mb']:g} MB")
                else:
                    notes.append(f"{os.path.basename(path)} is {mb:.1f} MB; {jname} asks for files under "
                                 f"{rules['max_mb']:g} MB where possible")
    return warnings, notes


def _sha_kind(var: dict):
    return var["sha256"], var["kind"]

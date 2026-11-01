"""Pre-export check: what a journal (or a careful co-author) would flag before submission."""
from __future__ import annotations

import ctypes
import math

from .. import vectors
from ..assets import PDFIUM_LOCK, get_cache, resolve_link
from ..geometry import DrawPath
from ..journals import JOURNALS, MM
from ..model import iter_items
from ..resolve import DrawPicture, DrawText, Resolver, flat_prims

MIN_PHOTO_DPI = 300.0
MIN_LINE_PT = 0.25   # Nature asks for 0.25 to 1 pt, and many journals for at least 0.25 pt


def _pdf_text_sizes(path: str, page_index: int) -> list[float]:
    """Effective size (points) of every character on a PDF page."""
    with PDFIUM_LOCK:
        return _text_sizes(path, page_index)


def _text_sizes(path: str, page_index: int) -> list[float]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    sizes = []
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
            sizes.append(fs)
    finally:
        doc.close()
    return sizes


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
    """The page's size against a journal's figure widths and greatest depth."""
    w, h, name = float(page["width"]) / MM, float(page["height"]) / MM, journal["name"]
    types = sorted(journal["types"], key=lambda t: t["width_mm"])
    fits = next((t for t in types if abs(t["width_mm"] - w) <= 0.05), None)
    depth = _length(journal["depth_mm"], unit)
    out = []
    if h > journal["depth_mm"] + 0.05:
        out.append(("warning", f"The page is {_length(h, unit)} tall; {name} figures can be at most {depth} tall"))
    if w > types[-1]["width_mm"] + 0.05:
        out.append(("warning", f"The page is {_length(w, unit)} wide; the widest {name} figures are "
                               f"{_length(types[-1]['width_mm'], unit)} ({types[-1]['name'].lower()})"))
    elif fits is None:
        sizes = [f"{_length(t['width_mm'], unit)} ({t['name'].lower()})" for t in types]
        out.append(("info", f"The page is {_length(w, unit)} wide; {name} figures are "
                            + (", ".join(sizes[:-1]) + " or " + sizes[-1] if len(sizes) > 1 else sizes[0]) + " wide"))
    if not out:
        size = f"{_length(w, unit).rsplit(' ', 1)[0]} × {_length(h, unit)}"
        out.append(("ok", f"The page, {size}, fits the {name} {fits['name'].lower()} size (at most {depth} tall)"))
    return [{"level": level, "page": page["id"], "message": message} for level, message in out]


def _visible_stroke(prim, fills: dict) -> bool:
    """A line that shows as a line: not see-through, and not a border in its fill's own colour
    (a shape's fill is drawn on its own, along the same path: fills maps id(path) -> fill)."""
    s, f = prim.stroke, prim.fill or fills.get(id(prim.path))
    return s.opacity > 0 and not (f is not None and f.gradient is None and f.color.lower() == s.color.lower()
                                  and f.opacity == s.opacity)


def preflight(doc: dict, options: dict) -> dict:
    cache = get_cache()
    pages = options.get("pages")
    sel = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
    resolver = Resolver(doc)
    found: list[dict] = []
    smallest = thinnest = None
    min_dpi = float(options.get("min_dpi", MIN_PHOTO_DPI))
    min_line = float(options.get("min_line_pt", MIN_LINE_PT))
    text_cache: dict = {}
    for page in sel:
        pw, ph = float(page["width"]), float(page["height"])
        # The page's size against a journal's: the one asked for, else the page's own journal size
        jname = options["journal"] if "journal" in options else (page.get("preset") or {}).get("journal")
        journal = next((j for j in JOURNALS if j["name"] == jname), None)
        if journal:
            found += _journal_fit(page, journal, options.get("units", "mm"))
        resolver.use_page(page.get("items", []))
        for item in iter_items(page.get("items", [])):
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
                            smallest = min(smallest or 1e9, run.size * prim.matrix.scale_factor)
                elif isinstance(prim, DrawPicture):
                    asset = doc["assets"][prim.asset_id]
                    variants = asset["variants"]
                    scale = prim.scale
                    printed = []   # what the scaling changes: its smallest text and thinnest line
                    widths = _placed_lines(cache, prim, variants)
                    hairlines = hairlines or (bool(widths) and widths[0] == 0)
                    placed = [w * vectors.thinnest_scale(prim.matrix) for w in widths if w > 0]
                    if placed:
                        lines.append((placed[0], "placed"))
                    if "pdf" in variants:
                        key = (variants["pdf"]["sha256"], prim.page_index)
                        if key not in text_cache:
                            try:
                                text_cache[key] = _pdf_text_sizes(cache.path(*_sha_kind(variants["pdf"])), prim.page_index)
                            except Exception:
                                text_cache[key] = []
                        if text_cache[key]:
                            s = min(text_cache[key]) * scale
                            smallest = min(smallest or 1e9, s)
                            printed.append(f"its smallest text prints at {s:.2f} pt")
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
                        level = "warning" if dpi < min_dpi - 0.5 else "ok"
                        found.append({"level": level, "item": item.get("id"), "page": page["id"],
                                      "message": f"{name}: {dpi:.0f} dpi at its placed size"
                                                 + (f" (below {min_dpi:.0f})" if level == "warning" else "")})
                    if placed:
                        printed.append(f"its thinnest line {'at' if printed else 'prints at'} {placed[0]:.2f} pt")
                    if printed and abs(scale - 1.0) > 0.005:
                        found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name} is scaled to {scale * 100:.1f}%: " + " and ".join(printed)})
                    prim_var = variants.get(asset.get("primary")) or next(iter(variants.values()))
                    if prim_var.get("src") and not resolve_link(prim_var, None):
                        found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name}: linked file not found; using the copy stored "
                                                 f"in the document"})
            if lines:
                width, what = min(lines)
                thinnest = min(thinnest if thinnest is not None else 1e9, width)
                if width < min_line - 0.005:
                    found.append({"level": "warning", "item": item.get("id"), "page": page["id"],
                                  "message": f"{name}: " + {"line": "its line is", "outline": "its outline is",
                                                            "placed": "its thinnest line prints at"}[what]
                                             + f" {width:.2f} pt (below {min_line:g} pt)"})
            if hairlines:
                found.append({"level": "warning", "item": item.get("id"), "page": page["id"],
                              "message": f"{name} has hairlines (lines set to 0 pt wide), which print as thin as "
                                         f"the printer can make them, or not at all"})
    summary = {"smallest_text_pt": round(smallest, 2) if smallest else None,
               "thinnest_line_pt": round(thinnest, 2) if thinnest is not None else None}
    top = []
    if smallest is not None and smallest < float(options.get("min_text_pt", 5.0)) - 0.005:
        top.append({"level": "warning", "message": f"smallest text is {smallest:.2f} pt "
                                                   f"(below {options.get('min_text_pt', 5.0)} pt)"})
    if thinnest is not None and thinnest < min_line - 0.005:
        top.append({"level": "warning", "message": f"thinnest line is {thinnest:.2f} pt (below {min_line:g} pt)"})
    found = top + found
    # De-duplicate messages
    seen = set()
    found = [f for f in found if not (f["message"] in seen or seen.add(f["message"]))]
    return {"items": found, "summary": summary}


def _sha_kind(var: dict):
    return var["sha256"], var["kind"]

"""Pre-export check: what a journal (or a careful co-author) would flag before submission."""
from __future__ import annotations

import ctypes
import math

from ..assets import get_cache, resolve_link
from ..model import iter_items
from ..resolve import DrawPicture, DrawText, Resolver, flat_prims

MIN_PHOTO_DPI = 300.0


def _pdf_text_sizes(path: str, page_index: int) -> list[float]:
    """Effective size (points) of every character on a PDF page."""
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


def preflight(doc: dict, options: dict) -> dict:
    cache = get_cache()
    pages = options.get("pages")
    sel = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
    resolver = Resolver(doc)
    found: list[dict] = []
    smallest = None
    min_dpi = float(options.get("min_dpi", MIN_PHOTO_DPI))
    text_cache: dict = {}
    for page in sel:
        pw, ph = float(page["width"]), float(page["height"])
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
            for prim in flat_prims(r.prims):   # pictures cropped to a shape are inside a group
                if isinstance(prim, DrawText):
                    for run in prim.runs:
                        if run.text.strip():
                            smallest = min(smallest or 1e9, run.size)
                elif isinstance(prim, DrawPicture):
                    asset = doc["assets"][prim.asset_id]
                    variants = asset["variants"]
                    scale = prim.scale
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
                            if abs(scale - 1.0) > 0.005:
                                found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                              "message": f"{name} is scaled to {scale * 100:.1f}%: its smallest "
                                                         f"text prints at {s:.2f} pt"})
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
                    prim_var = variants.get(asset.get("primary")) or next(iter(variants.values()))
                    if prim_var.get("src") and not resolve_link(prim_var, None):
                        found.append({"level": "info", "item": item.get("id"), "page": page["id"],
                                      "message": f"{name}: linked file not found; using the copy stored "
                                                 f"in the document"})
    summary = {"smallest_text_pt": round(smallest, 2) if smallest else None}
    if smallest is not None and smallest < float(options.get("min_text_pt", 5.0)) - 0.005:
        found.insert(0, {"level": "warning", "message": f"smallest text is {smallest:.2f} pt "
                                                        f"(below {options.get('min_text_pt', 5.0)} pt)"})
    # De-duplicate messages
    seen = set()
    found = [f for f in found if not (f["message"] in seen or seen.add(f["message"]))]
    return {"items": found, "summary": summary}


def _sha_kind(var: dict):
    return var["sha256"], var["kind"]

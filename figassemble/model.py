"""The document model: plain JSON shared by the editor, the engine and .figasm files.

Coordinates are points (1/72 in) on the page, origin top-left, y down. Every item has an
`id` and a `type`:

- picture  {asset, page_index, frame [x, y, w, h], crop [l, t, r, b] (fractions), rot,
            flip_h, flip_v, opacity, source: auto|pdf|svg|png}
- shape    {geom (DrawingML preset name or "custom"), adj, frame, rot, flip_h, flip_v,
            stroke, fill, arrow_start, arrow_end, path (custom), text, textbox}
- line     {points [[x, y], ...], stroke, arrow_start, arrow_end}
- group    {items: [...]}   children keep page coordinates

stroke {color, width, dash (preset or list of widths), cap: flat|round|square,
        join: round|miter|bevel, opacity}
fill   {color, opacity}
text   {paragraphs: [{align: l|ctr|r, line_spacing {pct} | {pts}, space_before,
        space_after, end_size, runs: [{t, font, size, bold, italic, color, baseline,
        underline}]}], insets [l, t, r, b], wrap, anchor: t|ctr|b, autofit: none|shape}
"""
from __future__ import annotations

import copy
import time

from .assets import new_id

FORMAT_VERSION = 1
MM = 72.0 / 25.4

# Page presets (points); Nature's double column is 180 mm wide
PAGE_PRESETS = {
    "Journal double column (180 x 170 mm)": (180 * MM, 170 * MM),
    "Journal single column (88 x 120 mm)": (88 * MM, 120 * MM),
    "US Letter": (612.0, 792.0),
    "A4": (210 * MM, 297 * MM),
    "Slide 16:9 (13.33 x 7.5 in)": (960.0, 540.0),
}
DEFAULT_PAGE = (180 * MM, 170 * MM)

DEFAULT_STROKE = {"color": "#000000", "width": 1.0, "dash": "solid", "cap": "round", "join": "round", "opacity": 1.0}
DEFAULT_TEXT_RUN = {"font": "Helvetica", "size": 6.0, "bold": False, "italic": False, "color": "#000000"}


def new_page(name: str = "Page 1", width: float | None = None, height: float | None = None) -> dict:
    w, h = (width, height) if width and height else DEFAULT_PAGE
    return {"id": new_id("pg"), "name": name, "width": w, "height": h, "background": None,
            "guides": {"x": [], "y": []}, "items": []}


def new_document(title: str = "Untitled figure") -> dict:
    now = time.time()
    return {
        "figassemble": FORMAT_VERSION,
        "meta": {"title": title, "created": now, "modified": now},
        "settings": {"units": "pt", "page_units": "mm"},
        "assets": {},
        "pages": [new_page()],
    }


def picture_item(asset_id: str, asset: dict, x: float, y: float, page_index: int = 0) -> dict:
    """A picture at true size (100%) with its top-left corner at (x, y)."""
    sizes = asset.get("page_sizes")
    w, h = sizes[page_index] if sizes else asset["size_pt"]
    return {"id": new_id("it"), "type": "picture", "name": asset.get("name", ""), "asset": asset_id,
            "page_index": page_index, "frame": [x, y, w, h], "crop": [0.0, 0.0, 0.0, 0.0],
            "rot": 0.0, "flip_h": False, "flip_v": False, "opacity": 1.0, "source": "auto"}


def text_item(text: str, x: float, y: float, size: float = 6.0, bold: bool = False, **run) -> dict:
    r = dict(DEFAULT_TEXT_RUN, t=text, size=size, bold=bold, **run)
    return {"id": new_id("it"), "type": "shape", "geom": "rect", "textbox": True, "frame": [x, y, 20.0, 10.0],
            "rot": 0.0, "stroke": None, "fill": None,
            "text": {"paragraphs": [{"align": "l", "runs": [r]}], "insets": [0.0, 0.0, 0.0, 0.0],
                     "wrap": False, "anchor": "t", "autofit": "shape"}}


def iter_items(items):
    """All items depth-first, groups included."""
    for it in items:
        yield it
        if it.get("type") == "group":
            yield from iter_items(it.get("items", []))


def used_assets(doc: dict) -> set[str]:
    return {it["asset"] for page in doc.get("pages", []) for it in iter_items(page.get("items", []))
            if it.get("type") == "picture"}


def validate(doc: dict) -> list[str]:
    """Problems that would stop the document from loading or exporting."""
    problems = []
    if doc.get("figassemble") != FORMAT_VERSION:
        problems.append(f"unsupported document version {doc.get('figassemble')!r}")
    assets = doc.get("assets", {})
    for page in doc.get("pages", []):
        if not page.get("width") or not page.get("height"):
            problems.append(f"page {page.get('name')!r} has no size")
        for it in iter_items(page.get("items", [])):
            if it.get("type") == "picture" and it.get("asset") not in assets:
                problems.append(f"picture {it.get('name') or it.get('id')} refers to a missing asset")
    return problems


def clone(doc: dict) -> dict:
    return copy.deepcopy(doc)

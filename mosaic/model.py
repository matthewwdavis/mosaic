"""The document model: plain JSON shared by the editor, the engine and .mosaic files.

Coordinates are points (1/72 in) on the page, origin top-left, y down. A page is {id, name,
width, height, background, preset, guides, items}; guides {x: [...], y: [...]} are the positions
of its vertical and horizontal guides, which help with lining things up and are never exported.
Every item has an `id` and a `type`:

- picture  {asset, page_index, frame [x, y, w, h], crop [l, t, r, b] (fractions), rot,
            flip_h, flip_v, opacity, source: auto|pdf|svg|png, mask {geom, adj, rounding}: cropped to
            that shape, fitted to the frame (geom custom: path {subpaths} and even_odd, the outline
            of a shape drawn over it, in the frame's own points); border {color, width, swatch};
            scale (see scalebar); inset {box}: a zoom inset showing what's in that box (zoom.js); picture_kind:
            photo|combination|line_art, for journals' resolution rules (guessed when absent,
            picturekind.py)}
            A zoom inset's box is a shape with zoom {picture, seen}, and its two lines have zoomline
            {box, inset, which}; the editor keeps the three in step
- shape    {geom (DrawingML preset name or "custom"), adj, frame, rot, flip_h, flip_v,
            stroke, fill, arrow_start, arrow_end, path (custom), text, textbox, outline, rounding}
- line     {points [[x, y], ...], curve: straight|smooth, stroke, arrow_start, arrow_end, outline,
            start_link, end_link}: a link {item, site} attaches that end to another object's
            connection point (connect.py), and the editor keeps the end there
- scalebar {picture, length, unit, frame, anchor {corner: tl|tr|bl|br, dx, dy}, thickness, size,
            label: above|below|none, color, swatch, bold}: a bar `length` long on its picture, which
            has scale {per_pt, unit, how}: the real length of one point of its source. The editor
            keeps the frame in step with the picture (scalebar.js); the engine draws the frame
- bracket  {frame, label, dir: up|down|left|right (the label's side), tick (upright ones), size, font,
            bold, color, swatch, line_width}: a significance bracket; across, its ticks are as long
            as the frame leaves below (or above) the label's room (resolve._bracket)
- group    {items: [...], clip, rot}   children keep page coordinates; with clip true it's a clipping
            mask: its last item, a shape, clips the others and isn't drawn. rot: how far the group
            has turned as a whole since it was made (degrees clockwise), for the editor's Rotation
            field only; its children already carry the turn, so nothing draws it

adj     {name: value}: a preset's adjust values as fractions, or degrees for angles (presets.py)
rounding 0..1: corner rounding of a shape's straight-edged corners (1 = as round as fits)
fill_reach inner|outer: a shape's or area fill's fill stops at its lines' inner edge, or reaches
        their outer edge, rather than their middle (absent); shows through dashed, dotted or
        see-through lines (fillreach.py)
arrow_start, arrow_end {type: triangle|stealth|arrow|oval|diamond, w, len: sm|med|lg, rounding 0..1}
outline {color, width, opacity, type}: a contour of `width` points in another colour around
        everything the item draws; its opacity applies to the contour as a whole. type:
        outside (default; underneath, so it shows only outside a filled shape), both (round
        the line on both sides, over the fill), outside_gaps (underneath, leaving a dashed
        line's gaps empty), both_filled (both sides, running on through a dashed line's gaps),
        inside / inside_gaps (outside / outside_gaps kept to the shape's area, over the fill),
        outside_only / outside_only_gaps (outside / outside_gaps kept off the area of an
        unfilled shape too); the editor offers these as Sides and Gaps (resolve.with_outline)

swatches (on the document) [{id, name, color}]: named colours. A colour picked from one (a stroke,
        fill, outline, gradient stop or text run) carries swatch: id beside its color, and the
        editor recolours it when the swatch changes; only color is drawn
stroke {color, width, dash (preset or list of widths), cap: flat|round|square,
        join: round|miter|bevel, opacity, even_dashes: false for PowerPoint's dash spacing
        (absent or true: a dash on every corner and end, evenly spaced; dashes.py),
        dash_spacing: the gaps between dashes and dots as a multiple of the style's (absent: 1;
        0.5 twice as dense)}
fill   {color, opacity}
text_styles (on the document) [{id, name, font, size, bold, italic, underline, color, swatch, align,
        line_spacing, space_before, space_after}]: named text formats; a paragraph using one has
        style: id and its runs keep the format themselves (the editor updates them)
text   {paragraphs: [{align: l|ctr|r, line_spacing {pct} | {pts}, space_before,
        space_after, end_size, runs: [{t, font, size, bold, italic, color, baseline,
        underline}]}], insets [l, t, r, b], wrap, anchor: t|ctr|b, autofit: none|shape}
"""
from __future__ import annotations

import copy
import time

from .assets import new_id
from .journals import DEFAULT_SIZE, preset_size, standard_size

FORMAT_VERSION = 1
MM = 72.0 / 25.4

# New pages are a normal sheet of paper; journal sizes are chosen per page (see journals.py)
DEFAULT_PAGE = standard_size(DEFAULT_SIZE)

DEFAULT_STROKE = {"color": "#000000", "width": 1.0, "dash": "solid", "cap": "round", "join": "round", "opacity": 1.0}
DEFAULT_TEXT_RUN = {"font": "Helvetica", "size": 6.0, "bold": False, "italic": False, "color": "#000000"}


def new_page(name: str = "Page 1", width: float | None = None, height: float | None = None,
             preset: dict | None = None) -> dict:
    """A blank page: width x height points, else the size a preset names (journals.preset_size),
    else A4."""
    page = {"id": new_id("pg"), "name": name, "background": None, "guides": {"x": [], "y": []}, "items": []}
    size = preset_size(preset) if preset else None
    if width and height:
        page["width"], page["height"] = width, height
    elif size:
        page["width"], page["height"] = size
        page["preset"] = ({"standard": preset["standard"]} if preset.get("standard")
                          else {"journal": preset["journal"], "type": preset["type"]})
    else:
        page["width"], page["height"] = DEFAULT_PAGE
        page["preset"] = {"standard": DEFAULT_SIZE}
    return page


def new_document(title: str = "Untitled figure", page: dict | None = None) -> dict:
    """A blank document of one page, the size the preset `page` names ({"standard": "Slide 16:9"},
    say), else A4."""
    now = time.time()
    return {
        "mosaic": FORMAT_VERSION,
        "meta": {"title": title, "created": now, "modified": now},
        "settings": {"units": "pt", "page_units": "mm"},
        "assets": {},
        "pages": [new_page(preset=page)],
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
    if doc.get("mosaic") != FORMAT_VERSION:
        problems.append(f"unsupported document version {doc.get('mosaic')!r}")
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

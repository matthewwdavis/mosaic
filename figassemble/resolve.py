"""Turn document items into drawing primitives in page coordinates.

Every writer (PDF, SVG, PNG/TIFF) and the editor preview draw these primitives, so all
outputs share one geometry and one text layout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .fonts import FontIndex
from .geometry import (OPEN_PRESETS, DrawPath, Fill, Matrix, Path, Stroke, arrowhead, dash_array,
                       frame_matrix, preset_paths, preset_text_rect)
from .textlayout import GlyphRun, TextLayout, layout_text


@dataclass
class DrawText:
    runs: list[GlyphRun]
    matrix: Matrix            # frame-local coordinates -> page
    meta: dict = field(default_factory=dict)

    def bbox(self) -> tuple[float, float, float, float] | None:
        pts = []
        for r in self.runs:
            top, bottom = r.y - r.face.ascent * r.size, r.y + r.face.descent * r.size
            for x, y in ((r.x, top), (r.x + r.width, top), (r.x, bottom), (r.x + r.width, bottom)):
                pts.append(self.matrix.apply(x, y))
        if not pts:
            return None
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class DrawPicture:
    asset_id: str
    page_index: int
    src_size: tuple[float, float]               # displayed size of the source page/image, points
    crop: tuple[float, float, float, float]     # visible source box x0, y0, x1, y1 (points, top-left origin)
    matrix: Matrix                              # source coordinates -> page
    opacity: float = 1.0
    source: str = "auto"                        # which variant to export from: auto | pdf | svg | png
    meta: dict = field(default_factory=dict)

    def corners(self) -> list[tuple[float, float]]:
        x0, y0, x1, y1 = self.crop
        return [self.matrix.apply(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    def bbox(self) -> tuple[float, float, float, float]:
        c = self.corners()
        xs, ys = [p[0] for p in c], [p[1] for p in c]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def scale(self) -> float:
        return self.matrix.scale_factor


@dataclass
class Resolved:
    item_id: str
    prims: list = field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    autofit_frame: list[float] | None = None    # frame an auto-fitted text box should take
    warnings: list[str] = field(default_factory=list)


def union_bbox(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def make_stroke(d: dict | None) -> Stroke | None:
    if not d:
        return None
    width = float(d.get("width", 1.0))
    if width <= 0:
        return None
    cap = d.get("cap", "flat")
    return Stroke(color=d.get("color", "#000000"), width=width,
                  dash=dash_array(d.get("dash", "solid"), width, cap), cap=cap,
                  join=d.get("join", "round"), opacity=float(d.get("opacity", 1.0)))


def make_fill(d: dict | None) -> Fill | None:
    if not d:
        return None
    return Fill(color=d.get("color", "#000000"), opacity=float(d.get("opacity", 1.0)),
                even_odd=bool(d.get("even_odd", False)))


def line_end_trim(spec: dict, width: float) -> float:
    """How far a line is shortened under an arrowhead (calibrated against PowerPoint)."""
    if not spec or spec.get("type") in (None, "none", "arrow", "oval", "diamond"):
        return 0.0
    from .geometry import ARROW_MIN_BASE_WIDTH, ARROW_SIZE
    length = ARROW_SIZE.get(spec.get("len", "med"), 3.0) * max(width, ARROW_MIN_BASE_WIDTH)
    if spec.get("type") == "stealth":
        return max(length * 0.5 - width / 2, 0.0)
    return max(length - width, 0.0)


def stroke_with_ends(path: Path, stroke: Stroke, start: dict | None, end: dict | None) -> list[DrawPath]:
    """An open path with optional line ends: the (shortened) line plus its heads."""
    out: list[DrawPath] = []
    heads: list[DrawPath] = []
    original = path
    trim_s = line_end_trim(start, stroke.width) if start else 0.0
    trim_e = line_end_trim(end, stroke.width) if end else 0.0
    body = path.trimmed(trim_s, trim_e) if (trim_s or trim_e) else path
    head_fill = Fill(color=stroke.color, opacity=stroke.opacity)
    head_stroke = Stroke(color=stroke.color, width=stroke.width, cap=stroke.cap, join="miter",
                         opacity=stroke.opacity)
    for spec, at_end in ((start, False), (end, True)):
        if not spec or spec.get("type") in (None, "none"):
            continue
        tan = original.end_tangent() if at_end else original.start_tangent()
        if tan is None:
            continue
        tip, direction = tan
        # The head points along the chord from where the line now stops to the tip
        stop = (body.end_tangent() if at_end else body.start_tangent())
        if stop is not None and (trim_e if at_end else trim_s) > 0:
            dx, dy = tip[0] - stop[0][0], tip[1] - stop[0][1]
            n = math.hypot(dx, dy)
            if n > 1e-9:
                direction = (dx / n, dy / n)
        for sp in arrowhead(tip, direction, stroke.width, spec)[0]:
            heads.append(DrawPath(sp.path, stroke=head_stroke if sp.stroke else None,
                                  fill=head_fill if sp.fill else None, meta={"role": "line-end"}))
    if not body.is_empty:
        out.append(DrawPath(body, stroke=stroke))
    return out + heads


class Resolver:
    """Resolves items of one document; needs asset sizes and the font index."""

    def __init__(self, doc: dict, fonts: FontIndex | None = None):
        self.doc = doc
        self.fonts = fonts

    def asset_size(self, asset_id: str, page_index: int = 0) -> tuple[float, float]:
        asset = self.doc.get("assets", {}).get(asset_id) or {}
        sizes = asset.get("page_sizes")
        if sizes and 0 <= page_index < len(sizes):
            return tuple(sizes[page_index])
        return tuple(asset.get("size_pt") or (100.0, 100.0))

    def resolve(self, item: dict) -> Resolved:
        kind = item.get("type")
        if kind == "picture":
            r = self._picture(item)
        elif kind == "shape":
            r = self._shape(item)
        elif kind == "line":
            r = self._line(item)
        elif kind == "group":
            r = Resolved(item.get("id", ""))
            for child in item.get("items", []):
                if child.get("hidden"):
                    continue
                cr = self.resolve(child)
                r.prims += cr.prims
                r.warnings += cr.warnings
        else:
            r = Resolved(item.get("id", ""), warnings=[f"unknown item type {kind!r}"])
        r.bbox = union_bbox(p.bbox() for p in r.prims)
        return r

    def resolve_page(self, page: dict) -> list[Resolved]:
        return [self.resolve(it) for it in page.get("items", []) if not it.get("hidden")]

    # Items ------------------------------------------------------------------------

    def _picture(self, item: dict) -> Resolved:
        r = Resolved(item.get("id", ""))
        page_index = int(item.get("page_index", 0))
        sw, sh = self.asset_size(item["asset"], page_index)
        l, t, rr, b = item.get("crop") or (0.0, 0.0, 0.0, 0.0)
        x0, y0, x1, y1 = l * sw, t * sh, sw - rr * sw, sh - b * sh
        x, y, w, h = item["frame"]
        if x1 - x0 <= 0 or y1 - y0 <= 0 or w <= 0 or h <= 0:
            r.warnings.append("picture is cropped or sized to nothing")
            return r
        m = (frame_matrix(item["frame"], item.get("rot", 0.0), item.get("flip_h", False), item.get("flip_v", False))
             @ Matrix.scale(w / (x1 - x0), h / (y1 - y0)) @ Matrix.translate(-x0, -y0))
        r.prims.append(DrawPicture(item["asset"], page_index, (sw, sh), (x0, y0, x1, y1), m,
                                   float(item.get("opacity", 1.0)), item.get("source", "auto"),
                                   meta={"item": item.get("id")}))
        return r

    def _shape(self, item: dict) -> Resolved:
        r = Resolved(item.get("id", ""))
        x, y, w, h = item["frame"]
        m = frame_matrix(item["frame"], item.get("rot", 0.0), item.get("flip_h", False), item.get("flip_v", False))
        geom = item.get("geom", "rect")
        stroke = make_stroke(item.get("stroke"))
        fill = make_fill(item.get("fill"))
        if geom == "custom":
            shape_paths = custom_paths(item.get("path") or {}, w, h)
        else:
            shape_paths = preset_paths(geom, w, h, item.get("adj"))
        has_ends = bool(item.get("arrow_start") or item.get("arrow_end"))
        for sp in shape_paths:
            path = sp.path.transformed(m)
            if sp.fill and fill is not None and not path.is_empty:
                r.prims.append(DrawPath(path, fill=fill))
            if sp.stroke and stroke is not None and not path.is_empty:
                open_path = not sp.path.is_closed() and (geom in OPEN_PRESETS or geom == "custom")
                if open_path and has_ends:
                    r.prims += stroke_with_ends(path, stroke, item.get("arrow_start"), item.get("arrow_end"))
                else:
                    r.prims.append(DrawPath(path, stroke=stroke))
        body = item.get("text")
        if body and body.get("paragraphs"):
            tx0, ty0, tx1, ty1 = preset_text_rect(geom, w, h, item.get("adj"))
            layout = layout_text(body, tx1 - tx0, ty1 - ty0, self.fonts)
            if layout.runs:
                r.prims.append(DrawText(layout.runs, m @ Matrix.translate(tx0, ty0), meta={"item": item.get("id")}))
            if body.get("autofit") == "shape":
                new_h = layout.autofit_height + (h - (ty1 - ty0))
                new_w = w if body.get("wrap", True) else layout.autofit_width + (w - (tx1 - tx0))
                if abs(new_h - h) > 0.005 or abs(new_w - w) > 0.005:
                    r.autofit_frame = [x, y, new_w, new_h]
        return r

    def _line(self, item: dict) -> Resolved:
        r = Resolved(item.get("id", ""))
        pts = item.get("points") or []
        stroke = make_stroke(item.get("stroke"))
        if len(pts) < 2 or stroke is None:
            return r
        path = Path().move_to(*pts[0])
        for p in pts[1:]:
            path.line_to(*p)
        r.prims += stroke_with_ends(path, stroke, item.get("arrow_start"), item.get("arrow_end"))
        return r


def custom_paths(spec: dict, w: float, h: float):
    """Freeform paths stored in their own coordinate space, scaled to the frame."""
    from .geometry import ShapePath
    out = []
    for sub in spec.get("subpaths", []):
        pw = float(sub.get("w") or w) or 1.0
        ph = float(sub.get("h") or h) or 1.0
        # Build in the path's own units (arc angles are defined there), then scale to the frame
        p = Path()
        for cmd in sub.get("cmds", []):
            op, vals = cmd[0], cmd[1:]
            if op == "M":
                p.move_to(vals[0], vals[1])
            elif op == "L":
                p.line_to(vals[0], vals[1])
            elif op == "C":
                p.curve_to(*vals[:6])
            elif op == "Q":
                p.quad_to(*vals[:4])
            elif op == "A":
                # DrawingML arcTo: radii, start angle, sweep angle (degrees)
                p.arc_to(vals[0], vals[1], vals[2], vals[3])
            elif op == "Z":
                p.close()
        out.append(ShapePath(p.transformed(Matrix.scale(w / pw, h / ph)),
                             fill=sub.get("fill", True), stroke=sub.get("stroke", True)))
    return out

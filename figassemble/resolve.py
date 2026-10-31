"""Turn document items into drawing primitives in page coordinates.

Every writer (PDF, SVG, PNG/TIFF) and the editor preview draw these primitives, so all
outputs share one geometry and one text layout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .fonts import FontIndex
from .geometry import (OPEN_PRESETS, DrawPath, Fill, Matrix, Path, Stroke, arrowhead, dash_array,
                       frame_matrix, linear_gradient, preset_paths, preset_text_rect)
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


def chord_point(path: Path, distance: float, from_end: bool):
    """First point along a path whose straight-line distance from its start (or end) is
    `distance`. Returns (point, arc length to it) or None if the path is too short."""
    p = path.reversed() if from_end else path
    from .geometry import _bezier_point
    start = cur = None
    walked = 0.0
    prev = None
    for s in p.segs:
        if s[0] == "M":
            start = cur = prev = (s[1], s[2])
            continue
        if s[0] == "L":
            samples = [(s[1], s[2])]
            # Lines may be long: subdivide so the crossing is found precisely
            n = 64
            samples = [(cur[0] + (s[1] - cur[0]) * k / n, cur[1] + (s[2] - cur[1]) * k / n) for k in range(1, n + 1)]
        elif s[0] == "C":
            bez = [cur, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])]
            samples = [_bezier_point(bez, k / 128) for k in range(1, 129)]
        else:
            continue
        for q in samples:
            dq = math.dist(q, start)
            if dq >= distance:
                # Interpolate within the last small step
                dp = math.dist(prev, start)
                t = (distance - dp) / (dq - dp) if dq > dp else 1.0
                pt = (prev[0] + (q[0] - prev[0]) * t, prev[1] + (q[1] - prev[1]) * t)
                return pt, walked + math.dist(prev, pt)
            walked += math.dist(prev, q)
            prev = q
        cur = (s[-2], s[-1])
    return None


def stroke_with_ends(path: Path, stroke: Stroke, start: dict | None, end: dict | None) -> list[DrawPath]:
    """An open path with optional line ends: the line plus its heads.

    PowerPoint's rule, measured from its own PDF export: a head points at the spot on the
    path one head-length from the tip, so it follows curves. The line is cut at that spot
    and continues straight along the head's axis, stopping one line-width short of the
    head's length so its cap stays hidden inside the head.
    """
    from .geometry import ARROW_MIN_BASE_WIDTH, ARROW_SIZE
    heads: list[DrawPath] = []
    head_fill = Fill(color=stroke.color, opacity=stroke.opacity)
    head_stroke = Stroke(color=stroke.color, width=stroke.width, cap=stroke.cap, join="miter",
                         opacity=stroke.opacity)
    body = path
    plan = []
    for spec, at_end in ((start, False), (end, True)):
        if not spec or spec.get("type") in (None, "none"):
            continue
        tan = path.end_tangent() if at_end else path.start_tangent()
        if tan is None:
            continue
        tip = tan[0]
        length = ARROW_SIZE.get(spec.get("len", "med"), 3.0) * max(stroke.width, ARROW_MIN_BASE_WIDTH)
        found = chord_point(path, length, from_end=at_end)
        if found is not None:
            q, arc = found
            ax = ((q[0] - tip[0]) / length, (q[1] - tip[1]) / length)   # from the tip into the path
        else:   # path shorter than the head: point along the end tangent
            travel = tan[1] if at_end else (-tan[1][0], -tan[1][1])
            ax, q, arc = (-travel[0], -travel[1]), None, 0.0
        plan.append((spec, at_end, tip, ax, q, arc, line_end_trim(spec, stroke.width)))
        for sp in arrowhead(tip, (-ax[0], -ax[1]), stroke.width, spec)[0]:
            heads.append(DrawPath(sp.path, stroke=head_stroke if sp.stroke else None,
                                  fill=head_fill if sp.fill else None, meta={"role": "line-end"}))
    # Cut the line under the heads that hide its end, and bridge to the head's axis
    cut_s = next(((tip, ax, q, arc, trim) for spec, at_end, tip, ax, q, arc, trim in plan
                  if not at_end and trim > 0 and q is not None), None)
    cut_e = next(((tip, ax, q, arc, trim) for spec, at_end, tip, ax, q, arc, trim in plan
                  if at_end and trim > 0 and q is not None), None)
    if cut_s or cut_e:
        body = path.trimmed(cut_s[3] if cut_s else 0.0, cut_e[3] if cut_e else 0.0)
        if cut_s:
            tip, ax, q, _arc, trim = cut_s
            stub = Path().move_to(tip[0] + ax[0] * trim, tip[1] + ax[1] * trim).line_to(*q)
            body = Path(stub.segs + [s for s in body.segs if s[0] != "M"][0:])
        if cut_e:
            tip, ax, q, _arc, trim = cut_e
            body = Path(body.segs + [("L", tip[0] + ax[0] * trim, tip[1] + ax[1] * trim)])
    out: list[DrawPath] = []
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
        if fill is not None and (item.get("fill") or {}).get("gradient"):
            fill.gradient = linear_gradient(item["fill"]["gradient"], w, h, m)
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
            # Like PowerPoint, text is never mirrored: a horizontal flip leaves it alone and a
            # vertical flip turns it 180 degrees
            tm = frame_matrix(item["frame"], item.get("rot", 0.0) + (180.0 if item.get("flip_v") else 0.0))
            if layout.runs:
                r.prims.append(DrawText(layout.runs, tm @ Matrix.translate(tx0, ty0), meta={"item": item.get("id")}))
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

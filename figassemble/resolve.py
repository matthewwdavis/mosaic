"""Turn document items into drawing primitives in page coordinates.

Every writer (PDF, SVG, PNG/TIFF) and the editor preview draw these primitives, so all
outputs share one geometry and one text layout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from . import dashes, presets
from .fonts import FontIndex
from .geometry import (DrawPath, Fill, Matrix, Path, Stroke, arrowhead, dash_array, frame_matrix, head_outline,
                       line_end_inside, make_gradient, round_shape_paths, sample_path, smooth_path)
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


@dataclass
class DrawGroup:
    """Primitives composited together, then faded as one (so overlaps don't darken)."""

    prims: list
    opacity: float = 1.0
    meta: dict = field(default_factory=dict)

    def bbox(self):
        return union_bbox(p.bbox() for p in self.prims)


def outline_prims(prims: list, spec: dict | None) -> list:
    """A contour of `spec["width"]` points in another colour around everything an item
    draws (lines, arrowheads, fills), to sit underneath it. Its transparency applies to the
    contour as a whole, so the outline of a line and of its head don't double up."""
    if not spec:
        return []
    t = float(spec.get("width", 1.0))
    if t <= 0:
        return []
    color = spec.get("color", "#ffffff")
    out = []
    for p in prims:
        if not isinstance(p, DrawPath):
            continue
        if p.stroke is not None:
            s = p.stroke
            path, dash = p.path, s.dash
            laid_out = p.meta.get("dashes")
            if laid_out:
                # The same dashes; flat ends don't grow with the width, so lengthen each by t
                layout, extend = laid_out
                path = layout.path(extend + (t if s.cap == "flat" else 0.0))
            elif s.cap == "flat" and not path.is_closed():
                # Flat ends don't grow with the width: continue the line by t at each end and
                # lengthen each dash by t either side (the gaps shrink to match)
                path = path.extended(t, t)
                if dash:
                    dash = [d + 2 * t if i % 2 == 0 else max(d - 2 * t, 0.0) for i, d in enumerate(dash)]
            out.append(DrawPath(path, stroke=Stroke(color=color, width=s.width + 2 * t, dash=dash, cap=s.cap,
                                                    join=s.join, miter_limit=s.miter_limit),
                                meta={"role": "outline"}))
        if p.fill is not None:
            out.append(DrawPath(p.path, stroke=Stroke(color=color, width=2 * t, cap="round", join="round"),
                                fill=Fill(color=color, even_odd=p.fill.even_odd), meta={"role": "outline"}))
    opacity = float(spec.get("opacity", 1.0))
    if out and opacity < 1.0:
        return [DrawGroup(out, opacity, meta={"role": "outline"})]
    return out


def _dashed(prim) -> bool:
    return isinstance(prim, DrawPath) and prim.stroke is not None and bool(prim.stroke.dash or prim.meta.get("dashes"))


def with_outline(prims: list, spec: dict | None) -> list:
    """An item's drawing with its outline (outline_prims) where the outline's type puts it:

    - "outside" (the default): underneath everything, so a filled shape's outline shows only
      outside it, and runs through the gaps of a dashed line along the fill's edge;
    - "both": around the line on both sides, between each fill and its line, so it shows inside
      a filled shape too, and only round the dashes of a dashed line;
    - "outside_gaps": underneath, like "outside", but leaving the gaps of a dashed line empty
      (no band along the fill's edge).

    A shape with no line has only its outside to outline, whatever the type."""
    if not spec or float(spec.get("width", 1.0)) <= 0:
        return prims
    kind = spec.get("type", "outside")
    body = {id(p) for p in prims if isinstance(p, DrawPath) and p.fill is not None and p.meta.get("role") == "body"}
    strokes = {id(p) for p in prims if isinstance(p, DrawPath) and p.stroke is not None}
    if kind == "both" and body and strokes:
        # Arrowheads' outlines underneath; each line's outline over the fill drawn before it
        out = outline_prims([p for p in prims if id(p) not in body | strokes], spec)
        for p in prims:
            if id(p) in strokes:
                out += outline_prims([p], spec)
            out.append(p)
        return out
    if kind == "outside_gaps" and any(_dashed(p) for p in prims if id(p) in strokes):
        return outline_prims([p for p in prims if id(p) not in body], spec) + prims
    return outline_prims(prims, spec) + prims


def make_stroke(d: dict | None) -> Stroke | None:
    if not d:
        return None
    width = float(d.get("width", 1.0))
    if width <= 0:
        return None
    cap = d.get("cap", "flat")
    return Stroke(color=d.get("color", "#000000"), width=width,
                  dash=dash_array(d.get("dash", "solid"), width, cap), cap=cap,
                  join=d.get("join", "round"), opacity=float(d.get("opacity", 1.0)),
                  even_dashes=d.get("even_dashes", True) is not False)


def even_dashes(prim):
    """A dashed stroke with its dashes laid out to fit corners and ends (dashes.py), drawn
    solid; the layout stays in meta for outlines. Square caps become flat ones on dashes
    lengthened by half the width, which PDF and SVG draw alike even for dots."""
    s = getattr(prim, "stroke", None)
    if not isinstance(prim, DrawPath) or s is None or not s.dash or not s.even_dashes or prim.fill is not None:
        return prim
    layout = dashes.layout(prim.path, s.dash)
    if layout is None:
        return prim
    extend = s.width / 2 if s.cap == "square" else 0.0
    stroke = replace(s, dash=None, dash_phase=0.0, cap="flat" if s.cap == "square" else s.cap)
    return DrawPath(layout.path(extend), stroke=stroke, meta={**prim.meta, "dashes": (layout, extend)})


def make_fill(d: dict | None) -> Fill | None:
    if not d:
        return None
    return Fill(color=d.get("color", "#000000"), opacity=float(d.get("opacity", 1.0)),
                even_odd=bool(d.get("even_odd", False)))


# DrawingML's darker and lighter faces (a cube's sides, a cylinder's top): (keep, towards)
_SHADES = {"darken": (0.6, 0.0), "darkenLess": (0.8, 0.0), "lighten": (0.6, 1.0), "lightenLess": (0.8, 1.0)}


def shaded(fill: Fill, mode: str | None) -> Fill:
    if mode not in _SHADES or fill.gradient is not None or not fill.color.startswith("#") or len(fill.color) != 7:
        return fill
    keep, toward = _SHADES[mode]
    rgb = [int(fill.color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    color = "#" + "".join(f"{round((c * keep + toward * (1 - keep)) * 255):02x}" for c in rgb)
    return Fill(color=color, opacity=fill.opacity, even_odd=fill.even_odd)


def line_end_trim(spec: dict, width: float, cap: str = "round") -> float:
    """How far a line is shortened under an arrowhead (calibrated against PowerPoint).

    A rounded head slides forward to keep its tip on the end point, and the line's end moves
    with it, as far back as it needs to stay hidden inside the head."""
    if not spec or spec.get("type") in (None, "none", "arrow", "oval", "diamond"):
        return 0.0
    from .geometry import head_size
    length = head_size(spec, width)[1]
    if spec.get("type") == "stealth":
        trim = max(length * 0.5 - width / 2, 0.0)
    else:
        trim = max(length - width, 0.0)
    if spec.get("rounding"):
        outline, shift = head_outline(spec, width)
        cap_reach = width / 2 * (math.sqrt(2) if cap == "square" else 1.0)
        trim = line_end_inside(outline, max(trim - shift, 0.0), cap_reach, length)
    return trim


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
        plan.append((spec, at_end, tip, ax, q, arc, line_end_trim(spec, stroke.width, stroke.cap)))
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
            fill.gradient = make_gradient(item["fill"]["gradient"], w, h, m)
        if geom == "custom":
            shape_paths = custom_paths(item.get("path") or {}, w, h)
        else:
            shape_paths = presets.shape_paths(geom, w, h, item.get("adj"))
        if item.get("rounding"):
            shape_paths = round_shape_paths(shape_paths, item["rounding"])
        has_ends = bool(item.get("arrow_start") or item.get("arrow_end"))
        for sp in shape_paths:
            path = sp.path.transformed(m)
            if sp.fill and fill is not None and not path.is_empty:
                r.prims.append(DrawPath(path, fill=shaded(fill, sp.shade), meta={"role": "body"}))
            if sp.stroke and stroke is not None and not path.is_empty:
                open_path = not sp.path.is_closed() and (presets.is_open(geom) or geom == "custom")
                if open_path and has_ends:
                    r.prims += stroke_with_ends(path, stroke, item.get("arrow_start"), item.get("arrow_end"))
                else:
                    r.prims.append(DrawPath(path, stroke=stroke))
        r.prims = with_outline([even_dashes(p) for p in r.prims], item.get("outline"))
        body = item.get("text")
        if body and body.get("paragraphs"):
            tx0, ty0, tx1, ty1 = presets.text_rect(geom, w, h, item.get("adj"))
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
        if item.get("curve") == "smooth" and len(pts) >= 3:
            path = smooth_path(pts)   # passes through every point
        else:
            path = Path().move_to(*pts[0])
            for p in pts[1:]:
                path.line_to(*p)
        drawn = [even_dashes(p) for p in stroke_with_ends(path, stroke, item.get("arrow_start"), item.get("arrow_end"))]
        r.prims += with_outline(drawn, item.get("outline"))
        return r


def shape_to_curve(item: dict, assets: dict | None = None) -> dict:
    """Turn an open shape (an arc, e.g. a curved arrow from PowerPoint) into a line whose
    points can be dragged: a smooth curve through points spread along the original."""
    plain = dict(item, arrow_start=None, arrow_end=None)
    r = Resolver({"assets": assets or {}}).resolve(plain)
    strokes = [p for p in r.prims if isinstance(p, DrawPath) and p.stroke is not None]
    if not strokes:
        raise ValueError("this shape has no line to turn into a curve")
    path = strokes[0].path
    if item.get("geom") == "arc":
        adj = item.get("adj") or {}
        sweep = (adj.get("adj2", 0.0) - adj.get("adj1", 270.0)) % 360.0 or 360.0
        n = 3 if sweep <= 90 else 1 + math.ceil(sweep / 60.0)
    else:
        bb = path.bbox()
        n = max(3, min(12, 2 + round(math.hypot(bb[2] - bb[0], bb[3] - bb[1]) / 40.0))) if bb else 3
    out = {"id": item.get("id"), "type": "line", "name": item.get("name", ""), "points": sample_path(path, n),
           "curve": "smooth", "stroke": item.get("stroke"), "arrow_start": item.get("arrow_start"),
           "arrow_end": item.get("arrow_end")}
    for key in ("hidden", "locked", "alt"):
        if key in item:
            out[key] = item[key]
    return out


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

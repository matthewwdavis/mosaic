"""Pathfinder, as in Illustrator: shapes combined into one new freeform shape (unite, minus front,
intersect, exclude), keeping exact curves (skia-pathops does the geometry)."""
from __future__ import annotations

import copy

import pathops

from .geometry import Path
from .regions import custom_path
from .resolve import item_area

OPS = {"unite": pathops.PathOp.UNION, "intersect": pathops.PathOp.INTERSECTION, "exclude": pathops.PathOp.XOR}
STYLE_KEYS = ("fill", "stroke", "outline")


def _to_skia(area: list) -> pathops.Path:
    """A shape's area as one skia path: each part simplified under its own fill rule, then joined."""
    out = None
    for path, even_odd in area:
        part = pathops.Path(fillType=pathops.FillType.EVEN_ODD if even_odd else pathops.FillType.WINDING)
        for seg in path.segs:
            if seg[0] == "M":
                part.moveTo(*seg[1:])
            elif seg[0] == "L":
                part.lineTo(*seg[1:])
            elif seg[0] == "C":
                part.cubicTo(*seg[1:])
            elif seg[0] == "Z":
                part.close()
        part.simplify(fix_winding=True)
        out = part if out is None else pathops.op(out, part, pathops.PathOp.UNION)
    return out if out is not None else pathops.Path()


def _from_skia(p: pathops.Path) -> Path:
    out = Path()
    for verb, pts in p.segments:
        if verb == "moveTo":
            out.move_to(*pts[0])
        elif verb == "lineTo":
            out.line_to(*pts[0])
        elif verb == "curveTo":
            out.curve_to(*pts[0], *pts[1], *pts[2])
        elif verb == "qCurveTo":
            for (cx, cy), (x, y) in pathops.decompose_quadratic_segment(pts):
                out.quad_to(cx, cy, x, y)
        elif verb == "closePath":
            out.close()
    return out


def combine(items: list[dict], how: str) -> dict:
    """The shapes (bottom to top) as one freeform shape: unite, minus_front (the bottom one less
    the rest), intersect or exclude (what an odd number of them cover). It takes the top shape's
    style, or for minus front the bottom one's, as in Illustrator."""
    areas = [item_area(it) for it in items]
    if len(items) < 2 or any(a is None for a in areas):
        raise ValueError("Pathfinder combines two or more shapes")
    paths = [_to_skia(a) for a in areas]
    if how == "minus_front":
        front = paths[1]
        for p in paths[2:]:
            front = pathops.op(front, p, pathops.PathOp.UNION)
        result = pathops.op(paths[0], front, pathops.PathOp.DIFFERENCE)
    elif how in OPS:
        result = paths[0]
        for p in paths[1:]:
            result = pathops.op(result, p, OPS[how])
    else:
        raise ValueError(f"unknown Pathfinder operation {how!r}")
    path = _from_skia(result)
    box = path.bbox() if path.segs else None
    if not box or box[2] - box[0] <= 1e-6 or box[3] - box[1] <= 1e-6:
        raise ValueError("Nothing is left: the shapes don't overlap that way")
    frame = [box[0], box[1], box[2] - box[0], box[3] - box[1]]
    style = items[0] if how == "minus_front" else items[-1]
    shape = {"type": "shape", "geom": "custom", "frame": frame, "rot": 0.0, "flip_h": False, "flip_v": False,
             "path": custom_path(path, frame, stroke=True)}
    for k in STYLE_KEYS:
        if k in style:
            shape[k] = copy.deepcopy(style[k])
    return shape

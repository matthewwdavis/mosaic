"""Pathfinder, as in Illustrator: shapes combined into one new freeform shape (unite, minus front,
intersect, exclude), keeping exact curves (skia-pathops does the geometry)."""
from __future__ import annotations

import copy

import pathops

from .fillreach import from_skia as _from_skia, to_skia as _to_skia
from .regions import custom_path
from .resolve import item_area

OPS = {"unite": pathops.PathOp.UNION, "intersect": pathops.PathOp.INTERSECTION, "exclude": pathops.PathOp.XOR}
STYLE_KEYS = ("fill", "stroke", "outline")


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

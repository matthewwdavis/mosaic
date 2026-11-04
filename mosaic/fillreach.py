"""Where a fill stops against its lines: their middle (as anything is drawn, the default), their
inner edge, or their outer edge. It shows only where the lines don't hide the fill's edge: in the
gaps of dashed and dotted lines, or through see-through ones. skia-pathops traces each line's
outline exactly, curves and all (Pathfinder uses the same conversions)."""
from __future__ import annotations

import pathops

from .geometry import Path

REACHES = ("inner", "outer")   # (and "middle", the default, stored as nothing)
_CAPS = {"flat": pathops.LineCap.BUTT_CAP, "round": pathops.LineCap.ROUND_CAP, "square": pathops.LineCap.SQUARE_CAP}
_JOINS = {"miter": pathops.LineJoin.MITER_JOIN, "round": pathops.LineJoin.ROUND_JOIN, "bevel": pathops.LineJoin.BEVEL_JOIN}


def _raw(path: Path, even_odd: bool = False) -> pathops.Path:
    out = pathops.Path(fillType=pathops.FillType.EVEN_ODD if even_odd else pathops.FillType.WINDING)
    for seg in path.segs:
        if seg[0] == "M":
            out.moveTo(*seg[1:])
        elif seg[0] == "L":
            out.lineTo(*seg[1:])
        elif seg[0] == "C":
            out.cubicTo(*seg[1:])
        elif seg[0] == "Z":
            out.close()
    return out


def to_skia(area: list) -> pathops.Path:
    """A shape's area as one skia path: each part simplified under its own fill rule, then joined."""
    out = None
    for path, even_odd in area:
        part = _raw(path, even_odd)
        part.simplify(fix_winding=True)
        out = part if out is None else pathops.op(out, part, pathops.PathOp.UNION)
    return out if out is not None else pathops.Path()


def from_skia(p: pathops.Path) -> Path:
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


def _covered(path: Path, width: float, cap: str, join: str, miter_limit: float) -> pathops.Path:
    """What a line of this width covers, whole (its dashes left out), as an area."""
    out = _raw(path)
    out.stroke(width, _CAPS.get(cap, pathops.LineCap.BUTT_CAP), _JOINS.get(join, pathops.LineJoin.ROUND_JOIN), max(miter_limit, 1.0))
    out.simplify(fix_winding=True)
    return out


def reach(area: list, lines: list, where: str | None) -> Path | None:
    """A fill's area [(path, even_odd)] stopping at its lines' inner edge (less what the lines
    cover), or reaching their outer edge (with what they cover beside it, not where a line runs on
    past the area). lines: [(path, stroke)]. None when it stays as it is (the middle)."""
    lines = [(p, s) for p, s in lines if s is not None and s.width > 0 and not p.is_empty]
    if where not in REACHES or not lines:
        return None
    fill, cover = to_skia(area), None
    for path, s in lines:
        c = _covered(path, s.width, s.cap, s.join, s.miter_limit)
        cover = c if cover is None else pathops.op(cover, c, pathops.PathOp.UNION)
    if where == "inner":
        return from_skia(pathops.op(fill, cover, pathops.PathOp.DIFFERENCE))
    beside = None   # the area grown by the widest line's half width: what it reaches into
    for path, _ in area:
        g = _covered(path, max(s.width for _, s in lines), "flat", "miter", 10.0)
        beside = g if beside is None else pathops.op(beside, g, pathops.PathOp.UNION)
    beside = pathops.op(beside, fill, pathops.PathOp.UNION)
    return from_skia(pathops.op(pathops.op(fill, cover, pathops.PathOp.UNION), beside, pathops.PathOp.INTERSECTION))

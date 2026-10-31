"""Connection points: where line and arrow ends can attach to an object.

A shape's points come from its own outline: its corners (sharp ones and the middles of rounded
ones) and the middle of each side between them; a smooth outline without corners, such as an
ellipse, gets 8 points round it, towards its frame's corners and side middles; an open outline
(an arc, a bracket) its two ends too. A dashed outline adds both ends and the middle of every
dash, so a line can meet it on a dash rather than in a gap.

Points are named so a connection survives resizing: "c3" corner 4, "m0" the middle of side 1,
"p5" point 6 of 8, "e0"/"e1" the ends, "d12s"/"d12m"/"d12e" dash 13's start, middle and end.
Shapes give them as fractions of their frame (before rotation), so the editor can follow a
resize at once; lines give their dashes' points on the page.
"""
from __future__ import annotations

from . import dashes, presets
from .geometry import dash_array, round_shape_paths


def shape_sites(item: dict) -> list[tuple[str, float, float]]:
    """(name, u, v): a shape's connection points as fractions of its frame's width and height."""
    _x, _y, w, h = item["frame"]
    if w <= 0 or h <= 0:
        return []
    path = _outline(item, w, h)
    if path is None:
        return []
    pts = outline_sites(path, w, h)
    stroke = item.get("stroke") or {}
    if stroke and stroke.get("even_dashes", True) is not False:
        layout = dashes.layout(path, dash_array(stroke.get("dash", "solid"), float(stroke.get("width", 1.0)),
                                                stroke.get("cap", "flat")))
        if layout is not None:
            pts += layout.sites()
    return [(key, x / w, y / h) for key, x, y in pts]


def outline_sites(path, w: float, h: float) -> list[tuple[str, float, float]]:
    """Corners, side middles and ends of an outline (its first subpath), in its own coordinates."""
    subs = dashes._subpaths(path)
    if not subs:
        return []
    sub = dashes._Sub(*subs[0])
    if sub.length <= 1e-9:
        return []
    corners = sub.corners()
    out = []
    if sub.closed and not corners:
        # Round a smooth outline, 8 points towards the frame's corners and side middles
        cx, cy = w / 2, h / 2
        for k, (fx, fy) in enumerate([(1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5), (0, 0), (0.5, 0), (1, 0)]):
            hit = _ray_hit(sub, (cx, cy), (fx * w - cx, fy * h - cy))
            if hit is not None:
                out.append((f"p{k}", *hit))
        return out
    for k, c in enumerate(corners):
        out.append((f"c{k}", *sub.point(c)))
    stops = corners if sub.closed else [0.0] + corners + [sub.length]
    if not sub.closed:
        out += [("e0", *sub.point(0.0)), ("e1", *sub.point(sub.length))]
    spans = list(zip(stops, stops[1:] + ([stops[0] + sub.length] if sub.closed else [])))
    for k, (a, b) in enumerate(spans):
        out.append((f"m{k}", *sub.point(((a + b) / 2) % sub.length if sub.closed else (a + b) / 2)))
    return out


def _outline(item: dict, w: float, h: float):
    """The path that outlines a shape: the first one drawn with a line (an arc's line, not its
    filled wedge), or else the first filled one."""
    from .resolve import custom_paths
    geom = item.get("geom", "rect")
    paths = custom_paths(item.get("path") or {}, w, h) if geom == "custom" else presets.shape_paths(geom, w, h, item.get("adj"))
    if item.get("rounding"):
        paths = round_shape_paths(paths, item["rounding"])
    drawn = [sp for sp in paths if not sp.path.is_empty]
    return next((sp.path for sp in drawn if sp.stroke), next((sp.path for sp in drawn if sp.fill), None))


def _ray_hit(sub, origin, direction):
    """Where a ray from inside an outline first crosses it."""
    run = dashes._Run(sub, 0.0, sub.length)
    best = None
    dx, dy = direction
    for (ax, ay), (bx, by) in zip(run.pts, run.pts[1:]):
        ex, ey = bx - ax, by - ay
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((ax - origin[0]) * ey - (ay - origin[1]) * ex) / den   # along the ray
        s = ((ax - origin[0]) * dy - (ay - origin[1]) * dx) / den   # along the segment
        if t > 1e-9 and -1e-9 <= s <= 1 + 1e-9 and (best is None or t < best):
            best = t
    return None if best is None else (origin[0] + dx * best, origin[1] + dy * best)


def line_sites(prims) -> list[tuple[str, float, float]]:
    """A dashed line's dash points, on the page (its ends and middle the editor works out). A
    see-through line is drawn in a group with its arrowheads (resolve.fade_together)."""
    for p in prims:
        inner = getattr(p, "prims", None)
        found = line_sites(inner) if inner is not None else None
        if found:
            return found
        laid_out = getattr(p, "meta", {}).get("dashes")
        if laid_out:
            return laid_out[0].sites()
    return []


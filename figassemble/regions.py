"""Area fills that follow their lines, like Illustrator's Live Paint: the space a set of lines
and shapes encloses, found again from their current geometry every time it's drawn.

An area fill is a shape with geom "region" and region {items: [the lines and shapes round it],
seed: [u, v]}, the seed being a point inside the area as fractions of those items' combined
box, so it moves and scales with them. Each time the area is found, the seed moves to a point
well inside it, ready for the next change.

Lines enclose an area along their centre lines; the fill is drawn behind them, so their width
covers its edge. An open line's ends reach a little past where they stop (half the line's
width and a bit), so lines that look joined close the area even with a hairline gap.
"""
from __future__ import annotations

import math

import shapely
from shapely import ops
from shapely.geometry import LineString, MultiLineString, Point, Polygon

from .geometry import Path, flatten
from .resolve import centre_paths

PER_CURVE = 24    # points along each curve segment
REACH = 0.25      # pt past half a line's width that an open line's ends reach
GRID = 1e-4       # pt: coordinates closer than this are the same point
TOUCH = 0.5       # pt of shared edge that makes an item part of an area's boundary


def _lines(item: dict) -> list[LineString]:
    out = []
    for path, width in centre_paths(item):
        for sub in path.subpaths():
            pts = flatten(sub, PER_CURVE)[0] if sub.segs else []
            pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > GRID]
            if len(pts) < 2:
                continue
            if sub.is_closed() or math.dist(pts[0], pts[-1]) <= GRID:
                if math.dist(pts[0], pts[-1]) > GRID:
                    pts.append(pts[0])
                if len(pts) >= 4:
                    out.append(LineString(pts))
                continue
            # An open line reaches a little past each end, to meet what it nearly touches
            reach = width / 2 + REACH
            def past(a, b):
                d = math.dist(a, b)
                return (a[0] + (a[0] - b[0]) / d * reach, a[1] + (a[1] - b[1]) / d * reach)
            out.append(LineString([past(pts[0], pts[1]), *pts, past(pts[-1], pts[-2])]))
    return out


def _faces(lines: list[LineString]) -> list[Polygon]:
    if not lines:
        return []
    noded = shapely.unary_union(lines, grid_size=GRID)
    return [f for f in ops.polygonize(noded) if f.area > GRID]


def _box(lines: list[LineString]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = MultiLineString(lines).bounds
    return x0, y0, max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)


def _path(face: Polygon) -> Path:
    path = Path()
    for ring in [face.exterior, *face.interiors]:
        coords = list(ring.coords)
        path.move_to(*coords[0])
        for c in coords[1:-1]:
            path.line_to(*c)
        path.close()
    return path


def _covered(areas: list):
    """The area several closed paths [(path, even_odd)] cover together (shapely)."""
    covered = []
    for path, _even_odd in areas:
        area = None
        for pts in flatten(path, PER_CURVE):
            pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > GRID]
            if len(pts) < 3:
                continue
            ring = shapely.make_valid(Polygon(pts))
            area = ring if area is None else area.symmetric_difference(ring)   # holes, as drawn
        if area is not None:
            covered.append(area)
    # Only the areas: making a ring valid can leave stray lines and points
    faces = [g for g in shapely.get_parts(shapely.unary_union(covered)) if isinstance(g, Polygon)] if covered else []
    return shapely.unary_union(faces) if faces else Polygon()


def union_path(areas: list) -> Path:
    """The area several closed paths [(path, even_odd)] cover together, as one path of straight
    edges, to fill or clip even-odd (a shape whose area is several paths, like a cube's faces)."""
    out = Path()
    for face in shapely.get_parts(_covered(areas)):
        if isinstance(face, Polygon) and face.area > GRID:
            out.segs += _path(face).segs
    return out


def edge_traced(areas: list, lines: list, tol: float) -> bool:
    """Whether lines run along the whole edge of the area the closed paths [(path, even_odd)]
    cover, to within tol: a can's line goes all the way round it, a bracket pair's doesn't."""
    edge = _covered(areas).boundary
    pieces = []
    for path in lines:
        for sub in path.subpaths():
            pts = flatten(sub, PER_CURVE)[0] if sub.segs else []
            if sub.is_closed() and pts:
                pts = [*pts, pts[0]]   # the closing edge
            if len(pts) >= 2:
                pieces.append(LineString(pts))
    if edge.is_empty or not pieces:
        return False
    return edge.difference(shapely.unary_union(pieces).buffer(tol)).length <= 0.01 * edge.length


def area_at(items: list[dict], point) -> dict | None:
    """The area enclosed round `point` by `items` (a page's items): {items: ids of those round it,
    seed: [u, v], frame: its box}, or None if nothing encloses that point."""
    lines_by = {it["id"]: _lines(it) for it in _flat(items)}
    every = [line for lines in lines_by.values() for line in lines]
    pt = Point(point)
    face = next((f for f in _faces(every) if f.contains(pt)), None)
    if face is None:
        return None
    edge = face.boundary.buffer(GRID * 10)
    ids = [i for i, lines in lines_by.items() if any(line.intersection(edge).length > TOUCH for line in lines)]
    if not ids:
        return None
    return {"items": ids, "seed": _seed(face, [l for i in ids for l in lines_by[i]]), "frame": _frame(face)}


def find(region: dict, items: dict) -> dict | None:
    """An area fill's area now: {path, frame, seed} from its lines and shapes (`items` by id), or
    None if they no longer enclose an area round its seed."""
    lines = [line for i in region.get("items", []) if i in items for line in _lines(items[i])]
    if not lines:
        return None
    x0, y0, w, h = _box(lines)
    u, v = region.get("seed", (0.5, 0.5))
    pt = Point(x0 + u * w, y0 + v * h)
    faces = _faces(lines)
    face = next((f for f in faces if f.contains(pt)), None)
    if face is None:
        # Just on an edge: the nearest area within a hair
        near = [f for f in faces if f.distance(pt) < 0.01]
        face = min(near, key=lambda f: f.distance(pt)) if near else None
    if face is None:
        return None
    return {"path": _path(face), "frame": _frame(face), "seed": _seed(face, lines)}


def _seed(face: Polygon, lines: list[LineString]) -> list[float]:
    """A point well inside the area, as fractions of its lines' combined box."""
    x0, y0, w, h = _box(lines)
    inside = shapely.maximum_inscribed_circle(face, tolerance=max(math.sqrt(face.area) / 200, GRID)).coords[0]
    return [round((inside[0] - x0) / w, 9), round((inside[1] - y0) / h, 9)]


def _frame(face: Polygon) -> list[float]:
    x0, y0, x1, y1 = face.bounds
    return [x0, y0, x1 - x0, y1 - y0]


def _flat(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        if it.get("type") == "group":
            out += _flat(it.get("items", []))
        else:
            out.append(it)
    return out


def custom_path(path: Path, frame: list[float]) -> dict:
    """A path as a freeform shape's own path (resolve.custom_paths), relative to its frame: for
    turning an area fill into an ordinary shape that no longer follows its lines."""
    x0, y0, w, h = frame
    cmds = []
    for seg in path.segs:
        if seg[0] == "Z":
            cmds.append(["Z"])
        else:
            cmds.append([seg[0], *[round(v - (x0 if k % 2 == 0 else y0), 4) for k, v in enumerate(seg[1:])]])
    return {"subpaths": [{"w": w, "h": h, "cmds": cmds, "fill": True, "stroke": False}]}

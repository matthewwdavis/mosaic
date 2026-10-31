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
from shapely.geometry import LinearRing, LineString, MultiLineString, Point, Polygon

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


def painted_path(prims: list) -> Path:
    """The area some drawn paths paint, fills and strokes (with their dashes, ends and corners)
    together, as straight-edged rings to clip by even-odd."""
    shapes = []
    for p in prims:
        if p.fill is not None:
            shapes.append(_covered([(p.path, p.fill.even_odd)]))
        if p.stroke is not None:
            shapes.append(_stroke_area(p.path, p.stroke))
    out = Path()
    for face in shapely.get_parts(shapely.unary_union(shapes)) if shapes else []:
        if isinstance(face, Polygon) and face.area > GRID:
            out.segs += _path(face).segs
    return out


_CAPS = {"round": "round", "flat": "flat", "square": "square"}
_JOINS = {"round": "round", "miter": "mitre", "bevel": "bevel"}


def _stroke_area(path: Path, s):
    """The area a stroke paints (shapely): its width, ends, corners and dashes."""
    width = dict(quad_segs=16, cap_style=_CAPS.get(s.cap, "flat"), join_style=_JOINS.get(s.join, "round"),
                 mitre_limit=max(s.miter_limit, 1.0))
    pieces = []
    for sub in path.subpaths():
        pts = flatten(sub, PER_CURVE)[0] if sub.segs else []
        pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > GRID]
        closed = sub.is_closed() and len(pts) >= 3
        if closed and math.dist(pts[0], pts[-1]) <= GRID:
            pts = pts[:-1]
        if s.dash:
            for run in _dash_runs(pts + [pts[0]] if closed else pts, s.dash, s.dash_phase):
                pieces.append(_run_area(run, s.width, width))
        elif closed:
            pieces.append(LinearRing(pts).buffer(s.width / 2, **width))   # corners all round, no ends
        elif pts:
            pieces.append(_run_area(pts, s.width, width))
    return shapely.unary_union(pieces) if pieces else Polygon()


def _run_area(pts: list, w: float, style: dict):
    if len(pts) < 2 or LineString(pts).length <= GRID:   # a dot: a round end makes a disc
        return Point(pts[0]).buffer(w / 2, quad_segs=16) if style["cap_style"] == "round" else Polygon()
    return LineString(pts).buffer(w / 2, **style)


def _dash_runs(pts: list, dash: list, phase: float) -> list:
    """The stretches of a polyline that a dash pattern draws (PDF rules: the pattern starts
    `phase` along it and repeats; an odd-length pattern repeats twice to pair dashes and gaps)."""
    pattern = list(dash) * (1 if len(dash) % 2 == 0 else 2)
    total = sum(pattern)
    if total <= 0 or len(pts) < 2:
        return [pts]
    i, left = 0, phase % total
    while left >= pattern[i]:
        left -= pattern[i]
        i = (i + 1) % len(pattern)
    left = pattern[i] - left
    runs, cur = [], [pts[0]] if i % 2 == 0 else None
    for a, b in zip(pts, pts[1:]):
        seg, t = math.dist(a, b), 0.0
        while seg - t >= left:
            t += left
            q = (a[0] + (b[0] - a[0]) * t / seg, a[1] + (b[1] - a[1]) * t / seg) if seg else a
            if cur is not None:
                cur.append(q)
                runs.append(cur)
                cur = None
            else:
                cur = [q]
            i = (i + 1) % len(pattern)
            left = pattern[i]   # a zero-length dash (a round dot) ends where it starts
        left -= seg - t
        if cur is not None:
            cur.append(b)
    if cur is not None:
        runs.append(cur)
    return runs


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

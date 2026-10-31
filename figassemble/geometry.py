"""Matrices, paths and the DrawingML-compatible shape geometry FigAssemble draws with.

Coordinates are points (1/72 in) with y pointing down, as in SVG and PowerPoint.
Angles are in degrees and positive angles turn clockwise on screen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Matrices
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Matrix:
    """Affine map (x, y) -> (a*x + c*y + e, b*x + d*y + f), the SVG/PDF convention."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def __matmul__(self, other: "Matrix") -> "Matrix":
        # (self @ other) applies `other` first, then `self`
        return Matrix(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def apply_vector(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y, self.b * x + self.d * y)

    def inverse(self) -> "Matrix":
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-15:
            raise ValueError("matrix is not invertible")
        a, b, c, d = self.d / det, -self.b / det, -self.c / det, self.a / det
        return Matrix(a, b, c, d, -(a * self.e + c * self.f), -(b * self.e + d * self.f))

    @property
    def scale_factor(self) -> float:
        """How much lengths grow on average (square root of |determinant|)."""
        return math.sqrt(abs(self.a * self.d - self.b * self.c))

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    @staticmethod
    def translate(tx: float, ty: float) -> "Matrix":
        return Matrix(1.0, 0.0, 0.0, 1.0, tx, ty)

    @staticmethod
    def scale(sx: float, sy: float | None = None) -> "Matrix":
        return Matrix(sx, 0.0, 0.0, sx if sy is None else sy, 0.0, 0.0)

    @staticmethod
    def rotate(degrees: float) -> "Matrix":
        # Quarter turns are snapped so 90/180/270 degree rotations stay exact
        quarter = degrees / 90.0
        if abs(quarter - round(quarter)) < 1e-12:
            cos, sin = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)][int(round(quarter)) % 4]
        else:
            r = math.radians(degrees)
            cos, sin = math.cos(r), math.sin(r)
        return Matrix(cos, sin, -sin, cos, 0.0, 0.0)


IDENTITY = Matrix()


def frame_matrix(frame, rot: float = 0.0, flip_h: bool = False, flip_v: bool = False) -> Matrix:
    """Map local frame coordinates (0..w, 0..h) to the page.

    Matches PowerPoint: flips happen first, then rotation clockwise about the frame centre.
    """
    x, y, w, h = frame
    return (Matrix.translate(x + w / 2.0, y + h / 2.0)
            @ Matrix.rotate(rot)
            @ Matrix.scale(-1.0 if flip_h else 1.0, -1.0 if flip_v else 1.0)
            @ Matrix.translate(-w / 2.0, -h / 2.0))


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _fmt(v: float, ndigits: int) -> str:
    """Compact number formatting: fixed precision, no trailing zeros, no '-0'."""
    s = f"{v:.{ndigits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _param_angle(a: float, b: float, theta: float) -> float:
    """Parametric ellipse angle of the point seen at visual angle `theta` (radians).

    DrawingML arcs use visual angles: the ray from the centre at `theta` hits the arc point.
    The result stays in the same turn as `theta` so sweeps keep their size and sign.
    """
    t = math.atan2(a * math.sin(theta), b * math.cos(theta))
    return t + 2.0 * math.pi * round((theta - t) / (2.0 * math.pi))


class Path:
    """Subpaths made of move (M), line (L), cubic Bezier (C) and close (Z) segments."""

    __slots__ = ("segs",)

    def __init__(self, segs=None):
        # ('M', x, y) | ('L', x, y) | ('C', x1, y1, x2, y2, x, y) | ('Z',)
        self.segs: list[tuple] = list(segs or [])

    def __repr__(self) -> str:
        return f"Path({self.to_svg(2)!r})"

    # Building ---------------------------------------------------------------

    def move_to(self, x: float, y: float) -> "Path":
        self.segs.append(("M", x, y))
        return self

    def line_to(self, x: float, y: float) -> "Path":
        self.segs.append(("L", x, y))
        return self

    def curve_to(self, x1: float, y1: float, x2: float, y2: float, x: float, y: float) -> "Path":
        self.segs.append(("C", x1, y1, x2, y2, x, y))
        return self

    def quad_to(self, x1: float, y1: float, x: float, y: float) -> "Path":
        x0, y0 = self.current_point
        return self.curve_to(x0 + 2 / 3 * (x1 - x0), y0 + 2 / 3 * (y1 - y0),
                             x + 2 / 3 * (x1 - x), y + 2 / 3 * (y1 - y), x, y)

    def close(self) -> "Path":
        self.segs.append(("Z",))
        return self

    def extend(self, other: "Path") -> "Path":
        self.segs.extend(other.segs)
        return self

    @property
    def current_point(self) -> tuple[float, float]:
        start = (0.0, 0.0)
        cur = (0.0, 0.0)
        for s in self.segs:
            if s[0] == "M":
                start = cur = (s[1], s[2])
            elif s[0] == "Z":
                cur = start
            else:
                cur = (s[-2], s[-1])
        return cur

    def arc_to(self, wr: float, hr: float, start: float, sweep: float) -> "Path":
        """DrawingML arcTo: continue along an ellipse with radii (wr, hr).

        The current point sits on the ellipse at visual angle `start`; the arc sweeps
        `sweep` degrees (positive = clockwise on screen).
        """
        if sweep == 0:
            return self
        x0, y0 = self.current_point
        a, b = max(abs(wr), 1e-9), max(abs(hr), 1e-9)
        t1 = _param_angle(a, b, math.radians(start))
        t2 = _param_angle(a, b, math.radians(start + sweep))
        cx, cy = x0 - a * math.cos(t1), y0 - b * math.sin(t1)
        dt = t2 - t1
        n = max(1, math.ceil(abs(dt) / (math.pi / 2.0) - 1e-9))
        step = dt / n
        k = 4.0 / 3.0 * math.tan(step / 4.0)
        t = t1
        for _ in range(n):
            ta, tb = t, t + step
            ca, sa, cb, sb = math.cos(ta), math.sin(ta), math.cos(tb), math.sin(tb)
            p0 = (cx + a * ca, cy + b * sa)
            p3 = (cx + a * cb, cy + b * sb)
            self.curve_to(p0[0] - k * a * sa, p0[1] + k * b * ca,
                          p3[0] + k * a * sb, p3[1] - k * b * cb,
                          p3[0], p3[1])
            t = tb
        return self

    # Queries ------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not any(s[0] in "LC" for s in self.segs)

    def transformed(self, m: Matrix) -> "Path":
        out = []
        for s in self.segs:
            if s[0] in "ML":
                out.append((s[0],) + m.apply(s[1], s[2]))
            elif s[0] == "C":
                out.append(("C",) + m.apply(s[1], s[2]) + m.apply(s[3], s[4]) + m.apply(s[5], s[6]))
            else:
                out.append(s)
        return Path(out)

    def bbox(self) -> tuple[float, float, float, float] | None:
        """Exact bounding box of the drawn geometry (curve extrema included)."""
        xs: list[float] = []
        ys: list[float] = []
        cur = start = None
        for s in self.segs:
            if s[0] == "M":
                cur = start = (s[1], s[2])
            elif s[0] == "L":
                if cur is not None:
                    xs += [cur[0], s[1]]
                    ys += [cur[1], s[2]]
                cur = (s[1], s[2])
            elif s[0] == "C":
                p0 = cur if cur is not None else (s[1], s[2])
                pts = [p0, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])]
                for t in _bezier_extrema(pts):
                    x, y = _bezier_point(pts, t)
                    xs.append(x)
                    ys.append(y)
                cur = (s[5], s[6])
            elif s[0] == "Z":
                cur = start
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def subpaths(self) -> list["Path"]:
        out: list[Path] = []
        for s in self.segs:
            if s[0] == "M" or not out:
                out.append(Path())
            out[-1].segs.append(s)
        return out

    def is_closed(self) -> bool:
        return bool(self.segs) and self.segs[-1][0] == "Z"

    def start_tangent(self) -> tuple[tuple[float, float], tuple[float, float]] | None:
        """(start point, unit direction pointing backwards out of the path) for line ends."""
        segs = [s for s in self.segs if s[0] != "Z"]
        if len(segs) < 2 or segs[0][0] != "M":
            return None
        p0 = (segs[0][1], segs[0][2])
        s = segs[1]
        candidates = [(s[1], s[2]), (s[3], s[4]), (s[5], s[6])] if s[0] == "C" else [(s[1], s[2])]
        for q in candidates:
            dx, dy = p0[0] - q[0], p0[1] - q[1]
            n = math.hypot(dx, dy)
            if n > 1e-9:
                return p0, (dx / n, dy / n)
        return None

    def end_tangent(self) -> tuple[tuple[float, float], tuple[float, float]] | None:
        """(end point, unit direction of travel at the end) for line ends."""
        segs = [s for s in self.segs if s[0] != "Z"]
        if len(segs) < 2:
            return None
        s = segs[-1]
        p_end = (s[-2], s[-1])
        prev = segs[-2]
        p_prev = (prev[-2], prev[-1])
        candidates = [(s[3], s[4]), (s[1], s[2]), p_prev] if s[0] == "C" else [p_prev]
        for q in candidates:
            dx, dy = p_end[0] - q[0], p_end[1] - q[1]
            n = math.hypot(dx, dy)
            if n > 1e-9:
                return p_end, (dx / n, dy / n)
        return None

    # Editing -----------------------------------------------------------------

    def trimmed(self, start: float = 0.0, end: float = 0.0) -> "Path":
        """Shorten an open single-subpath path by arc length at either end."""
        p = self
        if end > 0:
            p = p._trim_end(end)
        if start > 0:
            p = p.reversed()._trim_end(start).reversed()
        return p

    def reversed(self) -> "Path":
        """Reverse a single open subpath."""
        pts: list[tuple] = []
        cur = None
        for s in self.segs:
            if s[0] == "M":
                cur = (s[1], s[2])
                pts.append(("M", cur))
            elif s[0] == "L":
                pts.append(("L", cur, (s[1], s[2])))
                cur = (s[1], s[2])
            elif s[0] == "C":
                pts.append(("C", cur, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])))
                cur = (s[5], s[6])
        if cur is None:
            return Path()
        out = Path().move_to(*cur)
        for seg in reversed(pts[1:]):
            if seg[0] == "L":
                out.line_to(*seg[1])
            else:
                _, p0, c1, c2, _p3 = seg
                out.curve_to(c2[0], c2[1], c1[0], c1[1], p0[0], p0[1])
        return out

    def _trim_end(self, length: float) -> "Path":
        segs = [s for s in self.segs if s[0] != "Z"]
        if len(segs) < 2:
            return Path(segs)
        # Walk back from the end, consuming segments until `length` is used up
        out = list(segs)
        remaining = length
        while len(out) > 1 and remaining > 1e-12:
            s = out[-1]
            prev = out[-2]
            p0 = (prev[-2], prev[-1])
            if s[0] == "L":
                seg_len = math.hypot(s[1] - p0[0], s[2] - p0[1])
                if seg_len <= remaining:
                    out.pop()
                    remaining -= seg_len
                    continue
                t = 1.0 - remaining / seg_len
                out[-1] = ("L", p0[0] + (s[1] - p0[0]) * t, p0[1] + (s[2] - p0[1]) * t)
                remaining = 0.0
            else:
                pts = [p0, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])]
                seg_len = _bezier_length(pts, 0.0, 1.0)
                if seg_len <= remaining:
                    out.pop()
                    remaining -= seg_len
                    continue
                t = _bezier_param_at_length_from_end(pts, remaining, seg_len)
                left, _ = _split_bezier(pts, t)
                out[-1] = ("C", left[1][0], left[1][1], left[2][0], left[2][1], left[3][0], left[3][1])
                remaining = 0.0
        return Path(out)

    # Serialisation --------------------------------------------------------------

    def to_svg(self, ndigits: int = 3) -> str:
        parts = []
        for s in self.segs:
            if s[0] == "Z":
                parts.append("Z")
            else:
                parts.append(s[0] + " ".join(_fmt(v, ndigits) for v in s[1:]))
        return "".join(parts)

    def to_pdf(self, ndigits: int = 4) -> str:
        ops = []
        for s in self.segs:
            if s[0] == "M":
                ops.append(f"{_fmt(s[1], ndigits)} {_fmt(s[2], ndigits)} m")
            elif s[0] == "L":
                ops.append(f"{_fmt(s[1], ndigits)} {_fmt(s[2], ndigits)} l")
            elif s[0] == "C":
                ops.append(" ".join(_fmt(v, ndigits) for v in s[1:]) + " c")
            else:
                ops.append("h")
        return "\n".join(ops)


def _bezier_point(pts, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
    mt = 1 - t
    a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
    return (a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3)


def _bezier_extrema(pts) -> list[float]:
    ts = [0.0, 1.0]
    for i in (0, 1):
        p0, p1, p2, p3 = (p[i] for p in pts)
        # Derivative 3[(p1-p0)(1-t)^2 + 2(p2-p1)(1-t)t + (p3-p2)t^2] as a*t^2 + b*t + c
        a = -p0 + 3 * p1 - 3 * p2 + p3
        b = 2 * (p0 - 2 * p1 + p2)
        c = p1 - p0
        if abs(a) < 1e-12:
            if abs(b) > 1e-12:
                ts.append(-c / b)
        else:
            disc = b * b - 4 * a * c
            if disc >= 0:
                r = math.sqrt(disc)
                ts += [(-b + r) / (2 * a), (-b - r) / (2 * a)]
    return [t for t in ts if 0.0 <= t <= 1.0]


def _split_bezier(pts, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts

    def lerp(p, q):
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

    p01, p12, p23 = lerp((x0, y0), (x1, y1)), lerp((x1, y1), (x2, y2)), lerp((x2, y2), (x3, y3))
    p012, p123 = lerp(p01, p12), lerp(p12, p23)
    mid = lerp(p012, p123)
    return [(x0, y0), p01, p012, mid], [mid, p123, p23, (x3, y3)]


def _bezier_length(pts, t0: float, t1: float, steps: int = 64) -> float:
    total = 0.0
    prev = _bezier_point(pts, t0)
    for i in range(1, steps + 1):
        p = _bezier_point(pts, t0 + (t1 - t0) * i / steps)
        total += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
    return total


def _bezier_param_at_length_from_end(pts, length: float, total: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if _bezier_length(pts, mid, 1.0) > length:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# Preset shapes (DrawingML presetShapeDefinitions formulas)
# ---------------------------------------------------------------------------

@dataclass
class ShapePath:
    """One drawn path of a shape and whether it may be filled and/or stroked."""

    path: Path
    fill: bool = True
    stroke: bool = True


# Adjust-value defaults, in the units FigAssemble stores them: fractions or degrees
PRESET_DEFAULTS: dict[str, dict[str, float]] = {
    "rect": {},
    "roundRect": {"adj": 0.16667},
    "ellipse": {},
    "triangle": {"adj": 0.5},
    "rtTriangle": {},
    "arc": {"adj1": 270.0, "adj2": 0.0},
    "rightBracket": {"adj": 0.08333},
    "leftBracket": {"adj": 0.08333},
    "line": {},
}

# Presets whose stroke is an open path, so line ends (arrowheads) apply
OPEN_PRESETS = {"arc", "rightBracket", "leftBracket", "line"}


def preset_paths(geom: str, w: float, h: float, adj: dict | None = None) -> list[ShapePath]:
    """Paths for a DrawingML preset shape filling a w x h frame."""
    a = dict(PRESET_DEFAULTS.get(geom, {}))
    a.update(adj or {})
    ss = min(w, h)
    if geom == "roundRect":
        r = ss * min(max(a["adj"], 0.0), 0.5)
        p = (Path().move_to(0, r).arc_to(r, r, 180, 90).line_to(w - r, 0).arc_to(r, r, 270, 90)
             .line_to(w, h - r).arc_to(r, r, 0, 90).line_to(r, h).arc_to(r, r, 90, 90).close())
        return [ShapePath(p)]
    if geom == "ellipse":
        rx, ry = w / 2, h / 2
        p = (Path().move_to(0, ry).arc_to(rx, ry, 180, 90).arc_to(rx, ry, 270, 90)
             .arc_to(rx, ry, 0, 90).arc_to(rx, ry, 90, 90).close())
        return [ShapePath(p)]
    if geom == "triangle":
        x2 = w * min(max(a["adj"], 0.0), 1.0)
        return [ShapePath(Path().move_to(0, h).line_to(x2, 0).line_to(w, h).close())]
    if geom == "rtTriangle":
        return [ShapePath(Path().move_to(0, h).line_to(0, 0).line_to(w, h).close())]
    if geom == "arc":
        st = a["adj1"] % 360.0
        en = a["adj2"] % 360.0
        sw = en - st
        if sw <= 0:
            sw += 360.0
        rx, ry = w / 2, h / 2
        t = _param_angle(max(rx, 1e-9), max(ry, 1e-9), math.radians(st))
        x1, y1 = rx + rx * math.cos(t), ry + ry * math.sin(t)
        stroke = Path().move_to(x1, y1).arc_to(rx, ry, st, sw)
        fill = Path().move_to(x1, y1).arc_to(rx, ry, st, sw).line_to(rx, ry).close()
        return [ShapePath(fill, fill=True, stroke=False), ShapePath(stroke, fill=False, stroke=True)]
    if geom in ("rightBracket", "leftBracket"):
        max_adj = 0.5 * h / ss if ss > 0 else 0.0
        y1 = ss * min(max(a["adj"], 0.0), max_adj)
        if geom == "rightBracket":
            def draw(p):
                return p.move_to(0, 0).arc_to(w, y1, 270, 90).line_to(w, h - y1).arc_to(w, y1, 0, 90)
        else:
            def draw(p):
                return p.move_to(w, h).arc_to(w, y1, 90, 90).line_to(0, y1).arc_to(w, y1, 180, 90)
        return [ShapePath(draw(Path()).close(), fill=True, stroke=False),
                ShapePath(draw(Path()), fill=False, stroke=True)]
    if geom == "line":
        return [ShapePath(Path().move_to(0, 0).line_to(w, h), fill=False, stroke=True)]
    # rect, and the fallback for presets not implemented yet
    return [ShapePath(Path().move_to(0, 0).line_to(w, 0).line_to(w, h).line_to(0, h).close())]


def preset_text_rect(geom: str, w: float, h: float, adj: dict | None = None) -> tuple[float, float, float, float]:
    """Area text is laid out in, before insets (x0, y0, x1, y1 in frame coordinates)."""
    a = dict(PRESET_DEFAULTS.get(geom, {}))
    a.update(adj or {})
    if geom == "roundRect":
        il = min(w, h) * min(max(a["adj"], 0.0), 0.5) * 0.29289
        return (il, il, w - il, h - il)
    if geom == "ellipse":
        dx, dy = w / 2 * math.cos(math.radians(45)), h / 2 * math.sin(math.radians(45))
        return (w / 2 - dx, h / 2 - dy, w / 2 + dx, h / 2 + dy)
    if geom == "triangle":
        x2 = w * min(max(a["adj"], 0.0), 1.0)
        return (x2 / 2, h / 2, (x2 + w) / 2, h)
    return (0.0, 0.0, w, h)


# ---------------------------------------------------------------------------
# Line ends (arrowheads)
# ---------------------------------------------------------------------------

# Arrowhead width and length as multiples of the line width (DrawingML sm / med / lg)
ARROW_SIZE = {"sm": 2.0, "med": 3.0, "lg": 5.0}
# Thin lines get arrowheads sized as if the line were at least this wide (points);
# measured from PowerPoint: a small head on a 1 pt line is 4 x 4 pt
ARROW_MIN_BASE_WIDTH = 2.0


def arrowhead(tip: tuple[float, float], direction: tuple[float, float], line_width: float,
              spec: dict) -> tuple[list[ShapePath], float]:
    """Geometry of a line end at `tip`, travelling along unit vector `direction`.

    Returns the paths to draw (filled or stroked in the line colour) and how far the line
    itself should be shortened so it doesn't poke out past the head.
    """
    kind = spec.get("type", "triangle")
    base = max(line_width, ARROW_MIN_BASE_WIDTH)
    w = ARROW_SIZE.get(spec.get("w", "med"), 3.0) * base
    length = ARROW_SIZE.get(spec.get("len", "med"), 3.0) * base
    dx, dy = direction
    nx, ny = -dy, dx
    tx, ty = tip

    def pt(along: float, across: float) -> tuple[float, float]:
        return (tx + dx * along + nx * across, ty + dy * along + ny * across)

    if kind == "triangle":
        p = Path().move_to(*pt(0, 0)).line_to(*pt(-length, w / 2)).line_to(*pt(-length, -w / 2)).close()
        return [ShapePath(p, fill=True, stroke=False)], length
    if kind == "stealth":
        p = (Path().move_to(*pt(0, 0)).line_to(*pt(-length, w / 2)).line_to(*pt(-length * 0.5, 0))
             .line_to(*pt(-length, -w / 2)).close())
        return [ShapePath(p, fill=True, stroke=False)], length * 0.5
    if kind == "diamond":
        p = (Path().move_to(*pt(length / 2, 0)).line_to(*pt(0, w / 2)).line_to(*pt(-length / 2, 0))
             .line_to(*pt(0, -w / 2)).close())
        return [ShapePath(p, fill=True, stroke=False)], 0.0
    if kind == "oval":
        rx, ry = length / 2, w / 2
        p = Path()
        k = 0.5522847498307936
        p.move_to(*pt(rx, 0))
        p.curve_to(*pt(rx, ry * k), *pt(rx * k, ry), *pt(0, ry))
        p.curve_to(*pt(-rx * k, ry), *pt(-rx, ry * k), *pt(-rx, 0))
        p.curve_to(*pt(-rx, -ry * k), *pt(-rx * k, -ry), *pt(0, -ry))
        p.curve_to(*pt(rx * k, -ry), *pt(rx, -ry * k), *pt(rx, 0))
        p.close()
        return [ShapePath(p, fill=True, stroke=False)], 0.0
    if kind == "arrow":
        p = Path().move_to(*pt(-length, w / 2)).line_to(*pt(0, 0)).line_to(*pt(-length, -w / 2))
        return [ShapePath(p, fill=False, stroke=True)], 0.0
    return [], 0.0


# ---------------------------------------------------------------------------
# Dash patterns
# ---------------------------------------------------------------------------

# DrawingML preset dashes as dash/gap lengths in multiples of the line width
DASH_PRESETS: dict[str, tuple[float, ...] | None] = {
    "solid": None,
    "dot": (1, 3),
    "dash": (4, 3),
    "lgDash": (8, 3),
    "dashDot": (4, 3, 1, 3),
    "lgDashDot": (8, 3, 1, 3),
    "lgDashDotDot": (8, 3, 1, 3, 1, 3),
    "sysDash": (3, 1),
    "sysDot": (1, 1),
    "sysDashDot": (3, 1, 1, 1),
    "sysDashDotDot": (3, 1, 1, 1, 1, 1),
}


def dash_array(dash, width: float, cap: str = "flat") -> list[float] | None:
    """Dash lengths in points for a stroke, or None for a solid line.

    `dash` is a preset name or a list of multiples of the line width. Round and square
    caps extend every dash by half a line width at each end, so the drawn dashes are
    shortened by one width (and the gaps lengthened) to keep the preset's rhythm.
    """
    if dash is None:
        return None
    pattern = DASH_PRESETS.get(dash) if isinstance(dash, str) else tuple(dash)
    if not pattern:
        return None
    w = max(width, 1e-6)
    out = []
    for i, v in enumerate(pattern):
        length = v * w
        if cap in ("round", "square"):
            length = max(length - w, 0.0) if i % 2 == 0 else length + w
        out.append(length)
    return out


@dataclass
class Stroke:
    """A resolved stroke style (lengths in points)."""

    color: str = "#000000"
    width: float = 1.0
    dash: list[float] | None = None
    cap: str = "flat"     # flat | round | square
    join: str = "round"   # round | miter | bevel
    opacity: float = 1.0
    miter_limit: float = 8.0


@dataclass
class Gradient:
    """A linear gradient defined in a unit square, mapped onto the page by `matrix`."""

    stops: list[tuple[float, str, float]]          # (position 0..1, colour, opacity)
    p0: tuple[float, float]                        # axis start, unit-square coordinates
    p1: tuple[float, float]
    matrix: Matrix = field(default_factory=Matrix)

    @property
    def has_alpha(self) -> bool:
        return any(op < 1.0 for _, _, op in self.stops)


def linear_gradient(spec: dict, w: float, h: float, frame_m: Matrix) -> Gradient:
    """DrawingML linear gradient over a w x h shape whose local box maps to the page by frame_m.

    `angle` turns clockwise from +x. With `scaled`, the angle is set in a unit square that is
    then stretched over the shape; otherwise it is measured in the shape's own proportions.
    The axis runs through the centre and spans the box projected onto it.
    """
    theta = math.radians(spec.get("angle", 0.0))
    dx, dy = math.cos(theta), math.sin(theta)
    stops = [(float(s["pos"]), s["color"], float(s.get("opacity", 1.0))) for s in spec.get("stops", [])]
    stops = stops or [(0.0, "#000000", 1.0)]
    if spec.get("scaled", True):
        extent = abs(dx) + abs(dy)
        p0 = (0.5 - dx * extent / 2, 0.5 - dy * extent / 2)
        p1 = (0.5 + dx * extent / 2, 0.5 + dy * extent / 2)
        return Gradient(stops, p0, p1, frame_m @ Matrix.scale(max(w, 1e-9), max(h, 1e-9)))
    extent = w * abs(dx) + h * abs(dy)
    p0 = (w / 2 - dx * extent / 2, h / 2 - dy * extent / 2)
    p1 = (w / 2 + dx * extent / 2, h / 2 + dy * extent / 2)
    return Gradient(stops, p0, p1, frame_m)


@dataclass
class Fill:
    color: str = "#000000"
    opacity: float = 1.0
    even_odd: bool = False
    gradient: Gradient | None = None


@dataclass
class DrawPath:
    """A path in page coordinates with the style to paint it."""

    path: Path
    stroke: Stroke | None = None
    fill: Fill | None = None
    meta: dict = field(default_factory=dict)

    def bbox(self) -> tuple[float, float, float, float] | None:
        bb = self.path.bbox()
        if bb is None:
            return None
        pad = self.stroke.width / 2 if self.stroke else 0.0
        return (bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad)

"""Even dash spacing: dashes and dots laid out so that every corner and line end gets one and
the stretches between them hold a whole number of repeats.

PowerPoint (and PDF and SVG dash patterns) run a pattern continuously along a path, so the
dashes either side of a corner fall wherever the pattern happens to be: two dots straddling a
corner sit closer together than anywhere else, and a closed outline has a squeezed spot where
the pattern meets its own start. Here, as with Illustrator's "align dashes to corners":

- a dash is centred on every corner (a dot sits on it), bends in lines and the middles of rounded
  corners included, and lines start and end on a whole dash;
- each stretch between corners and ends holds a whole number of repeats, its dashes and gaps
  scaled together to fit; closed curves without corners too, so they have no seam;
- gaps are measured straight across, so dots on tight curves stay as far apart as elsewhere.

The result is explicit geometry, each dash its own subpath, to be drawn with a solid stroke.
"""
from __future__ import annotations

import bisect
import math

from .geometry import Path, _bezier_point, _split_bezier

CORNER_DEG = 20.0     # a turn sharper than this is a corner (gentler bends are passed through)
ROUNDED_DEG = 45.0    # a curve between straight stretches turning this much is a rounded corner
SAMPLES = 48          # points per curve for measuring along it
DOT = 1e-3            # a dot is a stroke this long, made round by its caps
EPS = 1e-9


class _Piece:
    """One line or cubic of a subpath, measured along its length."""

    __slots__ = ("pts", "curve", "length", "ts", "ss", "samples")

    def __init__(self, pts):
        self.pts = pts
        self.curve = len(pts) == 4
        if self.curve:
            self.ts = [k / SAMPLES for k in range(SAMPLES + 1)]
            self.samples = [_bezier_point(pts, t) for t in self.ts]
            self.ss = [0.0]
            for a, b in zip(self.samples, self.samples[1:]):
                self.ss.append(self.ss[-1] + math.dist(a, b))
            self.length = self.ss[-1]
        else:
            self.samples = list(pts)
            self.length = math.dist(*pts)
            self.ss = [0.0, self.length]

    def t_at(self, s: float) -> float:
        if not self.curve:
            return min(max(s / self.length, 0.0), 1.0) if self.length > 0 else 0.0
        k = min(max(bisect.bisect_right(self.ss, s) - 1, 0), SAMPLES - 1)
        span = self.ss[k + 1] - self.ss[k]
        f = min(max((s - self.ss[k]) / span, 0.0), 1.0) if span > 0 else 0.0
        return self.ts[k] + f * (self.ts[k + 1] - self.ts[k])

    def point(self, t: float):
        if self.curve:
            return _bezier_point(self.pts, t)
        (x0, y0), (x1, y1) = self.pts
        return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    def direction(self, t: float):
        if self.curve:
            p0, p1, p2, p3 = self.pts
            mt = 1 - t
            d = [3 * mt * mt * (p1[i] - p0[i]) + 6 * mt * t * (p2[i] - p1[i]) + 3 * t * t * (p3[i] - p2[i]) for i in (0, 1)]
            if math.hypot(*d) < EPS:   # a control point on its end point: look further along
                d = [(p2[i] - p0[i]) if t < 0.5 else (p3[i] - p1[i]) for i in (0, 1)]
                if math.hypot(*d) < EPS:
                    d = [p3[i] - p0[i] for i in (0, 1)]
        else:
            d = [self.pts[1][i] - self.pts[0][i] for i in (0, 1)]
        n = math.hypot(*d) or 1.0
        return (d[0] / n, d[1] / n)

    def part(self, t0: float, t1: float):
        """The control points from t0 to t1 (t0 < t1) of a curve."""
        tail = _split_bezier(self.pts, t0)[1] if t0 > 0 else list(self.pts)
        return _split_bezier(tail, (t1 - t0) / (1 - t0))[0] if t1 < 1 and t0 < 1 else tail


class _Sub:
    """A subpath as pieces laid end to end, with positions measured along it."""

    def __init__(self, pieces: list[_Piece], closed: bool):
        self.pieces = pieces
        self.closed = closed
        self.offs = [0.0]
        for p in pieces:
            self.offs.append(self.offs[-1] + p.length)
        self.length = self.offs[-1]

    def locate(self, a: float, before: bool = False):
        """(piece index, t) at position a; at a joint, the earlier piece's end if `before`."""
        find = bisect.bisect_left if before else bisect.bisect_right
        i = min(max(find(self.offs, a) - 1, 0), len(self.pieces) - 1)
        return i, self.pieces[i].t_at(a - self.offs[i])

    def point(self, a: float):
        i, t = self.locate(a)
        return self.pieces[i].point(t)

    def direction(self, a: float):
        i, t = self.locate(a)
        return self.pieces[i].direction(t)

    def corners(self):
        """Where to centre a dash: joints that turn by more than CORNER_DEG, and the middles of
        rounded corners, i.e. curves between straight stretches or sharp corners that turn by
        ROUNDED_DEG or more (a rounded rectangle's corners; not an ellipse, all one curve)."""
        n = len(self.pieces)
        # joint[k]: the signed turn where piece k begins (k = 0 on closed paths: the join)
        joint = [0.0] * n
        for k in range(0 if self.closed else 1, n):
            joint[k] = _angle(self.pieces[k - 1].direction(1.0), self.pieces[k].direction(0.0))
        sharp = [k for k in range(n) if abs(joint[k]) > CORNER_DEG and (self.closed or k > 0)]
        out = [self.offs[k] for k in sharp]
        bound = [not p.curve or k in sharp or (k == 0 and not self.closed) for k, p in enumerate(self.pieces)]
        first = next((k for k in range(n) if bound[k]), None)
        if first is None:
            return sorted(out)   # one smooth curve all the way round
        k = 0
        while k < n:
            i = (first + k) % n
            if not self.pieces[i].curve:
                k += 1
                continue
            start, length, turn, j = self.offs[i], 0.0, 0.0, k
            while j < n:
                ii = (first + j) % n
                if not self.pieces[ii].curve or (j > k and bound[ii]):
                    break
                p = self.pieces[ii]
                turn += (joint[ii] if j > k else 0.0) + _angle(p.direction(0.0), p.direction(1.0))
                length += p.length
                j += 1
            if abs(turn) >= ROUNDED_DEG:
                mid = start + length / 2
                out.append(mid % self.length if self.closed else mid)
            k = j
        return sorted(out)

    def emit(self, a: float, b: float, out: Path) -> None:
        """Add the stretch from a to b as a subpath: around the join for closed paths, straight
        on past the ends of open ones (for dashes lengthened at both ends)."""
        if self.closed:   # positions past the join count from the start again
            turns = math.floor(a / self.length) * self.length
            a, b = a - turns, b - turns
        if b - a < EPS:
            p, d = self.point(a), self.direction(a)
            out.move_to(*p).line_to(p[0] + d[0] * DOT, p[1] + d[1] * DOT)
            return
        if self.closed:
            if b - a >= self.length - EPS:   # all the way round
                self._span(0.0, self.length, out, True)
                out.close()
                return
            a0 = a % self.length
            b0 = a0 + (b - a)
            if b0 <= self.length + EPS:
                self._span(a0, min(b0, self.length), out, True)
            else:
                self._span(a0, self.length, out, True)
                self._span(0.0, b0 - self.length, out, False)
            return
        lead, trail = max(-a, 0.0), max(b - self.length, 0.0)
        a, b = max(a, 0.0), min(b, self.length)
        if lead > 0:
            p, d = self.point(0.0), self.direction(0.0)
            out.move_to(p[0] - d[0] * lead, p[1] - d[1] * lead).line_to(*p)
        if b > a:
            self._span(a, b, out, lead == 0)
        elif lead == 0:
            out.move_to(*self.point(a))
        if trail > 0:
            p, d = self.point(self.length), self.direction(self.length)
            out.line_to(p[0] + d[0] * trail, p[1] + d[1] * trail)

    def _span(self, u: float, v: float, out: Path, move: bool) -> None:
        i, tu = self.locate(u)
        j, tv = self.locate(v, before=True)
        if j < i or (j == i and tv < tu):
            j, tv = i, tu
        if move:
            out.move_to(*self.pieces[i].point(tu))
        for k in range(i, j + 1):
            p = self.pieces[k]
            t0, t1 = (tu if k == i else 0.0), (tv if k == j else 1.0)
            if t1 - t0 < EPS:
                continue
            if p.curve:
                q = p.part(t0, t1)
                out.curve_to(*q[1], *q[2], *q[3])
            else:
                out.line_to(*p.point(t1))


class _Run:
    """The stretch of a subpath between two corners or ends, as a polyline for measuring
    straight-line distances along it."""

    def __init__(self, sub: _Sub, start: float, length: float):
        self.length = length
        where = (lambda a: a % sub.length) if sub.closed else (lambda a: a)
        self.arcs, self.pts = [0.0], [sub.point(where(start))]
        # The sample points of every piece inside the run, in order (round the join if closed)
        i = min(max(bisect.bisect_right(sub.offs, where(start)) - 1, 0), len(sub.pieces) - 1)
        base = sub.offs[i] + (start - where(start))
        while True:
            piece = sub.pieces[i]
            for s, q in zip(piece.ss, piece.samples):
                if EPS < base + s - start < length - EPS:
                    self.arcs.append(base + s - start)
                    self.pts.append(q)
            base += piece.length
            i += 1
            if base - start >= length - EPS or (i == len(sub.pieces) and not sub.closed):
                break
            i %= len(sub.pieces)
        self.arcs.append(length)
        self.pts.append(sub.point(where(start + length)))

    def point(self, a: float):
        k = min(max(bisect.bisect_right(self.arcs, a) - 1, 0), len(self.arcs) - 2)
        span = self.arcs[k + 1] - self.arcs[k]
        f = (a - self.arcs[k]) / span if span > EPS else 0.0
        (x0, y0), (x1, y1) = self.pts[k], self.pts[k + 1]
        return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)

    def advance(self, a: float, c: float) -> float:
        """The position past a whose straight-line distance from the point at a is c."""
        if c <= EPS:
            return a
        q = self.point(a)
        k = bisect.bisect_right(self.arcs, a)
        prev_a, prev = a, q
        while k < len(self.arcs):
            p = self.pts[k]
            if math.dist(p, q) >= c:
                # Where the segment prev-p crosses the circle of radius c around q
                dx, dy = p[0] - prev[0], p[1] - prev[1]
                fx, fy = prev[0] - q[0], prev[1] - q[1]
                aa, bb, cc = dx * dx + dy * dy, 2 * (fx * dx + fy * dy), fx * fx + fy * fy - c * c
                disc = max(bb * bb - 4 * aa * cc, 0.0)
                lam = (-bb + math.sqrt(disc)) / (2 * aa) if aa > EPS else 1.0
                return prev_a + min(max(lam, 0.0), 1.0) * (self.arcs[k] - prev_a)
            prev_a, prev = self.arcs[k], p
            k += 1
        return self.length + max(c - math.dist(self.pts[-1], q), 0.0)   # past the end: straight on


def _angle(u, v) -> float:
    """The signed turn from direction u to direction v, in degrees."""
    return math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]))


def _pattern(dash) -> list[float] | None:
    pat = [max(float(v), 0.0) for v in dash or []]
    if len(pat) % 2:
        pat += pat     # as in PDF and SVG, an odd list repeats with dashes and gaps swapped
    if not pat or sum(pat) <= EPS or sum(pat[1::2]) <= EPS:
        return None    # nothing, or no gaps: a solid line
    return pat


def _elements(pat: list[float], n: int, start_corner: bool, end_corner: bool):
    """The dashes and gaps along a stretch: from the middle of a first dash (at a corner) or its
    start (at a line end), through n repeats, to the middle (corner) or end of a first dash.
    Items are (is_dash, length, role) with role "head"/"tail" for halves of corner dashes."""
    d0 = pat[0]
    if n == 0:   # shorter than one repeat: a single dash, or half of one meeting a corner's
        role = "head" if start_corner else "tail" if end_corner else None
        return [(True, d0 / 2 if (start_corner or end_corner) else d0, role)]
    out = [(True, d0 / 2 if start_corner else d0, "head" if start_corner else None)]
    out += [(i % 2 == 0, v, None) for i, v in enumerate(pat) if i > 0]
    for _ in range(n - 1):
        out += [(i % 2 == 0, v, None) for i, v in enumerate(pat)]
    out.append((True, d0 / 2 if end_corner else d0, "tail" if end_corner else None))
    return out


def _fit(run: _Run, pat: list[float], start_corner: bool, end_corner: bool):
    """Dash intervals (a, b, role) along a run: the whole number of repeats that changes the
    pattern least, scaled to end exactly at the run's end."""
    period, d0 = sum(pat), pat[0]
    # Beyond its whole repeats, a stretch holds half a first dash at each line end it reaches
    fixed = (0.0 if start_corner else d0 / 2) + (0.0 if end_corner else d0 / 2)
    least = 1 if fixed <= EPS else 0
    guess = max((run.length - fixed) / period, 0.0)
    cands = {max(math.floor(guess), least), max(math.ceil(guess), least)}
    n = min(cands, key=lambda m: abs(math.log(max(run.length, EPS) / max(m * period + fixed, EPS))))
    elems = _elements(pat, n, start_corner, end_corner)

    def walk(s, record=False):
        a, out = 0.0, []
        for is_dash, v, role in elems:
            if is_dash:
                if record:
                    out.append((a, a + v * s, role))
                a += v * s
            else:
                a = run.advance(a, v * s)
        return a, out

    s = run.length / max(n * period + fixed, EPS)
    for _ in range(40):   # gaps measured straight across take a little more on curves
        used, _o = walk(s)
        if abs(used - run.length) <= 1e-9 * max(run.length, 1.0):
            break
        s *= run.length / max(used, EPS)
    _used, out = walk(s, record=True)
    a, _b, role = out[-1]   # every stretch ends on a dash: land it exactly on the end
    out[-1] = (min(a, run.length), run.length, role)
    return out


class DashLayout:
    """Where an evenly dashed stroke's dashes go: per subpath, the stretches that are drawn."""

    def __init__(self, parts: list[tuple[_Sub, list[tuple[float, float]]]]):
        self.parts = parts

    def path(self, extend: float = 0.0) -> Path:
        """The dashes as subpaths, each lengthened by `extend` at both ends (square caps drawn
        as flat ones, and outlines around flat-ended dashes)."""
        out = Path()
        for sub, spans in self.parts:
            for a, b in spans:
                sub.emit(a - extend, b + extend, out)
        return out


def layout(path: Path, dash) -> DashLayout | None:
    """Even dashes for a path and a dash pattern in points (as from geometry.dash_array, caps
    already allowed for); None if the pattern is solid."""
    pat = _pattern(dash)
    if pat is None:
        return None
    period = sum(pat)
    parts = []
    for pieces, closed in _subpaths(path):
        sub = _Sub(pieces, closed)
        if sub.length <= EPS:
            continue
        # Corners closer together than half a repeat would crowd: keep the first of them
        anchors = []
        for c in sub.corners():
            if (not anchors and (closed or c >= period / 2)) or (anchors and c - anchors[-1] >= period / 2):
                anchors.append(c)
        if closed and len(anchors) > 1 and sub.length - anchors[-1] + anchors[0] < period / 2:
            anchors.pop()
        if not closed:
            anchors = [c for c in anchors if sub.length - c >= period / 2]
        spans: list[tuple[float, float, str | None]] = []
        if closed:
            starts = anchors or [0.0]
            for k, a0 in enumerate(starts):
                a1 = starts[k + 1] if k + 1 < len(starts) else starts[0] + sub.length
                for a, b, role in _fit(_Run(sub, a0, a1 - a0), pat, True, True):
                    spans.append((a0 + a, a0 + b, role))
        else:
            stops = [0.0] + anchors + [sub.length]
            for k in range(len(stops) - 1):
                a0, a1 = stops[k], stops[k + 1]
                for a, b, role in _fit(_Run(sub, a0, a1 - a0), pat, k > 0, k + 1 < len(stops) - 1):
                    spans.append((a0 + a, a0 + b, role))
        parts.append((sub, _merge(spans, sub.length if closed else None)))
    return DashLayout(parts)


def _merge(spans, loop: float | None) -> list[tuple[float, float]]:
    """Join the halves of each corner dash into one dash around the corner (and, on closed
    paths, the last half with the first, across the start)."""
    out: list[list] = []
    for a, b, role in spans:
        if role == "head" and out and out[-1][2] == "tail" and abs(out[-1][1] - a) < 1e-6:
            out[-1][1], out[-1][2] = b, None
        else:
            out.append([a, b, role])
    if loop is not None and len(out) > 1 and out[0][2] == "head" and out[-1][2] == "tail":
        first = out.pop(0)
        out[-1][1] = first[1] + loop
    return [(a, b) for a, b, _role in out]


def _subpaths(path: Path) -> list[tuple[list[_Piece], bool]]:
    """Each subpath's pieces, without zero-length ones; closing lines made explicit."""
    out = []
    pieces: list[_Piece] = []
    cur = start = None
    for s in path.segs:
        if s[0] == "M":
            if pieces:
                out.append((pieces, False))
            pieces, cur, start = [], (s[1], s[2]), (s[1], s[2])
        elif s[0] == "L" and cur is not None:
            p = (s[1], s[2])
            if math.dist(cur, p) > EPS:
                pieces.append(_Piece((cur, p)))
            cur = p
        elif s[0] == "C" and cur is not None:
            piece = _Piece((cur, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])))
            if piece.length > EPS:
                pieces.append(piece)
            cur = (s[5], s[6])
        elif s[0] == "Z" and cur is not None:
            if math.dist(cur, start) > EPS:
                pieces.append(_Piece((cur, start)))
            if pieces:
                out.append((pieces, True))
            pieces, cur = [], start
    if pieces:
        out.append((pieces, False))
    return out

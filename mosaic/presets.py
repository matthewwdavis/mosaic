"""PowerPoint's built-in shapes (DrawingML presets), drawn from their published definitions.

data/presets.json holds the formulas of all 187 presets in the Office Open XML standard
(tools/build_presets.py converts the standard's presetShapeDefinitions.xml). A shape's guides
are evaluated in points for its frame, so mosaic draws, adjusts and places text in every
preset the way PowerPoint does, and slides import with their shapes intact.

Items store adjust values as fractions (DrawingML's 1/100000 units) or, for angles, degrees
(its 1/60000-degree units): a rounded rectangle's {"adj": 0.16667}, an arc's
{"adj1": 270, "adj2": 0}.
"""
from __future__ import annotations

import functools
import json
import math
import re
from pathlib import Path as _FilePath

from .geometry import Matrix, Path, ShapePath, corner_count

ANGLE_UNIT = 60000.0       # DrawingML angles: 1/60000 degree
FRACTION_UNIT = 100000.0   # DrawingML proportions: 1/100000


# ---------------------------------------------------------------------------
# Guide formulas
# ---------------------------------------------------------------------------

def builtin_guides(w: float, h: float) -> dict[str, float]:
    ss = min(w, h)
    g = {"w": w, "h": h, "l": 0.0, "t": 0.0, "r": w, "b": h, "hc": w / 2, "vc": h / 2,
         "ss": ss, "ls": max(w, h), "cd2": 10800000.0, "cd4": 5400000.0, "cd8": 2700000.0,
         "3cd4": 16200000.0, "3cd8": 8100000.0, "5cd8": 13500000.0, "7cd8": 18900000.0}
    for n in (2, 3, 4, 5, 6, 8, 10, 12, 16, 32):
        g[f"wd{n}"] = w / n
        g[f"hd{n}"] = h / n
        g[f"ssd{n}"] = ss / n
    return g


def _ang(v: float) -> float:
    return math.radians(v / ANGLE_UNIT)


def apply_op(op: str, v: list[float]) -> float:
    if op == "val":
        return v[0]
    if op == "*/":
        return v[0] * v[1] / v[2] if v[2] else 0.0
    if op == "+-":
        return v[0] + v[1] - v[2]
    if op == "+/":
        return (v[0] + v[1]) / v[2] if v[2] else 0.0
    if op == "?:":
        return v[1] if v[0] > 0 else v[2]
    if op == "abs":
        return abs(v[0])
    if op == "at2":
        return math.degrees(math.atan2(v[1], v[0])) * ANGLE_UNIT
    if op == "cat2":
        return v[0] * math.cos(math.atan2(v[2], v[1]))
    if op == "sat2":
        return v[0] * math.sin(math.atan2(v[2], v[1]))
    if op == "cos":
        return v[0] * math.cos(_ang(v[1]))
    if op == "sin":
        return v[0] * math.sin(_ang(v[1]))
    if op == "tan":
        return v[0] * math.tan(_ang(v[1]))
    if op == "max":
        return max(v[0], v[1])
    if op == "min":
        return min(v[0], v[1])
    if op == "mod":
        return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if op == "pin":
        return min(max(v[1], v[0]), v[2])
    if op == "sqrt":
        return math.sqrt(max(v[0], 0.0))
    raise ValueError(f"unknown guide operator {op}")


def lookup(x, env: dict[str, float]) -> float:
    """A formula argument: a number, or the name of a guide evaluated before it."""
    if isinstance(x, float):
        return x
    if x in env:
        return env[x]
    try:
        return float(x)
    except ValueError:
        raise KeyError(x) from None


def eval_formula(fmla: str, env: dict[str, float]) -> float:
    parts = fmla.split()
    return apply_op(parts[0], [lookup(a, env) for a in parts[1:]])


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------

def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return s


@functools.lru_cache(maxsize=None)
def _presets() -> dict:
    raw = json.loads((_FilePath(__file__).parent / "data" / "presets.json").read_text())
    out = {}
    for name, d in raw.items():
        out[name] = {
            "av": [(n, float(f.split()[1])) for n, f in d["av"]],
            "gd": [(n, f.split()[0], [_num(a) for a in f.split()[1:]]) for n, f in d["gd"]],
            "ah": [{k: (_num(v) if k.startswith(("min", "max")) else v) for k, v in hd.items()}
                   for hd in d["ah"]],
            "rect": [_num(v) for v in d.get("rect", ["l", "t", "r", "b"])],
            "paths": [dict(p, cmds=[[c[0], *[_num(a) for a in c[1:]]] for c in p["cmds"]]) for p in d["paths"]],
            "angles": {hd["gdRefAng"] for hd in d["ah"] if hd.get("gdRefAng")},
        }
    return out


def is_preset(geom: str) -> bool:
    return geom in _presets()


def _unit(geom: str, name: str) -> float:
    return ANGLE_UNIT if name in _presets()[geom]["angles"] else FRACTION_UNIT


def defaults(geom: str) -> dict[str, float]:
    """Adjust values a new shape starts with, in stored units."""
    return {n: v / _unit(geom, n) for n, v in _presets()[geom]["av"]}


def to_stored(geom: str, name: str, raw: float) -> float:
    """A DrawingML adjust value (as written in .pptx files) in the units items store."""
    return raw / _unit(geom, name)


def _raw(geom: str, adj: dict | None) -> dict[str, float]:
    return {n: float(v) * _unit(geom, n) for n, v in (adj or {}).items() if isinstance(v, (int, float))}


def _guides(geom: str, w: float, h: float, raw: dict[str, float]) -> dict[str, float]:
    d = _presets()[geom]
    env = builtin_guides(w, h)
    for name, default in d["av"]:
        env[name] = raw.get(name, default)
    for name, op, args in d["gd"]:
        try:
            env[name] = apply_op(op, [lookup(a, env) for a in args])
        except (KeyError, ValueError, IndexError, ZeroDivisionError, OverflowError):
            env[name] = 0.0
    return env


def guides(geom: str, w: float, h: float, adj: dict | None = None) -> dict[str, float]:
    return _guides(geom, w, h, _raw(geom, adj))


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _build(p: dict, env: dict[str, float], w: float, h: float) -> Path:
    path = Path()
    for cmd in p["cmds"]:
        op = cmd[0]
        v = [lookup(a, env) for a in cmd[1:]]
        if op == "M":
            path.move_to(v[0], v[1])
        elif op == "L":
            path.line_to(v[0], v[1])
        elif op == "C":
            path.curve_to(*v)
        elif op == "Q":
            path.quad_to(*v)
        elif op == "A":
            path.arc_to(v[0], v[1], v[2] / ANGLE_UNIT, v[3] / ANGLE_UNIT)
        elif op == "Z":
            path.close()
    # A path with its own coordinate space (w/h) is drawn there, then stretched over the frame
    pw, ph = p.get("w") or 0.0, p.get("h") or 0.0
    if pw or ph:
        path = path.transformed(Matrix.scale(w / pw if pw else 1.0, h / ph if ph else 1.0))
    return path


def shape_paths(geom: str, w: float, h: float, adj: dict | None = None) -> list[ShapePath]:
    """The paths of a preset shape filling a w x h frame. Unknown presets draw a rectangle."""
    d = _presets().get(geom)
    if d is None:
        return [ShapePath(Path().move_to(0, 0).line_to(w, 0).line_to(w, h).line_to(0, h).close())]
    env = guides(geom, w, h, adj)
    out = []
    for p in d["paths"]:
        fill = p.get("fill", "norm")
        out.append(ShapePath(_build(p, env, w, h), fill=fill != "none", stroke=p.get("stroke", True),
                             shade=None if fill in ("norm", "none") else fill))
    return out


def text_rect(geom: str, w: float, h: float, adj: dict | None = None) -> tuple[float, float, float, float]:
    """Area text is laid out in, before insets (x0, y0, x1, y1 in frame coordinates)."""
    d = _presets().get(geom)
    if d is None:
        return (0.0, 0.0, w, h)
    env = guides(geom, w, h, adj)
    try:
        x0, y0, x1, y1 = (lookup(v, env) for v in d["rect"])
    except KeyError:
        return (0.0, 0.0, w, h)
    return (x0, y0, x1, y1)


# Presets that are lines rather than outlines, so they can take arrowheads
_LINE_LIKE = {"arc", "leftBracket", "rightBracket", "leftBrace", "rightBrace", "line", "lineInv",
              "straightConnector1", "bentConnector2", "bentConnector3", "bentConnector4", "bentConnector5",
              "curvedConnector2", "curvedConnector3", "curvedConnector4", "curvedConnector5"}


@functools.lru_cache(maxsize=None)
def is_open(geom: str) -> bool:
    """Whether the shape is a line drawn as one open path, so line ends (arrowheads) apply."""
    if geom not in _LINE_LIKE or not is_preset(geom):
        return False
    strokes = [sp.path for sp in shape_paths(geom, 100.0, 60.0) if sp.stroke and not sp.path.is_empty]
    return len(strokes) == 1 and len(strokes[0].subpaths()) == 1 and not strokes[0].is_closed()


@functools.lru_cache(maxsize=None)
def encloses(geom: str) -> bool:
    """Whether the shape's own line runs all the way round its area, so with no fill its outline
    can still keep inside or outside that area (resolve.shape_interior)."""
    if not is_preset(geom) or is_open(geom):
        return False
    from .regions import edge_traced
    paths = [sp for sp in shape_paths(geom, 100.0, 60.0) if not sp.path.is_empty]
    return edge_traced([(sp.path, False) for sp in paths if sp.fill], [sp.path for sp in paths if sp.stroke], 0.5)


@functools.lru_cache(maxsize=None)
def has_corners(geom: str) -> bool:
    """Whether the shape's outline has corners between straight edges, which Corner rounding
    rounds (an arc's filled wedge doesn't count)."""
    if not is_preset(geom):
        return False
    return corner_count([sp.path for sp in shape_paths(geom, 100.0, 60.0) if sp.stroke]) > 0


# ---------------------------------------------------------------------------
# Adjust handles (PowerPoint's yellow handles)
# ---------------------------------------------------------------------------

def handles(geom: str, w: float, h: float, adj: dict | None = None) -> list[list[float]]:
    """Where each adjust handle sits, in frame coordinates."""
    d = _presets().get(geom)
    if not d or not d["ah"]:
        return []
    env = guides(geom, w, h, adj)
    out = []
    for hd in d["ah"]:
        try:
            out.append([lookup(hd["pos"][0], env), lookup(hd["pos"][1], env)])
        except KeyError:
            out.append([0.0, 0.0])
    return out


def _limits(hd: dict, key: str, env: dict[str, float]) -> tuple[float, float]:
    lo = lookup(hd.get(f"min{key}", 0.0), env)
    hi = lookup(hd.get(f"max{key}", 0.0), env)
    return (lo, hi) if lo <= hi else (hi, lo)


def _minimize(f, lo: float, hi: float, around: float | None = None) -> float:
    """The value in [lo, hi] where f is smallest: a coarse scan, then a golden-section refine.
    With `around`, only a window of a tenth of the range around that value is searched."""
    if around is not None:
        span = (hi - lo) * 0.05
        lo, hi = max(lo, around - span), min(hi, around + span)
    if hi - lo <= 0:
        return lo
    samples = 48 if around is None else 12
    xs = [lo + (hi - lo) * i / samples for i in range(samples + 1)]
    fs = [f(x) for x in xs]
    i = min(range(len(xs)), key=fs.__getitem__)
    a, b = xs[max(i - 1, 0)], xs[min(i + 1, samples)]
    g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(40):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    best = (a + b) / 2
    return best if f(best) <= fs[i] else xs[i]


def _polish(pos2, v1: float, v2: float, lim1, lim2, x: float, y: float) -> tuple[float, float]:
    """Newton steps on two adjust values at once, kept while they bring the handle closer to (x, y)."""
    p0 = pos2(v1, v2)
    e0 = math.hypot(p0[0] - x, p0[1] - y)
    for _ in range(8):
        if e0 < 1e-6:
            break
        h1 = max((lim1[1] - lim1[0]) * 1e-6, 1e-9)
        h2 = max((lim2[1] - lim2[0]) * 1e-6, 1e-9)
        pa, pb = pos2(v1 + h1, v2), pos2(v1, v2 + h2)
        j00, j10 = (pa[0] - p0[0]) / h1, (pa[1] - p0[1]) / h1
        j01, j11 = (pb[0] - p0[0]) / h2, (pb[1] - p0[1]) / h2
        det = j00 * j11 - j01 * j10
        if abs(det) < 1e-12:
            break
        ex, ey = p0[0] - x, p0[1] - y
        n1 = min(max(v1 - (j11 * ex - j01 * ey) / det, lim1[0]), lim1[1])
        n2 = min(max(v2 - (j00 * ey - j10 * ex) / det, lim2[0]), lim2[1])
        pn = pos2(n1, n2)
        en = math.hypot(pn[0] - x, pn[1] - y)
        if en >= e0:
            break
        v1, v2, p0, e0 = n1, n2, pn, en
    return v1, v2


def drag_handle(geom: str, w: float, h: float, adj: dict | None, index: int, x: float, y: float) -> dict:
    """New adjust values (stored units) that bring handle `index` as close as possible to the
    frame point (x, y). Each value stays in its handle's range, as in PowerPoint."""
    d = _presets()[geom]
    hd = d["ah"][index]
    raw = {n: v for n, v in d["av"]}
    raw.update(_raw(geom, adj))

    def pos(name: str, v: float) -> tuple[float, float]:
        env = _guides(geom, w, h, dict(raw, **{name: v}))
        return lookup(hd["pos"][0], env), lookup(hd["pos"][1], env)

    if hd["kind"] == "xy":
        steps = [("gdRefX", "X", lambda p: abs(p[0] - x)), ("gdRefY", "Y", lambda p: abs(p[1] - y))]
    else:
        dist = (lambda p: math.hypot(p[0] - x, p[1] - y))
        steps = [("gdRefAng", "Ang", dist), ("gdRefR", "R", dist)]
    steps = [s for s in steps if hd.get(s[0])]
    # One value at a time; a handle that sets two (an angle and a radius) goes round again,
    # searching near the last answer, then both are polished together
    for rnd in range(2 if len(steps) > 1 else 1):
        for ref, key, cost in steps:
            name = hd[ref]
            lo, hi = _limits(hd, key, _guides(geom, w, h, raw))
            raw[name] = _minimize(lambda v: cost(pos(name, v)), lo, hi, around=raw[name] if rnd else None)
    if len(steps) == 2:
        (r1, k1, _), (r2, k2, _) = steps
        n1, n2 = hd[r1], hd[r2]
        env = _guides(geom, w, h, raw)

        def pos2(a: float, b: float) -> tuple[float, float]:
            e = _guides(geom, w, h, dict(raw, **{n1: a, n2: b}))
            return lookup(hd["pos"][0], e), lookup(hd["pos"][1], e)

        raw[n1], raw[n2] = _polish(pos2, raw[n1], raw[n2], _limits(hd, k1, env), _limits(hd, k2, env), x, y)
    out = dict(adj or {})
    for ref in ("gdRefX", "gdRefY", "gdRefAng", "gdRefR"):
        if hd.get(ref):
            out[hd[ref]] = round(to_stored(geom, hd[ref], raw[hd[ref]]), 6)
    return out


def clamp_adjust(geom: str, w: float, h: float, adj: dict | None, name: str, value: float) -> float:
    """An adjust value typed into the properties panel, kept inside its handle's range."""
    d = _presets().get(geom)
    if not d:
        return value
    raw = {n: v for n, v in d["av"]}
    raw.update(_raw(geom, adj))
    env = _guides(geom, w, h, raw)
    v = value * _unit(geom, name)
    for hd in d["ah"]:
        for ref, key in (("gdRefX", "X"), ("gdRefY", "Y"), ("gdRefAng", "Ang"), ("gdRefR", "R")):
            if hd.get(ref) == name:
                lo, hi = _limits(hd, key, env)
                v = min(max(v, lo), hi)
    return round(to_stored(geom, name, v), 6)


# ---------------------------------------------------------------------------
# The Shapes menu
# ---------------------------------------------------------------------------

GALLERY = [
    ("Rectangles", "rect roundRect snip1Rect snip2SameRect snip2DiagRect snipRoundRect round1Rect "
                   "round2SameRect round2DiagRect"),
    ("Basic shapes", "ellipse triangle rtTriangle parallelogram trapezoid diamond pentagon hexagon heptagon "
                     "octagon decagon dodecagon pie chord teardrop frame halfFrame corner diagStripe plus plaque "
                     "can cube bevel donut noSmoking blockArc foldedCorner smileyFace heart lightningBolt sun "
                     "moon cloud arc"),
    ("Block arrows", "rightArrow leftArrow upArrow downArrow leftRightArrow upDownArrow quadArrow "
                     "leftRightUpArrow bentArrow uturnArrow leftUpArrow bentUpArrow curvedRightArrow "
                     "curvedLeftArrow curvedUpArrow curvedDownArrow stripedRightArrow notchedRightArrow "
                     "homePlate chevron circularArrow"),
    ("Stars", "star4 star5 star6 star7 star8 star10 star12 star16 star24 star32"),
    ("Brackets and braces", "leftBracket rightBracket leftBrace rightBrace bracketPair bracePair"),
    ("Equation symbols", "mathPlus mathMinus mathMultiply mathDivide mathEqual mathNotEqual"),
]

NAMES = {
    "rect": "Rectangle", "roundRect": "Rounded rectangle", "snip1Rect": "Snipped corner rectangle",
    "snip2SameRect": "Snipped same-side corners", "snip2DiagRect": "Snipped diagonal corners",
    "snipRoundRect": "Snipped and rounded corners", "round1Rect": "One rounded corner",
    "round2SameRect": "Rounded same-side corners", "round2DiagRect": "Rounded diagonal corners",
    "ellipse": "Ellipse", "triangle": "Triangle", "rtTriangle": "Right triangle", "parallelogram": "Parallelogram",
    "trapezoid": "Trapezoid", "diamond": "Diamond", "pentagon": "Pentagon", "hexagon": "Hexagon",
    "heptagon": "Heptagon", "octagon": "Octagon", "decagon": "Decagon", "dodecagon": "Dodecagon",
    "pie": "Partial circle", "chord": "Chord", "teardrop": "Teardrop", "frame": "Frame", "halfFrame": "Half frame",
    "corner": "L-shape", "diagStripe": "Diagonal stripe", "plus": "Cross", "plaque": "Plaque", "can": "Cylinder",
    "cube": "Cube", "bevel": "Bevel", "donut": "Ring", "noSmoking": "“No” symbol", "blockArc": "Block arc",
    "foldedCorner": "Folded corner", "smileyFace": "Smiley face", "heart": "Heart", "lightningBolt": "Lightning bolt",
    "sun": "Sun", "moon": "Moon", "cloud": "Cloud", "arc": "Arc",
    "rightArrow": "Right arrow", "leftArrow": "Left arrow", "upArrow": "Up arrow", "downArrow": "Down arrow",
    "leftRightArrow": "Left-right arrow", "upDownArrow": "Up-down arrow", "quadArrow": "Four-way arrow",
    "leftRightUpArrow": "Left-right-up arrow", "bentArrow": "Bent arrow", "uturnArrow": "U-turn arrow",
    "leftUpArrow": "Left-up arrow", "bentUpArrow": "Bent-up arrow", "curvedRightArrow": "Curved right arrow",
    "curvedLeftArrow": "Curved left arrow", "curvedUpArrow": "Curved up arrow", "curvedDownArrow": "Curved down arrow",
    "stripedRightArrow": "Striped right arrow", "notchedRightArrow": "Notched right arrow",
    "homePlate": "Pentagon arrow", "chevron": "Chevron", "circularArrow": "Circular arrow",
    "star4": "4-point star", "star5": "5-point star", "star6": "6-point star", "star7": "7-point star",
    "star8": "8-point star", "star10": "10-point star", "star12": "12-point star", "star16": "16-point star",
    "star24": "24-point star", "star32": "32-point star",
    "leftBracket": "Left bracket", "rightBracket": "Right bracket", "leftBrace": "Left brace",
    "rightBrace": "Right brace", "bracketPair": "Double bracket", "bracePair": "Double brace",
    "mathPlus": "Plus sign", "mathMinus": "Minus sign", "mathMultiply": "Multiplication sign",
    "mathDivide": "Division sign", "mathEqual": "Equals sign", "mathNotEqual": "Not-equal sign",
    "line": "Line", "straightConnector1": "Straight connector",
}

# What each adjust value does, for the properties panel: (name, label[, scale]). The panel shows
# a proportion as raw / scale in percent (scale 100000 unless given) and an angle in degrees.
# Values not listed (e.g. a regular pentagon's proportions) keep their defaults.
_ARROW2 = [("adj1", "Shaft width"), ("adj2", "Head length")]
_ARROW3 = [("adj1", "Shaft width"), ("adj2", "Head width"), ("adj3", "Head length")]
_STAR = [("adj", "Inner radius", 50000.0)]
ADJUSTMENTS = {
    "roundRect": [("adj", "Corner radius")], "snip1Rect": [("adj", "Corner cut")],
    "snip2SameRect": [("adj1", "Top corner cut"), ("adj2", "Bottom corner cut")],
    "snip2DiagRect": [("adj1", "Cut, top left and bottom right"), ("adj2", "Cut, top right and bottom left")],
    "snipRoundRect": [("adj1", "Rounded corner"), ("adj2", "Cut corner")],
    "round1Rect": [("adj", "Corner radius")],
    "round2SameRect": [("adj1", "Top corner radius"), ("adj2", "Bottom corner radius")],
    "round2DiagRect": [("adj1", "Radius, top left and bottom right"), ("adj2", "Radius, top right and bottom left")],
    "triangle": [("adj", "Apex position")], "parallelogram": [("adj", "Slant")], "trapezoid": [("adj", "Slant")],
    "hexagon": [("adj", "Corner inset")], "octagon": [("adj", "Corner cut")],
    "pie": [("adj1", "Start angle"), ("adj2", "End angle")], "chord": [("adj1", "Start angle"), ("adj2", "End angle")],
    "arc": [("adj1", "Start angle"), ("adj2", "End angle")],
    "blockArc": [("adj1", "Start angle"), ("adj2", "End angle"), ("adj3", "Thickness")],
    "teardrop": [("adj", "Point")], "frame": [("adj1", "Border width")],
    "halfFrame": [("adj1", "Top width"), ("adj2", "Side width")],
    "corner": [("adj1", "Bottom width"), ("adj2", "Side width")],
    "diagStripe": [("adj", "Stripe width")], "plus": [("adj", "Corner size")], "plaque": [("adj", "Corner size")],
    "can": [("adj", "Top depth")], "cube": [("adj", "Depth")], "bevel": [("adj", "Bevel width")],
    "donut": [("adj", "Ring thickness")], "noSmoking": [("adj", "Ring thickness")],
    "foldedCorner": [("adj", "Fold size")], "smileyFace": [("adj", "Smile")], "sun": [("adj", "Ray length")],
    "moon": [("adj", "Thickness")],
    "rightArrow": _ARROW2, "leftArrow": _ARROW2, "upArrow": _ARROW2, "downArrow": _ARROW2,
    "leftRightArrow": _ARROW2, "upDownArrow": _ARROW2, "stripedRightArrow": _ARROW2, "notchedRightArrow": _ARROW2,
    "quadArrow": _ARROW3, "leftRightUpArrow": _ARROW3, "leftUpArrow": _ARROW3, "bentUpArrow": _ARROW3,
    "curvedRightArrow": _ARROW3, "curvedLeftArrow": _ARROW3, "curvedUpArrow": _ARROW3, "curvedDownArrow": _ARROW3,
    "bentArrow": _ARROW3 + [("adj4", "Bend radius")],
    "uturnArrow": _ARROW3 + [("adj4", "Bend radius"), ("adj5", "Height")],
    "homePlate": [("adj", "Point depth")], "chevron": [("adj", "Point depth")],
    "circularArrow": [("adj1", "Thickness"), ("adj5", "Head width"), ("adj2", "Head length"),
                      ("adj4", "Start angle"), ("adj3", "End angle")],
    "star4": _STAR, "star5": _STAR, "star6": _STAR, "star7": _STAR, "star8": _STAR, "star10": _STAR,
    "star12": _STAR, "star16": _STAR, "star24": _STAR, "star32": _STAR,
    "leftBracket": [("adj", "End curve")], "rightBracket": [("adj", "End curve")],
    "leftBrace": [("adj1", "End curve"), ("adj2", "Point position")],
    "rightBrace": [("adj1", "End curve"), ("adj2", "Point position")],
    "bracketPair": [("adj", "Corner curve")], "bracePair": [("adj", "Curve size")],
    "mathPlus": [("adj1", "Bar thickness")], "mathMinus": [("adj1", "Bar thickness")],
    "mathMultiply": [("adj1", "Bar thickness")],
    "mathDivide": [("adj1", "Bar thickness"), ("adj2", "Dot spacing"), ("adj3", "Dot size")],
    "mathEqual": [("adj1", "Bar thickness"), ("adj2", "Gap")],
    "mathNotEqual": [("adj1", "Bar thickness"), ("adj2", "Slash angle"), ("adj3", "Gap")],
}

# Icon boxes (width, height in a 24 x 24 icon) for shapes that aren't square
_ICON_BOX = {
    "rect": (21, 15), "roundRect": (21, 15), "snip1Rect": (21, 15), "snip2SameRect": (21, 15),
    "snip2DiagRect": (21, 15), "snipRoundRect": (21, 15), "round1Rect": (21, 15), "round2SameRect": (21, 15),
    "round2DiagRect": (21, 15), "ellipse": (21, 16), "parallelogram": (22, 14), "trapezoid": (21, 15),
    "hexagon": (21, 18), "can": (15, 20), "cube": (19, 19), "frame": (20, 18), "plaque": (21, 16),
    "foldedCorner": (19, 20), "moon": (12, 20), "lightningBolt": (17, 20), "cloud": (22, 16), "chord": (20, 20),
    "rightArrow": (21, 14), "leftArrow": (21, 14), "leftRightArrow": (22, 12), "stripedRightArrow": (21, 14),
    "notchedRightArrow": (21, 14), "homePlate": (21, 14), "chevron": (17, 16), "upArrow": (14, 21),
    "downArrow": (14, 21), "upDownArrow": (12, 22), "curvedRightArrow": (12, 21), "curvedLeftArrow": (12, 21),
    "curvedUpArrow": (21, 12), "curvedDownArrow": (21, 12), "uturnArrow": (19, 20), "bentArrow": (19, 20),
    "leftBracket": (6, 20), "rightBracket": (6, 20), "leftBrace": (8, 20), "rightBrace": (8, 20),
    "bracketPair": (21, 16), "bracePair": (21, 16), "mathMinus": (20, 20), "mathEqual": (20, 20),
}


# Icons drawn with stronger corners than the shapes' defaults, so the rectangles tell apart
_ICON_ADJ = {
    "roundRect": {"adj": 0.3}, "snip1Rect": {"adj": 0.3}, "snip2SameRect": {"adj1": 0.3},
    "snip2DiagRect": {"adj2": 0.3}, "snipRoundRect": {"adj1": 0.3, "adj2": 0.3}, "round1Rect": {"adj": 0.35},
    "round2SameRect": {"adj1": 0.35}, "round2DiagRect": {"adj1": 0.35},
}


def display_name(geom: str) -> str:
    if geom in NAMES:
        return NAMES[geom]
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", geom).lower()
    return words[:1].upper() + words[1:]


def icon_box(geom: str) -> list[float]:
    """Where the shape sits in its 24 x 24 icon: x, y, width, height."""
    bw, bh = _ICON_BOX.get(geom, (20, 20))
    return [(24 - bw) / 2, (24 - bh) / 2, float(bw), float(bh)]


def icon_path(geom: str) -> str:
    """SVG path data of the shape's outline in a 24 x 24 icon."""
    x, y, bw, bh = icon_box(geom)
    paths = [sp.path for sp in shape_paths(geom, bw, bh, _ICON_ADJ.get(geom)) if sp.stroke]
    return "".join(p.transformed(Matrix.translate(x, y)).to_svg(2) for p in paths)


def _adjust_info(geom: str) -> list[dict]:
    d = _presets()[geom]
    refs = []
    for hd in d["ah"]:
        for ref in ("gdRefX", "gdRefY", "gdRefAng", "gdRefR"):
            if hd.get(ref) and hd[ref] not in refs:
                refs.append(hd[ref])
    labels = ADJUSTMENTS.get(geom) or [(n, f"Adjustment {i + 1}") for i, n in enumerate(refs)]
    dflt = defaults(geom)
    out = []
    for entry in labels:
        name, label = entry[0], entry[1]
        if name not in dflt:
            continue
        angle = name in d["angles"]
        lo = hi = None
        for hd in d["ah"]:
            for ref, key in (("gdRefX", "X"), ("gdRefY", "Y"), ("gdRefAng", "Ang"), ("gdRefR", "R")):
                if hd.get(ref) == name:
                    a, b = hd.get(f"min{key}"), hd.get(f"max{key}")
                    lo = a / _unit(geom, name) if isinstance(a, float) else None
                    hi = b / _unit(geom, name) if isinstance(b, float) else None
        # Shown value = stored value * factor (percent of the scale, or degrees)
        factor = 1.0 if angle else 100.0 * FRACTION_UNIT / (entry[2] if len(entry) > 2 else FRACTION_UNIT)
        out.append({"name": name, "label": label, "unit": "deg" if angle else "%", "factor": factor,
                    "default": dflt[name], "min": lo, "max": hi})
    return out


@functools.lru_cache(maxsize=None)
def catalog() -> dict:
    """Everything the editor needs to offer shapes: the menu's groups, and for every preset its
    name, adjustments, whether it can be rounded or take arrowheads, and a menu icon."""
    shapes = {}
    in_menu = {g for _, names in GALLERY for g in names.split()}
    for geom in _presets():
        shapes[geom] = {"name": display_name(geom), "adjust": _adjust_info(geom), "corners": has_corners(geom),
                        "open": is_open(geom), "closed": encloses(geom)}
        if geom in in_menu:
            shapes[geom]["icon"] = icon_path(geom)
            shapes[geom]["box"] = icon_box(geom)
    return {"groups": [{"title": t, "shapes": names.split()} for t, names in GALLERY], "shapes": shapes}

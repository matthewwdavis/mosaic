"""Lines drawn inside placed PDFs and SVGs: every stroke a page paints, how wide it prints and
where it is, for the pre-export check.

A width is the narrowest the line gets once its transforms are applied (a line stretched more
one way than the other is thinnest across the short way), in the source's points. A box is in
the source's displayed coordinates (points from the top left, after a PDF page's /Rotate), the
space a picture's crop is in.

A stroke in the same colour as the fill it goes round is left out: it only makes the fill a
little bigger and can't be seen as a line. ggplot draws its points that way, and with
stroke = 0 R's pdf() gives them a 0.01 pt border. A PDF line 0 wide is a hairline, drawn as thin
as the device can draw it; an SVG line 0 wide isn't drawn at all.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

import numpy as np

from .geometry import Matrix

TOUCH = 0.01   # pt: a line this close to a crop's edge counts as inside it


def thinnest_scale(m: Matrix) -> float:
    """How much a transform multiplies a line's width by, across the line's narrowest way (the
    smaller singular value)."""
    s = m.a * m.a + m.b * m.b + m.c * m.c + m.d * m.d
    det = m.a * m.d - m.b * m.c
    return math.sqrt(max(s - math.sqrt(max(s * s - 4 * det * det, 0.0)), 0.0) / 2)


@lru_cache(maxsize=64)
def strokes(path: str, kind: str, page_index: int = 0) -> dict[float, np.ndarray]:
    """Width (points, to 4 places) -> boxes [x0, y0, x1, y1] of the lines drawn that wide. The
    file is a content-addressed copy, so it never changes under the same path."""
    found = _pdf_strokes(path, page_index) if kind == "pdf" else _svg_strokes(path)
    by_width: dict[float, list] = {}
    for width, box in found:
        by_width.setdefault(round(width, 4), []).append(box)
    return {w: np.array(boxes, dtype=float) for w, boxes in by_width.items()}


def visible_widths(found: dict[float, np.ndarray], crop) -> list[float]:
    """The widths of lines that reach into a crop box (x0, y0, x1, y1), thinnest first."""
    x0, y0, x1, y1 = crop
    return sorted(w for w, b in found.items()
                  if np.any((b[:, 0] <= x1 + TOUCH) & (b[:, 2] >= x0 - TOUCH)
                            & (b[:, 1] <= y1 + TOUCH) & (b[:, 3] >= y0 - TOUCH)))


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

STROKING = {"S", "s", "B", "B*", "b", "b*"}
PAINTING = STROKING | {"f", "F", "f*", "n"}


def _colour(op: str, operands, space: str) -> tuple:
    vals = tuple(round(float(v), 4) for v in operands if isinstance(v, (int, float)) or hasattr(v, "as_integer_ratio"))
    names = tuple(str(v) for v in operands if not (isinstance(v, (int, float)) or hasattr(v, "as_integer_ratio")))
    if op in ("G", "g"):
        return ("rgb",) + vals * 3
    if op in ("RG", "rg"):
        return ("rgb",) + vals
    if op in ("K", "k"):
        return ("cmyk",) + vals
    return (space,) + vals + names


def _display(page):
    """A page's user space -> its displayed points from the top left, and its UserUnit."""
    from .assets import display_box
    x0, y0, x1, y1 = display_box(page)
    uu = float(page.obj.get("/UserUnit", 1.0))
    w, h = (x1 - x0) * uu, (y1 - y0) * uu
    rot = int(page.obj.get("/Rotate", 0)) % 360

    def to(x: float, y: float) -> tuple[float, float]:
        u, v = (x - x0) * uu, (y - y0) * uu
        if rot == 90:
            return v, u
        if rot == 180:
            return w - u, v
        if rot == 270:
            return h - v, w - u
        return u, h - v
    return to, uu


def _pdf_strokes(path: str, page_index: int) -> list[tuple[float, tuple]]:
    import pikepdf
    out: list[tuple[float, tuple]] = []
    with pikepdf.open(path) as pdf:
        page = pdf.pages[page_index]
        to, uu = _display(page)
        parsed: dict = {}

        def ops_of(obj):
            key = obj.objgen if obj.is_indirect else id(obj)
            if key not in parsed:
                parsed[key] = [(str(op), operands) for operands, op in pikepdf.parse_content_stream(obj)]
            return key, parsed[key]

        def walk(obj, resources, st: dict, active: frozenset) -> None:
            key, ops = ops_of(obj)
            if key in active:   # a form that draws itself
                return
            active = active | {key}
            ext = resources.get("/ExtGState", {}) if resources is not None else {}
            xobjects = resources.get("/XObject", {}) if resources is not None else {}
            stack, pts = [], []
            for o, operands in ops:
                if o == "q":
                    stack.append(dict(st))
                elif o == "Q":
                    if stack:
                        st = stack.pop()
                elif o == "cm" and len(operands) == 6:
                    st["ctm"] = st["ctm"] @ Matrix(*(float(v) for v in operands))
                elif o == "w" and operands:
                    st["lw"] = float(operands[0])
                elif o == "gs" and operands:
                    g = ext.get(operands[0])
                    if g is not None:
                        if "/LW" in g:
                            st["lw"] = float(g.LW)
                        if "/CA" in g:
                            st["CA"] = float(g.CA)
                        if "/ca" in g:
                            st["ca"] = float(g.ca)
                elif o in ("RG", "G", "K", "SC", "SCN"):
                    st["sc"] = _colour(o, operands, st["ss"])
                elif o in ("rg", "g", "k", "sc", "scn"):
                    st["fc"] = _colour(o, operands, st["fs"])
                elif o == "CS" and operands:
                    st["ss"] = str(operands[0])
                    st["sc"] = (st["ss"],)
                elif o == "cs" and operands:
                    st["fs"] = str(operands[0])
                    st["fc"] = (st["fs"],)
                elif o in ("m", "l", "c", "v", "y"):
                    v = [float(x) for x in operands]
                    pts += [st["ctm"].apply(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]
                elif o == "re" and len(operands) == 4:
                    x, y, w, h = (float(v) for v in operands)
                    pts += [st["ctm"].apply(px, py) for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))]
                elif o in PAINTING:
                    fill = o in ("B", "B*", "b", "b*")
                    hidden = st["CA"] <= 0 or (fill and st["sc"] == st["fc"] and st["CA"] == st["ca"])
                    if o in STROKING and pts and not hidden:
                        shown = [to(x, y) for x, y in pts]
                        xs, ys = [p[0] for p in shown], [p[1] for p in shown]
                        out.append((st["lw"] * thinnest_scale(st["ctm"]) * uu, (min(xs), min(ys), max(xs), max(ys))))
                    pts = []
                elif o == "Do" and operands:
                    xo = xobjects.get(operands[0])
                    if xo is not None and xo.get("/Subtype") == pikepdf.Name.Form:
                        m = Matrix(*(float(v) for v in xo.get("/Matrix", [1, 0, 0, 1, 0, 0])))
                        walk(xo, xo.get("/Resources", resources), {**st, "ctm": st["ctm"] @ m}, active)

        start = {"ctm": Matrix(), "lw": 1.0, "CA": 1.0, "ca": 1.0, "sc": ("rgb", 0.0, 0.0, 0.0),
                 "fc": ("rgb", 0.0, 0.0, 0.0), "ss": "/DeviceGray", "fs": "/DeviceGray"}
        walk(page.obj, page.obj.get("/Resources"), start, frozenset())
    return out


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
# Never drawn where they stand (a <symbol> only through <use>); text has no lines to check
NOT_DRAWN = {"defs", "clipPath", "mask", "marker", "pattern", "symbol", "linearGradient", "radialGradient",
             "filter", "metadata", "title", "desc", "style", "script", "text", "image", "foreignObject"}
SHAPES = {"path", "line", "polyline", "polygon", "rect", "circle", "ellipse"}
INHERITED = ("stroke", "stroke-width", "stroke-opacity", "fill", "fill-opacity", "visibility")
PROPS = set(INHERITED) | {"opacity", "display", "vector-effect"}
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_NUM_RE = re.compile(rf"[\s,]*({_NUM})")
_FLAG_RE = re.compile(r"[\s,]*([01])")
_CMD_RE = re.compile(r"[\s,]*([MmLlHhVvCcSsQqTtAaZz])")
_TRANSFORM_RE = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_UNIT_PX = {"": 1.0, "px": 1.0, "pt": 4 / 3, "pc": 16.0, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0}


def _length(value, default: float) -> float:
    """An SVG length in user units (CSS pixels); percentages and ems count as plain numbers."""
    m = re.match(rf"\s*({_NUM})\s*([a-z%]*)", value or "")
    if not m:
        return default
    return float(m.group(1)) * _UNIT_PX.get(m.group(2), 1.0)


def _number(value, default: float) -> float:
    try:
        v = str(value).strip()
        return float(v[:-1]) / 100 if v.endswith("%") else float(v)
    except (TypeError, ValueError):
        return default


def _declarations(text: str) -> dict:
    out = {}
    for part in (text or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            k = k.strip().lower()
            if k in PROPS:
                out[k] = v.replace("!important", "").strip()
    return out


def _css_rules(root) -> list:
    """Rules from the SVG's style sheets, in the order they apply: selectors made of tags,
    classes and ids, joined by spaces (descendant) or ">" (child), as svglite and Illustrator
    write them. Other selectors are left out."""
    rules = []
    for sheet in root.iter(f"{{{SVG_NS}}}style"):
        text = re.sub(r"/\*.*?\*/", "", sheet.text or "", flags=re.S)
        for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
            decls = _declarations(block.group(2))
            if not decls:
                continue
            for sel in block.group(1).split(","):
                parts = []
                for comb, compound in re.findall(r"\s*(>?)\s*([^\s>]+)", sel):
                    m = re.fullmatch(r"([a-zA-Z][\w-]*|\*)?((?:[.#][\w-]+)*)", compound)
                    if not m:
                        parts = []
                        break
                    tag = None if m.group(1) in (None, "*") else m.group(1)
                    parts.append((comb, tag, set(re.findall(r"#([\w-]+)", m.group(2))),
                                  set(re.findall(r"\.([\w-]+)", m.group(2)))))
                if parts:
                    spec = tuple(sum(x) for x in zip(*((len(i), len(c), int(t is not None)) for _, t, i, c in parts)))
                    rules.append((spec, len(rules), parts, decls))
    rules.sort(key=lambda r: (r[0], r[1]))
    return rules


def _selects(parts: list, chain: list) -> bool:
    """Whether a rule's selector picks the last element of chain [(tag, classes, id)], root first."""
    def fits(part, node):
        _, tag, ids, classes = part
        return (tag is None or tag == node[0]) and classes <= node[1] and (not ids or ids == {node[2]})
    i = len(chain) - 1
    if not fits(parts[-1], chain[i]):
        return False
    for k in range(len(parts) - 1, 0, -1):
        i -= 1
        if parts[k][0] == ">":
            if i < 0 or not fits(parts[k - 1], chain[i]):
                return False
        else:
            while i >= 0 and not fits(parts[k - 1], chain[i]):
                i -= 1
            if i < 0:
                return False
    return True


def _transform(text: str) -> Matrix:
    m = Matrix()
    for name, args in _TRANSFORM_RE.findall(text or ""):
        v = [float(a) for a in re.findall(_NUM, args)]
        if not v:
            continue
        if name == "matrix" and len(v) == 6:
            t = Matrix(*v)
        elif name == "translate":
            t = Matrix(1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            t = Matrix(v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif name == "rotate":
            a = math.radians(v[0])
            t = Matrix(math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0.0, 0.0)
            if len(v) == 3:
                t = Matrix(1.0, 0.0, 0.0, 1.0, v[1], v[2]) @ t @ Matrix(1.0, 0.0, 0.0, 1.0, -v[1], -v[2])
        elif name == "skewX":
            t = Matrix(1.0, 0.0, math.tan(math.radians(v[0])), 1.0, 0.0, 0.0)
        elif name == "skewY":
            t = Matrix(1.0, math.tan(math.radians(v[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            continue
        m = m @ t   # the first in the list is the outermost
    return m


def path_points(d: str) -> list[tuple[float, float]]:
    """Every point a path's data passes through or pulls towards (its ends and control points,
    and an arc's reach), so their box holds the whole path."""
    pts: list[tuple[float, float]] = []
    pos, cmd = 0, None
    x = y = x0 = y0 = 0.0

    def num() -> float:
        nonlocal pos
        m = _NUM_RE.match(d, pos)
        if not m:
            raise ValueError
        pos = m.end()
        return float(m.group(1))

    def flag() -> None:
        nonlocal pos
        m = _FLAG_RE.match(d, pos)
        if not m:
            raise ValueError
        pos = m.end()
    while pos < len(d):
        m = _CMD_RE.match(d, pos)
        if m:
            cmd, pos = m.group(1), m.end()
        elif cmd is None or cmd in "Zz":
            break
        rel, c = cmd.islower(), cmd.upper()
        try:
            if c == "Z":
                x, y = x0, y0
            elif c in "ML":
                nx, ny = num(), num()
                x, y = (nx + x, ny + y) if rel else (nx, ny)
                pts.append((x, y))
                if c == "M":
                    x0, y0, cmd = x, y, "l" if rel else "L"
            elif c == "H":
                x = num() + (x if rel else 0.0)
                pts.append((x, y))
            elif c == "V":
                y = num() + (y if rel else 0.0)
                pts.append((x, y))
            elif c in "CSQT":
                for _ in range({"C": 3, "S": 2, "Q": 2, "T": 1}[c]):
                    px, py = num(), num()
                    pts.append((px + x, py + y) if rel else (px, py))
                x, y = pts[-1]
            elif c == "A":
                r = 2 * max(abs(num()), abs(num()))   # an arc stays within its diameter of both ends
                num()
                flag()
                flag()
                nx, ny = num(), num()
                nx, ny = (nx + x, ny + y) if rel else (nx, ny)
                pts += [(x - r, y - r), (x + r, y + r), (nx - r, ny - r), (nx + r, ny + r), (nx, ny)]
                x, y = nx, ny
        except ValueError:
            break
    return pts


def _colour_key(v: str) -> str:
    v = v.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        return "#" + "".join(ch * 2 for ch in v[1:])
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", ",").split(",") if p.strip()]
        rgb = [round(float(p[:-1]) * 2.55) if p.endswith("%") else round(float(p)) for p in parts[:3]]
        return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in rgb)
    return v


def _shape_points(el, tag: str) -> list[tuple[float, float]]:
    g = lambda name: _length(el.get(name), 0.0)
    if tag == "line":
        return [(g("x1"), g("y1")), (g("x2"), g("y2"))]
    if tag == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        return [(x, y), (x + w, y + h)] if w > 0 and h > 0 else []
    if tag in ("circle", "ellipse"):
        cx, cy = g("cx"), g("cy")
        rx, ry = (g("r"), g("r")) if tag == "circle" else (g("rx"), g("ry"))
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)] if rx > 0 and ry > 0 else []
    if tag in ("polyline", "polygon"):
        v = [float(n) for n in re.findall(_NUM, el.get("points") or "")]
        return list(zip(v[0::2], v[1::2]))
    return path_points(el.get("d") or "")


def _svg_strokes(path: str) -> list[tuple[float, tuple]]:
    from lxml import etree

    from .assets import svg_geometry, svg_user_matrix
    root = etree.parse(path, etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)).getroot()
    to_pt = svg_user_matrix(svg_geometry(root))
    rules = _css_rules(root)
    by_id = {el.get("id"): el for el in root.iter() if isinstance(el.tag, str) and el.get("id")}
    out: list[tuple[float, tuple]] = []

    def own_style(el, chain: list) -> dict:
        style = {k: el.get(k) for k in PROPS if el.get(k) is not None}
        for _, _, parts, decls in rules:
            if _selects(parts, chain):
                style.update(decls)
        style.update(_declarations(el.get("style")))
        return style

    def walk(el, ctm: Matrix, inherited: dict, active: frozenset, chain: list) -> None:
        if not isinstance(el.tag, str):
            return
        tag = etree.QName(el).localname
        if tag in NOT_DRAWN and not (tag == "symbol" and el in active):
            return
        chain = chain + [(tag, set((el.get("class") or "").split()), el.get("id"))]
        own = own_style(el, chain)
        if own.get("display") == "none" or _number(own.get("opacity"), 1.0) <= 0:
            return
        style = {**inherited, **{k: v for k, v in own.items() if k in INHERITED and v != "inherit"}}
        if el.get("transform"):
            ctm = ctm @ _transform(el.get("transform"))
        if tag == "use":
            ref = el.get("href") or el.get(XLINK_HREF) or ""
            target = by_id.get(ref[1:]) if ref.startswith("#") else None
            if target is not None and target not in active:
                shift = Matrix(1.0, 0.0, 0.0, 1.0, _length(el.get("x"), 0.0), _length(el.get("y"), 0.0))
                walk(target, ctm @ shift, style, active | {target}, chain)
            return
        if tag not in SHAPES:
            for child in el:
                walk(child, ctm, style, active, chain)
            return
        stroke = (style.get("stroke") or "none").strip().lower()
        opacity = _number(style.get("stroke-opacity"), 1.0)
        width = _length(style.get("stroke-width"), 1.0)
        if stroke in ("none", "transparent") or opacity <= 0 or width <= 0 \
                or style.get("visibility") in ("hidden", "collapse"):
            return
        fill = (style.get("fill") or "#000000").strip().lower()
        if tag != "line" and fill not in ("none", "transparent") and _colour_key(fill) == _colour_key(stroke) \
                and _number(style.get("fill-opacity"), 1.0) == opacity:
            return   # a border in the fill's own colour
        local = _shape_points(el, tag)
        if not local:
            return
        xs, ys = [p[0] for p in local], [p[1] for p in local]
        corners = [ctm.apply(x, y) for x, y in ((min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys)))]
        cx, cy = [p[0] for p in corners], [p[1] for p in corners]
        scale = 0.75 if own.get("vector-effect") == "non-scaling-stroke" else thinnest_scale(ctm)
        out.append((width * scale, (min(cx), min(cy), max(cx), max(cy))))

    walk(root, to_pt, {}, frozenset(), [])
    return out

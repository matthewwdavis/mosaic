"""SVG export.

A placed SVG's markup is copied in unchanged apart from two safety edits: element IDs get
a per-panel prefix (two plots can't clash), and its stylesheet rules are scoped to its own
group (one plot's CSS can't restyle another). Raster images are embedded byte-for-byte as
data URIs. FigAssemble's own shapes and text use inline styles, which no stylesheet can
override.
"""
from __future__ import annotations

import base64
import copy
import io
import re

from lxml import etree

from ..assets import SourceResolver, svg_geometry
from ..geometry import DrawPath, Matrix, _fmt
from ..resolve import DrawGroup, DrawPicture, DrawText, Resolved

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {None: SVG_NS, "xlink": XLINK_NS}
_PARSER = etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True, remove_blank_text=False)
_URL_REF = re.compile(r"url\(\s*['\"]?#([^'\")\s]+)['\"]?\s*\)")
_GENERIC = {"sans": "sans-serif", "serif": "serif", "mono": "monospace"}


def _q(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def _matrix(m: Matrix) -> str:
    return "matrix(" + " ".join(_fmt(v, 6) for v in m.as_tuple()) + ")"


def _family_list(family: str) -> str:
    low = family.lower()
    generic = "serif" if any(k in low for k in ("times", "serif", "georgia", "garamond")) and "sans" not in low \
        else "monospace" if any(k in low for k in ("courier", "mono")) else "sans-serif"
    fams = [family]
    if generic == "sans-serif" and low not in ("arial",):
        fams.append("Arial")
    fams.append(generic)
    return ", ".join(f"'{f}'" if " " in f else f for f in fams)


def scope_css(css: str, scope: str, id_map: dict[str, str]) -> str:
    """Prefix every top-level selector with `scope` and rename #id references."""
    def rename_ids(text: str) -> str:
        text = _URL_REF.sub(lambda m: f"url(#{id_map.get(m.group(1), m.group(1))})", text)
        return re.sub(r"#([A-Za-z_][\w\-]*)", lambda m: "#" + id_map.get(m.group(1), m.group(1)), text)

    out = []
    pos = 0
    depth = 0
    rule_start = 0
    # Walk top-level rules: "selectors { body }"; leave @-blocks untouched
    while pos < len(css):
        ch = css[pos]
        if ch == "{":
            if depth == 0:
                selectors = css[rule_start:pos]
                body_start = pos
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = css[body_start:pos + 1]
                sel = selectors.strip()
                if sel.startswith("@"):
                    out.append(selectors + body)
                else:
                    scoped = []
                    for s in sel.split(","):
                        s = s.strip()
                        if not s:
                            continue
                        s = re.sub(r"^(svg|:root)\b", scope, s)
                        scoped.append(s if s.startswith(scope) else f"{scope} {s}")
                    out.append(rename_ids(", ".join(scoped)) + " " + rename_ids(body))
                rule_start = pos + 1
        pos += 1
    return "\n".join(out)


_PCT_X = ("x", "width", "x1", "x2", "cx", "rx", "fx")
_PCT_Y = ("y", "height", "y1", "y2", "cy", "ry", "fy")


def _resolve_percentages(root, vx: float, vy: float, vw: float, vh: float) -> None:
    """Turn % lengths into user units, except inside nested <svg> viewports (which keep their own)."""
    diag = ((vw ** 2 + vh ** 2) / 2) ** 0.5
    # Inside these, percentages are relative to an object's bounding box, not the viewport
    bbox_relative = {"linearGradient", "radialGradient", "pattern", "mask", "filter"}

    def walk(el, skip=False):
        for child in el:
            if not isinstance(child.tag, str):
                continue
            local = etree.QName(child).localname
            if local == "svg":
                continue
            child_skip = skip or local in bbox_relative or (
                local == "clipPath" and child.get("clipPathUnits") == "objectBoundingBox")
            if not child_skip:
                for attr in _PCT_X + _PCT_Y + ("r",):
                    val = child.get(attr)
                    if val and val.strip().endswith("%"):
                        try:
                            frac = float(val.strip()[:-1]) / 100.0
                        except ValueError:
                            continue
                        if attr in _PCT_X:
                            num = frac * vw + (vx if attr in ("x", "x1", "x2", "cx", "fx") else 0.0)
                        elif attr in _PCT_Y:
                            num = frac * vh + (vy if attr in ("y", "y1", "y2", "cy", "fy") else 0.0)
                        else:
                            num = frac * diag
                        child.set(attr, _fmt(num, 6))
            walk(child, child_skip)

    walk(root)


class SvgWriter:
    def __init__(self, sources: SourceResolver):
        self.sources = sources
        self.warnings: list[str] = []
        self._panel = 0

    def page(self, page: dict, resolved: list[Resolved]) -> bytes:
        w, h = float(page["width"]), float(page["height"])
        root = etree.Element(_q("svg"), nsmap=NSMAP)
        root.set("version", "1.1")
        root.set("width", f"{_fmt(w, 4)}pt")
        root.set("height", f"{_fmt(h, 4)}pt")
        root.set("viewBox", f"0 0 {_fmt(w, 4)} {_fmt(h, 4)}")
        self._defs = etree.SubElement(root, _q("defs"))
        self._clip = 0
        if page.get("background"):
            bg = etree.SubElement(root, _q("rect"))
            bg.set("width", _fmt(w, 4))
            bg.set("height", _fmt(h, 4))
            bg.set("style", f"fill:{page['background']};stroke:none")
        for r in resolved:
            for prim in r.prims:
                try:
                    self._prim(root, prim)
                except Exception as exc:
                    self.warnings.append(f"item {r.item_id}: {exc}")
        if not len(self._defs):
            root.remove(self._defs)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    # Primitives -------------------------------------------------------------------------

    def _prim(self, parent, prim, pictures: bool = True) -> None:
        if isinstance(prim, DrawPath):
            self._path(parent, prim)
        elif isinstance(prim, DrawText):
            self._text(parent, prim)
        elif isinstance(prim, DrawPicture) and pictures:
            self._picture(parent, prim)
        elif isinstance(prim, DrawGroup):
            # A faded group fades as one, so its parts don't double up where they overlap
            g = etree.SubElement(parent, _q("g"))
            if prim.opacity < 1:
                g.set("opacity", _fmt(prim.opacity, 4))
            for p in prim.prims:
                self._prim(g, p, pictures)

    def _path(self, parent, prim: DrawPath) -> None:
        if prim.stroke is None and prim.fill is None:
            return
        el = etree.SubElement(parent, _q("path"))
        el.set("d", prim.path.to_svg(3))
        style = []
        if prim.fill is not None and prim.fill.gradient is not None:
            style.append(f"fill:url(#{self._gradient(prim.fill)})")
            if prim.fill.even_odd:
                style.append("fill-rule:evenodd")
        elif prim.fill is not None:
            style.append(f"fill:{prim.fill.color}")
            if prim.fill.opacity < 1:
                style.append(f"fill-opacity:{_fmt(prim.fill.opacity, 4)}")
            if prim.fill.even_odd:
                style.append("fill-rule:evenodd")
        else:
            style.append("fill:none")
        s = prim.stroke
        if s is not None:
            style += [f"stroke:{s.color}", f"stroke-width:{_fmt(s.width, 4)}",
                      f"stroke-linecap:{'butt' if s.cap == 'flat' else s.cap}",
                      f"stroke-linejoin:{s.join}", f"stroke-miterlimit:{_fmt(s.miter_limit, 2)}"]
            if s.dash:
                style.append("stroke-dasharray:" + ",".join(_fmt(v, 4) for v in s.dash))
                if s.dash_phase:
                    style.append(f"stroke-dashoffset:{_fmt(s.dash_phase, 4)}")
            if s.opacity < 1:
                style.append(f"stroke-opacity:{_fmt(s.opacity, 4)}")
        else:
            style.append("stroke:none")
        el.set("style", ";".join(style))

    def _gradient(self, fill) -> str:
        g = fill.gradient
        self._clip += 1
        gid = f"fa-grad{self._clip}"
        lg = etree.SubElement(self._defs, _q("radialGradient" if g.kind == "radial" else "linearGradient"))
        lg.set("id", gid)
        lg.set("gradientUnits", "userSpaceOnUse")
        if g.kind == "radial":
            for k, v in zip(("cx", "cy", "r", "fx", "fy"), (g.p0[0], g.p0[1], g.radius, g.p0[0], g.p0[1])):
                lg.set(k, _fmt(v, 6))
        else:
            for k, v in zip(("x1", "y1", "x2", "y2"), (g.p0[0], g.p0[1], g.p1[0], g.p1[1])):
                lg.set(k, _fmt(v, 6))
        lg.set("gradientTransform", _matrix(g.matrix))
        for pos, color, opacity in g.stops:
            stop = etree.SubElement(lg, _q("stop"))
            stop.set("offset", _fmt(pos, 6))
            stop.set("style", f"stop-color:{color};stop-opacity:{_fmt(opacity * fill.opacity, 4)}")
        return gid

    def _text(self, parent, prim: DrawText) -> None:
        for run in prim.runs:
            if not run.text.strip():
                continue
            el = etree.SubElement(parent, _q("text"))
            m = prim.matrix
            if m != Matrix():
                el.set("transform", _matrix(m))
            el.set("x", _fmt(run.x, 4))
            el.set("y", _fmt(run.y, 4))
            ref = run.face.ref
            style = [f"font-family:{_family_list(ref.family)}", f"font-size:{_fmt(run.size, 4)}px",
                     f"fill:{run.color}", "white-space:pre"]
            if ref.weight >= 600:
                style.append("font-weight:bold")
            if ref.italic or run.skew:
                style.append("font-style:italic")
            if run.opacity < 1:
                style.append(f"fill-opacity:{_fmt(run.opacity, 4)}")
            if run.underline:
                style.append("text-decoration:underline")
            el.set("style", ";".join(style))
            # Pin the run's width so every renderer matches FigAssemble's layout (as svglite does)
            el.set("textLength", _fmt(run.width, 4))
            el.set("lengthAdjust", "spacingAndGlyphs")
            el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            el.text = run.text

    def _clip_rect(self, x: float, y: float, w: float, h: float) -> str:
        self._clip += 1
        cid = f"fa-clip{self._clip}"
        cp = etree.SubElement(self._defs, _q("clipPath"))
        cp.set("id", cid)
        cp.set("clipPathUnits", "userSpaceOnUse")
        rect = etree.SubElement(cp, _q("rect"))
        for k, v in (("x", x), ("y", y), ("width", w), ("height", h)):
            rect.set(k, _fmt(v, 6))
        return cid

    def _picture(self, parent, prim: DrawPicture) -> None:
        kind, path = self.sources.for_svg(prim.asset_id, prim.source)
        x0, y0, x1, y1 = prim.crop
        if kind == "svg":
            self._inline_svg(parent, prim, path)
            return
        g = etree.SubElement(parent, _q("g"))
        g.set("transform", _matrix(prim.matrix))
        g.set("clip-path", f"url(#{self._clip_rect(x0, y0, x1 - x0, y1 - y0)})")
        if prim.opacity < 1:
            g.set("opacity", _fmt(prim.opacity, 4))
        sw, sh = prim.src_size
        img = etree.SubElement(g, _q("image"))
        img.set("width", _fmt(sw, 6))
        img.set("height", _fmt(sh, 6))
        img.set("preserveAspectRatio", "none")
        img.set(f"{{{XLINK_NS}}}href", self._data_uri(path, kind))

    def _data_uri(self, path: str, kind: str) -> str:
        if kind == "tiff":
            from PIL import Image
            buf = io.BytesIO()
            with Image.open(path) as im:
                im.save(buf, "PNG")
            data, mime = buf.getvalue(), "image/png"
        else:
            with open(path, "rb") as fh:
                data = fh.read()
            mime = "image/jpeg" if kind == "jpeg" else "image/png"
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")

    def _inline_svg(self, parent, prim: DrawPicture, path: str) -> None:
        self._panel += 1
        scope = f"fa-p{self._panel}"
        src = etree.parse(path, _PARSER).getroot()
        geo = svg_geometry(src)
        (sw, sh), (vx, vy, vw, vh) = geo["size_pt"], geo["viewbox"]
        # User units -> source points, honouring preserveAspectRatio
        sx, sy = sw / vw, sh / vh
        ox = oy = 0.0
        par = (geo["par"] or "xMidYMid meet").split()
        if par[0] != "none":
            s = min(sx, sy) if (len(par) < 2 or par[1] == "meet") else max(sx, sy)
            align = par[0]
            ox = {"xMin": 0.0, "xMid": 0.5, "xMax": 1.0}.get(align[:4], 0.5) * (sw - vw * s)
            oy = {"YMin": 0.0, "YMid": 0.5, "YMax": 1.0}.get(align[4:], 0.5) * (sh - vh * s)
            sx = sy = s
        to_pt = Matrix(sx, 0.0, 0.0, sy, ox - vx * sx, oy - vy * sy)
        # Rename every id and every reference to one
        id_map = {}
        for el in src.iter():
            if not isinstance(el.tag, str):
                continue
            eid = el.get("id")
            if eid:
                id_map[eid] = f"{scope}-{eid}"
        for el in src.iter():
            if not isinstance(el.tag, str):
                continue
            for attr, val in list(el.attrib.items()):
                if attr == "id":
                    el.set(attr, id_map[val])
                elif attr in ("href", f"{{{XLINK_NS}}}href") and val.startswith("#"):
                    el.set(attr, "#" + id_map.get(val[1:], val[1:]))
                elif "url(" in val:
                    el.set(attr, _URL_REF.sub(lambda m: f"url(#{id_map.get(m.group(1), m.group(1))})", val))
            if el.tag == _q("style") and el.text:
                el.text = etree.CDATA(scope_css(el.text, "." + scope, id_map)) if "<" in el.text or "&" in el.text \
                    else scope_css(el.text, "." + scope, id_map)
        # Percentages meant the source's own viewport; once inlined they would mean the page's
        _resolve_percentages(src, vx, vy, vw, vh)
        # Crop box in the source's user units (to_pt is a scale plus a shift)
        x0, y0, x1, y1 = prim.crop
        ux0, uy0 = (x0 - to_pt.e) / to_pt.a, (y0 - to_pt.f) / to_pt.d
        ux1, uy1 = (x1 - to_pt.e) / to_pt.a, (y1 - to_pt.f) / to_pt.d
        g = etree.SubElement(parent, _q("g"))
        g.set("class", scope)
        g.set("transform", _matrix(prim.matrix @ to_pt))
        g.set("clip-path", f"url(#{self._clip_rect(ux0, uy0, ux1 - ux0, uy1 - uy0)})")
        if prim.opacity < 1:
            g.set("opacity", _fmt(prim.opacity, 4))
        # Carry the root's own styling onto the group (its class joins the scope class)
        for attr, val in src.attrib.items():
            local = etree.QName(attr).localname if attr.startswith("{") else attr
            if local in ("width", "height", "viewBox", "x", "y", "version", "preserveAspectRatio",
                         "baseProfile", "overflow", "id", "enable-background"):
                continue
            if local == "class":
                g.set("class", f"{scope} {val}")
            elif not attr.startswith("{"):
                g.set(attr, val)
        for child in list(src):
            g.append(child)


def fragment(resolved: Resolved, id_prefix: str) -> str:
    """SVG markup for an item's shapes and text (pictures are drawn by the editor itself).

    The editor shows exactly what SVG export writes, from the same code.
    """
    w = SvgWriter(sources=None)   # type: ignore[arg-type]
    g = etree.Element(_q("g"), nsmap={None: SVG_NS})
    w._defs = etree.SubElement(g, _q("defs"))
    w._clip = 0
    for prim in resolved.prims:
        w._prim(g, prim, pictures=False)
    for el in g.iter():
        if isinstance(el.tag, str):
            if el.get("id"):
                el.set("id", f"{id_prefix}-{el.get('id')}")
            st = el.get("style")
            if st and "url(#" in st:
                el.set("style", st.replace("url(#", f"url(#{id_prefix}-"))
    if not len(w._defs):
        g.remove(w._defs)
    return "".join(etree.tostring(child, encoding="unicode") for child in g)


def write_svg(page: dict, resolved: list[Resolved], path: str, sources: SourceResolver) -> list[str]:
    w = SvgWriter(sources)
    data = w.page(page, resolved)
    with open(path, "wb") as fh:
        fh.write(data)
    return w.warnings

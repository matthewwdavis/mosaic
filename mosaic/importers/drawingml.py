"""DrawingML pieces shared by the PowerPoint importer: themes, colours, line/fill styles,
text defaults and custom-geometry guides (presets.py has the formula language).
"""
from __future__ import annotations

import colorsys
import re

from ..presets import builtin_guides, eval_formula

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"a": A, "p": P, "r": R}
EMU_PER_PT = 12700.0

PRESET_COLORS = {
    "black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000", "blue": "0000FF",
    "yellow": "FFFF00", "gray": "808080", "grey": "808080", "darkGray": "A9A9A9", "lightGray": "D3D3D3",
    "orange": "FFA500", "purple": "800080", "cyan": "00FFFF", "magenta": "FF00FF",
}
def _found(el, path: str):
    """A child's children, or none if it isn't there (an element with no children is false)."""
    child = el.find(path, NS) if el is not None else None
    return child if child is not None else []


SYSTEM_COLORS = {"windowText": "000000", "window": "FFFFFF", "btnFace": "F0F0F0", "btnText": "000000"}


def tag(el) -> str:
    return el.tag.split("}")[1] if "}" in el.tag else el.tag


def emu(v, default: float = 0.0) -> float:
    return int(v) / EMU_PER_PT if v is not None else default


class Theme:
    """Colour scheme, fonts and style matrix of a slide master's theme."""

    def __init__(self, root=None):
        self.colors: dict[str, str] = {"dk1": "000000", "lt1": "FFFFFF", "dk2": "44546A", "lt2": "E7E6E6",
                                       "accent1": "4472C4", "accent2": "ED7D31", "accent3": "A5A5A5",
                                       "accent4": "FFC000", "accent5": "5B9BD5", "accent6": "70AD47",
                                       "hlink": "0563C1", "folHlink": "954F72"}
        self.major_font = "Calibri Light"
        self.minor_font = "Calibri"
        self.fill_styles: list = []
        self.line_styles: list = []
        self.bg_fill_styles: list = []
        if root is None:
            return
        scheme = root.find("a:themeElements/a:clrScheme", NS)
        if scheme is not None:
            for el in scheme:
                c = el[0] if len(el) else None
                if c is None:
                    continue
                if tag(c) == "srgbClr":
                    self.colors[tag(el)] = c.get("val", "000000").upper()
                elif tag(c) == "sysClr":
                    self.colors[tag(el)] = (c.get("lastClr") or SYSTEM_COLORS.get(c.get("val"), "000000")).upper()
        fonts = root.find("a:themeElements/a:fontScheme", NS)
        if fonts is not None:
            maj = fonts.find("a:majorFont/a:latin", NS)
            mnr = fonts.find("a:minorFont/a:latin", NS)
            self.major_font = maj.get("typeface") if maj is not None else self.major_font
            self.minor_font = mnr.get("typeface") if mnr is not None else self.minor_font
        fmt = root.find("a:themeElements/a:fmtScheme", NS)
        if fmt is not None:
            self.fill_styles = list(_found(fmt, "a:fillStyleLst"))
            self.line_styles = list(_found(fmt, "a:lnStyleLst"))
            self.bg_fill_styles = list(_found(fmt, "a:bgFillStyleLst"))


class ColorContext:
    """Resolves DrawingML colour elements for one slide (theme + colour map)."""

    def __init__(self, theme: Theme, clr_map: dict[str, str] | None = None):
        self.theme = theme
        self.clr_map = clr_map or {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}

    def scheme(self, name: str, placeholder: tuple[str, float] | None = None) -> str:
        if name == "phClr" and placeholder is not None:
            return placeholder[0]
        name = self.clr_map.get(name, name)
        return self.theme.colors.get(name, "000000")

    def resolve(self, el, placeholder: tuple[str, float] | None = None) -> tuple[str, float] | None:
        """(hex colour '#RRGGBB', opacity) of a colour element (srgbClr, schemeClr, ...)."""
        if el is None:
            return None
        t = tag(el)
        if t == "srgbClr":
            base = el.get("val", "000000")
        elif t == "schemeClr":
            if el.get("val") == "phClr" and placeholder is not None:
                base, alpha0 = placeholder[0].lstrip("#"), placeholder[1]
                return self._apply(base, el, alpha0)
            base = self.scheme(el.get("val", "tx1"))
        elif t == "sysClr":
            base = el.get("lastClr") or SYSTEM_COLORS.get(el.get("val"), "000000")
        elif t == "prstClr":
            base = PRESET_COLORS.get(el.get("val"), "000000")
        elif t == "scrgbClr":
            def lin(v):
                x = int(v) / 100000.0
                return x * 12.92 if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
            base = "".join(f"{round(max(0, min(1, lin(el.get(k, '0')))) * 255):02X}" for k in "rgb")
        elif t == "hslClr":
            h, s, l = int(el.get("hue", 0)) / 21600000.0, int(el.get("sat", 0)) / 100000.0, int(el.get("lum", 0)) / 100000.0
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            base = f"{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"
        else:
            return None
        return self._apply(base, el, 1.0)

    def _apply(self, base: str, el, alpha: float) -> tuple[str, float]:
        r, g, b = (int(base[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        for mod in el:
            t, v = tag(mod), int(mod.get("val", "0")) / 100000.0
            if t == "alpha":
                alpha = v
            elif t == "alphaMod":
                alpha *= v
            elif t == "tint":
                r, g, b = (c * v + (1 - v) for c in (r, g, b))
            elif t == "shade":
                r, g, b = (c * v for c in (r, g, b))
            elif t in ("lumMod", "lumOff", "satMod", "satOff", "hueMod", "hueOff"):
                h, l, s = colorsys.rgb_to_hls(r, g, b)
                if t == "lumMod":
                    l *= v
                elif t == "lumOff":
                    l += v
                elif t == "satMod":
                    s *= v
                elif t == "satOff":
                    s += v
                elif t == "hueMod":
                    h = (h * v) % 1.0
                elif t == "hueOff":
                    h = (h + int(mod.get("val", "0")) / 21600000.0) % 1.0
                r, g, b = colorsys.hls_to_rgb(h, min(max(l, 0), 1), min(max(s, 0), 1))
            elif t == "inv":
                r, g, b = 1 - r, 1 - g, 1 - b
            elif t == "gray":
                y = 0.2126 * r + 0.7152 * g + 0.0722 * b
                r = g = b = y
        hexc = "#" + "".join(f"{round(min(max(c, 0), 1) * 255):02X}" for c in (r, g, b))
        return hexc, alpha


def _bool_attr(v) -> bool:
    return v in ("1", "true", "on")


def first_color(el):
    """The colour element directly inside a fill/ref element, if any."""
    if el is None:
        return None
    for child in el:
        if tag(child) in ("srgbClr", "schemeClr", "sysClr", "prstClr", "scrgbClr", "hslClr"):
            return child
    return None


def parse_fill(el, colors: ColorContext, placeholder=None) -> tuple[dict | None, list[str]] | None:
    """Fill dict from the first fill element under `el` (spPr or a style entry).

    Returns None when `el` sets no fill at all (so a style default applies).
    """
    notes: list[str] = []
    if el is None:
        return None
    for child in el:
        t = tag(child)
        if t == "noFill":
            return None, notes
        if t == "solidFill":
            c = colors.resolve(first_color(child), placeholder)
            return ({"color": c[0], "opacity": c[1]} if c else None), notes
        if t == "gradFill":
            stops = []
            for gs in child.findall("a:gsLst/a:gs", NS):
                c = colors.resolve(first_color(gs), placeholder)
                if c:
                    stops.append({"pos": int(gs.get("pos", "0")) / 100000.0, "color": c[0], "opacity": c[1]})
            if not stops:
                return None, notes
            stops.sort(key=lambda s: s["pos"])
            lin, path = child.find("a:lin", NS), child.find("a:path", NS)
            if lin is None and path is not None:
                # A path gradient: circles round the middle of its focus rectangle (given as
                # insets from the shape's edges, in thousandths of a percent)
                if path.get("path", "circle") != "circle":
                    notes.append(f"{path.get('path')}-shaped gradient drawn as a circular one")
                ftr = path.find("a:fillToRect", NS)
                l, t, r, b = ((int(ftr.get(k, "0")) / 100000.0 for k in ("l", "t", "r", "b")) if ftr is not None
                              else (0.0, 0.0, 0.0, 0.0))
                center = [round((l + 1.0 - r) / 2, 6), round((t + 1.0 - b) / 2, 6)]
                # (the stops carry the transparency; the fill's own opacity would apply on top of it)
                return {"color": stops[0]["color"], "opacity": 1.0,
                        "gradient": {"type": "radial", "center": center, "stops": stops}}, notes
            angle = int(lin.get("ang", "0")) / 60000.0 if lin is not None else 90.0
            scaled = lin is None or _bool_attr(lin.get("scaled", "0"))
            return {"color": stops[0]["color"], "opacity": 1.0,
                    "gradient": {"type": "linear", "angle": angle, "scaled": scaled, "stops": stops}}, notes
        if t == "pattFill":
            c = colors.resolve(first_color(child.find("a:fgClr", NS)), placeholder)
            notes.append("pattern fill approximated by its foreground colour")
            return ({"color": c[0], "opacity": c[1]} if c else None), notes
        if t == "blipFill":
            notes.append("picture fill in a shape is not supported yet")
            return None, notes
        if t == "grpFill":
            notes.append("group fill not supported; shape left unfilled")
            return None, notes
    return None


DASH_MAP = {"solid", "dot", "dash", "lgDash", "dashDot", "lgDashDot", "lgDashDotDot",
            "sysDash", "sysDot", "sysDashDot", "sysDashDotDot"}
CAP_MAP = {"rnd": "round", "sq": "square", "flat": "flat"}


def parse_line(ln, colors: ColorContext, base: dict | None = None, placeholder=None) -> dict | None:
    """Stroke dict from an a:ln element layered over `base` (from the theme style)."""
    stroke = dict(base) if base else None
    if ln is None:
        return stroke
    if ln.find("a:noFill", NS) is not None:
        return None
    stroke = stroke or {"color": "#000000", "width": 0.75, "dash": "solid", "cap": "flat", "join": "miter",
                        "opacity": 1.0}
    if ln.get("w") is not None:
        stroke["width"] = emu(ln.get("w"))
    if ln.get("cap"):
        stroke["cap"] = CAP_MAP.get(ln.get("cap"), "flat")
    fill = ln.find("a:solidFill", NS)
    if fill is not None:
        c = colors.resolve(first_color(fill), placeholder)
        if c:
            stroke["color"], stroke["opacity"] = c
    grad = ln.find("a:gradFill", NS)
    if grad is not None:
        stops = grad.findall("a:gsLst/a:gs", NS)
        c = colors.resolve(first_color(stops[0]), placeholder) if stops else None
        if c:
            stroke["color"], stroke["opacity"] = c
    dash = ln.find("a:prstDash", NS)
    if dash is not None:
        stroke["dash"] = dash.get("val") if dash.get("val") in DASH_MAP else "solid"
    cust = ln.find("a:custDash", NS)
    if cust is not None:
        pattern = []
        for ds in cust.findall("a:ds", NS):
            pattern += [int(ds.get("d", 100000)) / 100000.0, int(ds.get("sp", 100000)) / 100000.0]
        stroke["dash"] = pattern or "solid"
    for j in ("round", "bevel", "miter"):
        if ln.find(f"a:{j}", NS) is not None:
            stroke["join"] = j
    for end, key in (("headEnd", "arrow_start"), ("tailEnd", "arrow_end")):
        e = ln.find(f"a:{end}", NS)
        if e is not None:
            kind = e.get("type", "none")
            stroke[key] = None if kind == "none" else {"type": kind, "w": e.get("w", "med"), "len": e.get("len", "med")}
    return stroke


def style_line(theme: Theme, colors: ColorContext, style_el) -> dict | None:
    """Base stroke from a shape's p:style lnRef (theme line style + the ref's colour)."""
    if style_el is None:
        return None
    ref = style_el.find("a:lnRef", NS)
    if ref is None:
        return None
    idx = int(ref.get("idx", "0"))
    if idx <= 0 or idx > len(theme.line_styles):
        return None
    ph = colors.resolve(first_color(ref))
    return parse_line(theme.line_styles[idx - 1], colors, None, placeholder=ph)


def style_fill(theme: Theme, colors: ColorContext, style_el) -> dict | None:
    if style_el is None:
        return None
    ref = style_el.find("a:fillRef", NS)
    if ref is None:
        return None
    idx = int(ref.get("idx", "0"))
    ph = colors.resolve(first_color(ref))
    if idx == 0:
        return None
    lst = theme.bg_fill_styles if idx >= 1001 else theme.fill_styles
    i = (idx - 1001) if idx >= 1001 else (idx - 1)
    if i < 0 or i >= len(lst):
        return {"color": ph[0], "opacity": ph[1]} if ph else None
    res = parse_fill([lst[i]], colors, placeholder=ph)   # parse_fill reads the fill elements it's given
    return res[0] if res else None


def style_font_color(colors: ColorContext, style_el) -> tuple[str, float] | None:
    if style_el is None:
        return None
    ref = style_el.find("a:fontRef", NS)
    return colors.resolve(first_color(ref)) if ref is not None else None


# ---------------------------------------------------------------------------
# Shape guide formulas (used by custom geometry)
# ---------------------------------------------------------------------------

def guide_env(geom_el, w: float, h: float) -> dict[str, float]:
    env = builtin_guides(w, h)
    for lst in ("a:avLst", "a:gdLst"):
        node = geom_el.find(lst, NS) if geom_el is not None else None
        if node is None:
            continue
        for gd in node.findall("a:gd", NS):
            try:
                env[gd.get("name")] = eval_formula(gd.get("fmla", "val 0"), env)
            except (KeyError, ValueError, IndexError, ZeroDivisionError):
                env[gd.get("name")] = 0.0
    return env


def num(value: str | None, env: dict[str, float], default: float = 0.0) -> float:
    if value is None:
        return default
    if value in env:
        return env[value]
    try:
        return float(value)
    except ValueError:
        return default


_SPACE = re.compile(r"\s+")


def clean_text(s: str) -> str:
    return _SPACE.sub(" ", s)

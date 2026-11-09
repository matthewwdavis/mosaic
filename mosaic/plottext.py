"""Dangerous mode: the text inside placed PDFs and SVGs, and copies of them with some taken out.

In dangerous mode a double-click on a placed plot's text lifts it out: it becomes an ordinary
mosaic text box in the same font, size, colour, angle and place, and the picture remembers what
was lifted (its item's "lifted_text": {"hidden": [...], "dropped": [...]}, see liftedtext.js).
The picture is then drawn and exported from a copy of its file without those texts; the file
placed stays in the document as it was, so they can be put back. When R saves the file again,
the same texts are found in the new one (by their words, size, angle and place) and taken out
again; any that aren't there any more are dropped (the editor deletes their boxes and Check
says so).

Texts are read from the files themselves: a PDF's text-showing operators (pieces drawn one
after another along one line join into one text) and an SVG's <text> elements and their
<tspan>s. Positions are the source's displayed points from the top left, as in vectors.py (the
space a picture's crop is in); angles are degrees clockwise, as mosaic turns things.

Taking a text out of a PDF swaps each operator that showed it for a move of the same length (a
TJ holding only a number), so whatever is drawn after it on the same line stays where it was.
In an SVG a whole <text> is removed; part of one is hidden (visibility), because the parts after
it carry on from where it ends.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .geometry import Matrix

MINUS = "−"
DEFAULT_FAMILY = "Helvetica"


@dataclass
class PlotText:
    """One text in a placed plot: its words and look, where its baseline starts (`origin`), how
    long it is along the baseline (`width`) and how it lines up there (`align`: "l", "ctr" or
    "r", from an SVG's text-anchor; PDFs don't say, so "l"). `refs`: where it is in the file."""
    text: str
    font: str
    bold: bool
    italic: bool
    size: float
    color: str
    opacity: float
    angle: float
    origin: tuple
    width: float
    align: str = "l"
    refs: list = field(default_factory=list)
    symbol: bool = False    # drawn in the Symbol font (R's Greek): joins text in any font

    def point(self, along: float, up: float = 0.0) -> tuple[float, float]:
        """A point `along` the baseline from its start and `up` from it (towards the tops of the letters)."""
        a = math.radians(self.angle)
        ox, oy = self.origin
        return (ox + along * math.cos(a) + up * math.sin(a), oy + along * math.sin(a) - up * math.cos(a))

    def end(self) -> tuple[float, float]:
        return self.point(self.width)

    def record(self, i: int) -> dict:
        """What the editor gets: the text and its look, the middle of its baseline (`mid`, for
        finding it again) and the four corners of a box round its letters (`quad`, to hit)."""
        lo, hi = -0.25 * self.size, 0.8 * self.size
        quad = [self.point(0, lo), self.point(self.width, lo), self.point(self.width, hi), self.point(0, hi)]
        r6 = lambda v: round(v, 4)
        return {"id": i, "text": self.text, "font": self.font, "bold": self.bold, "italic": self.italic,
                "size": r6(self.size), "color": self.color, "opacity": r6(self.opacity), "angle": r6(self.angle),
                "origin": [r6(v) for v in self.origin], "width": r6(self.width), "align": self.align,
                "mid": [r6(v) for v in self.point(self.width / 2)], "quad": [[r6(x), r6(y)] for x, y in quad]}


def _norm(text: str) -> str:
    """Text as compared between files: R's PDF draws "-" as a minus sign and its SVG as a hyphen."""
    return re.sub(r"\s+", " ", text.replace(MINUS, "-").replace(" ", " ")).strip()


def _turn(a: float) -> float:
    """An angle in (-180, 180]."""
    a = math.fmod(a, 360.0)
    return a - 360.0 if a > 180.0 else a + 360.0 if a <= -180.0 else a


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(float(v) * 255))):02x}" for v in rgb)


# ---------------------------------------------------------------------------
# Joining pieces drawn one after another
# ---------------------------------------------------------------------------

def _continues(last: PlotText, p: PlotText) -> bool:
    """Whether piece `p` carries on `last` along the same line, in the same look."""
    same_font = last.symbol or p.symbol or (last.font, last.bold, last.italic) == (p.font, p.bold, p.italic)
    if not same_font or last.color != p.color or abs(last.size - p.size) > 0.02 * max(last.size, p.size):
        return False
    if abs(_turn(last.angle - p.angle)) > 0.5:
        return False
    ex, ey = last.end()
    a = math.radians(last.angle)
    dx, dy = p.origin[0] - ex, p.origin[1] - ey
    along, across = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
    return abs(across) < 0.1 * p.size and -0.25 * p.size <= along <= 0.6 * p.size


def _join(pieces: list[PlotText]) -> list[PlotText]:
    out: list[PlotText] = []
    for p in pieces:
        last = out[-1] if out else None
        if last is not None and _continues(last, p):
            ex, ey = last.end()
            gap = math.hypot(p.origin[0] - ex, p.origin[1] - ey)
            sep = " " if gap > 0.15 * p.size and not last.text.endswith(" ") and not p.text.startswith(" ") else ""
            if last.symbol and not p.symbol:   # Greek first: the text takes the next part's font
                last.font, last.bold, last.italic, last.symbol = p.font, p.bold, p.italic, False
            last.text += sep + p.text
            a = math.radians(last.angle)
            px, py = p.end()
            last.width = (px - last.origin[0]) * math.cos(a) + (py - last.origin[1]) * math.sin(a)
            last.refs += p.refs
        else:
            out.append(p)
    for t in out:
        if t.symbol:
            t.font, t.symbol = DEFAULT_FAMILY, False
    return [t for t in out if t.text.strip()]


# ---------------------------------------------------------------------------
# Fonts: which family a file's font is
# ---------------------------------------------------------------------------

_KNOWN = {"timesnewroman": "Times New Roman", "times": "Times", "arial": "Arial", "helvetica": "Helvetica",
          "helveticaneue": "Helvetica Neue", "courier": "Courier", "couriernew": "Courier New",
          "liberationsans": "Liberation Sans", "liberationserif": "Liberation Serif", "dejavusans": "DejaVu Sans",
          "symbol": "Symbol", "calibri": "Calibri", "sansserif": "Helvetica", "serif": "Times", "monospace": "Courier"}


@lru_cache(maxsize=1)
def _ps_names() -> dict:
    from .fonts import get_font_index
    try:
        return {f.ps_name: f for f in get_font_index().faces()}
    except Exception:
        return {}


def font_style(name: str, bold: bool = False, italic: bool = False) -> tuple[str, bool, bool]:
    """(family, bold, italic) for a font named in a file: a PostScript name ("Arial-BoldMT",
    "ABCDEF+Helvetica") or a family ("Helvetica", "Liberation Sans")."""
    name = re.sub(r"^[A-Z]{6}\+", "", (name or "").strip().strip("'\"")) or DEFAULT_FAMILY
    face = _ps_names().get(name)
    if face is not None:
        return face.family, face.bold or bold, face.italic or italic
    low = name.lower()
    bold = bold or bool(re.search(r"bold|black|heavy|semibold|demi", low))
    italic = italic or bool(re.search(r"italic|oblique", low))
    fam = re.split(r"[-,]", name)[0]
    fam = re.sub(r"(PSMT|MT|PS)$", "", fam).strip()
    key = re.sub(r"[\s_]", "", fam).lower()
    if key in _KNOWN:
        return _KNOWN[key], bold, italic
    if " " not in fam:
        fam = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fam)
    return fam or DEFAULT_FAMILY, bold, italic


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

# The Symbol font's codes (R draws Greek and some signs in it)
_SYMBOL = dict(zip(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
                   "ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖαβχδεφγηιϕκλμνοπθρστυϖωξψζ"))
_SYMBOL.update({0x2D: MINUS, 0x22: "∀", 0x24: "∃", 0x27: "∋", 0x2A: "∗", 0x40: "≅", 0x5E: "⊥", 0x7E: "∼",
                0xA2: "′", 0xA3: "≤", 0xA5: "∞", 0xAC: "←", 0xAD: "↑", 0xAE: "→", 0xAF: "↓", 0xB0: "°",
                0xB1: "±", 0xB2: "″", 0xB3: "≥", 0xB4: "×", 0xB5: "∝", 0xB6: "∂", 0xB7: "•", 0xB8: "÷",
                0xB9: "≠", 0xBA: "≡", 0xBB: "≈", 0xBC: "…", 0xC5: "⊕", 0xC6: "∅", 0xC7: "∩", 0xC8: "∪",
                0xCE: "∈", 0xD0: "∠", 0xD1: "∇", 0xD5: "∏", 0xD6: "√", 0xD7: "⋅", 0xD9: "∧", 0xDA: "∨",
                0xE5: "∑", 0xF2: "∫"})


def _utf16(hexstr: str) -> str:
    try:
        return bytes.fromhex(hexstr if len(hexstr) % 2 == 0 else "0" + hexstr).decode("utf-16-be")
    except ValueError:
        return ""


def _to_unicode(obj) -> dict:
    """A ToUnicode CMap: code -> text."""
    if obj is None:
        return {}
    try:
        data = obj.read_bytes().decode("latin-1")
    except Exception:
        return {}
    out: dict = {}
    for block in re.findall(r"beginbfchar(.*?)endbfchar", data, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            out[int(src, 16)] = _utf16(dst)
    for block in re.findall(r"beginbfrange(.*?)endbfrange", data, re.S):
        for m in re.finditer(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(?:<([0-9A-Fa-f]*)>|\[([^\]]*)\])", block):
            lo, hi = int(m.group(1), 16), int(m.group(2), 16)
            if m.group(3) is not None:
                start, digits = int(m.group(3) or "0", 16), max(len(m.group(3)), 4)
                for k in range(min(hi - lo, 65535) + 1):
                    out[lo + k] = _utf16(format(start + k, f"0{digits}X"))
            else:
                for k, d in enumerate(re.findall(r"<([0-9A-Fa-f]*)>", m.group(4))):
                    out[lo + k] = _utf16(d)
    return out


def _cid_widths(w) -> dict:
    import pikepdf
    out: dict = {}
    if w is None:
        return out
    items = list(w)
    i = 0
    while i < len(items):
        first = int(items[i])
        nxt = items[i + 1] if i + 1 < len(items) else None
        if isinstance(nxt, pikepdf.Array):
            for k, v in enumerate(nxt):
                out[first + k] = float(v)
            i += 2
        elif i + 2 < len(items):
            for c in range(first, int(items[i + 1]) + 1):
                out[c] = float(items[i + 2])
            i += 3
        else:
            break
    return out


class _PdfFont:
    """What text-showing needs of a PDF font: each code's text and width."""

    def __init__(self, fd):
        import pikepdf
        from fontTools import agl
        self.subtype = str(fd.get("/Subtype", ""))
        base = str(fd.get("/BaseFont")) if fd.get("/BaseFont") is not None else "/"
        self.ps = re.sub(r"^[A-Z]{6}\+", "", base[1:])
        self.composite = self.subtype == "/Type0"
        self.unicode = _to_unicode(fd.get("/ToUnicode"))
        desc = fd
        if self.composite:
            kids = fd.get("/DescendantFonts")
            desc = kids[0] if kids is not None and len(kids) else fd
            self.dw = float(desc.get("/DW", 1000))
            self.cid_w = _cid_widths(desc.get("/W"))
        else:
            self.first = int(fd.get("/FirstChar", 0))
            self.widths = [float(v) for v in fd.get("/Widths", [])]
            fm = fd.get("/FontMatrix") if self.subtype == "/Type3" else None
            self.fm = float(fm[0]) if fm is not None else 0.001
            self.enc = self._encoding(fd, pikepdf, agl)
        fdesc = desc.get("/FontDescriptor")
        flags = int(fdesc.get("/Flags", 0)) if fdesc is not None else 0
        weight = float(fdesc.get("/FontWeight", 400)) if fdesc is not None else 400
        self.missing = float(fdesc.get("/MissingWidth", 0)) if fdesc is not None else 0.0
        self.symbol = self.ps.startswith("Symbol")
        self.family, self.bold, self.italic = font_style(self.ps, weight >= 600 or bool(flags & (1 << 18)),
                                                         bool(flags & 64))
        self._face = None

    def _encoding(self, fd, pikepdf, agl) -> list:
        from fontTools.encodings.MacRoman import MacRoman
        from fontTools.encodings.StandardEncoding import StandardEncoding
        enc = fd.get("/Encoding")
        base = diffs = None
        if isinstance(enc, pikepdf.Name):
            base = str(enc)
        elif isinstance(enc, pikepdf.Dictionary):
            base = str(enc.get("/BaseEncoding")) if enc.get("/BaseEncoding") is not None else None
            diffs = enc.get("/Differences")
        name = lambda g: agl.toUnicode(g) if g and g != ".notdef" else ""
        if self.ps.startswith("Symbol") and base is None:
            table = [_SYMBOL.get(i, chr(i) if 32 <= i < 127 else "") for i in range(256)]
        elif base == "/MacRomanEncoding":
            table = [name(MacRoman[i]) for i in range(256)]
        elif base == "/WinAnsiEncoding" or (base is None and self.subtype != "/Type1"):
            table = [bytes([i]).decode("cp1252", errors="ignore") or chr(i) for i in range(256)]
        else:
            table = [name(StandardEncoding[i]) for i in range(256)]
        if diffs is not None:
            code = 0
            for v in diffs:
                if not isinstance(v, pikepdf.Name):
                    code = int(v)
                elif 0 <= code < 256:
                    table[code] = name(str(v)[1:])
                    code += 1
        return table

    def _fallback(self, text: str) -> float:
        """A width from the installed font of the same family (fonts without /Widths: the
        standard 14, as R's pdf() uses them), in text space per point of size."""
        if self._face is None:
            from .fonts import resolve_face
            self._face = resolve_face(DEFAULT_FAMILY if self.symbol else self.family, self.bold, self.italic)[0]
        return sum(self._face.advance(self._face.gid(ch)) for ch in text)

    def decode(self, data: bytes) -> list[tuple[str, float, bool]]:
        """(text, width in text space per point of size, a single-byte space) for each code."""
        out = []
        if self.composite:
            for i in range(0, len(data) - 1, 2):
                code = (data[i] << 8) | data[i + 1]
                out.append((self.unicode.get(code, "�"), self.cid_w.get(code, self.dw) / 1000.0, False))
            return out
        for b in data:
            text = self.unicode.get(b) or self.enc[b]
            k = b - self.first
            if 0 <= k < len(self.widths):
                w = self.widths[k] * self.fm
            elif self.widths:
                w = self.missing * self.fm
            else:
                w = self._fallback(text)
            out.append((text, w, b == 32))
        return out


def _pdf_colour(c: tuple) -> str:
    vals = [v for v in c[1:] if isinstance(v, float)]
    if len(vals) == 4:     # CMYK, roughly
        c_, m, y, k = vals
        return _hex(((1 - c_) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)))
    if len(vals) == 3:
        return _hex(vals)
    if len(vals) == 1:
        return _hex(vals * 3)
    return "#000000"


def _pdf_texts(path: str, page_index: int) -> tuple[list[PlotText], dict]:
    """A PDF page's texts, and for each operator that shows one, the TJ number that moves as far."""
    import pikepdf

    from .vectors import _colour, _display
    pieces: list[PlotText] = []
    moves: dict = {}
    with pikepdf.open(path) as pdf:
        page = pdf.pages[page_index]
        to, uu, _size = _display(page)
        fonts: dict = {}

        def font_of(fd):
            key = fd.objgen if fd.is_indirect else id(fd)
            if key not in fonts:
                try:
                    fonts[key] = _PdfFont(fd)
                except Exception:
                    fonts[key] = None
            return fonts[key]

        def show(st, tm, items, ref):
            font = st["font"]
            if font is None:
                return tm
            tfs, th, tc, tw, rise = st["tfs"], st["th"], st["tc"], st["tw"], st["rise"]
            x, text = 0.0, []
            for item in items:
                if isinstance(item, (bytes, bytearray)):
                    for t, w, space in font.decode(item):
                        text.append(t)
                        x += (w * tfs + tc + (tw if space else 0.0)) * th
                else:
                    x -= float(item) / 1000.0 * tfs * th
            moves[ref] = -x / (tfs * th) * 1000.0 if tfs and th else None
            if st["tr"] in (3, 7):   # invisible
                return tm @ Matrix.translate(x, 0.0)
            full = st["ctm"] @ tm
            o = to(*full.apply(0.0, rise))
            e = to(*full.apply(x, rise))
            u = to(*full.apply(1.0, rise))
            up = to(*full.apply(0.0, rise + tfs))
            size = math.hypot(up[0] - o[0], up[1] - o[1])
            angle = math.degrees(math.atan2(u[1] - o[1], u[0] - o[0]))
            a = math.radians(angle)
            width = (e[0] - o[0]) * math.cos(a) + (e[1] - o[1]) * math.sin(a)
            colour = st["sc"] if st["tr"] in (1, 5) else st["fc"]
            pieces.append(PlotText("".join(text), font.family, font.bold, font.italic, size, _pdf_colour(colour),
                                   st["ca"], angle, o, width, "l", [ref], font.symbol))
            return tm @ Matrix.translate(x, 0.0)

        def walk(obj, key, resources, st, active):
            if key in active:
                return
            active = active | {key}
            res_fonts = resources.get("/Font", {}) if resources is not None else {}
            ext = resources.get("/ExtGState", {}) if resources is not None else {}
            xobjects = resources.get("/XObject", {}) if resources is not None else {}
            stack = []
            tm = tlm = Matrix()
            for i, (operands, op) in enumerate(pikepdf.parse_content_stream(obj)):
                o = str(op)
                ref = (key, i)
                if o == "q":
                    stack.append(dict(st))
                elif o == "Q":
                    if stack:
                        st = stack.pop()
                elif o == "cm" and len(operands) == 6:
                    st["ctm"] = st["ctm"] @ Matrix(*(float(v) for v in operands))
                elif o == "gs" and operands:
                    g = ext.get(operands[0])
                    if g is not None:
                        if "/ca" in g:
                            st["ca"] = float(g.ca)
                        if "/Font" in g:
                            st["font"], st["tfs"] = font_of(g.Font[0]), float(g.Font[1])
                elif o in ("RG", "G", "K", "SC", "SCN"):
                    st["sc"] = _colour(o, operands, st["ss"])
                elif o in ("rg", "g", "k", "sc", "scn"):
                    st["fc"] = _colour(o, operands, st["fs"])
                elif o == "CS" and operands:
                    st["ss"] = str(operands[0])
                elif o == "cs" and operands:
                    st["fs"] = str(operands[0])
                elif o == "BT":
                    tm = tlm = Matrix()
                elif o == "Tf" and len(operands) == 2:
                    fd = res_fonts.get(operands[0])
                    st["font"] = font_of(fd) if fd is not None else None
                    st["tfs"] = float(operands[1])
                elif o == "Tc" and operands:
                    st["tc"] = float(operands[0])
                elif o == "Tw" and operands:
                    st["tw"] = float(operands[0])
                elif o == "Tz" and operands:
                    st["th"] = float(operands[0]) / 100.0
                elif o == "TL" and operands:
                    st["tl"] = float(operands[0])
                elif o == "Ts" and operands:
                    st["rise"] = float(operands[0])
                elif o == "Tr" and operands:
                    st["tr"] = int(operands[0])
                elif o in ("Td", "TD") and len(operands) == 2:
                    tx, ty = float(operands[0]), float(operands[1])
                    if o == "TD":
                        st["tl"] = -ty
                    tlm = tlm @ Matrix.translate(tx, ty)
                    tm = tlm
                elif o == "Tm" and len(operands) == 6:
                    tm = tlm = Matrix(*(float(v) for v in operands))
                elif o == "T*":
                    tlm = tlm @ Matrix.translate(0.0, -st["tl"])
                    tm = tlm
                elif o == "Tj" and operands:
                    tm = show(st, tm, [bytes(operands[0])], ref)
                elif o == "TJ" and operands:
                    tm = show(st, tm, [bytes(v) if isinstance(v, pikepdf.String) else float(v) for v in operands[0]], ref)
                elif o in ("'", '"') and operands:
                    if o == '"' and len(operands) == 3:
                        st["tw"], st["tc"] = float(operands[0]), float(operands[1])
                    tlm = tlm @ Matrix.translate(0.0, -st["tl"])
                    tm = show(st, tlm, [bytes(operands[-1])], ref)
                elif o == "Do" and operands:
                    xo = xobjects.get(operands[0])
                    if xo is not None and xo.get("/Subtype") == pikepdf.Name.Form:
                        m = Matrix(*(float(v) for v in xo.get("/Matrix", [1, 0, 0, 1, 0, 0])))
                        sub = f"{xo.objgen[0]}.{xo.objgen[1]}"
                        walk(xo, sub, xo.get("/Resources", resources), {**st, "ctm": st["ctm"] @ m}, active)

        start = {"ctm": Matrix(), "ca": 1.0, "sc": ("rgb", 0.0, 0.0, 0.0), "fc": ("rgb", 0.0, 0.0, 0.0),
                 "ss": "/DeviceGray", "fs": "/DeviceGray", "font": None, "tfs": 0.0, "tc": 0.0, "tw": 0.0,
                 "th": 1.0, "tl": 0.0, "rise": 0.0, "tr": 0}
        walk(page.obj, "page", page.obj.get("/Resources"), start, frozenset())
    return _join(pieces), moves


def _pdf_hide(path: str, page_index: int, refs: list, moves: dict) -> bytes:
    """The PDF with the operators at `refs` showing nothing but moving as far as they did."""
    import pikepdf
    by_stream: dict = {}
    for key, i in refs:
        by_stream.setdefault(key, set()).add(i)
    with pikepdf.open(path) as pdf:
        page = pdf.pages[page_index]
        targets = {"page": page.obj}

        def find_forms(obj, seen):
            res = obj.get("/Resources")
            for _, xo in (res.get("/XObject", {}) if res is not None else {}).items():
                if xo.get("/Subtype") == pikepdf.Name.Form and xo.is_indirect and xo.objgen not in seen:
                    seen.add(xo.objgen)
                    targets[f"{xo.objgen[0]}.{xo.objgen[1]}"] = xo
                    find_forms(xo, seen)
        find_forms(page.obj, set())
        for key, wanted in by_stream.items():
            obj = targets.get(key)
            if obj is None:
                continue
            ops = list(pikepdf.parse_content_stream(obj))
            out = []
            for i, (operands, op) in enumerate(ops):
                if i not in wanted:
                    out.append((operands, op))
                    continue
                o = str(op)
                n = moves.get((key, i))
                if o == '"' and len(operands) == 3:
                    out += [([operands[0]], pikepdf.Operator("Tw")), ([operands[1]], pikepdf.Operator("Tc"))]
                if o in ("'", '"'):
                    out.append(([], pikepdf.Operator("T*")))
                if n is not None:
                    out.append(([pikepdf.Array([round(n, 3)])], pikepdf.Operator("TJ")))
                else:   # (no font size to measure the move by: shown invisibly instead)
                    out += [([3], pikepdf.Operator("Tr")), (operands[-1:], pikepdf.Operator("Tj" if o != "TJ" else "TJ")),
                            ([0], pikepdf.Operator("Tr"))]
            data = pikepdf.unparse_content_stream(out)
            if key == "page":
                page.obj.Contents = pdf.make_stream(data)
            else:
                obj.write(data)
        buf = io.BytesIO()
        pdf.save(buf, deterministic_id=True)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

TEXT_PROPS = {"font-family", "font-size", "font-weight", "font-style", "fill", "fill-opacity", "opacity",
              "text-anchor", "visibility", "display"}
TEXT_INHERITED = ("font-family", "font-size", "font-weight", "font-style", "fill", "fill-opacity", "text-anchor",
                  "visibility")
_SKIP = {"defs", "clipPath", "mask", "marker", "pattern", "symbol", "linearGradient", "radialGradient", "filter",
         "metadata", "title", "desc", "style", "script", "image", "foreignObject"}


def _first(value) -> float | None:
    m = re.match(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)", value or "")
    return float(m.group(1)) if m else None


def _svg_parse(path: str):
    from lxml import etree
    return etree.parse(path, etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True))


def _svg_texts(path: str) -> list[PlotText]:
    from lxml import etree

    from .assets import svg_geometry, svg_user_matrix
    from .fonts import resolve_face
    from .vectors import _css_rules, _declarations, _length, _number, _selects, _svg_colour, _transform
    root = _svg_parse(path).getroot()
    to_pt = svg_user_matrix(svg_geometry(root))
    rules = _css_rules(root, TEXT_PROPS)
    pieces: list[PlotText] = []

    def own_style(el, chain):
        style = {k: el.get(k) for k in TEXT_PROPS if el.get(k) is not None}
        for _, _, parts, decls in rules:
            if _selects(parts, chain):
                style.update(decls)
        style.update(_declarations(el.get("style"), TEXT_PROPS))
        return style

    def look(style):
        fam = (style.get("font-family") or DEFAULT_FAMILY).split(",")[0].strip().strip("'\"")
        weight = (style.get("font-weight") or "normal").strip().lower()
        bold = weight in ("bold", "bolder") or (weight.isdigit() and int(weight) >= 600)
        italic = (style.get("font-style") or "").strip().lower() in ("italic", "oblique")
        family, bold, italic = font_style(fam, bold, italic)
        size = _length(style.get("font-size"), 16.0)
        colour = _svg_colour(style.get("fill") or "#000000")
        hexc = _hex(colour[1:4]) if colour[0] == "rgb" else "#000000"
        return family, bold, italic, size, hexc

    def text_of(el) -> str:
        return re.sub(r"\s+", " ", "".join(el.itertext()))

    def measure(text, family, bold, italic, size):
        face = resolve_face(family, bold, italic)[0]
        return face.text_width(text, size)

    def read_text(el, ctm, style, chain, path):
        # The parts of a <text>: its own words, each <tspan> and the words after one, each at a
        # place of its own or carrying on from the last
        parts = []   # (text, style, x or None, y or None, ref)
        if el.text and el.text.strip():
            parts.append((el.text, style, None, None, f"{path}:t"))
        for i, child in enumerate(el):
            if not isinstance(child.tag, str):
                continue
            if etree.QName(child).localname == "tspan":
                cchain = chain + [("tspan", set((child.get("class") or "").split()), child.get("id"))]
                cstyle = {**style, **{k: v for k, v in own_style(child, cchain).items() if k in TEXT_INHERITED}}
                if cstyle.get("display") != "none":
                    parts.append((text_of(child), cstyle, _first(child.get("x")), _first(child.get("y")), f"{path}/{i}"))
            if child.tail and child.tail.strip():
                parts.append((child.tail, style, None, None, f"{path}/{i}:tail"))
        x = (_first(el.get("x")) or 0.0) + (_first(el.get("dx")) or 0.0)
        y = (_first(el.get("y")) or 0.0) + (_first(el.get("dy")) or 0.0)
        chunks = []   # each [start x, y, anchor, [(text, style, width, ref)]]
        for k, (text, st, px, py, ref) in enumerate(parts):
            text = re.sub(r"\s+", " ", text)
            if k == 0:
                text = text.lstrip()
            if k == len(parts) - 1:
                text = text.rstrip()
            fam, bold, italic, size, _ = look(st)
            if px is not None or py is not None or not chunks:
                x = px if px is not None else x
                y = py if py is not None else y
                chunks.append([x, y, (st.get("text-anchor") or "start").strip(), []])
            w = measure(text, fam, bold, italic, size)
            chunks[-1][3].append((text, st, w, ref))
            x += w
        length = _length(el.get("textLength"), 0.0) if el.get("textLength") else None
        for cx, cy, anchor, items in chunks:
            total = sum(w for _, _, w, _ in items)
            if length and len(chunks) == 1 and total > 0:   # svglite gives R's own width
                items = [(t, s, w * length / total, r) for t, s, w, r in items]
                total = length
            start = cx - (total / 2 if anchor == "middle" else total if anchor == "end" else 0.0)
            align = {"middle": "ctr", "end": "r"}.get(anchor, "l")
            at = start
            for text, st, w, ref in items:
                if st.get("visibility") in ("hidden", "collapse") or not text:
                    at += w
                    continue
                fam, bold, italic, size, colour = look(st)
                o = ctm.apply(at, cy)
                e = ctm.apply(at + w, cy)
                u = ctm.apply(at + 1.0, cy)
                up = ctm.apply(at, cy - size)
                angle = math.degrees(math.atan2(u[1] - o[1], u[0] - o[0]))
                op = _number(st.get("fill-opacity"), 1.0) * st.get("_opacity", 1.0)
                pieces.append(PlotText(text, fam, bold, italic, math.hypot(up[0] - o[0], up[1] - o[1]), colour,
                                       op, angle, o, math.hypot(e[0] - o[0], e[1] - o[1]), align, [ref]))
                at += w

    def walk(el, ctm, inherited, chain, path):
        if not isinstance(el.tag, str):
            return
        tag = etree.QName(el).localname
        if tag in _SKIP:
            return
        chain = chain + [(tag, set((el.get("class") or "").split()), el.get("id"))]
        own = own_style(el, chain)
        if own.get("display") == "none":
            return
        opacity = inherited.get("_opacity", 1.0) * _number(own.get("opacity"), 1.0)
        if opacity <= 0:
            return
        style = {**inherited, **{k: v for k, v in own.items() if k in TEXT_INHERITED and v != "inherit"},
                 "_opacity": opacity}
        if el.get("transform"):
            ctm = ctm @ _transform(el.get("transform"))
        if tag == "text":
            read_text(el, ctm, style, chain, path)
            return
        for i, child in enumerate(el):
            walk(child, ctm, style, chain, f"{path}.{i}")

    walk(root, to_pt, {}, [], "0")
    return _join(pieces)


def _svg_node(root, path: str):
    """The element a path of child numbers ("0.3.12") leads to."""
    parts = path.split(".")
    el = root
    for k in parts[1:]:
        kids = list(el)
        i = int(k)
        if i >= len(kids):
            return None
        el = kids[i]
    return el


def _svg_hide(path: str, refs: list) -> bytes:
    from lxml import etree
    tree = _svg_parse(path)
    root = tree.getroot()
    ns = etree.QName(root).namespace
    tspan = f"{{{ns}}}tspan" if ns else "tspan"

    def invisible(el):
        el.set("style", ((el.get("style") or "").rstrip().rstrip(";") + ";visibility:hidden").lstrip(";"))

    # Every part to hide, grouped by its <text>; resolved before anything changes
    by_text: dict = {}
    for ref in refs:
        m = re.fullmatch(r"([\d.]+)(?:(:t)|/(\d+)(:tail)?)", ref)
        if not m:
            continue
        el = _svg_node(root, m.group(1))
        if el is not None:
            by_text.setdefault(el, []).append(("own" if m.group(2) else "tail" if m.group(4) else "tspan",
                                               int(m.group(3)) if m.group(3) else None))
    for el, parts in by_text.items():
        kids = list(el)
        # Every part of the <text> that shows: when all of them go, the element goes
        shown = {("own", None)} if el.text and el.text.strip() else set()
        for i, c in enumerate(kids):
            if isinstance(c.tag, str) and etree.QName(c).localname == "tspan" and "".join(c.itertext()).strip():
                shown.add(("tspan", i))
            if c.tail and c.tail.strip():
                shown.add(("tail", i))
        if shown <= set(parts):
            parent = el.getparent()
            if parent is None:
                continue
            if el.tail:   # (keep the whitespace after it)
                prev = el.getprevious()
                if prev is not None:
                    prev.tail = (prev.tail or "") + el.tail
                else:
                    parent.text = (parent.text or "") + el.tail
            parent.remove(el)
            continue
        for kind, i in parts:
            if kind == "tspan":
                invisible(kids[i])
            elif kind == "own":
                wrap = etree.Element(tspan)
                wrap.text, el.text = el.text, None
                invisible(wrap)
                el.insert(0, wrap)
            else:
                wrap = etree.Element(tspan)
                wrap.text, kids[i].tail = kids[i].tail, None
                invisible(wrap)
                kids[i].addnext(wrap)
    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8")


# ---------------------------------------------------------------------------
# What the editor and the exports use
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _read(path: str, kind: str, page_index: int) -> tuple:
    """A file's texts (and a PDF's moves). The files are content-addressed copies, so a path's
    contents never change."""
    if kind == "pdf":
        texts, moves = _pdf_texts(path, page_index)
        return texts, moves
    return _svg_texts(path), {}


def texts(path: str, kind: str, page_index: int = 0) -> list[dict]:
    return [t.record(i) for i, t in enumerate(_read(path, kind, page_index)[0])]


def plot_texts(asset: dict, page_index: int = 0, prefer: str | None = None, cache=None) -> dict:
    """A placed plot's texts for the editor: from the copy it shows (`prefer`), else its SVG copy
    (it says how each text lines up), else its PDF copy, whichever has some. R lays out a plot's
    PDF and SVG a little differently, so texts are lifted from the copy on screen. {"kind": ...,
    "texts": [...]}; no texts for a photo, or a file whose letters are drawn as outlines."""
    from .assets import get_cache
    cache = cache or get_cache()
    variants = (asset or {}).get("variants", {})
    for kind in dict.fromkeys([k for k in (prefer, "svg", "pdf") if k in ("svg", "pdf")]):
        if kind not in variants:
            continue
        found = texts(cache.path(variants[kind]["sha256"], kind), kind, int(page_index or 0) if kind == "pdf" else 0)
        if found:
            return {"kind": kind, "texts": found}
    return {"kind": None, "texts": []}


def match(found: list, d: dict, used=()) -> int | None:
    """Which of a file's texts (records or PlotTexts) is the one lifted as `d`: the same words,
    size and angle, its middle close by; the nearest if several are."""
    best, best_d = None, None
    want = _norm(d.get("text", ""))
    mid = d.get("mid") or [0.0, 0.0]
    size = float(d.get("size", 0.0))
    for i, t in enumerate(found):
        if i in used:
            continue
        rec = t if isinstance(t, dict) else t.record(i)
        if _norm(rec["text"]) != want or abs(_turn(rec["angle"] - float(d.get("angle", 0.0)))) > 2.0:
            continue
        if abs(rec["size"] - size) > max(0.6, 0.12 * size):   # (R's pdf() writes 4.8 pt text at 5 pt)
            continue
        dist = math.hypot(rec["mid"][0] - mid[0], rec["mid"][1] - mid[1])
        if dist > max(1.5, 0.5 * size):
            continue
        if best_d is None or dist < best_d:
            best, best_d = i, dist
    return best


def descriptor(t: dict) -> dict:
    """What a picture keeps of a text it lifted, to find it again (in its other copies, or in a
    file R saved again)."""
    return {k: t[k] for k in ("text", "size", "angle", "mid", "font", "bold", "italic")}


def lift_box(t: dict, scale: float = 1.0) -> dict:
    """A text box for a lifted text, in the source's points: its frame (unturned) and turn, so its
    letters sit where the plot's were at `scale` (the picture's size against its file), with the
    same alignment, and its text. The editor scales it onto the page."""
    from .fonts import resolve_face
    from .textlayout import first_baseline, line_height
    scale = float(scale or 1.0)
    size = float(t["size"]) * scale
    face = resolve_face(t["font"], bool(t["bold"]), bool(t["italic"]))[0]
    wm = face.text_width(t["text"], size) / scale
    lh = line_height(face, size)
    base = first_baseline(face, size, lh) / scale
    lh /= scale
    width = float(t["width"])
    x0 = {"ctr": width / 2 - wm / 2, "r": width - wm}.get(t.get("align"), 0.0)
    cx, cy = x0 + wm / 2, -base + lh / 2          # the frame's middle, from the baseline's start
    a = math.radians(float(t["angle"]))
    ox, oy = t["origin"]
    mx, my = ox + cx * math.cos(a) - cy * math.sin(a), oy + cx * math.sin(a) + cy * math.cos(a)
    run = {"t": t["text"], "font": t["font"], "size": float(t["size"]), "bold": bool(t["bold"]),
           "italic": bool(t["italic"]), "color": t.get("color", "#000000")}
    if float(t.get("opacity", 1.0)) < 0.999:
        run["opacity"] = float(t["opacity"])
    return {"frame": [mx - wm / 2, my - lh / 2, wm, lh], "rot": float(t["angle"]) % 360.0,
            "align": t.get("align", "l"), "run": run}


def _wanted(d: dict) -> str:
    return json.dumps(descriptor(d), sort_keys=True)


def _key(var: dict, kind: str, page_index: int, hidden: list[dict]) -> str:
    wanted = sorted(_wanted(d) for d in hidden)
    return hashlib.sha256(json.dumps([var["sha256"], kind, page_index, wanted]).encode()).hexdigest()[:32]


def derived(asset: dict, page_index: int, hidden: list[dict], cache=None) -> dict:
    """A picture's copies without the texts it lifted: {"variants": {kind: variant},
    "missing": {kind: [ids of lifted texts not found in that copy]}}. Raster copies are left
    out (a plot exports from its PDF and SVG). Each copy is kept in the cache, so it's made once."""
    from .assets import get_cache, probe
    cache = cache or get_cache()
    out, missing = {}, {}
    for kind in ("pdf", "svg"):
        var = asset.get("variants", {}).get(kind)
        if not var:
            continue
        page = int(page_index or 0) if kind == "pdf" else 0
        note = cache.derived(f"lift2-{_key(var, kind, page, hidden)}", ".json")
        made = None
        if os.path.exists(note):
            try:
                with open(note, encoding="utf-8") as fh:
                    made = json.load(fh)
                if not cache.has(made["variant"]["sha256"], kind):
                    made = None
            except (OSError, ValueError, KeyError):
                made = None
        if made is None:
            src = cache.path(var["sha256"], kind)
            found, moves = _read(src, kind, page)
            refs, lost, used = [], [], set()
            for d in hidden:
                i = match(found, d, used)
                if i is None:
                    lost.append(_wanted(d))   # (by what it is: the copy is kept for any picture lifting the same)
                else:
                    used.add(i)
                    refs += found[i].refs
            record = var
            if refs:
                data = _pdf_hide(src, page, refs, moves) if kind == "pdf" else _svg_hide(src, refs)
                sha, p = cache.put_bytes(data, kind)
                record = {"sha256": sha, "kind": kind, "bytes": len(data)}
                record.update({k: v for k, v in probe(p, kind).items() if k != "kind"})
            made = {"variant": record, "missing": lost}
            with open(note + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(made, fh)
            os.replace(note + ".tmp", note)
        out[kind] = made["variant"]
        missing[kind] = [d.get("id") for d in hidden if _wanted(d) in made["missing"]]
    return {"variants": out, "missing": missing}


def notes(name: str, it: dict, asset: dict) -> list[tuple[str, str]]:
    """Check's notes on a picture with texts lifted out (its asset as with_lifts made it):
    (level, message)."""
    out = []
    hidden = lifted(it)
    if hidden:
        words = ", ".join(f"“{d.get('text', '')}”" for d in hidden[:3]) + (", …" if len(hidden) > 3 else "")
        out.append(("info", f"{name}: {len(hidden)} text{'s' if len(hidden) != 1 else ''} lifted out in dangerous mode "
                            f"({words}), now text boxes rather than part of its file"))
        missing = asset.get("lifted_missing") or {}
        for d in hidden:
            lost = [k for k, ids in missing.items() if d.get("id") in ids]
            if not lost:
                continue
            if len(lost) == len(missing):
                out.append(("warning", f"{name}: “{d.get('text', '')}” isn't in its file any more, so its text box "
                                       f"stands alone"))
            else:
                kinds = " and ".join(k.upper() for k in lost)
                out.append(("warning", f"{name}: “{d.get('text', '')}” couldn't be found in its {kinds} copy, so "
                                       f"{kinds} export shows it as well as its text box"))
    for d in ((it.get("lifted_text") or {}).get("dropped")) or []:
        out.append(("info", f"{name}: the edit to “{d.get('text', '')}” was dropped when its file changed, as the "
                            f"text isn't there any more (its text box had “{d.get('box_text', '')}”)"))
    return out


def lifted(it: dict) -> list[dict]:
    """The texts a picture item has lifted out of its plot."""
    return list(((it.get("lifted_text") or {}).get("hidden")) or [])


def with_lifts(doc: dict, cache=None) -> dict:
    """The document as exported and checked: each picture that lifted texts out of its plot
    uses a copy of its file without them (an asset of its own, "<asset>~<key>"). The document
    passed in isn't changed; one without lifted texts comes back as it is."""
    from .model import iter_items
    if not any(lifted(it) for page in doc.get("pages", []) for it in iter_items(page.get("items", []))
               if it.get("type") == "picture"):
        return doc
    doc = json.loads(json.dumps(doc))
    for page in doc["pages"]:
        for it in iter_items(page.get("items", [])):
            hidden = lifted(it) if it.get("type") == "picture" else []
            asset = doc["assets"].get(it.get("asset")) if hidden else None
            if not asset or not any(k in asset.get("variants", {}) for k in ("pdf", "svg")):
                continue
            try:
                got = derived(asset, it.get("page_index", 0), hidden, cache)
            except Exception:
                continue
            key = f"{it['asset']}~{_key({'sha256': ''}, '', it.get('page_index', 0), hidden)[:12]}"
            for v in got["variants"].values():
                v.pop("src", None)
            doc["assets"][key] = {**asset, "variants": got["variants"], "auto_update": False, "lifted_from": it["asset"],
                                  "lifted_missing": got["missing"]}
            it["asset"] = key
    return doc

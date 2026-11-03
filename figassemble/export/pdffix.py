"""Embed fonts that placed PDFs reference but don't contain (R's pdf() and Helvetica).

Only the font resources change: each unembedded simple font gets a CFF (Type1C) program
holding just the characters the drawing uses, built from the installed font, with widths
rounded to the standard AFM metrics R laid the text out with. The drawing instructions and
the character codes they show are left byte-for-byte as they were.
"""
from __future__ import annotations

import hashlib
import logging

import pikepdf
from pikepdf import Array, Dictionary, Name

from ..fonts import resolve_face

logging.getLogger("fontTools").setLevel(logging.ERROR)

# Base-14 (and common) font names -> (family, bold, italic)
_STANDARD = {
    "Helvetica": ("Helvetica", False, False), "Helvetica-Bold": ("Helvetica", True, False),
    "Helvetica-Oblique": ("Helvetica", False, True), "Helvetica-BoldOblique": ("Helvetica", True, True),
    "Arial": ("Arial", False, False), "ArialMT": ("Arial", False, False),
    "Arial-Bold": ("Arial", True, False), "Arial-BoldMT": ("Arial", True, False),
    "Arial-Italic": ("Arial", False, True), "Arial-ItalicMT": ("Arial", False, True),
    "Arial-BoldItalicMT": ("Arial", True, True),
    "Times-Roman": ("Times", False, False), "Times-Bold": ("Times", True, False),
    "Times-Italic": ("Times", False, True), "Times-BoldItalic": ("Times", True, True),
    "TimesNewRomanPSMT": ("Times New Roman", False, False),
    "Courier": ("Courier", False, False), "Courier-Bold": ("Courier", True, False),
    "Courier-Oblique": ("Courier", False, True), "Courier-BoldOblique": ("Courier", True, True),
}


def _base_encoding(name: str) -> list[str]:
    from fontTools.agl import UV2AGL
    from fontTools.encodings.MacRoman import MacRoman
    from fontTools.encodings.StandardEncoding import StandardEncoding
    if name == "MacRomanEncoding":
        return list(MacRoman)
    if name == "WinAnsiEncoding":
        out = []
        for code in range(256):
            try:
                ch = bytes([code]).decode("cp1252")
            except UnicodeDecodeError:
                out.append(".notdef")
                continue
            out.append(UV2AGL.get(ord(ch), f"uni{ord(ch):04X}") if code >= 32 else ".notdef")
        out[0xA0], out[0xAD] = "space", "hyphen"   # PDF's WinAnsi quirks
        return out
    return list(StandardEncoding)


def code_names(font) -> list[str]:
    enc = font.get("/Encoding")
    if isinstance(enc, pikepdf.Name):
        names = _base_encoding(str(enc)[1:])
    elif isinstance(enc, pikepdf.Dictionary):
        base = enc.get("/BaseEncoding")
        names = _base_encoding(str(base)[1:] if base is not None else "StandardEncoding")
        code = 0
        for v in enc.get("/Differences", []):
            if isinstance(v, (int, pikepdf.Object)) and not isinstance(v, pikepdf.Name):
                try:
                    code = int(v)
                    continue
                except (TypeError, ValueError):
                    pass
            if isinstance(v, pikepdf.Name) and 0 <= code < 256:
                names[code] = str(v)[1:]
                code += 1
    else:
        names = _base_encoding("StandardEncoding")
    return names


def _needs_embedding(font) -> bool:
    if font.get("/Subtype") not in (Name.Type1, Name.TrueType, Name.MMType1):
        return False
    fd = font.get("/FontDescriptor")
    return fd is None or not any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3"))


def _strings(operands) -> list[bytes]:
    out = []
    for o in operands:
        if isinstance(o, pikepdf.String):
            out.append(bytes(o))
        elif isinstance(o, pikepdf.Array):
            out += [bytes(x) for x in o if isinstance(x, pikepdf.String)]
    return out


def collect_codes(obj, resources, used: dict, seen: set) -> None:
    """Character codes shown with each font (keyed by font objgen), recursing into forms."""
    key = obj.objgen if obj.is_indirect else id(obj)
    if key in seen:
        return
    seen.add(key)
    fonts = resources.get("/Font", {}) if resources is not None else {}
    xobjects = resources.get("/XObject", {}) if resources is not None else {}
    current = None
    for operands, op in pikepdf.parse_content_stream(obj):
        o = str(op)
        if o == "Tf":
            current = fonts.get(operands[0])
        elif o in ("Tj", "TJ", "'", '"') and current is not None:
            entry = used.setdefault(current.objgen, {"font": current, "codes": set()})
            for s in _strings(operands):
                entry["codes"].update(s)
        elif o == "Do":
            xo = xobjects.get(operands[0])
            if xo is not None and xo.get("/Subtype") == Name.Form:
                collect_codes(xo, xo.get("/Resources", resources), used, seen)


def _cff_font(face, ps_name: str, glyphs: dict[str, int]) -> tuple[bytes, dict[str, float]]:
    """Build a CFF program with the named glyphs from an installed face (1000 units/em)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    tt = TTFont(face.ref.path, fontNumber=face.ref.index)
    gs = tt.getGlyphSet()
    order = tt.getGlyphOrder()
    scale = 1000.0 / tt["head"].unitsPerEm
    names = [".notdef"] + sorted(n for n in glyphs if n != ".notdef")
    charstrings, widths = {}, {}
    for name in names:
        gname = order[glyphs[name]] if name in glyphs else ".notdef"
        adv = round(gs[gname].width * scale) if gname in gs else 0   # integer AFM-style widths
        widths[name] = adv
        pen = T2CharStringPen(adv, gs)
        if gname in gs:
            gs[gname].draw(TransformPen(pen, (scale, 0, 0, scale, 0, 0)))
        charstrings[name] = pen.getCharString()
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(names)
    fb.setupCFF(ps_name, {"FullName": ps_name, "FamilyName": face.ref.family}, charstrings, {})
    data = fb.font["CFF "].compile(fb.font)
    tt.close()
    return data, widths


def embed_missing_fonts(pdf: pikepdf.Pdf, roots: list) -> tuple[list[str], list[str]]:
    """Embed every unembedded simple font used by the given form XObjects (in place). Returns
    warnings (a font that couldn't be embedded, or only a stand-in) and notes (what was embedded,
    which is FigAssemble doing its job, not a problem)."""
    used: dict = {}
    seen: set = set()
    for form in roots:
        collect_codes(form, form.get("/Resources"), used, seen)
    warnings, notes = [], []
    done: dict[str, int] = {}
    for entry in used.values():
        font = entry["font"]
        if not _needs_embedding(font) or not entry["codes"]:
            continue
        base = str(font.get("/BaseFont", "/"))[1:].split("+")[-1]
        family = _STANDARD.get(base)
        if family is None:
            if base in ("Symbol", "ZapfDingbats"):
                warnings.append(f"{base} is used but can't be embedded automatically yet")
                continue
            family = (base.split("-")[0], "Bold" in base, any(k in base for k in ("Italic", "Oblique")))
        face, _ = resolve_face(*family)
        if not face.ref.family.lower().startswith(family[0].lower()):
            warnings.append(f"{base}: {family[0]} isn't installed, embedded {face.ref.family} instead")
        names = code_names(font)
        glyphs = {}
        for code in sorted(entry["codes"]):
            gname = names[code] if code < len(names) else ".notdef"
            if gname == ".notdef":
                continue
            from fontTools.agl import toUnicode
            text = toUnicode(gname)
            gid = face.gid(text[0]) if text else 0
            if gid:
                glyphs[gname] = gid
        tag = "".join(chr(ord("A") + b % 26) for b in hashlib.sha1(
            (base + ",".join(sorted(glyphs))).encode()).digest()[:6])
        ps = f"{tag}+{base}"
        data, widths = _cff_font(face, base, glyphs)
        first, last = min(entry["codes"]), max(entry["codes"])
        width_list = [widths.get(names[c], 0) if c < len(names) else 0 for c in range(first, last + 1)]
        stream = pdf.make_stream(data)
        stream.Subtype = Name.Type1C
        desc = Dictionary(Type=Name.FontDescriptor, FontName=Name("/" + ps),
                          Flags=32 | (64 if family[2] else 0),
                          FontBBox=Array([round(v * 1000) for v in face.bbox]),
                          ItalicAngle=face.italic_angle, Ascent=round(face.ascent * 1000),
                          Descent=round(-face.descent * 1000), CapHeight=round(face.cap_height * 1000),
                          StemV=80, FontFile3=stream)
        font.Subtype = Name.Type1
        font.BaseFont = Name("/" + ps)
        font.FirstChar, font.LastChar = first, last
        font.Widths = Array(width_list)
        font.FontDescriptor = pdf.make_indirect(desc)
        done[base] = done.get(base, 0) + 1
    if done:
        notes.append("embedded fonts the placed PDFs lacked: " +
                     ", ".join(f"{k}" + (f" (x{v})" if v > 1 else "") for k, v in sorted(done.items())))
    return warnings, notes

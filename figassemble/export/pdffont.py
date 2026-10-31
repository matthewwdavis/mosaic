"""Embed font subsets for text FigAssemble draws itself (Type0 / Identity-H fonts).

Glyph IDs are kept (retain_gids), so a CID is the glyph ID and /W carries exactly the
advances text layout used: what the layout measured is what the PDF positions.
"""
from __future__ import annotations

import hashlib
import io
import logging

import pikepdf
from pikepdf import Array, Dictionary, Name

from ..fonts import Face

logging.getLogger("fontTools").setLevel(logging.ERROR)


def _subset_tag(seed: str) -> str:
    digest = hashlib.sha1(seed.encode()).digest()
    return "".join(chr(ord("A") + b % 26) for b in digest[:6])


def _to_unicode_cmap(mapping: dict[int, str]) -> bytes:
    entries = []
    for gid, text in sorted(mapping.items()):
        utf16 = text.encode("utf-16-be").hex().upper()
        entries.append(f"<{gid:04X}> <{utf16}>")
    blocks = []
    for i in range(0, len(entries), 100):
        chunk = entries[i:i + 100]
        blocks.append(f"{len(chunk)} beginbfchar\n" + "\n".join(chunk) + "\nendbfchar")
    body = "\n".join(blocks)
    return ("/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
            "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
            f"{body}\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n").encode("ascii")


def _widths_array(face: Face, gids: list[int]) -> Array:
    """/W entries grouping consecutive glyph IDs: [first [w1 w2 ...] ...]."""
    out = []
    run: list[float] = []
    start = prev = None
    for gid in gids:
        w = round(face.advance(gid) * 1000.0, 4)
        if prev is not None and gid == prev + 1:
            run.append(w)
        else:
            if run:
                out += [start, Array(run)]
            start, run = gid, [w]
        prev = gid
    if run:
        out += [start, Array(run)]
    return Array(out)


class FontEmbedder:
    def __init__(self, pdf: pikepdf.Pdf):
        self.pdf = pdf
        self._fonts: dict[tuple[str, int], dict] = {}

    def use(self, face: Face, gids: list[int], text: str) -> pikepdf.Object:
        """Register glyphs for a face; returns its (indirect) Type0 font dictionary."""
        entry = self._fonts.get(face.key)
        if entry is None:
            obj = self.pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type0))
            entry = {"obj": obj, "face": face, "map": {}}
            self._fonts[face.key] = entry
        for gid, ch in zip(gids, text):
            entry["map"].setdefault(gid, ch)
        return entry["obj"]

    def finalize(self) -> list[str]:
        """Build every subset. Call once, after all pages are drawn and before saving."""
        warnings = []
        for entry in self._fonts.values():
            face: Face = entry["face"]
            if not face.embeddable:
                warnings.append(f"{face.ps_name} doesn't allow embedding; its text may display "
                                f"with a substitute font")
            self._build(entry)
        return warnings

    def _build(self, entry: dict) -> None:
        from fontTools import subset
        from fontTools.ttLib import TTFont

        face: Face = entry["face"]
        gids = sorted(set(entry["map"]) | {0})
        tt = TTFont(face.ref.path, fontNumber=face.ref.index)
        opts = subset.Options()
        opts.retain_gids = True
        opts.notdef_outline = True
        opts.name_IDs = ["*"]
        opts.name_languages = ["*"]
        opts.layout_features = []
        opts.hinting = False
        opts.desubroutinize = True
        opts.glyph_names = False
        opts.legacy_kern = False
        opts.drop_tables += ["GSUB", "GPOS", "GDEF", "kern", "morx", "kerx", "feat", "trak", "meta",
                             "DSIG", "BASE", "JSTF", "MATH", "SVG ", "sbix", "CBDT", "CBLC", "COLR", "CPAL"]
        sub = subset.Subsetter(opts)
        sub.populate(gids=gids)
        sub.subset(tt)
        buf = io.BytesIO()
        tt.save(buf)
        data = buf.getvalue()
        tt.close()

        base = f"{_subset_tag(face.ps_name + ':' + ','.join(map(str, gids)))}+{face.ps_name}"
        flags = 32 | (64 if face.italic_angle else 0)
        upm_bbox = [round(v * 1000.0) for v in face.bbox]
        descriptor = Dictionary(
            Type=Name.FontDescriptor, FontName=Name("/" + base), Flags=flags,
            FontBBox=Array(upm_bbox), ItalicAngle=face.italic_angle,
            Ascent=round(face.ascent * 1000.0), Descent=round(-face.descent * 1000.0),
            CapHeight=round(face.cap_height * 1000.0), StemV=80)
        if face.is_cff:
            stream = self.pdf.make_stream(data)
            stream.Subtype = Name.OpenType
            descriptor.FontFile3 = stream
            subtype = Name.CIDFontType0
        else:
            stream = self.pdf.make_stream(data)
            stream.Length1 = len(data)
            descriptor.FontFile2 = stream
            subtype = Name.CIDFontType2
        cid = Dictionary(
            Type=Name.Font, Subtype=subtype, BaseFont=Name("/" + base),
            CIDSystemInfo=Dictionary(Registry=pikepdf.String("Adobe"), Ordering=pikepdf.String("Identity"),
                                     Supplement=0),
            FontDescriptor=self.pdf.make_indirect(descriptor), DW=0,
            W=_widths_array(face, gids))
        if subtype == Name.CIDFontType2:
            cid.CIDToGIDMap = Name.Identity
        obj = entry["obj"]
        obj.BaseFont = Name("/" + base)
        obj.Encoding = Name("/Identity-H")
        obj.DescendantFonts = Array([self.pdf.make_indirect(cid)])
        obj.ToUnicode = self.pdf.make_stream(_to_unicode_cmap(entry["map"]))

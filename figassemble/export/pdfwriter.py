"""PDF export with pikepdf (qpdf).

- A placed PDF page is copied in unchanged as a Form XObject: its drawing instructions,
  fonts and images are the original bytes.
- PNGs without transparency go in without being decoded (their compressed data plus a
  PNG predictor); other images are stored losslessly; JPEG bytes pass straight through.
- Shapes and text are drawn natively, with fonts embedded as subsets.
"""
from __future__ import annotations

import os
import zlib

import pikepdf
from pikepdf import Array, Dictionary, Name

from ..assets import SourceResolver, display_box
from ..geometry import DrawPath, Matrix, _fmt
from ..resolve import DrawPicture, DrawText, Resolved
from .pdffont import FontEmbedder

_CAP = {"flat": 0, "round": 1, "square": 2}
_JOIN = {"miter": 0, "round": 1, "bevel": 2}


def _n(v: float, nd: int = 4) -> str:
    return _fmt(v, nd)


def _rgb(color: str) -> str:
    c = (color or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return f"{_n(r)} {_n(g)} {_n(b)}"


def _cm(m: Matrix) -> str:
    return " ".join(_n(v, 6) for v in m.as_tuple()) + " cm"


def _png_chunks(data: bytes):
    pos = 8
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        yield data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        pos += 12 + length


class PdfWriter:
    def __init__(self, sources: SourceResolver, title: str = ""):
        self.pdf = pikepdf.new()
        self.sources = sources
        self.fonts = FontEmbedder(self.pdf)
        self._forms: dict = {}
        self._images: dict = {}
        self._open: dict[str, pikepdf.Pdf] = {}
        self._gstates: dict = {}
        self.warnings: list[str] = []
        self.title = title

    # Pages --------------------------------------------------------------------------

    def add_page(self, page: dict, resolved: list[Resolved]) -> None:
        w, h = float(page["width"]), float(page["height"])
        pg = self.pdf.add_blank_page(page_size=(w, h))
        res: dict[str, dict] = {"/XObject": {}, "/Font": {}, "/ExtGState": {}, "/Shading": {}}
        self._names: dict = {}
        ops = [f"1 0 0 -1 0 {_n(h)} cm"]   # everything below is in y-down page coordinates
        if page.get("background"):
            ops += ["q", f"{_rgb(page['background'])} rg", f"0 0 {_n(w)} {_n(h)} re f", "Q"]
        for r in resolved:
            for prim in r.prims:
                try:
                    if isinstance(prim, DrawPath):
                        ops += self._path(prim, res)
                    elif isinstance(prim, DrawText):
                        ops += self._text(prim, res)
                    elif isinstance(prim, DrawPicture):
                        ops += self._picture(prim, res)
                except Exception as exc:   # one bad item shouldn't lose the whole page
                    self.warnings.append(f"item {r.item_id}: {exc}")
        pg.obj.Contents = self.pdf.make_stream("\n".join(ops).encode("latin-1"))
        pg.obj.Resources = Dictionary({k: Dictionary(v) for k, v in res.items() if v})

    def finish(self, embed_fonts: bool = True) -> None:
        """Build font subsets and (by default) embed fonts the placed PDFs lack."""
        self.warnings += self.fonts.finalize()
        if embed_fonts and self._forms:
            from .pdffix import embed_missing_fonts
            self.warnings += embed_missing_fonts(self.pdf, [form for form, _ in self._forms.values()])
        self.pdf.docinfo[Name.Producer] = pikepdf.String("FigAssemble")
        if self.title:
            self.pdf.docinfo[Name.Title] = pikepdf.String(self.title)

    def close_sources(self) -> None:
        for src in self._open.values():
            src.close()
        self._open.clear()

    def save(self, path: str, embed_fonts: bool = True) -> list[str]:
        self.finish(embed_fonts)
        self.pdf.docinfo[Name.Producer] = pikepdf.String("FigAssemble")
        if self.title:
            self.pdf.docinfo[Name.Title] = pikepdf.String(self.title)
        tmp = path + ".tmp"
        self.pdf.save(tmp, compress_streams=True, recompress_flate=False, deterministic_id=True,
                      object_stream_mode=pikepdf.ObjectStreamMode.generate)
        os.replace(tmp, path)
        for src in self._open.values():
            src.close()
        self._open.clear()
        return self.warnings + self.sources.notes

    # Resources -----------------------------------------------------------------------

    def _name(self, res: dict, category: str, prefix: str, obj) -> str:
        key = (category, obj.objgen if obj.is_indirect else id(obj))
        name = self._names.get(key)
        if name is None:
            name = f"{prefix}{len(res[category]) + 1}"
            res[category]["/" + name] = obj
            self._names[key] = name
        return name

    def _gstate(self, res: dict, stroke_alpha: float, fill_alpha: float) -> str | None:
        if stroke_alpha >= 1.0 and fill_alpha >= 1.0:
            return None
        key = (round(stroke_alpha, 4), round(fill_alpha, 4))
        obj = self._gstates.get(key)
        if obj is None:
            obj = self.pdf.make_indirect(Dictionary(Type=Name.ExtGState, CA=key[0], ca=key[1]))
            self._gstates[key] = obj
        return self._name(res, "/ExtGState", "GS", obj)

    # Primitives ------------------------------------------------------------------------

    def _function(self, stops: list[tuple[float, list[float]]]):
        """PDF function interpolating colour stops linearly (stitched Type 2 pieces)."""
        pts = sorted(stops, key=lambda s: s[0])
        if pts[0][0] > 0:
            pts.insert(0, (0.0, pts[0][1]))
        if pts[-1][0] < 1:
            pts.append((1.0, pts[-1][1]))
        if len(pts) == 1:
            pts.append((1.0, pts[0][1]))
        # Bounds must increase; nudge stops that share a position
        fixed = [pts[0]]
        for p, c in pts[1:]:
            fixed.append((max(p, fixed[-1][0] + 1e-6), c))
        pts = fixed
        funcs = [Dictionary(FunctionType=2, Domain=Array([0, 1]), C0=Array(c0), C1=Array(c1), N=1)
                 for (_, c0), (_, c1) in zip(pts, pts[1:])]
        if len(funcs) == 1:
            return funcs[0]
        span = pts[-1][0] - pts[0][0]
        return Dictionary(FunctionType=3, Domain=Array([0, 1]), Functions=Array(funcs),
                          Bounds=Array([(p - pts[0][0]) / span for p, _ in pts[1:-1]]),
                          Encode=Array([0, 1] * len(funcs)))

    def _shading(self, g, gray_alpha: float | None = None):
        def comps(color, opacity):
            if gray_alpha is not None:
                return [round(opacity * gray_alpha, 6)]
            return [float(v) for v in _rgb(color).split()]
        func = self._function([(pos, comps(c, op)) for pos, c, op in g.stops])
        return self.pdf.make_indirect(Dictionary(
            ShadingType=2, ColorSpace=Name.DeviceGray if gray_alpha is not None else Name.DeviceRGB,
            Coords=Array([g.p0[0], g.p0[1], g.p1[0], g.p1[1]]), Function=func,
            Extend=Array([True, True])))

    def _gradient_fill(self, prim: DrawPath, res: dict) -> list[str]:
        g, f = prim.fill.gradient, prim.fill
        name = self._name(res, "/Shading", "Sh", self._shading(g))
        ops = ["q"]
        if g.has_alpha or f.opacity < 1:
            # Transparency comes from a luminosity soft mask painted with the alpha values
            mask_sh = self._shading(g, gray_alpha=f.opacity)
            form = pikepdf.Stream(self.pdf, ("q " + _cm(g.matrix) + " /A sh Q").encode())
            form.Type, form.Subtype = Name.XObject, Name.Form
            form.BBox = Array([-1e5, -1e5, 1e5, 1e5])
            form.Group = Dictionary(S=Name.Transparency, CS=Name.DeviceGray)
            form.Resources = Dictionary(Shading=Dictionary(A=mask_sh))
            gs = self.pdf.make_indirect(Dictionary(
                Type=Name.ExtGState, SMask=Dictionary(Type=Name.Mask, S=Name.Luminosity,
                                                      G=self.pdf.make_indirect(form))))
            ops.append(f"/{self._name(res, '/ExtGState', 'GS', gs)} gs")
        ops += [prim.path.to_pdf(), "W* n" if f.even_odd else "W n", _cm(g.matrix), f"/{name} sh", "Q"]
        return ops

    def _path(self, prim: DrawPath, res: dict) -> list[str]:
        s, f = prim.stroke, prim.fill
        if s is None and f is None:
            return []
        if f is not None and f.gradient is not None:
            out = self._gradient_fill(prim, res)
            if s is not None:
                out += self._path(DrawPath(prim.path, stroke=s), res)
            return out
        ops = ["q"]
        gs = self._gstate(res, s.opacity if s else 1.0, f.opacity if f else 1.0)
        if gs:
            ops.append(f"/{gs} gs")
        if f is not None:
            ops.append(f"{_rgb(f.color)} rg")
        if s is not None:
            ops += [f"{_n(s.width)} w", f"{_CAP.get(s.cap, 0)} J", f"{_JOIN.get(s.join, 1)} j",
                    f"{_n(s.miter_limit)} M", f"{_rgb(s.color)} RG"]
            if s.dash:
                ops.append("[" + " ".join(_n(v) for v in s.dash) + "] 0 d")
        ops.append(prim.path.to_pdf())
        if f is not None and s is not None:
            ops.append("B*" if f.even_odd else "B")
        elif f is not None:
            ops.append("f*" if f.even_odd else "f")
        else:
            ops.append("S")
        ops.append("Q")
        return ops

    def _text(self, prim: DrawText, res: dict) -> list[str]:
        ops = []
        for run in prim.runs:
            if not run.gids:
                continue
            font = self.fonts.use(run.face, run.gids, run.text)
            name = self._name(res, "/Font", "F", font)
            tm = prim.matrix @ Matrix.translate(run.x, run.y) @ Matrix.scale(1.0, -1.0) \
                @ Matrix(1.0, 0.0, run.skew, 1.0, 0.0, 0.0)
            ops.append("q")
            gs = self._gstate(res, run.opacity, run.opacity)
            if gs:
                ops.append(f"/{gs} gs")
            hexstr = "".join(f"{g:04X}" for g in run.gids)
            ops += [f"{_rgb(run.color)} rg", "BT", f"/{name} {_n(run.size)} Tf",
                    " ".join(_n(v, 6) for v in tm.as_tuple()) + " Tm", f"<{hexstr}> Tj", "ET"]
            if run.underline:
                pos, thick = run.face.underline_position * run.size, run.face.underline_thickness * run.size
                um = prim.matrix @ Matrix.translate(run.x, run.y - pos)
                ops += [_cm(um), f"{_rgb(run.color)} rg", f"0 {_n(-thick / 2)} {_n(run.width)} {_n(thick)} re f"]
            ops.append("Q")
        return ops

    def _picture(self, prim: DrawPicture, res: dict) -> list[str]:
        kind, path = self.sources.for_pdf(prim.asset_id, prim.source)
        x0, y0, x1, y1 = prim.crop
        ops = ["q"]
        gs = self._gstate(res, prim.opacity, prim.opacity)
        if gs:
            ops.append(f"/{gs} gs")
        ops += [_cm(prim.matrix), f"{_n(x0)} {_n(y0)} {_n(x1 - x0)} {_n(y1 - y0)} re W n"]
        if kind == "pdf":
            form, disp = self._form(path, prim.page_index)
            name = self._name(res, "/XObject", "Fm", form)
            ops += [_cm(disp), f"/{name} Do"]
        else:
            img = self._image(path, kind)
            name = self._name(res, "/XObject", "Im", img)
            sw, sh = prim.src_size
            ops += [f"{_n(sw, 6)} 0 0 {_n(-sh, 6)} 0 {_n(sh, 6)} cm", f"/{name} Do"]
        ops.append("Q")
        return ops

    # Placed files -----------------------------------------------------------------------

    def _form(self, path: str, page_index: int):
        """Form XObject of a source page, and the map from its user space to display space."""
        key = (path, page_index)
        if key in self._forms:
            return self._forms[key]
        src = self._open.get(path)
        if src is None:
            src = pikepdf.open(path)
            self._open[path] = src
        page = src.pages[page_index]
        box = [float(v) for v in display_box(page)]
        rot = int(page.obj.get("/Rotate", 0)) % 360
        uu = float(page.obj.get("/UserUnit", 1.0))
        form = self.pdf.copy_foreign(page.as_form_xobject(handle_transformations=False))
        form.BBox = Array(box)
        bw, bh = (box[2] - box[0]) * uu, (box[3] - box[1]) * uu
        flip = Matrix(uu, 0.0, 0.0, -uu, -box[0] * uu, box[3] * uu)   # PDF y-up -> top-left, y-down
        turn = {0: Matrix(), 90: Matrix(0.0, 1.0, -1.0, 0.0, bh, 0.0),
                180: Matrix(-1.0, 0.0, 0.0, -1.0, bw, bh), 270: Matrix(0.0, -1.0, 1.0, 0.0, 0.0, bw)}[rot]
        self._forms[key] = (form, turn @ flip)
        return self._forms[key]

    def _image(self, path: str, kind: str):
        if path in self._images:
            return self._images[path]
        if kind == "jpeg":
            img = self._jpeg(path)
        else:
            img = self._png_passthrough(path) if kind == "png" else None
            if img is None:
                img = self._decoded_image(path)
        self._images[path] = img
        return img

    def _icc(self, profile: bytes, n: int, alternate: str):
        stream = self.pdf.make_stream(profile)
        stream.N = n
        stream.Alternate = Name(alternate)
        return Array([Name.ICCBased, stream])

    def _jpeg(self, path: str):
        from PIL import Image
        with Image.open(path) as im:
            mode, (w, h) = im.mode, im.size
            icc = im.info.get("icc_profile")
            adobe = "adobe" in im.info
        with open(path, "rb") as fh:
            data = fh.read()
        n, alt = {"L": (1, "/DeviceGray"), "CMYK": (4, "/DeviceCMYK")}.get(mode, (3, "/DeviceRGB"))
        stream = self.pdf.make_stream(data)
        stream.Type, stream.Subtype = Name.XObject, Name.Image
        stream.Width, stream.Height, stream.BitsPerComponent = w, h, 8
        stream.ColorSpace = self._icc(icc, n, alt) if icc else Name(alt)
        stream.Filter = Name.DCTDecode
        if mode == "CMYK" and adobe:
            stream.Decode = Array([1, 0, 1, 0, 1, 0, 1, 0])   # Adobe CMYK JPEGs are stored inverted
        return self.pdf.make_indirect(stream)

    def _png_passthrough(self, path: str):
        """Embed a PNG's compressed data as-is when it needs no decoding (no alpha, not interlaced)."""
        with open(path, "rb") as fh:
            data = fh.read()
        ihdr = None
        idat = []
        palette = trns = icc = None
        for ctype, body in _png_chunks(data):
            if ctype == b"IHDR":
                ihdr = body
            elif ctype == b"IDAT":
                idat.append(body)
            elif ctype == b"PLTE":
                palette = body
            elif ctype == b"tRNS":
                trns = body
            elif ctype == b"iCCP":
                name_end = body.index(b"\0")
                icc = zlib.decompress(body[name_end + 2:])
        if ihdr is None:
            return None
        w, h = int.from_bytes(ihdr[0:4], "big"), int.from_bytes(ihdr[4:8], "big")
        depth, ctype, interlace = ihdr[8], ihdr[9], ihdr[12]
        if interlace or trns is not None or ctype in (4, 6):
            return None
        colors = {0: 1, 2: 3, 3: 1}[ctype]
        if ctype == 3:
            cs = Array([Name.Indexed, Name.DeviceRGB, len(palette) // 3 - 1, pikepdf.String(palette)])
        elif icc:
            cs = self._icc(icc, colors, "/DeviceGray" if ctype == 0 else "/DeviceRGB")
        else:
            cs = Name.DeviceGray if ctype == 0 else Name.DeviceRGB
        stream = pikepdf.Stream(self.pdf, b"".join(idat))
        stream.Type, stream.Subtype = Name.XObject, Name.Image
        stream.Width, stream.Height, stream.BitsPerComponent = w, h, depth
        stream.ColorSpace = cs
        stream.Filter = Name.FlateDecode
        stream.DecodeParms = Dictionary(Predictor=15, Colors=colors, BitsPerComponent=depth, Columns=w)
        return self.pdf.make_indirect(stream)

    def _decoded_image(self, path: str):
        """Decode with Pillow and store losslessly (Flate), alpha as a soft mask."""
        import numpy as np
        from PIL import Image
        with Image.open(path) as im:
            im.load()
            icc = im.info.get("icc_profile")
            mode = im.mode
            if mode == "P":
                im = im.convert("RGBA" if "transparency" in im.info else "RGB")
            elif mode in ("LA", "PA"):
                im = im.convert("LA")
            elif mode not in ("1", "L", "RGB", "RGBA", "CMYK", "I;16", "I;16B", "I;16L", "I"):
                self.warnings.append(f"{os.path.basename(path)}: converted {mode} image to RGB")
                im = im.convert("RGB")
            mode = im.mode
            alpha = None
            if mode in ("RGBA", "LA"):
                alpha = im.getchannel("A")
                im = im.convert("RGB" if mode == "RGBA" else "L")
                mode = im.mode
            w, h = im.size
            if mode == "1":
                raw, bpc, n, alt = im.tobytes(), 1, 1, "/DeviceGray"
            elif mode in ("I;16", "I;16L", "I;16B", "I"):
                arr = np.asarray(im)
                if arr.dtype != np.uint16:
                    arr = np.clip(arr, 0, 65535).astype(np.uint16)
                raw, bpc, n, alt = arr.astype(">u2").tobytes(), 16, 1, "/DeviceGray"
            else:
                n, alt = {"L": (1, "/DeviceGray"), "RGB": (3, "/DeviceRGB"), "CMYK": (4, "/DeviceCMYK")}[mode]
                raw, bpc = im.tobytes(), 8
        stream = pikepdf.Stream(self.pdf, zlib.compress(raw, 6))
        stream.Type, stream.Subtype = Name.XObject, Name.Image
        stream.Width, stream.Height, stream.BitsPerComponent = w, h, bpc
        stream.ColorSpace = self._icc(icc, n, alt) if icc and n in (1, 3, 4) else Name(alt)
        stream.Filter = Name.FlateDecode
        if alpha is not None:
            mask = pikepdf.Stream(self.pdf, zlib.compress(alpha.tobytes(), 6))
            mask.Type, mask.Subtype = Name.XObject, Name.Image
            mask.Width, mask.Height, mask.BitsPerComponent = w, h, 8
            mask.ColorSpace = Name.DeviceGray
            mask.Filter = Name.FlateDecode
            stream.SMask = self.pdf.make_indirect(mask)
        return self.pdf.make_indirect(stream)


def write_pdf(doc: dict, pages: list[dict], resolved_pages: list[list[Resolved]], path: str,
              sources: SourceResolver) -> list[str]:
    w = PdfWriter(sources, title=doc.get("meta", {}).get("title", ""))
    for page, resolved in zip(pages, resolved_pages):
        w.add_page(page, resolved)
    return w.save(path)

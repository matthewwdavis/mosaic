"""Export to PowerPoint, editable. Each page becomes a slide its size, and each object PowerPoint's
own wherever PowerPoint draws it the same way: shapes (its ready-made shapes with their
adjustments, and freeforms), lines and arrows, text and text boxes, pictures (a placed PDF or SVG
goes in as an SVG with a PNG copy, as PowerPoint itself stores them, cropped, turned and faded
as placed) and groups. Corner rounding goes in built into a freeform outline, and an area fill
as a freeform of its area now.

Anything PowerPoint can't draw exactly goes in as an exact picture of itself, an SVG with a PNG
copy drawn by mosaic's own engine: outlines, even dashes, the pathway and rounded
arrowheads, scale bars, brackets, symbols' copies, clipping masks and pictures cropped to a shape
or with a border. Each picture keeps its object's name.

One slide size holds every slide (PowerPoint's rule): the largest page's, at least an inch.
"""
from __future__ import annotations

import io
import math
from xml.sax.saxutils import escape, quoteattr

from .. import presets
from ..assets import PDFIUM_LOCK, SourceResolver
from ..geometry import Matrix, Path, smooth_path
from ..resolve import DrawGroup, DrawPath, Resolved, Resolver, flat_prims, shape_to_custom

EMU = 12700   # per point
NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
SVG_EXT = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
HEADS = {"triangle", "stealth", "diamond", "oval", "arrow"}
CAPS = {"round": "rnd", "square": "sq", "flat": "flat"}
SLIDE_MIN, SLIDE_MAX = 914400, 51206400   # EMU: PowerPoint's smallest and largest slide sides
FALLBACK_DPI = 300.0


def e(v: float) -> int:
    return int(round(float(v) * EMU))


def _colour(c: str | None, opacity: float = 1.0) -> str:
    hexes = (c or "#000000").lstrip("#").upper()
    if len(hexes) == 3:
        hexes = "".join(ch * 2 for ch in hexes)
    alpha = f'<a:alpha val="{int(round(opacity * 100000))}"/>' if opacity < 1 else ""
    return f'<a:srgbClr val="{hexes[:6]}">{alpha}</a:srgbClr>'


def _xfrm(frame, rot=0.0, flip_h=False, flip_v=False, tag="a:xfrm") -> str:
    x, y, w, h = frame
    attrs = (f' rot="{int(round((rot or 0) * 60000)) % 21600000}"' if rot else "") + (' flipH="1"' if flip_h else "") \
        + (' flipV="1"' if flip_v else "")
    return f'<{tag}{attrs}><a:off x="{e(x)}" y="{e(y)}"/><a:ext cx="{max(e(w), 1)}" cy="{max(e(h), 1)}"/></{tag}>'


def _fill(f: dict | None) -> str:
    if not f:
        return "<a:noFill/>"
    g = f.get("gradient")
    if not g:
        return f"<a:solidFill>{_colour(f.get('color'), float(f.get('opacity', 1.0)))}</a:solidFill>"
    stops = "".join(f'<a:gs pos="{int(round(float(s["pos"]) * 100000))}">{_colour(s["color"], float(s.get("opacity", 1.0)))}</a:gs>'
                    for s in sorted(g.get("stops", []), key=lambda s: float(s["pos"])))
    if g.get("type") == "radial":
        cx, cy = (float(v) for v in g.get("center", (0.5, 0.5)))
        shade = (f'<a:path path="circle"><a:fillToRect l="{int(cx * 100000)}" t="{int(cy * 100000)}" '
                 f'r="{int((1 - cx) * 100000)}" b="{int((1 - cy) * 100000)}"/></a:path>')
    else:
        shade = f'<a:lin ang="{int(round(float(g.get("angle", 0.0)) * 60000)) % 21600000}" scaled="{1 if g.get("scaled", True) else 0}"/>'
    return f'<a:gradFill rotWithShape="1"><a:gsLst>{stops}</a:gsLst>{shade}</a:gradFill>'


def _line(s: dict | None, start: dict | None = None, end: dict | None = None) -> str:
    if not s:
        return "<a:ln><a:noFill/></a:ln>"
    dash = s.get("dash", "solid")
    if isinstance(dash, list):
        pairs = list(zip(dash[0::2], dash[1::2]))
        dash_xml = "<a:custDash>" + "".join(f'<a:ds d="{int(d * 100000)}" sp="{int(sp * 100000)}"/>' for d, sp in pairs) + "</a:custDash>"
    else:
        dash_xml = f'<a:prstDash val="{dash or "solid"}"/>'
    join = {"round": "<a:round/>", "bevel": "<a:bevel/>"}.get(s.get("join"), '<a:miter lim="800000"/>')
    ends = ""
    for tag, a in (("a:headEnd", start), ("a:tailEnd", end)):
        if a:
            ends += f'<{tag} type="{a.get("type", "triangle")}" w="{a.get("w", "med")}" len="{a.get("len", "med")}"/>'
    return (f'<a:ln w="{e(s.get("width", 1.0))}" cap="{CAPS.get(s.get("cap"), "flat")}">'
            f'<a:solidFill>{_colour(s.get("color"), float(s.get("opacity", 1.0)))}</a:solidFill>{dash_xml}{join}{ends}</a:ln>')


def _path_xml(path: Path, w: float, h: float, ox: float, oy: float, open_fill: bool = True, stroke: bool = True) -> str:
    """One a:path of a Path's segments, relative to (ox, oy), in a w x h box (points)."""
    pt = lambda x, y: f'<a:pt x="{e(x - ox)}" y="{e(y - oy)}"/>'
    body = ""
    for seg in path.segs:
        op = seg[0]
        if op == "M":
            body += f"<a:moveTo>{pt(*seg[1:3])}</a:moveTo>"
        elif op == "L":
            body += f"<a:lnTo>{pt(*seg[1:3])}</a:lnTo>"
        elif op == "C":
            body += f"<a:cubicBezTo>{pt(*seg[1:3])}{pt(*seg[3:5])}{pt(*seg[5:7])}</a:cubicBezTo>"
        elif op == "Z":
            body += "<a:close/>"
    attrs = ("" if open_fill else ' fill="none"') + ("" if stroke else ' stroke="0"')
    return f'<a:path w="{max(e(w), 1)}" h="{max(e(h), 1)}"{attrs}>{body}</a:path>'


def _cust_geom(paths: list[str], w: float, h: float) -> str:
    return (f'<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="{max(e(w), 1)}" b="{max(e(h), 1)}"/>'
            f'<a:pathLst>{"".join(paths)}</a:pathLst></a:custGeom>')


def _text_body(item: dict) -> str:
    body = item.get("text") or {}
    paras = body.get("paragraphs") or []
    if not any(r.get("t") for p in paras for r in p.get("runs", [])):
        return ""
    l, t, r, b = body.get("insets") or [7.2, 3.6, 7.2, 3.6]
    fit = "<a:spAutoFit/>" if body.get("autofit") == "shape" else "<a:noAutofit/>"
    anchor = {"ctr": "ctr", "b": "b"}.get(body.get("anchor"), "t")
    out = [f'<p:txBody><a:bodyPr wrap="{"square" if body.get("wrap", True) else "none"}" lIns="{e(l)}" tIns="{e(t)}" '
           f'rIns="{e(r)}" bIns="{e(b)}" anchor="{anchor}" rtlCol="0">{fit}</a:bodyPr><a:lstStyle/>']
    for p in paras:
        ppr = f'<a:pPr algn="{p.get("align", "l") if p.get("align") in ("l", "ctr", "r", "just") else "l"}">'
        if p.get("line_spacing"):
            ppr += f'<a:lnSpc><a:spcPct val="{int(round(float(p["line_spacing"]) * 100000))}"/></a:lnSpc>'
        if p.get("space_before"):
            ppr += f'<a:spcBef><a:spcPts val="{int(round(float(p["space_before"]) * 100))}"/></a:spcBef>'
        if p.get("space_after"):
            ppr += f'<a:spcAft><a:spcPts val="{int(round(float(p["space_after"]) * 100))}"/></a:spcAft>'
        out.append(f"<a:p>{ppr}</a:pPr>")
        last = {}
        for run in p.get("runs", []):
            last = run
            rpr = (f'<a:rPr lang="en-US" sz="{int(round(float(run.get("size", 6)) * 100))}"'
                   + (' b="1"' if run.get("bold") else ' b="0"') + (' i="1"' if run.get("italic") else ' i="0"')
                   + (' u="sng"' if run.get("underline") else "")
                   + (f' baseline="{int(round(float(run["baseline"]) * 100000))}"' if run.get("baseline") else "")
                   + f' dirty="0"><a:solidFill>{_colour(run.get("color"))}</a:solidFill>'
                   + f'<a:latin typeface={quoteattr(run.get("font") or "Helvetica")}/>'
                   + f'<a:cs typeface={quoteattr(run.get("font") or "Helvetica")}/></a:rPr>')
            for k, piece in enumerate(str(run.get("t", "")).replace("\v", "\n").split("\n")):
                if k:
                    out.append(f"<a:br>{rpr}</a:br>")
                if piece:
                    out.append(f"<a:r>{rpr}<a:t>{escape(piece)}</a:t></a:r>")
        out.append(f'<a:endParaRPr lang="en-US" sz="{int(round(float(last.get("size", 6)) * 100))}" dirty="0"/></a:p>')
    out.append("</p:txBody>")
    return "".join(out)


class PptxWriter:
    def __init__(self, doc: dict, cache, doc_dir: str | None = None, fonts=None):
        from pptx import Presentation
        self.doc = doc
        self.src = SourceResolver(doc, cache, doc_dir)
        self.resolver = Resolver(doc, fonts)
        self.prs = Presentation()
        self.pictured: dict[str, int] = {}   # why objects went in as pictures, and how many
        self.warnings: list[str] = []
        self._svgs: dict = {}

    def size(self, pages: list[dict]) -> None:
        w = max(float(p["width"]) for p in pages)
        h = max(float(p["height"]) for p in pages)
        cw, ch = (min(max(e(v), SLIDE_MIN), SLIDE_MAX) for v in (w, h))
        if (cw, ch) != (e(w), e(h)):
            self.warnings.append("PowerPoint: the slide is at least an inch and at most 56 inches each way, so the page sits on a "
                                 "slide of that size")
        if len({(p["width"], p["height"]) for p in pages}) > 1:
            self.warnings.append("PowerPoint has one slide size: every page sits at the top left of a slide the size of the largest")
        self.prs.slide_width, self.prs.slide_height = cw, ch

    def add_page(self, page: dict) -> None:
        from pptx.oxml import parse_xml
        self.slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self._id = 1
        if page.get("background"):
            from pptx.dml.color import RGBColor
            fill = self.slide.background.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor.from_string(page["background"].lstrip("#")[:6].upper())
        self.resolver.use_page(page.get("items", []))
        tree = self.slide.shapes._spTree
        for it in page.get("items", []):
            if not it.get("hidden"):
                for xml in self.item(it):
                    tree.append(parse_xml(xml))

    def save(self, path: str) -> list[str]:
        self.prs.save(path)
        notes = [f"PowerPoint: {n} object{'s' if n != 1 else ''} with {why} went in as exact pictures"
                 for why, n in self.pictured.items()]
        return self.warnings + notes + self.src.notes

    # Objects -----------------------------------------------------------------------------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def why_picture(self, it: dict) -> str | None:
        """What about an object PowerPoint can't draw exactly, or None if it can."""
        kind = it.get("type")
        if kind == "group":
            return "a clipping mask" if it.get("clip") else None
        if kind == "picture":
            return "a crop to a shape" if it.get("mask") else "a border" if it.get("border") else None
        if kind not in ("line", "shape"):
            return {"scalebar": "a scale bar", "bracket": "a significance bracket", "symbol": "a symbol"}.get(kind, f"type {kind}")
        if float((it.get("outline") or {}).get("width", 0) or 0) > 0:
            return "an outline"
        s = it.get("stroke") or {}
        if s and s.get("dash", "solid") not in ("solid", None) and s.get("even_dashes", True) is not False:
            return "even dashes"
        for k in ("arrow_start", "arrow_end"):
            a = it.get(k)
            if a and (a.get("type") not in HEADS or float(a.get("rounding") or 0) > 0):
                return "a pathway or rounded arrowhead"
        return None

    def item(self, it: dict) -> list[str]:
        why = self.why_picture(it)
        if why is None:
            kind = it.get("type")
            if kind == "group":
                return [self.group(it)]
            if kind == "picture":
                return [self.picture(it)]
            if kind == "line":
                return [self.line(it)]
            return [self.shape(it)]
        self.pictured[why] = self.pictured.get(why, 0) + 1
        pic = self.exact_picture(it)
        return [pic] if pic else []

    def _name(self, it: dict, fallback: str) -> str:
        return quoteattr(it.get("name") or fallback)

    def group(self, it: dict) -> str:
        kids = [x for c in it.get("items", []) if not c.get("hidden") for x in self.item(c)]
        r = self.resolver.resolve(it)
        x0, y0, x1, y1 = r.bbox or (0, 0, 1, 1)
        box = (f'<a:off x="{e(x0)}" y="{e(y0)}"/><a:ext cx="{max(e(x1 - x0), 1)}" cy="{max(e(y1 - y0), 1)}"/>')
        return (f'<p:grpSp {NS}><p:nvGrpSpPr><p:cNvPr id="{self._next_id()}" name={self._name(it, "Group")}/><p:cNvGrpSpPr/><p:nvPr/>'
                f'</p:nvGrpSpPr><p:grpSpPr><a:xfrm>{box}{box.replace("a:off", "a:chOff").replace("a:ext", "a:chExt")}</a:xfrm>'
                f'</p:grpSpPr>{"".join(k.replace(" " + NS, "") for k in kids)}</p:grpSp>')

    def line(self, it: dict) -> str:
        pts = [p for i, p in enumerate(it["points"]) if i == 0 or tuple(p) != tuple(it["points"][i - 1])]
        ln = _line(it.get("stroke"), it.get("arrow_start"), it.get("arrow_end"))
        name = self._name(it, "Line")
        if len(pts) == 2 and it.get("curve") != "smooth":
            (ax, ay), (bx, by) = pts
            frame = [min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay)]
            return (f'<p:cxnSp {NS}><p:nvCxnSpPr><p:cNvPr id="{self._next_id()}" name={name}/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>'
                    f'<p:spPr>{_xfrm(frame, 0, bx < ax, by < ay)}<a:prstGeom prst="line"><a:avLst/></a:prstGeom>{ln}</p:spPr></p:cxnSp>')
        if it.get("curve") == "smooth" and len(pts) >= 3:
            path = smooth_path(pts)
        else:
            path = Path().move_to(*pts[0])
            for p in pts[1:]:
                path.line_to(*p)
        x0, y0, x1, y1 = path.bbox()
        w, h = max(x1 - x0, 0.01), max(y1 - y0, 0.01)
        geom = _cust_geom([_path_xml(path, w, h, x0, y0, open_fill=False)], w, h)
        return (f'<p:sp {NS}><p:nvSpPr><p:cNvPr id="{self._next_id()}" name={name}/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
                f'<p:spPr>{_xfrm([x0, y0, w, h])}{geom}<a:noFill/>{ln}</p:spPr></p:sp>')

    def shape(self, it: dict) -> str:
        if it.get("rounding") and it.get("geom") not in ("custom", "region"):
            it = shape_to_custom(it)   # PowerPoint can't round any shape's corners: the outline, rounded
        geom = it.get("geom", "rect")
        x, y, w, h = it["frame"]
        if geom == "region":
            # An area fill: a freeform of its area as it is now
            r = self.resolver.resolve(it)
            body = [p for p in flat_prims(r.prims) if isinstance(p, DrawPath) and p.fill is not None and p.meta.get("role") != "outline"]
            g = _cust_geom([_path_xml(p.path, w, h, x, y) for p in body[:1]], w, h)
            frame, rot, fh, fv = [x, y, w, h], 0, False, False
        elif geom == "custom":
            paths = []
            for sp in (it.get("path") or {}).get("subpaths", []):
                pw, ph = float(sp.get("w") or w) or 1.0, float(sp.get("h") or h) or 1.0
                path = Path()
                for cmd in sp.get("cmds", []):
                    op, v = cmd[0], cmd[1:]
                    if op == "M":
                        path.move_to(*v[:2])
                    elif op == "L":
                        path.line_to(*v[:2])
                    elif op == "C":
                        path.curve_to(*v[:6])
                    elif op == "Q":
                        path.quad_to(*v[:4])
                    elif op == "A":
                        path.arc_to(*v[:4])
                    elif op == "Z":
                        path.close()
                path = path.transformed(Matrix.scale(w / pw, h / ph))
                paths.append(_path_xml(path, w, h, 0, 0, open_fill=sp.get("fill", True), stroke=sp.get("stroke", True)))
            g = _cust_geom(paths, w, h)
            frame, rot, fh, fv = it["frame"], it.get("rot", 0), it.get("flip_h"), it.get("flip_v")
        else:
            raw = presets._raw(geom, it.get("adj")) if presets.is_preset(geom) else {}
            av = "".join(f'<a:gd name="{n}" fmla="val {int(round(v))}"/>' for n, v in raw.items())
            g = f'<a:prstGeom prst="{geom if presets.is_preset(geom) else "rect"}"><a:avLst>{av}</a:avLst></a:prstGeom>'
            frame, rot, fh, fv = it["frame"], it.get("rot", 0), it.get("flip_h"), it.get("flip_v")
        ln = _line(it.get("stroke"), it.get("arrow_start"), it.get("arrow_end"))
        box = ' txBox="1"' if it.get("textbox") else ""
        return (f'<p:sp {NS}><p:nvSpPr><p:cNvPr id="{self._next_id()}" name={self._name(it, "Shape")}/><p:cNvSpPr{box}/><p:nvPr/>'
                f'</p:nvSpPr><p:spPr>{_xfrm(frame, rot, fh, fv)}{g}{_fill(it.get("fill"))}{ln}</p:spPr>{_text_body(it)}</p:sp>')

    # Pictures ----------------------------------------------------------------------------

    def _image_rid(self, data: bytes) -> str:
        _, rid = self.slide.part.get_or_add_image_part(io.BytesIO(data))
        return rid

    def _svg_rid(self, data: bytes) -> str:
        from pptx.opc.constants import RELATIONSHIP_TYPE as RT
        from pptx.opc.package import Part
        key = hash(data)
        part = self._svgs.get(key)
        if part is None:
            package = self.prs.part.package
            part = self._svgs[key] = Part(package.next_partname("/ppt/media/image%d.svg"), "image/svg+xml", package, data)
        return self.slide.part.relate_to(part, RT.IMAGE)

    def _png_of_pdf(self, path: str, page_index: int, size_pt) -> bytes:
        import pypdfium2 as pdfium
        scale = min(FALLBACK_DPI / 72.0, 6000.0 / max(max(size_pt), 1e-9))
        with PDFIUM_LOCK:
            doc = pdfium.PdfDocument(path)
            try:
                im = doc[page_index].render(scale=scale, fill_color=(0, 0, 0, 0), may_draw_forms=False).to_pil().convert("RGBA")
            finally:
                doc.close()
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return buf.getvalue()

    def _blip_pic(self, it: dict, name: str, frame, rot, fh, fv, png: bytes, svg: bytes | None, crop=(0, 0, 0, 0),
                  opacity: float = 1.0) -> str:
        rid = self._image_rid(png)
        alpha = f'<a:alphaModFix amt="{int(round(opacity * 100000))}"/>' if opacity < 1 else ""
        ext = (f'<a:extLst><a:ext uri="{SVG_EXT}"><asvg:svgBlip xmlns:asvg="{SVG_NS}" r:embed="{self._svg_rid(svg)}"/>'
               f'</a:ext></a:extLst>') if svg else ""
        l, t, r, b = (int(round(v * 100000)) for v in crop)
        src = f'<a:srcRect l="{l}" t="{t}" r="{r}" b="{b}"/>' if any((l, t, r, b)) else ""
        descr = f" descr={quoteattr(it['alt'])}" if it.get("alt") else ""
        return (f'<p:pic {NS}><p:nvPicPr><p:cNvPr id="{self._next_id()}" name={name}{descr}/><p:cNvPicPr><a:picLocks noChangeAspect="1"/>'
                f'</p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{rid}">{alpha}{ext}</a:blip>{src}'
                f'<a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>{_xfrm(frame, rot, fh, fv)}'
                f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')

    def picture(self, it: dict) -> str:
        asset = self.doc["assets"][it["asset"]]
        variants, page_index = asset["variants"], int(it.get("page_index", 0))
        sizes = asset.get("page_sizes")
        size = sizes[page_index] if sizes else asset["size_pt"]
        name = self._name(it, asset.get("name", "Picture"))
        source = it.get("source", "auto")
        if source != "png" and any(k in variants for k in ("pdf", "svg")):
            kind, svg_path = self.src.for_svg(it["asset"], source)
            svg = open(svg_path, "rb").read() if kind == "svg" else None
            pkind, pdf_path = self.src.for_pdf(it["asset"], source)
            png = self._png_of_pdf(pdf_path, page_index if "pdf" in variants else 0, size) if pkind == "pdf" else open(pdf_path, "rb").read()
        else:
            kind = next(k for k in ("png", "jpeg", "tiff") if k in variants)
            data = open(self.src.file(it["asset"], kind), "rb").read()
            if kind == "tiff":
                from PIL import Image
                buf = io.BytesIO()
                with Image.open(io.BytesIO(data)) as im:
                    im.save(buf, "PNG")
                data = buf.getvalue()
            png, svg = data, None
        return self._blip_pic(it, name, it["frame"], it.get("rot", 0), it.get("flip_h"), it.get("flip_v"), png, svg,
                              tuple(it.get("crop") or (0, 0, 0, 0)), float(it.get("opacity", 1.0)))

    def exact_picture(self, it: dict) -> str | None:
        """An object as a picture of itself: an SVG and a PNG drawn by mosaic's engine."""
        from . import raster
        from .pdfwriter import PdfWriter
        from .svgwriter import SvgWriter
        r = self.resolver.resolve(it)
        if not r.prims or not r.bbox:
            return None
        x0, y0, x1, y1 = r.bbox
        w, h = max(x1 - x0, 0.1), max(y1 - y0, 0.1)
        page = {"id": "pptx", "name": "", "width": w, "height": h, "background": None, "items": []}
        shifted = [Resolved(r.item_id, prims=[DrawGroup(r.prims, 1.0, matrix=Matrix(1.0, 0.0, 0.0, 1.0, -x0, -y0))], bbox=(0, 0, w, h))]
        svg = SvgWriter(self.src).page(page, shifted)
        pdf = PdfWriter(self.src)
        pdf.add_page(page, shifted)
        pdf.finish(True)
        buf = io.BytesIO()
        pdf.pdf.save(buf)
        pdf.close_sources()
        dpi = min(FALLBACK_DPI, 6000.0 * 72.0 / max(w, h))
        im = raster.render_pdf_bytes(buf.getvalue(), dpi, transparent=True)[0]
        out = io.BytesIO()
        im.save(out, "PNG", optimize=True)
        kind = it.get("type", "object")
        return self._blip_pic(it, self._name(it, kind[:1].upper() + kind[1:]), [x0, y0, w, h], 0, False, False, out.getvalue(), svg)


def write_pptx(doc: dict, pages: list[dict], path: str, cache, doc_dir: str | None = None, fonts=None) -> list[str]:
    """Write the pages as an editable PowerPoint file; returns notes on what went in as pictures."""
    w = PptxWriter(doc, cache, doc_dir, fonts)
    w.size(pages)
    for page in pages:
        w.add_page(page)
    return w.save(path)

"""Open PowerPoint slides as mosaic pages.

Each slide becomes a page of the same size. Pictures are pulled out of the deck and, where
possible, relinked to the original figure files on disk (so exports use R's own PDF/SVG).
Shapes, lines, freeforms and text boxes keep PowerPoint's geometry, line styles and text
layout parameters; groups are flattened into page coordinates the way PowerPoint draws them.

A deck can also be the bytes PowerPoint puts on the clipboard for copied slides: a small deck
whose parts sit under clipboard/ rather than ppt/ (found through the package's relationships).
"""
from __future__ import annotations

import collections
import io
import math
import os
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

from .. import model, presets
from ..assets import AssetCache, get_cache, new_asset, new_asset_from_bytes, new_id
from ..geometry import Matrix, frame_matrix
from .drawingml import (NS, P, R, ColorContext, Theme, emu, first_color, guide_env, num, parse_fill,
                        parse_line, style_fill, style_font_color, style_line, tag)
from .relink import CandidateIndex, default_search_dirs

REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
SVG_BLIP = "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip"

_LINE_PRESETS = {"line", "straightConnector1"}


class Package:
    """An Office package: a file path, or its bytes (path None)."""

    def __init__(self, source: str | bytes):
        self.path = source if isinstance(source, str) else None
        self.z = zipfile.ZipFile(source if isinstance(source, str) else io.BytesIO(source))
        self.names = set(self.z.namelist())
        self._xml: dict[str, ET.Element] = {}

    def main_part(self, kind: str = "officeDocument", default: str | None = None) -> str | None:
        """The part the package's own relationships point to (the presentation, or a copied
        drawing)."""
        return self.rel_of_type("", kind) or default

    def xml(self, part: str) -> ET.Element:
        if part not in self._xml:
            self._xml[part] = ET.fromstring(self.z.read(part))
        return self._xml[part]

    def rels(self, part: str) -> dict[str, tuple[str, str]]:
        d, f = posixpath.split(part)
        rp = posixpath.join(d, "_rels", f + ".rels")
        out = {}
        if rp in self.names:
            for rel in ET.fromstring(self.z.read(rp)):
                target = rel.get("Target", "")
                if rel.get("TargetMode") == "External":
                    out[rel.get("Id")] = (target, rel.get("Type", ""))
                elif target.startswith("/"):
                    out[rel.get("Id")] = (target[1:], rel.get("Type", ""))
                else:
                    out[rel.get("Id")] = (posixpath.normpath(posixpath.join(d, target)), rel.get("Type", ""))
        return out

    def rel_of_type(self, part: str, kind: str) -> str | None:
        for target, rtype in self.rels(part).values():
            if rtype.endswith("/" + kind):
                return target
        return None


def emf_pdf(data: bytes) -> bytes | None:
    """Pull the original PDF out of a PowerPoint for Mac EMF wrapper."""
    start, end = data.find(b"%PDF"), data.rfind(b"%%EOF")
    return data[start:end + 5] if start >= 0 and end > start else None


class _Level:
    """One enclosing group: its child space -> parent space mapping (PowerPoint semantics)."""

    def __init__(self, off, ext, choff, chext, rot, flip_h, flip_v):
        self.sx = ext[0] / chext[0] if chext[0] else 1.0
        self.sy = ext[1] / chext[1] if chext[1] else 1.0
        self.tx = off[0] - choff[0] * self.sx
        self.ty = off[1] - choff[1] * self.sy
        self.frame = [off[0], off[1], ext[0], ext[1]]
        self.turn = None
        if rot or flip_h or flip_v:
            self.turn = frame_matrix(self.frame, rot, flip_h, flip_v) @ Matrix.translate(-off[0], -off[1])


def _decompose(m: Matrix, w: float, h: float):
    """Frame, rotation and flip that draw local (0..w, 0..h) through matrix m."""
    ux, uy = m.apply_vector(w, 0.0), m.apply_vector(0.0, h)
    nw, nh = math.hypot(*ux), math.hypot(*uy)
    rot = math.degrees(math.atan2(ux[1], ux[0])) % 360.0
    if abs(rot - round(rot)) < 1e-7:
        rot = float(round(rot)) % 360.0
    flip_v = (m.a * m.d - m.b * m.c) < 0
    cx, cy = m.apply(w / 2.0, h / 2.0)
    return [cx - nw / 2.0, cy - nh / 2.0, nw, nh], rot, False, flip_v


def map_frame(levels: list[_Level], frame, rot, flip_h, flip_v):
    x, y, w, h = frame
    for lv in reversed(levels):
        x, y, w, h = lv.tx + lv.sx * x, lv.ty + lv.sy * y, lv.sx * w, lv.sy * h
        if lv.turn is not None:
            (x, y, w, h), rot, flip_h, flip_v = _decompose(
                lv.turn @ frame_matrix([x, y, w, h], rot, flip_h, flip_v), w, h)
    return [x, y, w, h], rot, flip_h, flip_v


def map_point(levels: list[_Level], x: float, y: float):
    for lv in reversed(levels):
        x, y = lv.tx + lv.sx * x, lv.ty + lv.sy * y
        if lv.turn is not None:
            x, y = lv.turn.apply(x, y)
    return x, y


def _xfrm(el):
    x = el.find("a:xfrm", NS) if el is not None else None
    if x is None:
        return None
    off, ext = x.find("a:off", NS), x.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return {"off": (emu(off.get("x")), emu(off.get("y"))), "ext": (emu(ext.get("cx")), emu(ext.get("cy"))),
            "rot": int(x.get("rot", "0")) / 60000.0, "flip_h": x.get("flipH") in ("1", "true"),
            "flip_v": x.get("flipV") in ("1", "true"),
            "choff": ((emu(x.find("a:chOff", NS).get("x")), emu(x.find("a:chOff", NS).get("y")))
                      if x.find("a:chOff", NS) is not None else None),
            "chext": ((emu(x.find("a:chExt", NS).get("cx")), emu(x.find("a:chExt", NS).get("cy")))
                      if x.find("a:chExt", NS) is not None else None)}


def _bool(v) -> bool:
    return v in ("1", "true", "on")


class SlideImporter:
    def __init__(self, deck: "DeckImporter", slide_part: str):
        self.deck = deck
        self.pkg = deck.pkg
        self.part = slide_part
        self.root = self.pkg.xml(slide_part)
        self.rels = self.pkg.rels(slide_part)
        self.layout = self.pkg.rel_of_type(slide_part, "slideLayout")
        self.master = self.pkg.rel_of_type(self.layout, "slideMaster") if self.layout else None
        theme_part = self.pkg.rel_of_type(self.master, "theme") if self.master else None
        self.theme = deck.theme(theme_part)
        clr_map = {}
        if self.master:
            cm = self.pkg.xml(self.master).find("p:clrMap", NS)
            if cm is not None:
                clr_map = dict(cm.attrib)
        for part in (self.layout, slide_part):
            if not part:
                continue
            ovr = self.pkg.xml(part).find("p:clrMapOvr/a:overrideClrMapping", NS)
            if ovr is not None:
                clr_map = dict(ovr.attrib)
        self.colors = ColorContext(self.theme, clr_map or None)
        self.other_style = self.pkg.xml(self.master).find("p:txStyles/p:otherStyle", NS) if self.master else None
        self.notes = collections.Counter()
        self.counts = collections.Counter()

    # Text ----------------------------------------------------------------------------

    def _font_name(self, typeface: str | None) -> str | None:
        if not typeface:
            return None
        if typeface.startswith("+mn"):
            return self.theme.minor_font
        if typeface.startswith("+mj"):
            return self.theme.major_font
        return typeface

    def _run_props(self, rpr, base: dict) -> dict:
        out = dict(base)
        if rpr is None:
            return out
        if rpr.get("sz"):
            out["size"] = int(rpr.get("sz")) / 100.0
        if rpr.get("b") is not None:
            out["bold"] = _bool(rpr.get("b"))
        if rpr.get("i") is not None:
            out["italic"] = _bool(rpr.get("i"))
        if rpr.get("u") is not None:
            out["underline"] = rpr.get("u") != "none"
        if rpr.get("baseline") is not None:
            out["baseline"] = int(rpr.get("baseline")) / 100000.0
        if rpr.get("cap") == "all":
            out["_caps"] = True
        if rpr.get("spc") not in (None, "0"):
            self.notes["character spacing ignored"] += 1
        latin = rpr.find("a:latin", NS)
        if latin is not None and latin.get("typeface"):
            out["font"] = self._font_name(latin.get("typeface"))
        fill = rpr.find("a:solidFill", NS)
        if fill is not None:
            c = self.colors.resolve(first_color(fill))
            if c:
                out["color"], out["opacity"] = c
        return out

    def _level_defaults(self, lst_styles: list, lvl: int) -> tuple[dict, dict]:
        """Run and paragraph defaults for a level, nearest style first."""
        run: dict = {}
        para: dict = {}
        for lst in reversed([s for s in lst_styles if s is not None]):
            lp = lst.find(f"a:lvl{lvl + 1}pPr", NS)
            if lp is None:
                continue
            run = self._run_props(lp.find("a:defRPr", NS), run)
            if lp.get("algn"):
                para["align"] = lp.get("algn")
            ls = lp.find("a:lnSpc/a:spcPct", NS)
            if ls is not None:
                para["line_spacing"] = {"pct": int(ls.get("val")) / 100000.0}
        return run, para

    def text_body(self, tx, font_color) -> dict | None:
        if tx is None:
            return None
        body = tx.find("a:bodyPr", NS)
        lst = tx.find("a:lstStyle", NS)
        chain = [lst, self.other_style, self.deck.default_text_style]
        insets = [emu(body.get("lIns"), 7.2) if body is not None and body.get("lIns") else 7.2,
                  emu(body.get("tIns"), 3.6) if body is not None and body.get("tIns") else 3.6,
                  emu(body.get("rIns"), 7.2) if body is not None and body.get("rIns") else 7.2,
                  emu(body.get("bIns"), 3.6) if body is not None and body.get("bIns") else 3.6]
        out = {"paragraphs": [], "insets": insets,
               "wrap": not (body is not None and body.get("wrap") == "none"),
               "anchor": {"ctr": "ctr", "b": "b"}.get(body.get("anchor") if body is not None else "t", "t"),
               "autofit": "none"}
        scale, spacing_cut = 1.0, 0.0
        if body is not None:
            if body.find("a:spAutoFit", NS) is not None:
                out["autofit"] = "shape"
            norm = body.find("a:normAutofit", NS)
            if norm is not None:
                scale = int(norm.get("fontScale", "100000")) / 100000.0
                spacing_cut = int(norm.get("lnSpcReduction", "0")) / 100000.0
                if scale != 1.0 or spacing_cut:
                    self.notes["shrink-to-fit text baked in at PowerPoint's scale"] += 1
            if body.get("vert") not in (None, "horz"):
                out["vert"] = body.get("vert")
                self.notes["vertical text direction not supported yet"] += 1
        any_text = False
        for p in tx.findall("a:p", NS):
            ppr = p.find("a:pPr", NS)
            lvl = int(ppr.get("lvl", "0")) if ppr is not None else 0
            run_defaults, para = self._level_defaults(chain, lvl)
            run_defaults.setdefault("font", self.theme.minor_font)
            run_defaults.setdefault("size", 18.0)
            if "color" not in run_defaults and font_color:
                run_defaults["color"], run_defaults["opacity"] = font_color
            para = dict({"align": "l"}, **para)
            if ppr is not None:
                if ppr.get("algn"):
                    para["align"] = ppr.get("algn") if ppr.get("algn") in ("l", "ctr", "r") else "l"
                ls = ppr.find("a:lnSpc/a:spcPct", NS)
                lp = ppr.find("a:lnSpc/a:spcPts", NS)
                if ls is not None:
                    para["line_spacing"] = {"pct": int(ls.get("val")) / 100000.0}
                elif lp is not None:
                    para["line_spacing"] = {"pts": int(lp.get("val")) / 100.0}
                for key, name in (("space_before", "a:spcBef"), ("space_after", "a:spcAft")):
                    pts = ppr.find(f"{name}/a:spcPts", NS)
                    pct = ppr.find(f"{name}/a:spcPct", NS)
                    if pts is not None:
                        para[key] = int(pts.get("val")) / 100.0
                    elif pct is not None:
                        para[key] = int(pct.get("val")) / 100000.0 * run_defaults["size"] * 1.2
                if ppr.find("a:buChar", NS) is not None or ppr.find("a:buAutoNum", NS) is not None:
                    self.notes["bullets not supported yet"] += 1
            if spacing_cut and "line_spacing" in para and "pct" in para["line_spacing"]:
                para["line_spacing"] = {"pct": para["line_spacing"]["pct"] * (1 - spacing_cut)}
            runs = []
            for r in p:
                t = tag(r)
                if t in ("r", "fld"):
                    props = self._run_props(r.find("a:rPr", NS), run_defaults)
                    text = r.findtext("a:t", default="", namespaces=NS)
                    if props.pop("_caps", False):
                        text = text.upper()
                    if text:
                        props["size"] = round(props["size"] * scale, 4)
                        runs.append(dict(props, t=text))
                        any_text = any_text or bool(text.strip())
                elif t == "br":
                    props = self._run_props(r.find("a:rPr", NS), run_defaults)
                    props.pop("_caps", None)
                    props["size"] = round(props["size"] * scale, 4)
                    runs.append(dict(props, t="\n"))
            end = p.find("a:endParaRPr", NS)
            if end is not None and end.get("sz"):
                para["end_size"] = int(end.get("sz")) / 100.0 * scale
            elif not runs:
                para["end_size"] = run_defaults["size"] * scale
            para["runs"] = runs
            out["paragraphs"].append(para)
        return out if any_text else None

    # Shapes --------------------------------------------------------------------------

    def items(self) -> list[dict]:
        tree = self.root.find("p:cSld/p:spTree", NS)
        return self._walk(tree, [])

    def _walk(self, tree, levels: list[_Level]) -> list[dict]:
        out = []
        for el in tree:
            t = tag(el)
            try:
                if t == "sp":
                    it = self._shape(el, levels)
                elif t == "cxnSp":
                    it = self._shape(el, levels, connector=True)
                elif t == "pic":
                    it = self._picture(el, levels)
                elif t == "grpSp":
                    it = self._group(el, levels)
                elif t == "graphicFrame":
                    self.notes["tables/charts/diagrams skipped"] += 1
                    it = None
                elif t == "AlternateContent":
                    choice = el.find("{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback")
                    it = None
                    if choice is not None:
                        sub = self._walk(choice, levels)
                        out += sub
                else:
                    it = None
            except Exception as exc:   # keep importing the rest of the slide
                self.notes[f"skipped an object: {exc}"] += 1
                it = None
            if it is not None:
                out.append(it)
        return out

    def _meta(self, el, nv_name: str) -> dict:
        nv = el.find(f"p:{nv_name}/p:cNvPr", NS)
        meta = {"name": nv.get("name", "") if nv is not None else ""}
        if nv is not None and nv.get("descr"):
            meta["alt"] = nv.get("descr")
        if nv is not None and _bool(nv.get("hidden")):
            meta["hidden"] = True
        return meta

    def _group(self, el, levels):
        xf = _xfrm(el.find("p:grpSpPr", NS))
        if xf is None:
            return None
        lv = _Level(xf["off"], xf["ext"], xf["choff"] or xf["off"], xf["chext"] or xf["ext"],
                    xf["rot"], xf["flip_h"], xf["flip_v"])
        children = self._walk(el, levels + [lv])
        if not children:
            return None
        self.counts["group"] += 1
        return dict(self._meta(el, "nvGrpSpPr"), id=new_id("it"), type="group", items=children)

    def _placeholder_xfrm(self, el):
        ph = el.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is None:
            return None
        for part in (self.layout, self.master):
            if not part:
                continue
            for sp in self.pkg.xml(part).iter(f"{{{P}}}sp"):
                ph2 = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
                if ph2 is None:
                    continue
                if (ph.get("idx") and ph.get("idx") == ph2.get("idx")) or \
                        (ph.get("type") and ph.get("type") == ph2.get("type")):
                    xf = _xfrm(sp.find("p:spPr", NS))
                    if xf:
                        return xf
        return None

    def _shape(self, el, levels, connector=False):
        sppr = el.find("p:spPr", NS)
        xf = _xfrm(sppr) or (None if connector else self._placeholder_xfrm(el))
        if xf is None:
            return None
        style = el.find("p:style", NS)
        meta = self._meta(el, "nvCxnSpPr" if connector else "nvSpPr")
        prst = sppr.find("a:prstGeom", NS)
        cust = sppr.find("a:custGeom", NS)
        geom = prst.get("prst") if prst is not None else ("custom" if cust is not None else "rect")
        stroke = parse_line(sppr.find("a:ln", NS), self.colors, style_line(self.theme, self.colors, style))
        if sppr.find("a:ln", NS) is None and style is None:
            stroke = None
        fill_res = parse_fill(sppr, self.colors)
        if fill_res is None:
            fill = style_fill(self.theme, self.colors, style)
        else:
            fill, notes = fill_res
            for n in notes:
                self.notes[n] += 1
        ends = {}
        if stroke:
            ends = {k: stroke.pop(k) for k in ("arrow_start", "arrow_end") if k in stroke}
        x, y = xf["off"]
        w, h = xf["ext"]
        if geom in _LINE_PRESETS or (connector and geom.startswith(("straight", "line"))):
            m = frame_matrix([x, y, w, h], xf["rot"], xf["flip_h"], xf["flip_v"])
            pts = [map_point(levels, *m.apply(0, 0)), map_point(levels, *m.apply(w, h))]
            self.counts["line"] += 1
            return dict(meta, id=new_id("it"), type="line", points=[list(p) for p in pts],
                        stroke=stroke, arrow_start=ends.get("arrow_start"), arrow_end=ends.get("arrow_end"))
        if connector:
            self.notes[f"{geom} connector drawn straight"] += 1
            m = frame_matrix([x, y, w, h], xf["rot"], xf["flip_h"], xf["flip_v"])
            pts = [map_point(levels, *m.apply(0, 0)), map_point(levels, *m.apply(w, h))]
            return dict(meta, id=new_id("it"), type="line", points=[list(p) for p in pts], stroke=stroke,
                        arrow_start=ends.get("arrow_start"), arrow_end=ends.get("arrow_end"))
        frame, rot, fh, fv = map_frame(levels, [x, y, w, h], xf["rot"], xf["flip_h"], xf["flip_v"])
        item = dict(meta, id=new_id("it"), type="shape", frame=frame, rot=rot, flip_h=fh, flip_v=fv,
                    stroke=stroke, fill=fill, arrow_start=ends.get("arrow_start"), arrow_end=ends.get("arrow_end"))
        if geom == "custom":
            item["geom"] = "custom"
            item["path"] = self._custom_path(cust, xf["ext"])
            self.counts["freeform"] += 1
        elif presets.is_preset(geom):
            # Every PowerPoint preset is drawn from its own formulas; adjust values convert
            # to fractions and degrees
            item["geom"] = geom
            adj = {}
            for gd in (prst.findall("a:avLst/a:gd", NS) if prst is not None else []):
                name, fmla = gd.get("name"), gd.get("fmla", "")
                if fmla.startswith("val "):
                    adj[name] = presets.to_stored(geom, name, float(fmla.split()[1]))
            if adj:
                item["adj"] = adj
        else:
            item["geom"] = "rect"
            self.notes[f"{geom} shape drawn as a rectangle"] += 1
        nv = el.find("p:nvSpPr/p:cNvSpPr", NS)
        if nv is not None and _bool(nv.get("txBox")):
            item["textbox"] = True
        font_color = style_font_color(self.colors, style) or self.colors.resolve(
            ET.fromstring(f'<a:schemeClr xmlns:a="{NS["a"]}" val="tx1"/>'))
        body = self.text_body(el.find("p:txBody", NS), font_color)
        if body is not None:
            item["text"] = body
            self.counts["text box" if item.get("textbox") else "shape with text"] += 1
        elif geom != "custom":
            self.counts[geom] += 1
        if stroke is None and fill is None and body is None:
            return None   # nothing visible (e.g. an empty placeholder)
        return item

    def _custom_path(self, cust, ext) -> dict:
        shape_w, shape_h = ext[0] * 12700.0, ext[1] * 12700.0   # EMU, the unit guides work in
        env = guide_env(cust, shape_w, shape_h)
        subpaths = []
        for p in cust.findall("a:pathLst/a:path", NS):
            pw = float(p.get("w")) if p.get("w") else shape_w
            ph = float(p.get("h")) if p.get("h") else shape_h
            cmds = []
            for c in p:
                t = tag(c)
                pts = [(num(pt.get("x"), env), num(pt.get("y"), env)) for pt in c.findall("a:pt", NS)]
                if t == "moveTo" and pts:
                    cmds.append(["M", *pts[0]])
                elif t == "lnTo" and pts:
                    cmds.append(["L", *pts[0]])
                elif t == "cubicBezTo" and len(pts) == 3:
                    cmds.append(["C", *pts[0], *pts[1], *pts[2]])
                elif t == "quadBezTo" and len(pts) == 2:
                    cmds.append(["Q", *pts[0], *pts[1]])
                elif t == "arcTo":
                    cmds.append(["A", num(c.get("wR"), env), num(c.get("hR"), env),
                                 num(c.get("stAng"), env) / 60000.0, num(c.get("swAng"), env) / 60000.0])
                elif t == "close":
                    cmds.append(["Z"])
            subpaths.append({"w": pw, "h": ph, "cmds": cmds,
                             "fill": p.get("fill", "norm") != "none",
                             "stroke": not (p.get("stroke") in ("0", "false"))})
        return {"subpaths": subpaths}

    def _picture(self, el, levels):
        sppr = el.find("p:spPr", NS)
        xf = _xfrm(sppr)
        if xf is None:
            return None
        blip = el.find("p:blipFill/a:blip", NS)
        if blip is None:
            return None
        svg = blip.find(f".//{SVG_BLIP}")
        rid = (svg if svg is not None else blip).get(f"{{{R}}}embed")
        target = self.rels.get(rid, (None, ""))[0]
        if not target or target not in self.pkg.names:
            self.notes["linked (not embedded) picture skipped"] += 1
            return None
        aid = self.deck.media_asset(target)
        if aid is None:
            self.notes[f"unsupported picture format ({posixpath.splitext(target)[1]})"] += 1
            return None
        meta = self._meta(el, "nvPicPr")
        frame, rot, fh, fv = map_frame(levels, [xf["off"][0], xf["off"][1], xf["ext"][0], xf["ext"][1]],
                                       xf["rot"], xf["flip_h"], xf["flip_v"])
        crop = [0.0, 0.0, 0.0, 0.0]
        src = el.find("p:blipFill/a:srcRect", NS)
        if src is not None:
            crop = [int(src.get(k, "0")) / 100000.0 for k in "ltrb"]
            if any(v < 0 for v in crop):
                self.notes["picture padding (negative crop) ignored"] += 1
                crop = [max(v, 0.0) for v in crop]
        opacity = 1.0
        amf = blip.find("a:alphaModFix", NS)
        if amf is not None:
            opacity = int(amf.get("amt", "100000")) / 100000.0
        if sppr.find("a:ln", NS) is not None and sppr.find("a:ln/a:noFill", NS) is None:
            self.notes["picture borders not supported yet"] += 1
        self.counts["picture"] += 1
        asset = self.deck.doc["assets"][aid]
        return dict(meta, id=new_id("it"), type="picture", name=meta.get("name") or asset["name"], asset=aid,
                    page_index=0, frame=frame, crop=crop, rot=rot, flip_h=fh, flip_v=fv, opacity=opacity,
                    source="auto")


class DeckImporter:
    """`source`: a deck's path, or its bytes (copied slides). `index`: figure files to relink
    pictures to, if already gathered (else from `search_dirs`, or the folders near the deck)."""

    def __init__(self, source: str | bytes, search_dirs: list[str] | None, relink: bool, cache: AssetCache | None,
                 name: str | None = None, index: CandidateIndex | None = None):
        self.pkg = Package(source)
        path = self.pkg.path
        self.cache = cache or get_cache()
        self.doc = model.new_document(name or os.path.splitext(os.path.basename(path or "Copied slides"))[0])
        self.doc["pages"] = []
        if path:
            self.doc["meta"]["imported_from"] = os.path.abspath(path)
        self.relink = relink
        self.index = (index or CandidateIndex(search_dirs or (default_search_dirs(path) if path else []))) if relink else None
        self._themes: dict = {}
        self._media: dict[str, str | None] = {}
        # What each picture's relinking said, and which pictures each slide used, so a report can
        # be made for any of the slides
        self._media_lines: dict[str, list[str]] = {}
        self._slide_media: list[str] | None = None
        self.slide_media: dict[int, list[str]] = {}
        self.slide_lines: dict[int, list[str]] = {}
        self.report: list[str] = []
        self.default_text_style = None
        self.slides: list[str] = []
        self.slide_ids: list[int] = []
        self._presentation()

    def _presentation(self) -> None:
        part = self.pkg.main_part(default="ppt/presentation.xml")
        pres = self.pkg.xml(part)
        sz = pres.find("p:sldSz", NS)
        self.width, self.height = emu(sz.get("cx")), emu(sz.get("cy"))
        self.default_text_style = pres.find("p:defaultTextStyle", NS)
        prels = self.pkg.rels(part)
        lst = pres.find("p:sldIdLst", NS)
        for s in (lst if lst is not None else []):
            self.slides.append(prels[s.get(f"{{{R}}}id")][0])
            self.slide_ids.append(int(s.get("id", "0")))

    def slide_info(self) -> list[dict]:
        """Each slide's number, title (its title placeholder's text, if it has one) and whether
        it's hidden in the slide show."""
        out = []
        for n, part in enumerate(self.slides, 1):
            root = self.pkg.xml(part)
            title = ""
            for sp in root.iter(f"{{{P}}}sp"):
                ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
                if ph is not None and ph.get("type") in ("title", "ctrTitle"):
                    paras = ("".join(t.text or "" for t in p.iter(f"{{{NS['a']}}}t")) for p in sp.iter(f"{{{NS['a']}}}p"))
                    title = re.sub(r"\s+", " ", " ".join(paras)).strip()
                    break
            out.append({"n": n, "title": title, "hidden": root.get("show") == "0"})
        return out

    def theme(self, part: str | None) -> Theme:
        if part not in self._themes:
            self._themes[part] = Theme(self.pkg.xml(part) if part else None)
        return self._themes[part]

    def media_asset(self, part: str) -> str | None:
        if self._slide_media is not None:
            self._slide_media.append(part)
        if part in self._media:
            return self._media[part]
        lines = self._media_lines.setdefault(part, [])
        data = self.pkg.z.read(part)
        ext = posixpath.splitext(part)[1].lower()
        kind = {".svg": "svg", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".tif": "tiff",
                ".tiff": "tiff", ".pdf": "pdf"}.get(ext)
        if ext == ".emf":
            pdf = emf_pdf(data)
            if pdf is not None:
                data, kind = pdf, "pdf"
        if ext in (".gif", ".bmp"):
            import io
            from PIL import Image
            buf = io.BytesIO()
            Image.open(io.BytesIO(data)).save(buf, "PNG")
            data, kind = buf.getvalue(), "png"
        if kind is None:
            self._media[part] = None
            return None
        name = posixpath.basename(part)
        aid = None
        if self.index is not None:
            orig, info = (self.index.match_svg(data) if kind == "svg" else (self.index.by_hash(kind, data), {}))
            if orig:
                aid, asset, warns = new_asset(orig, self.cache)
                self.doc["assets"][aid] = asset
                extra = f" (match score {info['score']}, runner-up {info['runner_up']})" if info else ""
                variants = "+".join(sorted(asset["variants"]))
                lines.append(f"relinked {name} -> {orig} [{variants}]{extra}")
                for w in warns:
                    lines.append(f"  {w}")
            elif kind == "svg":
                lines.append(f"kept the deck's copy of {name}: no original found "
                             f"(best score {info.get('score', 0)})")
            else:
                lines.append(f"kept the deck's copy of {name}: no identical file found")
        if aid is None:
            ext_name = name if kind != "pdf" or name.endswith(".pdf") else posixpath.splitext(name)[0] + ".pdf"
            aid, asset = new_asset_from_bytes(data, ext_name, self.cache)
            self.doc["assets"][aid] = asset
        self._media[part] = aid
        return aid

    def run(self, slide_numbers: list[int] | None) -> tuple[dict, list[str]]:
        numbers = slide_numbers or list(range(1, len(self.slides) + 1))
        reported: set[str] = set()
        for n in numbers:
            if not 1 <= n <= len(self.slides):
                self.report.append(f"slide {n} doesn't exist (deck has {len(self.slides)})")
                continue
            self._slide_media = []
            si = SlideImporter(self, self.slides[n - 1])
            page = model.new_page(f"Slide {n}", self.width, self.height)
            page["items"] = si.items()
            page["origin"] = {"deck": self.pkg.path, "slide": n}
            self.doc["pages"].append(page)
            counts = ", ".join(f"{v} {k}" for k, v in si.counts.most_common())
            lines = [f"slide {n}: {counts}"]
            for note, k in si.notes.most_common():
                lines.append(f"  note: {note}" + (f" (x{k})" if k > 1 else ""))
            self.slide_media[n], self.slide_lines[n] = list(dict.fromkeys(self._slide_media)), lines
            self._slide_media = None
            for part in self.slide_media[n]:
                if part not in reported:
                    self.report += self._media_lines.get(part, [])
                    reported.add(part)
            self.report += lines
        return self.doc, self.report

    def report_for(self, numbers: list[int]) -> list[str]:
        """The report for some of the slides run (each picture's relinking said once)."""
        out: list[str] = []
        seen: set[str] = set()
        for n in numbers:
            for part in self.slide_media.get(n, []):
                if part not in seen:
                    out += self._media_lines.get(part, [])
                    seen.add(part)
            out += self.slide_lines.get(n, [])
        return out


def import_pptx(path: str, slides: list[int] | None = None, search_dirs: list[str] | None = None,
                relink: bool = True, cache: AssetCache | None = None) -> tuple[dict, list[str]]:
    """Import slides (1-based numbers; default all) as pages of a new document."""
    return DeckImporter(path, search_dirs, relink, cache).run(slides)


def slide_ids(source: str | bytes) -> list[int]:
    """A deck's slide ids (presentation.xml's sldId: what PowerPoint calls a slide by when one is
    dragged out of it), in slide order."""
    pkg = Package(source)
    lst = pkg.xml(pkg.main_part(default="ppt/presentation.xml")).find("p:sldIdLst", NS)
    return [int(s.get("id", "0")) for s in (lst if lst is not None else [])]

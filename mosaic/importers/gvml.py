"""Shapes copied in PowerPoint: the DrawingML package Office puts on the clipboard ("Art::GVML
ClipFormat"), as editable objects.

The package holds one drawing: a locked canvas of DrawingML shapes (a:sp, a:pic, a:grpSp,
a:cxnSp) at the positions they had on the slide, with the theme they used and their pictures.
They're the slide importer's shapes wrapped in DrawingML's own elements instead of
PresentationML's (a:nvSpPr for p:nvSpPr, a:txSp/a:txBody for p:txBody, and so on), so they're
rewrapped and read by the same code.
"""
from __future__ import annotations

import collections
import xml.etree.ElementTree as ET

from ..assets import AssetCache
from .drawingml import NS, ColorContext
from .pptx import DeckImporter, SlideImporter
from .relink import CandidateIndex

A, P = NS["a"], NS["p"]
LOCKED_CANVAS = "{http://schemas.openxmlformats.org/drawingml/2006/lockedCanvas}lockedCanvas"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_SHAPES = {"sp", "pic", "grpSp", "cxnSp", "graphicFrame"}
_NON_VISUAL = {"nvSpPr", "nvPicPr", "nvGrpSpPr", "nvCxnSpPr", "nvGraphicFramePr"}
_PROPERTIES = {"spPr", "grpSpPr", "style", "blipFill"}


def _local(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _rewrap_into(out, children) -> None:
    """Shapes (and PowerPoint's alternative versions of them) appended to `out`, rewrapped."""
    for child in children:
        if child.tag.startswith(f"{{{A}}}") and _local(child) in _SHAPES:
            out.append(_rewrap(child))
        elif child.tag == f"{{{MC}}}AlternateContent":
            fallback = child.find(f"{{{MC}}}Fallback")
            if fallback is not None:
                alt = ET.SubElement(out, child.tag, child.attrib)
                _rewrap_into(ET.SubElement(alt, fallback.tag, fallback.attrib), list(fallback))


def _rewrap(el):
    """A DrawingML shape as PresentationML's: the shape's own parts in the p: namespace, what's
    inside them as it was."""
    out = ET.Element(f"{{{P}}}{_local(el)}", el.attrib)
    for child in el:
        name = _local(child)
        if child.tag == f"{{{MC}}}AlternateContent" or (child.tag.startswith(f"{{{A}}}") and name in _SHAPES):
            _rewrap_into(out, [child])   # a group's shapes
        elif not child.tag.startswith(f"{{{A}}}"):
            out.append(child)
        elif name in _NON_VISUAL:
            nv = ET.SubElement(out, f"{{{P}}}{name}")
            for c in child:
                if _local(c).startswith("cNv"):
                    ET.SubElement(nv, f"{{{P}}}{_local(c)}", c.attrib).extend(list(c))
                else:
                    nv.append(c)
        elif name in _PROPERTIES:
            ET.SubElement(out, f"{{{P}}}{name}", child.attrib).extend(list(child))
        elif name == "txSp":
            body = child.find("a:txBody", NS)
            if body is not None:
                ET.SubElement(out, f"{{{P}}}txBody", body.attrib).extend(list(body))
        else:
            out.append(child)
    return out


class _Canvas(SlideImporter):
    """The copied shapes, read like a slide's: no layout or master, the copy's own theme."""

    def __init__(self, deck: "ShapesImporter", part: str, tree):
        self.deck = deck
        self.pkg = deck.pkg
        self.part = part
        self.root = tree
        self.rels = self.pkg.rels(part)
        self.layout = self.master = None
        self.theme = deck.theme(self.pkg.rel_of_type(part, "theme"))
        self.colors = ColorContext(self.theme)
        self.other_style = None
        self.notes = collections.Counter()
        self.counts = collections.Counter()

    def items(self) -> list[dict]:
        return self._walk(self.root, [])


class ShapesImporter(DeckImporter):
    """A copied drawing instead of a deck; run() gives its objects, at their slide positions."""

    def _presentation(self) -> None:
        self.part = self.pkg.main_part("drawing")
        if not self.part:
            raise ValueError("no drawing in the copied shapes")
        self.width = self.height = 0.0

    def run(self, slide_numbers=None):   # noqa: ARG002 (one drawing, no slides)
        canvas = self.pkg.xml(self.part).find(f".//{LOCKED_CANVAS}")
        tree = ET.Element(f"{{{P}}}spTree")
        if canvas is not None:
            _rewrap_into(tree, list(canvas))
        self._slide_media = []
        reader = _Canvas(self, self.part, tree)
        items = reader.items()
        for part in dict.fromkeys(self._slide_media):
            self.report += self._media_lines.get(part, [])
        self._slide_media = None
        counts = ", ".join(f"{v} {k}" for k, v in reader.counts.most_common())
        self.report.append(f"copied shapes: {counts}" if counts else "copied shapes: nothing that can be drawn")
        for note, k in reader.notes.most_common():
            self.report.append(f"  note: {note}" + (f" (x{k})" if k > 1 else ""))
        return items, self.report


def import_shapes(data: bytes, search_dirs: list[str] | None = None, relink: bool = True,
                  cache: AssetCache | None = None, index: CandidateIndex | None = None) -> tuple[list[dict], dict, list[str]]:
    """Copied shapes -> (objects, the pictures they use, report)."""
    imp = ShapesImporter(data, search_dirs, relink, cache, name="Copied shapes", index=index)
    items, report = imp.run()
    return items, imp.doc["assets"], report

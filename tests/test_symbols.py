"""Symbols: a copy draws its symbol's objects scaled to its frame, lines and text with them, in
the editor and every export; the check sees them as drawn."""
import numpy as np
from lxml import etree
from PIL import Image

from mosaic import model
from mosaic.export.preflight import preflight
from mosaic.export.run import export_document
from mosaic.resolve import DrawGroup, DrawPath, DrawText, Resolver, flat_prims

SYMBOL = {"id": "sym1", "name": "Cell", "size": [40.0, 20.0], "items": [
    {"id": "box", "type": "shape", "geom": "rect", "frame": [0, 0, 40, 20], "rot": 0,
     "stroke": {"color": "#000000", "width": 1.0}, "fill": {"color": "#ff0000"}},
    {"id": "txt", "type": "shape", "geom": "rect", "textbox": True, "frame": [4, 4, 30, 10], "rot": 0, "stroke": None,
     "fill": None, "text": {"paragraphs": [{"align": "l", "runs": [{"t": "A", "font": "Helvetica", "size": 6,
                                                                    "bold": False, "italic": False, "color": "#000000"}]}],
                           "insets": [0, 0, 0, 0], "wrap": False, "anchor": "t", "autofit": "none"}},
]}


def copy(x, y, scale=1.0, **kw):
    return {"id": f"c{x}", "type": "symbol", "symbol": "sym1", "frame": [x, y, 40 * scale, 20 * scale], "rot": 0,
            "flip_h": False, "flip_v": False, **kw}


def doc_with(*items):
    doc = model.new_document("symbols")
    doc["symbols"] = [SYMBOL]
    page = doc["pages"][0]
    page["width"], page["height"], page["background"] = 200.0, 100.0, "#ffffff"
    page["items"] = list(items)
    return doc


def test_a_copy_scales_lines_and_text_with_it():
    doc = doc_with(copy(10, 10, 2.0))
    r = Resolver(doc).resolve(doc["pages"][0]["items"][0])
    (group,) = r.prims
    assert isinstance(group, DrawGroup) and group.matrix.as_tuple() == (2.0, 0.0, 0.0, 2.0, 10.0, 10.0)
    assert r.bbox[0] < 10 and r.bbox[2] > 90 and r.bbox[3] > 50   # the 80 x 40 box and its 2 pt line
    flat = list(flat_prims(r.prims))
    assert [p.stroke.width for p in flat if isinstance(p, DrawPath) and p.stroke] == [2.0]
    (text,) = [p for p in flat if isinstance(p, DrawText)]
    assert abs(text.matrix.scale_factor - 2.0) < 1e-9
    summary = preflight(doc, {"pages": [0]})["summary"]
    assert summary["thinnest_line_pt"] == 2.0 and summary["smallest_text_pt"] == 12.0


def test_copies_in_every_export(tmp_path):
    doc = doc_with(copy(10, 10), copy(100, 10, 2.0))
    export_document(doc, str(tmp_path / "s"), ["pdf", "svg", "png"], dpi=144, transparent=False)
    svg = etree.parse(str(tmp_path / "s.svg"))
    transforms = [g.get("transform") for g in svg.iter("{http://www.w3.org/2000/svg}g") if g.get("transform")]
    assert "matrix(2 0 0 2 100 10)" in transforms
    px = np.asarray(Image.open(tmp_path / "s.png").convert("RGB"), dtype=int)
    # Inside both boxes red; the big one's line twice as wide (2 pt = 4 px at 144 dpi)
    assert tuple(px[int(20 * 2), int(30 * 2)]) == (255, 0, 0) and tuple(px[int(40 * 2), int(150 * 2)]) == (255, 0, 0)
    dark = lambda row: [x for x in range(px.shape[1]) if px[row, x].sum() < 200]
    left_edge = [x for x in dark(int(45 * 2)) if 195 <= x <= 210]
    assert len(left_edge) >= 3


def test_a_symbol_cant_hold_itself():
    doc = doc_with(copy(10, 10))
    doc["symbols"][0] = {**SYMBOL, "items": [*SYMBOL["items"], copy(0, 0)]}
    r = Resolver(doc).resolve(doc["pages"][0]["items"][0])
    assert r.prims and any("itself" in w for w in r.warnings)
    missing = Resolver(doc_with()).resolve({**copy(0, 0), "symbol": "gone"})
    assert not missing.prims and missing.warnings == ["its symbol is missing"]


def test_a_turned_copy():
    doc = doc_with(copy(50, 40, rot=90))
    r = Resolver(doc).resolve(doc["pages"][0]["items"][0])
    x0, y0, x1, y1 = r.bbox
    assert abs((x1 - x0) - 21) < 0.6 and abs((y1 - y0) - 41) < 0.6   # 20 wide and 40 tall, with its line

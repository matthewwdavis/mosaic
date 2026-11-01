"""Export to editable PowerPoint: PowerPoint's own shapes, lines, text and pictures where it draws
them the same, exact pictures (SVG with a PNG copy) where it can't; it reads back as it was."""
import zipfile

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from figassemble import assets, model
from figassemble.export.run import export_document
from figassemble.importers.pptx import import_pptx


def stroke(**kw):
    return {"color": "#2b6cb0", "width": 1.5, "dash": "solid", "cap": "round", "join": "round", "opacity": 1, **kw}


def test_native_objects_and_exact_pictures(fixtures, cache, tmp_path):
    doc = model.new_document("deck")
    page = doc["pages"][0]
    page["width"], page["height"] = 300.0, 200.0
    aid, asset, _ = assets.new_asset(fixtures["pdf"], cache)
    doc["assets"][aid] = asset
    pic = model.picture_item(aid, asset, 10, 10)
    pic["crop"], pic["rot"], pic["opacity"] = [0.1, 0, 0, 0.2], 10, 0.5
    page["items"] = [
        pic,
        {"id": "star", "type": "shape", "geom": "star5", "frame": [150, 10, 50, 50], "rot": 20, "adj": {"adj": 0.3},
         "stroke": stroke(), "fill": {"color": "#e69f00"}},
        {"id": "round", "type": "shape", "geom": "rect", "frame": [210, 10, 60, 30], "rounding": 0.5, "stroke": stroke(), "fill": None},
        {"id": "text", "type": "shape", "geom": "rect", "textbox": True, "frame": [150, 80, 120, 20], "stroke": None, "fill": None,
         "text": {"paragraphs": [{"align": "l", "runs": [{"t": "OD", "font": "Helvetica", "size": 8, "bold": True, "italic": False,
                                                          "color": "#000000"}]}], "insets": [0, 0, 0, 0], "wrap": True,
                  "anchor": "t", "autofit": "shape"}},
        {"id": "arrow", "type": "line", "points": [[150, 120], [280, 150]], "stroke": stroke(), "arrow_start": None,
         "arrow_end": {"type": "triangle", "w": "med", "len": "med"}},
        {"id": "outlined", "type": "line", "points": [[20, 180], [120, 180]], "stroke": stroke(), "arrow_start": None, "arrow_end": None,
         "outline": {"color": "#ffffff", "width": 1}},
    ]
    res = export_document(doc, str(tmp_path / "deck"), ["pptx"], cache=cache)
    path = tmp_path / "deck.pptx"
    assert res["files"] == [str(path)] and any("an outline went in as exact pictures" in w for w in res["warnings"])
    prs = Presentation(str(path))
    assert (prs.slide_width, prs.slide_height) == (300 * 12700, 200 * 12700)
    kinds = [sh.shape_type for sh in prs.slides[0].shapes]
    assert kinds == [MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.AUTO_SHAPE, MSO_SHAPE_TYPE.FREEFORM, MSO_SHAPE_TYPE.TEXT_BOX,
                     MSO_SHAPE_TYPE.LINE, MSO_SHAPE_TYPE.PICTURE]
    slide_xml = zipfile.ZipFile(path).read("ppt/slides/slide1.xml").decode()
    assert slide_xml.count("svgBlip") == 2 and 'alphaModFix amt="50000"' in slide_xml and 'srcRect l="10000" t="0" r="0" b="20000"' in slide_xml
    # It reads back as it was
    back, _ = import_pptx(str(path), cache=cache)
    items = back["pages"][0]["items"]
    star = next(it for it in items if it.get("geom") == "star5")
    assert star["frame"] == [150.0, 10.0, 50.0, 50.0] and round(star["rot"]) == 20 and abs(star["adj"]["adj"] - 0.3) < 1e-6
    line = next(it for it in items if it["type"] == "line")
    assert line["points"] == [[150.0, 120.0], [280.0, 150.0]] and line["arrow_end"]["type"] == "triangle"
    text = next(it for it in items if it.get("textbox"))
    assert text["text"]["paragraphs"][0]["runs"][0]["t"] == "OD" and text["text"]["paragraphs"][0]["runs"][0]["bold"]
    assert next(it for it in items if it.get("geom") == "custom")["frame"] == [210.0, 10.0, 60.0, 30.0]

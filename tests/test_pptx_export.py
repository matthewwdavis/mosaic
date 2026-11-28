"""Export to editable PowerPoint: PowerPoint's own shapes, lines, text and pictures where it draws
them the same, exact pictures (SVG with a PNG copy) where it can't; it reads back as it was."""
import zipfile

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from mosaic import assets, model
from mosaic.export.run import export_document
from mosaic.importers.pptx import import_pptx


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


def test_extra_small_and_extra_large_arrowheads_go_in_as_pictures(cache, tmp_path):
    # PowerPoint has only small, medium and large ends: a line with mosaic's extra small or extra
    # large goes in as an exact picture of itself; one with PowerPoint's sizes stays a line
    doc = model.new_document("deck")
    page = doc["pages"][0]
    page["width"], page["height"] = 300.0, 200.0
    arrow = lambda i, y, size: {"id": i, "type": "line", "points": [[20, y], [200, y]], "stroke": stroke(width=0.25),
                                "arrow_start": None, "arrow_end": {"type": "triangle", "w": size, "len": size}}
    page["items"] = [arrow("xs", 40, "xs"), arrow("lg", 80, "lg"), arrow("xl", 140, "xl")]
    res = export_document(doc, str(tmp_path / "deck"), ["pptx"], cache=cache)
    assert any("an extra small or extra large arrowhead went in as exact pictures" in w for w in res["warnings"]), res["warnings"]
    kinds = [sh.shape_type for sh in Presentation(str(tmp_path / "deck.pptx")).slides[0].shapes]
    assert kinds == [MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.LINE, MSO_SHAPE_TYPE.PICTURE]
    slide_xml = zipfile.ZipFile(tmp_path / "deck.pptx").read("ppt/slides/slide1.xml").decode()
    assert 'w="lg" len="lg"' in slide_xml and 'w="xs"' not in slide_xml and 'w="xl"' not in slide_xml


def test_objects_parked_off_the_page_are_left_out_of_every_export(cache, tmp_path):
    """Wholly off the page (kept there, like PowerPoint's pasteboard), an object isn't exported;
    one partly on the page is, cut at the page's edge."""
    doc = model.new_document("parked")
    page = doc["pages"][0]
    page["width"], page["height"] = 300.0, 200.0
    rect = lambda id, frame, colour: {"id": id, "type": "shape", "geom": "rect", "frame": frame, "rot": 0,  # noqa: E731
                                      "stroke": None, "fill": {"color": colour}}
    page["items"] = [rect("on", [20, 20, 60, 40], "#0072b2"), rect("half", [-30, 100, 60, 40], "#e69f00"),
                     rect("parked", [-200, 50, 60, 40], "#cc79a7")]
    export_document(doc, str(tmp_path / "fig"), ["svg", "pptx"], cache=cache)
    svg = (tmp_path / "fig.svg").read_text(encoding="utf-8").lower()
    assert "#0072b2" in svg and "#e69f00" in svg and "#cc79a7" not in svg
    slide = zipfile.ZipFile(tmp_path / "fig.pptx").read("ppt/slides/slide1.xml").decode("utf-8").upper()
    assert "0072B2" in slide and "E69F00" in slide and "CC79A7" not in slide


def test_thin_objects_go_in_as_pictures_at_least_3_pt_across(cache, tmp_path):
    """A PDF page can't be under 3 pt a side, so an upright dotted line 1.5 pt across (an exact
    picture: even dashes) sits centred in a 3 pt picture; it used to stop the export (V6, 11-27)."""
    doc = model.new_document("thin")
    page = doc["pages"][0]
    page["width"], page["height"] = 300.0, 200.0
    page["items"] = [{"id": "dots", "type": "line", "points": [[100, 20], [100, 120]], "stroke": stroke(dash="sysDot"),
                      "arrow_start": None, "arrow_end": None}]
    res = export_document(doc, str(tmp_path / "thin"), ["pptx"], cache=cache)
    assert any("even dashes went in as exact pictures" in w for w in res["warnings"]), res["warnings"]
    (pic,) = Presentation(str(tmp_path / "thin.pptx")).slides[0].shapes
    assert pic.shape_type == MSO_SHAPE_TYPE.PICTURE
    assert abs(pic.width / 12700 - 3.0) < 1e-3 and abs((pic.left + pic.width / 2) / 12700 - 100.0) < 1e-3


def test_line_spacing_goes_in_as_a_multiple_or_exact_points(cache, tmp_path):
    """The model keeps line spacing as {pct} or {pts}; the writer took it for a bare number and
    stopped the export ("float() argument must be ... not 'dict'", 11-27). Both read back as they were."""
    doc = model.new_document("spacing")
    page = doc["pages"][0]
    page["width"], page["height"] = 300.0, 200.0
    text = lambda id, y, spacing: {"id": id, "type": "shape", "geom": "rect", "textbox": True, "frame": [20, y, 200, 40],  # noqa: E731
                                   "stroke": None, "fill": None,
                                   "text": {"paragraphs": [{"align": "l", "line_spacing": spacing,
                                                            "runs": [{"t": "one\ntwo", "font": "Helvetica", "size": 6, "bold": False,
                                                                      "italic": False, "color": "#000000"}]}],
                                            "insets": [0, 0, 0, 0], "wrap": True, "anchor": "t", "autofit": "none"}}
    page["items"] = [text("pct", 20, {"pct": 0.9}), text("pts", 80, {"pts": 7.5})]
    export_document(doc, str(tmp_path / "spacing"), ["pptx"], cache=cache)
    slide_xml = zipfile.ZipFile(tmp_path / "spacing.pptx").read("ppt/slides/slide1.xml").decode()
    assert '<a:spcPct val="90000"/>' in slide_xml and '<a:spcPts val="750"/>' in slide_xml
    back, _ = import_pptx(str(tmp_path / "spacing.pptx"), cache=cache)
    spacings = [it["text"]["paragraphs"][0].get("line_spacing") for it in back["pages"][0]["items"] if it.get("textbox")]
    assert spacings == [{"pct": 0.9}, {"pts": 7.5}], spacings

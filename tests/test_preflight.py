"""The pre-export check's thinnest line (the figure's own lines, outlines, and the lines inside
placed PDFs and SVGs at their printed size) and the page's size against a journal's."""
import numpy as np
import pikepdf
import pytest

from mosaic import assets, model, vectors
from mosaic.export.preflight import preflight
from mosaic.journals import MM


def page_with(*items, width=200.0, height=150.0):
    doc = model.new_document("check")
    page = doc["pages"][0]
    page["width"], page["height"] = width, height
    page["items"] = list(items)
    return doc


def line(width, **kw):
    return {"id": "l", "type": "line", "name": "Line", "points": [[20, 30], [120, 30]], "arrow_start": None,
            "arrow_end": None, "stroke": {"color": "#000000", "width": width}, **kw}


def messages(doc, **options):
    return [f["message"] for f in preflight(doc, {"pages": [0], **options})["items"]]


def place(doc, path, scale=1.0, crop=None):
    aid, asset, _ = assets.new_asset(str(path), use_siblings=False)
    doc["assets"][aid] = asset
    pic = model.picture_item(aid, asset, 10, 10)
    pic["name"] = "Plot"
    pic["frame"][2] *= scale
    pic["frame"][3] *= scale
    if crop:
        pic["crop"] = crop
    doc["pages"][0]["items"].append(pic)
    return pic


def pdf_file(path, content: bytes, size=(100, 50), rotate=0, forms=None):
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=size)
    page.obj.Contents = pdf.make_stream(content)
    if rotate:
        page.obj.Rotate = rotate
    for name, (stream, matrix) in (forms or {}).items():
        form = pdf.make_stream(stream, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Form,
                               BBox=[0, 0, size[0], size[1]], Matrix=matrix)
        page.obj.Resources = page.obj.get("/Resources", pikepdf.Dictionary())
        page.obj.Resources.XObject = page.obj.Resources.get("/XObject", pikepdf.Dictionary())
        page.obj.Resources.XObject[name] = form
    pdf.save(path)
    return path


def test_the_figures_own_thin_lines_and_outlines():
    doc = page_with(line(0.1))
    res = preflight(doc, {"pages": [0]})
    assert res["summary"]["thinnest_line_pt"] == 0.1
    assert "thinnest line is 0.10 pt (below 0.25 pt)" in res["items"][0]["message"]
    assert any(f.get("item") == "l" and f["message"] == "Line: its line is 0.10 pt (below 0.25 pt)" for f in res["items"])
    assert preflight(page_with(line(0.5)), {"pages": [0]})["summary"]["thinnest_line_pt"] == 0.5
    assert not any("thin" in m for m in messages(page_with(line(0.5))))
    # A thin outline round a thick line is a thin band
    assert "Line: its outline is 0.10 pt (below 0.25 pt)" in messages(
        page_with(line(1.0, outline={"color": "#ffffff", "width": 0.1})))
    # A border in the fill's own colour, and a see-through line, don't show as lines
    shape = {"id": "s", "type": "shape", "geom": "rect", "frame": [10, 10, 50, 40], "rot": 0,
             "fill": {"color": "#ff0000"}, "stroke": {"color": "#FF0000", "width": 0.05}}
    assert preflight(page_with(shape), {"pages": [0]})["summary"]["thinnest_line_pt"] is None
    assert preflight(page_with(line(0.1, stroke={"color": "#000000", "width": 0.1, "opacity": 0})),
                     {"pages": [0]})["summary"]["thinnest_line_pt"] is None


def test_lines_inside_a_placed_pdf_at_their_printed_size(tmp_path):
    f = pdf_file(tmp_path / "plot.pdf", b"0 0 0 RG 0.5 w 10 40 m 90 40 l S 1 w 10 10 m 90 10 l S")
    doc = page_with()
    pic = place(doc, f)
    assert preflight(doc, {"pages": [0]})["summary"]["thinnest_line_pt"] == 0.5
    # At 40% its 0.5 pt line prints at 0.2 pt
    pic["frame"][2:] = [40.0, 20.0]
    res = preflight(doc, {"pages": [0]})
    assert res["summary"]["thinnest_line_pt"] == 0.2
    assert "Plot: its thinnest line prints at 0.20 pt (below 0.25 pt)" in [f["message"] for f in res["items"]]
    assert any(m.startswith("Plot is scaled to 40.0%: its thinnest line prints at 0.20 pt") for m in messages(doc))
    # Cropped to the bottom half, only the 1 pt line shows (0.4 pt at 40%)
    pic["crop"] = [0.0, 0.5, 0.0, 0.0]
    assert preflight(doc, {"pages": [0]})["summary"]["thinnest_line_pt"] == 0.4


def test_a_picture_stretched_unevenly(tmp_path):
    f = pdf_file(tmp_path / "legend.pdf", b"0 0 0 RG 0.5 w 10 25 m 90 25 l S", size=(85, 10))
    doc = page_with()
    pic = place(doc, f)
    assert not any("stretched" in m for m in messages(doc))
    # As PowerPoint left a legend: 85 x 10 pt in an 84 x 9 pt frame
    pic["frame"][2:] = [84.0, 9.0]
    assert "Plot is stretched, 98.8% across and 90.0% down, so its text and curves are distorted " \
           "(100% on its Picture tab puts it back)" in messages(doc)
    assert next(f for f in preflight(doc, {"pages": [0]})["items"] if "stretched" in f["message"])["level"] == "warning"
    # Scaled evenly, or turned a quarter, it isn't stretched
    pic["frame"][2:] = [42.5, 5.0]
    assert not any("stretched" in m for m in messages(doc))
    pic["rot"] = 90.0
    assert not any("stretched" in m for m in messages(doc))


def test_what_counts_as_a_line_in_a_pdf(tmp_path):
    def widths(content, **kw):
        found = vectors.strokes(str(pdf_file(tmp_path / f"p{len(list(tmp_path.iterdir()))}.pdf", content, **kw)), "pdf", 0)
        return sorted(found)
    # Filled and stroked in one colour: ggplot's points with stroke = 0
    assert widths(b"0.01 w 1 0 0 rg 1 0 0 RG 10 10 20 20 re B 0.3 w 10 10 m 20 20 l S") == [0.3]
    # A border in another colour is a line
    assert widths(b"0.01 w 1 0 0 rg 0 0 0 RG 10 10 20 20 re B") == [0.01]
    # Transforms scale the width (the narrowest way), inside a q/Q pair only
    assert widths(b"q 0.5 0 0 0.25 0 0 cm 1 w 10 10 m 20 20 l S Q 2 w 10 10 m 20 20 l S") == [0.25, 2.0]
    # Lines drawn in a form, which has its own matrix
    assert widths(b"/F1 Do", forms={"/F1": (b"3 w 0 0 m 10 10 l S", [0.5, 0, 0, 0.5, 0, 0])}) == [1.5]
    # A hairline (0 wide), and no stroke at all
    assert widths(b"0 w 10 10 m 20 20 l S 10 10 30 30 re f") == [0.0]
    doc = page_with()
    place(doc, pdf_file(tmp_path / "hair.pdf", b"0 w 10 10 m 20 20 l S"))
    assert any("Plot has hairlines" in m for m in messages(doc))


def test_where_a_pdf_line_is_on_a_turned_page(tmp_path):
    # Landscape 200 x 100, turned a quarter clockwise: shown 100 wide, 200 tall
    f = pdf_file(tmp_path / "turned.pdf", b"0.5 w 10 90 m 30 90 l S", size=(200, 100), rotate=90)
    (box,) = vectors.strokes(str(f), "pdf", 0)[0.5]
    # The unturned top left corner is now at the top right
    assert box.tolist() == pytest.approx([90, 10, 90, 30])


SVGLITE = """<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'
  width='200pt' height='100pt' viewBox='0 0 400 200'>
<g class='svglite'><defs><style type='text/css'><![CDATA[
  .svglite line, .svglite polyline, .svglite path, .svglite rect, .svglite circle { fill: none; stroke: #000000; }
  .svglite g.glyphgroup path { fill: inherit; stroke: none; }
  .thin { stroke-width: 0.2; }
  ]]></style>
  <path id='tick' d='M0 0 v5'/>
  <symbol id='sym'><polyline points='0,0 10,10' style='stroke-width: 7;'/></symbol>
</defs>
<polyline points='10,10 100,10' style='stroke-width: 1.5;'/>
<g class='glyphgroup'><path d='M0 0 L5 5' style='stroke-width: 0.1;'/></g>
<line x1='0' y1='0' x2='10' y2='0' class='thin'/>
<g transform='scale(0.5)'><rect x='0' y='0' width='10' height='10' style='stroke-width: 3;'/></g>
<use xlink:href='#tick' transform='translate(5 5)' style='stroke-width: 9;'/>
<use xlink:href='#sym'/>
<circle cx='5' cy='5' r='2' style='fill: #FF0000; stroke: #f00; stroke-width: 0.05;'/>
<polyline points='0,0 5,5' style='display: none; stroke-width: 0.11;'/>
<polyline points='0,0 5,5' style='stroke-width: 0.12; stroke: none;'/>
<polyline points='0,0 5,5' style='stroke-width: 0.13;' vector-effect='non-scaling-stroke'/>
</g></svg>"""


def test_what_counts_as_a_line_in_an_svg(tmp_path):
    f = tmp_path / "plot.svg"
    f.write_text(SVGLITE)
    found = vectors.strokes(str(f), "svg", 0)
    # User units are half a point: 1.5 -> 0.75 pt; the class rule 0.2 -> 0.1 pt; 3 at half scale ->
    # 0.75 pt; the <use>s 9 -> 4.5 pt and 7 -> 3.5 pt; non-scaling 0.13 px -> 0.0975 pt. Glyph
    # outlines, hidden lines, no-stroke lines and a border in the fill's colour don't count.
    assert sorted(found) == [0.0975, 0.1, 0.75, 3.5, 4.5]
    assert found[0.75] == pytest.approx(np.array([[5, 5, 50, 5], [0, 0, 2.5, 2.5]]))
    assert found[4.5] == pytest.approx(np.array([[2.5, 2.5, 2.5, 5]]))


def test_path_data_points():
    assert vectors.path_points("M10 10 h5 v5 H0 z m1 1 l1 1") == [(10, 10), (15, 10), (15, 15), (0, 15), (11, 11), (12, 12)]
    assert vectors.path_points("M0,0C1,2,3,4,5,6s1 1 2 2") == [(0, 0), (1, 2), (3, 4), (5, 6), (6, 7), (7, 8)]
    # Arc flags may run together with the numbers after them
    assert vectors.path_points("M0 0a5 5 0 1010 0")[-1] == (10, 0)


def test_the_page_size_against_a_journal():
    doc = page_with(width=180 * MM, height=175 * MM)
    doc["pages"][0]["preset"] = {"journal": "Nature", "type": "Double column"}
    assert messages(doc) == ["The page is 175 mm tall; Nature figures can be at most 170 mm tall"]
    doc["pages"][0]["height"] = 150 * MM
    assert messages(doc) == ["The page, 180 × 150 mm, fits the Nature double column size (at most 170 mm tall)"]
    assert messages(doc, units="cm") == ["The page, 18 × 15 cm, fits the Nature double column size (at most 17 cm tall)"]
    # Another journal chosen in Check, or none
    assert messages(doc, journal="Science") == [
        "The page is 180 mm wide; Science figures are 57 mm (1 column), 121 mm (2 columns) or 184 mm (3 columns) wide"]
    assert messages(doc, journal="") == []
    doc["pages"][0]["width"] = 200 * MM
    assert messages(doc) == ["The page is 200 mm wide; the widest Nature figures are 180 mm (double column)"]
    # A page with no journal size isn't compared unless one is chosen
    del doc["pages"][0]["preset"]
    assert messages(doc) == []

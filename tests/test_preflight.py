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


def test_biorxiv_takes_any_size_within_its_text_area():
    # Any width up to 180 mm (wider than the 7 in text width prints scaled to it) and any depth up to
    # 9.5 in (a US Letter page less 0.75 in margins), with no note for a width that's neither of its
    # presets; only a bigger page is warned about
    doc = page_with(width=120 * MM, height=200 * MM)
    doc["pages"][0]["preset"] = {"journal": "bioRxiv"}
    assert messages(doc) == ["The page, 120 × 200 mm, fits bioRxiv's figures (any size up to 180 × 241.3 mm)"]
    assert messages(doc, units="in") == ["The page, 4.72 × 7.87 in, fits bioRxiv's figures (any size up to 7.09 × 9.5 in)"]
    doc["pages"][0]["width"] = 85.7 * MM
    assert messages(doc) == ["The page, 85.7 × 200 mm, fits the bioRxiv one column size (at most 241.3 mm tall)"]
    doc["pages"][0]["width"] = 180 * MM   # (Matthew's figures: Nature's double column)
    assert messages(doc) == ["The page, 180 × 200 mm, fits bioRxiv's figures (any size up to 180 × 241.3 mm); prose prints "
                             "it scaled to the 177.8 mm text width"]
    doc["pages"][0]["width"], doc["pages"][0]["height"] = 181 * MM, 250 * MM
    assert messages(doc) == ["The page is 250 mm tall; bioRxiv figures can be at most 241.3 mm tall",
                             "The page is 181 mm wide; the widest bioRxiv figures are 180 mm"]
    # The same page against Nature (fixed widths): a width in between is still noted there
    doc["pages"][0]["width"], doc["pages"][0]["height"] = 120 * MM, 150 * MM
    assert messages(doc, journal="Nature") == ["The page is 120 mm wide; Nature figures are 90 mm (single column) or 180 mm "
                                               "(double column) wide"]


# A page's text against its journal's rules (journals.py: "text" and "labels")
JOURNAL = {"name": "Test Journal", "depth_mm": 200.0, "types": [{"name": "Full", "width_mm": 180.0}], "note": "", "source": "",
           "labels": {"font": "Arial", "size": 8.0, "bold": True, "case": "upper", "form": "a"},
           "text": {"min_pt": 6.0, "max_pt": 9.0, "fonts": ["Arial", "Helvetica"], "fonts_only": True}}


def text_box(id_, t, size=6.0, font="Helvetica", bold=False, y=20, **kw):
    return {"id": id_, "type": "shape", "geom": "rect", "textbox": True, "frame": [20, y, 60, 14], "rot": 0, "stroke": None,
            "fill": None, "text": {"paragraphs": [{"align": "l", "runs": [{"t": t, "font": font, "size": size, "bold": bold}]}],
                                   "insets": [0, 0, 0, 0], "wrap": False, "anchor": "t", "autofit": "none"}, **kw}


def journal_page(*items):
    doc = page_with(*items, width=180 * MM, height=100 * MM)
    doc["pages"][0]["preset"] = {"journal": "Test Journal", "type": "Full"}
    return doc


def test_text_sizes_against_the_pages_journal(monkeypatch):
    from mosaic.export import preflight as pf
    monkeypatch.setattr(pf, "JOURNALS", [JOURNAL])
    doc = journal_page(text_box("t1", "Axis", size=5), text_box("t2", "Title", size=10, y=40),
                       text_box("la", "A", size=12, font="Arial", bold=True, y=60))
    got = messages(doc)
    assert "“Axis”: text at 5.00 pt; Test Journal asks for at least 6 pt" in got
    # The largest text leaves panel labels out: they have a size of their own
    assert "“Title”: text at 10.00 pt; Test Journal asks for at most 9 pt" in got
    assert "Panel label “A” isn't in Test Journal's style (A, B, C in bold 8 pt Arial)" in got
    # A page with a journal size is judged by its journal, not by the 5 pt smallest size for all pages
    assert not any(m.startswith("smallest text is") for m in got)
    doc["pages"][0]["items"] = [text_box("t1", "Axis", size=7), text_box("la", "(b)", size=8, font="Arial", bold=True, y=60)]
    assert [m for m in messages(doc) if "text at" in m] == []
    assert "Panel label “(b)” isn't in Test Journal's style (A, B, C in bold 8 pt Arial)" in messages(doc)
    doc["pages"][0]["items"][1]["text"]["paragraphs"][0]["runs"][0]["t"] = "B"
    assert not any("Panel label" in m for m in messages(doc))
    # Without a journal: only the smallest size for all pages
    del doc["pages"][0]["preset"]
    doc["pages"][0]["items"][0]["text"]["paragraphs"][0]["runs"][0]["size"] = 4
    assert messages(doc)[0] == "smallest text is 4.00 pt (below 5.0 pt)"


def test_fonts_against_the_pages_journal(monkeypatch, tmp_path):
    from mosaic.export import preflight as pf
    monkeypatch.setattr(pf, "JOURNALS", [JOURNAL])
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(100, 50))
    fonts = pikepdf.Dictionary()
    for key, base in (("F1", "Helvetica-Bold"), ("F2", "Times-Roman")):
        fonts[f"/{key}"] = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                                BaseFont=pikepdf.Name(f"/{base}")))
    page.obj.Resources = pikepdf.Dictionary(Font=fonts)
    page.obj.Contents = pdf.make_stream(b"BT /F1 7 Tf 10 30 Td (Wild type) Tj ET BT /F2 7 Tf 10 10 Td (Dose) Tj ET")
    pdf.save(tmp_path / "plot.pdf")
    doc = journal_page()
    place(doc, tmp_path / "plot.pdf")
    got = messages(doc)
    assert "Plot: text in Times; Test Journal accepts only Arial or Helvetica" in got
    assert not any("Helvetica;" in m for m in got)


def test_font_families_from_pdf_names():
    from mosaic.export.preflight import accepts, family
    assert family("ABCDEF+Arial-BoldMT") == "Arial"
    assert family("Helvetica-Bold") == "Helvetica"
    assert family("ArialMT") == "Arial"
    assert family("TimesNewRomanPSMT") == "TimesNewRoman"
    assert family("HelveticaNeue-Bold") == "HelveticaNeue"
    assert accepts(["Times New Roman"], "TimesNewRoman") and not accepts(["Helvetica"], "HelveticaNeue")


def test_rough_sizes_and_preferred_fonts(monkeypatch, tmp_path):
    from mosaic.export import preflight as pf
    rough = {**JOURNAL, "text": {"min_pt": 6.0, "max_pt": 8.0, "about": True, "fonts": ["Helvetica"]},
             "labels": {**JOURNAL["labels"], "measured": True}}
    monkeypatch.setattr(pf, "JOURNALS", [rough])
    doc = journal_page(text_box("t1", "Axis", size=5), text_box("la", "a", size=8, font="Arial", bold=True, y=60))
    found = {f["message"]: f["level"] for f in pf.preflight(doc, {"pages": [0]})["items"]}
    assert found["“Axis”: text at 5.00 pt; Test Journal asks for about 6–8 pt"] == "info"
    assert found["Panel label “a” isn't in Test Journal's style (A, B, C in bold 8 pt Arial as measured in its published "
                 "figures)"] == "info"
    # A rough smallest size is only a note, so mosaic's 5 pt for all pages still warns
    assert not any(m.startswith("smallest text is") for m in found)
    doc["pages"][0]["items"][0]["text"]["paragraphs"][0]["runs"][0]["size"] = 4
    found = {f["message"]: f["level"] for f in pf.preflight(doc, {"pages": [0]})["items"]}
    assert found["smallest text is 4.00 pt (below 5.0 pt)"] == "warning"
    assert found["“Axis”: text at 4.00 pt; Test Journal asks for about 6–8 pt"] == "info"


def test_horticulture_research_notes_text_under_7_pt():
    # OUP's 7 pt is a tip: a note at 5 pt, nothing more; capital bold 10 pt Arial labels
    from mosaic.export import preflight as pf
    doc = journal_page(text_box("t1", "Axis", size=5, font="Arial"), text_box("la", "A", size=10, font="Arial", bold=True, y=60))
    doc["pages"][0]["preset"] = {"journal": "Horticulture Research", "type": "Double column"}
    doc["pages"][0]["width"] = 178 * MM
    found = {f["message"]: f["level"] for f in pf.preflight(doc, {"pages": [0]})["items"]}
    assert found["“Axis”: text at 5.00 pt; Horticulture Research asks for at least 7 pt"] == "info"
    # Nothing warns (on Linux, Arial is drawn in Liberation Sans, which gets a font note of its own)
    assert [m for m, level in found.items() if level == "warning"] == []
    assert not any(m.startswith("Panel label") for m in found)


def test_plant_journal_notes_text_under_8_pt():
    # "8pt Helvetica if possible": a note at 6 pt, nothing more; (a) labels in regular 8 pt Helvetica
    from mosaic.export import preflight as pf
    doc = journal_page(text_box("t1", "Axis", size=6), text_box("la", "(a)", size=8, y=60),
                       text_box("lb", "B", size=8, bold=True, y=80))
    doc["pages"][0]["preset"] = {"journal": "The Plant Journal", "type": "Double column"}
    doc["pages"][0]["width"] = 168 * MM
    found = {f["message"]: f["level"] for f in pf.preflight(doc, {"pages": [0]})["items"]}
    assert found["“Axis”: text at 6.00 pt; The Plant Journal asks for at least 8 pt"] == "info"
    # Nothing warns (on Linux, Helvetica is drawn in a stand-in, which gets a font note of its own)
    assert [m for m, level in found.items() if level == "warning"] == []
    assert [m for m in found if m.startswith("Panel label")] == [
        "Panel label “B” isn't in The Plant Journal's style ((a), (b), (c) in 8 pt Helvetica as measured in its "
        "published figures)"]


def test_every_journal_has_label_and_text_rules_with_sources():
    from mosaic.journals import JOURNALS
    for j in JOURNALS:
        labels, text = j["labels"], j["text"]
        assert labels["case"] in ("lower", "upper") and "a" in labels["form"] and labels["size"] > 0 and labels["source"], j["name"]
        assert text["source"], j["name"]
        assert text["min_pt"] is None or text["max_pt"] is None or text["min_pt"] < text["max_pt"], j["name"]


# Line widths, resolution and export settings against the page's journal (journals.py: "lines",
# "pictures" and "export")
def photo_png(path, size=(600, 300), dpi=300, label=False):
    """A stand-in photo: smooth shading with grain; with label, a white letter drawn on it."""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:size[1], 0:size[0]]
    base = 60 + 120 * (x / size[0]) + 40 * np.sin(y / 23.0)
    a = np.clip(base[:, :, None] + rng.normal(0, 6, (size[1], size[0], 3)), 0, 255).astype(np.uint8)
    im = Image.fromarray(a, "RGB")
    if label:
        d = ImageDraw.Draw(im)
        d.rectangle([20, 20, 30, 70], fill="white")
        d.rectangle([20, 20, 60, 30], fill="white")
        d.rectangle([size[0] - 140, size[1] - 20, size[0] - 40, size[1] - 14], fill="white")
    im.save(path, dpi=(dpi, dpi))
    return path


def chart_png(path, size=(600, 300), dpi=300):
    """A stand-in plot: axes and a few bars on white."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.line([(40, 10), (40, size[1] - 30), (size[0] - 10, size[1] - 30)], fill="black", width=2)
    for i, h in enumerate((120, 200, 90, 160)):
        d.rectangle([70 + i * 120, size[1] - 30 - h, 140 + i * 120, size[1] - 31], fill=(70, 130, 180), outline="black")
    im.save(path, dpi=(dpi, dpi))
    return path


def test_the_kind_of_a_picture(tmp_path):
    from mosaic.picturekind import guess
    assert guess(str(photo_png(tmp_path / "photo.png"))) == "photo"
    assert guess(str(photo_png(tmp_path / "labelled.png", label=True))) == "combination"
    assert guess(str(chart_png(tmp_path / "chart.png"))) == "line_art"
    # A plot saved as JPEG is still line art, despite JPEG's noise round its edges
    from PIL import Image
    Image.open(tmp_path / "chart.png").save(tmp_path / "chart.jpg", quality=85)
    assert guess(str(tmp_path / "chart.jpg")) == "line_art"
    # A 16-bit microscope image is read at its full range, not clipped at 255
    Image.fromarray((np.asarray(Image.open(tmp_path / "photo.png").convert("L")).astype(np.uint16) * 200)).save(tmp_path / "deep.tif")
    assert guess(str(tmp_path / "deep.tif")) == "photo"


LINES_JOURNAL = {**JOURNAL, "lines": {"min_pt": 0.5, "max_pt": 1.5, "source": "test"},
                 "pictures": {"photo": 300.0, "combination": 500.0, "line_art": 1000.0, "source": "test"},
                 "export": {"formats": ["pdf", "eps", "tiff"], "colour": "rgb", "max_mb": 0.001, "max_dpi": 1200.0,
                            "embed_fonts": True, "no_alpha": True, "source": "test"}}


def test_line_widths_against_the_pages_journal(monkeypatch):
    from mosaic.export import preflight as pf
    monkeypatch.setattr(pf, "JOURNALS", [LINES_JOURNAL])
    doc = journal_page(line(0.25), {**line(2.0), "id": "l2", "name": "Bracket"})
    found = {f["message"]: f["level"] for f in pf.preflight(doc, {"pages": [0]})["items"]}
    assert found["Line: its line is 0.25 pt; Test Journal asks for at least 0.5 pt"] == "warning"
    # A thicker line than the journal asks for is only a note
    assert found["Bracket: its line is 2.00 pt; Test Journal asks for at most 1.5 pt"] == "info"
    # The journal's smallest width replaces mosaic's 0.25 pt for all pages
    assert not any(m.startswith("thinnest line is") for m in found)
    doc["pages"][0]["items"] = [line(0.75)]
    assert [m for m in messages(doc) if "line" in m] == []
    # Without a journal: mosaic's 0.25 pt, and no largest width
    del doc["pages"][0]["preset"]
    doc["pages"][0]["items"] = [line(0.2), {**line(3.0), "id": "l2"}]
    assert messages(doc)[0] == "thinnest line is 0.20 pt (below 0.25 pt)"
    assert not any("at most" in m for m in messages(doc))


def test_resolution_by_kind_against_the_pages_journal(monkeypatch, tmp_path):
    from mosaic.export import preflight as pf
    monkeypatch.setattr(pf, "JOURNALS", [LINES_JOURNAL])
    doc = journal_page()
    pic = place(doc, photo_png(tmp_path / "micrograph.png"))
    found = {f["message"]: f["level"] for f in pf.preflight(doc, {"pages": [0]})["items"]}
    assert found["Plot: 300 dpi at its placed size; Test Journal asks for at least 300 dpi for a photo (kind guessed from "
                 "the picture; its Picture tab can set it)"] == "ok"
    # Set by hand on the Picture tab: no longer a guess
    pic["picture_kind"] = "line_art"
    found = {f["message"]: f["level"] for f in pf.preflight(doc, {"pages": [0]})["items"]}
    assert found["Plot: 300 dpi at its placed size; Test Journal asks for at least 1000 dpi for line art"] == "warning"
    del pic["picture_kind"]
    doc["pages"][0]["items"] = []
    place(doc, chart_png(tmp_path / "chart.png"), scale=0.25)   # 1200 dpi placed at a quarter of its size
    assert "Plot: 1200 dpi at its placed size; Test Journal asks for at least 1000 dpi for line art (kind guessed from " \
           "the picture; its Picture tab can set it)" in messages(doc)
    # A journal that wants line art as vector files, not pictures
    monkeypatch.setattr(pf, "JOURNALS", [{**LINES_JOURNAL, "pictures": {"photo": 300.0, "vector": ["line_art", "combination"],
                                                                          "source": "test"}}])
    assert "Plot: 1200 dpi at its placed size; Test Journal asks for line art as vector files (PDF, EPS or SVG), not " \
           "pictures (kind guessed from the picture; its Picture tab can set it)" in messages(doc)
    doc["pages"][0]["items"][0]["picture_kind"] = "combination"
    assert "Plot: 1200 dpi at its placed size; Test Journal asks for text and lines over photos to stay editable, not " \
           "drawn into the picture (add them in mosaic)" in messages(doc)
    # Without a journal: mosaic's 300 dpi, whatever the kind
    del doc["pages"][0]["preset"]
    assert "Plot: 1200 dpi at its placed size" in messages(doc)


def test_export_settings_against_the_pages_journal(monkeypatch, tmp_path):
    from mosaic.export import preflight as pf
    monkeypatch.setattr(pf, "JOURNALS", [LINES_JOURNAL])
    doc = journal_page(text_box("t1", "Axis", size=7))
    settings = {"formats": ["pdf", "png", "tiff"], "dpi": 600, "cmyk": False, "embed_fonts": True, "transparent": False,
                "pages": [0]}
    found = {f["message"]: f["level"] for f in pf.export_check(doc, settings)}
    assert found == {"Test Journal takes PDF, EPS or TIFF files in RGB colour, at most 0.001 MB each": "info",
                     "Test Journal doesn't take PNG files for final figures": "warning",
                     # A page of text and drawings is line art as a picture
                     "TIFF at 600 dpi: Test Journal asks for at least 1000 dpi for line art": "warning"}
    # With a photo on it, the page is a photo with text or lines
    place(doc, photo_png(tmp_path / "micrograph.png"))
    assert "TIFF at 600 dpi: Test Journal asks for at least 500 dpi for a photo with text or lines" not in \
        [f["message"] for f in pf.export_check(doc, settings)]
    got = [f["message"] for f in pf.export_check(doc, {**settings, "dpi": 400})]
    assert "TIFF at 400 dpi: Test Journal asks for at least 500 dpi for a photo with text or lines" in got
    got = [f["message"] for f in pf.export_check(doc, {**settings, "dpi": 2400, "cmyk": True, "embed_fonts": False,
                                                       "transparent": True})]
    assert "TIFF at 2400 dpi: Test Journal takes at most 1200 dpi" in got
    assert "CMYK colour is ticked; Test Journal asks for RGB" in got
    assert "Fonts left out of placed PDFs won't be embedded; Test Journal asks for embedded fonts" in got
    assert "Test Journal takes no transparency (alpha channels): set Background to White" in got
    # Pages without a journal aren't checked; written files bigger than the journal takes are
    (tmp_path / "fig.tif").write_bytes(b"x" * 5000)
    assert pf.size_limits(doc, [0], [str(tmp_path / "fig.tif")]) == (
        ["fig.tif is 0.0 MB; Test Journal takes files of at most 0.001 MB"], [])
    # A limit asked "where possible" is a note
    LINES_JOURNAL["export"]["firm"] = False
    assert pf.size_limits(doc, [0], [str(tmp_path / "fig.tif")]) == (
        [], ["fig.tif is 0.0 MB; Test Journal asks for files under 0.001 MB where possible"])
    del LINES_JOURNAL["export"]["firm"]
    del doc["pages"][0]["preset"]
    assert pf.export_check(doc, settings) == [] and pf.size_limits(doc, [0], [str(tmp_path / "fig.tif")]) == ([], [])


def test_every_journal_has_line_picture_and_export_rules_with_sources():
    from mosaic.export.preflight import COLOUR_NAMES, FORMAT_NAMES
    from mosaic.journals import JOURNALS
    for j in JOURNALS:
        lines, pictures, export = j["lines"], j["pictures"], j["export"]
        assert lines["source"] and pictures["source"] and export["source"], j["name"]
        assert lines["min_pt"] is None or lines["max_pt"] is None or lines["min_pt"] < lines["max_pt"], j["name"]
        # Every kind of picture has a resolution, or the journal wants it as vector artwork
        assert all(pictures[k] or k in pictures["vector"] for k in ("photo", "combination", "line_art")), j["name"]
        assert export["formats"] and set(export["formats"]) <= set(FORMAT_NAMES) and export["colour"] in COLOUR_NAMES, j["name"]


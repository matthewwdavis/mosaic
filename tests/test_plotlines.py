"""What a placed plot offers to snap to (vectors.plot_lines): its axis and frame lines, not tick
marks, data or grid lines, and the box round its ink."""
import pikepdf
import pytest

from mosaic import vectors
from mosaic.app.api import Api


def pdf_file(path, content: bytes, size=(200, 100)):
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=size)
    page.obj.Contents = pdf.make_stream(content)
    pdf.save(path)
    return str(path)


def test_axis_and_frame_lines_in_a_pdf(tmp_path):
    # PDF y runs up: on a 200 x 100 page, y = 80 is 20 from the top
    f = pdf_file(tmp_path / "plot.pdf", b" ".join([
        b"1 1 1 rg 0 0 200 100 re f",                         # white background over the whole page
        b"0 0 0 RG 0.5 w 20 20 m 20 95 l S 20 20 m 190 20 l S",   # the axes: x = 20 and y = 80 from the top
        b"20 20 m 20 17 l S 60 20 m 60 17 l S",               # tick marks
        b"100 30 m 100 60 l S",                               # an error bar, under half the y axis
        b"0.92 G 20 50 m 190 50 l S",                         # a light grid line
        b"0 G 120 20 8 50 re S",                              # a bar's outline, narrow
        b"0.9 0.9 0.9 rg 30 25 150 60 re f",                  # a grey panel background
    ]))
    found = vectors.plot_lines(f, "pdf", 0)
    assert found["size"] == [200.0, 100.0]
    lines = {tuple(line) for line in found["lines"]}
    assert (0, 20.0, 5.0, 80.0) in lines and (1, 80.0, 20.0, 190.0) in lines
    # The panel background's four sides
    assert {(0, 30.0, 15.0, 75.0), (0, 180.0, 15.0, 75.0), (1, 15.0, 30.0, 180.0), (1, 75.0, 30.0, 180.0)} <= lines
    assert len(lines) == 6
    # Ink: anything not white
    assert found["ink"] == pytest.approx([19.75, 5.0, 190.25, 83.25], abs=0.3)


def test_a_frame_drawn_as_a_rectangle_and_a_blank_page(tmp_path):
    f = pdf_file(tmp_path / "frame.pdf", b"0 G 1 w 10 10 180 80 re S")
    assert {tuple(line) for line in vectors.plot_lines(f, "pdf", 0)["lines"]} == {
        (0, 10.0, 10.0, 90.0), (0, 190.0, 10.0, 90.0), (1, 10.0, 10.0, 190.0), (1, 90.0, 10.0, 190.0)}
    blank = pdf_file(tmp_path / "blank.pdf", b"1 1 1 rg 0 0 200 100 re f")
    assert vectors.plot_lines(blank, "pdf", 0) == {"lines": [], "ink": None, "size": [200.0, 100.0]}


def test_axis_lines_in_an_svg_from_svglite(tmp_path):
    f = tmp_path / "plot.svg"
    f.write_text("""<svg xmlns='http://www.w3.org/2000/svg' width='200pt' height='100pt' viewBox='0 0 200 100'>
<g class='svglite'><defs><style type='text/css'><![CDATA[
  .svglite line, .svglite polyline, .svglite path, .svglite rect { fill: none; stroke: #000000; }
]]></style></defs>
<rect width='100%' height='100%' style='stroke: none; fill: #FFFFFF;'/>
<polyline points='20,5 20,80' style='stroke-width: 1.07;'/>
<polyline points='20,80 190,80' style='stroke-width: 1.07;'/>
<polyline points='60,80 60,83' style='stroke-width: 1.07;'/>
<polyline points='20,50 190,50' style='stroke-width: 0.53; stroke: #EBEBEB;'/>
</g></svg>""")
    found = vectors.plot_lines(str(f), "svg", 0)
    assert [tuple(line) for line in found["lines"]] == [(0, 20.0, 5.0, 80.0), (1, 80.0, 20.0, 190.0)]


def test_the_api_offers_nothing_for_a_photo():
    assert Api().plot_lines({"variants": {"png": {"sha256": "0" * 64}}}, 0) is None

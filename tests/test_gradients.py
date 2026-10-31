"""Gradient fills: linear and radial, through the engine, both writers and the PowerPoint importer."""
import math
import os

import pikepdf
from lxml import etree

from figassemble.export.run import export_document
from figassemble.geometry import Matrix, make_gradient
from figassemble.importers.drawingml import ColorContext, Theme, parse_fill

TWO = [{"pos": 0, "color": "#1f3a93", "opacity": 1}, {"pos": 1, "color": "#ffd166", "opacity": 0.5}]


def test_radial_reaches_the_farthest_corner():
    g = make_gradient({"type": "radial", "stops": TWO}, 200, 100, Matrix.translate(10, 20))
    assert g.kind == "radial" and g.p0 == (0.5, 0.5) and math.isclose(g.radius, math.sqrt(0.5))
    corner = make_gradient({"type": "radial", "center": [0, 0], "stops": TWO}, 200, 100, Matrix())
    assert math.isclose(corner.radius, math.sqrt(2))
    # Its space is the shape's box: the centre lands in the middle of the 200 x 100 box at (10, 20)
    assert g.matrix.apply(0.5, 0.5) == (110.0, 70.0)
    assert make_gradient({"type": "linear", "angle": 0, "stops": TWO}, 200, 100, Matrix()).kind == "linear"


def test_radial_gradient_in_svg_and_pdf(tmp_path):
    from figassemble.app.api import Api
    doc = Api().new_document()
    doc["pages"][0]["items"] = [{"id": "e", "type": "shape", "geom": "ellipse", "frame": [20, 20, 120, 60], "rot": 0,
                                 "stroke": None, "fill": {"color": "#1f3a93", "opacity": 1,
                                                          "gradient": {"type": "radial", "center": [0, 0], "stops": TWO}}}]
    export_document(doc, str(tmp_path / "g"), ["svg", "pdf"])
    svg = etree.parse(str(tmp_path / "g.svg"))
    rg = svg.findall(".//{http://www.w3.org/2000/svg}radialGradient")
    assert len(rg) == 1 and rg[0].get("cx") == "0" and math.isclose(float(rg[0].get("r")), math.sqrt(2), rel_tol=1e-5)
    offsets = [s.get("offset") for s in rg[0]]
    assert offsets == ["0", "1"] and "stop-opacity:0.5" in rg[0][1].get("style")
    pdf = pikepdf.open(str(tmp_path / "g.pdf"))
    shadings = [sh for name, sh in pdf.pages[0].Resources.Shading.items()]
    assert [int(sh.ShadingType) for sh in shadings] == [3]
    assert [float(v) for v in shadings[0].Coords][:3] == [0.0, 0.0, 0.0]
    # The see-through stop makes a soft mask, itself a radial shading
    assert pdf.pages[0].Resources.ExtGState


def fill_xml(inner):
    return etree.fromstring(f'<a:spPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{inner}</a:spPr>')


def test_powerpoint_radial_gradient_imports_as_radial():
    stops = ('<a:gsLst><a:gs pos="0"><a:srgbClr val="1F3A93"/></a:gs>'
             '<a:gs pos="100000"><a:srgbClr val="FFD166"><a:alpha val="50000"/></a:srgbClr></a:gs></a:gsLst>')
    colors = ColorContext(Theme())
    # "From the centre": the focus rectangle is inset 50% from every side
    fill, notes = parse_fill(fill_xml(f'<a:gradFill>{stops}<a:path path="circle"><a:fillToRect l="50000" t="50000" '
                                      'r="50000" b="50000"/></a:path></a:gradFill>'), colors)
    assert fill["gradient"]["type"] == "radial" and fill["gradient"]["center"] == [0.5, 0.5] and not notes
    # The stops keep the transparency; the fill itself is opaque, so it isn't applied twice
    assert fill["opacity"] == 1.0 and fill["gradient"]["stops"][1]["opacity"] == 0.5
    # "From the top left corner": the focus rectangle is that corner
    fill, _ = parse_fill(fill_xml(f'<a:gradFill>{stops}<a:path path="circle"><a:fillToRect r="100000" b="100000"/>'
                                  '</a:path></a:gradFill>'), colors)
    assert fill["gradient"]["center"] == [0.0, 0.0]
    fill, notes = parse_fill(fill_xml(f'<a:gradFill>{stops}<a:path path="rect"/></a:gradFill>'), colors)
    assert fill["gradient"]["type"] == "radial" and notes

"""Equations: maths drawn by matplotlib as a PDF and an SVG of one size, with real text (the PDF's
fonts embedded), the ink just inside the top left, and a plain reason when the maths is wrong."""
import os
import shutil

import numpy as np
import pikepdf
import pypdfium2 as pdfium
from lxml import etree

from figassemble import equations
from figassemble.app.api import Api
from figassemble.assets import probe


def ink_box(pdf):
    doc = pdfium.PdfDocument(pdf)
    try:
        page = doc[0]
        a = np.asarray(page.render(scale=10, fill_color=(0, 0, 0, 0)).to_pil().convert("RGBA"))[:, :, 3] > 0
        text = page.get_textpage().get_text_range()
    finally:
        doc.close()
    rows, cols = np.flatnonzero(a.any(axis=1)), np.flatnonzero(a.any(axis=0))
    return [cols[0] / 10, rows[0] / 10, (cols[-1] + 1) / 10, (rows[-1] + 1) / 10], text


def test_real_text_in_both_copies_of_one_size():
    for font in ("figure", "cm"):
        pdf, svg = equations.render(r"y = \alpha e^{-kt} + \sum_{i=1}^{n} x_i^2", 6, font)
        try:
            with pikepdf.open(pdf) as doc:
                page = doc.pages[0]
                size = [float(v) for v in page.MediaBox][2:]
                fonts = list(page.Resources.Font.values())
                assert fonts and all(f.get("/Subtype") == "/Type0" or f.get("/FontDescriptor") is not None for f in fonts)
            assert probe(svg)["size_pt"] == size and all(v == int(v) for v in size)
            assert etree.parse(svg).findall(".//{http://www.w3.org/2000/svg}text"), font
            (x0, y0, x1, y1), text = ink_box(pdf)
            # Nothing cut off, the ink 0.2 pt in from the top left, and the letters searchable
            assert abs(x0 - 0.2) < 0.11 and abs(y0 - 0.2) < 0.11 and x1 <= size[0] and y1 <= size[1], (font, x0, y0)
            assert "y" in text and "k" in text, (font, text)
        finally:
            shutil.rmtree(os.path.dirname(pdf), ignore_errors=True)


def test_limits_above_a_sum_arent_cut_off():
    pdf, _ = equations.render(r"\sum_{i=1}^{n}", 6, "figure")
    try:
        (_, y0, _, _), _ = ink_box(pdf)
        assert y0 >= 0.1   # mathtext's own box falls short of the n in Helvetica
    finally:
        shutil.rmtree(os.path.dirname(pdf), ignore_errors=True)


def test_the_api_stores_both_copies_or_says_why_not():
    res = Api().make_equation({"tex": r"\mathrm{OD}_{600}", "size": 6, "color": "#0000ff"})
    asset = res["asset"]
    assert set(asset["variants"]) == {"pdf", "svg"} and asset["name"].startswith("Equation")
    assert not any(v.get("src") for v in asset["variants"].values())   # kept in the figure, not linked
    assert Api().make_equation({"tex": r"\frac{a}{"}) == {"error": r"expected \frac{num}{den} but found '{', at character 6"}
    assert Api().make_equation({"tex": "  "}) == {"error": "type some maths first"}
    assert equations.check_tex(r"\foo") == r"Unknown symbol: \foo"

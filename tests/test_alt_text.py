"""A page's description (alt text, the Page panel's Description): what the figure shows, in
words. It's saved in the document, written into the SVG and PDF exports, and given to other
programs by `mosaic info --json` and `mosaic export --json` (prose puts it in its accessible PDF)."""
import io
import json

import pikepdf

from mosaic import cli, docfile, model
from mosaic.export.run import export_document

ALT = "Bar chart: treated plants are 30% taller than controls at day 14 <n = 12>."


def described():
    doc = model.new_document("Fig 1")
    doc["pages"][0]["alt"] = ALT
    doc["pages"][0]["items"].append({"id": "r1", "type": "shape", "geom": "rect", "frame": [10, 10, 50, 30], "rot": 0,
                                     "flip_h": False, "flip_v": False, "fill": {"color": "#56b4e9", "opacity": 1}, "stroke": None})
    return doc


def test_the_description_goes_into_the_svg_and_the_pdf(tmp_path):
    files = export_document(described(), str(tmp_path / "fig"), ["svg", "pdf"])["files"]
    svg = open([f for f in files if f.endswith(".svg")][0], encoding="utf-8").read()
    assert 'role="img"' in svg and "<title>Page 1</title>" in svg
    assert "<desc>Bar chart: treated plants are 30% taller than controls at day 14 &lt;n = 12&gt;.</desc>" in svg
    with pikepdf.open([f for f in files if f.endswith(".pdf")][0]) as pdf:
        assert str(pdf.docinfo["/Subject"]) == ALT


def test_a_figure_without_one_exports_as_before(tmp_path):
    doc = described()
    del doc["pages"][0]["alt"]
    files = export_document(doc, str(tmp_path / "fig"), ["svg", "pdf"])["files"]
    svg = open([f for f in files if f.endswith(".svg")][0], encoding="utf-8").read()
    assert "<desc>" not in svg and "<title>" not in svg and "role=" not in svg
    with pikepdf.open([f for f in files if f.endswith(".pdf")][0]) as pdf:
        assert "/Subject" not in pdf.docinfo


def test_other_programs_read_it_from_the_command_line(tmp_path, capsys):
    path = str(tmp_path / "fig.mosaic")
    doc = described()
    doc["pages"].append(model.new_page("Page 2"))
    docfile.save(doc, path)
    assert cli.main(["info", path, "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["title"] == "Fig 1" and [p["alt"] for p in info["pages"]] == [ALT, ""]
    assert info["pages"][0]["number"] == 1 and info["pages"][0]["objects"] == 1
    assert cli.main(["export", path, "-f", "svg", "--pages", "1", "--json", "-o", str(tmp_path / "out")]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["pages"] == [{"name": "Page 1", "alt": ALT}] and len(got["files"]) == 1

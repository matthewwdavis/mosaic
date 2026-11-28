"""One figure holding every kind of object and option the editor makes, exported in every format.

Each format's own tests use a few objects made for them; real figures reach code those never do
(11-27: a dotted line under 3 pt across, an SVG holding a photo over 10 MB, a text box's line
spacing and CMYK PDF's colour profile each stopped an export of finished figures). Any option
added to the editor belongs in this figure too.
"""
import io
import zipfile

import pikepdf
import pytest
from lxml import etree
from PIL import Image
from pptx import Presentation

from mosaic import assets, model, regions
from mosaic.export.run import export_document
from mosaic.importers.pptx import import_pptx

FORMATS = ["pdf", "svg", "png", "tiff", "jpeg", "eps", "pptx"]


def stroke(**kw):
    return {"color": "#2b6cb0", "width": 1.0, "dash": "solid", "cap": "round", "join": "round", "opacity": 1, **kw}


def run(t, **kw):
    return {"t": t, "font": "Helvetica", "size": 6, "bold": False, "italic": False, "color": "#000000", **kw}


def textbox(id, frame, paragraphs, **kw):
    return {"id": id, "type": "shape", "geom": "rect", "textbox": True, "frame": frame, "rot": 0, "stroke": None, "fill": None,
            "text": {"paragraphs": paragraphs, "insets": [1, 1, 1, 1], "wrap": True, "anchor": "t", "autofit": "none"} | kw}


def line(id, points, **kw):
    return {"id": id, "type": "line", "points": points, "stroke": stroke(), "arrow_start": None, "arrow_end": None, **kw}


def shape(id, geom, frame, **kw):
    return {"id": id, "type": "shape", "geom": geom, "frame": frame, "rot": 0, "stroke": stroke(), "fill": {"color": "#e69f00"}, **kw}


SYMBOL = {"id": "sym1", "name": "Cell", "size": [40.0, 20.0], "items": [
    shape("sbox", "rect", [0, 0, 40, 20]),
    textbox("stxt", [4, 4, 30, 10], [{"align": "l", "runs": [run("A")]}]),
]}


def every_object_document(fixtures, cache):
    doc = model.new_document("everything")
    doc["symbols"] = [SYMBOL]
    doc["swatches"] = [{"id": "sw1", "name": "Blue", "color": "#0072b2"}]
    doc["text_styles"] = [{"id": "ts1", "name": "Panel label", "font": "Helvetica", "size": 8, "bold": True, "italic": False,
                           "underline": False, "color": "#000000", "swatch": None, "align": "l", "line_spacing": {"pct": 0.9},
                           "space_before": 0, "space_after": 2}]
    ids = {}
    for kind in ("pdf", "svg", "png", "jpg", "rgba"):
        aid, asset, _ = assets.new_asset(fixtures[kind], cache)
        doc["assets"][aid] = asset
        ids[kind] = aid
    pic = lambda kind, x, y, **kw: model.picture_item(ids[kind], doc["assets"][ids[kind]], x, y) | kw   # noqa: E731

    page = doc["pages"][0]
    page["width"], page["height"], page["background"] = 400.0, 300.0, "#ffffff"
    tri = [line("ta", [[20, 290], [60, 230]]), line("tb", [[60, 230], [100, 290]]), line("tc", [[100, 290], [20, 290]])]
    found = regions.area_at(tri, [60, 270])
    page["items"] = [
        # Pictures: placed PDF (cropped, turned, faded, with a scale), SVG (flipped), PNG drawn as PNG,
        # a JPEG cropped to an ellipse with a border, a transparent PNG with a dashed border and an
        # outline, one cropped to a shape drawn over it
        pic("pdf", 10, 10, crop=[0.1, 0, 0, 0.2], rot=10, opacity=0.5, scale={"per_pt": 1.0, "unit": "µm", "how": "typed"},
            name="Placed PDF"),
        pic("svg", 120, 10, flip_h=True),
        pic("png", 230, 10, source="png"),
        pic("jpg", 10, 70, mask={"geom": "ellipse"}, border={"color": "#ff0000", "width": 1}),
        pic("rgba", 80, 70, border={"color": "#000000", "width": 0.5, "dash": "dash"}, outline={"color": "#ffffff", "width": 1}),
        pic("pdf", 130, 70, mask={"geom": "custom", "path": {"subpaths": [{"w": 100, "h": 100, "cmds": [
            ["M", 50, 0], ["L", 100, 100], ["L", 0, 100], ["Z"]]}]}}),
        # Scale bars and brackets (a plain label, and a rich one with an italic P)
        {"id": "sb", "type": "scalebar", "frame": [240, 70, 40, 11.2], "length": 50, "unit": "µm", "thickness": 2,
         "size": 6, "label": "above", "color": "#000000"},
        {"id": "sb2", "type": "scalebar", "frame": [290, 70, 60, 8], "length": 20, "unit": "mm", "thickness": 1.5, "size": 5,
         "label": "right", "color": "#000000", "ends": "round", "gap": 1, "outline": {"color": "#ffffff", "width": 1}},
        {"id": "br", "type": "bracket", "frame": [240, 90, 60, 13], "label": "**", "size": 6, "dir": "up", "tick": 3,
         "stroke": {"color": "#000000", "width": 0.5}},
        {"id": "br2", "type": "bracket", "frame": [310, 90, 15, 40], "label": "P < 0.05", "size": 5, "dir": "right",
         "stroke": {"color": "#0072b2", "width": 0.75},
         "text": {"paragraphs": [{"runs": [{"t": "P", "italic": True}, {"t": " < 0.05"}]}]}},
        # Shapes: ready-made with adjustments and rounding, gradients, a freeform with every kind of
        # segment, a fill to its line's inner edge, an outline inside, a dashed one
        shape("star", "star5", [10, 130, 40, 40], rot=20, adj={"adj": 0.3}),
        shape("round", "rect", [60, 130, 50, 30], rounding=0.5, fill={"color": "#56b4e9", "swatch": "sw1"}),
        shape("lin", "ellipse", [120, 130, 40, 30], fill={"color": "#1f3a93", "opacity": 0.8, "gradient": {
            "type": "linear", "angle": 45, "stops": [{"pos": 0, "color": "#ffffff"}, {"pos": 1, "color": "#000000", "opacity": 0.5}]}}),
        shape("rad", "rect", [170, 130, 40, 30], stroke=None, fill={"color": "#1f3a93", "gradient": {
            "type": "radial", "center": [0.3, 0.3], "stops": [{"pos": 0, "color": "#ffffff"}, {"pos": 1, "color": "#cc79a7"}]}}),
        shape("free", "custom", [220, 130, 50, 40], path={"subpaths": [{"w": 50, "h": 40, "cmds": [
            ["M", 0, 40], ["L", 10, 0], ["C", 20, 0, 30, 10, 30, 20], ["Q", 40, 30, 50, 20], ["L", 50, 40], ["Z"]]}]}),
        shape("reach", "rect", [280, 140, 30, 20], fill_reach="inner", stroke=stroke(width=3, dash="dash", opacity=0.6)),
        shape("inside", "ellipse", [320, 140, 30, 20], outline={"color": "#ffffff", "width": 1, "opacity": 1, "type": "inside"}),
        shape("dashed", "rect", [360, 140, 30, 20], fill=None, stroke=stroke(dash="sysDot", cap="flat")),
        # Text: paragraphs with every format, a text style, line spacing as a multiple and in points,
        # space before and after, super- and subscripts, underline, kerning, line breaks
        textbox("text", [10, 180, 150, 50], [
            {"align": "l", "style": "ts1", "line_spacing": {"pct": 0.9}, "space_after": 2,
             "runs": [run("a", size=8, bold=True)]},
            {"align": "ctr", "line_spacing": {"pts": 7.5}, "space_before": 1.5,
             "runs": [run("x"), run("2", baseline=0.3), run(" CO"), run("2", baseline=-0.25), run(" under", underline=True),
                      run(" AV kerned", kern=True), run("\nnext line\vand a soft break", italic=True, color="#d55e00")]},
            {"align": "r", "runs": [run("right")]},
            {"align": "just", "end_size": 7, "runs": []},
        ], anchor="ctr"),
        textbox("fit", [170, 180, 60, 10], [{"align": "l", "runs": [run("autofit, no wrap")]}], wrap=False, autofit="shape",
                anchor="b"),
        # Pasted text can carry control characters (Word's line break is a vertical tab); an SVG
        # can't hold them, and lxml refused the whole text box (11-27)
        textbox("ctrl", [170, 195, 60, 20], [{"align": "l", "runs": [run("bell\x07 null\x00 cr\r\nend")]}]),
        # Lines: a straight arrow, a bent line with a repeated point, a smooth curve, PowerPoint's
        # ends and mosaic's own sizes and rounding, dashes as PowerPoint spaces them, a custom dash,
        # closer dashes, outlines of every kind
        line("arrow", [[240, 185], [300, 185]], arrow_end={"type": "triangle", "w": "sm", "len": "sm"}),
        line("bent", [[240, 195], [260, 205], [260, 205], [300, 195]], arrow_start={"type": "oval", "w": "lg", "len": "lg"},
             arrow_end={"type": "stealth", "w": "med", "len": "med"}),
        line("smooth", [[310, 185], [330, 205], [350, 185], [370, 205]], curve="smooth",
             arrow_end={"type": "diamond", "w": "med", "len": "med"}),
        line("xs", [[240, 215], [300, 215]], arrow_end={"type": "arrow", "w": "xs", "len": "xl"}),
        line("rounded", [[310, 215], [370, 215]], arrow_end={"type": "triangle", "w": "med", "len": "med", "rounding": 0.5}),
        line("pptdash", [[240, 225], [300, 225]], stroke=stroke(dash="dash", even_dashes=False)),
        line("custdash", [[310, 225], [370, 225]], stroke=stroke(dash=[3, 1, 1, 1], even_dashes=False)),
        line("close", [[240, 235], [300, 235]], stroke=stroke(dash="lgDash", even_dashes=False, dash_spacing=0.5)),
        line("thin", [[380, 180], [380, 260]], stroke=stroke(dash="sysDot", width=0.25)),
        line("o1", [[240, 245], [300, 245]], outline={"color": "#ffffff", "width": 1, "type": "outside"}),
        line("o2", [[310, 245], [370, 245]], stroke=stroke(dash="dash"), outline={"color": "#000000", "width": 0.5, "type": "both_filled"}),
        line("o3", [[240, 255], [300, 255]], stroke=stroke(dash="dash"),
             outline={"color": "#000000", "width": 0.5, "opacity": 0.5, "type": "outside_gaps"}),
        # An area fill between three lines, groups (one turned, one a clipping mask), a symbol's copy
        {"id": "fillr", "type": "shape", "geom": "region", "region": {"items": found["items"], "seed": found["seed"]},
         "frame": found["frame"], "rot": 0, "stroke": None, "fill": {"color": "#ffd166", "opacity": 1}},
        *tri,
        {"id": "grp", "type": "group", "rot": 15, "items": [shape("g1", "rect", [120, 240, 20, 20]),
                                                           line("g2", [[120, 270], [150, 270]])]},
        {"id": "clip", "type": "group", "clip": True, "items": [shape("c1", "rect", [160, 240, 40, 40], fill={"color": "#ff0000"}),
                                                               shape("c2", "ellipse", [165, 245, 30, 30])]},
        {"id": "copy", "type": "symbol", "symbol": "sym1", "frame": [210, 260, 40, 20], "rot": 0, "flip_h": False, "flip_v": False},
        # Hidden, and parked off the page: in no export
        shape("hidden", "rect", [300, 270, 20, 20], hidden=True),
        shape("parked", "rect", [-100, 10, 20, 20]),
    ]
    # A second, smaller page with no background
    second = model.new_page("Page 2", 200.0, 100.0)
    second["background"] = None
    second["items"] = [textbox("t2", [10, 10, 100, 20], [{"align": "l", "runs": [run("Second page")]}]),
                       line("l2", [[10, 50], [150, 50]], arrow_end={"type": "triangle", "w": "med", "len": "med"})]
    doc["pages"].append(second)
    assert model.validate(doc) == []
    return doc


def test_every_object_exports_in_every_format(fixtures, cache, tmp_path):
    doc = every_object_document(fixtures, cache)
    res = export_document(doc, str(tmp_path / "every"), FORMATS, dpi=72, cache=cache)
    files = res["files"]
    assert not [w for w in res["warnings"] if w.startswith("item ")], res["warnings"]   # (an object a writer left out)
    for ext in ("pdf", "pptx"):
        assert str(tmp_path / f"every.{ext}") in files
    for ext in ("svg", "png", "tif", "jpg", "eps"):
        assert sum(f.endswith("." + ext) for f in files) == 2, (ext, files)
    assert all((tmp_path / f).stat().st_size > 0 for f in files)
    with pikepdf.open(tmp_path / "every.pdf") as pdf:
        assert len(pdf.pages) == 2
    for f in files:
        if f.endswith(".svg"):
            etree.parse(f)
        elif f.endswith((".png", ".tif", ".jpg")):
            with Image.open(f) as im:
                assert im.size in ((400, 300), (200, 100)), (f, im.size)
        elif f.endswith(".eps"):
            assert open(f, "rb").read(4) == b"%!PS"
    prs = Presentation(str(tmp_path / "every.pptx"))
    assert len(prs.slides) == 2 and len(prs.slides[0].shapes) > 30
    slide = zipfile.ZipFile(tmp_path / "every.pptx").read("ppt/slides/slide1.xml").decode()
    assert '<a:spcPct val="90000"/>' in slide and '<a:spcPts val="750"/>' in slide
    back, _ = import_pptx(str(tmp_path / "every.pptx"), cache=cache)   # PowerPoint's file reads back
    assert len(back["pages"]) == 2


def test_every_object_exports_as_a_cmyk_pdf(fixtures, cache, tmp_path):
    """Ghostscript runs with -dSAFER, which reads only its own files and the ones it's given: the
    colour profile (the system's, when Ghostscript has none of its own as a file) stopped every
    CMYK export (11-27)."""
    from mosaic.export.raster import default_cmyk_profile
    if not default_cmyk_profile():
        pytest.skip("no CMYK colour profile on this computer")
    doc = every_object_document(fixtures, cache)
    export_document(doc, str(tmp_path / "cmyk"), ["pdf"], cmyk=True, cache=cache)
    with pikepdf.open(tmp_path / "cmyk.pdf") as pdf:
        assert len(pdf.pages) == 2
        content = b"".join(page.Contents.read_bytes() if not isinstance(page.Contents, pikepdf.Array)
                           else b"".join(c.read_bytes() for c in page.Contents) for page in pdf.pages)
    assert b" rg" not in content and b" RG" not in content   # no RGB colours left on the pages themselves


def test_a_profile_outside_ghostscripts_folders_is_read(tmp_path):
    """A profile anywhere (a folder with a space in its name, like /System/Library/ColorSync/Profiles/Generic CMYK Profile.icc)."""
    import shutil

    from mosaic.export.postscript import pdf_to_cmyk
    from mosaic.export.raster import default_cmyk_profile
    if not default_cmyk_profile():
        pytest.skip("no CMYK colour profile on this computer")
    folder = tmp_path / "Colour profiles"
    folder.mkdir()
    profile = folder / "My CMYK.icc"
    shutil.copyfile(default_cmyk_profile(), profile)
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(100, 50))
    page.obj.Contents = pdf.make_stream(b"1 0 0 rg 10 10 30 20 re f")
    buf = io.BytesIO()
    pdf.save(buf)
    with pikepdf.open(io.BytesIO(pdf_to_cmyk(buf.getvalue(), str(profile)))) as out:
        assert len(out.pages) == 1


def test_ghostscripts_own_words_say_why_it_stopped():
    from mosaic.export.postscript import GhostscriptError
    said = ("Error: /undefined in --runpdf--\nOperand stack:\n   --nostringval--   3   0   --nostringval--   (   **** Error: x\\n)\n"
            "Last OS error: Permission denied\nGPL Ghostscript 10.08.0: Unrecoverable error, exit code 1\n")
    msg = str(GhostscriptError("CMYK PDF", 1, ["gs"], said))
    assert msg.startswith("Ghostscript couldn't make the CMYK PDF (exit 1): ") and "Permission denied" in msg
    assert "nostringval" not in msg


def test_a_failed_export_writes_its_whole_error_in_the_log(capsys, monkeypatch):
    """The editor shows a failed export's last line; the log (what mosaic writes to stderr) has all
    of it, with what a program it ran said."""
    import subprocess

    from mosaic.app.api import Api
    from mosaic.export import run as export_run

    def broken(*a, **kw):
        raise subprocess.CalledProcessError(1, ["rsvg-convert", "in.svg"], stderr=b"librsvg: value too large")
    monkeypatch.setattr(export_run, "export_document", broken)
    with pytest.raises(subprocess.CalledProcessError):
        Api().export({"pages": [], "assets": {}}, {"base": "/nowhere/x", "formats": ["pdf"]})
    err = capsys.readouterr().err
    assert "---- Export failed" in err and "Traceback" in err and "librsvg: value too large" in err

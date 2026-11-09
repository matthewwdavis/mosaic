"""Kerning: letter pairs set as the font's kerning says, for runs that ask for it (text made in
mosaic since 2026-11-09, text from PowerPoint as each run's setting says); text without it keeps
its spacing, and exports place kerned letters where the layout put them."""
import zipfile

import pytest
from pptx import Presentation
from pptx.util import Pt

from mosaic import model, plottext
from mosaic.export.run import export_document
from mosaic.fonts import resolve_face
from mosaic.importers.pptx import import_pptx
from mosaic.textlayout import layout_text

WORDS = "AVATAR To Ty"


def box(t, kern, size=8.0, y=20):
    run = {"t": t, "font": "Helvetica", "size": size, "bold": False, "italic": False, "color": "#000000"}
    if kern is not None:
        run["kern"] = kern
    return {"id": f"t{y}", "type": "shape", "geom": "rect", "textbox": True, "frame": [20, y, 150, 14], "rot": 0,
            "stroke": None, "fill": None,
            "text": {"paragraphs": [{"align": "l", "runs": [run]}], "insets": [0, 0, 0, 0], "wrap": False,
                     "anchor": "t", "autofit": "none"}}


def width(kern):
    return sum(r.width for r in layout_text(box(WORDS, kern)["text"], 150, 14).runs)


def test_the_fonts_own_kerning():
    face = resolve_face("Helvetica")[0]   # (Arial on Windows, Liberation Sans on Linux: the same pairs, roughly)
    pair = lambda p: face.kern(face.gid(p[0]), face.gid(p[1]))
    assert pair("AV") < -0.05 and pair("To") < -0.05 and pair("Ty") < -0.03
    assert pair("ab") == 0.0 and pair("oo") == 0.0


def test_kerned_runs_are_narrower_and_others_unchanged():
    face = resolve_face("Helvetica")[0]
    plain = face.text_width(WORDS, 8.0)
    # No setting (text from before mosaic kerned) or off: the letters' own advances, as before
    assert width(None) == pytest.approx(plain) and width(False) == pytest.approx(plain)
    assert width(True) < plain - 0.5


def test_pdf_export_places_kerned_letters(tmp_path):
    doc = model.new_document("k")
    doc["pages"][0].update({"width": 200.0, "height": 60.0, "items": [box(WORDS, True, y=10), box(WORDS, None, y=35)]})
    export_document(doc, str(tmp_path / "k"), ["pdf"])
    import pikepdf
    with pikepdf.open(tmp_path / "k.pdf") as pdf:
        ops = [str(op) for _, op in pikepdf.parse_content_stream(pdf.pages[0].obj)]
    assert ops.count("TJ") == 1 and ops.count("Tj") == 1   # (unkerned text is written as before)
    # Read back: the kerned line ends where the layout ends it
    found = {round(t["origin"][1]): t for t in plottext.texts(str(tmp_path / "k.pdf"), "pdf", 0)}
    kerned, unkerned = sorted(found.items())[0][1], sorted(found.items())[1][1]
    assert kerned["width"] == pytest.approx(width(True), abs=0.01)
    assert unkerned["width"] == pytest.approx(width(None), abs=0.01)


def test_powerpoint_keeps_each_runs_kerning(tmp_path):
    # Out: mosaic's kerned text kerns at any size in PowerPoint, the rest not at all
    doc = model.new_document("k")
    doc["pages"][0].update({"width": 200.0, "height": 60.0, "items": [box(WORDS, True, y=10), box(WORDS, None, y=35)]})
    export_document(doc, str(tmp_path / "k"), ["pptx"])
    xml = zipfile.ZipFile(tmp_path / "k.pptx").read("ppt/slides/slide1.xml").decode()
    assert xml.count('kern="100"') == 1 and xml.count('kern="0"') == 1
    back, _ = import_pptx(str(tmp_path / "k.pptx"))
    runs = [it["text"]["paragraphs"][0]["runs"][0] for it in back["pages"][0]["items"] if it.get("textbox")]
    assert [bool(r.get("kern")) for r in runs] == [True, False]
    # In: PowerPoint kerns from a size up (12 pt by default), so a deck's small text stays unkerned
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    para = slide.shapes.add_textbox(Pt(10), Pt(10), Pt(200), Pt(40)).text_frame.paragraphs[0]
    for text, size, kern in (("small", 8, "1200"), ("large", 14, "1200"), ("always", 8, "100"), ("never", 14, "0")):
        r = para.add_run()
        r.text, r.font.size = text, Pt(size)
        r._r.get_or_add_rPr().set("kern", kern)
    prs.save(tmp_path / "deck.pptx")
    deck, _ = import_pptx(str(tmp_path / "deck.pptx"))
    runs = next(it for it in deck["pages"][0]["items"] if it.get("textbox"))["text"]["paragraphs"][0]["runs"]
    assert {r["t"]: bool(r.get("kern")) for r in runs} == {"small": False, "large": True, "always": True, "never": False}


def test_lifted_text_is_kerned(tmp_path):
    f = tmp_path / "plot.svg"
    f.write_text("<svg xmlns='http://www.w3.org/2000/svg' width='200pt' height='50pt' viewBox='0 0 200 50'>"
                 "<text x='20' y='30' style='font-size: 8px; font-family: Helvetica;'>Type To</text></svg>")
    t = plottext.texts(str(f), "svg", 0)[0]
    lifted = plottext.lift_box(t)
    assert lifted["run"]["kern"] is True
    face = resolve_face("Helvetica")[0]
    assert lifted["frame"][2] < face.text_width("Type To", 8.0)

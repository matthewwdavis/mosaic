import os

import pikepdf
import pytest
from lxml import etree
from PIL import Image

from figassemble import assets, docfile, model
from figassemble.export.run import export_document
from figassemble.fonts import resolve_face
from figassemble.textlayout import AUTOFIT_EXTRA, LINE_FACTOR


def make_doc(fixtures, cache):
    doc = model.new_document("test")
    page = doc["pages"][0]
    page["width"], page["height"] = 300.0, 200.0
    aid, asset, warns = assets.new_asset(fixtures["svg"], cache)
    assert sorted(asset["variants"]) == ["pdf", "svg"]   # the PNG copy isn't needed for a vector plot
    assert not warns
    doc["assets"][aid] = asset
    page["items"].append(model.picture_item(aid, asset, 10, 10))
    jid, jasset, _ = assets.new_asset(fixtures["jpg"], cache)
    doc["assets"][jid] = jasset
    page["items"].append(model.picture_item(jid, jasset, 150, 10))
    rid, rasset, _ = assets.new_asset(fixtures["rgba"], cache)
    doc["assets"][rid] = rasset
    page["items"].append(model.picture_item(rid, rasset, 150, 80))
    page["items"].append(model.text_item("a", 2, 2, size=8, bold=True))
    page["items"].append({"id": "it_line", "type": "line", "points": [[20, 150], [120, 150]],
                          "stroke": {"color": "#000000", "width": 1, "cap": "round", "dash": "dash"},
                          "arrow_end": {"type": "triangle", "w": "sm", "len": "sm"}})
    return doc, aid


def test_asset_siblings_and_sizes(fixtures, cache):
    _, asset, _ = assets.new_asset(fixtures["svg"], cache)
    assert asset["size_pt"] == pytest.approx([100, 50])
    _, png, _ = assets.new_asset(fixtures["png"], cache, use_siblings=False)
    assert png["size_pt"] == pytest.approx([100, 50])   # 200 px at 144 dpi = 100 pt


def test_pdf_places_pages_unchanged_and_embeds_fonts(fixtures, cache, tmp_path):
    doc, _ = make_doc(fixtures, cache)
    out = export_document(doc, str(tmp_path / "out"), ["pdf"], cache=cache)
    pdf = pikepdf.open(out["files"][0])
    page = pdf.pages[0]
    assert [float(v) for v in page.mediabox] == [0, 0, 300, 200]
    xobjs = page.Resources.XObject
    forms = [x for x in xobjs.values() if x.Subtype == "/Form"]
    images = [x for x in xobjs.values() if x.Subtype == "/Image"]
    assert len(forms) == 1 and len(images) == 2
    # The placed PDF's drawing instructions are the original bytes
    src = pikepdf.open(fixtures["pdf"])
    assert forms[0].read_bytes() == src.pages[0].Contents.read_bytes()
    # The JPEG goes in byte-for-byte
    jpeg = next(x for x in images if x.get("/Filter") == "/DCTDecode")
    with open(fixtures["jpg"], "rb") as fh:
        assert jpeg.read_raw_bytes() == fh.read()
    # The transparent PNG keeps its alpha as a soft mask
    assert any("/SMask" in x for x in images)
    # Text fonts are embedded subsets
    fonts = list(page.Resources.Font.values())
    desc = fonts[0].DescendantFonts[0].FontDescriptor
    assert "/FontFile2" in desc or "/FontFile3" in desc


def test_png_without_alpha_is_not_reencoded(fixtures, cache, tmp_path):
    doc = model.new_document()
    aid, asset, _ = assets.new_asset(fixtures["png"], cache, use_siblings=False)
    doc["assets"][aid] = asset
    doc["pages"][0]["items"].append(model.picture_item(aid, asset, 0, 0))
    out = export_document(doc, str(tmp_path / "png"), ["pdf"], cache=cache)
    pdf = pikepdf.open(out["files"][0])
    img = next(iter(pdf.pages[0].Resources.XObject.values()))
    assert img.DecodeParms.Predictor == 15
    pdfimg = pikepdf.PdfImage(img).as_pil_image()
    assert pdfimg.getpixel((5, 5)) == (200, 30, 30)


def test_svg_inlines_markup_with_prefixed_ids_and_scoped_css(fixtures, cache, tmp_path):
    doc, _ = make_doc(fixtures, cache)
    out = export_document(doc, str(tmp_path / "out"), ["svg"], cache=cache)
    root = etree.parse(out["files"][0]).getroot()
    ns = {"s": "http://www.w3.org/2000/svg"}
    ids = [el.get("id") for el in root.iter() if el.get("id")]
    assert "cp1" not in ids and any(i.endswith("-cp1") for i in ids)
    style = root.find(".//s:style", ns).text
    # Every rule is scoped to the panel's group, so the plot's "*" rule can't restyle anything else
    assert all(line.startswith(".fa-p1 ") for line in style.splitlines() if line.strip())
    # The 100% background rect now has the panel's own size, not the page's
    rect = [el for el in root.iter("{http://www.w3.org/2000/svg}rect") if el.get("style") == "fill: none"][0]
    assert float(rect.get("width")) == pytest.approx(100)
    # Raster images become data URIs
    hrefs = [el.get("{http://www.w3.org/1999/xlink}href") for el in root.iter("{http://www.w3.org/2000/svg}image")]
    assert any(h.startswith("data:image/jpeg;base64,") for h in hrefs)


def test_raster_export_size_and_dpi(fixtures, cache, tmp_path):
    doc, _ = make_doc(fixtures, cache)
    out = export_document(doc, str(tmp_path / "out"), ["png", "tiff"], dpi=300, cache=cache)
    png = Image.open(out["files"][0])
    assert png.size == (1250, 833)   # 300 x 200 pt at 300 dpi
    assert round(png.info["dpi"][0]) == 300
    assert png.mode == "RGBA"
    tif = Image.open(out["files"][1])
    assert tif.info.get("compression") == "tiff_lzw"
    # The blue rectangle from the placed PDF is drawn at its spot: PDF (10,10)-(40,30) bottom-up
    # -> page x 20..50, y 30..50 (picture top-left at 10,10; plot is 50 pt tall)
    px = png.getpixel((int(30 * 300 / 72), int(40 * 300 / 72)))
    assert px[:3] == (0, 0, 255)


def test_document_round_trip_embeds_assets(fixtures, cache, tmp_path):
    doc, aid = make_doc(fixtures, cache)
    path = str(tmp_path / "fig.figasm")
    assert docfile.save(doc, path, cache) == []
    other = assets.AssetCache(str(tmp_path / "other-cache"))
    loaded = docfile.load(path, other)
    for kind, var in loaded["assets"][aid]["variants"].items():
        assert other.has(var["sha256"], kind)
        assert var["src_rel"] == os.path.join("Figures", f"plot.{kind}")


def test_autofit_height_follows_powerpoint_model():
    from figassemble.resolve import Resolver
    face, _ = resolve_face("Helvetica")
    item = {"id": "t", "type": "shape", "geom": "rect", "frame": [0, 0, 50, 5], "stroke": None, "fill": None,
            "text": {"paragraphs": [{"runs": [{"t": "x", "size": 6}]}, {"runs": [{"t": "y", "size": 6}]}],
                     "autofit": "shape"}}
    r = Resolver({"assets": {}}).resolve(item)
    line = LINE_FACTOR * 6 * (face.ascent + face.descent + face.line_gap)
    assert r.autofit_frame[3] == pytest.approx(7.2 + 2 * line + AUTOFIT_EXTRA)

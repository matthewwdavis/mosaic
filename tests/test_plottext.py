"""Dangerous mode's engine (plottext.py): the texts in placed PDFs and SVGs, copies without the ones
lifted out, finding them again in a file saved again, the text box a lifted text becomes, and
exports and Check using the copies."""
import pikepdf
import pytest

from mosaic import model, plottext
from mosaic.assets import AssetCache, new_asset
from mosaic.textlayout import first_baseline, line_height
from mosaic.fonts import resolve_face

# The font as R's pdf() writes it: Helvetica, not embedded, no widths, "-" drawn as a minus sign
R_FONT = {"/Type": pikepdf.Name.Font, "/Subtype": pikepdf.Name.Type1, "/BaseFont": pikepdf.Name.Helvetica,
          "/Encoding": {"/Type": pikepdf.Name.Encoding, "/BaseEncoding": pikepdf.Name.WinAnsiEncoding,
                        "/Differences": [45, pikepdf.Name.minus]}}


def r_pdf(path, content: bytes, size=(200, 120)):
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=size)
    page.obj.Resources = pikepdf.Dictionary({"/Font": pikepdf.Dictionary({"/F2": pikepdf.Dictionary(R_FONT)})})
    page.obj.Contents = pdf.make_stream(content)
    pdf.save(path)
    return str(path)


# R's way: each text its own BT ... ET with its own Tm; a title kerned with TJ; a y axis title turned
R_PLOT = b" ".join([
    b"0 0 0 RG 0.5 w 20 30 m 190 30 l S",
    b"BT /F2 1 Tf 5.00 0.00 0.00 5.00 18.0 20.0 Tm (-1) Tj ET",
    b"BT 0.6 0.2 0.2 rg /F2 1 Tf 6.00 0.00 0.00 6.00 80.0 8.0 Tm [(Da) 30 (ys after sowing)] TJ ET",
    b"BT 0 g /F2 1 Tf 0.00 6.00 -6.00 0.00 9.0 50.0 Tm (Height \\(cm\\)) Tj ET",
])


def svg(path, body: str, w=200, h=120):
    path.write_text(f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}pt' height='{h}pt' viewBox='0 0 {w} {h}'>{body}</svg>")
    return str(path)


SVGLITE = ("<g class='svglite'><text x='23.2' y='100.1' text-anchor='end' style='font-size: 4.80px; font-family: \"Helvetica\";' "
           "textLength='5.70px' lengthAdjust='spacingAndGlyphs'>-1</text>"
           "<text x='105' y='112' text-anchor='middle' style='font-size: 6.00px; font-family: \"Helvetica\"; fill: #993333;' "
           "textLength='47.42px'>Days after sowing</text>"
           "<text transform='translate(9,60) rotate(-90)' text-anchor='middle' style='font-size: 6.00px; font-family: Helvetica;'>"
           "Height (cm)</text></g>")


def by_text(found):
    return {t["text"]: t for t in found}


def test_reads_r_pdf_text(tmp_path):
    found = by_text(plottext.texts(r_pdf(tmp_path / "plot.pdf", R_PLOT), "pdf", 0))
    assert set(found) == {"−1", "Days after sowing", "Height (cm)"}
    tick, title, ytitle = found["−1"], found["Days after sowing"], found["Height (cm)"]
    # Positions from the top left: the page is 120 pt tall
    assert tick["origin"] == pytest.approx([18.0, 100.0]) and tick["size"] == pytest.approx(5.0)
    assert tick["font"] == "Helvetica" and not tick["bold"] and tick["angle"] == pytest.approx(0)
    # The kerning (30/1000 of 6 pt) makes the title that much shorter than its letters
    face = resolve_face("Helvetica")[0]
    assert title["width"] == pytest.approx(face.text_width("Days after sowing", 6.0) - 0.18, abs=0.01)
    assert title["color"] == "#993333"
    assert ytitle["angle"] == pytest.approx(-90) and ytitle["origin"] == pytest.approx([9.0, 70.0])


def test_hiding_text_in_a_pdf_keeps_the_rest_in_place(tmp_path):
    # Two texts in one BT, the second carrying on from where the first ends (a colour between them)
    f = r_pdf(tmp_path / "line.pdf", b"BT /F2 1 Tf 8 0 0 8 20 50 Tm (Ab) Tj 1 0 0 rg (Cd) Tj ET")
    found, moves = plottext._read(f, "pdf", 0)
    assert [t.text for t in found] == ["Ab", "Cd"]
    before = found[1].origin
    data = plottext._pdf_hide(f, 0, found[0].refs, moves)
    out = tmp_path / "hidden.pdf"
    out.write_bytes(data)
    left = plottext.texts(str(out), "pdf", 0)
    assert [t["text"] for t in left] == ["Cd"] and left[0]["origin"] == pytest.approx(list(before), abs=1e-3)


def test_reads_and_hides_svglite_text(tmp_path):
    f = svg(tmp_path / "plot.svg", SVGLITE)
    found = by_text(plottext.texts(f, "svg", 0))
    assert set(found) == {"-1", "Days after sowing", "Height (cm)"}
    tick, title, ytitle = found["-1"], found["Days after sowing"], found["Height (cm)"]
    # svglite's own widths (textLength), and its text-anchor as the alignment
    assert tick["align"] == "r" and tick["origin"] == pytest.approx([17.5, 100.1]) and tick["size"] == pytest.approx(4.8)
    assert title["align"] == "ctr" and title["mid"] == pytest.approx([105.0, 112.0]) and title["color"] == "#993333"
    assert ytitle["angle"] == pytest.approx(-90) and ytitle["mid"] == pytest.approx([9.0, 60.0])
    refs = [r for t in plottext._read(f, "svg", 0)[0] if t.text != "-1" for r in t.refs]
    out = tmp_path / "hidden.svg"
    out.write_bytes(plottext._svg_hide(f, refs))
    assert [t["text"] for t in plottext.texts(str(out), "svg", 0)] == ["-1"]
    assert "Days" not in out.read_text()


def test_hiding_part_of_an_svg_text_keeps_the_rest_where_it_was(tmp_path):
    # Illustrator's way: a tspan, then words carrying on from it in another colour
    f = svg(tmp_path / "parts.svg", "<text x='10' y='50' style='font-size: 8px; font-family: Helvetica;'>"
                                    "<tspan>Wild</tspan><tspan style='fill: #ff0000;'> type</tspan></text>")
    found = plottext._read(f, "svg", 0)[0]
    assert [t.text for t in found] == ["Wild", " type"] or [t.text for t in found] == ["Wild", "type"]
    out = tmp_path / "hidden.svg"
    out.write_bytes(plottext._svg_hide(f, found[0].refs))
    left = plottext.texts(str(out), "svg", 0)
    assert len(left) == 1 and left[0]["text"].strip() == "type"
    assert left[0]["origin"] == pytest.approx(list(found[1].origin))
    assert "visibility:hidden" in out.read_text()


def test_a_text_is_found_again_in_the_other_copy_and_after_r_saves_it(tmp_path):
    # R's PDF writes 4.8 pt text at 5 pt and "-" as a minus; its SVG a hyphen at 4.8 pt, a little apart
    pdf_found = plottext.texts(r_pdf(tmp_path / "plot.pdf", R_PLOT), "pdf", 0)
    svg_found = plottext.texts(svg(tmp_path / "plot.svg", SVGLITE), "svg", 0)
    tick = by_text(svg_found)["-1"]
    i = plottext.match(pdf_found, plottext.descriptor(tick))
    assert i is not None and pdf_found[i]["text"] == "−1"
    # Changed words, or the same words somewhere else, aren't the same text
    assert plottext.match(pdf_found, {**plottext.descriptor(tick), "text": "-2"}) is None
    assert plottext.match(pdf_found, {**plottext.descriptor(tick), "mid": [60.0, 100.0]}) is None


def test_lifted_text_box_sits_on_the_text(tmp_path):
    found = by_text(plottext.texts(svg(tmp_path / "plot.svg", SVGLITE), "svg", 0))
    face = resolve_face("Helvetica")[0]
    for name, scale in (("Days after sowing", 1.0), ("Days after sowing", 1.5), ("-1", 1.0)):
        t = found[name]
        box = plottext.lift_box(t, scale)
        x, y, w, h = box["frame"]
        size = t["size"] * scale
        # The box's first baseline (at its size on the page) lands on the text's baseline
        assert y + first_baseline(face, size, line_height(face, size)) / scale == pytest.approx(t["origin"][1], abs=1e-3)
        assert box["run"]["t"] == name and box["run"]["size"] == pytest.approx(t["size"]) and box["rot"] == 0
        if t["align"] == "ctr":
            assert x + w / 2 == pytest.approx(t["mid"][0], abs=1e-3)
        else:   # lined up on the right, as the tick label was
            assert x + w == pytest.approx(t["origin"][0] + t["width"], abs=1e-3)
    turned = plottext.lift_box(found["Height (cm)"])
    assert turned["rot"] == pytest.approx(270) and turned["align"] == "ctr"
    x, y, w, h = turned["frame"]
    assert y + h / 2 == pytest.approx(60.0, abs=1e-3)   # its middle on the baseline's middle, across the plot


def doc_with(tmp_path, cache, lifted=("Days after sowing",)):
    r_pdf(tmp_path / "plot.pdf", R_PLOT)
    svg(tmp_path / "plot.svg", SVGLITE)
    aid, asset, _ = new_asset(str(tmp_path / "plot.pdf"), cache, link=False)
    found = by_text(plottext.plot_texts(asset, 0, "svg", cache)["texts"])
    hidden = [{**plottext.descriptor(found[t]), "id": f"lt{i}", "box": f"b{i}"} for i, t in enumerate(lifted)]
    pic = {"id": "pic", "type": "picture", "name": "plot.pdf", "asset": aid, "frame": [0, 0, 200, 120],
           "crop": [0, 0, 0, 0], "rot": 0, "lifted_text": {"hidden": hidden}}
    doc = model.new_document("t")
    doc["pages"][0].update({"width": 200.0, "height": 120.0, "items": [pic]})
    doc["assets"][aid] = asset
    return doc, aid


def test_copies_without_lifted_text_for_exports_and_check(tmp_path):
    cache = AssetCache(str(tmp_path / "cache"))
    doc, aid = doc_with(tmp_path, cache)
    got = plottext.derived(doc["assets"][aid], 0, doc["pages"][0]["items"][0]["lifted_text"]["hidden"], cache)
    assert got["missing"] == {"pdf": [], "svg": []}
    for kind in ("pdf", "svg"):
        left = [t["text"] for t in plottext.texts(cache.path(got["variants"][kind]["sha256"], kind), kind, 0)]
        assert "Days after sowing" not in left and len(left) == 2
    # Made once: the same copy again, from the cache
    assert plottext.derived(doc["assets"][aid], 0, doc["pages"][0]["items"][0]["lifted_text"]["hidden"], cache) == got
    # Exports and Check see the copy; the document passed in is left alone
    out = plottext.with_lifts(doc, cache)
    pic = out["pages"][0]["items"][0]
    assert pic["asset"] != aid and out["assets"][pic["asset"]]["variants"]["pdf"] == got["variants"]["pdf"]
    assert doc["pages"][0]["items"][0]["asset"] == aid
    plain = model.new_document("plain")
    assert plottext.with_lifts(plain, cache) is plain


def test_text_r_saved_differently_is_missing(tmp_path):
    cache = AssetCache(str(tmp_path / "cache"))
    doc, aid = doc_with(tmp_path, cache)
    hidden = doc["pages"][0]["items"][0]["lifted_text"]["hidden"]
    # R saves the plot again with another x axis title
    r_pdf(tmp_path / "plot.pdf", R_PLOT.replace(b"ys after sowing", b"ys"))
    svg(tmp_path / "plot.svg", SVGLITE.replace("Days after sowing", "Days"))
    _, asset, _ = new_asset(str(tmp_path / "plot.pdf"), cache, link=False)
    assert plottext.derived(asset, 0, hidden, cache)["missing"] == {"pdf": ["lt0"], "svg": ["lt0"]}


def test_check_notes_lifted_text(tmp_path, monkeypatch):
    from mosaic.export import preflight as pf
    cache = AssetCache(str(tmp_path / "cache"))
    monkeypatch.setattr(pf, "get_cache", lambda: cache)
    doc, aid = doc_with(tmp_path, cache)
    msgs = {f["message"]: f["level"] for f in pf.preflight(doc, {})["items"]}
    assert msgs["plot.pdf: 1 text lifted out in dangerous mode (“Days after sowing”), now text boxes rather than part "
                "of its file"] == "info"
    # A text only one copy has: the other copy's export would show it as well as its box
    pic = doc["pages"][0]["items"][0]
    pic["lifted_text"]["hidden"][0].update({"text": "Days after planting"})
    svg(tmp_path / "plot.svg", SVGLITE.replace("Days after sowing", "Days after planting"))
    _, asset, _ = new_asset(str(tmp_path / "plot.pdf"), cache, link=False)
    doc["assets"][aid] = asset
    msgs = {f["message"]: f["level"] for f in pf.preflight(doc, {})["items"]}
    assert msgs["plot.pdf: “Days after planting” couldn't be found in its PDF copy, so PDF export shows it as well as its "
                "text box"] == "warning"
    pic["lifted_text"]["dropped"] = [{"text": "Height (cm)", "box_text": "Height (mm)"}]
    msgs = {f["message"]: f["level"] for f in pf.preflight(doc, {})["items"]}
    assert msgs["plot.pdf: the edit to “Height (cm)” was dropped when its file changed, as the text isn't there any more "
                "(its text box had “Height (mm)”)"] == "info"


def test_export_leaves_out_the_lifted_text(tmp_path):
    from mosaic.export.run import export_document
    cache = AssetCache(str(tmp_path / "cache"))
    doc, aid = doc_with(tmp_path, cache)
    export_document(doc, str(tmp_path / "out"), ["pdf", "svg"], cache=cache)
    assert "Days after sowing" not in [t["text"] for t in plottext.texts(str(tmp_path / "out.pdf"), "pdf", 0)]
    assert "Height (cm)" in [t["text"] for t in plottext.texts(str(tmp_path / "out.pdf"), "pdf", 0)]
    assert "Days after sowing" not in (tmp_path / "out.svg").read_text()

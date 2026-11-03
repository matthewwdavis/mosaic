"""The figure report: each picture's source, copies, size, place, scale, crop, turns, resolution
and calibration, in HTML, Markdown, CSV and PDF."""
import csv

import pypdfium2 as pdfium

from mosaic import assets, model, report


def figure(fixtures, cache):
    doc = model.new_document("Report test")
    page = doc["pages"][0]
    page["width"], page["height"] = 300.0, 200.0
    vid, va, _ = assets.new_asset(fixtures["pdf"], cache)
    pid, pa, _ = assets.new_asset(fixtures["png"], cache, use_siblings=False)
    doc["assets"].update({vid: va, pid: pa})
    plot = model.picture_item(vid, va, 10, 20)
    plot["crop"] = [0.1, 0.0, 0.0, 0.2]
    plot["frame"][2:] = [45.0, 20.0]   # half the cropped plot's size
    photo = model.picture_item(pid, pa, 150, 20)
    photo["rot"], photo["flip_h"] = 90, True
    photo["scale"] = {"per_pt": 0.5, "unit": "µm", "how": "measured"}
    bar = {"id": "bar", "type": "scalebar", "picture": photo["id"], "length": 20, "unit": "µm", "frame": [0, 0, 10, 4]}
    page["items"] = [plot, photo, bar]
    return doc, plot, photo


def test_one_row_per_picture(fixtures, cache):
    doc, plot, photo = figure(fixtures, cache)
    rows = report.rows(doc, unit="mm")
    assert [r["panel"] for r in rows] == [plot["name"], photo["name"]]
    p, ph = rows
    assert p["copies"] == "PDF + SVG" and p["resolution"] == "vector" and p["scale"] == "50%"
    assert p["crop"] == "left 10%, bottom 20%" and p["turns"] == "none" and p["size"] == "15.87 × 7.06 mm"
    assert ph["turns"] == "turned 90°, flipped across" and ph["resolution"].endswith("ppi at this size")
    assert ph["calibration"].startswith("1 pixel = ") and "(measured)" in ph["calibration"] and ph["calibration"].endswith("scale bar 20 µm")
    assert p["file_found"] == "yes" and fixtures["pdf"] in p["source"]


def test_every_format(fixtures, cache, tmp_path):
    doc, plot, _ = figure(fixtures, cache)
    base = str(tmp_path / "fig_report")
    files = report.write(doc, base, ["html", "md", "csv", "pdf"], unit="cm")
    assert files == [base + ext for ext in (".html", ".md", ".csv", ".pdf")]
    with open(base + ".csv", newline="", encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    assert len(table) == 2 and table[0]["unit"] == "cm" and float(table[0]["scale_percent_across"]) == 50.0
    md = open(base + ".md", encoding="utf-8").read()
    assert md.startswith("# Figure report: Report test") and "| Panel | Source |" in md and "## Page 1\n" in md
    html_text = open(base + ".html", encoding="utf-8").read()
    assert "<table>" in html_text and "turned 90°" in html_text
    doc_pdf = pdfium.PdfDocument(base + ".pdf")
    text = doc_pdf[0].get_textpage().get_text_range()
    doc_pdf.close()
    assert "Figure report: Report test" in text and "left 10%" in text
    # Only what's asked for
    assert report.write(doc, str(tmp_path / "just"), ["csv"]) == [str(tmp_path / "just") + ".csv"]

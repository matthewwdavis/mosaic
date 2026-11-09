"""Linked pictures follow their files (assets.refresh_asset, through Api.refresh_assets, which the
editor calls every 2 s): a figure re-saved under the same name, as R does, is read again, every copy
of it (PDF, SVG, PNG), with its new size; a file only touched isn't an update; a file saved under a
new name, a missing file and an unlinked picture are left alone; a document moved together with its
figures finds them beside it. The editor's side (the picture keeping its place and scale, undo) is
in the editor self-test (linkedFileChecks)."""
import os
import shutil

import pikepdf

from mosaic import docfile, model
from mosaic.app.api import Api
from mosaic.assets import new_asset


def svg(w: float, colour: str = "#336699", label: str = "first") -> str:
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}pt' height='50pt' viewBox='0 0 {w} 50'>"
            f"<rect x='5' y='5' width='{w - 10}' height='30' fill='{colour}'/><text x='5' y='46'>{label}</text></svg>")


def write_pdf(path: str, w: float, rgb: str = "0 0 1") -> None:
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(w, 50))
    page.obj.Contents = pdf.make_stream(f"{rgb} rg 5 5 {w - 10} 30 re f".encode())
    pdf.save(path)


def moved_on(path: str, before_ns: int) -> None:
    """Make sure a re-saved file's time stamp moved on (some file systems keep coarse times)."""
    if os.stat(path).st_mtime_ns <= before_ns:
        os.utime(path, ns=(before_ns + 10_000_000, before_ns + 10_000_000))


def resave(path: str, text: str) -> None:
    before = os.stat(path).st_mtime_ns
    with open(path, "w") as fh:
        fh.write(text)
    moved_on(path, before)


def plot(folder) -> str:
    """An R-style figure saved as SVG and PDF under one name; returns the SVG's path."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plot.svg").write_text(svg(100))
    write_pdf(str(folder / "plot.pdf"), 100)
    return str(folder / "plot.svg")


def test_a_figure_re_saved_under_its_name_is_read_again_with_every_copy(tmp_path):
    path = plot(tmp_path / "Figures")
    aid, asset, _ = new_asset(path)
    assert asset["auto_update"] and sorted(asset["variants"]) == ["pdf", "svg"]
    api = Api()
    assert api.refresh_assets({aid: asset}) == {"changed": {}}
    # Re-run in R: wider, another colour, both copies saved again
    resave(path, svg(140, "#993333", "second"))
    pdf_path = str(tmp_path / "Figures" / "plot.pdf")
    before = os.stat(pdf_path).st_mtime_ns
    write_pdf(pdf_path, 140, "1 0 0")
    moved_on(pdf_path, before)
    neu = api.refresh_assets({aid: asset})["changed"][aid]
    assert neu["size_pt"] == [140.0, 50.0]
    assert all(neu["variants"][k]["sha256"] != asset["variants"][k]["sha256"] for k in ("pdf", "svg"))
    assert [neu["variants"][k]["src"] for k in ("pdf", "svg")] == [asset["variants"][k]["src"] for k in ("pdf", "svg")]
    # Read once: the next look finds nothing new
    assert api.refresh_assets({aid: neu}) == {"changed": {}}


def test_a_file_only_touched_is_not_an_update(tmp_path):
    path = plot(tmp_path / "Figures")
    aid, asset, _ = new_asset(path)
    moved_on(path, os.stat(path).st_mtime_ns)   # saved again with the same contents
    assert Api().refresh_assets({aid: asset}) == {"changed": {}}


def test_a_new_name_a_missing_file_and_an_unlinked_picture_are_left_alone(tmp_path):
    path = plot(tmp_path / "Figures")
    aid, asset, _ = new_asset(path)
    api = Api()
    # Saved under a new name: the picture keeps following the old one
    (tmp_path / "Figures" / "plot_v2.svg").write_text(svg(160, "#000000", "v2"))
    assert api.refresh_assets({aid: asset}) == {"changed": {}}
    # Unlinked (Unlink, or Option-dropped): stays as it is
    unlinked = {**asset, "auto_update": False}
    resave(path, svg(140, "#993333", "second"))
    assert api.refresh_assets({aid: unlinked}) == {"changed": {}}
    # Gone: no update and no error; the Picture tab says the link is missing
    os.remove(path)
    os.remove(str(tmp_path / "Figures" / "plot.pdf"))
    assert api.refresh_assets({aid: asset}) == {"changed": {}}
    assert api.link_status({aid: asset}) == {aid: "missing"}


def test_refresh_all_reads_every_file_again_and_finds_new_copies(tmp_path):
    # Placed as an SVG alone; R then saves a PDF copy too, and re-saves the SVG keeping its size
    # and date (as a copy from a synced folder can be): the regular look sees neither
    folder = tmp_path / "Figures"
    folder.mkdir()
    path = str(folder / "plot.svg")
    (folder / "plot.svg").write_text(svg(100))
    aid, asset, _ = new_asset(path)
    assert sorted(asset["variants"]) == ["svg"]
    write_pdf(str(folder / "plot.pdf"), 100)
    st = os.stat(path)
    (folder / "plot.svg").write_text(svg(100, "#993399"))   # (the same length: one colour for another)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    api = Api()
    assert api.refresh_assets({aid: asset}) == {"changed": {}}
    res = api.refresh_assets({aid: asset}, None, True)
    neu = res["changed"][aid]
    assert res["added"] == {aid: ["pdf"]} and res["missing"] == []
    assert sorted(neu["variants"]) == ["pdf", "svg"] and neu["variants"]["svg"]["sha256"] != asset["variants"]["svg"]["sha256"]
    assert neu["variants"]["pdf"]["src"] == str(folder / "plot.pdf")
    # A copy of another size isn't the same plot
    write_pdf(str(folder / "other.pdf"), 120)
    (folder / "other.svg").write_text(svg(100))
    oid, other, _ = new_asset(str(folder / "other.svg"))
    assert sorted(other["variants"]) == ["svg"]
    assert api.refresh_assets({oid: other}, None, True) == {"changed": {}, "added": {}, "missing": []}
    # Nothing new: nothing changed; a file gone is listed
    assert api.refresh_assets({aid: neu}, None, True) == {"changed": {}, "added": {}, "missing": []}
    os.remove(path)
    os.remove(str(folder / "plot.pdf"))
    assert api.refresh_assets({aid: neu}, None, True)["missing"] == [aid]


def test_a_document_moved_with_its_figures_finds_them_beside_it(tmp_path):
    first = tmp_path / "project"
    path = plot(first / "Figures")
    aid, asset, _ = new_asset(path)
    doc = model.new_document()
    doc["assets"][aid] = asset
    doc["pages"][0]["items"].append(model.picture_item(aid, asset, 20, 20))
    docfile.save(doc, str(first / "figure.mosaic"))
    moved = tmp_path / "moved"
    shutil.move(str(first), str(moved))   # the whole folder, figures and all
    doc = docfile.load(str(moved / "figure.mosaic"))
    api = Api()
    assert api.link_status(doc["assets"], str(moved / "figure.mosaic")) == {aid: "linked"}
    resave(str(moved / "Figures" / "plot.svg"), svg(140, "#993333", "second"))
    changed = api.refresh_assets(doc["assets"], str(moved / "figure.mosaic"))["changed"]
    assert changed[aid]["size_pt"] == [140.0, 50.0]

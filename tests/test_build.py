"""`mosaic build` (mosaic/refresh.py, cli.py): a figure rebuilt from plots a script just re-made.
Every linked picture is read again from its file, keeping its place and scale, and the figure
is exported; the document itself changes only with --save, its earlier state kept as a version."""
import json
import os
import time

from mosaic import cli, docfile, model
from mosaic.app import kept
from mosaic.assets import get_cache, new_asset


def plot(path, width, colour):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}pt" height="50pt" viewBox="0 0 {width} 50">'
                    f'<rect x="5" y="5" width="{width - 10}" height="40" fill="{colour}"/></svg>')
    t = time.time() + width   # (a date of its own, as a file saved again has)
    os.utime(path, (t, t))


def figure(tmp_path):
    """A saved figure with one linked plot at 150% and one stored in the document only."""
    plots = tmp_path / "Figures"
    plots.mkdir()
    plot(plots / "linked.svg", 100, "#336699")
    plot(plots / "stored.svg", 80, "#999999")
    doc = model.new_document("Fig")
    aid, asset, _ = new_asset(str(plots / "linked.svg"), get_cache())
    bid, stored, _ = new_asset(str(plots / "stored.svg"), get_cache(), link=False)
    doc["assets"].update({aid: asset, bid: stored})
    item = model.picture_item(aid, asset, 20, 30)
    item["frame"] = [20, 30, 150, 75]
    doc["pages"][0]["items"] += [item, model.picture_item(bid, stored, 20, 200)]
    path = str(tmp_path / "fig.mosaic")
    docfile.save(doc, path)
    return path, plots


def test_build_reads_the_plots_again_and_exports_without_touching_the_document(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    path, plots = figure(tmp_path)
    before = open(path, "rb").read()
    plot(plots / "linked.svg", 140, "#993333")   # R saves it again: wider, another colour
    plot(plots / "stored.svg", 90, "#000000")    # (not linked: stays as it is)
    assert cli.main(["build", path, "-f", "svg", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["refreshed"] == {"changed": ["linked.svg"], "missing": [], "linked": 1} and "saved" not in got
    svg = open(got["files"][0], encoding="utf-8").read()
    assert "#993333" in svg and "#336699" not in svg and "#999999" in svg
    assert open(path, "rb").read() == before   # the document: as it was


def test_build_save_keeps_the_scale_and_an_earlier_version(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    path, plots = figure(tmp_path)
    plot(plots / "linked.svg", 140, "#993333")
    assert cli.main(["build", path, "-f", "svg", "--save", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["saved"] == path
    doc = docfile.load(path)
    linked = next(it for it in doc["pages"][0]["items"] if it["frame"][1] == 30)
    assert [round(v, 3) for v in linked["frame"]] == [20, 30, 210, 75]   # still at 150%, where it was
    assert len(kept.listing(path)["versions"]) == 1                     # the file as it was: under Browse Versions
    # Nothing changed since: nothing saved, nothing more kept
    assert cli.main(["build", path, "-f", "svg", "--save", "--json"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["refreshed"]["changed"] == [] and "saved" not in again and len(kept.listing(path)["versions"]) == 1


def test_a_plot_whose_file_is_gone_uses_the_copy_in_the_document(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    path, plots = figure(tmp_path)
    os.remove(plots / "linked.svg")
    assert cli.main(["build", path, "-f", "svg", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["refreshed"]["missing"] == ["linked.svg"] and any("wasn't found" in w for w in got["warnings"])
    assert "#336699" in open(got["files"][0], encoding="utf-8").read()
    assert cli.main(["export", path, "--save"]) == 2   # (--save needs --refresh)

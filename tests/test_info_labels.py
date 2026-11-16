"""A page's panel labels for other programs: `mosaic info --json` gives each page's labels as
they're read (rows from the top, each from the left), with where they are and whether each is a
panel's letter (level 1) or a sub-panel's (level 2). prose fills a figure's legend from them."""
import json

from mosaic import cli, docfile, model


def label(text, x, y, panel_label=True):
    return {"id": f"lb_{text}_{x}_{y}", "type": "shape", "geom": "rect", "textbox": True, "stroke": None, "fill": None, "rot": 0,
            "frame": [x, y, 6, 9], "text": {"paragraphs": [{"runs": [{"t": text, "bold": True, "size": 8}]}]},
            **({"panel_label": True} if panel_label else {})}


def test_info_gives_each_pages_panel_labels_in_reading_order(tmp_path, capsys):
    doc = model.new_document("Fig 1")
    page = doc["pages"][0]
    # (stacked out of order; c sits a little lower than b but on the same row)
    page["items"] += [label("c", 200, 1.5), label("a", 1, 0), label("d", 1, 120), label("b", 100, 0, panel_label=False),
                      label("Height (mm)", 50, 60)]
    page["items"].append({"id": "g1", "type": "group", "items": [label("i", 20, 130), label("ii", 80, 130.5), label("d(iii)", 140, 131)]})
    doc["pages"].append(model.new_page("Page 2"))
    path = str(tmp_path / "fig.mff")
    docfile.save(doc, path)
    assert cli.main(["info", path, "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    got = info["pages"][0]["labels"]
    assert [(d["text"], d["level"]) for d in got] == [("a", 1), ("b", 1), ("c", 1), ("d", 1), ("i", 2), ("ii", 2), ("d(iii)", 2)]
    assert got[0] == {"text": "a", "x": 1, "y": 0, "level": 1}
    assert info["pages"][1]["labels"] == []
    # (and in words)
    assert cli.main(["info", path]) == 0
    assert "panel labels: a, b, c, d, i, ii, d(iii)" in capsys.readouterr().out


def test_text_that_isnt_made_as_a_label_isnt_one(tmp_path, capsys):
    doc = model.new_document("Fig 2")
    # (a roman numeral typed in an ordinary text box is an axis's or a note's, not a sub-panel)
    doc["pages"][0]["items"] += [label("ii", 10, 10, panel_label=False), label("A", 40, 10, panel_label=False)]
    path = str(tmp_path / "fig.mff")
    docfile.save(doc, path)
    assert cli.main(["info", path, "--json"]) == 0
    assert [d["text"] for d in json.loads(capsys.readouterr().out)["pages"][0]["labels"]] == ["A"]

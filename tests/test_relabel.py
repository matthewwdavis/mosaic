"""A figure's panel labels in another journal's look from the command line (`mosaic export
--journal`): what the app's Size ▸ journal does to a page's labels, on every page, with the document
and its own exports left as they are."""
import json
import os

import pytest

from mosaic import cli, docfile, model, relabel
from mosaic.journals import MM


def label(text, size=8.0, bold=True, font="Helvetica", **kw):
    it = model.text_item(text, 10, 10, size=size, bold=bold, font=font)
    it.update(kw)
    return it


def figure(*items, journal="Nature", width=180.0):
    doc = model.new_document("fig")
    page = doc["pages"][0]
    page["width"], page["height"] = width * MM, 120 * MM
    page["items"] = list(items)
    if journal:
        page["preset"] = {"journal": journal, "type": "Double column"}
    return doc


def runs(item):
    return [(r["t"], r.get("font"), r.get("size"), bool(r.get("bold"))) for p in item["text"]["paragraphs"] for r in p["runs"]]


def test_labels_take_the_journal_look_but_keep_changes_made_by_hand():
    a, b = label("a"), label("b", size=10.0)                     # b's size changed by hand
    word = label("leaf", panel_label=True)                         # other text the Label tool made
    group = {"id": "g", "type": "group", "name": "Group", "frame": [0, 0, 50, 50], "items": [label("c")]}
    plain = label("Leaf area", size=6.0, bold=False)               # not a label: left alone
    doc = figure(a, b, word, group, plain)
    counts = relabel.relabel(doc, relabel.find_journal("Cell"))
    assert counts == [4]
    assert runs(a) == [("A", "Arial", 9.0, True)]
    assert runs(b) == [("B", "Arial", 10.0, True)], "its own size kept"
    assert runs(word) == [("LEAF", "Arial", 9.0, True)]
    assert runs(group["items"][0]) == [("C", "Arial", 9.0, True)]
    assert runs(plain) == [("Leaf area", "Helvetica", 6.0, False)]
    page = doc["pages"][0]
    assert page["preset"] == {"journal": "Cell", "type": "Full width"}, "the nearest of Cell's widths to 180 mm"


def test_a_page_without_a_journal_takes_all_of_it_and_bracketed_forms():
    a = label("A", size=12.0, bold=False, font="Arial")
    doc = figure(a, journal=None, width=80.0)
    assert relabel.relabel(doc, relabel.find_journal("new phytologist")) == [1]
    assert runs(a) == [("(a)", "Helvetica", 8.0, True)]
    assert doc["pages"][0]["preset"] == {"journal": "New Phytologist", "type": "Single column"}


def test_biorxiv_labels_are_bold_lower_case_and_its_page_keeps_a_width_of_its_own():
    # Matthew's labels (bold lower-case 8 pt Helvetica, as his figures have them) are bioRxiv's already
    a, big = label("a", size=8.0, bold=True), label("B", size=12.0, bold=False, font="Arial")
    doc = figure(a, width=120.0)   # (a Nature page before, as his are)
    assert relabel.relabel(doc, relabel.find_journal("biorxiv")) == [0]
    assert runs(a) == [("a", "Helvetica", 8.0, True)]
    assert doc["pages"][0]["preset"] == {"journal": "bioRxiv"}, "any width: no figure type"
    assert doc["pages"][0]["width"] == 120.0 * MM
    doc = figure(big, journal=None, width=177.8)   # (no journal before: all of bioRxiv's look)
    assert relabel.relabel(doc, relabel.find_journal("bioRxiv")) == [1]
    assert runs(big) == [("b", "Helvetica", 8.0, True)]
    assert doc["pages"][0]["preset"] == {"journal": "bioRxiv", "type": "Full width"}


def test_journal_names_and_file_names():
    assert relabel.find_journal("plos_genetics")["name"] == "PLOS Genetics"
    assert relabel.find_journal("MBE")["name"] == "Molecular Biology and Evolution"
    assert relabel.find_journal("the plant journal")["name"] == "The Plant Journal"
    assert relabel.find_journal("Nature Plants") is None
    assert [relabel.slug(n) for n in ("Nature", "PLOS Genetics", "The Plant Journal", "Molecular Biology and Evolution")] == \
        ["nature", "plos_genetics", "plant_journal", "mbe"]


def test_export_journal_copy_leaves_the_document_alone(tmp_path, capsys):
    doc = figure(label("a"), label("b"))
    src = tmp_path / "main_figures_v1.mosaic"
    docfile.save(doc, str(src))
    before = src.read_bytes()
    # How many would change, nothing written
    assert cli.main(["export", str(src), "--journal", "Cell", "--dry-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"journal": "Cell", "labels": [2]}
    assert sorted(os.listdir(tmp_path)) == ["main_figures_v1.mosaic"]
    # The copy and its PDF
    copy = tmp_path / "main_figures_v1_cell.mosaic"
    assert cli.main(["export", str(src), "--journal", "Cell", "--copy", str(copy), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["copy"] == str(copy) and out["labels"] == [2]
    assert out["files"] == [str(tmp_path / "main_figures_v1_cell.pdf")]
    assert src.read_bytes() == before, "the document untouched"
    relabelled = docfile.load(str(copy))
    texts = [it["text"]["paragraphs"][0]["runs"][0]["t"] for it in relabelled["pages"][0]["items"]]
    assert texts == ["A", "B"] and relabelled["pages"][0]["preset"]["journal"] == "Cell"
    # Its box fits the bigger letter (as the app gives it when it draws the page)
    assert relabelled["pages"][0]["items"][0]["frame"][3] != doc["pages"][0]["items"][0]["frame"][3]
    # Named after the journal when nothing names it
    assert cli.main(["export", str(src), "--journal", "Science"]) == 0
    assert os.path.exists(tmp_path / "main_figures_v1_science.pdf")


def test_never_over_the_document_or_its_own_exports(tmp_path, capsys):
    src = tmp_path / "fig.mosaic"
    docfile.save(figure(label("a")), str(src))
    before = src.read_bytes()
    assert cli.main(["export", str(src), "--journal", "Cell", "--copy", str(src)]) == 2
    assert cli.main(["export", str(src), "--journal", "Cell", "-o", str(tmp_path / "fig")]) == 2
    assert cli.main(["export", str(src), "--journal", "Nature Plants"]) == 2
    assert cli.main(["export", str(src), "--copy", str(tmp_path / "x.mosaic")]) == 2, "--copy needs --journal"
    assert src.read_bytes() == before
    assert sorted(os.listdir(tmp_path)) == ["fig.mosaic"]
    capsys.readouterr()


def test_labels_already_in_the_look_are_not_changed():
    """Sizes stored as whole numbers (8) are the journal's 8.0: nothing to change, nothing counted."""
    a = label("a")
    a["text"]["paragraphs"][0]["runs"][0]["size"] = 8
    doc = figure(a, label("b"))
    assert relabel.relabel(doc, relabel.find_journal("Nature")) == [0]
    assert a["text"]["paragraphs"][0]["runs"][0]["size"] == 8 and isinstance(a["text"]["paragraphs"][0]["runs"][0]["size"], int)
    doc = figure(label("a"), journal=None)
    assert relabel.relabel(doc, relabel.find_journal("Nature")) == [0], "no journal before, but already Nature's look"


def test_a_powerpoint_label_box_keeps_its_letter_on_one_line_and_on_the_page():
    """Boxes made in PowerPoint (7.2 pt insets each side of a 9.3 pt box, the text centred, wrapped)
    would break "(a)" into three lines: each grows about its centre to hold the text, and one at the
    page's edge moves in just enough to keep its text on the page."""
    from mosaic.fonts import get_font_index
    from mosaic.resolve import Resolver

    def ppt(text, x):
        it = label(text)
        it["frame"] = [x, 20.0, 9.3, 17.0]
        it["text"].update({"insets": [7.2, 3.6, 7.2, 3.6], "wrap": True})
        it["text"]["paragraphs"][0]["align"] = "ctr"
        return it

    inner, edge = ppt("b", 100.0), ppt("a", -1.1)
    doc = figure(inner, edge)
    fonts = get_font_index()
    assert relabel.relabel(doc, relabel.find_journal("New Phytologist"), fonts) == [2]
    r = Resolver(doc, fonts)
    for it in (inner, edge):
        need = r.resolve({**it, "text": {**it["text"], "wrap": False}}).autofit_frame
        assert it["frame"][2] >= (need[2] if need else it["frame"][2]) - 1e-6, "wide enough for one line"
    x, _, w, _ = inner["frame"]
    assert abs((x + w / 2) - (100.0 + 9.3 / 2)) < 1e-6, "its centre where it was"
    x, _, w, _ = edge["frame"]
    need = r.resolve({**edge, "text": {**edge["text"], "wrap": False}}).autofit_frame[2]
    assert abs(x + w / 2 - (need - 14.4) / 2) < 1e-6, "its text starts at the page's edge"


def test_the_boxes_are_fitted_for_an_export_without_a_copy(tmp_path, monkeypatch, capsys):
    """Fitted whether or not the relabelled document is saved too (a plain --journal export)."""
    src = tmp_path / "fig.mosaic"
    docfile.save(figure(label("a")), str(src))
    seen = []
    real = relabel.relabel
    monkeypatch.setattr(relabel, "relabel", lambda doc, journal, fonts=None: seen.append(fonts) or real(doc, journal, fonts))
    assert cli.main(["export", str(src), "--journal", "New Phytologist", "--json"]) == 0
    assert cli.main(["export", str(src), "--journal", "New Phytologist", "--dry-run", "--json"]) == 0
    assert seen[0] is not None and seen[1] is None
    capsys.readouterr()


def test_quick_set_p_values_follow_the_journal_and_hand_changes_stay():
    import json
    from mosaic.journals import p_styles
    from mosaic.relabel import find_journal, relabel
    styles = p_styles()
    capital = next(n for n, v in styles.items() if v.get("letter") == "P")
    sig = lambda runs: json.dumps([[r["t"], bool(r.get("italic"))] for r in runs], separators=(",", ":"))   # noqa: E731
    as_set = [{"t": "p", "italic": True}, {"t": " < 0.05"}]
    edited = [{"t": "p", "italic": True}, {"t": " < 0.04"}]
    bracket = lambda i, runs, label, pset_runs: {"id": i, "type": "bracket", "frame": [10, 10, 60, 13], "label": label, "dir": "up",   # noqa: E731
                                                 "text": {"paragraphs": [{"runs": runs}]}, "pset": {"v": "0.05", "sig": sig(pset_runs)}}
    doc = {"mosaic": 1, "meta": {}, "assets": {}, "pages": [{"id": "pg", "width": 500, "height": 500, "items": [
        bracket("a", as_set, "p < 0.05", as_set), bracket("b", edited, "p < 0.04", as_set)]}]}
    relabel(doc, find_journal(capital))
    a, b = doc["pages"][0]["items"]
    assert a["label"] == "P < 0.05" and a["text"]["paragraphs"][0]["runs"] == [{"t": "P", "italic": True}, {"t": " < 0.05"}]
    assert a["pset"]["sig"] == sig(a["text"]["paragraphs"][0]["runs"])   # (still as set: it follows the next journal too)
    assert b["label"] == "p < 0.04" and "pset" not in b   # changed by hand: kept, no longer a quick-set
    # The figure's own choice of letter wins
    doc["meta"]["p_letter"] = "p"
    relabel(doc, find_journal(capital))
    assert doc["pages"][0]["items"][0]["label"] == "p < 0.05"

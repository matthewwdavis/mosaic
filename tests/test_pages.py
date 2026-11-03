import json

import pytest

from figassemble import journals, model

MM = 72 / 25.4


def test_new_pages_are_a4():
    page = model.new_page()
    assert page["width"] == pytest.approx(210 * MM)
    assert page["height"] == pytest.approx(297 * MM)
    assert page["preset"] == {"standard": "A4"}


def test_journal_figure_sizes():
    assert journals.journal_size("Nature", "Single column") == pytest.approx((90 * MM, 170 * MM))
    assert journals.journal_size("Nature", "Double column") == pytest.approx((180 * MM, 170 * MM))
    assert journals.journal_size("Science", "2 columns") == pytest.approx((121 * MM, 199 * MM))
    assert journals.journal_size("Cell", "Full width") == pytest.approx((174 * MM, 200 * MM))
    assert journals.journal_size("PNAS", "1.5 columns") == pytest.approx((114 * MM, 225 * MM))
    assert journals.journal_size("G3", "Double column") == journals.journal_size("Genetics", "Double column")
    assert journals.journal_size("PLOS Genetics", "Full width") == pytest.approx((190.5 * MM, 222.3 * MM))
    names = [j["name"] for j in journals.JOURNALS]
    assert len(names) == 14 and names == sorted(names, key=str.lower)
    for j in journals.JOURNALS:
        types = [t["name"] for t in j["types"]]
        assert len(types) == len(set(types)) and j["depth_mm"] > 0 and j["source"]
        assert all(0 < t["width_mm"] < 200 for t in j["types"])


def test_slide_and_poster_sizes():
    # PowerPoint's slides (16:9 its default, exactly 960 x 540 pt; 4:3 its old Standard; 16:10) and
    # the usual conference posters, each in its group of the size lists, the groups in order
    assert journals.standard_size("Slide 16:9") == pytest.approx((960, 540), abs=0.001)
    assert journals.standard_size("Slide 4:3") == pytest.approx((10 * 72, 7.5 * 72))
    assert journals.standard_size("Slide 16:10") == pytest.approx((10 * 72, 6.25 * 72))
    assert journals.standard_size("Poster 48 × 36 in") == pytest.approx((48 * 72, 36 * 72))
    assert journals.standard_size("Poster A0") == pytest.approx((841 * MM, 1189 * MM))
    groups = [s["group"] for s in journals.STANDARD_SIZES]
    assert [g for i, g in enumerate(groups) if not i or groups[i - 1] != g] == ["Paper", "Slides", "Posters"]
    assert journals.preset_size({"journal": "Nature", "type": "Single column"}) == pytest.approx((90 * MM, 170 * MM))
    assert journals.preset_size({"standard": "Tabloid"}) is None and journals.preset_size(None) is None


def test_new_documents_start_at_the_size_settings_give(tmp_path, monkeypatch):
    from figassemble.app.api import Api
    monkeypatch.setenv("FIGASSEMBLE_HOME", str(tmp_path))
    api = Api()
    assert api.new_document()["pages"][0]["preset"] == {"standard": "A4"}
    api.prefs_set({"new_page": {"standard": "Slide 16:9"}})
    page = api.new_document()["pages"][0]
    assert (page["width"], page["height"]) == pytest.approx((960, 540), abs=0.001)
    assert page["preset"] == {"standard": "Slide 16:9"}
    api.prefs_set({"new_page": {"journal": "Nature", "type": "Double column"}})
    page = api.new_document()["pages"][0]
    assert (page["width"], page["height"]) == pytest.approx((180 * MM, 170 * MM))
    assert page["preset"] == {"journal": "Nature", "type": "Double column"}
    # A size this version doesn't have (a newer version's) gives A4
    api.prefs_set({"new_page": {"standard": "Tabloid"}})
    assert api.new_document()["pages"][0]["preset"] == {"standard": "A4"}
    # Choosing A4 again leaves no choice of its own in the settings file
    api.prefs_set({"new_page": {"standard": "A4"}})
    assert "new_page" not in json.loads((tmp_path / "prefs.json").read_text())


def test_old_settings_files_switch_to_centimetres(tmp_path, monkeypatch):
    from figassemble.app.api import Api
    monkeypatch.setenv("FIGASSEMBLE_HOME", str(tmp_path))
    # Version 1 wrote every default, including points, alongside real choices
    (tmp_path / "prefs.json").write_text(json.dumps({"units": "pt", "theme": "dark", "recent": []}))
    api = Api()
    prefs = api.prefs_get()
    assert prefs["units"] == "cm" and prefs["theme"] == "dark"
    stored = json.loads((tmp_path / "prefs.json").read_text())
    assert stored == {"theme": "dark", "prefs_version": 2}
    # A real choice of points sticks; choosing the default again removes it from the file
    assert api.prefs_set({"units": "pt"})["units"] == "pt"
    assert api.prefs_set({"units": "cm"})["units"] == "cm"
    assert "units" not in json.loads((tmp_path / "prefs.json").read_text())


def test_guides_are_never_exported(cache, tmp_path):
    import pikepdf
    from figassemble.export.run import export_document
    outputs = []
    for guides in ({"x": [], "y": []}, {"x": [36.0, 100.0], "y": [50.0]}):
        doc = model.new_document("guides")
        page = doc["pages"][0]
        page["width"], page["height"] = 200.0, 120.0
        page["guides"] = guides
        page["items"].append({"id": "it_box", "type": "shape", "geom": "rect", "frame": [36, 50, 64, 40], "rot": 0,
                              "stroke": {"color": "#000000", "width": 1}, "fill": None})
        out = export_document(doc, str(tmp_path / f"g{len(guides['x'])}"), ["pdf", "svg"], cache=cache)
        pdf = pikepdf.open(out["files"][0])
        svg = open(out["files"][1], encoding="utf-8").read()
        outputs.append((pdf.pages[0].Contents.read_bytes(), svg))
    assert outputs[0] == outputs[1]


def test_layout_aid_settings(tmp_path, monkeypatch):
    from figassemble.app.api import Api
    monkeypatch.setenv("FIGASSEMBLE_HOME", str(tmp_path))
    api = Api()
    prefs = api.prefs_get()
    # Rulers and guides show, the grid doesn't; snapping is on; the grid is 1 cm squares of 1 mm lines
    assert (prefs["show_rulers"], prefs["show_guides"], prefs["show_grid"], prefs["snap"]) == (True, True, False, True)
    assert prefs["grid"]["spacing"] == pytest.approx(10 * MM) and prefs["grid"]["subdivisions"] == 10
    api.prefs_set({"show_grid": True, "snap": False})
    stored = json.loads((tmp_path / "prefs.json").read_text())
    assert stored["show_grid"] is True and stored["snap"] is False and "show_rulers" not in stored


def test_recovery_copies_can_be_listed_and_deleted(tmp_path, monkeypatch):
    from figassemble.app.api import Api
    monkeypatch.setenv("FIGASSEMBLE_HOME", str(tmp_path))
    api = Api()
    doc = model.new_document("Figure 3 draft")
    doc["pages"][0]["items"].append(model.text_item("a", 2, 2))
    api.autosave(doc, "doc-old")
    api.autosave(model.new_document("Other"), "doc-now")
    kept = api.autosaved(exclude_key="doc-now")     # this session's own copy is left out
    assert [(k["title"], k["pages"], k["objects"]) for k in kept] == [("Figure 3 draft", 1, 1)]
    assert kept[0]["bytes"] > 0
    outside = tmp_path / "not-an-autosave.figasm"
    outside.write_text("keep me")
    left = api.delete_autosaves([kept[0]["path"], str(outside)], exclude_key="doc-now")
    assert left == [] and outside.exists()               # only FigAssemble's own copies go
    assert [k["title"] for k in api.autosaved()] == ["Other"]

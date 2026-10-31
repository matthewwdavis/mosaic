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

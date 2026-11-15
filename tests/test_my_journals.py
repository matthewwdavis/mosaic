"""Your own journals (Size > My Journals; mosaic/journals.py over the shared _labapp/journals.py):
a name, figure widths and a depth, kept in the settings folder and listed with the built-in ones."""
import json
import os

import pytest

from mosaic import journals, model
from mosaic.app.api import Api

MINE = {"name": "Tree Genetics & Genomes", "depth_mm": 234, "types": [{"name": "Single column", "width_mm": "84"},
                                                                       {"name": "Double column", "width_mm": 174}]}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    yield Api()
    journals.load_user()   # (the next test's settings folder: none of these)


def test_a_journal_of_your_own_is_kept_and_listed_with_the_others(api):
    built_in = len(journals.JOURNALS)
    got = api.user_journals_save([MINE])
    assert [j["name"] for j in got["mine"]] == ["Tree Genetics & Genomes"] and got["mine"][0]["user"] is True
    assert got["mine"][0]["types"][0]["width_mm"] == 84.0 and len(got["journals"]) == built_in + 1
    names = [j["name"] for j in api.app_info()["journals"]]
    assert "Tree Genetics & Genomes" in names and names == sorted(names, key=str.lower)
    w, h = journals.journal_size("Tree Genetics & Genomes", "Double column")
    assert abs(w - 174 * journals.MM) < 1e-9 and abs(h - 234 * journals.MM) < 1e-9
    page = model.new_page(preset={"journal": "Tree Genetics & Genomes", "type": "Single column"})
    assert abs(page["width"] - 84 * journals.MM) < 1e-6
    assert json.load(open(os.path.join(os.environ["MOSAIC_HOME"], "journals.json")))["journals"][0]["name"] == MINE["name"]
    assert [j["name"] for j in Api().user_journals()] == [MINE["name"]]   # (still there the next time mosaic starts)


def test_what_cannot_be_a_journal_says_why_and_changes_nothing(api):
    api.user_journals_save([MINE])
    for bad, why in (({**MINE, "name": " "}, "name"), ({**MINE, "name": "nature"}, "already listed"),
                     ({**MINE, "types": []}, "at least one"), ({**MINE, "depth_mm": "deep"}, "millimetres"),
                     ({**MINE, "types": [{"name": "a", "width_mm": 0}]}, "between"),
                     ({**MINE, "types": [{"name": "a", "width_mm": 80}, {"name": "A", "width_mm": 90}]}, "own name")):
        with pytest.raises(ValueError, match=why):
            api.user_journals_save([MINE, bad] if bad["name"].strip().lower() not in ("", "nature") else [bad])
    with pytest.raises(ValueError, match="own name"):
        api.user_journals_save([MINE, dict(MINE)])
    assert [j["name"] for j in api.user_journals()] == [MINE["name"]]


def test_deleting_one_takes_it_off_the_lists_and_a_page_keeps_its_size(api):
    api.user_journals_save([MINE])
    page = model.new_page(preset={"journal": MINE["name"], "type": "Double column"})
    api.user_journals_save([])
    assert not any(j.get("user") for j in journals.JOURNALS) and api.user_journals() == []
    assert journals.preset_size(page["preset"]) is None and abs(page["width"] - 174 * journals.MM) < 1e-6


def test_a_file_changed_by_hand_cannot_break_the_lists(api):
    path = os.path.join(os.environ["MOSAIC_HOME"], "journals.json")
    with open(path, "w") as fh:
        fh.write('{"journals": [{"name": "Good", "depth_mm": 200, "types": [{"name": "w", "width_mm": 80}]}, {"name": "Science"}, 7, {"depth_mm": 3}]}')
    assert [j["name"] for j in journals.load_user() if j.get("user")] == ["Good"]
    with open(path, "w") as fh:
        fh.write("not json")
    assert not any(j.get("user") for j in journals.load_user())

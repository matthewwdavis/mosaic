"""The journal lists are grouped by publisher, as prose's Journal menu groups them: the shared
table's "publisher" for each journal (bioRxiv "In house"), your own under "My journals"; the
groups, and the journals in each, in alphabetical order (mosaic/journals.py grouped(), and
journalGroups in the editor's inspector.js, which the editor self-test checks)."""
import json

import pytest

from mosaic import cli, docfile, journals, model
from mosaic.app.api import Api

# prose's Journal menu, as it groups the journals both apps know (its own templates aside)
PROSE_GROUPS = [
    ("AAAS (Science)", ["Science"]),
    ("BMC (Springer Nature)", ["Genome Biology"]),
    ("Cell Press", ["Cell", "Molecular Plant"]),
    ("Cold Spring Harbor Laboratory Press", ["Genome Research"]),
    ("Genetics Society of America", ["G3", "Genetics"]),
    ("In house", ["bioRxiv"]),
    ("National Academy of Sciences", ["PNAS"]),
    ("Oxford University Press", ["Horticulture Research", "Molecular Biology and Evolution", "Plant Cell"]),
    ("PLOS", ["PLOS Genetics"]),
    ("Springer Nature", ["Heredity", "Nature"]),
    ("Wiley", ["New Phytologist", "The Plant Journal"]),
]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    yield Api()
    journals.load_user()


def test_the_journals_are_grouped_by_publisher_in_prose_s_order():
    built_in = [j for j in journals.JOURNALS if not j.get("user")]
    assert all(j.get("publisher") for j in built_in), "every journal in the shared table has its publisher"
    assert [(g, [j["name"] for j in js]) for g, js in journals.grouped(built_in)] == PROSE_GROUPS


def test_your_own_journals_are_a_group_of_their_own(api):
    api.user_journals_save([{"name": "Tree Genetics & Genomes", "depth_mm": 234, "types": [{"name": "Single column", "width_mm": 84}]},
                            {"name": "American Journal of Botany", "depth_mm": 230, "types": [{"name": "Single column", "width_mm": 84}]}])
    groups = [(g, [j["name"] for j in js]) for g, js in journals.grouped(api.app_info()["journals"])]
    assert ("My journals", ["American Journal of Botany", "Tree Genetics & Genomes"]) in groups
    order = [g for g, _ in groups]
    assert order == sorted(order, key=str.lower) and order.index("My journals") == order.index("In house") + 1
    assert all(j.get("publisher") for j in api.app_info()["journals"] if not j.get("user")), "the editor gets each publisher"


def test_a_journal_mosaic_does_not_know_lists_the_ones_it_does_by_publisher(tmp_path, capsys):
    src = tmp_path / "fig.mff"
    docfile.save(model.new_document("Fig"), str(src))
    assert cli.main(["export", str(src), "--journal", "Nature Plants", "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert "by publisher" in err and "  Springer Nature: Heredity, Nature" in err and "  In house: bioRxiv" in err
    assert err.index("AAAS (Science)") < err.index("Wiley")

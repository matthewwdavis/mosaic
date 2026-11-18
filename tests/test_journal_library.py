"""Size > Find a Journal… and My Journals > Share… (journals.py, the shared library's
journallibrary.py): journals found by name, ISSN or abbreviation across mosaic's, your own and the
library's; one from the library fetched the first time it's chosen, listed "From the library" with
its badge, and sizing a page; offline said; sharing a pull request through gh. A fake library (a
folder) and a fake gh: nothing reaches the network or GitHub."""
import base64
import json
import os
import subprocess
import sys

import pytest

from mosaic import journals
from mosaic._labapp import fakegh, fakelibrary, journallibrary

no_gh_on_windows = pytest.mark.skipif(os.name == "nt", reason="the fake gh is a script")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    os.makedirs(tmp_path / "home")
    journals.load_user()
    yield tmp_path
    monkeypatch.undo()
    journals.load_user()


@pytest.fixture
def library(home):
    return fakelibrary.make(home / "library")


def test_find_a_journal_by_issn_name_or_abbreviation(home, library):
    journallibrary.refresh(library, journals.library_cache())
    got = journals.find(library, "1614-2950")
    assert [(r["name"], r["where"], r["verified"], r["listed"]) for r in got] == [("Tree Genetics & Genomes", "library", "community", None)]
    pnas = journals.find(library, "Proceedings of the National Academy of Sciences")[0]
    assert pnas["listed"] == "PNAS" and pnas["where"] == "built_in" and pnas["verified"] == "verified"
    assert journals.find(library, "0028-0836")[0]["listed"] == "Nature"


def test_a_library_journal_is_fetched_listed_and_sizes_a_page(home, library, tmp_path):
    entry = journals.use_library_journal(library, "tree_genetics_genomes")
    assert entry["name"] == "Tree Genetics & Genomes" and entry["library"] is True and entry["verified"] == "community"
    assert entry["publisher"] == journals.FROM_LIBRARY and journals.group_of(entry) == journals.FROM_LIBRARY
    listed = next(j for j in journals.JOURNALS if j["name"] == "Tree Genetics & Genomes")
    assert listed is entry or listed == entry
    w, h = journals.journal_size("Tree Genetics & Genomes", "Double column")
    assert abs(w - 174 * journals.MM) < 1e-6 and abs(h - 234 * journals.MM) < 1e-6
    assert os.path.isfile(os.path.join(journals.library_cache(), "journals", "tree_genetics_genomes@1.0.0.json"))
    # Offline for good: the library gone, it's still listed after a restart
    os.rename(library, str(tmp_path / "unplugged"))
    journals.load_user()
    assert any(j["name"] == "Tree Genetics & Genomes" for j in journals.JOURNALS)
    assert journals.find(library, "tree genet")[0]["where"] == "fetched"


def test_offline_the_first_time_is_said(home, tmp_path):
    with pytest.raises(journallibrary.OfflineError, match="needs a connection the first time"):
        journals.use_library_journal(str(tmp_path / "unplugged drive"), "tree_genetics_genomes")


def test_a_library_journal_named_like_one_of_yours_keeps_yours(home, library):
    journals.save_user([{"name": "Tree Genetics & Genomes", "depth_mm": 200, "types": [{"name": "One", "width_mm": 80}]}])
    journallibrary.fetch("tree_genetics_genomes", source=library, cache=journals.library_cache())
    journals.load_user()
    trees = [j for j in journals.JOURNALS if j["name"] == "Tree Genetics & Genomes"]
    assert len(trees) == 1 and trees[0].get("user") and trees[0]["depth_mm"] == 200
    journals.save_user([])


@no_gh_on_windows
def test_share_offers_your_journal_as_a_pull_request(home, monkeypatch, tmp_path):
    journals.save_user([{"name": "Selftest Trees", "depth_mm": 230, "types": [{"name": "Single column", "width_mm": 84}]}])
    folder = str(tmp_path / "gh")
    monkeypatch.setenv("LABAPP_GH", fakegh.make(folder, {
        "GET user": {"login": "bob"}, "GET repos/lab/journals": {"permissions": {"push": False}},
        "GET repos/lab/journals/pulls?state=open&per_page=100": [], "POST repos/lab/journals/forks": {}, "GET repos/bob/journals": {},
        "POST repos/bob/journals/merge-upstream": {}, "GET repos/bob/journals/git/ref/heads/main": {"object": {"sha": "s"}},
        "POST repos/bob/journals/git/refs": {}, "PUT repos/bob/journals/contents/journals/selftest_trees.json": {},
        "POST repos/lab/journals/pulls": {"html_url": "https://github.com/lab/journals/pull/2"}}))
    got = journals.share_user_journal("github:lab/journals", "Selftest Trees")
    assert got["pull_request"] == "https://github.com/lab/journals/pull/2"
    put = next(c for c in fakegh.calls(folder) if c["method"] == "PUT")
    sent = json.loads(base64.b64decode(put["body"]["content"]))
    assert sent["name"] == "Selftest Trees" and sent["verified"]["status"] == "community"
    assert "shared from mosaic by @bob" in fakegh.calls(folder)[-1]["body"]["body"]
    journals.save_user([])


def test_share_to_a_lab_folder_writes_it_in(home):
    folder = home / "lab library"
    folder.mkdir()
    journals.save_user([{"name": "Selftest Trees", "depth_mm": 230, "types": [{"name": "Single column", "width_mm": 84}]}])
    got = journals.share_user_journal(str(folder), "Selftest Trees")
    assert "pull_request" not in got and "lab library" in got["where"]
    index = json.loads((folder / "index.json").read_text())
    assert index["format"] == 2 and index["journals"][0]["id"] == "selftest_trees"
    journals.save_user([])


def test_the_api_never_reads_github_from_a_test_copy(home, monkeypatch):
    from mosaic.app.api import Api
    api = Api.__new__(Api)
    monkeypatch.setattr(Api, "prefs_get", lambda self: {"journal_library": ""})
    assert api._library_offline() is True
    got = api.find_journals("nature", True)
    assert got["offline"] is True and got["results"][0]["name"] == "Nature"
    with pytest.raises(ValueError, match="test copy"):
        api.user_journal_share("Anything")


def test_the_find_dialogs_words():
    """journalfind.js's helpers, run in Node."""
    import shutil
    node = shutil.which("node") or os.path.join(os.path.dirname(sys.executable), "node")
    if not os.path.isfile(node):
        pytest.skip("no Node here")
    import pathlib
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # (a file:// address: Node takes a Windows path's drive letter, D:, for an address's scheme)
    module = pathlib.Path(here, "mosaic", "ui", "js", "journalfind.js").as_uri()
    code = ("import('" + module + "').then((m) => {"
            "const [n, b, line] = m.describeResult({name: 'Tree', verified: 'community', publisher: 'Springer', issn: ['1614-2942'], where: 'library'});"
            "const t = m.typeLabels({types: [{name: 'Single column', width_mm: 84}], depth_mm: 234});"
            "console.log(JSON.stringify([n, b.label, line, t]));})")
    # (Node writes UTF-8; Windows would read it in its own code page and garble "·" and "×")
    out = subprocess.run([node, "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert json.loads(out) == ["Tree", "Community", "Springer · ISSN 1614-2942 · from the library",
                               [{"type": "Single column", "label": "Single column (84 mm × 234 mm)"}]]

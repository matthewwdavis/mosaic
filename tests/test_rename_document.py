"""Renaming a document's file (File > Rename…, the title bar's name on a Mac): where it is, the
extension kept, never over another file, Open Recent and the window's record following."""
import os

import pytest

from mosaic.app.api import Api, _same_file


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))   # (its own Open Recent)
    return Api()


@pytest.fixture
def docs(tmp_path):
    """The documents' folder (the settings are beside it)."""
    d = tmp_path / "docs"
    d.mkdir()
    return d


def saved(folder, name, data=b"figure"):
    p = folder / name
    p.write_bytes(data)
    return str(p)


def test_a_rename_keeps_the_folder_extension_and_contents(api, docs):
    old = saved(docs, "figure_3.mosaic")
    res = api.rename_document(old, "figure_4")
    assert res == {"path": str(docs / "figure_4.mosaic")}
    assert not os.path.exists(old) and (docs / "figure_4.mosaic").read_bytes() == b"figure"
    # Typing the extension too is the same; a FigAssemble document keeps its own
    assert api.rename_document(res["path"], " figure_5.mosaic ") == {"path": str(docs / "figure_5.mosaic")}
    legacy = saved(docs, "old.figasm")
    assert api.rename_document(legacy, "older") == {"path": str(docs / "older.figasm")}


def test_names_that_cant_be_taken_are_refused_and_nothing_changes(api, docs):
    old = saved(docs, "a.mosaic")
    saved(docs, "b.mosaic", b"another figure")
    assert "already a file called b.mosaic" in api.rename_document(old, "b")["error"]
    for bad in ["", "   ", "sub/name", "back\\slash", "co:lon", ".hidden"]:
        assert "error" in api.rename_document(old, bad), bad
    assert (docs / "a.mosaic").read_bytes() == b"figure" and (docs / "b.mosaic").read_bytes() == b"another figure"
    assert sorted(os.listdir(docs)) == ["a.mosaic", "b.mosaic"]
    gone = str(docs / "gone.mosaic")
    assert "isn't in its folder any more" in api.rename_document(gone, "c")["error"]


def test_a_change_of_case_alone_renames(api, docs):
    old = saved(docs, "figure.mosaic")
    res = api.rename_document(old, "Figure")
    assert res == {"path": str(docs / "Figure.mosaic")}
    assert "Figure.mosaic" in os.listdir(docs) and "figure.mosaic" not in os.listdir(docs)
    assert api.rename_document(res["path"], "Figure") == res   # (the same name: nothing to do)


def test_open_recent_and_the_windows_record_follow(api, docs):
    old, other = saved(docs, "a.mosaic"), saved(docs, "other.mosaic")
    api.prefs_set({"recent": [other, old]})
    api._win_state["1"] = {"path": _same_file(old), "dirty": True, "name": "a"}
    new = api.rename_document(old, "renamed")["path"]
    assert api.prefs_get()["recent"] == [other, new]   # (in its place)
    assert api._win_state["1"]["path"] == _same_file(new) and api._win_state["1"]["dirty"] is True

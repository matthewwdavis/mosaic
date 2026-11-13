"""Copies kept against crashes and mistakes (mosaic/app/kept.py): earlier versions of a file
saved over, a history of recovery copies, recovering as the document it was, and the limits."""
import json
import os
import time

import pytest

from mosaic import docfile, model
from mosaic.app import closing, kept
from mosaic.app.api import Api


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    return Api()


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    return d


def doc(title="Figure"):
    return model.new_document(title)


def aged(path, seconds_ago):
    """Make a file look saved some time ago."""
    t = time.time() - seconds_ago
    os.utime(path, (t, t))


def test_saving_over_a_file_keeps_it_as_an_earlier_version(api, docs):
    path = str(docs / "fig.mosaic")
    api.save_document(doc("one"), path)
    assert kept.listing(path)["versions"] == []   # (nothing there before)
    aged(path, 120)
    first = os.path.getmtime(path)
    api.save_document(doc("two"), path)
    versions = kept.listing(path)["versions"]
    assert len(versions) == 1 and versions[0]["modified"] == pytest.approx(first, abs=1)
    assert api.read_kept(versions[0]["path"])["doc"]["meta"]["title"] == "one"
    assert path in api.prefs_get()["recent"] and versions[0]["path"] not in api.prefs_get()["recent"]


def test_a_files_last_versions_are_kept_and_autosave_keeps_fewer(api, docs, monkeypatch):
    monkeypatch.setattr(kept, "VERSION_KEEP", 3)
    path = str(docs / "fig.mosaic")
    for k in range(6):
        api.save_document(doc(str(k)), path)
        aged(path, 3600 - k * 60)   # (each save a minute after the one before)
    titles = [api.read_kept(v["path"])["doc"]["meta"]["title"] for v in kept.listing(path)["versions"]]
    assert titles == ["4", "3", "2"]   # newest first; the file itself is "5"
    # AutoSave's own saves, seconds apart: one version at most every 10 minutes
    other = str(docs / "auto.mosaic")
    for k in range(4):
        api.save_document(doc(str(k)), other, auto=True)
    assert len(kept.listing(other)["versions"]) == 1


def test_recovery_copies_keep_a_history_and_their_document(api, docs, monkeypatch):
    path = str(docs / "fig.mosaic")
    api.save_document(doc("saved"), path)
    api.autosave(doc("edit 1"), "doc-abc1", path)
    api.autosave(doc("edit 2"), "doc-abc1", path)   # (seconds later: not kept in the history)
    assert len(api.recovery_history("doc-abc1")) == 1
    monkeypatch.setattr(kept, "HISTORY_EVERY", 0)
    monkeypatch.setattr(kept, "HISTORY_KEEP", 2)
    for k in range(3, 6):
        api.autosave(doc(f"edit {k}"), "doc-abc1", path)
        time.sleep(0.01)
    history = api.recovery_history("doc-abc1")
    assert [api.read_kept(c["path"])["doc"]["meta"]["title"] for c in history] == ["edit 5", "edit 4"]
    listed = next(s for s in api.autosaved() if s["key"] == "doc-abc1")
    assert listed["doc_path"] == path and listed["title"] == "fig.mosaic"
    assert [c["path"] for c in kept.listing(path)["history"]] == [c["path"] for c in history]   # (Browse Versions)


def test_saving_lets_the_recovery_copy_go_and_deleting_it_its_history(api):
    api.autosave(doc("unsaved"), "doc-k1", None)
    api.autosave(doc("unsaved"), "doc-k2", None)
    home = os.path.join(os.environ["MOSAIC_HOME"], "autosave")
    api.discard_autosave("doc-k1")
    assert not os.path.exists(os.path.join(home, "doc-k1.mosaic")) and not os.path.exists(os.path.join(home, "doc-k1.json"))
    assert len(api.recovery_history("doc-k1")) == 1   # (its history stays, pruned by age)
    api._unlock_autosave("doc-k2")   # (as if from an earlier session)
    api.delete_autosaves([os.path.join(home, "doc-k2.mosaic")])
    assert api.recovery_history("doc-k2") == [] and not os.path.exists(os.path.join(home, "doc-k2.json"))


def test_only_mosaics_own_copies_are_read_back(api, docs):
    path = str(docs / "fig.mosaic")
    docfile.save(doc(), path)
    with pytest.raises(ValueError):
        api.read_kept(path)
    with pytest.raises(ValueError):
        api.read_kept(os.path.join(os.environ["MOSAIC_HOME"], "autosave", "..", "..", "docs", "fig.mosaic"))


def test_a_renamed_file_keeps_its_versions(api, docs):
    path = str(docs / "fig.mosaic")
    api.save_document(doc("one"), path)
    aged(path, 60)
    api.save_document(doc("two"), path)
    new = api.rename_document(path, "renamed")["path"]
    assert len(kept.listing(new)["versions"]) == 1 and kept.listing(path)["versions"] == []


def test_old_history_goes_and_past_the_limit_the_oldest(api, docs, monkeypatch):
    monkeypatch.setattr(kept, "HISTORY_EVERY", 0)
    api.autosave(doc("old"), "doc-old1", None)
    for c in api.recovery_history("doc-old1"):
        aged(c["path"], 15 * 86400)
    path = str(docs / "fig.mosaic")
    for k in range(3):
        api.save_document(doc(str(k)), path)
        aged(path, 3600 - k * 60)
    kept.prune()
    assert api.recovery_history("doc-old1") == [] and len(kept.listing(path)["versions"]) == 2
    one = kept.listing(path)["versions"][0]["bytes"]
    monkeypatch.setattr(kept, "KEPT_LIMIT", one)   # room for one
    kept.prune()
    assert [api.read_kept(v["path"])["doc"]["meta"]["title"] for v in kept.listing(path)["versions"]] == ["1"]


def test_closing_a_figure_with_autosave_on_saves_without_asking(api, monkeypatch):
    class Window:
        confirm_close = True
    w = Window()
    api._windows["1"] = w
    api._caller = type("Caller", (), {"win": "1"})()
    api.doc_state("/tmp/fig.mosaic", True, "fig", autosave=True)
    asked, answered = [], []
    monkeypatch.setattr(closing, "_show", lambda *a: asked.append(a))
    monkeypatch.setattr(closing, "answer", lambda window, choice, then: answered.append(choice))
    closing.ask(api, w, lambda ok: None)
    assert answered == ["save"] and asked == []
    api.doc_state(None, True, "Untitled", autosave=True)   # (never saved: it asks, as before)
    closing.ask(api, w, lambda ok: None)
    assert len(asked) == 1


def test_recovery_notes_are_json(api):
    api.autosave(doc(), "doc-j1", "/somewhere/fig.mosaic")
    with open(os.path.join(os.environ["MOSAIC_HOME"], "autosave", "doc-j1.json"), encoding="utf-8") as fh:
        assert json.load(fh) == {"path": "/somewhere/fig.mosaic"}

"""Help > Report a Problem (mosaic/diagnostics.py): a report file with the versions, the system,
the settings and the log's end, and nothing of the person's figures or file names."""
import json
import os
import zipfile

import pytest

from mosaic import diagnostics
from mosaic.app.api import Api


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "settings"))
    monkeypatch.setenv("HOME", str(tmp_path / "person"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "person"))
    (tmp_path / "person" / "Desktop").mkdir(parents=True)
    monkeypatch.setattr(diagnostics.d, "log", None)
    return tmp_path / "person"


def test_the_report_says_what_helps_and_nothing_private(home, monkeypatch):
    api = Api()
    monkeypatch.setattr(api, "reveal", lambda path: True)
    api.prefs_set({"recent": [str(home / "Thesis" / "secret_figure.mosaic")], "units": "mm"})
    monkeypatch.setattr(diagnostics.d, "log", diagnostics.d.new_log())
    api.log_error(f"TypeError: x is undefined, opening {home}/Thesis/secret_figure.mosaic")
    got = api.problem_report("It froze when I exported.")
    assert got["folder"] == "Desktop" and os.path.dirname(got["path"]) == str(home / "Desktop")
    assert got["name"].startswith("mosaic-report-") and got["name"].endswith(".zip")
    with zipfile.ZipFile(got["path"]) as z:
        assert sorted(z.namelist()) == ["README.txt", "log.txt", "report.json"]
        info, text = json.loads(z.read("report.json")), z.read("log.txt").decode()
        whole = b"".join(z.read(n) for n in z.namelist()).decode()
    assert info["app"] == "mosaic" and info["format"] == 1 and info["version"] and info["notes"] == "It froze when I exported."
    assert info["system"]["platform"] and info["system"]["python"] and "pikepdf" in info["libraries"]
    assert info["settings"]["units"] == "mm" and "recent" not in info["settings"]
    assert "editor: TypeError: x is undefined" in text and "(a .mosaic file)" in text
    assert "secret_figure" not in whole   # (nor the names of the person's files, in the log or the settings)
    assert str(home) not in whole   # the home folder (the account's name) is written ~


def test_the_log_starts_again_when_it_is_full(home, monkeypatch):
    monkeypatch.setattr(diagnostics.d, "log_bytes", 200)
    log = diagnostics.d.new_log()
    for k in range(20):
        log.write(f"line {k} of some length to fill the file\n")
    assert os.path.getsize(diagnostics.log_path()) < 400 and os.path.exists(diagnostics.log_path() + ".1")
    lines = open(diagnostics.log_path(), encoding="utf-8").read().splitlines()
    assert lines[-1].endswith("line 19 of some length to fill the file") and lines[-1][:4].isdigit()   # (dated)


def test_the_sample_figure_opens_as_a_figure_of_its_own(home):
    """Help > Open the Sample Figure, and the first window the first time mosaic runs."""
    api = Api()
    assert api.app_info()["first_run"] is True   # (no settings yet)
    doc = api.sample_document()
    page = doc["pages"][0]
    assert doc["meta"]["title"] == "Sample figure" and len(doc["assets"]) == 4
    assert sum(it["type"] == "picture" for it in page["items"]) == 4 and page["alt"].startswith("Four panels")
    assert all(v.get("src") is None for a in doc["assets"].values() for v in a["variants"].values())   # stored, not linked
    api.prefs_set({"units": "mm"})
    assert Api().app_info()["first_run"] is False   # (settings now: not the first run any more)

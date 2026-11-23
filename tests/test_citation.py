"""How to cite mosaic: CITATION.cff (GitHub and Zenodo read it), its copy that Help > Cite mosaic
reads, .zenodo.json, and the reference copied to the clipboard."""
import json
import os

import pytest

from mosaic import __version__
from mosaic.app import clipboard as cb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_citation_file_and_its_copy_agree_with_the_version():
    from mosaic._labapp import citation
    assert read("CITATION.cff") == read("mosaic", "data", "CITATION.cff")
    cff = citation.read_cff(read("CITATION.cff"))
    assert cff["version"] == __version__ and cff["title"] == "mosaic" and cff["license"] == "MIT"
    assert cff["authors"] == [{"family-names": "Davis", "given-names": "Matthew"}]
    assert cff["repository-code"] == "https://github.com/matthewwdavis/mosaic"
    # (the README shows the same reference)
    apa = citation.formats(cff)["apa"]
    assert f"Davis, M. ({cff['date-released'][:4]}). *mosaic* (Version {__version__}) [Computer software]." in read("README.md")
    assert apa.startswith("Davis, M. (")


def test_zenodo_record():
    z = json.loads(read(".zenodo.json"))
    assert z["title"] == "mosaic" and z["upload_type"] == "software" and z["creators"] == [{"name": "Davis, Matthew"}]
    assert "version" not in z   # (Zenodo takes each release's tag)
    form = read(".github", "ISSUE_TEMPLATE", "paper.yml")
    assert "name: Add a paper that used mosaic" in form and "required: true" in form
    assert "issues/new?template=paper.yml" in read("README.md")


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("MOSAIC_FAKE_CLIPBOARD", "1")
    monkeypatch.setattr(cb, "_fake", None)
    return cb.backend()


def test_help_cite_copies_the_reference(fake):
    from mosaic.app.api import Api
    api = Api()
    c = api.citation()
    assert c["apa"].startswith("Davis, M. (") and f"(Version {__version__})" in c["apa"]
    assert c["bibtex"].startswith("@software{Davis_mosaic_") and c["ris"].startswith("TY  - COMP")
    assert api.copy_text(c["apa"], c["apa_html"]) is True
    assert fake.get("text") == c["apa"] and "<i>mosaic</i>" in fake.get("html")
    assert cb.put_text(None, "x") is False   # (no clipboard of mosaic's own: the page copies it)

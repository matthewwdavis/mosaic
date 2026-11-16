"""mosaic's documents are .mff ("mosaic figure file"); older ones (.mosaic until November 2026, .figasm
from when mosaic was called FigAssemble) open everywhere a document opens and save under their own
names, as Word keeps a .doc a .doc until Save As (docfile.py has the one list of extensions)."""
import json
import os
import zipfile

import pytest

from mosaic import cli, docfile, model
from mosaic.app import kept
from mosaic.app.api import Api

LEGACY = [".mosaic", ".figasm"]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    return Api()


def test_one_new_extension_and_the_older_ones():
    assert docfile.EXTENSION == ".mff"
    assert list(docfile.LEGACY_EXTENSIONS) == LEGACY
    assert docfile.EXTENSIONS == (".mff", ".mosaic", ".figasm")
    for name in ("a.mff", "a.MFF", "a.mosaic", "b.Mosaic", "c.figasm"):
        assert docfile.has_extension(name)
    assert not docfile.has_extension("a.pdf") and not docfile.has_extension("mff")
    assert docfile.extension_of("/x/Fig.MOSAIC") == ".MOSAIC" and docfile.extension_of("fig.pdf") == ""
    assert docfile.strip_extension("fig 2.mosaic") == "fig 2" and docfile.strip_extension("fig.pdf") == "fig.pdf"
    assert docfile.with_extension("/x/fig") == "/x/fig.mff" and docfile.with_extension("/x/fig.figasm") == "/x/fig.figasm"
    assert docfile.with_extension("/x/fig.v2") == "/x/fig.v2.mff"


def test_a_new_document_saves_as_mff(api, tmp_path):
    res = api.save_document(model.new_document("New"), str(tmp_path / "fig-new"))
    assert res["path"] == str(tmp_path / "fig-new.mff") and docfile.is_document(res["path"])
    assert api.save_dialog.__defaults__[0] == "Untitled.mff"   # (Save's suggested name)
    info = api.app_info()
    assert info["doc_ext"] == ".mff" and info["doc_exts"] == [".mff", ".mosaic", ".figasm"]


@pytest.mark.parametrize("ext", LEGACY)
def test_an_older_document_opens_and_saves_under_its_own_name(api, tmp_path, ext):
    path = str(tmp_path / f"fig-old{ext}")
    docfile.save(model.new_document("Old"), path)
    opened = api.open_document(path)
    assert opened["path"] == path
    opened["doc"]["pages"][0]["items"].append(model.text_item("changed", 72, 72))
    assert api.save_document(opened["doc"], path)["path"] == path
    assert sorted(os.listdir(tmp_path)) == [f"fig-old{ext}", "home"]   # (no .mff beside it)
    assert len(docfile.load(path)["pages"][0]["items"]) == 1
    assert api.prefs_get()["recent"][0] == path
    # Renamed, it keeps its extension; a name typed with it too is the same
    assert api.rename_document(path, "fig-renamed") == {"path": str(tmp_path / f"fig-renamed{ext}")}
    assert api.rename_document(str(tmp_path / f"fig-renamed{ext}"), f"fig-again{ext}") == {"path": str(tmp_path / f"fig-again{ext}")}


def test_open_offers_every_extension(api):
    class Window:
        def create_file_dialog(self, kind, allow_multiple=False, file_types=()):
            self.types = file_types
            return None
    w = Window()
    api.window = w
    api.open_dialog("document")
    shown = w.types[0]
    for ext in (".mff", ".mosaic", ".figasm", ".pptx"):
        assert f"*{ext}" in shown


@pytest.mark.parametrize("ext", [".mff", *LEGACY])
def test_each_extension_opens_from_the_finder_and_drops(api, tmp_path, ext):
    path = str(tmp_path / f"sent{ext}")
    docfile.save(model.new_document("Sent"), path)
    assert api._system_open([path]) == []   # (before any window: kept for the first)
    assert api.launch_documents() == [path]
    pages = api.figure_pages(path)   # (dropped on a page)
    assert pages["name"] == "sent" and len(pages["pages"]) == 1


def test_a_recovery_copy_left_as_mosaic_is_offered_and_kept_writing(api):
    home = os.path.join(os.environ["MOSAIC_HOME"], "autosave")
    os.makedirs(home)
    left = os.path.join(home, "doc-old1.mosaic")   # (as an earlier mosaic left it)
    docfile.save(model.new_document("Left behind"), left, prune=False)
    with open(os.path.join(home, "doc-old1.json"), "w") as fh:
        json.dump({"path": None}, fh)
    api.autosave(model.new_document("New work"), "doc-new1")
    api._unlock_autosave("doc-new1")
    got = {c["key"]: c for c in api.autosaved()}
    assert set(got) == {"doc-old1", "doc-new1"}
    assert os.path.basename(got["doc-new1"]["path"]) == "doc-new1.mff" and got["doc-old1"]["title"] == "Left behind"
    assert kept.is_kept(left) and api.read_kept(left)["doc"]["meta"]["title"] == "Left behind"
    # Recovered into a window: it goes on writing that copy, never a second one
    api.claim_autosave("doc-old1")
    api.autosave(model.new_document("Recovered"), "doc-old1")
    assert sorted(n for n in os.listdir(home) if n.startswith("doc-old1.") and not n.endswith((".lock", ".json"))) == ["doc-old1.mosaic"]
    api.discard_autosave("doc-old1")
    assert not os.path.exists(left)
    assert [c["key"] for c in api.delete_autosaves([got["doc-new1"]["path"]])] == []


def test_versions_kept_as_mosaic_count_and_keep_their_files(api, tmp_path):
    from PIL import Image
    png = tmp_path / "plot.png"
    Image.new("RGB", (40, 30), (200, 30, 30)).save(png)
    d = model.new_document("With a picture")
    [asset] = api.add_files([str(png)])
    d["assets"][asset["asset_id"]] = asset["asset"]
    d["pages"][0]["items"].append(model.picture_item(asset["asset_id"], asset["asset"], 10, 10))
    path = str(tmp_path / "fig.mosaic")
    api.save_document(d, path)
    api.save_document(d, path)   # (the first kept as an earlier version)
    [version] = kept.listing(path)["versions"]
    # As an earlier mosaic named its kept copies: still listed, read back, and its files stay
    older = version["path"][:-len(docfile.EXTENSION)] + ".mosaic"
    os.rename(version["path"], older)
    kept.prune()
    [listed] = kept.listing(path)["versions"]
    assert listed["path"] == older and kept.is_kept(older)
    assert api.read_kept(older)["doc"]["pages"][0]["items"][0]["type"] == "picture"


def test_the_command_line_reads_every_extension_and_names_new_files_mff(tmp_path, capsys):
    for ext in (".mff", *LEGACY):
        src = tmp_path / f"cli{ext}"
        docfile.save(model.new_document(f"CLI {ext}"), str(src))
        assert cli.main(["info", str(src), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["title"] == f"CLI {ext}"
    # A relabelled copy named without an extension: .mff; one named .mosaic stays .mosaic
    src = tmp_path / "cli.mosaic"
    assert cli.main(["export", str(src), "--journal", "Nature", "--copy", str(tmp_path / "copy-a"), "-f", "svg"]) == 0
    assert (tmp_path / "copy-a.mff").is_file()
    assert cli.main(["export", str(src), "--journal", "Nature", "--copy", str(tmp_path / "copy-b.mosaic"),
                     "-o", str(tmp_path / "copy-b-out"), "-f", "svg"]) == 0
    assert (tmp_path / "copy-b.mosaic").is_file() and not (tmp_path / "copy-b.mosaic.mff").exists()


def test_the_sample_figure_is_an_mff():
    data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mosaic", "data")
    assert os.path.isfile(os.path.join(data, "sample.mff")) and not os.path.exists(os.path.join(data, "sample.mosaic"))
    with zipfile.ZipFile(os.path.join(data, "sample.mff")) as z:
        assert docfile.DOC_NAME in z.namelist()


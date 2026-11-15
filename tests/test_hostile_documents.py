"""A document file is somebody else's data: the names it gives its placed files (a SHA-256 and a
file kind) become paths in mosaic's cache, so anything else is refused, both when the document
is opened (nothing written outside the cache) and when it is saved (nothing read from outside it)."""
import json
import os
import zipfile

import pytest

from mosaic import docfile, model
from mosaic.assets import AssetCache


def _write(path, doc, files=()):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(docfile.DOC_NAME, json.dumps(doc))
        for name, data in files:
            z.writestr(name, data)


def _doc_with_variant(kind, sha):
    doc = model.new_document()
    doc["assets"]["a1"] = {"name": "plot", "variants": {kind: {"sha256": sha}}}
    return doc


@pytest.mark.parametrize("kind, sha", [
    ("/../../../../escaped.txt", "ab" * 32),      # a kind that climbs out of the cache
    ("pdf", "../../"),                            # a hash that does
    ("pdf", "AB" * 32),                           # not a lower-case SHA-256
    ("ssh/id_ed25519", "../../"),
])
def test_a_document_naming_paths_is_refused_on_open(tmp_path, kind, sha):
    cache = AssetCache(str(tmp_path / "home" / "cache"))
    path = str(tmp_path / "bad.mosaic")
    name = f"assets/{sha}{'.' + kind}"
    _write(path, _doc_with_variant(kind, sha), [(name, b"attacker bytes")])
    with pytest.raises(ValueError):
        docfile.load(path, cache)
    written = [os.path.join(d, f) for d, _, fs in os.walk(tmp_path) for f in fs]
    assert written == [path]   # nothing but the document itself, in or out of the cache


def test_a_document_naming_paths_embeds_nothing_on_save(tmp_path):
    cache = AssetCache(str(tmp_path / "home" / "cache"))
    secret = tmp_path / "home" / "secret.key"
    secret.write_bytes(b"private")
    doc = _doc_with_variant("key", "../secret")   # cache/../secret.key
    out = str(tmp_path / "out.mosaic")
    with pytest.raises(ValueError):
        docfile.save(doc, out, cache, prune=False)
    assert not os.path.exists(out)


def test_ordinary_names_still_work(tmp_path):
    cache = AssetCache(str(tmp_path / "cache"))
    sha, dst = cache.put_bytes(b"%PDF-1.4", "pdf")
    assert cache.path(sha, "pdf") == dst and cache.has(sha, "pdf")


def test_saving_over_a_file_keeps_placed_files_only_it_still_holds(tmp_path):
    """The cache emptied and the linked file gone: the bytes come from the file being saved over."""
    cache = AssetCache(str(tmp_path / "cache"))
    sha, _ = cache.put_bytes(b"%PDF-1.4 a plot", "pdf")
    doc = model.new_document()
    doc["assets"]["a1"] = {"name": "plot.pdf", "variants": {"pdf": {"sha256": sha}}}
    doc["pages"][0]["items"].append({"id": "p1", "type": "picture", "asset": "a1", "frame": [0, 0, 10, 10]})
    path = str(tmp_path / "fig.mosaic")
    assert docfile.save(doc, path, cache, prune=False) == []
    empty = AssetCache(str(tmp_path / "cache2"))
    assert docfile.save(doc, path, empty, prune=False) == []
    with zipfile.ZipFile(path) as z:
        assert z.read(f"assets/{sha}.pdf") == b"%PDF-1.4 a plot"


def test_a_failed_save_leaves_nothing_beside_the_document(tmp_path, monkeypatch):
    cache = AssetCache(str(tmp_path / "cache"))
    out = tmp_path / "docs"
    out.mkdir()
    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError(28, "No space left on device")))
    with pytest.raises(OSError):
        docfile.save(model.new_document(), str(out / "fig.mosaic"), cache)
    assert os.listdir(out) == []

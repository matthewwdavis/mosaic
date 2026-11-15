"""mosaic/_labapp is a copy of the shared library (labapp's tools/vendor.py makes it). It must be
exactly what was copied: a change belongs in labapp, then copied again."""
import hashlib
import json
import os

import mosaic

COPY = os.path.join(os.path.dirname(os.path.abspath(mosaic.__file__)), "_labapp")


def _files():
    out = {}
    for folder, dirs, names in os.walk(COPY):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            if name.endswith((".pyc", ".pyo")) or name in ("VENDORED.json", ".DS_Store", "claude-commands.log"):
                continue
            path = os.path.join(folder, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, COPY).replace(os.sep, "/")] = hashlib.sha256(fh.read()).hexdigest()
    return out


def test_the_copy_is_as_it_was_copied():
    with open(os.path.join(COPY, "VENDORED.json"), encoding="utf-8") as fh:
        listed = json.load(fh)
    assert listed["version"] and _files() == listed["files"], "mosaic/_labapp was edited in place: change labapp and run its tools/vendor.py"


def test_the_copy_matches_labapp_when_it_is_beside_mosaic():
    """On the computer the library is developed on: the copy isn't behind it."""
    source = os.path.join(os.path.dirname(os.path.dirname(COPY)), os.pardir, "labapp", "labapp")
    if not os.path.isdir(source):
        import pytest
        pytest.skip("labapp isn't beside mosaic here")
    theirs = {}
    for folder, dirs, names in os.walk(source):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            if name.endswith((".pyc", ".pyo")) or name in (".DS_Store", "claude-commands.log"):
                continue
            path = os.path.join(folder, name)
            with open(path, "rb") as fh:
                theirs[os.path.relpath(path, source).replace(os.sep, "/")] = hashlib.sha256(fh.read()).hexdigest()
    assert _files() == theirs, "mosaic/_labapp is behind labapp: run labapp's tools/vendor.py"

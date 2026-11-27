"""An installed mosaic has every file of the shared library's copy (mosaic/_labapp) that isn't Python:
pyproject.toml's package data takes each one in. labapp's web parts (_labapp/web: the button
callouts' tips.js and tips.css) were left out on 27 Nov 2026, and an installed mosaic's editor didn't
start (its main script imports tips.js)."""
import fnmatch
import os
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "mosaic")


def _patterns():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        conf = tomllib.load(fh)["tool"]["setuptools"]
    return conf["package-data"]["mosaic"], conf.get("exclude-package-data", {}).get("mosaic", [])


def _taken(rel, patterns):
    # (setuptools' globs: ** across folders, * within one)
    for p in patterns:
        if "**" in p:
            if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p.replace("**/", "")):
                return True
        elif fnmatch.fnmatch(rel, p) and rel.count("/") == p.count("/"):
            return True
    return False


def test_every_file_of_the_shared_copy_is_installed():
    take, leave = _patterns()
    missing = []
    for folder, dirs, names in os.walk(os.path.join(PKG, "_labapp")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            rel = os.path.relpath(os.path.join(folder, name), PKG).replace(os.sep, "/")
            if name.endswith((".py", ".pyc")) or name in ("claude-commands.log", ".DS_Store") or _taken(rel, leave):
                continue
            if not _taken(rel, take):
                missing.append(rel)
    assert not missing, f"not in pyproject.toml's package data, so not installed: {missing}"

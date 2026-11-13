"""Copies kept against crashes and mistakes, in mosaic's settings folder (fonts.config_dir):

- **Recovery history** (autosave/history/<window's key>/): every HISTORY_EVERY seconds of
  editing, the recovery copy the editor has just written (api.autosave) is kept too, so a
  figure can be taken back to how it was a while ago, not only to the newest copy. A document's
  last HISTORY_KEEP are kept, for HISTORY_DAYS.
- **Earlier versions of saved files** (versions/<the file's key>/): each time a document is
  saved over, the file as it was is kept first, with its own time. A file's last VERSION_KEEP are
  kept; AutoSave's own saves (every few seconds) keep one at most every VERSION_AUTO_EVERY seconds.

Each folder has an info.json saying which document it's for. Past KEPT_LIMIT bytes all
together, the oldest go first. Nothing here is ever a document's only copy.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile

from .. import docfile
from ..fonts import config_dir

HISTORY_EVERY = 600              # s between the recovery copies kept in a document's history
HISTORY_KEEP = 18                # a document's last 18: 3 hours of editing
HISTORY_DAYS = 14                # days a history is kept
VERSION_KEEP = 10                # earlier versions kept of each saved file
VERSION_AUTO_EVERY = 600         # s between the versions AutoSave's own saves keep
KEPT_LIMIT = 2 * 1024 ** 3       # bytes of history and versions together


def history_root() -> str:
    return os.path.join(config_dir(), "autosave", "history")


def versions_root() -> str:
    return os.path.join(config_dir(), "versions")


def _same(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))


def file_key(path: str) -> str:
    """The versions folder's name for a document file."""
    return hashlib.sha1(_same(path).encode("utf-8")).hexdigest()[:16]


def _copies(folder: str) -> list[tuple[str, float, int]]:
    """The copies in a folder, newest first: (path, time, bytes)."""
    if not os.path.isdir(folder):
        return []
    out = []
    for n in os.listdir(folder):
        if n.endswith(docfile.EXTENSION):
            p = os.path.join(folder, n)
            try:
                out.append((p, os.path.getmtime(p), os.path.getsize(p)))
            except OSError:
                pass
    return sorted(out, key=lambda c: c[1], reverse=True)


def _info(folder: str) -> dict:
    try:
        with open(os.path.join(folder, "info.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _set_info(folder: str, **values) -> None:
    info = {**_info(folder), **values}
    with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh)


def _keep(src: str, folder: str, when: float, every: float = 0) -> str | None:
    """Copy src into folder, named and dated by `when` (its modification time is kept), unless
    the newest copy there is less than `every` seconds older, or is this very file already."""
    copies = _copies(folder)
    if copies:
        newest, size = copies[0][1], copies[0][2]
        if (newest == when and size == os.path.getsize(src)) or (every and 0 <= when - newest < every):
            return None
    os.makedirs(folder, exist_ok=True)
    stem = time.strftime("%Y%m%d-%H%M%S", time.localtime(when))
    dest, n = os.path.join(folder, stem + docfile.EXTENSION), 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(folder, f"{stem}-{n}{docfile.EXTENSION}")
    shutil.copy2(src, dest)
    os.utime(dest, (when, when))
    return dest


def _trim(folder: str, keep: int) -> None:
    for p, _, _ in _copies(folder)[keep:]:
        os.remove(p)   # one of mosaic's own kept copies


def keep_history(recovery: str, key: str, doc_path: str | None, title: str | None = None) -> str | None:
    """A recovery copy just written: kept in its document's history too if the last one kept is
    HISTORY_EVERY seconds old. Returns the copy kept, if one was."""
    folder = os.path.join(history_root(), key)
    kept = _keep(recovery, folder, time.time(), HISTORY_EVERY)
    if os.path.isdir(folder):
        _set_info(folder, path=doc_path, title=title)
    if kept:
        _trim(folder, HISTORY_KEEP)
        prune()
    return kept


def keep_version(path: str, auto: bool = False, title: str | None = None) -> str | None:
    """A document file about to be saved over: kept as it is first (AutoSave's own saves: at
    most one every VERSION_AUTO_EVERY seconds). Returns the copy kept, if one was."""
    if not os.path.isfile(path):
        return None
    folder = os.path.join(versions_root(), file_key(path))
    kept = _keep(path, folder, os.path.getmtime(path), VERSION_AUTO_EVERY if auto else 0)
    if kept:
        _set_info(folder, path=os.path.abspath(path), title=title)
        _trim(folder, VERSION_KEEP)
        prune()
    return kept


def moved(old: str, new: str) -> None:
    """A document file renamed: its earlier versions go with it, and its histories say so."""
    src, dest = os.path.join(versions_root(), file_key(old)), os.path.join(versions_root(), file_key(new))
    if os.path.isdir(src) and not os.path.exists(dest):
        os.rename(src, dest)
        _set_info(dest, path=os.path.abspath(new))
    root, was = history_root(), _same(old)
    if os.path.isdir(root):
        for key in os.listdir(root):
            folder = os.path.join(root, key)
            if os.path.isdir(folder) and _info(folder).get("path") and _same(_info(folder)["path"]) == was:
                _set_info(folder, path=os.path.abspath(new))


def forget_history(key: str) -> None:
    """A recovery copy deleted on purpose: its history goes too."""
    folder = os.path.join(history_root(), key)
    if os.path.isdir(folder) and os.path.dirname(os.path.realpath(folder)) == os.path.realpath(history_root()):
        shutil.rmtree(folder)   # mosaic's own kept copies


def _entry(copy: tuple[str, float, int]) -> dict:
    """A kept copy as listed: {"path", "modified", "bytes", "pages", "objects"} (counts None if unreadable)."""
    p, t, b = copy
    pages = objects = None
    try:
        with zipfile.ZipFile(p) as z:
            got = json.loads(z.read(docfile.DOC_NAME)).get("pages", [])
        pages, objects = len(got), sum(len(pg.get("items", [])) for pg in got)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        pass
    return {"path": p, "modified": t, "bytes": b, "pages": pages, "objects": objects}


def listing(doc_path: str | None = None, key: str | None = None) -> dict:
    """What's kept of a document: {"versions": its file's earlier versions, "history": the
    recovery copies kept while editing it (this window's, by `key`, and earlier sessions' of the
    same file)}, each newest first (_entry)."""
    versions = [_entry(c) for c in _copies(os.path.join(versions_root(), file_key(doc_path)))] if doc_path else []
    history, root = [], history_root()
    if os.path.isdir(root):
        same = _same(doc_path) if doc_path else None
        for k in os.listdir(root):
            folder = os.path.join(root, k)
            p = _info(folder).get("path") if os.path.isdir(folder) else None
            if k == key or (same and p and _same(p) == same):
                history += [_entry(c) for c in _copies(folder)]
    return {"versions": versions, "history": sorted(history, key=lambda e: e["modified"], reverse=True)}


def history_of(key: str) -> list[dict]:
    """One window's (or earlier session's) kept recovery copies, newest first."""
    return [_entry(c) for c in _copies(os.path.join(history_root(), key))]


def is_kept(path: str) -> bool:
    """Whether a path is one of mosaic's own copies (recovery copies, their history, earlier
    versions): what may be read back as a figure without becoming the document's file."""
    real = os.path.realpath(path)
    roots = [os.path.realpath(r) for r in (os.path.join(config_dir(), "autosave"), versions_root())]
    return real.endswith(docfile.EXTENSION) and any(real.startswith(r + os.sep) for r in roots) and os.path.isfile(real)


def prune() -> None:
    """Histories older than HISTORY_DAYS go; then, past KEPT_LIMIT bytes, the oldest copies."""
    now, every = time.time(), []
    for root, is_history in ((history_root(), True), (versions_root(), False)):
        if not os.path.isdir(root):
            continue
        for k in os.listdir(root):
            folder = os.path.join(root, k)
            for p, t, b in _copies(folder):
                if is_history and now - t > HISTORY_DAYS * 86400:
                    os.remove(p)   # one of mosaic's own kept copies
                else:
                    every.append((t, b, p))
            if os.path.isdir(folder) and not _copies(folder):
                shutil.rmtree(folder)   # (only its info.json was left)
    total = sum(b for _, b, _ in every)
    for t, b, p in sorted(every):
        if total <= KEPT_LIMIT:
            break
        os.remove(p)
        total -= b

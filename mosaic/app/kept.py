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

A kept copy holds the figure's layout only; the files placed in it are kept once, in
kept-assets/ (store_root), however many copies use them: as hard links to the cache's own copies
where the disk allows, so they take no room of their own while the cache has them and stay when
it doesn't. A copy is read back with load(). Placed files no copy uses any more go when copies
do (_sweep). Copies kept before this (whole documents) read back as they are; should a copy not
be writable this way, the whole document is kept instead.

The parts any app's kept copies need (files kept once as hard links, sweeping, small JSON files, a
file's key) are the shared library's (_labapp/kept.py).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import zipfile

from .. import docfile
from .._labapp import kept as _shared
from ..assets import get_cache
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


def store_root() -> str:
    """Where the files placed in kept copies are, once each: <sha[:2]>/<sha><ext>."""
    return os.path.join(config_dir(), "kept-assets")


_ASSET_RE = re.compile(r"[0-9a-f]{64}\.[a-z0-9]{1,8}")   # a placed file's name in a document: its hash and kind
_MARK = b"mosaic-kept bytes="                            # a slim copy's zip comment, with its document's size
_SWEEP_GRACE = 3600                                      # s a stored file stays although no copy uses it (yet)


def _store(z: zipfile.ZipFile, member: zipfile.ZipInfo, name: str) -> None:
    """Keep one placed file of a document in the store, unless it's there: a hard link to the
    cache's copy of it if there is one, else its bytes from the document."""
    dest = os.path.join(store_root(), name[:2], name)
    if os.path.exists(dest):
        return
    if not _shared.link(os.path.join(get_cache().root, name[:2], name), dest, size=member.file_size):
        with z.open(member) as src:   # (not in the cache)
            _shared.copy_stream(src, dest)


def _slim(src: str, dest: str) -> None:
    """Keep the document src as dest: its layout, with its placed files in the store."""
    tmp = dest + ".tmp"   # (a name _sweep reads too: its placed files are in use from the start)
    try:
        with zipfile.ZipFile(src) as z, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            out.comment = _MARK + str(os.path.getsize(src)).encode()
            members = z.infolist()
            for m in members:   # the layout first, so the placed files are spoken for before they're stored
                if not (m.filename.startswith("assets/") and _ASSET_RE.fullmatch(m.filename[len("assets/"):])):
                    out.writestr(m.filename, z.read(m))
        with zipfile.ZipFile(src) as z:
            for m in z.infolist():
                name = m.filename[len("assets/"):]
                if m.filename.startswith("assets/") and _ASSET_RE.fullmatch(name):
                    _store(z, m, name)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)   # this copy's own unfinished file
        raise


def _bytes(path: str) -> int:
    """The size of the document a kept copy is of (a slim copy's own file is much smaller)."""
    try:
        with zipfile.ZipFile(path) as z:
            if z.comment.startswith(_MARK):
                return int(z.comment[len(_MARK):])
    except (OSError, ValueError, zipfile.BadZipFile):
        pass
    return os.path.getsize(path)


def _uses(path: str) -> set[str] | None:
    """The stored files a kept copy needs (their names); None if it can't be read."""
    try:
        with zipfile.ZipFile(path) as z:
            doc = json.loads(z.read(docfile.DOC_NAME))
        out = set()
        for asset in (doc.get("assets") or {}).values():
            for kind, var in (asset.get("variants") or {}).items():
                out.add(f"{var['sha256']}{docfile.KIND_EXT.get(kind, '.' + kind)}")
        return out
    except (OSError, ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile):
        return None


def _sweep() -> None:
    """Stored files no kept copy uses go (ones just stored wait: their copy may be on its way)."""
    root = store_root()
    if not os.path.isdir(root):
        return
    used: set[str] = set()
    for top in (history_root(), versions_root()):
        for folder, _, names in os.walk(top):
            for n in names:
                if n.endswith((docfile.EXTENSION, docfile.EXTENSION + ".tmp")):
                    got = _uses(os.path.join(folder, n))
                    if got is None and not n.endswith(".tmp"):
                        return   # a copy that can't be read: nothing is removed on its account
                    used |= got or set()
    _shared.sweep(root, used, _SWEEP_GRACE)   # mosaic's own stored files, used by no kept copy


def _stored_bytes() -> int:
    return _shared.tree_bytes(store_root())


def load(path: str) -> dict:
    """A kept copy as a document, its placed files back in the cache."""
    return docfile.load(path, assets_dir=store_root())


_same = _shared.same_path


def file_key(path: str) -> str:
    """The versions folder's name for a document file."""
    return _shared.path_key(path)


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
    got = _shared.read_json(os.path.join(folder, "info.json"), {})
    return got if isinstance(got, dict) else {}


def _set_info(folder: str, **values) -> None:
    _shared.write_json(os.path.join(folder, "info.json"), {**_info(folder), **values})


def _keep(src: str, folder: str, when: float, every: float = 0) -> str | None:
    """Copy src into folder, named and dated by `when` (its modification time is kept), unless
    the newest copy there is less than `every` seconds older, or is this very file already."""
    copies = _copies(folder)
    if copies:
        newest, size = copies[0][1], _bytes(copies[0][0])
        if (newest == when and size == os.path.getsize(src)) or (every and 0 <= when - newest < every):
            return None
    os.makedirs(folder, exist_ok=True)
    stem = time.strftime("%Y%m%d-%H%M%S", time.localtime(when))
    dest, n = os.path.join(folder, stem + docfile.EXTENSION), 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(folder, f"{stem}-{n}{docfile.EXTENSION}")
    try:
        _slim(src, dest)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        shutil.copy2(src, dest)   # (not a document that can be kept slim: kept whole)
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
    return {"path": p, "modified": t, "bytes": _bytes(p), "pages": pages, "objects": objects}


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
    """Histories older than HISTORY_DAYS go; then, past KEPT_LIMIT bytes (the copies and the
    files placed in them, each counted once), the oldest copies; then placed files none uses."""
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
    _sweep()
    every.sort()
    total = sum(b for _, b, _ in every)
    while every and total + _stored_bytes() > KEPT_LIMIT:
        t, b, p = every.pop(0)
        os.remove(p)   # the oldest of mosaic's own kept copies
        total -= b
        _sweep()

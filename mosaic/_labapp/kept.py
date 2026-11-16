"""What the apps' kept copies (recovery copies, their history, earlier versions) are built from.

Each app keeps its copies in its own form (mosaic: slim mosaic documents by the document's path;
prose: the saved parts by the document's id), so those stay in the apps. What they share is here:

- files kept **once each**, named by their content (sha256.ext): put into a folder as hard links
  where the disk allows (no room of their own while the original is there, and they stay when it
  isn't), else as copies written whole or not at all (link, link_all, copy_stream);
- **sweeping** the ones nothing uses any more, and the room a folder takes (sweep, tree_bytes);
- which copies to **keep as they age** (thin: all from the last hour, then one an hour, a day, a
  week, a month);
- small JSON files written whole or not at all (write_json, read_json);
- one name for a file however it's spelled (same_path, path_key);
- **who has a folder open** (OwnerLocks): a lock the system frees however the app stops, so a
  folder whose lock is free was left by a crash.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import threading
import time

from .oslock import try_lock, unlock

HOUR, DAY = 3600, 86400


# Small files ------------------------------------------------------------------------------------

def write_json(path: str, data, indent: int | None = None) -> None:
    """A JSON file written beside itself first, then moved into place (never half a file)."""
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path: str, default=None):
    """A JSON file's contents; `default` when it isn't there or can't be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


# One name for a file -----------------------------------------------------------------------------

def same_path(path: str) -> str:
    """A path as one spelling: absolute, links followed, and case folded where the system does."""
    return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))


def path_key(path: str) -> str:
    """A short folder name for a file, the same however its path is spelled."""
    return hashlib.sha1(same_path(path).encode("utf-8")).hexdigest()[:16]   # noqa: S324 (a name, not a secret)


def safe_name(name: str) -> bool:
    """A plain file name: no folders, not hidden."""
    return bool(name) and "/" not in name and "\\" not in name and not name.startswith(".") and name == os.path.basename(name)


# Files kept once each ----------------------------------------------------------------------------

def link(src: str, dest: str, size: int | None = None) -> bool:
    """Put src at dest as a hard link, else a copy (written beside it, then moved into place).
    Left alone if dest is there; False if src isn't a file (or, given `size`, isn't that size)."""
    if os.path.exists(dest):
        return True
    try:
        if not os.path.isfile(src) or (size is not None and os.path.getsize(src) != size):
            return False
    except OSError:
        return False
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    try:
        os.link(src, dest)
        return True
    except FileExistsError:
        return True
    except OSError:   # (a disk without hard links, or another disk)
        pass
    tmp = f"{dest}.{os.getpid()}.tmp"
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return True


def copy_stream(src, dest: str) -> None:
    """An open file's bytes written to dest, whole or not at all."""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = f"{dest}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as out:
            shutil.copyfileobj(src, out)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def link_all(src_dir: str, names, dst_dir: str) -> None:
    """Files from one folder into another by name (link). Ones already there are left; names
    that aren't plain file names are skipped."""
    os.makedirs(dst_dir, exist_ok=True)
    for name in set(names or []):
        if safe_name(name):
            link(os.path.join(src_dir, name), os.path.join(dst_dir, name))


def sweep(folder: str, used, grace: float = 0) -> int:
    """Remove the files under `folder` whose names aren't in `used` (ones newer than `grace`
    seconds wait: what uses them may be on its way). How many went."""
    used, now, gone = set(used), time.time(), 0
    for where, _, names in os.walk(folder):
        for n in names:
            if n in used:
                continue
            p = os.path.join(where, n)
            try:
                st = os.stat(p)
                if now - max(st.st_ctime, st.st_mtime) > grace:
                    os.remove(p)
                    gone += 1
            except OSError:
                pass
    return gone


def tree_bytes(folder: str) -> int:
    """The bytes of the files under a folder."""
    total = 0
    for where, _, names in os.walk(folder):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(where, n))
            except OSError:
                pass
    return total


# Which copies to keep as they age ------------------------------------------------------------------

def thin(items: list[dict], now: float, time_key: str = "t", keep_key: str = "label") -> list[dict]:
    """Which copies to keep (newest first): every one from the last hour, then the newest of each
    hour for a day, of each day for a month, of each week for a year, of each month after. One
    with a value under keep_key (a name someone gave it) is kept whatever its age."""
    out, taken = [], set()
    for e in sorted(items, key=lambda e: e[time_key], reverse=True):
        age = now - e[time_key]
        if age < HOUR or e.get(keep_key):
            out.append(e)
            continue
        when = _dt.datetime.fromtimestamp(e[time_key])
        if age < DAY:
            bucket = ("hour", when.strftime("%Y%m%d%H"))
        elif age < 30 * DAY:
            bucket = ("day", when.strftime("%Y%m%d"))
        elif age < 365 * DAY:
            year, week, _ = when.isocalendar()
            bucket = ("week", f"{year}-{week}")
        else:
            bucket = ("month", when.strftime("%Y%m"))
        if bucket not in taken:
            taken.add(bucket)
            out.append(e)
    return out


# Who has a folder open -----------------------------------------------------------------------------

class OwnerLocks:
    """Locks on folders this app has open (a file owner.lock in each), held while it runs. The
    lock is the operating system's, so it frees itself however the app stops; process ids, which
    systems reuse, aren't trusted."""

    NAME = "owner.lock"

    def __init__(self):
        self.held: dict[str, int] = {}   # folder -> its open lock file
        self.guard = threading.Lock()

    def take(self, folder: str) -> bool:
        """Take a folder's lock (kept until release or exit). False if another running app has it."""
        with self.guard:
            if folder in self.held:
                return True
            fd = os.open(os.path.join(folder, self.NAME), os.O_RDWR | os.O_CREAT, 0o600)
            if not try_lock(fd):
                os.close(fd)
                return False
            self.held[folder] = fd
            return True

    def release(self, folder: str) -> None:
        with self.guard:
            fd = self.held.pop(folder, None)
        if fd is not None:
            os.close(fd)   # (closing the file frees the lock)

    def mine(self, folder: str) -> bool:
        return folder in self.held

    def free(self, folder: str) -> bool:
        """Whether nobody has the folder open: not this app, and no other running one."""
        if folder in self.held:
            return False
        try:
            fd = os.open(os.path.join(folder, self.NAME), os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:
            return False
        try:
            if not try_lock(fd):
                return False
            unlock(fd)
            return True
        finally:
            os.close(fd)

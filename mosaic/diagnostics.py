"""What a problem report needs, gathered into one file to send (Help > Report a Problem).

Two parts:

- **The log** (<settings folder>/logs/mosaic.log): what mosaic prints as it runs (failures it
  got past, errors in the editor's page), which an app started from the Dock or Start menu would
  otherwise print nowhere. Kept to LOG_BYTES, the file before it as mosaic.log.1.
- **The report** (report()): a ZIP named <app>-report-<date>-<time>.zip holding
    report.json   {"app", "format": 1, "version", "made", "system": {...}, "install": {...},
                   "libraries": {name: version}, "tools": {name: found or not},
                   "settings": {...}, "notes": what the person typed}
    log.txt       the end of the log
    README.txt    what's in the ZIP and what isn't, in plain words

Nothing of the figures goes in: no documents, no placed files, no file names. The home folder's
path is written "~" wherever it appears, and the settings leave out lists of recent files.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import platform
import sys
import threading
import zipfile

from . import __version__
from .fonts import config_dir

APP = "mosaic"
LOG_BYTES = 1_000_000      # the log file's size before it starts again
LOG_TAIL = 400_000         # bytes of the log that go in a report
LIBRARIES = ("pikepdf", "pypdfium2", "pillow", "lxml", "fonttools", "numpy", "shapely", "skia-pathops",
             "matplotlib", "python-pptx", "pywebview", "cryptography", "PySide6", "QtPy", "pyobjc-core", "pythonnet")
TOOLS = ("gs", "rsvg-convert", "pdftocairo")
PRIVATE_SETTINGS = ("recent", "recent_exports", "recent_folders", "github_user")   # (names of files, folders and accounts)


def log_path() -> str:
    return os.path.join(config_dir(), "logs", f"{APP}.log")


class _Tee(io.TextIOBase):
    """A stream that also writes to the log (and goes on working if the log can't be written)."""

    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        try:
            self.log.write(text)
        except Exception:   # noqa: BLE001
            pass
        try:
            return self.stream.write(text) if self.stream else len(text)
        except Exception:   # noqa: BLE001 (an app with no terminal: nowhere to print)
            return len(text)

    def flush(self):
        for s in (self.stream, self.log):
            try:
                if s:
                    s.flush()
            except Exception:   # noqa: BLE001
                pass

    def isatty(self):
        return False


class _Log:
    """The log file: lines with the time they were written, starting again past LOG_BYTES."""

    def __init__(self, path: str):
        self.path, self.lock, self.start = path, threading.Lock(), True
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(self, text: str) -> None:
        if not text:
            return
        with self.lock:
            try:
                if os.path.exists(self.path) and os.path.getsize(self.path) > LOG_BYTES:
                    os.replace(self.path, self.path + ".1")
            except OSError:
                pass
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ")
            out = []
            for piece in text.splitlines(keepends=True):
                out.append((stamp if self.start else "") + piece)
                self.start = piece.endswith("\n")
            with open(self.path, "a", encoding="utf-8", errors="replace") as fh:
                fh.write("".join(out))

    def flush(self) -> None:
        pass


_log: _Log | None = None


def start_log() -> str | None:
    """From now on what mosaic prints is kept in the log too (once; the app calls this as it
    starts). Returns the log's path, or None if it can't be written."""
    global _log
    if _log is not None:
        return _log.path
    try:
        _log = _Log(log_path())
        _log.write(f"--- mosaic {__version__} started on {platform.platform()} (Python {platform.python_version()})\n")
    except OSError:
        _log = None
        return None
    sys.stdout, sys.stderr = _Tee(sys.stdout, _log), _Tee(sys.stderr, _log)
    return _log.path


def note(text: str) -> None:
    """A line for the log (an error in the editor's page, say); nothing if there's no log."""
    if _log is not None:
        try:
            _log.write(text.rstrip("\n")[:4000] + "\n")
        except OSError:
            pass


def _tidy(text: str) -> str:
    """The home folder's path written as ~ (it holds the account's name)."""
    home = os.path.expanduser("~")
    for h in {home, os.path.realpath(home), home.replace("\\", "/"), home.replace("\\", "\\\\")}:
        if len(h) > 3:
            text = text.replace(h, "~")
    return text


def _libraries() -> dict:
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for name in LIBRARIES:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            pass
    return out


def _tail(path: str, limit: int) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return data if size <= limit else data.split("\n", 1)[-1]   # (from a whole line on)


def gather(settings: dict | None = None, extra: dict | None = None, notes: str = "") -> dict:
    """report.json's contents. `settings`: the app's settings (private ones are left out);
    `extra`: more to say about the installation (the window's kind, the update state)."""
    from .assets import tool_path
    try:
        from .updates import install_kind
        kind = install_kind()
    except Exception:   # noqa: BLE001
        kind = None
    shown = {k: v for k, v in (settings or {}).items() if k not in PRIVATE_SETTINGS}
    return {
        "app": APP, "format": 1, "version": __version__,
        "made": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "system": {"platform": sys.platform, "os": platform.platform(), "machine": platform.machine(),
                   "python": platform.python_version(), "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
                   "wayland": bool(os.environ.get("WAYLAND_DISPLAY")) if sys.platform.startswith("linux") else None},
        "install": {"kind": kind, "prefix": _tidy(sys.prefix), **(extra or {})},
        "libraries": _libraries(),
        "tools": {t: bool(tool_path(t)) for t in TOOLS},
        "settings": json.loads(_tidy(json.dumps(shown, default=str))),
        "notes": notes.strip(),
    }


README = """This is a problem report from {app} {version}, made {made}.

What's in it
  report.json  the version of {app} and of the libraries it uses, the operating system,
               how {app} was installed, its settings, and anything typed in the report's box
  log.txt      the last messages {app} printed while running (errors it met, mostly)

What isn't
  No figures, documents, pictures or plots, and no names of your files or folders.
  Your home folder's path is written as "~".

It's a plain ZIP: open it to see exactly what it holds before sending it.
"""


def report(dest_dir: str, settings: dict | None = None, extra: dict | None = None, notes: str = "") -> str:
    """Write the report ZIP into dest_dir and return its path."""
    info = gather(settings, extra, notes)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f"{APP}-report-{stamp}.zip")
    log = _tail(log_path() + ".1", LOG_TAIL // 4) + _tail(log_path(), LOG_TAIL)
    with zipfile.ZipFile(path + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.json", json.dumps(info, indent=1, ensure_ascii=False))
        z.writestr("log.txt", _tidy(log) or "(nothing logged)\n")
        z.writestr("README.txt", README.format(app=APP, version=info["version"], made=info["made"]))
    os.replace(path + ".tmp", path)
    return path

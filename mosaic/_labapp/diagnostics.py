"""What a problem report needs, gathered into one file to send (Help > Report a Problem), laid out
the same in every app that uses this, so one person can read all their reports.

Two parts:

- **The log** (<settings folder>/logs/<app>.log): what the app prints as it runs (failures it got
  past, errors in the editor's page), which an app started from the Dock or Start menu would
  otherwise print nowhere. Kept to log_bytes, the file before it as <app>.log.1.
- **The report** (report()): a ZIP named <app>-report-<date>-<time>.zip holding
    report.json   {"app", "format": 1, "version", "made", "system": {...}, "install": {...},
                   "libraries": {name: version}, "tools": {name: found or not},
                   "settings": {...}, "notes": what the person typed}
    log.txt       the end of the log
    README.txt    what's in the ZIP and what isn't, in plain words

Nothing of the person's documents goes in. The home folder's path is written "~" wherever it
appears, paths to the person's own files in the log become "(a .pdf file)", and the app says which
of its settings may go in (settings_shown).

An app makes one Diagnostics and keeps it:

    d = Diagnostics("mosaic", __version__, settings_dir=config_dir, libraries=(...),
                    tools=lambda: {...}, settings_shown=..., whats_in="...", whats_not="...")
"""
from __future__ import annotations

import datetime
import io
import json
import os
import platform
import re
import sys
import threading
import traceback
import zipfile

LOG_BYTES = 1_000_000      # the log file's size before it starts again
LOG_TAIL = 400_000         # bytes of the log that go in a report

README = """This is a problem report from {app} {version}, made {made}.

What's in it
{whats_in}
  log.txt      the last messages {app} printed while running (errors it met, mostly)

What isn't
{whats_not}
  Your home folder's path is written as "~".

It's a plain ZIP: open it to see exactly what it holds before sending it.
"""

# A path in the log: quoted ('…', "…"), or bare up to a space; in the home folder (written ~ by then),
# on another disk (/Volumes, /media, /mnt, a Windows drive), or under /Users or /home
_QUOTED = re.compile(r"""(['"])((?:~|/Users/|/home/|/Volumes/|/media/|/mnt/|[A-Za-z]:\\)[^'"\n]*)\1""")
_BARE = re.compile(r"""(?<![\w'"])((?:~[/\\]|/Users/|/home/|/Volumes/|/media/|/mnt/|[A-Za-z]:\\)[^\s'"<>|*?]+)""")
_NAMED = re.compile(r"“[^”\n]{1,200}”")


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


def _whole(exc_type, exc, tb, head: str) -> None:
    """A traceback written in one piece (several threads failing at once otherwise mix theirs line
    by line in the log)."""
    try:
        sys.stderr.write(head + "".join(traceback.format_exception(exc_type, exc, tb)))
    except Exception:   # noqa: BLE001 (nowhere to write it)
        pass


def _thread_hook(args) -> None:
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread is not None else threading.get_ident()
    _whole(args.exc_type, args.exc_value, args.exc_traceback, f"Exception in thread {name}:\n")


def _main_hook(exc_type, exc, tb) -> None:
    _whole(exc_type, exc, tb, "")


class Log:
    """The log file: lines with the time they were written, starting again past `limit` bytes."""

    def __init__(self, path: str, limit=LOG_BYTES):
        self.path, self.lock, self.start = path, threading.Lock(), True
        self.limit = limit   # (a number, or a function giving it)
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(self, text: str) -> None:
        if not text:
            return
        limit = self.limit() if callable(self.limit) else self.limit
        with self.lock:
            try:
                if os.path.exists(self.path) and os.path.getsize(self.path) > limit:
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


def tidy(text: str) -> str:
    """The home folder's path written as ~ (it holds the account's name)."""
    home = os.path.expanduser("~")
    for h in sorted({home, os.path.realpath(home), home.replace("\\", "/"), home.replace("\\", "\\\\")}, key=len, reverse=True):
        if len(h) > 3:
            text = text.replace(h, "~")
    return text


def tail(path: str, limit: int) -> str:
    """The end of a text file, from a whole line on."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return data if size <= limit else data.split("\n", 1)[-1]


def switches_only(prefs: dict, safe_text: tuple = (), groups: tuple = ()) -> dict:
    """The strictest choice of settings for a report: switches and numbers, the text settings
    named in safe_text (choices, not the person's words), and inside the groups named, the same.
    The names of everything left out are listed, so it's clear they exist."""
    out: dict = {}
    for k, v in (prefs or {}).items():
        if isinstance(v, (bool, int, float)) or v is None:
            out[k] = v
        elif isinstance(v, str) and k in safe_text:
            out[k] = v
        elif k in groups and isinstance(v, dict):
            out[k] = {a: b for a, b in v.items()
                      if isinstance(b, (bool, int, float)) or (isinstance(b, str) and len(b) <= 20)}
    left = sorted(k for k in (prefs or {}) if k not in out)
    if left:
        out["(not included)"] = left
    return out


def all_but(prefs: dict, private: tuple = ()) -> dict:
    """A looser choice of settings: everything but the ones named (recent files, accounts)."""
    return {k: v for k, v in (prefs or {}).items() if k not in private}


class Diagnostics:
    """One app's log and problem report.

    app, version      the app's name and version
    settings_dir      its settings folder, or a function giving it (the log goes in logs/ there)
    own_dirs          folders of the app's own (its code, its cache), or a function giving them:
                      paths in them stay in the log, since they say how the app is installed
    libraries         names of the Python packages whose versions the report gives
    tools             a function giving {program: found or not}
    settings_shown    a function taking the app's settings and giving the part a report may hold
    install_kind      a function saying how the app was installed ("app", "source"…)
    whats_in/_not     the README's lines about report.json and about what's left out
    hide_names        also take names the app printed in curly quotes (“paper”) out of the log
    """

    def __init__(self, app: str, version: str, settings_dir, own_dirs=(), libraries: tuple = (), tools=None,
                 settings_shown=None, install_kind=None, whats_in: str = "", whats_not: str = "",
                 hide_names: bool = True):
        self.app, self.version = app, version
        self._settings_dir, self._own_dirs = settings_dir, own_dirs
        self.libraries, self._tools = tuple(libraries), tools
        self._settings_shown = settings_shown or (lambda prefs: switches_only(prefs))
        self._install_kind = install_kind
        self.whats_in = whats_in or ("  report.json  the version of {app} and of the libraries it uses, the operating system,\n"
                                     "               how {app} was installed, and anything typed in the report's box")
        self.whats_not = whats_not or "  None of your documents, and no names of your files or folders."
        self.hide_names = hide_names
        self.log_bytes, self.log_tail = LOG_BYTES, LOG_TAIL
        self.log: Log | None = None

    # The log ----------------------------------------------------------------------------------

    def log_path(self) -> str:
        d = self._settings_dir() if callable(self._settings_dir) else self._settings_dir
        return os.path.join(d, "logs", f"{self.app}.log")

    def new_log(self, path: str | None = None) -> Log:
        return Log(path or self.log_path(), lambda: self.log_bytes)

    def start_log(self) -> str | None:
        """From now on what the app prints is kept in the log too (once; the app calls this as
        it starts). Returns the log's path, or None if it can't be written."""
        if self.log is not None:
            return self.log.path
        try:
            self.log = self.new_log()
            self.log.write(f"--- {self.app} {self.version} started on {platform.platform()} (Python {platform.python_version()})\n")
        except OSError:
            self.log = None
            return None
        sys.stdout, sys.stderr = _Tee(sys.stdout, self.log), _Tee(sys.stderr, self.log)
        threading.excepthook, sys.excepthook = _thread_hook, _main_hook   # (whole tracebacks, not mixed)
        return self.log.path

    def note(self, text: str) -> None:
        """A line for the log (an error in the editor's page, say); nothing if there's no log."""
        if self.log is not None:
            try:
                self.log.write(str(text).rstrip("\n")[:4000] + "\n")
            except OSError:
                pass

    # The report -------------------------------------------------------------------------------

    def own_dirs(self) -> list[str]:
        d = self._settings_dir() if callable(self._settings_dir) else self._settings_dir
        more = self._own_dirs() if callable(self._own_dirs) else self._own_dirs
        return [sys.prefix, d, *more]

    def private(self, text: str) -> str:
        """The log with the names of the person's files and folders taken out: each path to one
        of their own files becomes "(a .pdf file)"; the app's own folders and its environment's
        stay; a name printed in curly quotes becomes “(a name)”."""
        own = [tidy(p) for p in self.own_dirs() if p]

        def hidden(path: str) -> str | None:
            if any(path.startswith(k) for k in own if len(k) > 3):
                return None
            ext = os.path.splitext(path.rstrip(".,;:)]"))[1].lower()
            return f"(a {ext} file)" if re.fullmatch(r"\.[a-z0-9]{1,8}", ext) else "(a folder or file)"
        text = _QUOTED.sub(lambda m: m.group(1) + (hidden(m.group(2)) or m.group(2)) + m.group(1), text)
        text = _BARE.sub(lambda m: hidden(m.group(1)) or m.group(1), text)
        return _NAMED.sub("“(a name)”", text) if self.hide_names else text

    def library_versions(self) -> dict:
        from importlib.metadata import PackageNotFoundError, version
        out = {}
        for name in self.libraries:
            try:
                out[name] = version(name)
            except PackageNotFoundError:
                pass
        return out

    def gather(self, settings: dict | None = None, extra: dict | None = None, notes: str = "") -> dict:
        """report.json's contents. settings: the app's settings (settings_shown picks what goes
        in); extra: more about the installation (the window's kind, the update state)."""
        kind = None
        if self._install_kind:
            try:
                kind = self._install_kind()
            except Exception:   # noqa: BLE001
                kind = None
        try:
            tools = dict(self._tools()) if self._tools else {}
        except Exception:   # noqa: BLE001
            tools = {}
        return {
            "app": self.app, "format": 1, "version": self.version,
            "made": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "system": {"platform": sys.platform, "os": platform.platform(), "machine": platform.machine(),
                       "python": platform.python_version(), "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
                       "wayland": bool(os.environ.get("WAYLAND_DISPLAY")) if sys.platform.startswith("linux") else None},
            "install": {"kind": kind, "prefix": tidy(sys.prefix), **(extra or {})},
            "libraries": self.library_versions(),
            "tools": tools,
            "settings": json.loads(tidy(json.dumps(self._settings_shown(settings or {}), default=str))),
            "notes": tidy(notes.strip()),   # (what the person typed, as they typed it)
        }

    def report(self, dest_dir: str, settings: dict | None = None, extra: dict | None = None, notes: str = "") -> str:
        """Write the report ZIP into dest_dir and return its path."""
        info = self.gather(settings, extra, notes)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        os.makedirs(dest_dir, exist_ok=True)
        path = os.path.join(dest_dir, f"{self.app}-report-{stamp}.zip")
        log = tail(self.log_path() + ".1", self.log_tail // 4) + tail(self.log_path(), self.log_tail)
        fill = {"app": self.app, "version": info["version"], "made": info["made"]}
        readme = README.format(whats_in=self.whats_in.format(**fill), whats_not=self.whats_not.format(**fill), **fill)
        try:
            with zipfile.ZipFile(path + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("report.json", json.dumps(info, indent=1, ensure_ascii=False))
                z.writestr("log.txt", self.private(tidy(log)) or "(nothing logged)\n")
                z.writestr("README.txt", readme)
            os.replace(path + ".tmp", path)
        except BaseException:
            try:
                os.remove(path + ".tmp")
            except OSError:
                pass
            raise
        return path

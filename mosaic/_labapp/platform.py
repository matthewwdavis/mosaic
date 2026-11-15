"""What differs between macOS, Windows and Linux, in one place: where an app keeps its settings and
caches, where the programs it runs are, and how a file, a folder or a web page is opened.

Nothing here knows which app it is in: the app passes its name."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

EXE = ".exe" if os.name == "nt" else ""
# (on Windows, a program the app runs opens no console window of its own: pass **HIDDEN to subprocess)
HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
# Files that would run as a program if "opened": these are shown in their folder instead
RUNNABLE = {".app", ".command", ".tool", ".sh", ".bash", ".zsh", ".csh", ".fish", ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1",
            ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".reg", ".scr", ".pif", ".jar", ".py", ".pyw", ".pl", ".rb",
            ".workflow", ".action", ".pkg", ".mpkg", ".dmg", ".desktop", ".appimage", ".run", ".bin", ".lnk", ".url", ".webloc",
            ".terminal", ".scpt", ".applescript"}


# Folders ---------------------------------------------------------------------------------------

def settings_dir(app: str) -> str:
    """The system's own place for an app's settings (macOS: ~/Library/Application Support;
    Windows: %APPDATA%; Linux: ~/.config, or XDG's)."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", app)
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), app)
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), app)


def cache_dir(app: str) -> str:
    """The system's own place for what an app can make again (macOS: ~/Library/Caches; Windows:
    %LOCALAPPDATA%; Linux: ~/.cache, or XDG's)."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", app)
    if os.name == "nt":
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), app, "Cache")
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"), app)


def desktop_dir() -> str:
    """The Desktop, else the home folder (where a file made for the person to send goes)."""
    home = os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    return desktop if os.path.isdir(desktop) else home


# Programs --------------------------------------------------------------------------------------

def env_dirs(prefix: str | None = None) -> list[str]:
    """Where a conda environment (this Python's, by default) keeps its programs."""
    if prefix is None:
        prefix = sys.prefix
        beside = [os.path.dirname(sys.executable)]
    else:
        beside = []
    if os.name == "nt":
        dirs = [prefix, os.path.join(prefix, "Library", "bin"), os.path.join(prefix, "Scripts"), os.path.join(prefix, "bin")]
    else:
        dirs = [os.path.join(prefix, "bin")]
    return list(dict.fromkeys(dirs + beside))


def tool(name: str, path_first: bool = False) -> str | None:
    """A program in this Python's environment, else on the PATH (path_first: the PATH, then the
    environment); None when there's none."""
    def in_env():
        for d in env_dirs():
            p = os.path.join(d, name + EXE)
            if os.path.isfile(p):
                return p
        return None
    if path_first:
        return shutil.which(name) or in_env()
    return in_env() or shutil.which(name)


def conda_roots() -> list[str]:
    """Where conda itself is usually installed, on each system."""
    home = os.path.expanduser("~")
    roots = [os.path.join(home, n) for n in ("anaconda3", "miniconda3", "miniforge3", "mambaforge")]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        drive = os.environ.get("SystemDrive", "C:")
        user = os.environ.get("USERNAME", "")
        roots += [os.path.join(local, "anaconda3"), os.path.join(local, "miniconda3"), r"C:\ProgramData\anaconda3",
                  r"C:\ProgramData\miniconda3", r"C:\anaconda3", r"C:\miniconda3",
                  os.path.join(drive + os.sep, f"miniforge3-{user}")]   # (the installers', for a profile path with a space)
    else:
        roots += ["/opt/anaconda3", "/opt/miniconda3", "/opt/miniforge3", "/opt/homebrew/Caskroom/miniforge/base",
                  "/usr/local/anaconda3", "/opt/conda"]
    return roots


def in_conda_envs(name: str) -> list[str]:
    """A program in any conda environment on this computer."""
    found = []
    for root in conda_roots():
        for env in [root, *sorted(glob.glob(os.path.join(root, "envs", "*")))]:
            for d in env_dirs(env):
                p = os.path.join(d, name + EXE)
                if os.path.isfile(p) and p not in found:
                    found.append(p)
    return found


def env_python(program: str) -> str:
    """The Python in the same conda environment as a program found there."""
    d = os.path.dirname(program)
    prefix = os.path.dirname(d) if os.path.basename(d).lower() in ("bin", "scripts") else d
    if os.name == "nt":
        for p in (os.path.join(prefix, "python.exe"), os.path.join(d, "python.exe")):
            if os.path.isfile(p):
                return p
        return os.path.join(prefix, "python.exe")
    return os.path.join(d, "python")


# Opening things --------------------------------------------------------------------------------

def open_path(path: str, reveal: bool = False) -> bool:
    """A file opened in its own app, or (reveal) shown in its folder: Finder, Explorer, or the
    file manager. A folder, or a file that would run as a program, is always shown, never run."""
    if not reveal and (os.path.splitext(path)[1].lower() in RUNNABLE or os.path.isdir(path)):
        reveal = True
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if reveal else ["open", path])
        elif os.name == "nt":
            if reveal:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)   # noqa: S606 (Windows' own way to open a file)
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(os.path.abspath(path)) if reveal else path])
    except OSError:   # (no xdg-open, say)
        return False
    return True


def reveal(path: str) -> bool:
    """A file shown in its folder."""
    return open_path(path, reveal=True)


def open_url(url: str, http: bool = False) -> bool:
    """A web page in the browser. https always, and http on this computer (the app's own pages);
    http elsewhere only when asked (http=True: a link an author put in a document). Nothing else,
    so a document can't have the app open a file or another program's address."""
    url = url or ""
    ok = url.startswith(("https://", "http://127.0.0.1", "http://localhost")) or (http and url.startswith("http://"))
    if not ok:
        return False
    import webbrowser
    return bool(webbrowser.open(url))

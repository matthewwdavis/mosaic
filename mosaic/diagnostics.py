"""What a problem report needs, gathered into one file to send (Help > Report a Problem).

The work is the shared library's (_labapp/diagnostics.py: the log, the report ZIP and what stays
out of it); this says what is mosaic's own: its name, where its log goes, the libraries and
programs it uses, and which settings may go in.

- The log: <settings folder>/logs/mosaic.log, what mosaic prints as it runs.
- The report: mosaic-report-<date>-<time>.zip with report.json, log.txt and README.txt.

Nothing of the figures goes in: no documents, no placed files, no file names (paths to your own
files in the log become "(a .pdf file)"). The home folder's path is written "~", and the settings
leave out lists of recent files.
"""
from __future__ import annotations

import os

from . import __version__
from ._labapp import diagnostics as _shared
from ._labapp.platform import tool
from .fonts import config_dir

APP = "mosaic"
LIBRARIES = ("pikepdf", "pypdfium2", "pillow", "lxml", "fonttools", "numpy", "shapely", "skia-pathops",
             "matplotlib", "python-pptx", "pywebview", "cryptography", "PySide6", "QtPy", "pyobjc-core", "pythonnet")
TOOLS = ("gs", "rsvg-convert", "pdftocairo")
PRIVATE_SETTINGS = ("recent", "recent_exports", "recent_folders", "github_user")   # (names of files, folders and accounts)


def _install_kind():
    from .updates import install_kind
    return install_kind()


def _own_dirs() -> list[str]:
    from .assets import get_cache
    dirs = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    try:
        dirs.append(get_cache().root)
    except Exception:   # noqa: BLE001
        pass
    return dirs


d = _shared.Diagnostics(
    APP, __version__, settings_dir=config_dir, own_dirs=_own_dirs, libraries=LIBRARIES,
    tools=lambda: {t: bool(tool(t, path_first=True)) for t in TOOLS},
    settings_shown=lambda prefs: _shared.all_but(prefs, PRIVATE_SETTINGS), install_kind=_install_kind,
    whats_in=("  report.json  the version of {app} and of the libraries it uses, the operating system,\n"
              "               how {app} was installed, its settings, and anything typed in the report's box"),
    whats_not="  No figures, documents, pictures or plots, and no names of your files or folders.",
    hide_names=False)

log_path, start_log, note, gather, report = d.log_path, d.start_log, d.note, d.gather, d.report

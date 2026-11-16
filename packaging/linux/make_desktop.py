"""Puts mosaic in a Linux desktop's applications menu, for the account (install-linux.sh): a
.desktop entry that starts `python -P -m mosaic` from the environment this runs in, with
mosaic's icon, and its file type (.mff, and the older .mosaic and .figasm: docfile.EXTENSIONS)
so documents open in it when double-clicked. PowerPoint decks get mosaic under Open with.

    python packaging/linux/make_desktop.py [--data ~/.local/share] [--no-register]

The work is the shared library's (mosaic/_labapp/packaging.py); what mosaic is comes from the
Mac script (packaging/macos/make_app.py: SPEC).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "macos"))
from make_app import SPEC, packaging  # noqa: E402  (the same name, types and icon as the Mac app)

MIME = SPEC.mime
MIME_XML = packaging.mime_xml(SPEC)


def desktop_entry(python: str) -> str:
    """The applications-menu entry: %f is the document double-clicked, if any."""
    return packaging.desktop_entry(SPEC, python)


def install(data: str, python: str = sys.executable, register: bool = True) -> str:
    """Write the entry, the file type and the icon under `data` (~/.local/share); returns the entry's path."""
    return packaging.linux_desktop(SPEC, data, python, register)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"))
    ap.add_argument("--no-register", action="store_true")
    args = ap.parse_args()
    print(install(args.data, register=not args.no_register))

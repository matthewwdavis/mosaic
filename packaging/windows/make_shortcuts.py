"""Add mosaic to the Windows Start menu and desktop, starting it from this Python environment.

    python packaging/windows/make_shortcuts.py [--no-desktop | --update]

Run it with the environment's own Python (install-windows.bat does): the shortcuts start
pythonw.exe -m mosaic from that environment, with mosaic's icon. With --update (an
update installing), the desktop shortcut is made again only if there is one, so one deleted
stays deleted.

It also registers mosaic's documents for this Windows account: double-clicking a .mosaic (or a
.figasm, from when mosaic was called FigAssemble) opens it in mosaic (each in a window of its
own), and decks list mosaic under Open with, never instead of PowerPoint.

The work is the shared library's (mosaic/_labapp/packaging.py); what mosaic is comes from the
Mac script beside this one (packaging/macos/make_app.py: SPEC).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "macos"))

from make_app import SPEC, packaging  # noqa: E402  (the same name, types and icon as the Mac app)

DOCUMENT_PROGID = "mosaic.Document"
DECK_PROGID = "mosaic.Deck"
DOCUMENT_EXTENSIONS = tuple(SPEC.extensions)        # (.figasm: from when mosaic was called FigAssemble)
DECK_EXTENSIONS = tuple(SPEC.alt_extensions)


def register_file_types(pythonw: str, icon: str, root: str = r"Software\Classes") -> None:
    """Double-clicking a .mosaic opens it in mosaic, and decks have mosaic under Open with
    (their own app stays theirs): in HKEY_CURRENT_USER, for this account."""
    packaging.register_file_types(SPEC, pythonw, icon, root)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-desktop", action="store_true")
    ap.add_argument("--update", action="store_true", help="keep the desktop shortcut only if there is one")
    args = ap.parse_args()
    for p in packaging.windows_shortcuts(SPEC, desktop=not args.no_desktop, update=args.update):
        print(p)
    print("mosaic opens .mosaic documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())

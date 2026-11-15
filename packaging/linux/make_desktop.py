"""Puts mosaic in a Linux desktop's applications menu, for the account (install-linux.sh): a
.desktop entry that starts `python -P -m mosaic` from the environment this runs in, with
mosaic's icon, and the .mosaic file type (and .figasm, from when mosaic was called FigAssemble)
so documents open in it when double-clicked. PowerPoint decks get mosaic under Open with.

    python packaging/linux/make_desktop.py [--data ~/.local/share] [--no-register]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "macos"))
from make_app import draw_icon  # noqa: E402  (the same icon as the Mac app)

MIME = "application/x-mosaic"
MIME_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="{MIME}">
    <comment>mosaic figure</comment>
    <glob pattern="*.mosaic"/>
    <glob pattern="*.figasm"/>
    <sub-class-of type="application/zip"/>
    <icon name="mosaic"/>
  </mime-type>
</mime-info>
"""
DECKS = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def desktop_entry(python: str) -> str:
    """The applications-menu entry: %f is the document double-clicked, if any."""
    return "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=mosaic",
        "Comment=Assemble multi-panel scientific figures",
        f'Exec="{python}" -P -m mosaic %f', "Icon=mosaic", "Terminal=false",
        "Categories=Graphics;Science;", f"MimeType={MIME};{DECKS};", "StartupWMClass=mosaic", ""])


def install(data: str, python: str = sys.executable, register: bool = True) -> str:
    """Write the entry, the file type and the icon under `data` (~/.local/share); returns the entry's path."""
    apps, mime = os.path.join(data, "applications"), os.path.join(data, "mime", "packages")
    icons = os.path.join(data, "icons", "hicolor", "256x256", "apps")
    for d in (apps, mime, icons):
        os.makedirs(d, exist_ok=True)
    draw_icon(256).save(os.path.join(icons, "mosaic.png"))
    with open(os.path.join(mime, "mosaic.xml"), "w", encoding="utf-8") as fh:
        fh.write(MIME_XML)
    entry = os.path.join(apps, "mosaic.desktop")
    with open(entry, "w", encoding="utf-8") as fh:
        fh.write(desktop_entry(python))
    os.chmod(entry, 0o755)
    if register:   # the desktop's own tools, where there are any (it finds the files by itself otherwise, later)
        for cmd in (["update-mime-database", os.path.join(data, "mime")], ["update-desktop-database", apps],
                    ["xdg-mime", "default", "mosaic.desktop", MIME]):
            if shutil.which(cmd[0]):
                subprocess.run(cmd, check=False, capture_output=True)
    return entry


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"))
    ap.add_argument("--no-register", action="store_true")
    args = ap.parse_args()
    print(install(args.data, register=not args.no_register))

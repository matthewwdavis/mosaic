"""Add FigAssemble to the Windows Start menu and desktop, starting it from this Python environment.

    python packaging/windows/make_shortcuts.py [--no-desktop | --update]

Run it with the environment's own Python (install-windows.bat does): the shortcuts start
pythonw.exe -m figassemble from that environment, with FigAssemble's icon. With --update (an
update installing), the desktop shortcut is made again only if there is one, so one deleted
stays deleted.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "macos"))

from make_app import draw_icon  # noqa: E402  (the same icon as the Mac app)


def make_ico(dest: str) -> None:
    draw_icon(256).save(dest, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-desktop", action="store_true")
    ap.add_argument("--update", action="store_true", help="keep the desktop shortcut only if there is one")
    args = ap.parse_args()
    prefix = sys.prefix
    pythonw = os.path.join(prefix, "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    icon = os.path.join(prefix, "FigAssemble.ico")
    make_ico(icon)
    folders = [os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")]
    if not args.no_desktop:
        folders.append("([Environment]::GetFolderPath('Desktop'))")   # follows a desktop moved to OneDrive
    made = []
    for folder in folders:
        where = folder if folder.startswith("(") else ps_quote(folder)
        keep = "if (-not (Test-Path $p)) { exit 0 }; " if args.update and folder.startswith("(") else ""
        script = (f"$s = New-Object -ComObject WScript.Shell; $p = Join-Path {where} 'FigAssemble.lnk'; {keep}"
                  f"$l = $s.CreateShortcut($p); $l.TargetPath = {ps_quote(pythonw)}; $l.Arguments = '-m figassemble'; "
                  f"$l.WorkingDirectory = $env:USERPROFILE; $l.IconLocation = {ps_quote(icon)}; "
                  f"$l.Description = 'FigAssemble: assemble multi-panel figures'; $l.Save(); Write-Output $p")
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                             capture_output=True, text=True, check=True)
        if out.stdout.strip():
            made.append(out.stdout.strip())
    for p in made:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())

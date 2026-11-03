"""Add FigAssemble to the Windows Start menu and desktop, starting it from this Python environment.

    python packaging/windows/make_shortcuts.py [--no-desktop | --update]

Run it with the environment's own Python (install-windows.bat does): the shortcuts start
pythonw.exe -m figassemble from that environment, with FigAssemble's icon. With --update (an
update installing), the desktop shortcut is made again only if there is one, so one deleted
stays deleted.

It also registers FigAssemble's documents for this Windows account: double-clicking a .figasm
opens it in FigAssemble (each in a window of its own), and decks list FigAssemble under Open
with, never instead of PowerPoint.
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


DOCUMENT_PROGID = "FigAssemble.Document"
DECK_PROGID = "FigAssemble.Deck"
DECK_EXTENSIONS = (".pptx", ".pptm", ".potx")


def register_file_types(pythonw: str, icon: str, root: str = r"Software\Classes") -> None:
    """Double-clicking a .figasm opens it in FigAssemble, and decks have FigAssemble under Open
    with (their own app stays theirs): in HKEY_CURRENT_USER, for this account, so no
    administrator is needed. -P: Python leaves the document's folder off its path (a folder with
    a copy of FigAssemble's source in it would otherwise run that)."""
    import winreg

    def put(path: str, value: str, name: str = "") -> None:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{root}\\{path}") as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    command = f'"{pythonw}" -P -m figassemble "%1"'
    for progid, name in ((DOCUMENT_PROGID, "FigAssemble figure"), (DECK_PROGID, "PowerPoint deck")):
        put(progid, name)
        put(f"{progid}\\DefaultIcon", f'"{icon}",0')
        put(f"{progid}\\shell\\open\\command", command)
        # The name Open with shows (else pythonw.exe's own, "Python")
        put(f"{progid}\\shell\\open", "FigAssemble", "FriendlyAppName")
        put(f"{progid}\\Application", "FigAssemble", "ApplicationName")
    put(".figasm", DOCUMENT_PROGID)
    put(".figasm\\OpenWithProgids", "", DOCUMENT_PROGID)
    for ext in DECK_EXTENSIONS:
        put(f"{ext}\\OpenWithProgids", "", DECK_PROGID)
    if root == r"Software\Classes":
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED: Explorer looks again


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
    register_file_types(pythonw, icon)
    print("FigAssemble opens .figasm documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())

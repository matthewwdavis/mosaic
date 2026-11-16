"""Putting an app where each system keeps apps, started from the Python environment it's installed
in: a Mac .app, Windows shortcuts and file types, a Linux applications-menu entry.

The installers run an app's own small scripts (packaging/macos/make_app.py and the like), which
say what the app is (an AppSpec) and call these.

    spec = AppSpec(name="mosaic", module="mosaic", version=__version__, bundle_id="io.github.me.mosaic",
                   description="Assemble multi-panel scientific figures", tagline="assemble multi-panel figures",
                   doc_kind="mosaic figure", doc_types=[("io.github.me.mosaic.mff", "mff"),
                                                        ("io.github.me.mosaic.document", "mosaic")],
                   draw_icon=draw_icon, ...)
    mac_app(spec, dest)                 # dest/mosaic.app
    windows_shortcuts(spec)             # Start menu, desktop, .mff (and .mosaic) opening in it
    linux_desktop(spec, data)           # ~/.local/share: the entry, the file type, the icon
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
              "/Support/lsregister")


@dataclass
class AppSpec:
    name: str                                   # the app's name, as people see it: "mosaic"
    module: str                                 # what Python runs: python -m <module>
    version: str
    bundle_id: str                              # the Mac's identifier for the app
    description: str                            # a line for the applications menu
    tagline: str                                # after "<name>: " on a Windows shortcut
    doc_kind: str                               # what its documents are called: "mosaic figure"
    doc_types: list                             # [(the Mac's type identifier, extension without its dot)]: the one new
                                                # documents get first, then older ones that still open (and save as
                                                # themselves). Each is the app's own, with the same icon and kind
    draw_icon: object                           # draw_icon(size) -> a PIL image
    conforms: list = field(default_factory=lambda: ["public.data", "public.content"])   # what the Mac's type is a kind of
    alt_name: str = ""                          # files of another app it also opens (Open With): "PowerPoint deck"
    alt_key: str = "Other"                      # the Windows name for those: <name>.<alt_key>
    alt_mac_types: list = field(default_factory=list)
    alt_extensions: list = field(default_factory=list)     # with their dots
    alt_mime: str = ""
    categories: str = "Office;"                 # the Linux menu's
    shortcut_args: str = ""                     # a Windows shortcut's arguments; "-m <module>" unless given
    icon_assets: str = ""                       # a Mac's Assets.car holding the icon named <name> (tools/make_mac_icon.py):
                                                # macOS 26 and later draw it in the system's appearance, light or dark

    @property
    def extensions(self) -> list:
        """Every extension its documents have, with their dots: new documents' first."""
        return ["." + ext for _, ext in self.doc_types]

    @property
    def extension(self) -> str:
        """The extension new documents get."""
        return self.extensions[0]

    @property
    def mime(self) -> str:
        return f"application/x-{self.name}"


# macOS ------------------------------------------------------------------------------------------

def document_types(spec: AppSpec) -> dict:
    """What the app opens, for its Info.plist: its own documents (it owns their types, declared
    here: the new extension's and the older ones', so a document of any of them opens with a
    double-click), and the other app's files as an alternative. Its documents are one kind, so
    every extension shows the same document icon: the one macOS draws from the app's icon."""
    kinds = [{"CFBundleTypeName": spec.doc_kind, "CFBundleTypeRole": "Editor", "LSHandlerRank": "Owner",
              "LSItemContentTypes": [uti for uti, _ in spec.doc_types], "CFBundleTypeIconSystemGenerated": True}]
    if spec.alt_mac_types:
        kinds.append({"CFBundleTypeName": spec.alt_name, "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
                      "LSItemContentTypes": list(spec.alt_mac_types)})
    return {
        "CFBundleDocumentTypes": kinds,
        "UTExportedTypeDeclarations": [
            {"UTTypeIdentifier": uti, "UTTypeDescription": spec.doc_kind, "UTTypeConformsTo": list(spec.conforms),
             "UTTypeTagSpecification": {"public.filename-extension": [ext]}}
            for uti, ext in spec.doc_types],
    }


def register(app: str) -> bool:
    """Tell macOS about the app now (its document types), rather than whenever it next looks."""
    if not os.path.exists(LSREGISTER):
        return False
    return subprocess.run([LSREGISTER, "-f", app], capture_output=True).returncode == 0


def make_icns(spec: AppSpec, dest: str) -> bool:
    if not shutil.which("iconutil"):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, f"{spec.name}.iconset")
        os.makedirs(iconset)
        for base in (16, 32, 128, 256, 512):
            spec.draw_icon(base).save(os.path.join(iconset, f"icon_{base}x{base}.png"))
            spec.draw_icon(base * 2).save(os.path.join(iconset, f"icon_{base}x{base}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", dest], check=True)
    return True


def mac_app(spec: AppSpec, dest: str, command: list | None = None, do_register: bool = True) -> str:
    """The app in dest: it runs `python -m <module>` with this environment's Python, linked into
    the app so that macOS takes the app's name, icon and version from the bundle (run from its
    own folder it would call the app "python"); or it runs the command given. Made again each
    time. Returns its path."""
    app = os.path.join(dest, f"{spec.name}.app")
    if os.path.exists(app):
        shutil.rmtree(app)   # (made again each time: the bundle is this function's)
    macos = os.path.join(app, "Contents", "MacOS")
    res = os.path.join(app, "Contents", "Resources")
    os.makedirs(macos)
    os.makedirs(res)
    launcher = os.path.join(macos, spec.name)
    if command is None:
        os.symlink(sys.executable, os.path.join(macos, "python"))
        body = (f"# Starts {spec.name} from the Python environment it was installed in, linked in beside this\n"
                f"# file so that macOS sees the app as {spec.name}\n"
                f'exec "$(dirname "$0")/python" -m {spec.module} "$@"\n')
    else:
        body = "exec " + " ".join(f'"{c}"' for c in command) + ' "$@"\n'
    with open(launcher, "w") as fh:
        fh.write("#!/bin/sh\n" + body)
    os.chmod(launcher, 0o755)
    has_icon = make_icns(spec, os.path.join(res, f"{spec.name}.icns"))
    info = {
        "CFBundleName": spec.name, "CFBundleDisplayName": spec.name,
        "CFBundleIdentifier": spec.bundle_id, "CFBundleExecutable": spec.name,
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": spec.version,
        "CFBundleVersion": spec.version, "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True, **document_types(spec),
    }
    if has_icon:
        info["CFBundleIconFile"] = spec.name   # (the drawn icon: what a Mac before macOS 26 shows)
    if spec.icon_assets and os.path.isfile(spec.icon_assets):
        shutil.copyfile(spec.icon_assets, os.path.join(res, "Assets.car"))
        info["CFBundleIconName"] = spec.name   # (macOS 26 and later: the icon in Assets.car, light or dark with the system)
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as fh:
        plistlib.dump(info, fh)
    if do_register and sys.platform == "darwin":
        register(app)
    return app


# Windows ----------------------------------------------------------------------------------------

def ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def make_ico(spec: AppSpec, dest: str) -> None:
    spec.draw_icon(256).save(dest, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def register_file_types(spec: AppSpec, pythonw: str, icon: str, root: str = r"Software\Classes") -> None:
    """Double-clicking one of the app's documents opens it in the app, and the other app's files
    have it under Open with (their own app stays theirs): in HKEY_CURRENT_USER, for this account,
    so no administrator is needed. -P: Python leaves the document's folder off its path (a folder
    with a copy of the app's source in it would otherwise run that)."""
    import winreg

    def put(path: str, value: str, name: str = "") -> None:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{root}\\{path}") as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    doc_id, alt_id = f"{spec.name}.Document", f"{spec.name}.{spec.alt_key}"
    command = f'"{pythonw}" -P -m {spec.module} "%1"'
    for progid, name in ((doc_id, spec.doc_kind), *(((alt_id, spec.alt_name),) if spec.alt_extensions else ())):
        put(progid, name)
        put(f"{progid}\\DefaultIcon", f'"{icon}",0')
        put(f"{progid}\\shell\\open\\command", command)
        # The name Open with shows (else pythonw.exe's own, "Python")
        put(f"{progid}\\shell\\open", spec.name, "FriendlyAppName")
        put(f"{progid}\\Application", spec.name, "ApplicationName")
    for ext in spec.extensions:
        put(ext, doc_id)
        put(f"{ext}\\OpenWithProgids", "", doc_id)
    for ext in spec.alt_extensions:
        put(f"{ext}\\OpenWithProgids", "", alt_id)
    if root == r"Software\Classes":
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED: Explorer looks again


def windows_shortcuts(spec: AppSpec, desktop: bool = True, update: bool = False) -> list:
    """Shortcuts in the Start menu and (desktop) on the desktop that start pythonw.exe -m <module>
    from this environment, with the app's icon; and the app's file types. With update (an update
    installing), the desktop shortcut is made again only if there is one, so one deleted stays
    deleted. Returns the shortcuts made."""
    prefix = sys.prefix
    pythonw = os.path.join(prefix, "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    icon = os.path.join(prefix, f"{spec.name}.ico")
    make_ico(spec, icon)
    folders = [os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")]
    if desktop:
        folders.append("([Environment]::GetFolderPath('Desktop'))")   # follows a desktop moved to OneDrive
    arguments = spec.shortcut_args or f"-m {spec.module}"
    made = []
    for folder in folders:
        where = folder if folder.startswith("(") else ps_quote(folder)
        keep = "if (-not (Test-Path $p)) { exit 0 }; " if update and folder.startswith("(") else ""
        script = (f"$s = New-Object -ComObject WScript.Shell; $p = Join-Path {where} '{spec.name}.lnk'; {keep}"
                  f"$l = $s.CreateShortcut($p); $l.TargetPath = {ps_quote(pythonw)}; $l.Arguments = '{arguments}'; "
                  f"$l.WorkingDirectory = $env:USERPROFILE; $l.IconLocation = {ps_quote(icon)}; "
                  f"$l.Description = {ps_quote(spec.name + ': ' + spec.tagline)}; $l.Save(); Write-Output $p")
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                             capture_output=True, text=True, check=True)
        if out.stdout.strip():
            made.append(out.stdout.strip())
    register_file_types(spec, pythonw, icon)
    return made


# Linux ------------------------------------------------------------------------------------------

def mime_xml(spec: AppSpec) -> str:
    """The app's file type for the desktop: its documents, by extension."""
    globs = "\n".join(f'    <glob pattern="*{ext}"/>' for ext in spec.extensions)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="{spec.mime}">
    <comment>{spec.doc_kind}</comment>
{globs}
    <sub-class-of type="application/zip"/>
    <icon name="{spec.name}"/>
  </mime-type>
</mime-info>
"""


def desktop_entry(spec: AppSpec, python: str) -> str:
    """The applications-menu entry: %f is the document double-clicked, if any."""
    types = f"{spec.mime};" + (f"{spec.alt_mime};" if spec.alt_mime else "")
    return "\n".join([
        "[Desktop Entry]", "Type=Application", f"Name={spec.name}",
        f"Comment={spec.description}",
        f'Exec="{python}" -P -m {spec.module} %f', f"Icon={spec.name}", "Terminal=false",
        f"Categories={spec.categories}", f"MimeType={types}", f"StartupWMClass={spec.name}", ""])


def linux_desktop(spec: AppSpec, data: str, python: str = sys.executable, do_register: bool = True) -> str:
    """Write the entry, the file type and the icon under `data` (~/.local/share); returns the entry's path."""
    apps, mime = os.path.join(data, "applications"), os.path.join(data, "mime", "packages")
    icons = os.path.join(data, "icons", "hicolor", "256x256", "apps")
    for d in (apps, mime, icons):
        os.makedirs(d, exist_ok=True)
    spec.draw_icon(256).save(os.path.join(icons, f"{spec.name}.png"))
    with open(os.path.join(mime, f"{spec.name}.xml"), "w", encoding="utf-8") as fh:
        fh.write(mime_xml(spec))
    entry = os.path.join(apps, f"{spec.name}.desktop")
    with open(entry, "w", encoding="utf-8") as fh:
        fh.write(desktop_entry(spec, python))
    os.chmod(entry, 0o755)
    if do_register:   # the desktop's own tools, where there are any (it finds the files by itself otherwise, later)
        for cmd in (["update-mime-database", os.path.join(data, "mime")], ["update-desktop-database", apps],
                    ["xdg-mime", "default", f"{spec.name}.desktop", spec.mime]):
            if shutil.which(cmd[0]):
                subprocess.run(cmd, check=False, capture_output=True)
    return entry

"""Build a double-clickable FigAssemble.app that starts the app from this Python environment.

    python packaging/macos/make_app.py [--dest dist]

Run it from the environment FigAssemble is installed in (conda activate figassemble); the
app remembers that environment's Python. Drag the result into Applications.

The environment's Python is linked into the app and runs from there, so macOS takes the app's
name, icon and version from this bundle, as for any Mac app (run from its own folder, it would
call the app "python").

The app declares the .figasm type as its own, so double-clicking a FigAssemble document opens it
in FigAssemble (macOS draws the documents' icon from the app's), and takes PowerPoint decks as
an alternative (in Open With, never instead of PowerPoint). The app is registered with macOS as
it's made, so that works straight away; not a build in this folder's dist (macOS would have two
apps of the same name to choose from), nor with --no-register (a test copy).
"""
import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from figassemble import __version__  # noqa: E402

DOCUMENT_TYPE = "org.figassemble.figasm"
# PowerPoint's: decks, decks with macros, templates (macOS's own types for them)
DECK_TYPES = ["org.openxmlformats.presentationml.presentation", "org.openxmlformats.presentationml.presentation.macroenabled",
              "org.openxmlformats.presentationml.template"]
LSREGISTER = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"


def document_types() -> dict:
    """What the app opens: its own documents (it owns the .figasm type, declared here), and decks
    as an alternative to PowerPoint."""
    return {
        "CFBundleDocumentTypes": [
            {"CFBundleTypeName": "FigAssemble figure", "CFBundleTypeRole": "Editor", "LSHandlerRank": "Owner",
             "LSItemContentTypes": [DOCUMENT_TYPE]},
            {"CFBundleTypeName": "PowerPoint deck", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
             "LSItemContentTypes": DECK_TYPES},
        ],
        "UTExportedTypeDeclarations": [
            {"UTTypeIdentifier": DOCUMENT_TYPE, "UTTypeDescription": "FigAssemble figure",
             "UTTypeConformsTo": ["public.data", "public.composite-content"],
             "UTTypeTagSpecification": {"public.filename-extension": ["figasm"]}},
        ],
    }


def register(app: str) -> bool:
    """Tell macOS about the app now (its document types), rather than whenever it next looks."""
    if not os.path.exists(LSREGISTER):
        return False
    return subprocess.run([LSREGISTER, "-f", app], capture_output=True).returncode == 0


def draw_icon(size: int):
    """A rounded tile with three figure panels and an 'a' label."""
    from PIL import Image, ImageDraw, ImageFont
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = round(s * 0.09)
    d.rounded_rectangle((pad, pad, s - pad, s - pad), radius=round(s * 0.2), fill=(250, 250, 247, 255),
                        outline=(40, 40, 38, 255), width=max(1, round(s * 0.02)))
    blue, orange, green = (11, 95, 204, 255), (230, 126, 34, 255), (76, 140, 60, 255)
    m = round(s * 0.2)
    gap = round(s * 0.04)
    top_h = round((s - 2 * m - gap) * 0.55)
    d.rectangle((m, m, s - m, m + top_h), fill=blue)
    bw = (s - 2 * m - gap) // 2
    d.rectangle((m, m + top_h + gap, m + bw, s - m), fill=orange)
    d.rectangle((m + bw + gap, m + top_h + gap, s - m, s - m), fill=green)
    font = None
    for path, index in (("/System/Library/Fonts/Helvetica.ttc", 1), ("arialbd.ttf", 0)):   # Mac, Windows
        try:
            font = ImageFont.truetype(path, round(s * 0.22), index=index)
            break
        except OSError:
            pass
    if font is None:
        font = ImageFont.load_default(round(s * 0.22))
    d.text((m + round(s * 0.04), m + round(s * 0.01)), "a", font=font, fill=(255, 255, 255, 255))
    return im


def make_icns(dest: str) -> bool:
    if not shutil.which("iconutil"):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "FigAssemble.iconset")
        os.makedirs(iconset)
        for base in (16, 32, 128, 256, 512):
            draw_icon(base).save(os.path.join(iconset, f"icon_{base}x{base}.png"))
            draw_icon(base * 2).save(os.path.join(iconset, f"icon_{base}x{base}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", dest], check=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--no-register", action="store_true", help="don't register it with macOS (a test copy)")
    args = ap.parse_args()
    app = os.path.join(args.dest, "FigAssemble.app")
    if os.path.exists(app):
        shutil.rmtree(app)   # rebuilt each time; the bundle is generated by this script
    macos = os.path.join(app, "Contents", "MacOS")
    res = os.path.join(app, "Contents", "Resources")
    os.makedirs(macos)
    os.makedirs(res)
    launcher = os.path.join(macos, "FigAssemble")
    os.symlink(sys.executable, os.path.join(macos, "python"))
    with open(launcher, "w") as fh:
        fh.write("#!/bin/sh\n"
                 "# Starts FigAssemble from the Python environment it was built with, linked in beside this\n"
                 "# file so that macOS sees the app as FigAssemble\n"
                 'exec "$(dirname "$0")/python" -m figassemble "$@"\n')
    os.chmod(launcher, 0o755)
    has_icon = make_icns(os.path.join(res, "FigAssemble.icns"))
    info = {
        "CFBundleName": "FigAssemble", "CFBundleDisplayName": "FigAssemble",
        "CFBundleIdentifier": "org.figassemble.app", "CFBundleExecutable": "FigAssemble",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__, "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True, **document_types(),
    }
    if has_icon:
        info["CFBundleIconFile"] = "FigAssemble"
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as fh:
        plistlib.dump(info, fh)
    # (not a test build in this folder's dist: macOS would choose between it and the installed
    # copy, which have the same name, for the documents)
    if not args.no_register and sys.platform == "darwin" and os.path.realpath(args.dest) != os.path.realpath(os.path.join(ROOT, "dist")):
        register(app)
    print(app)
    return 0


if __name__ == "__main__":
    sys.exit(main())

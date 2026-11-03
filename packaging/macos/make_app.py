"""Build a double-clickable mosaic.app that starts the app from this Python environment.

    python packaging/macos/make_app.py [--dest dist]

Run it from the environment mosaic is installed in (conda activate mosaic); the
app remembers that environment's Python. Drag the result into Applications.

The environment's Python is linked into the app and runs from there, so macOS takes the app's
name, icon and version from this bundle, as for any Mac app (run from its own folder, it would
call the app "python").

The app declares the .mosaic type as its own (and .figasm, its documents from when it was called
FigAssemble), so double-clicking a mosaic document opens it in mosaic (macOS draws the
documents' icon from the app's), and takes PowerPoint decks as
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

from mosaic import __version__  # noqa: E402

DOCUMENT_TYPE = "io.github.matthewwdavis.mosaic.document"
OLD_DOCUMENT_TYPE = "org.figassemble.figasm"   # .figasm, from when mosaic was called FigAssemble
# PowerPoint's: decks, decks with macros, templates (macOS's own types for them)
DECK_TYPES = ["org.openxmlformats.presentationml.presentation", "org.openxmlformats.presentationml.presentation.macroenabled",
              "org.openxmlformats.presentationml.template"]
LSREGISTER = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"


def document_types() -> dict:
    """What the app opens: its own documents (it owns the .mosaic and .figasm types, declared
    here), and decks as an alternative to PowerPoint."""
    return {
        "CFBundleDocumentTypes": [
            {"CFBundleTypeName": "mosaic figure", "CFBundleTypeRole": "Editor", "LSHandlerRank": "Owner",
             "LSItemContentTypes": [DOCUMENT_TYPE, OLD_DOCUMENT_TYPE]},
            {"CFBundleTypeName": "PowerPoint deck", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
             "LSItemContentTypes": DECK_TYPES},
        ],
        "UTExportedTypeDeclarations": [
            {"UTTypeIdentifier": uti, "UTTypeDescription": "mosaic figure",
             "UTTypeConformsTo": ["public.data", "public.composite-content"],
             "UTTypeTagSpecification": {"public.filename-extension": [ext]}}
            for uti, ext in ((DOCUMENT_TYPE, "mosaic"), (OLD_DOCUMENT_TYPE, "figasm"))
        ],
    }


def register(app: str) -> bool:
    """Tell macOS about the app now (its document types), rather than whenever it next looks."""
    if not os.path.exists(LSREGISTER):
        return False
    return subprocess.run([LSREGISTER, "-f", app], capture_output=True).returncode == 0


# The icon's mosaic: figure panels of different sizes fitted together as tiles, in the
# colour-blind-safe Okabe-Ito colours. (x0, y0, x1, y1) as fractions of the icon's width
ICON_TILES = [((0.2, 0.2, 0.55, 0.52), (0, 114, 178)), ((0.585, 0.2, 0.8, 0.36), (230, 159, 0)),
              ((0.585, 0.395, 0.8, 0.52), (86, 180, 233)), ((0.2, 0.555, 0.36, 0.8), (0, 158, 115)),
              ((0.395, 0.555, 0.8, 0.68), (213, 94, 0)), ((0.395, 0.715, 0.6, 0.8), (240, 228, 66)),
              ((0.635, 0.715, 0.8, 0.8), (204, 121, 167))]


def draw_icon(size: int):
    """A rounded tile holding the mosaic, drawn four times as big and scaled down, for smooth edges."""
    from PIL import Image, ImageDraw
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = round(s * 0.09)
    d.rounded_rectangle((pad, pad, s - pad, s - pad), radius=round(s * 0.2), fill=(250, 250, 247, 255),
                        outline=(40, 40, 38, 255), width=max(4, round(s * 0.02)))
    for (x0, y0, x1, y1), rgb in ICON_TILES:
        d.rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), radius=round(s * 0.018), fill=rgb + (255,))
    return im.resize((size, size), Image.LANCZOS)


def make_icns(dest: str) -> bool:
    if not shutil.which("iconutil"):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "mosaic.iconset")
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
    app = os.path.join(args.dest, "mosaic.app")
    if os.path.exists(app):
        shutil.rmtree(app)   # rebuilt each time; the bundle is generated by this script
    macos = os.path.join(app, "Contents", "MacOS")
    res = os.path.join(app, "Contents", "Resources")
    os.makedirs(macos)
    os.makedirs(res)
    launcher = os.path.join(macos, "mosaic")
    os.symlink(sys.executable, os.path.join(macos, "python"))
    with open(launcher, "w") as fh:
        fh.write("#!/bin/sh\n"
                 "# Starts mosaic from the Python environment it was built with, linked in beside this\n"
                 "# file so that macOS sees the app as mosaic\n"
                 'exec "$(dirname "$0")/python" -m mosaic "$@"\n')
    os.chmod(launcher, 0o755)
    has_icon = make_icns(os.path.join(res, "mosaic.icns"))
    info = {
        "CFBundleName": "mosaic", "CFBundleDisplayName": "mosaic",
        "CFBundleIdentifier": "io.github.matthewwdavis.mosaic", "CFBundleExecutable": "mosaic",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__, "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True, **document_types(),
    }
    if has_icon:
        info["CFBundleIconFile"] = "mosaic"
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

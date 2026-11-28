"""Build a double-clickable mosaic.app that starts the app from this Python environment.

    python packaging/macos/make_app.py [--dest dist]

Run it from the environment mosaic is installed in (conda activate mosaic); the
app remembers that environment's Python. Drag the result into Applications.

The app's program is labapp's launcher (mosaic/_labapp/mac/launcher.c), which runs the environment's
Python inside itself, and the app is signed (ad hoc), so macOS takes the app's name, icon and version
from this bundle, as for any Mac app, and names mosaic in its privacy prompts ("mosaic would like to
access files in your Desktop folder"; run as the environment's own Python, it would say "python").

The app declares the .mff type as its own, and the older documents' types too (.mosaic, and
.figasm from when it was called FigAssemble), so double-clicking a mosaic document of any of them
opens it in mosaic (macOS draws the documents' icon from the app's, the same for each), and takes PowerPoint decks as
an alternative (in Open With, never instead of PowerPoint). The app is registered with macOS as
it's made, so that works straight away; not a build in this folder's dist (macOS would have two
apps of the same name to choose from), nor with --no-register (a test copy).

Making the bundle is the shared library's (mosaic/_labapp/packaging.py); what mosaic is (SPEC:
its name, document types and icon) is here, and the Windows and Linux scripts read it from here.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from mosaic import __version__, docfile  # noqa: E402
from mosaic._labapp import packaging  # noqa: E402

# The Mac's type for each of docfile.EXTENSIONS, in its order: .mff (new documents'), then the older ones
DOCUMENT_TYPE = "io.github.matthewwdavis.mosaic.mff"
LEGACY_DOCUMENT_TYPES = ["io.github.matthewwdavis.mosaic.document",   # .mosaic, until November 2026
                         "org.figassemble.figasm"]                    # .figasm, from when mosaic was called FigAssemble
assert len(LEGACY_DOCUMENT_TYPES) == len(docfile.LEGACY_EXTENSIONS), "a Mac type for each older extension"
DOCUMENT_TYPES = list(zip([DOCUMENT_TYPE, *LEGACY_DOCUMENT_TYPES], [ext.lstrip(".") for ext in docfile.EXTENSIONS]))
# PowerPoint's: decks, decks with macros, templates (macOS's own types for them)
DECK_TYPES = ["org.openxmlformats.presentationml.presentation", "org.openxmlformats.presentationml.presentation.macroenabled",
              "org.openxmlformats.presentationml.template"]


from mosaic.icon import ICON_TILES, draw_icon  # noqa: E402,F401 (the icon, light; mosaic/icon.py has its dark one too)


SPEC = packaging.AppSpec(
    name="mosaic", module="mosaic", version=__version__, bundle_id="io.github.matthewwdavis.mosaic",
    description="Assemble multi-panel scientific figures", tagline="assemble multi-panel figures",
    doc_kind="mosaic figure", doc_types=DOCUMENT_TYPES,
    draw_icon=draw_icon, conforms=["public.data", "public.composite-content"],
    alt_name="PowerPoint deck", alt_key="Deck", alt_mac_types=DECK_TYPES, alt_extensions=[".pptx", ".pptm", ".potx"],
    alt_mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    categories="Graphics;Science;",
    icon_assets=os.path.join(HERE, "Assets.car"))   # (the icon, light or dark with the system on macOS 26 and later)


def document_types() -> dict:
    """What the app opens: its own documents (it owns the .mff, .mosaic and .figasm types,
    declared here), and decks as an alternative to PowerPoint."""
    return packaging.document_types(SPEC)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--no-register", action="store_true", help="don't register it with macOS (a test copy)")
    args = ap.parse_args()
    # (not a test build in this folder's dist: macOS would choose between it and the installed
    # copy, which have the same name, for the documents)
    here = os.path.realpath(args.dest) == os.path.realpath(os.path.join(ROOT, "dist"))
    print(packaging.mac_app(SPEC, args.dest, do_register=not args.no_register and not here))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Command line: `mosaic` opens the app; subcommands export and import headlessly.

    mosaic [document.mosaic]                      open the app
    mosaic export fig.mosaic -f pdf,png --dpi 600 [-o out/base] [--pages 1,3]
    mosaic import-pptx deck.pptx [--slides 13] [-o fig.mosaic] [--search DIR]
    mosaic fonts                                  list installed font families
    mosaic update [--install | --go-back] [--test] look for an update (and install it)
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _load(path: str) -> tuple[dict, str]:
    from . import docfile
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), os.path.dirname(os.path.abspath(path))
    return docfile.load(path), os.path.dirname(os.path.abspath(path))


def cmd_export(args) -> int:
    from .export.run import export_document
    doc, doc_dir = _load(args.document)
    base = args.output or os.path.splitext(os.path.abspath(args.document))[0]
    pages = [int(p) - 1 for p in args.pages.split(",")] if args.pages else None
    res = export_document(doc, base, [f.strip() for f in args.formats.split(",")], pages=pages, dpi=args.dpi,
                          transparent=not args.white, cmyk=args.cmyk, cmyk_profile=args.icc, doc_dir=doc_dir)
    for f in res["files"]:
        print(f)
    for w in res["warnings"]:
        print("warning:", w, file=sys.stderr)
    for n in res["notes"]:
        print("note:", n, file=sys.stderr)
    return 0


def cmd_import_pptx(args) -> int:
    from . import docfile
    from .importers.pptx import import_pptx
    slides = [int(s) for s in args.slides.split(",")] if args.slides else None
    doc, report = import_pptx(args.deck, slides=slides, search_dirs=args.search or None, relink=not args.no_relink)
    out = args.output or os.path.splitext(os.path.abspath(args.deck))[0] + docfile.EXTENSION
    docfile.save(doc, out)
    print(out)
    for line in report:
        print(line, file=sys.stderr)
    return 0


def cmd_fonts(_args) -> int:
    from .fonts import get_font_index
    for fam in get_font_index().families():
        print(fam)
    return 0


def cmd_update(args) -> int:
    from .updates import cli
    return cli(args)


def cmd_gui(args) -> int:
    from .updates import wait_for_install
    wait_for_install()   # opened again straight after quitting, while an update installs
    from .app.window import run_app
    return run_app(args.document, browser=args.browser, port=args.port)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or (argv[0] not in ("export", "import-pptx", "fonts", "update", "gui", "-h", "--help")):
        argv = ["gui"] + argv
    p = argparse.ArgumentParser(prog="mosaic", description="Assemble multi-panel figures.")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="export pages to PDF, SVG, PNG, TIFF, JPEG or EPS")
    e.add_argument("document")
    e.add_argument("-f", "--formats", default="pdf")
    e.add_argument("-o", "--output", help="output path without extension")
    e.add_argument("--dpi", type=float, default=600.0)
    e.add_argument("--pages", help="1-based page numbers, comma separated")
    e.add_argument("--white", action="store_true", help="white background instead of transparent")
    e.add_argument("--cmyk", action="store_true", help="CMYK colour (TIFF, JPEG, PDF); never the default")
    e.add_argument("--icc", help="CMYK ICC profile to convert with")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser("import-pptx", help="turn PowerPoint slides into a mosaic document")
    i.add_argument("deck")
    i.add_argument("--slides", help="1-based slide numbers, comma separated (default: all)")
    i.add_argument("-o", "--output")
    i.add_argument("--search", action="append", help="folder to look for the original figure files in")
    i.add_argument("--no-relink", action="store_true", help="keep the deck's copies of pictures")
    i.set_defaults(func=cmd_import_pptx)

    f = sub.add_parser("fonts", help="list installed font families")
    f.set_defaults(func=cmd_fonts)

    u = sub.add_parser("update", help="look for a newer version (and install it)")
    u.add_argument("--install", action="store_true", help="download the update and install it")
    u.add_argument("--go-back", action="store_true", help="install the version before this one")
    u.add_argument("--test", action="store_true", help="take test versions too")
    u.set_defaults(func=cmd_update)

    g = sub.add_parser("gui", help="open the app (the default)")
    g.add_argument("document", nargs="?")
    g.add_argument("--browser", action="store_true", help="use the web browser instead of an app window")
    g.add_argument("--port", type=int, default=0)
    g.set_defaults(func=cmd_gui)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

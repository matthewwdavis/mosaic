"""Command line: `mosaic` opens the app; subcommands export and import headlessly.

    mosaic [document.mosaic]                      open the app
    mosaic export fig.mosaic -f pdf,png --dpi 600 [-o out/base] [--pages 1,3]
    mosaic export fig.mosaic --journal Nature [--copy fig_nature.mosaic] [--dry-run] [--json]
                                                  the panel labels in a journal's look (relabel.py)
    mosaic build fig.mosaic -f pdf,png [--save]    read the linked plots again from their files, then export
    mosaic info fig.mosaic [--json]               its pages, sizes and descriptions
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
    if (args.copy or args.dry_run) and not args.journal:
        print("--copy and --dry-run go with --journal", file=sys.stderr)
        return 2
    doc, doc_dir = _load(args.document)
    src = os.path.abspath(args.document)
    own = os.path.splitext(src)[0]   # the document's own exports, which a relabelled copy never writes over
    report: dict = {}
    if getattr(args, "save", False) and not getattr(args, "refresh", False):
        print("--save goes with --refresh (or use `mosaic build --save`)", file=sys.stderr)
        return 2
    if getattr(args, "refresh", False):
        # The linked pictures read again from their files first, as Refresh All Pictures does
        from .refresh import refresh_document
        got = refresh_document(doc, doc_dir)
        report["refreshed"] = {k: got[k] for k in ("changed", "missing", "linked")}
        report["warnings"] = list(got["warnings"]) + [f"{name}: its file wasn't found; the copy in the document was used"
                                                      for name in got["missing"]]
        if args.save and src.lower().endswith(".json"):
            print("--save writes a .mosaic document, not a .json one", file=sys.stderr)
            return 2
        if args.save and got["changed"] and not args.dry_run:
            from . import docfile
            from .app import kept
            kept.keep_version(src, title=os.path.basename(src))   # the file as it was, under File > Browse Versions
            report["warnings"] += docfile.save(doc, src)
            report["saved"] = src
    if args.journal:
        # The panel labels in the journal's look; the document itself as it was (relabel.py)
        from . import docfile, relabel
        from . import journals as _journals
        from .journals import JOURNALS
        _journals.load_user()   # (your own journals are listed with the others)
        journal = relabel.find_journal(args.journal)
        if journal is None:
            print(f"No journal called {args.journal!r}; mosaic knows " + ", ".join(j["name"] for j in JOURNALS), file=sys.stderr)
            return 2
        fonts = None
        if not args.dry_run:   # (the labels' boxes fitted to their new text, for the export and any copy)
            from .fonts import get_font_index
            fonts = get_font_index()
        report["journal"] = journal["name"]
        report["labels"] = relabel.relabel(doc, journal, fonts)
        if args.dry_run:
            if args.json:
                print(json.dumps(report))
            else:
                for n, k in enumerate(report["labels"], 1):
                    print(f"page {n}: {k} label{'' if k == 1 else 's'} to change for {journal['name']}")
            return 0
        if args.copy:
            copy = os.path.abspath(args.copy if args.copy.lower().endswith(docfile.EXTENSIONS) else args.copy + docfile.EXTENSION)
            if os.path.exists(copy) and os.path.samefile(copy, src):
                print("--copy would write over the document itself; give the copy a name of its own", file=sys.stderr)
                return 2
            report["warnings"] = report.get("warnings", []) + docfile.save(doc, copy)
            report["copy"] = copy
        base = os.path.abspath(args.output) if args.output else \
            (os.path.splitext(report["copy"])[0] if args.copy else f"{own}_{relabel.slug(journal['name'])}")
        if base == own:
            print(f"That would write over {os.path.basename(own)}'s own exports; name the relabelled ones with -o", file=sys.stderr)
            return 2
    else:
        base = args.output or own
    pages = [int(p) - 1 for p in args.pages.split(",")] if args.pages else None
    res = export_document(doc, base, [f.strip() for f in args.formats.split(",")], pages=pages, dpi=args.dpi,
                          transparent=not args.white, cmyk=args.cmyk, cmyk_profile=args.icc, doc_dir=doc_dir)
    if args.json:
        shown = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
        report["pages"] = [{"name": pg.get("name", ""), "alt": (pg.get("alt") or "").strip()} for pg in shown]
        print(json.dumps({**report, "files": res["files"], "warnings": report.get("warnings", []) + res["warnings"],
                          "notes": res["notes"]}))
        return 0
    if report.get("copy"):
        print(report["copy"])
    for f in res["files"]:
        print(f)
    for w in report.get("warnings", []) + res["warnings"]:
        print("warning:", w, file=sys.stderr)
    for n in res["notes"]:
        print("note:", n, file=sys.stderr)
    if report.get("refreshed"):
        r = report["refreshed"]
        print(f"note: {len(r['changed'])} of {r['linked']} linked picture{'' if r['linked'] == 1 else 's'} had changed"
              + (f" ({', '.join(r['changed'])})" if r["changed"] else "")
              + (f"; saved in {os.path.basename(report['saved'])}" if report.get("saved") else ""), file=sys.stderr)
    if report.get("journal"):
        k = sum(report["labels"])
        print(f"note: {k} panel label{'' if k == 1 else 's'} in {report['journal']}'s look", file=sys.stderr)
    return 0


def cmd_info(args) -> int:
    """What a document holds, for other programs (prose reads each page's description here)."""
    from .model import iter_items
    doc, _ = _load(args.document)
    pages = [{"number": i + 1, "name": pg.get("name", ""), "width_pt": float(pg["width"]), "height_pt": float(pg["height"]),
              "objects": len(pg.get("items", [])), "alt": (pg.get("alt") or "").strip(),
              # (its pictures' own descriptions, in the order they're stacked)
              "pictures": [{"name": it.get("name") or "", "alt": it["alt"].strip()} for it in iter_items(pg.get("items", []))
                           if (it.get("alt") or "").strip()]} for i, pg in enumerate(doc["pages"])]
    info = {"title": (doc.get("meta") or {}).get("title", ""), "saved_by": (doc.get("meta") or {}).get("saved_by"), "pages": pages}
    if args.json:
        print(json.dumps(info, ensure_ascii=False))
        return 0
    print(info["title"] or os.path.basename(args.document))
    for pg in pages:
        print(f"  {pg['number']}. {pg['name']}: {pg['width_pt']:g} x {pg['height_pt']:g} pt, {pg['objects']} objects"
              + (f"\n     {pg['alt']}" if pg["alt"] else ""))
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
    if not argv or (argv[0] not in ("export", "build", "info", "import-pptx", "fonts", "update", "gui", "-h", "--help")):
        argv = ["gui"] + argv
    p = argparse.ArgumentParser(prog="mosaic", description="Assemble multi-panel figures.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def export_arguments(e):
        e.add_argument("document")
        e.add_argument("-f", "--formats", default="pdf")
        e.add_argument("-o", "--output", help="output path without extension")
        e.add_argument("--dpi", type=float, default=600.0)
        e.add_argument("--pages", help="1-based page numbers, comma separated")
        e.add_argument("--white", action="store_true", help="white background instead of transparent")
        e.add_argument("--cmyk", action="store_true", help="CMYK colour (TIFF, JPEG, PDF); never the default")
        e.add_argument("--icc", help="CMYK ICC profile to convert with")
        e.add_argument("--journal", help="the panel labels in this journal's look (the document itself is left as it is); "
                                         "the files are named after the journal unless -o names them")
        e.add_argument("--copy", help="with --journal: also save the relabelled document here")
        e.add_argument("--dry-run", action="store_true", help="with --journal: how many labels each page would change; nothing written")
        e.add_argument("--json", action="store_true", help="report as one JSON object")

    e = sub.add_parser("export", help="export pages to PDF, SVG, PNG, TIFF, JPEG or EPS")
    export_arguments(e)
    e.add_argument("--refresh", action="store_true", help="read the linked pictures again from their files first (as `mosaic build` does)")
    e.add_argument("--save", action="store_true", help="with --refresh: save the document with the new pictures (the file as it was is kept as a version)")
    b = sub.add_parser("build", help="read every linked picture again from its file, then export: the figure rebuilt from "
                                     "plots a script just re-made")
    export_arguments(b)
    b.add_argument("--save", action="store_true", help="save the document with the new pictures too (the file as it was is kept as a version)")
    b.set_defaults(func=cmd_export, refresh=True)
    e.set_defaults(func=cmd_export)

    n = sub.add_parser("info", help="a document's pages, their sizes and descriptions (alt text)")
    n.add_argument("document")
    n.add_argument("--json", action="store_true", help="as JSON, for other programs")
    n.set_defaults(func=cmd_info)

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

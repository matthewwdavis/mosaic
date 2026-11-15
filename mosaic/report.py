"""Figure report: what each panel of a figure is and how it's placed, for a methods section, a
reviewer, or whoever rebuilds the figure next. For every picture on the chosen pages: where it
comes from (and whether that file is still there), its copies, its size and place on the page,
its scale, crop and turns, its resolution, and its calibration and scale bars.

It's written in any of four formats: HTML (a page for a browser), Markdown (notes, a README),
CSV (a spreadsheet, one row per panel) and PDF, laid out with mosaic's own text engine.
"""
from __future__ import annotations

import csv
import datetime
import html
import io
import os
import uuid

from .assets import resolve_link
from .model import iter_items
from .progress import Cancelled, Progress

UNITS = {"pt": 1.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "in": 72.0}
COLUMNS = [("panel", "Panel"), ("source", "Source"), ("copies", "Copies"), ("size", "Size"), ("place", "Place"),
           ("scale", "Scale"), ("crop", "Crop"), ("turns", "Turns"), ("resolution", "Resolution"),
           ("calibration", "Calibration and scale bars")]
CSV_FIELDS = ["page", "page_name", "panel", "source", "file_found", "copies", "x", "y", "width", "height", "unit",
              "scale_percent_across", "scale_percent_down", "crop_left_percent", "crop_top_percent", "crop_right_percent",
              "crop_bottom_percent", "rotation_degrees", "flipped_across", "flipped_down", "resolution_ppi",
              "calibration", "scale_bars"]


def _n(v: float, digits: int = 2) -> str:
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _source(pic: dict, asset: dict, doc_dir: str | None) -> tuple[str, bool | None]:
    """Where a picture comes from, and whether its linked file is there (None if it isn't linked)."""
    if pic.get("equation"):
        return f"equation: {pic['equation'].get('tex', '')}", None
    var = asset["variants"].get(asset.get("primary")) or next(iter(asset["variants"].values()))
    if not var.get("src"):
        return f"{asset.get('name', 'picture')} (kept in the figure)", None
    return var["src"], bool(resolve_link(var, doc_dir))


def rows(doc: dict, pages: list[int] | None = None, unit: str = "cm", doc_dir: str | None = None) -> list[dict]:
    """One row per picture on the chosen pages: the report's columns as text, and the numbers."""
    k = UNITS.get(unit, UNITS["cm"])
    out = []
    for pi in (pages if pages is not None else range(len(doc["pages"]))):
        page = doc["pages"][pi]
        items = list(iter_items(page.get("items", [])))
        for pic in items:
            if pic.get("type") != "picture" or pic.get("asset") not in doc["assets"]:
                continue
            asset = doc["assets"][pic["asset"]]
            sizes = asset.get("page_sizes")
            sw, sh = sizes[pic.get("page_index", 0)] if sizes else asset["size_pt"]
            x, y, w, h = pic["frame"]
            l, t, r, b = pic.get("crop") or [0, 0, 0, 0]
            sx, sy = w / max(sw * (1 - l - r), 1e-9), h / max(sh * (1 - t - b), 1e-9)
            src, found = _source(pic, asset, doc_dir)
            kinds = [kd.upper() for kd in ("pdf", "svg", "png", "tiff", "jpeg") if kd in asset["variants"]]
            raster = next((asset["variants"][kd] for kd in ("png", "tiff", "jpeg") if kd in asset["variants"]), None)
            vector = any(kd in asset["variants"] for kd in ("pdf", "svg"))
            ppi = None
            if raster and not vector and raster.get("px"):
                ppi = raster["px"][0] * (1 - l - r) / max(w / 72.0, 1e-9)
            rot = round(float(pic.get("rot") or 0.0), 2) % 360
            turns = ([f"turned {_n(rot, 1)}°"] if rot else []) + (["flipped across"] if pic.get("flip_h") else []) \
                + (["flipped down"] if pic.get("flip_v") else [])
            cal = ""
            sc = pic.get("scale") or {}
            if sc.get("per_pt"):
                ppp = raster["px"][0] / asset["size_pt"][0] if raster and raster.get("px") else None
                per = sc["per_pt"] / ppp if ppp else sc["per_pt"]
                how = {"typed": "typed in", "measured": "measured", "file": "from the file"}.get(sc.get("how"), "")
                cal = f"1 {'pixel' if ppp else 'point of the original'} = {per:.4g} {sc.get('unit', '')}" + (f" ({how})" if how else "")
            bars = [f"{_n(float(it.get('length', 0)), 4)} {it.get('unit', '')}" for it in items
                    if it.get("type") == "scalebar" and it.get("picture") == pic.get("id")]
            crop = [round(v * 100, 1) for v in (l, t, r, b)]
            name = pic.get("name") or asset.get("name") or "Picture"
            out.append({
                "page": pi + 1, "page_name": page.get("name", ""), "page_size": f"{_n(page['width'] / k)} × {_n(page['height'] / k)} {unit}",
                "panel": name, "source": src + ("" if found is not False else " (file not found; the copy kept in the figure is used)"),
                "file_found": "" if found is None else ("yes" if found else "no"), "copies": " + ".join(kinds),
                "size": f"{_n(w / k)} × {_n(h / k)} {unit}", "place": f"{_n(x / k)}, {_n(y / k)} {unit}",
                "scale": f"{_n(sx * 100, 1)}%" if abs(sx - sy) < 1e-4 else f"{_n(sx * 100, 1)}% across, {_n(sy * 100, 1)}% down",
                "crop": "none" if not any(crop) else ", ".join(f"{side} {_n(v, 1)}%" for side, v in zip(("left", "top", "right", "bottom"), crop) if v),
                "turns": ", ".join(turns) or "none",
                "resolution": "vector" if vector else (f"{ppi:.0f} ppi at this size" if ppi else "unknown"),
                "calibration": "; ".join(filter(None, [cal, ("scale bar " + ", ".join(bars)) if bars else ""])) or "none",
                # The numbers, for the CSV
                "x": round(x / k, 4), "y": round(y / k, 4), "width": round(w / k, 4), "height": round(h / k, 4), "unit": unit,
                "scale_percent_across": round(sx * 100, 3), "scale_percent_down": round(sy * 100, 3),
                "crop_left_percent": crop[0], "crop_top_percent": crop[1], "crop_right_percent": crop[2], "crop_bottom_percent": crop[3],
                "rotation_degrees": rot, "flipped_across": bool(pic.get("flip_h")), "flipped_down": bool(pic.get("flip_v")),
                "resolution_ppi": round(ppi) if ppi else "", "scale_bars": "; ".join(bars),
            })
    return out


def _pages(doc: dict, found: list[dict], pages: list[int] | None) -> list[tuple[int, dict, list[dict]]]:
    chosen = pages if pages is not None else range(len(doc["pages"]))
    return [(pi, doc["pages"][pi], [r for r in found if r["page"] == pi + 1]) for pi in chosen]


def _heading(pi: int, page: dict) -> str:
    """'Page 2', or 'Page 2: Supplement' when it has a name of its own."""
    name = (page.get("name") or "").strip()
    return f"Page {pi + 1}" + (f": {name}" if name and name != f"Page {pi + 1}" else "")


def _title(doc: dict) -> str:
    return (doc.get("meta") or {}).get("title") or "Figure"


def to_csv(found: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in found:
        w.writerow({**r, "calibration": r["calibration"] if r["calibration"] != "none" else ""})
    return buf.getvalue()


def to_markdown(doc: dict, found: list[dict], pages: list[int] | None, made: str, where: str) -> str:
    cell = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    out = [f"# Figure report: {_title(doc)}", "", f"{made}. {where}", ""]
    for pi, page, rs in _pages(doc, found, pages):
        out += [f"## {_heading(pi, page)}", ""]
        if not rs:
            out += ["No pictures on this page.", ""]
            continue
        out += ["| " + " | ".join(t for _, t in COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
        out += ["| " + " | ".join(cell(r[k]) for k, _ in COLUMNS) + " |" for r in rs]
        out.append("")
    return "\n".join(out)


def to_html(doc: dict, found: list[dict], pages: list[int] | None, made: str, where: str) -> str:
    e = html.escape
    parts = []
    for pi, page, rs in _pages(doc, found, pages):
        size = f"{rs[0]['page_size']}" if rs else ""
        parts.append(f"<h2>{e(_heading(pi, page))} <span class='size'>{e(size)}</span></h2>")
        if not rs:
            parts.append("<p>No pictures on this page.</p>")
            continue
        head = "".join(f"<th scope='col'>{e(t)}</th>" for _, t in COLUMNS)
        body = "".join("<tr>" + "".join(f"<td>{e(str(r[k]))}</td>" for k, _ in COLUMNS) + "</tr>" for r in rs)
        parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Figure report: {e(_title(doc))}</title>
<style>
  body {{ font: 14px/1.45 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1b1b1b; background: #fff; margin: 2rem auto;
         max-width: 1200px; padding: 0 1rem; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.2rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  .size, .meta {{ color: #5b5b5b; font-weight: normal; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; }}
  th, td {{ text-align: left; vertical-align: top; padding: 0.35rem 0.5rem; border-bottom: 1px solid #ddd; overflow-wrap: anywhere; }}
  th {{ background: #f3f3f3; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #1e1e1e; color: #e8e8e8; }} th {{ background: #2c2c2c; }}
    th, td {{ border-color: #3a3a3a; }} .size, .meta {{ color: #a8a8a8; }} }}
</style></head>
<body><h1>Figure report: {e(_title(doc))}</h1><p class="meta">{e(made)}. {e(where)}</p>
{"".join(parts)}
</body></html>
"""


def to_pdf(doc: dict, found: list[dict], pages: list[int] | None, made: str, where: str, base: str) -> str:
    """The report as a PDF, laid out with mosaic's own text engine on landscape A4 pages."""
    from . import model
    from .export.run import export_document
    from .fonts import get_font_index
    from .textlayout import layout_text
    fonts = get_font_index()
    W, H, M = 842.0, 595.0, 36.0
    widths = [0.12, 0.2, 0.06, 0.09, 0.08, 0.07, 0.1, 0.07, 0.08, 0.13]
    report = model.new_document(f"Figure report: {_title(doc)}")
    report["pages"] = []

    def body(text, size=6.5, bold=False, color="#1b1b1b"):
        return {"paragraphs": [{"align": "l", "runs": [{"t": text, "font": "Helvetica", "size": size, "bold": bold, "italic": False,
                                                        "color": color}]}], "insets": [0, 0, 0, 0], "wrap": True, "anchor": "t",
                "autofit": "shape"}

    def box(page, x, y, w, text, **kw):
        b = body(text, **kw)
        hh = layout_text(b, w, 1e5, fonts).autofit_height
        page["items"].append({"id": model.new_id("it"), "type": "shape", "geom": "rect", "textbox": True, "frame": [x, y, w, hh],
                              "rot": 0, "stroke": None, "fill": None, "text": b})
        return hh

    def rule(page, y, width=0.5, color="#bbbbbb"):
        page["items"].append({"id": model.new_id("it"), "type": "line", "points": [[M, y], [W - M, y]], "arrow_start": None,
                              "arrow_end": None, "stroke": {"color": color, "width": width, "cap": "flat"}})

    def new_page():
        page = model.new_page(f"Page {len(report['pages']) + 1}", W, H)
        page["background"] = "#ffffff"
        report["pages"].append(page)
        return page

    def header(page, y):
        x, tallest = M, 0.0
        for (_, title), f in zip(COLUMNS, widths):
            tallest = max(tallest, box(page, x, y, f * (W - 2 * M) - 4, title, bold=True))
            x += f * (W - 2 * M)
        rule(page, y + tallest + 2, 0.75, "#555555")
        return y + tallest + 5

    page = new_page()
    y = M + box(page, M, M, W - 2 * M, f"Figure report: {_title(doc)}", size=12, bold=True) + 4
    y += box(page, M, y, W - 2 * M, f"{made}. {where}", size=7, color="#5b5b5b") + 10
    for pi, pg, rs in _pages(doc, found, pages):
        if y > H - M - 60:
            page, y = new_page(), M
        y += box(page, M, y, W - 2 * M, _heading(pi, pg) + (f"  ({rs[0]['page_size']})" if rs else ""),
                 size=9, bold=True) + 4
        if not rs:
            y += box(page, M, y, W - 2 * M, "No pictures on this page.") + 10
            continue
        y = header(page, y)
        for r in rs:
            cells = [str(r[k]) for k, _ in COLUMNS]
            tallest = max(layout_text(body(c), f * (W - 2 * M) - 4, 1e5, fonts).autofit_height for c, f in zip(cells, widths))
            if y + tallest > H - M:
                page = new_page()
                y = header(page, M)
            x = M
            for c, f in zip(cells, widths):
                box(page, x, y, f * (W - 2 * M) - 4, c)
                x += f * (W - 2 * M)
            rule(page, y + tallest + 2)
            y += tallest + 5
        y += 10
    export_document(report, base, ["pdf"], fonts=fonts)
    return base + ".pdf"


def write(doc: dict, base: str, formats: list[str], pages: list[int] | None = None, unit: str = "cm",
          doc_path: str | None = None, progress: Progress | None = None) -> list[str]:
    """Write the report in each format (html, md, csv, pdf) as base + its extension. `progress`
    hears each step (progress.py); stopped part-way, the files written are removed again."""
    p = progress or Progress()
    weights = {"html": 0.2, "md": 0.1, "csv": 0.1, "pdf": 4.0}   # (rough seconds, for the bar)
    p.plan(1.0 + sum(weights.get(f, 0.1) for f in formats))
    doc_dir = os.path.dirname(doc_path) if doc_path else None
    p.step("Reading the pictures")
    found = rows(doc, pages, unit, doc_dir)
    p.advance(1.0)
    today = datetime.date.today()
    made = f"Made by mosaic on {today.day} {today:%B %Y}"
    where = f"From {doc_path}." if doc_path else "From a figure not saved yet."
    # Each file is written under a name of its own and takes its real name once all are done:
    # stopping part-way leaves the folder as it was, an earlier report's files included
    part = f"{base}.{uuid.uuid4().hex[:6]}.part"
    staged: list[tuple[str, str]] = []   # (written as, to be named)
    files = []
    try:
        if "html" in formats:
            p.step("Writing the HTML report")
            staged.append((part + ".html", base + ".html"))
            with open(part + ".html", "w", encoding="utf-8") as fh:
                fh.write(to_html(doc, found, pages, made, where))
            p.advance(weights["html"])
        if "md" in formats:
            p.step("Writing the Markdown report")
            staged.append((part + ".md", base + ".md"))
            with open(part + ".md", "w", encoding="utf-8") as fh:
                fh.write(to_markdown(doc, found, pages, made, where))
            p.advance(weights["md"])
        if "csv" in formats:
            p.step("Writing the CSV report")
            staged.append((part + ".csv", base + ".csv"))
            with open(part + ".csv", "w", encoding="utf-8", newline="") as fh:
                fh.write(to_csv(found))
            p.advance(weights["csv"])
        if "pdf" in formats:
            p.step("Writing the PDF report")
            staged.append((part + ".pdf", base + ".pdf"))
            to_pdf(doc, found, pages, made, where, part)
            p.advance(weights["pdf"])
        for tmp, path in staged:
            os.replace(tmp, path)
            files.append(path)
    except BaseException:   # (stopped, or something failed)
        for tmp, _ in staged:   # this report's own unfinished files
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    return files

"""Export a document's pages to files: one entry point for the app and the command line."""
from __future__ import annotations

import io
import os
import re
import uuid

import pikepdf

from ..assets import AssetCache, SourceResolver, get_cache
from ..fonts import FontIndex
from ..plottext import with_lifts
from ..progress import Cancelled, Progress
from ..resolve import Resolver
from . import raster
from .pdfwriter import PdfWriter
from .svgwriter import SvgWriter

FORMATS = ("pdf", "svg", "png", "tiff", "jpeg", "eps")


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip()).strip("_")
    return s or "page"


def _on_page(bbox, page: dict) -> bool:
    if bbox is None:
        return False
    return bbox[2] > 0 and bbox[3] > 0 and bbox[0] < float(page["width"]) and bbox[1] < float(page["height"])


def page_filename(base: str, page: dict, index: int, n_pages: int, ext: str) -> str:
    if n_pages == 1:
        return f"{base}.{ext}"
    return f"{base}_{index + 1:02d}_{_slug(page.get('name', ''))}.{ext}"


def page_thumbnail(doc: dict, index: int, width_px: int, cache: AssetCache | None = None,
                   fonts: FontIndex | None = None):
    """A small picture of one page on white (a PIL image `width_px` wide), as the PNG export
    would draw it, e.g. for the slide picker. Fonts placed PDFs leave out aren't embedded first."""
    doc = with_lifts(doc, cache)   # (plots drawn without the texts lifted out of them in dangerous mode)
    page = doc["pages"][index]
    resolved = [r for r in Resolver(doc, fonts).resolve_page(page) if _on_page(r.bbox, page)]
    w = PdfWriter(SourceResolver(doc, cache or get_cache(), None))
    w.add_page(page, resolved)
    w.finish(embed_fonts=False)
    buf = io.BytesIO()
    w.pdf.save(buf)
    w.close_sources()
    return raster.render_pdf_bytes(buf.getvalue(), width_px / float(page["width"]) * 72.0, transparent=False)[0]


# Rough seconds for each step of an export at 600 dpi (a 6-page figure with 19 plots, 2026-11-13),
# for the progress bar: it fills by these, and its time left is read from how fast it goes
W_LAYOUT = 0.2      # a page laid out
W_COMPOSE = 1.5     # a page into the PDF
W_FINISH = 2.0      # the PDF finished: fonts embedded, written out
W_CMYK = 2.0        # Ghostscript's CMYK rewrite
W_SVG = 0.1         # an SVG page
W_RENDER = 0.4      # a page drawn as an image (times (dpi / 600)²)
W_SAVE = 0.2        # and the image file written (the same)
W_PPTX = 1.0        # a page of the PowerPoint
W_EPS = 1.0         # an EPS page


def export_document(doc: dict, base: str, formats=("pdf",), pages: list[int] | None = None, dpi: float = 600.0,
                    transparent: bool = True, cmyk: bool = False, cmyk_profile: str | None = None,
                    doc_dir: str | None = None, cache: AssetCache | None = None,
                    fonts: FontIndex | None = None, embed_fonts: bool = True, progress: Progress | None = None) -> dict:
    """Write the chosen pages in each format. `base` is the output path without extension.

    PDF holds all chosen pages in one file; other formats write one file per page. `progress`
    hears each step (progress.py); stopped part-way (Cancelled), the files this export had
    written are removed again.
    """
    p = progress or Progress()
    cache = cache or get_cache()
    doc = with_lifts(doc, cache)   # (plots drawn without the texts lifted out of them in dangerous mode)
    sel = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
    n = len(sel)
    which = lambda i: f"page {i + 1} of {n}" if n > 1 else "the page"   # noqa: E731
    fmts = [f.lower().replace("jpg", "jpeg").replace("tif", "tiff").replace("tifff", "tiff") for f in formats]
    scale = (float(dpi) / 600.0) ** 2
    weight = {"pdf": W_CMYK if cmyk else 0, "svg": n * W_SVG, "png": n * (W_RENDER + W_SAVE) * scale,
              "tiff": n * (W_RENDER + W_SAVE) * scale, "jpeg": n * (W_RENDER + W_SAVE) * scale, "pptx": n * W_PPTX, "eps": n * W_EPS}
    needs_pdf = any(f in ("pdf", "png", "tiff", "jpeg", "eps") for f in fmts)
    p.plan(n * W_LAYOUT + (n * W_COMPOSE + W_FINISH if needs_pdf else 0) + sum(weight.get(f, 0) for f in fmts))
    resolver = Resolver(doc, fonts)
    # Items parked entirely off the page (PowerPoint's pasteboard habit) aren't exported
    resolved = []
    for i, page in enumerate(sel):
        p.step(f"Laying out {which(i)}")
        resolved.append([r for r in resolver.resolve_page(page) if _on_page(r.bbox, page)])
        p.advance(W_LAYOUT)
    os.makedirs(os.path.dirname(os.path.abspath(base)) or ".", exist_ok=True)
    files: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []      # what went as it should but is worth saying (fonts embedded for placed PDFs)
    for r_page in resolved:
        for r in r_page:
            warnings += r.warnings

    pdf_bytes: bytes | None = None

    def compose_pdf() -> bytes:
        nonlocal pdf_bytes
        if pdf_bytes is None:
            src = SourceResolver(doc, cache, doc_dir)
            w = PdfWriter(src, title=doc.get("meta", {}).get("title", ""))
            for i, (page, rp) in enumerate(zip(sel, resolved)):
                p.step(f"Building the PDF, {which(i)}")
                w.add_page(page, rp)
                p.advance(W_COMPOSE)
            p.step("Finishing the PDF (fonts)")
            buf = io.BytesIO()
            w.finish(embed_fonts)
            described = [(pg.get("name") or f"Page {i + 1}", pg["alt"].strip()) for i, pg in enumerate(sel) if (pg.get("alt") or "").strip()]
            if described:   # the figure in words (the Page panel's Description), as the PDF's Subject
                subject = described[0][1] if n == 1 else "\n".join(f"{name}: {alt}" for name, alt in described)
                w.pdf.docinfo[pikepdf.Name.Subject] = pikepdf.String(subject)
            w.pdf.save(buf, compress_streams=True, recompress_flate=False, deterministic_id=True,
                       object_stream_mode=pikepdf.ObjectStreamMode.generate)
            w.close_sources()
            warnings.extend(w.warnings + src.notes)
            notes.extend(w.notes)
            pdf_bytes = buf.getvalue()
            p.advance(W_FINISH)
        return pdf_bytes

    # Every file is written under a name of its own first and only takes its real name once the
    # whole export is done: stopping (or a failure) half-way leaves the folder as it was, with
    # any files an earlier export left there untouched
    token = uuid.uuid4().hex[:6]
    staged: list[tuple[str, str]] = []   # (written as, to be named)

    def staging(path: str) -> str:
        root, ext = os.path.splitext(path)
        tmp = f"{root}.{token}.part{ext}"
        staged.append((tmp, path))
        return tmp

    try:
        for fmt in fmts:
            if fmt == "pdf":
                path = f"{base}.pdf"
                data = compose_pdf()
                if cmyk:
                    from .postscript import pdf_to_cmyk
                    p.step("Converting the PDF to CMYK")
                    data = pdf_to_cmyk(data, cmyk_profile)
                    warnings.append("CMYK PDF: Ghostscript rewrote the file to convert colours")
                    p.advance(W_CMYK)
                p.step("Writing the PDF")
                with open(staging(path), "wb") as fh:
                    fh.write(data)
            elif fmt == "svg":
                src = SourceResolver(doc, cache, doc_dir)
                for i, (page, rp) in enumerate(zip(sel, resolved)):
                    p.step(f"Writing SVG, {which(i)}")
                    w = SvgWriter(src)
                    path = page_filename(base, page, i, len(sel), "svg")
                    with open(staging(path), "wb") as fh:
                        fh.write(w.page(page, rp))
                    warnings += w.warnings
                    p.advance(W_SVG)
                warnings += src.notes
            elif fmt in ("png", "tiff", "jpeg"):
                name = {"png": "PNG", "tiff": "TIFF", "jpeg": "JPEG"}[fmt]

                def drawing(i, name=name):
                    p.step(f"Drawing {name} at {dpi:g} dpi, {which(i)}")
                # (a page at a time, drawn then written: only one page's image is in memory)
                images = raster.iter_pdf_pages(compose_pdf(), dpi, transparent=transparent and fmt != "jpeg", on_page=drawing)
                ext = {"png": "png", "tiff": "tif", "jpeg": "jpg"}[fmt]
                for i, (page, im) in enumerate(zip(sel, images)):
                    p.advance(W_RENDER * scale)
                    p.step(f"Writing {name}, {which(i)}")
                    path = page_filename(base, page, i, len(sel), ext)
                    raster.save_image(im, staging(path), fmt, dpi, cmyk=cmyk and fmt != "png", cmyk_profile=cmyk_profile)
                    p.advance(W_SAVE * scale)
            elif fmt == "pptx":
                from .pptxwriter import write_pptx
                p.step("Writing the PowerPoint")
                path = f"{base}.pptx"
                warnings += write_pptx(doc, sel, staging(path), cache, doc_dir, fonts)
                p.advance(n * W_PPTX)
            elif fmt == "eps":
                from .postscript import pdf_page_to_eps
                for i, page in enumerate(sel):
                    p.step(f"Writing EPS, {which(i)}")
                    path = page_filename(base, page, i, len(sel), "eps")
                    pdf_page_to_eps(compose_pdf(), i, staging(path))
                    p.advance(W_EPS)
                warnings.append("EPS can't hold transparency; Ghostscript flattened any transparent areas")
            else:
                raise ValueError(f"unknown format {fmt!r}")
        for tmp, path in staged:
            os.replace(tmp, path)
            files.append(path)
    except BaseException:   # (stopped, or something failed)
        for tmp, _ in staged:   # this export's own unfinished files: no half-finished set is left
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    # Files bigger than the pages' journals take
    from .preflight import size_limits
    big, roomy = size_limits(doc, pages, files)
    warnings += big
    notes += roomy
    # De-duplicate while keeping order
    seen = set()
    warnings = [w for w in warnings if not (w in seen or seen.add(w))]
    notes = [n for n in notes if not (n in seen or seen.add(n))]
    return {"files": files, "warnings": warnings, "notes": notes}

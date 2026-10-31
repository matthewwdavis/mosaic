"""Export a document's pages to files: one entry point for the app and the command line."""
from __future__ import annotations

import io
import os
import re

from ..assets import AssetCache, SourceResolver, get_cache
from ..fonts import FontIndex
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


def export_document(doc: dict, base: str, formats=("pdf",), pages: list[int] | None = None, dpi: float = 600.0,
                    transparent: bool = True, cmyk: bool = False, cmyk_profile: str | None = None,
                    doc_dir: str | None = None, cache: AssetCache | None = None,
                    fonts: FontIndex | None = None) -> dict:
    """Write the chosen pages in each format. `base` is the output path without extension.

    PDF holds all chosen pages in one file; other formats write one file per page.
    """
    cache = cache or get_cache()
    sel = [doc["pages"][i] for i in (pages if pages is not None else range(len(doc["pages"])))]
    resolver = Resolver(doc, fonts)
    # Items parked entirely off the page (PowerPoint's pasteboard habit) aren't exported
    resolved = [[r for r in resolver.resolve_page(p) if _on_page(r.bbox, p)] for p in sel]
    os.makedirs(os.path.dirname(os.path.abspath(base)) or ".", exist_ok=True)
    files: list[str] = []
    warnings: list[str] = []
    for r_page in resolved:
        for r in r_page:
            warnings += r.warnings

    pdf_bytes: bytes | None = None

    def compose_pdf() -> bytes:
        nonlocal pdf_bytes
        if pdf_bytes is None:
            src = SourceResolver(doc, cache, doc_dir)
            w = PdfWriter(src, title=doc.get("meta", {}).get("title", ""))
            for page, rp in zip(sel, resolved):
                w.add_page(page, rp)
            buf = io.BytesIO()
            warnings.extend(w.fonts.finalize())
            w.pdf.save(buf, compress_streams=True, recompress_flate=False, deterministic_id=True)
            for s in w._open.values():
                s.close()
            warnings.extend(w.warnings + src.notes)
            pdf_bytes = buf.getvalue()
        return pdf_bytes

    for fmt in formats:
        fmt = fmt.lower().replace("jpg", "jpeg").replace("tif", "tiff").replace("tifff", "tiff")
        if fmt == "pdf":
            path = f"{base}.pdf"
            data = compose_pdf()
            if cmyk:
                from .postscript import pdf_to_cmyk
                data = pdf_to_cmyk(data, cmyk_profile)
                warnings.append("CMYK PDF: Ghostscript rewrote the file to convert colours")
            with open(path + ".tmp", "wb") as fh:
                fh.write(data)
            os.replace(path + ".tmp", path)
            files.append(path)
        elif fmt == "svg":
            src = SourceResolver(doc, cache, doc_dir)
            for i, (page, rp) in enumerate(zip(sel, resolved)):
                w = SvgWriter(src)
                path = page_filename(base, page, i, len(sel), "svg")
                with open(path + ".tmp", "wb") as fh:
                    fh.write(w.page(page, rp))
                os.replace(path + ".tmp", path)
                files.append(path)
                warnings += w.warnings
            warnings += src.notes
        elif fmt in ("png", "tiff", "jpeg"):
            images = raster.render_pdf_bytes(compose_pdf(), dpi, transparent=transparent and fmt != "jpeg")
            ext = {"png": "png", "tiff": "tif", "jpeg": "jpg"}[fmt]
            for i, (page, im) in enumerate(zip(sel, images)):
                path = page_filename(base, page, i, len(sel), ext)
                raster.save_image(im, path, fmt, dpi, cmyk=cmyk and fmt != "png", cmyk_profile=cmyk_profile)
                files.append(path)
        elif fmt == "eps":
            from .postscript import pdf_page_to_eps
            for i, page in enumerate(sel):
                path = page_filename(base, page, i, len(sel), "eps")
                pdf_page_to_eps(compose_pdf(), i, path)
                files.append(path)
            warnings.append("EPS can't hold transparency; Ghostscript flattened any transparent areas")
        else:
            raise ValueError(f"unknown format {fmt!r}")
    # De-duplicate while keeping order
    seen = set()
    warnings = [w for w in warnings if not (w in seen or seen.add(w))]
    return {"files": files, "warnings": warnings}

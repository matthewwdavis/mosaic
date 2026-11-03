"""PNG / TIFF / JPEG export: the page is composed as a PDF (lossless) and rendered once by
PDFium at the requested resolution, so every vector panel is rasterised straight from its
original vectors.
"""
from __future__ import annotations

import io
import os

from PIL import Image, ImageCms

from ..assets import PDFIUM_LOCK


def render_pdf_bytes(pdf_bytes: bytes, dpi: float, transparent: bool = True) -> list[Image.Image]:
    with PDFIUM_LOCK:
        return _render(pdf_bytes, dpi, transparent)


def _render(pdf_bytes: bytes, dpi: float, transparent: bool) -> list[Image.Image]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_bytes)
    images = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            bitmap = page.render(scale=dpi / 72.0, fill_color=(0, 0, 0, 0) if transparent else (255, 255, 255, 255),
                                 may_draw_forms=False, draw_annots=False)
            im = bitmap.to_pil()
            # PDFium rounds the pixel size up; use the nearest whole pixel like other export tools
            want = (max(1, round(page.get_width() * dpi / 72.0)), max(1, round(page.get_height() * dpi / 72.0)))
            if im.size != want:
                im = im.crop((0, 0, want[0], want[1]))
            images.append(im.convert("RGBA") if transparent else im.convert("RGB"))
            page.close()
    finally:
        doc.close()
    return images


def default_cmyk_profile() -> str | None:
    """A CMYK ICC profile shipped with Ghostscript in this environment, else the OS's generic one."""
    import sys
    cands = [os.path.join(sys.prefix, "share", "ghostscript", d, "iccprofiles", "default_cmyk.icc")
             for d in ("", )]
    gs_share = os.path.join(sys.prefix, "share", "ghostscript")
    if os.path.isdir(gs_share):
        for sub in sorted(os.listdir(gs_share)):
            cands.append(os.path.join(gs_share, sub, "iccprofiles", "default_cmyk.icc"))
    cands += ["/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc",
              r"C:\Windows\System32\spool\drivers\color\RSWOP.icm"]
    return next((c for c in cands if os.path.exists(c)), None)


def to_cmyk(im: Image.Image, profile: str | None = None) -> tuple[Image.Image, bytes]:
    """Convert sRGB to CMYK through an ICC profile; returns the image and the profile bytes."""
    profile = profile or default_cmyk_profile()
    if not profile:
        raise RuntimeError("no CMYK ICC profile found; choose one in the export options")
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    srgb = ImageCms.createProfile("sRGB")
    cmyk = ImageCms.getOpenProfile(profile)
    out = ImageCms.profileToProfile(im, srgb, cmyk, renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                    outputMode="CMYK", flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
    with open(profile, "rb") as fh:
        return out, fh.read()


def save_image(im: Image.Image, path: str, fmt: str, dpi: float, cmyk: bool = False,
               cmyk_profile: str | None = None) -> None:
    fmt = fmt.lower()
    icc = None
    if cmyk:
        if fmt == "png":
            raise ValueError("PNG can't hold CMYK; use TIFF or JPEG")
        im, icc = to_cmyk(im, cmyk_profile)
    elif im.mode in ("RGB", "RGBA"):
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    if fmt == "jpeg" and im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    kwargs = {"dpi": (dpi, dpi)}
    if icc:
        kwargs["icc_profile"] = icc
    tmp = path + ".tmp"
    if fmt == "png":
        im.save(tmp, "PNG", optimize=False, **kwargs)
    elif fmt == "tiff":
        im.save(tmp, "TIFF", compression="tiff_lzw", **kwargs)
    elif fmt == "jpeg":
        im.save(tmp, "JPEG", quality=95, subsampling=0, **kwargs)
    else:
        raise ValueError(f"unknown raster format {fmt}")
    os.replace(tmp, path)

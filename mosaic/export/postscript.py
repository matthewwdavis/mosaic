"""Optional Ghostscript-based outputs: EPS pages and CMYK PDF (never the default)."""
from __future__ import annotations

import os
import subprocess
import tempfile

from ..assets import tool_path
from .raster import default_cmyk_profile


def _gs() -> str:
    exe = tool_path("gs") or tool_path("gswin64c") or tool_path("gswin32c")
    if not exe:
        raise RuntimeError("Ghostscript is needed for EPS and CMYK PDF export")
    return exe


def pdf_page_to_eps(pdf_bytes: bytes, page_index: int, out_path: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.pdf")
        with open(src, "wb") as fh:
            fh.write(pdf_bytes)
        n = page_index + 1
        subprocess.run([_gs(), "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=eps2write", "-dEPSCrop",
                        f"-dFirstPage={n}", f"-dLastPage={n}", "-r1200", f"-sOutputFile={out_path}", src],
                       check=True, capture_output=True)


def pdf_to_cmyk(pdf_bytes: bytes, profile: str | None = None) -> bytes:
    profile = profile or default_cmyk_profile()
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
        with open(src, "wb") as fh:
            fh.write(pdf_bytes)
        cmd = [_gs(), "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
               "-sColorConversionStrategy=CMYK", "-sProcessColorModel=DeviceCMYK",
               "-dEmbedAllFonts=true", "-dAutoRotatePages=/None", f"-sOutputFile={out}"]
        if profile:
            cmd.append(f"-sOutputICCProfile={profile}")
        subprocess.run(cmd + [src], check=True, capture_output=True)
        with open(out, "rb") as fh:
            return fh.read()

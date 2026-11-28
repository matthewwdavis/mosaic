"""Optional Ghostscript-based outputs: EPS pages and CMYK PDF (never the default)."""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile

import pikepdf

from ..assets import tool_path
from .raster import default_cmyk_profile


class GhostscriptError(subprocess.CalledProcessError):
    """Ghostscript stopped: says what it said (its error lines), not only its exit status.
    The whole of what it wrote is in .output for the log."""

    def __init__(self, what: str, returncode: int, cmd, said: str):
        super().__init__(returncode, cmd, output=said)
        self.what = what

    def __str__(self) -> str:
        lines = [ln.strip() for ln in (self.output or "").splitlines() if ln.strip()]
        errors = list(dict.fromkeys(ln.strip("* ").strip() for ln in lines   # (not its stack dumps)
                                    if re.search(r"error|\*\*\*\*", ln, re.I) and "--nostringval--" not in ln))
        return f"Ghostscript couldn't make the {self.what} (exit {self.returncode}): " + ("; ".join(errors[:4]) or
                                                                                          "; ".join(lines[-3:]) or "it said nothing")


def _gs() -> str:
    exe = tool_path("gs") or tool_path("gswin64c") or tool_path("gswin32c")
    if not exe:
        raise RuntimeError("Ghostscript is needed for EPS and CMYK PDF export")
    return exe


def _run_gs(args: list[str], what: str) -> None:
    cmd = [_gs(), *args]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode:
        said = (proc.stdout or b"").decode("utf-8", "replace") + (proc.stderr or b"").decode("utf-8", "replace")
        raise GhostscriptError(what, proc.returncode, cmd, said)


def _gs_path(path: str) -> str:
    """A path as Ghostscript's lists of permitted files take it (forward slashes on Windows too)."""
    return os.path.realpath(path).replace(os.sep, "/")


def pdf_page_to_eps(pdf_bytes: bytes, page_index: int, out_path: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.pdf")
        with open(src, "wb") as fh:
            fh.write(pdf_bytes)
        n = page_index + 1
        _run_gs(["-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=eps2write", "-dEPSCrop",
                 f"-dFirstPage={n}", f"-dLastPage={n}", "-r1200", f"-sOutputFile={out_path}", src], "EPS")


def pdf_to_cmyk(pdf_bytes: bytes, profile: str | None = None) -> bytes:
    profile = profile or default_cmyk_profile()
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
        with open(src, "wb") as fh:
            fh.write(pdf_bytes)
        cmd = ["-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
               "-sColorConversionStrategy=CMYK", "-sProcessColorModel=DeviceCMYK",
               "-dEmbedAllFonts=true", "-dAutoRotatePages=/None", f"-sOutputFile={out}"]
        if profile:
            # -dSAFER lets Ghostscript read only its own files and the ones it's given, so the profile
            # (the system's, in /System/Library/ColorSync or System32, when Ghostscript has none of its
            # own as a file) goes in as a copy here, the one other file it may read; 11-27
            icc = os.path.join(tmp, "cmyk.icc")
            shutil.copyfile(profile, icc)
            cmd += [f"--permit-file-read={_gs_path(icc)}", f"-sOutputICCProfile={_gs_path(icc)}"]
        _run_gs(cmd + [src], "CMYK PDF")
        with open(out, "rb") as fh:
            data = fh.read()
    # (Ghostscript can say "Output may be incorrect" and still finish without an error: the pages counted)
    with pikepdf.open(io.BytesIO(pdf_bytes)) as a, pikepdf.open(io.BytesIO(data)) as b:
        if len(b.pages) != len(a.pages):
            raise RuntimeError(f"Ghostscript's CMYK PDF has {len(b.pages)} of the {len(a.pages)} pages")
    return data

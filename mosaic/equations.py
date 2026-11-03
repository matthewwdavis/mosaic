"""Equations: LaTeX maths drawn by matplotlib's mathtext as a PDF and an SVG of the same size, with
real text: the PDF embeds its fonts (TrueType subsets), and the SVG names them. The figure places
them like any plot, so an equation prints exactly as drawn.

Fonts: "figure" sets the maths in the figure's text font (Helvetica unless changed), with STIX
Sans for the symbols that font lacks; "cm" in Computer Modern, LaTeX's own. A font installed as
a collection (.ttc, as Helvetica is on a Mac) has its faces copied out once, since matplotlib
reads only single fonts.

Both files are a whole number of points across and down, the equation's ink PAD in from their top
left: matplotlib rounds a tightly cropped PDF page to whole points but not an SVG, and the two
copies of a picture must match.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import threading

from .fonts import config_dir

PAD = 0.2                  # pt between the ink and the page's top and left edges
_lock = threading.Lock()   # matplotlib's settings are global
_faces: dict = {}          # (family, style) -> the family name matplotlib knows the face by


def _mpl():
    import logging

    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # fonts it can't weigh
    return matplotlib


def _face_name(family: str, bold: bool, italic: bool) -> str | None:
    """The figure's font face for matplotlib: added to its font list (copied out of a collection
    first), and the name it goes by; None if there's no such font."""
    key = (family, bold, italic)
    if key in _faces:
        return _faces[key]
    from matplotlib import font_manager

    from .fonts import get_font_index
    try:
        ref, _ = get_font_index().find(family, bold, italic)
        path = ref.path
        if path.lower().endswith((".ttc", ".otc")):
            from fontTools.ttLib import TTCollection
            folder = os.path.join(config_dir(), "math-fonts")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{ref.ps_name}.ttf")
            if not os.path.exists(path):
                TTCollection(ref.path).fonts[ref.index].save(path + ".tmp")
                os.replace(path + ".tmp", path)
        font_manager.fontManager.addfont(path)
        _faces[key] = font_manager.FontProperties(fname=path).get_name()
    except Exception:
        _faces[key] = None
    return _faces[key]


def _settings(font: str, family: str) -> dict:
    rc = {"pdf.fonttype": 42, "svg.fonttype": "none", "svg.hashsalt": "mosaic"}
    if font == "cm":
        rc["mathtext.fontset"] = "cm"
        return rc
    rm, it, bf = _face_name(family, False, False), _face_name(family, False, True), _face_name(family, True, False)
    if not rm:
        rc["mathtext.fontset"] = "dejavusans"
        return rc
    rc.update({"mathtext.fontset": "custom", "mathtext.rm": rm, "mathtext.sf": rm, "mathtext.fallback": "stixsans",
               "mathtext.it": f"{it or rm}:italic", "mathtext.bf": f"{bf or rm}:bold"})
    return rc


def _ink(fig) -> tuple[float, float, float, float]:
    """The box round a figure's ink as its PDF draws it (points, from the top left)."""
    import io

    import numpy as np
    import pypdfium2 as pdfium

    from .assets import PDFIUM_LOCK
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", transparent=True)
    with PDFIUM_LOCK:
        doc = pdfium.PdfDocument(buf.getvalue())
        try:
            ink = np.asarray(doc[0].render(scale=10, fill_color=(0, 0, 0, 0)).to_pil().convert("RGBA"))[:, :, 3] > 0
        finally:
            doc.close()
    rows, cols = np.flatnonzero(ink.any(axis=1)), np.flatnonzero(ink.any(axis=0))
    if not len(rows):
        raise ValueError("it draws nothing")
    return cols[0] / 10, rows[0] / 10, (cols[-1] + 1) / 10, (rows[-1] + 1) / 10


def check_tex(tex: str) -> str | None:
    """What's wrong with some maths, in mathtext's words, or None."""
    _mpl()
    from matplotlib.mathtext import MathTextParser
    try:
        MathTextParser("path").parse(f"${tex}$")
    except ValueError as exc:
        msg = str(exc).strip().splitlines()[-1] if str(exc).strip() else "it can't be read as maths"
        msg = re.sub(r",?\s*\(line:\d+, col:\d+\)", "", re.sub(r"^\w+(Exception|Error):\s*", "", msg))
        m = re.match(r"Expected (.*), found (.*?)\s*\(at char (\d+)\)", msg)
        if m:   # pyparsing's long lists of what it would have taken say little
            want, found, at = m.groups()
            want = "something else" if len(want) > 40 else want
            msg = f"expected {want} but found {'the end' if found == 'end of text' else found}, at character {int(at) + 1}"
        return re.sub(r",\s*found .*\(at char \d+\)$", "", msg)
    return None


def render(tex: str, size: float = 6.0, font: str = "figure", family: str = "Helvetica",
           color: str = "#000000") -> tuple[str, str]:
    """(PDF path, SVG path) of one equation, in a new temporary folder the caller removes."""
    _mpl()
    from matplotlib import rc_context
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    error = check_tex(tex)
    if error:
        raise ValueError(error)
    with _lock, rc_context(_settings(font, family)):
        # Its ink, from a PDF of it with room round it, drawn at 10 pixels a point: mathtext's own
        # box can fall short of the ink (limits over a sum, in some fonts), and its layout at a
        # drawing's resolution differs from a PDF's (fraction bars, say)
        fig = Figure(figsize=(1, 1), dpi=72, facecolor="none")
        canvas = FigureCanvasAgg(fig)
        text = fig.text(0, 0, f"${tex}$", fontsize=float(size), color=color, va="baseline", transform=fig.dpi_scale_trans)
        box = text.get_window_extent(canvas.get_renderer())
        room = 4 * float(size)
        big_w, big_h = math.ceil(box.width + 2 * room), math.ceil(box.height + 2 * room)
        fig.set_size_inches(big_w / 72, big_h / 72)
        text.set_position((room / 72, room / 72))
        x0, y0, x1, y1 = _ink(fig)   # points, from the top left
        w, h = max(math.ceil(x1 - x0 + 2 * PAD - 1e-6), 1), max(math.ceil(y1 - y0 + 2 * PAD - 1e-6), 1)
        fig.set_size_inches(w / 72, h / 72)
        # The ink's top left PAD in from the page's
        text.set_position(((room - x0 + PAD) / 72, (h - ((big_h - room) - y0 + PAD)) / 72))
        folder = tempfile.mkdtemp(prefix="mosaic-eq-")
        try:
            out = os.path.join(folder, "equation")
            fig.savefig(out + ".pdf", transparent=True, metadata={"Creator": "mosaic", "Producer": None})
            fig.savefig(out + ".svg", transparent=True, metadata={"Creator": "mosaic", "Date": None})
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return out + ".pdf", out + ".svg"

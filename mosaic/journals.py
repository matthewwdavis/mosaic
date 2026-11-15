"""Page sizes: standard paper, slide and poster sizes, and journal figure sizes.

The journals' table (JOURNALS, RULES) is the shared library's (_labapp/journals.py: prose sizes
and relabels a manuscript's figures by the same one); the notes below say how it was made. Your
own journals (a name, widths and a depth: Size > My Journals) are kept in one file that prose
reads too (user_file) and listed with the others (load_user, save_user).

Choosing a journal and a figure type sets the page to that type's width and the journal's
maximum figure depth ("Fit to content" crops it afterwards). To add a journal, add an entry
with its widths and depth and say where the numbers come from.

Where a journal publishes no figure sizes, the widths and depth were measured from a
published open-access article (PubMed Central, 2025-26): the width of a text column, the full
text width, and the depth of the text block. Measured widths are rounded to the nearest
0.5 mm and depths down to the whole millimetre. Checked against PNAS's published sizes, the
method gets the column width within 0.2 mm; the full text width can be up to ~3 mm wider
than a journal's stated double-column figure width.

Each journal also has its panel labels' look ("labels": font, size, bold, case, and form: how a
letter is written, "a", "(a)") and its rules for the rest of a figure's text ("text": the
smallest and largest size in points, and the fonts it accepts; "fonts_only" when it accepts no
others, "about" when its sizes are approximate). They come from the journal's own guidelines,
read on 2026-11-04. Where those don't say how labels look, the labels in a figure of a published
open-access article in the journal were measured (PubMed Central, 2025-26; "measured"): vector
labels read from the PDF, pictured ones from the height and weight of their letters.

Check and Export also follow each journal's final-figure rules, read on 2026-11-04: "lines", the
thinnest and thickest line in points ("about" when approximate); "pictures", the resolution it
asks of a placed picture of each kind (photo, combination: a photo with text or lines, line_art;
picturekind.py), with "vector" naming the kinds it wants as vector artwork rather than pictures;
and "export", the files it takes (mosaic's formats), their colour ("rgb", "rgb_preferred",
"either", "cmyk_preferred", "cmyk"), the largest file in MB ("firm" unless asked "where
possible"), the highest resolution, and whether fonts must be embedded or alpha channels are
refused. Where a journal states none, its publisher's guide gives them (Cell Press, OUP, Wiley,
Nature Portfolio), and each source says so; where neither does, mosaic's own rules apply (0.25 pt
lines, 300 dpi pictures).
"""
from __future__ import annotations

import os

from ._labapp import journals as _shared
from ._labapp.journals import JOURNALS, MM, RULES   # noqa: F401 (JOURNALS: one list, changed in place as your own are added)

# name, width mm, height mm, and the group the size lists show it in. Slides are PowerPoint's
# sizes (16:9 its default, 4:3 its old Standard, 16:10 its On-screen Show); posters the usual
# conference sizes (48 x 36 in landscape, A0 portrait; Swap width and height turns either)
STANDARD_SIZES = [
    {"name": "A4", "width_mm": 210.0, "height_mm": 297.0, "group": "Paper"},
    {"name": "US Letter", "width_mm": 215.9, "height_mm": 279.4, "group": "Paper"},
    {"name": "Slide 16:9", "width_mm": 338.66667, "height_mm": 190.5, "group": "Slides"},
    {"name": "Slide 4:3", "width_mm": 254.0, "height_mm": 190.5, "group": "Slides"},
    {"name": "Slide 16:10", "width_mm": 254.0, "height_mm": 158.75, "group": "Slides"},
    {"name": "Poster 48 × 36 in", "width_mm": 1219.2, "height_mm": 914.4, "group": "Posters"},
    {"name": "Poster A0", "width_mm": 841.0, "height_mm": 1189.0, "group": "Posters"},
]
DEFAULT_SIZE = "A4"


def standard_size(name: str) -> tuple[float, float]:
    s = next(s for s in STANDARD_SIZES if s["name"] == name)
    return s["width_mm"] * MM, s["height_mm"] * MM


def journal_size(journal: str, figure_type: str) -> tuple[float, float]:
    j = next(j for j in JOURNALS if j["name"] == journal)
    t = next(t for t in j["types"] if t["name"] == figure_type)
    return t["width_mm"] * MM, j["depth_mm"] * MM


def preset_size(preset) -> tuple[float, float] | None:
    """The size a page preset names, {"standard": name} or {"journal": name, "type": figure type},
    in points; None if this version has no such size (one a newer version added, say)."""
    try:
        if preset.get("standard"):
            return standard_size(preset["standard"])
        if preset.get("journal"):
            return journal_size(preset["journal"], preset.get("type"))
    except (AttributeError, StopIteration):
        pass
    return None


# Your own journals ------------------------------------------------------------------------------

def user_file() -> str:
    """The file of your own journals: the one mosaic and prose share (a journal added in either
    is in both), or journals.json in MOSAIC_HOME when that's set (tests, and trying mosaic out)."""
    if os.environ.get("MOSAIC_HOME"):
        return os.path.join(os.environ["MOSAIC_HOME"], "journals.json")
    return _shared.shared_user_file()


def user_journals() -> list[dict]:
    """Your own journals, as kept."""
    return _shared.read_user(user_file())


def load_user() -> list[dict]:
    """Put your own journals in the list with the others (as mosaic starts, and after a change)."""
    return _shared.with_user(user_journals(), into=JOURNALS)


def save_user(journals: list[dict]) -> list[dict]:
    """Keep your own journals (each checked: a name not already listed, widths and a depth in
    millimetres; ValueError says what's wrong) and list them with the others."""
    kept = _shared.write_user(user_file(), journals)
    _shared.with_user(kept, into=JOURNALS)
    return kept

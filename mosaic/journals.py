"""Page sizes: standard paper, slide and poster sizes, and journal figure sizes.

Choosing a journal and a figure type sets the page to that type's width and the journal's
maximum figure depth ("Fit to content" crops it afterwards). To add a journal, add an entry
with its widths and depth and say where the numbers come from.

Where a journal publishes no figure sizes, the widths and depth were measured from a
published open-access article (PubMed Central, 2025): the width of a text column, the full
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
"""
from __future__ import annotations

MM = 72.0 / 25.4

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


def _measured(pmcid: str) -> str:
    return f"measured from a published article ({pmcid}, 2025); the journal publishes no figure sizes"


JOURNALS = sorted([
    {
        "name": "Nature",
        "depth_mm": 170.0,
        "types": [{"name": "Single column", "width_mm": 90.0}, {"name": "Double column", "width_mm": 180.0}],
        "note": "90 mm single column, 180 mm double column; full page depth 170 mm.",
        "source": "Nature's figure guidelines (research-figure-guide.nature.com)",
    },
    {
        "name": "Science",
        "depth_mm": 199.0,
        "types": [{"name": "1 column", "width_mm": 57.0}, {"name": "2 columns", "width_mm": 121.0},
                  {"name": "3 columns", "width_mm": 184.0}],
        "note": "5.7, 12.1 or 18.4 cm wide; 19.9 cm deep leaves room for the legend below the figure.",
        "source": "Science's manuscript instructions (widths) and the Science family figure guide, 2026 (depth)",
    },
    {
        "name": "Cell",
        "depth_mm": 200.0,
        "types": [{"name": "1 column", "width_mm": 85.0}, {"name": "1.5 columns", "width_mm": 114.0},
                  {"name": "Full width", "width_mm": 174.0}],
        "note": "85, 114 or 174 mm wide; Cell Press recommends figures at most 20 cm tall.",
        "source": "Cell Press figure guidelines (two-column journals such as Cell)",
    },
    {
        "name": "PNAS",
        "depth_mm": 225.0,
        "types": [{"name": "1 column", "width_mm": 87.0}, {"name": "1.5 columns", "width_mm": 114.0},
                  {"name": "2 columns", "width_mm": 178.0}],
        "note": "8.7, 11.4 or 17.8 cm wide; at most 22.5 cm tall to leave room for the legend.",
        "source": "PNAS Digital Art Guidelines (pnas.org)",
    },
    {
        "name": "New Phytologist",
        "depth_mm": 226.0,
        "types": [{"name": "Single column", "width_mm": 80.0}, {"name": "Double column", "width_mm": 170.0}],
        "note": "80 mm column in a double-column format; largest printed figure 170 x 226 mm.",
        "source": "New Phytologist author guidelines, 2011 (the current Wiley page couldn't be read automatically)",
    },
    {
        "name": "Genetics",
        "depth_mm": 243.0,
        "types": [{"name": "Single column", "width_mm": 85.5}, {"name": "Double column", "width_mm": 177.5}],
        "note": "85.5 mm column, 177.5 mm full text width, 243 mm text depth (same layout as G3).",
        "source": _measured("PMC12405997"),
    },
    {
        "name": "G3",
        "depth_mm": 243.0,
        "types": [{"name": "Single column", "width_mm": 85.5}, {"name": "Double column", "width_mm": 177.5}],
        "note": "85.5 mm column, 177.5 mm full text width, 243 mm text depth (same layout as Genetics).",
        "source": _measured("PMC12836119; depth from the Genetics article PMC12405997"),
    },
    {
        "name": "Molecular Plant",
        "depth_mm": 200.0,
        "types": [{"name": "1 column", "width_mm": 85.0}, {"name": "1.5 columns", "width_mm": 114.0},
                  {"name": "Full width", "width_mm": 174.0}],
        "note": "A Cell Press journal: 85, 114 or 174 mm wide; at most 20 cm tall.",
        "source": "Cell Press figure guidelines (Molecular Plant isn't among the journals with different sizes)",
    },
    {
        "name": "Plant Cell",
        "depth_mm": 200.0,
        "types": [{"name": "One column", "width_mm": 82.5}, {"name": "Two columns", "width_mm": 165.0}],
        "note": "3.25 in (8.25 cm) or 6.5 in (16.5 cm) wide; under 8 in (20 cm) tall to leave room for the legend.",
        "source": "The Plant Cell author guidelines (academic.oup.com/plcell)",
    },
    {
        "name": "Genome Biology",
        "depth_mm": 225.0,
        "types": [{"name": "Half page", "width_mm": 85.0}, {"name": "Full page", "width_mm": 170.0}],
        "note": "85 or 170 mm wide; at most 225 mm tall including the legend.",
        "source": "BMC (Genome Biology's publisher) figure guidelines",
    },
    {
        "name": "Genome Research",
        "depth_mm": 238.0,
        "types": [{"name": "Single column", "width_mm": 84.5}, {"name": "Double column", "width_mm": 175.0}],
        "note": "84.5 mm column, 175 mm full text width, 238 mm text depth.",
        "source": _measured("PMC12667386"),
    },
    {
        "name": "Heredity",
        "depth_mm": 238.0,
        "types": [{"name": "Single column", "width_mm": 87.5}, {"name": "Double column", "width_mm": 181.0}],
        "note": "87.5 mm column, 181 mm full text width, 238 mm text depth.",
        "source": _measured("PMC13545244"),
    },
    {
        "name": "Molecular Biology and Evolution",
        "depth_mm": 236.0,
        "types": [{"name": "Single column", "width_mm": 86.0}, {"name": "Double column", "width_mm": 178.0}],
        "note": "86 mm column, 178 mm full text width, 236 mm text depth (online-only journal).",
        "source": _measured("PMC13223747"),
    },
    {
        "name": "PLOS Genetics",
        "depth_mm": 222.3,
        "types": [{"name": "Minimum width", "width_mm": 66.8}, {"name": "Text column", "width_mm": 132.0},
                  {"name": "Full width", "width_mm": 190.5}],
        "note": "6.68 to 19.05 cm wide (13.2 cm lines up with the text column); at most 22.23 cm tall.",
        "source": "PLOS figure guidelines (journals.plos.org)",
    },
], key=lambda j: j["name"].lower())


def _labels(font: str, size: float, bold: bool, case: str, source: str, form: str = "a", measured: bool = False) -> dict:
    return {"font": font, "size": size, "bold": bold, "case": case, "form": form, "source": source, "measured": measured}


def _text(source: str, min_pt=None, max_pt=None, fonts=None, fonts_only=False, about=False) -> dict:
    return {"min_pt": min_pt, "max_pt": max_pt, "fonts": fonts or [], "fonts_only": fonts_only, "about": about,
            "source": source}


def _published(pmcid: str, what: str) -> str:
    return f"measured from a published figure ({pmcid}): {what}"


# Panel labels and text rules (see the module's notes), read from each journal's guidelines
RULES = {
    "Nature": {
        "labels": _labels("Helvetica", 8.0, True, "lower", "Nature's final submission guidelines: 8 pt bold, upright, lowercase a, b, c"),
        "text": _text("Nature's final submission guidelines: text 5–7 pt, sans-serif, preferably Helvetica or Arial "
                      "(Symbol for Greek, Courier for sequences)", 5.0, 7.0, ["Helvetica", "Arial", "Symbol", "Courier"]),
    },
    "Science": {
        "labels": _labels("Helvetica", 10.0, True, "upper", "Science's manuscript instructions: capital A, B, C, 10 pt bold"),
        "text": _text("Science's manuscript instructions: about 7 pt and never below 5 pt; sans-serif, Helvetica preferred",
                      5.0, None, ["Helvetica"]),
    },
    "Cell": {
        "labels": _labels("Arial", 9.0, True, "upper", "Cell Press figure guidelines: capital letters; size and weight "
                          + _published("PMC11813165, 2025", "9 pt bold"), measured=True),
        "text": _text("Cell Press figure guidelines: text about 6–8 pt; Arial only", 6.0, 8.0, ["Arial"], fonts_only=True, about=True),
    },
    "PNAS": {
        "labels": _labels("Helvetica", 12.0, False, "upper", "PNAS's guidelines don't say; "
                          + _published("PMC12772206, 2025", "12 pt regular capitals"), measured=True),
        "text": _text("PNAS's guidelines: 6–12 pt after reduction; standard fonts such as Arial, Helvetica, Times, Symbol",
                      6.0, 12.0, ["Arial", "Helvetica", "Times", "Times New Roman", "Symbol", "Mathematical Pi", "European Pi"]),
    },
    "PLOS Genetics": {
        "labels": _labels("Arial", 12.0, False, "upper", "PLOS figure guidelines: lettered panels, (A) or (a); the look "
                          + _published("PMC12758814, 2025", "12 pt regular capitals"), measured=True),
        "text": _text("PLOS figure guidelines: Arial, Times or Symbol only, 8–12 pt", 8.0, 12.0,
                      ["Arial", "Times", "Times New Roman", "Symbol"], fonts_only=True),
    },
    "Genetics": {
        "labels": _labels("Helvetica", 10.0, True, "lower", "Genetics author guidelines: lowercase a, b, c at the top left; "
                          "size and weight " + _published("PMC12693585, 2025", "10 pt bold"), measured=True),
        "text": _text("Genetics's guidelines set no sizes or fonts for figure text"),
    },
    "G3": {
        "labels": _labels("Helvetica", 10.0, True, "lower", "G3 author guidelines: lowercase a, b, c at the top left; size and "
                          "weight " + _published("PMC12836119, 2025", "10 pt Helvetica Bold"), measured=True),
        "text": _text("G3's guidelines set no sizes or fonts for figure text"),
    },
    "Genome Research": {
        "labels": _labels("Helvetica", 12.0, True, "upper", "Genome Research's digital art guidelines (final figures): capital "
                          "A, B, C, 12 pt bold, Helvetica or Arial"),
        "text": _text("Genome Research's guidelines: 8–10 pt, Helvetica or Arial", 8.0, 10.0, ["Helvetica", "Arial"]),
    },
    "Genome Biology": {
        "labels": _labels("Helvetica", 10.0, True, "upper", "Genome Biology's guidelines don't say; "
                          + _published("PMC12849586, 2025", "10 pt bold capitals"), measured=True),
        "text": _text("Genome Biology's guidelines ask only that text be legible at 85 or 170 mm wide"),
    },
    "Heredity": {
        "labels": _labels("Helvetica", 9.0, True, "upper", "Heredity's guidelines don't say; "
                          + _published("PMC13031541, 2025", "9 pt bold capitals"), measured=True),
        "text": _text("Springer Nature's artwork guide (linked from Heredity's): 5–7 pt, sans-serif, preferably Helvetica or Arial",
                      5.0, 7.0, ["Helvetica", "Arial"]),
    },
    "New Phytologist": {
        "labels": _labels("Helvetica", 8.0, True, "lower", "New Phytologist author guidelines: bold lowercase (a), (b); size "
                          + _published("PMC13669809, 2026", "8 pt"), form="(a)", measured=True),
        "text": _text("New Phytologist's guidelines set no sizes or fonts for figure text"),
    },
    "Molecular Plant": {
        "labels": _labels("Arial", 9.0, True, "upper", "Molecular Plant's guidelines: capital letters in Helvetica or Arial; size "
                          "and weight measured from a published Cell figure (Cell Press publishes Molecular Plant, and no "
                          "Molecular Plant figure PDF could be had; PMC11813165, 2025): 9 pt bold", measured=True),
        "text": _text("Molecular Plant's guidelines: Helvetica or Arial only; text about 6–8 pt (Cell Press figure guidelines)",
                      6.0, 8.0, ["Helvetica", "Arial"], fonts_only=True, about=True),
    },
    "Plant Cell": {
        "labels": _labels("Arial", 12.0, True, "lower", "The Plant Cell author guidelines: panel headers in a sans-serif font, "
                          "12 pt bold; lowercase as in its current figures (PMC13711675, 2026; its 2020 figure guide asks "
                          "for capitals)", measured=True),
        "text": _text("The Plant Cell author guidelines: 8 pt recommended, no smaller than 6 pt; Arial or Helvetica, not "
                      "Times New Roman or Calibri", 6.0, None, ["Arial", "Helvetica"], fonts_only=True),
    },
    "Molecular Biology and Evolution": {
        "labels": _labels("Helvetica", 10.0, True, "lower", "MBE's guidelines don't say; "
                          + _published("PMC13696352, 2026", "(a), (b) in 10 pt bold"), form="(a)", measured=True),
        "text": _text("MBE's guidelines set no sizes or fonts for figure text"),
    },
}
for _j in JOURNALS:
    _j.update(RULES.get(_j["name"], {}))


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

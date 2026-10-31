"""Page sizes: standard paper sizes and journal figure sizes.

Choosing a journal and a figure type sets the page to that type's width and the journal's
maximum figure depth ("Fit to content" crops it afterwards). To add a journal, add an entry
with its widths and depth and say where the numbers come from.

Where a journal publishes no figure sizes, the widths and depth were measured from a
published open-access article (PubMed Central, 2025): the width of a text column, the full
text width, and the depth of the text block. Measured widths are rounded to the nearest
0.5 mm and depths down to the whole millimetre. Checked against PNAS's published sizes, the
method gets the column width within 0.2 mm; the full text width can be up to ~3 mm wider
than a journal's stated double-column figure width.
"""
from __future__ import annotations

MM = 72.0 / 25.4

# name, width mm, height mm (portrait)
STANDARD_SIZES = [
    {"name": "A4", "width_mm": 210.0, "height_mm": 297.0},
    {"name": "US Letter", "width_mm": 215.9, "height_mm": 279.4},
    {"name": "Slide 16:9", "width_mm": 338.667, "height_mm": 190.5},
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


def standard_size(name: str) -> tuple[float, float]:
    s = next(s for s in STANDARD_SIZES if s["name"] == name)
    return s["width_mm"] * MM, s["height_mm"] * MM


def journal_size(journal: str, figure_type: str) -> tuple[float, float]:
    j = next(j for j in JOURNALS if j["name"] == journal)
    t = next(t for t in j["types"] if t["name"] == figure_type)
    return t["width_mm"] * MM, j["depth_mm"] * MM

"""Page sizes: standard paper sizes and journal figure sizes.

Choosing a journal and a figure type sets the page to that type's width and the journal's
maximum figure depth ("Fit to content" crops it afterwards). To add a journal, add an entry
with its widths and depth and say where the numbers come from.
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

JOURNALS = [
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
]


def standard_size(name: str) -> tuple[float, float]:
    s = next(s for s in STANDARD_SIZES if s["name"] == name)
    return s["width_mm"] * MM, s["height_mm"] * MM


def journal_size(journal: str, figure_type: str) -> tuple[float, float]:
    j = next(j for j in JOURNALS if j["name"] == journal)
    t = next(t for t in j["types"] if t["name"] == figure_type)
    return t["width_mm"] * MM, j["depth_mm"] * MM

"""Page sizes: standard paper, slide and poster sizes, and journal figure sizes.

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


def _measured(pmcid: str, year: int = 2025) -> str:
    return f"measured from a published article ({pmcid}, {year}); the journal publishes no figure sizes"


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
        "name": "Horticulture Research",
        "depth_mm": 241.0,
        "types": [{"name": "Single column", "width_mm": 85.5}, {"name": "Double column", "width_mm": 178.0}],
        "note": "85.5 mm column, 178 mm (7 in) full text width, 241 mm text depth.",
        "source": _measured("PMC13102514; the same in PMC13091401 and PMC13255517", 2026),
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
    {
        "name": "The Plant Journal",
        "depth_mm": 226.0,
        "types": [{"name": "Single column", "width_mm": 80.0}, {"name": "Double column", "width_mm": 168.0}],
        "note": "8 cm column; 16.8 cm full width (the guidelines keep it for composite photographs, but published "
                "figures of every kind use it); 226 mm text depth.",
        "source": "The Plant Journal author guidelines (an archived 2022 copy; the current Wiley page couldn't be read "
                  "automatically): 8 cm, and 16.8 cm for full-page figures; the depth measured from published articles "
                  "(PMC13725933, PMC13732550 and PMC13720327, 2026), whose columns match: 79.9 and 168.6 mm",
    },
], key=lambda j: j["name"].lower())


def _labels(font: str, size: float, bold: bool, case: str, source: str, form: str = "a", measured: bool = False) -> dict:
    return {"font": font, "size": size, "bold": bold, "case": case, "form": form, "source": source, "measured": measured}


def _text(source: str, min_pt=None, max_pt=None, fonts=None, fonts_only=False, about=False) -> dict:
    return {"min_pt": min_pt, "max_pt": max_pt, "fonts": fonts or [], "fonts_only": fonts_only, "about": about,
            "source": source}


def _published(pmcid: str, what: str) -> str:
    return f"measured from a published figure ({pmcid}): {what}"


def _lines(source: str, min_pt=None, max_pt=None, about=False) -> dict:
    return {"min_pt": min_pt, "max_pt": max_pt, "about": about, "source": source}


def _pictures(source: str, photo=None, combination=None, line_art=None, vector=()) -> dict:
    return {"photo": photo, "combination": combination, "line_art": line_art, "vector": list(vector), "source": source}


def _files(source: str, formats, colour="either", max_mb=None, firm=True, max_dpi=None, embed_fonts=False,
           no_alpha=False) -> dict:
    return {"formats": list(formats), "colour": colour, "max_mb": max_mb, "firm": firm, "max_dpi": max_dpi,
            "embed_fonts": embed_fonts, "no_alpha": no_alpha, "source": source}


_CELL_PRESS = "Cell Press figure guidelines"
_OUP = "OUP's guidance for preparing artwork"


# Panel labels and text rules (see the module's notes), read from each journal's guidelines
RULES = {
    "Nature": {
        "labels": _labels("Helvetica", 8.0, True, "lower", "Nature's final submission guidelines: 8 pt bold, upright, lowercase a, b, c"),
        "text": _text("Nature's final submission guidelines: text 5–7 pt, sans-serif, preferably Helvetica or Arial "
                      "(Symbol for Greek, Courier for sequences)", 5.0, 7.0, ["Helvetica", "Arial", "Symbol", "Courier"]),
        "lines": _lines("Nature's final submission guidelines: line weights 0.25–1 pt at final size", 0.25, 1.0),
        "pictures": _pictures("Nature's final submission guidelines: photos at least 300 dpi at the largest size used; graphs, "
                              "line art and text over photos as editable vector artwork", 300.0, vector=("line_art", "combination")),
        "export": _files("Nature's figure guide: vector files (PDF or EPS preferred, SVG accepted), not JPEG, TIFF or PNG; RGB "
                         "recommended, CMYK accepted; files under 50 MB where possible; fonts embedded", ["pdf", "eps", "svg"],
                         "rgb_preferred", 50.0, firm=False, embed_fonts=True),
    },
    "Science": {
        "labels": _labels("Helvetica", 10.0, True, "upper", "Science's manuscript instructions: capital A, B, C, 10 pt bold"),
        "text": _text("Science's manuscript instructions: about 7 pt and never below 5 pt; sans-serif, Helvetica preferred",
                      5.0, None, ["Helvetica"]),
        "lines": _lines("Science's manuscript instructions: lines at least 0.5 pt at the final reduced size (its 2022 figure "
                        "guide says 0.28 pt)", 0.5),
        "pictures": _pictures("Science's revised-manuscript instructions: greyscale and colour images, and line art that isn't "
                              "vector, at least 300 dpi at final size", 300.0, 300.0, 300.0),
        "export": _files("Science's revised-manuscript instructions: PDF, EPS or AI preferred, TIFF for raster figures, not Word or "
                         "PowerPoint; its 2022 figure guide asks for CMYK colour unless the paper is online only",
                         ["pdf", "eps", "tiff"], "cmyk_preferred"),
    },
    "Cell": {
        "labels": _labels("Arial", 9.0, True, "upper", "Cell Press figure guidelines: capital letters; size and weight "
                          + _published("PMC11813165, 2025", "9 pt bold"), measured=True),
        "text": _text("Cell Press figure guidelines: text about 6–8 pt; Arial only", 6.0, 8.0, ["Arial"], fonts_only=True, about=True),
        "lines": _lines(f"{_CELL_PRESS} (Cell's page links to them): line weights 0.5–1.5 pt", 0.5, 1.5),
        "pictures": _pictures(f"{_CELL_PRESS}: colour or greyscale figures at least 300 dpi, line art at least 1,000 dpi",
                              300.0, 300.0, 1000.0),
        "export": _files(f"{_CELL_PRESS}: TIFF or PDF preferred, EPS and JPEG accepted; RGB; at most 20 MB a figure; fonts "
                         "embedded", ["tiff", "pdf", "eps", "jpeg"], "rgb", 20.0, embed_fonts=True),
    },
    "PNAS": {
        "labels": _labels("Helvetica", 12.0, False, "upper", "PNAS's guidelines don't say; "
                          + _published("PMC12772206, 2025", "12 pt regular capitals"), measured=True),
        "text": _text("PNAS's guidelines: 6–12 pt after reduction; standard fonts such as Arial, Helvetica, Times, Symbol",
                      6.0, 12.0, ["Arial", "Helvetica", "Times", "Times New Roman", "Symbol", "Mathematical Pi", "European Pi"]),
        "lines": _lines("PNAS Digital Art Guidelines: graph lines at least 0.25 pt wide", 0.25),
        "pictures": _pictures("PNAS Digital Art Guidelines: photos at least 300 ppi, photos with type 600–900 ppi, line art "
                              "1000–1200 ppi, at publication size", 300.0, 600.0, 1000.0),
        "export": _files("PNAS's submission guidelines: TIFF, EPS, PDF or PPT; its Digital Art Guidelines: original RGB colour, "
                         "fonts embedded", ["tiff", "eps", "pdf", "pptx"], "rgb", embed_fonts=True),
    },
    "PLOS Genetics": {
        "labels": _labels("Arial", 12.0, False, "upper", "PLOS figure guidelines: lettered panels, (A) or (a); the look "
                          + _published("PMC12758814, 2025", "12 pt regular capitals"), measured=True),
        "text": _text("PLOS figure guidelines: Arial, Times or Symbol only, 8–12 pt", 8.0, 12.0,
                      ["Arial", "Times", "Times New Roman", "Symbol"], fonts_only=True),
        "lines": _lines("PLOS figure guidelines set no line widths"),
        "pictures": _pictures("PLOS figure guidelines: 300–600 dpi for every figure", 300.0, 300.0, 300.0),
        "export": _files("PLOS figure guidelines: TIFF or EPS only; RGB or greyscale; 300–600 dpi; 10 MB or less; no alpha "
                         "channels; fonts embedded", ["tiff", "eps"], "rgb", 10.0, max_dpi=600.0, embed_fonts=True,
                         no_alpha=True),
    },
    "Genetics": {
        "labels": _labels("Helvetica", 10.0, True, "lower", "Genetics author guidelines: lowercase a, b, c at the top left; "
                          "size and weight " + _published("PMC12693585, 2025", "10 pt bold"), measured=True),
        "text": _text("Genetics's guidelines set no sizes or fonts for figure text"),
        "lines": _lines(f"{_OUP} (the journal's page refers authors to OUP's for the rest): line thickness 0.25–1 pt",
                        0.25, 1.0),
        "pictures": _pictures("Genetics's guidelines: printed pictures at least 350 dpi, line art at least 600 dpi (1200 for "
                              f"complex or fine line art); {_OUP}: combination half-tones 600–900 dpi", 350.0, 600.0, 600.0),
        "export": _files("Genetics's guidelines: TIFF and other raster files, PDF for vector figures, not Word, AI or JPEG; "
                         f"{_OUP}: EPS, SVG and PNG too, RGB recommended, fonts embedded",
                         ["tiff", "pdf", "eps", "svg", "png"], "rgb_preferred", embed_fonts=True),
    },
    "G3": {
        "labels": _labels("Helvetica", 10.0, True, "lower", "G3 author guidelines: lowercase a, b, c at the top left; size and "
                          "weight " + _published("PMC12836119, 2025", "10 pt Helvetica Bold"), measured=True),
        "text": _text("G3's guidelines set no sizes or fonts for figure text"),
        "lines": _lines(f"{_OUP} (the journal's page refers authors to OUP's for the rest): line thickness 0.25–1 pt",
                        0.25, 1.0),
        "pictures": _pictures("G3's guidelines: printed pictures at least 350 dpi, line art at least 600 dpi (1200 for "
                              f"complex or fine line art); {_OUP}: combination half-tones 600–900 dpi", 350.0, 600.0, 600.0),
        "export": _files("G3's guidelines: TIFF and other raster files, PDF for vector figures, not Word, AI or JPEG; "
                         f"{_OUP}: EPS, SVG and PNG too, RGB recommended, fonts embedded",
                         ["tiff", "pdf", "eps", "svg", "png"], "rgb_preferred", embed_fonts=True),
    },
    "Genome Research": {
        "labels": _labels("Helvetica", 12.0, True, "upper", "Genome Research's digital art guidelines (final figures): capital "
                          "A, B, C, 12 pt bold, Helvetica or Arial"),
        "text": _text("Genome Research's guidelines: 8–10 pt, Helvetica or Arial", 8.0, 10.0, ["Helvetica", "Arial"]),
        "lines": _lines("Genome Research's digital art guidelines: rules 0.25 pt or heavier", 0.25),
        "pictures": _pictures("Genome Research's digital art guidelines: halftones 300 dpi, combination halftones 600–900 dpi, "
                              "line art 1000–1200 dpi, at publication size", 300.0, 600.0, 1000.0),
        "export": _files("Genome Research's digital art guidelines: TIFF, EPS, PDF, JPEG or AI only; original RGB colour; "
                         "fonts embedded", ["tiff", "eps", "pdf", "jpeg"], "rgb", embed_fonts=True),
    },
    "Genome Biology": {
        "labels": _labels("Helvetica", 10.0, True, "upper", "Genome Biology's guidelines don't say; "
                          + _published("PMC12849586, 2025", "10 pt bold capitals"), measured=True),
        "text": _text("Genome Biology's guidelines ask only that text be legible at 85 or 170 mm wide"),
        "lines": _lines("Genome Biology's guidelines: all lines wider than 0.25 pt at 85 or 170 mm wide", 0.25),
        "pictures": _pictures("Genome Biology's guidelines: about 300 dpi at the final size", 300.0, 300.0, 300.0),
        "export": _files("Genome Biology's guidelines: EPS, PDF, PowerPoint, TIFF, JPEG or PNG (or Word, BMP, CDX); no colour "
                         "mode stated; figures at most 10 MB; fonts embedded", ["pdf", "eps", "pptx", "tiff", "jpeg", "png"],
                         max_mb=10.0, embed_fonts=True),
    },
    "Heredity": {
        "labels": _labels("Helvetica", 9.0, True, "upper", "Heredity's guidelines don't say; "
                          + _published("PMC13031541, 2025", "9 pt bold capitals"), measured=True),
        "text": _text("Springer Nature's artwork guide (linked from Heredity's): 5–7 pt, sans-serif, preferably Helvetica or Arial",
                      5.0, 7.0, ["Helvetica", "Arial"]),
        "lines": _lines("Heredity's house style asks for rules no thinner than 1 pt without saying whether that covers figure "
                        "lines, and its artwork guide gives no line widths, so Check uses mosaic's 0.25 pt"),
        "pictures": _pictures("Nature Portfolio's guide to preparing final artwork (linked from Heredity's): photos at least "
                              "300 dpi; graphs and line art as vector files; text and lines over photos as editable vectors",
                              300.0, vector=("line_art", "combination")),
        "export": _files("Nature Portfolio's guide to preparing final artwork: AI, EPS, PDF or editable PowerPoint, not JPEG, PNG "
                         "or TIFF; RGB; each figure under 50 MB where possible", ["pdf", "eps", "pptx"], "rgb", 50.0,
                         firm=False),
    },
    "New Phytologist": {
        "labels": _labels("Helvetica", 8.0, True, "lower", "New Phytologist author guidelines: bold lowercase (a), (b); size "
                          + _published("PMC13669809, 2026", "8 pt"), form="(a)", measured=True),
        "text": _text("New Phytologist's guidelines set no sizes or fonts for figure text"),
        "lines": _lines("New Phytologist author guidelines: lines about 0.5 mm thick on figures drawn at twice their printed "
                        "size, so about 0.7 pt printed", 0.7, about=True),
        "pictures": _pictures("Wiley's figure guidelines (New Phytologist refers authors to them): images 300 dpi, line art 600 "
                              "dpi, and figures with both follow line art", 300.0, 600.0, 600.0),
        "export": _files("New Phytologist author guidelines: RGB; Wiley's figure guidelines: any standard file type after "
                         "acceptance (SVG isn't among those listed), under 10 MB each preferred",
                         ["pdf", "eps", "tiff", "png", "jpeg", "pptx"], "rgb", 10.0, firm=False),
    },
    "Molecular Plant": {
        "labels": _labels("Arial", 9.0, True, "upper", "Molecular Plant's guidelines: capital letters in Helvetica or Arial; size "
                          "and weight measured from a published Cell figure (Cell Press publishes Molecular Plant, and no "
                          "Molecular Plant figure PDF could be had; PMC11813165, 2025): 9 pt bold", measured=True),
        "text": _text("Molecular Plant's guidelines: Helvetica or Arial only; text about 6–8 pt (Cell Press figure guidelines)",
                      6.0, 8.0, ["Helvetica", "Arial"], fonts_only=True, about=True),
        "lines": _lines(f"{_CELL_PRESS} (Molecular Plant's page links to them): line weights 0.5–1.5 pt", 0.5, 1.5),
        "pictures": _pictures("Molecular Plant's final file checklist: colour figures at least 300 dpi; line art at least 1,000 "
                              f"dpi ({_CELL_PRESS})", 300.0, 300.0, 1000.0),
        "export": _files("Molecular Plant's final file checklist: TIFF, EPS, PDF, AI, PPT or JPG; RGB, at most 20 MB a figure "
                         f"and fonts embedded ({_CELL_PRESS})", ["tiff", "eps", "pdf", "pptx", "jpeg"], "rgb", 20.0,
                         embed_fonts=True),
    },
    "Plant Cell": {
        "labels": _labels("Arial", 12.0, True, "lower", "The Plant Cell author guidelines: panel headers in a sans-serif font, "
                          "12 pt bold; lowercase as in its current figures (PMC13711675, 2026; its 2020 figure guide asks "
                          "for capitals)", measured=True),
        "text": _text("The Plant Cell author guidelines: 8 pt recommended, no smaller than 6 pt; Arial or Helvetica, not "
                      "Times New Roman or Calibri", 6.0, None, ["Arial", "Helvetica"], fonts_only=True),
        "lines": _lines(f"{_OUP} (The Plant Cell's pages give no line widths): line thickness 0.25–1 pt", 0.25, 1.0),
        "pictures": _pictures("The Plant Cell author guidelines: at least 300 PPI; its detailed figure guidelines (2020): 600 ppi "
                              "for line graphs mixed with photographs, 1,000 ppi for line graphs saved as TIFF", 300.0, 600.0, 1000.0),
        "export": _files("The Plant Cell author guidelines: tif, jpeg or eps (the page dropped PDF in 2026; its 2020 figure "
                         f"guidelines still prefer it); RGB, not CMYK; {_OUP}: fonts embedded", ["tiff", "jpeg", "eps"], "rgb",
                         embed_fonts=True),
    },
    "Molecular Biology and Evolution": {
        "labels": _labels("Helvetica", 10.0, True, "lower", "MBE's guidelines don't say; "
                          + _published("PMC13696352, 2026", "(a), (b) in 10 pt bold"), form="(a)", measured=True),
        "text": _text("MBE's guidelines set no sizes or fonts for figure text"),
        "lines": _lines(f"{_OUP} (MBE's page refers authors to OUP's for the rest): line thickness 0.25–1 pt", 0.25, 1.0),
        "pictures": _pictures("MBE's guidelines: 300 dpi for colour and half-tone artwork, 1200 dpi for line drawings; "
                              f"{_OUP}: combination half-tones 600–900 dpi", 300.0, 600.0, 1200.0),
        "export": _files("MBE's guidelines: .tif, .eps, .ppt, .xls, .doc, .pdf, .gif or .jpg; "
                         f"{_OUP}: RGB recommended, fonts embedded", ["tiff", "eps", "pptx", "pdf", "jpeg"], "rgb_preferred",
                         embed_fonts=True),
    },
    "Horticulture Research": {
        "labels": _labels("Arial", 10.0, True, "upper", "Horticulture Research's guidelines: capital letters A, B, C at each "
                          "panel's upper left; the look measured in published figures (13 articles, 2026): mostly bold, "
                          "sans-serif ones in Arial (PMC13102514's, kept as text, 8.95 pt Arial Bold), 10 pt the middle size",
                          measured=True),
        "text": _text(f"{_OUP} (linked from Horticulture Research's guidelines): text no less than 7 pt; Arial, Times New "
                      "Roman, Courier or Symbol. OUP calls its guide tips rather than strict rules, so Check notes rather "
                      "than warns", 7.0, None, ["Arial", "Times New Roman", "Courier", "Symbol"], about=True),
        "lines": _lines(f"{_OUP} (linked from Horticulture Research's guidelines): line thickness 0.25–1 pt", 0.25, 1.0),
        "pictures": _pictures("Horticulture Research's guidelines: printed pictures at least 350 dpi, line art at least 600 "
                              f"dpi (1200 for complex or finely drawn line art); {_OUP}: combination half-tones 600–900 dpi",
                              350.0, 600.0, 600.0),
        "export": _files("Horticulture Research's guidelines: TIFF for photographs; EPS, AI or PDF for charts and diagrams; "
                         f"not Word or JPEG; {_OUP}: SVG and PNG too, RGB recommended, fonts embedded",
                         ["tiff", "eps", "pdf", "svg", "png"], "rgb_preferred", embed_fonts=True),
    },
    "The Plant Journal": {
        "labels": _labels("Helvetica", 8.0, False, "lower", "The Plant Journal author guidelines (2022 copy): lowercase "
                          "letters, lettering in 8 pt Helvetica; brackets and regular weight as Wiley letters every label "
                          "in its published figures (15 articles, 2026, where they print at about 9 pt)", form="(a)",
                          measured=True),
        "text": _text("The Plant Journal author guidelines (2022 copy): lettering in 8 pt Helvetica if possible, so Check "
                      "notes rather than warns", 8.0, None, ["Helvetica"], about=True),
        "lines": _lines("Neither The Plant Journal's guidelines nor Wiley's figure guidelines give line widths, so Check "
                        "uses mosaic's 0.25 pt"),
        "pictures": _pictures("Wiley's figure guidelines (The Plant Journal's page links to them): images 300 dpi, line art "
                              "600 dpi, and figures with both follow line art", 300.0, 600.0, 600.0),
        "export": _files("Wiley's figure guidelines: PDF or EPS for line art, TIFF or PNG for images, any standard file type "
                         "after acceptance (SVG isn't among those listed), under 10 MB each preferred; no colour mode "
                         "stated", ["pdf", "eps", "tiff", "png", "jpeg", "pptx"], "either", 10.0, firm=False),
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

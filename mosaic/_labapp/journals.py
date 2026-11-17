"""The journals both apps know: each one's figure sizes, the look of its panel labels, and its
rules for a figure's text, lines, pictures and files. mosaic sizes pages and checks figures by
them; prose sizes and relabels the figures of a manuscript by the same table.

JOURNALS is the list, sorted by name; each entry:

    name        "Nature"
    depth_mm    the deepest a figure may be
    types       [{"name": "Single column", "width_mm": 90.0}, ...]: the widths it takes
    any_width   True where a figure may be any width up to the widest type (the types are then
                handy presets, not the only widths: bioRxiv); absent for the rest
    note        the sizes in a sentence
    source      where the numbers come from
    labels, text, lines, pictures, export   its rules (RULES[name]); absent where it states none

Where a journal publishes no figure sizes, the widths and depth were measured from a published
open-access article (PubMed Central, 2025-26): the width of a text column, the full text width,
and the depth of the text block. Measured widths are rounded to the nearest 0.5 mm and depths
down to the whole millimetre. Checked against PNAS's published sizes, the method gets the column
width within 0.2 mm; the full text width can be up to ~3 mm wider than a journal's stated
double-column figure width.

bioRxiv is no journal's layout but Matthew's choice for the Monroe lab's preprints (2026-11-16):
a figure may be any size within a US Letter page's text area (0.75 in margins: 7 x 9.5 in), with
one column of the lab's two-column template (3.375 in) and the full width as presets. bioRxiv
itself sets no figure sizes or figure rules, so mosaic's own apply.

Panel labels ("labels": font, size, bold, case, and form: how a letter is written, "a", "(a)")
and the rules for the rest of a figure's text ("text": the smallest and largest size in points,
and the fonts it accepts; "fonts_only" when it accepts no others, "about" when its sizes are
approximate) come from the journal's own guidelines, read on 2026-11-04. Where those don't say
how labels look, the labels in a figure of a published open-access article in the journal were
measured ("measured"). "lines": the thinnest and thickest line in points; "pictures": the
resolution it asks of a placed picture of each kind (photo, combination, line_art), with "vector"
naming the kinds it wants as vector artwork; "export": the files it takes, their colour, the
largest file in MB ("firm" unless asked "where possible"), the highest resolution, and whether
fonts must be embedded or alpha channels are refused. Where a journal states none, its
publisher's guide gives them, and each source says so.

**A person's own journals** (user journals) sit beside these: a name, widths and a depth they
typed in, kept in one JSON file that both apps read (shared_user_file; read_user, write_user), so
a journal added in either is in both. They carry "user": True, an "id" that stays when the name
changes, no rules unless given, and whatever else an app keeps with them under its own key
("manuscript": prose's page, reference style and sections), which the other app hands back
untouched. with_user() puts them into a list with the built-in ones.
"""
from __future__ import annotations

import json
import os
import re

MM = 72.0 / 25.4


def _measured(pmcid: str, year: int = 2025) -> str:
    return f"measured from a published article ({pmcid}, {year}); the journal publishes no figure sizes"


JOURNALS = sorted([
    {
        "name": "bioRxiv",
        "depth_mm": 241.3,
        "types": [{"name": "One column", "width_mm": 85.7}, {"name": "Full width", "width_mm": 177.8}],
        "any_width": True,
        "note": "Any size on a US Letter page's text area: up to 7 in (177.8 mm) wide and 9.5 in (241.3 mm) tall, "
                "legend aside. One column (3.375 in, 85.7 mm) and full width are presets for the Monroe lab's "
                "two-column template.",
        "source": "Matthew's choice for the Monroe lab's bioRxiv preprints (2026-11-16): a US Letter page with 0.75 in "
                  "margins, as the lab's template has; bioRxiv itself sets no figure sizes",
    },
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
_BIORXIV = "bioRxiv sets no rules for figures (a preprint is posted as the authors' own PDF)"
_OUP = "OUP's guidance for preparing artwork"


# Panel labels and text rules (see the module's notes), read from each journal's guidelines
RULES = {
    "bioRxiv": {
        "labels": _labels("Helvetica", 8.0, True, "upper", "prose's bioRxiv (Monroe lab) template: its legends letter the "
                          "panels (A), (B) with the letter in bold, so the labels are bold capitals A, B, C; 8 pt "
                          "Helvetica, mosaic's usual label (Matthew's choice, 2026-11-16)"),
        "text": _text(f"{_BIORXIV}: no sizes or fonts for figure text"),
        "lines": _lines(f"{_BIORXIV}, so Check uses mosaic's 0.25 pt"),
        "pictures": _pictures(f"{_BIORXIV}, so Check uses mosaic's 300 dpi", 300.0, 300.0, 300.0),
        "export": _files(f"{_BIORXIV}: any of mosaic's files, in RGB or CMYK, to place in the manuscript",
                         ["pdf", "svg", "png", "tiff", "jpeg", "eps", "pptx"], "either"),
    },
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


BUILT_IN = [j["name"] for j in JOURNALS]


def widest(journal: dict) -> float:
    """The widest figure a journal takes, in mm."""
    return max(t["width_mm"] for t in journal["types"])


def size_fit(journal: dict, width_mm: float, height_mm: float, slack_mm: float = 0.05) -> dict:
    """A figure's size against a journal: {"type": the type it is as wide as (within slack_mm), or
    None; "wide": wider than the widest type; "deep": deeper than depth_mm; "odd": a width that is
    none of the types, which only matters where the journal takes fixed widths (no "any_width")}."""
    fits = next((t for t in sorted(journal["types"], key=lambda t: t["width_mm"])
                 if abs(t["width_mm"] - width_mm) <= slack_mm), None)
    wide = width_mm > widest(journal) + slack_mm
    return {"type": fits, "wide": wide, "deep": height_mm > journal["depth_mm"] + slack_mm,
            "odd": fits is None and not wide and not journal.get("any_width")}


# A person's own journals ---------------------------------------------------------------------------

MAX_MM = 5000.0   # (a poster is 1.2 m: nothing sensible is wider than this)
APP_PARTS = ("manuscript",)   # what an app keeps with a journal under its own key, as it gave it


def shared_user_file() -> str:
    """The one file of a person's own journals, read by every app that uses this table
    (LABAPP_JOURNALS: somewhere else, for tests)."""
    from . import platform
    return os.environ.get("LABAPP_JOURNALS") or os.path.join(platform.settings_dir("mosaic-prose"), "journals.json")


def slug(name: str) -> str:
    """A journal's name as a plain id: "Tree Genetics & Genomes" -> "tree_genetics_genomes"."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "journal"


def clean(entry: dict) -> dict:
    """A person's journal as it's kept: {"name", "depth_mm", "types": [{"name", "width_mm"}], "note",
    "source", "user": True}. Raises ValueError, in words for the person, when it can't be one."""
    if not isinstance(entry, dict):
        raise ValueError("A journal needs a name and its figure sizes.")
    name = " ".join(str(entry.get("name") or "").split())[:80]
    if not name:
        raise ValueError("Give the journal a name.")
    if name.lower() in {n.lower() for n in BUILT_IN}:
        raise ValueError(f"{name} is one of the journals already listed; give yours another name.")

    def mm(value, what: str) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{what} needs a number of millimetres.") from None
        if not 1.0 <= v <= MAX_MM:
            raise ValueError(f"{what} has to be between 1 and {MAX_MM:g} mm.")
        return round(v, 3)
    types, seen = [], set()
    for t in entry.get("types") or []:
        if not isinstance(t, dict):
            continue
        tname = " ".join(str(t.get("name") or "").split())[:60] or f"Width {len(types) + 1}"
        if tname.lower() in seen:
            raise ValueError(f"Two widths are called {tname}; give each its own name.")
        seen.add(tname.lower())
        types.append({"name": tname, "width_mm": mm(t.get("width_mm"), f"The width of {tname}")})
    if not types:
        raise ValueError("Give at least one figure width.")
    if len(types) > 12:
        raise ValueError("A journal can have up to 12 figure widths.")
    ident = str(entry.get("id") or "")
    if not re.fullmatch(r"[a-z0-9_]{1,40}", ident):
        ident = slug(name)
    out = {"id": ident, "name": name, "depth_mm": mm(entry.get("depth_mm"), "The greatest depth"), "types": types,
           "note": str(entry.get("note") or "")[:400], "source": str(entry.get("source") or "")[:400] or "added by you",
           "user": True}
    for key in ("labels", "text", "lines", "pictures", "export", *APP_PARTS):   # (rules, and each app's own part)
        if isinstance(entry.get(key), dict):
            out[key] = entry[key]
    return out


def read_user(path: str) -> list[dict]:
    """The person's own journals from their file, sorted by name; ones that can't be read as a
    journal are left out (the file is theirs: nothing is rewritten here)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    out, names, ids = [], set(), set()
    for entry in (data.get("journals") if isinstance(data, dict) else data) or []:
        try:
            j = clean(entry)
        except ValueError:
            continue
        if j["name"].lower() not in names and j["id"] not in ids:
            names.add(j["name"].lower())
            ids.add(j["id"])
            out.append(j)
    return sorted(out, key=lambda j: j["name"].lower())


def write_user(path: str, journals: list[dict]) -> list[dict]:
    """Keep the person's own journals (each checked: clean); returns them as kept."""
    kept, names, ids = [], set(), set()
    for entry in journals or []:
        j = clean(entry)
        if j["name"].lower() in names:
            raise ValueError(f"Two of your journals are called {j['name']}; give each its own name.")
        base, n = j["id"], 2
        while j["id"] in ids:   # (two names that come to the same id)
            j["id"] = f"{base[:37]}_{n}"
            n += 1
        names.add(j["name"].lower())
        ids.add(j["id"])
        kept.append(j)
    kept.sort(key=lambda j: j["name"].lower())
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"format": 1, "journals": kept}, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return kept


def with_user(user: list[dict], into: list | None = None) -> list[dict]:
    """The built-in journals and the person's own, sorted by name. Given `into` (a list an app
    already handed out), that list is changed in place, so everything holding it sees them."""
    both = sorted([j for j in JOURNALS if not j.get("user")] + list(user or []), key=lambda j: j["name"].lower())
    if into is None:
        return both
    into[:] = both
    return into

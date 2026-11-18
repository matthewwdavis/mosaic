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


# The groups every list of journals shows -----------------------------------------------------------

MY_JOURNALS = "My journals"


def group_of(journal: dict) -> str:
    """The group a journal is listed under, as prose's Journal menu has them: its publisher (the
    shared table's "publisher"; bioRxiv "In house"), "My journals" for your own."""
    return MY_JOURNALS if journal.get("user") else (journal.get("publisher") or "Other")


def grouped(journals: list[dict] | None = None) -> list[tuple[str, list[dict]]]:
    """[(group, its journals)], the groups and the journals in each in alphabetical order ("Other"
    last), as the editor's lists show them (journalGroups in inspector.js)."""
    groups: dict[str, list[dict]] = {}
    for j in sorted(JOURNALS if journals is None else journals, key=lambda j: j["name"].lower()):
        groups.setdefault(group_of(j), []).append(j)
    return sorted(groups.items(), key=lambda g: (g[0] == "Other", g[0].lower()))


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
    """Put your own journals, and those fetched from the library, in the list with the others (as
    mosaic starts, and after a change)."""
    base = [j for j in JOURNALS if not j.get("user") and not j.get("library")]
    names = {j["name"].lower() for j in base}
    mine = user_journals()
    names |= {j["name"].lower() for j in mine}
    fetched = [j for j in library_journals() if j["name"].lower() not in names]
    JOURNALS[:] = sorted(base + mine + fetched, key=lambda j: j["name"].lower())
    return JOURNALS


def save_user(journals: list[dict]) -> list[dict]:
    """Keep your own journals (each checked: a name not already listed, widths and a depth in
    millimetres; ValueError says what's wrong) and list them with the others."""
    kept = _shared.write_user(user_file(), journals)
    _shared.with_user(kept, into=JOURNALS)
    return kept


# The journal library (Size > Find a Journal…): journals people have shared, found by name, ISSN or
# alias, fetched the first time one is chosen and kept in the cache prose reads too ------------------

from ._labapp import journalfile as _files            # noqa: E402
from ._labapp import journallibrary as _library      # noqa: E402

FROM_LIBRARY = "From the library"


def library_cache() -> str | None:
    """The cache of fetched journals: the one mosaic and prose share, or "library" in MOSAIC_HOME
    when that's set (tests, and trying mosaic out)."""
    if os.environ.get("MOSAIC_HOME"):
        return os.path.join(os.environ["MOSAIC_HOME"], "library")
    return None   # (the shared library's own: beside the list of your own journals)


def library_journals() -> list[dict]:
    """The journals fetched from the library that mosaic doesn't have built in, as the journal list
    has them, with "library": True, their version and their badge ("verified"), under
    "From the library"."""
    builtin = {j["id"] for j in _files.builtin()}
    out = []
    for j in _library.fetched(library_cache()):
        if j["id"] in builtin:
            continue
        entry = _files.figure_entry(j)
        if not entry:
            continue
        entry.update({"publisher": FROM_LIBRARY, "library": True, "id": j["id"], "library_version": j.get("version", "1.0.0"),
                      "verified": (j.get("verified") or {}).get("status", "unverified")})
        out.append(entry)
    return out


def find(source: str, query: str, limit: int = 30) -> list[dict]:
    """Size > Find a Journal…: [{id, name, publisher, issn, aliases, badge, verified, where,
    on_this_computer, summary, listed: its name in the journal list once it's here, else None}]."""
    mine = []
    for e in user_journals():
        j = e.get("journal") if isinstance(e.get("journal"), dict) else None
        if j:
            mine.append({**j, "id": "my_" + j["id"]})
    got = _library.search(query, limit=limit, cache=library_cache(), source=source, mine=mine)
    listed = {j["name"] for j in JOURNALS}
    for g in got:
        g["listed"] = g["name"] if g["name"] in listed and g["kind"] == "journal" else None
    return got


def use_library_journal(source: str, ident: str) -> dict:
    """A journal from the library made ready (fetched the first time, from the shared cache after
    that) and listed: its entry in the journal list. OfflineError when it needs a connection the
    first time; ValueError when it has no figure sizes."""
    j = _library.fetch(ident, source=source, cache=library_cache())
    load_user()
    entry = next((x for x in JOURNALS if x.get("id") == ident or x["name"] == j["name"]), None)
    if entry is None:
        raise ValueError(f"{j['name']} gives no figure sizes, so mosaic can't size a page by it.")
    return entry


def p_styles() -> dict:
    """How each journal writes P values in its house style ("p": letter, italic, space round "<",
    zero before the point), by name: the built-in journals' and those fetched from the library.
    These are prose's house styles (house_style_from says "print" where they were read from the
    journal's published articles, "stated" where its guidelines say so); a significance bracket's
    quick-set p-values follow the page's journal by them. Journals without one aren't listed."""
    out = {}
    try:
        files = [*_files.builtin(), *_library.fetched(library_cache())]
    except (OSError, ValueError):
        files = _files.builtin()
    for j in files:
        p = (j.get("house_style") or {}).get("p")
        if isinstance(p, dict) and j.get("name"):
            out[j["name"]] = {**p, "from": (j.get("house_style_from") or {}).get("p")}
    return out


def share_user_journal(source: str, name: str, dry_run: bool = False) -> dict:
    """My Journals > Share…: one of your own offered to the library (a pull request on GitHub when you
    can't change the library yourself; else written in). {"name", "where", "pull_request"?}."""
    e = next((e for e in user_journals() if e["name"] == name), None)
    if e is None:
        raise ValueError("There's no such journal in your list.")
    j = e.get("journal") if isinstance(e.get("journal"), dict) else _files.from_legacy(e)
    return _library.share(source, j, app="mosaic", dry_run=dry_run,
                          checked=["the file passes mosaic's journal-file check", "a page was sized by it in mosaic"])

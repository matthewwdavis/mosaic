"""The journals both apps know: each one's figure sizes, the look of its panel labels, and its
rules for a figure's text, lines, pictures and files. mosaic sizes pages and checks figures by
them; prose sizes and relabels the figures of a manuscript by the same table.

JOURNALS is the list, sorted by name; each entry:

    name        "Nature"
    depth_mm    the deepest a figure may be
    types       [{"name": "Single column", "width_mm": 90.0}, ...]: the widths it takes
    any_width   True where a figure may be any width up to the widest type (the types are then
                handy presets, not the only widths: bioRxiv); absent for the rest
    max_width_mm  the widest a figure may be where that's more than the widest type (bioRxiv: 180 mm,
                which prose prints scaled to its 177.8 mm text width); absent for the rest
    note        the sizes in a sentence
    source      where the numbers come from
    labels, text, lines, pictures, export   its rules (RULES[name]); absent where it states none
    publisher   the group both apps list it under ("Springer Nature"; PUBLISHERS[name]): the journal
                lists are grouped by it, groups and the journals in each in alphabetical order, a
                person's own journals as "My journals"; bioRxiv's is "In house", beside prose's
                in-house templates

Where a journal publishes no figure sizes, the widths and depth were measured from a published
open-access article (PubMed Central, 2025-26): the width of a text column, the full text width,
and the depth of the text block. Measured widths are rounded to the nearest 0.5 mm and depths
down to the whole millimetre. Checked against PNAS's published sizes, the method gets the column
width within 0.2 mm; the full text width can be up to ~3 mm wider than a journal's stated
double-column figure width.

bioRxiv is no journal's layout but Matthew's choice for his lab's preprints (prose's "bioRxiv (in house)" template) (2026-11-16):
a figure may be any size within a US Letter page's text area (0.75 in margins: 7 x 9.5 in), with
one column of the lab's two-column template (3.375 in) and the full width as presets, and up to
180 mm wide (Nature's double column, which he has posted to bioRxiv before): prose prints one
wider than 7 in scaled to the text width. Its panel letters are lower case, as he has posted them.
bioRxiv itself sets no figure sizes or figure rules, so mosaic's own apply.

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

Every built-in journal is a journal file (builtin_journals/, journalfile.py); this table is made
from their "figures".

**A person's own journals** (user journals) sit beside these, kept in one JSON file that both apps
read (shared_user_file; read_user, write_user), so a journal added in either is in both. Since
2026-11-17 (the list's "format": 2) each entry is a whole journal file ("journal": everything a
built-in journal can have), with the keys older versions read beside it: a name, widths and a depth,
"user": True, an "id" that stays when the name changes, rules where given, and "manuscript" (prose's
My Journals form: page, reference style, sections), which mosaic hands back untouched. An entry from
an older version (the keys only) is made a journal file when it's read. with_user() puts them into a
list with the built-in ones.
"""
from __future__ import annotations

import json
import os
import re

MM = 72.0 / 25.4


from . import journalfile as _files   # noqa: E402

# The table, made from the built-in journal files (builtin_journals/: each journal's "figures"), sorted
# by name; RULES: each journal's rules by its name (the same dicts as in its entry)
JOURNALS = sorted([e for e in (_files.figure_entry(j) for j in _files.builtin() if (j.get("figures") or {}).get("listed", True)) if e],
                  key=lambda j: j["name"].lower())
RULES = {j["name"]: {k: j[k] for k in _files.RULE_KEYS if k in j} for j in JOURNALS}


# The group each journal is listed under in both apps' journal lists: its publisher, as prose's
# Journal menu has always grouped them (a society journal under the society that publishes it;
# bioRxiv, Matthew's own layout, "In house" with prose's in-house templates): each journal file's
# "group", else its "publisher" (journalfile.figure_entry)
PUBLISHERS = {j["name"]: j["publisher"] for j in JOURNALS}


BUILT_IN = [j["name"] for j in JOURNALS]


def widest(journal: dict) -> float:
    """The widest figure a journal takes, in mm: its max_width_mm, else its widest type."""
    return journal.get("max_width_mm") or max(t["width_mm"] for t in journal["types"])


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


def clean(entry: dict, kept: bool = False) -> dict:
    """A person's journal as it's kept: its journal file ("journal", journalfile.py) with the keys
    older versions read beside it ({"id", "name", "depth_mm", "types": [{"name", "width_mm"}], "note",
    "source", "user": True, rules, "manuscript": prose's form}). An entry with only the older keys
    is made a journal file; one with both takes what was changed through the older keys (an app's
    form) into its file. kept: an entry as read from the list, where the journal file is the truth
    (one edited by hand) and the keys beside it only a copy for older versions. Raises ValueError, in
    words for the person, when it can't be one."""
    if kept and isinstance(entry, dict) and isinstance(entry.get("journal"), dict) and entry["journal"].get("format"):
        entry = {"journal": entry["journal"]}
    legacy = _clean_legacy(entry)
    full = entry.get("journal") if isinstance(entry.get("journal"), dict) and entry["journal"].get("format") else None
    if full is None:
        j = _files.from_legacy(legacy)
    else:
        j = json.loads(json.dumps(full))
        shown = _files.legacy_view(j)
        j["name"] = legacy["name"]
        fig = j.setdefault("figures", {})
        for k in ("depth_mm", "types", "note", "source", *_files.RULE_KEYS):
            if k in legacy and legacy[k] != shown.get(k):
                fig[k] = legacy[k]
        if isinstance(legacy.get("manuscript"), dict) and legacy["manuscript"] != shown["manuscript"]:
            j = _files.apply_form(j, legacy["manuscript"], shown["manuscript"])
    j["id"] = legacy["id"]
    errors, _ = _files.validate(j)
    if errors:
        raise ValueError(f"{legacy['name']}: {errors[0]}.")
    return {**_files.legacy_view(j), "journal": j}


def _clean_legacy(entry: dict) -> dict:
    """The older keys of an entry, checked (as kept before journal files)."""
    if not isinstance(entry, dict):
        raise ValueError("A journal needs a name and its figure sizes.")
    if isinstance(entry.get("journal"), dict) and entry["journal"].get("format"):
        entry = {**_files.legacy_view(entry["journal"]), **{k: v for k, v in entry.items() if k != "journal"}}
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
            j = clean(entry, kept=True)
        except ValueError:
            continue
        if j["name"].lower() not in names and j["id"] not in ids:
            names.add(j["name"].lower())
            ids.add(j["id"])
            out.append(j)
    return sorted(out, key=lambda j: j["name"].lower())


FORMAT = 2   # the shared list's format: 2, each entry with its journal file ("journal"); 1 before


def write_user(path: str, journals: list[dict]) -> list[dict]:
    """Keep the person's own journals (each checked: clean); returns them as kept. An entry that
    comes back without its journal file (from an app that only shows the sizes and the form) keeps
    the file it had, with the changes made."""
    before = {e["id"]: e["journal"] for e in read_user(path)}
    kept, names, ids = [], set(), set()
    for entry in journals or []:
        if isinstance(entry, dict) and not isinstance(entry.get("journal"), dict) and entry.get("id") in before:
            entry = {**entry, "journal": before[entry["id"]]}
        j = clean(entry)
        if j["name"].lower() in names:
            raise ValueError(f"Two of your journals are called {j['name']}; give each its own name.")
        base, n = j["id"], 2
        while j["id"] in ids:   # (two names that come to the same id)
            j["id"] = f"{base[:37]}_{n}"
            n += 1
        j["journal"]["id"] = j["id"]
        names.add(j["name"].lower())
        ids.add(j["id"])
        kept.append(j)
    kept.sort(key=lambda j: j["name"].lower())
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"format": FORMAT, "journals": kept}, fh, indent=1, ensure_ascii=False)
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

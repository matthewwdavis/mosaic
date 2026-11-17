"""A journal library in a folder, for tests and the apps' self-tests: journal files and the index
the real library's tools make (format 2, with checksums), so fetching and searching can be tried
with no network.

    folder = fakelibrary.make(tmp / "library")                  # Tree Genetics & Genomes, Community
    folder = fakelibrary.make(tmp / "library", [journal, ...])  # these journal files
    fakelibrary.add(folder, journal)                             # one more, or a new version of one

Point an app at it with the folder's path or its file:// address.
"""
from __future__ import annotations

import copy
import json
import os

from . import journalfile, journallibrary

TREE_GENETICS = {
    "format": 1, "id": "tree_genetics_genomes", "name": "Tree Genetics & Genomes", "version": "1.0.0", "kind": "journal",
    "publisher": "Springer", "group": "Springer Nature", "issn": {"print": "1614-2942", "online": "1614-2950"},
    "aliases": ["Tree Genet Genomes"], "homepage": "https://link.springer.com/journal/11295",
    "verified": {"status": "community", "by": "a-contributor", "date": "2026-11-17"},
    "page": {"paper": "a4"}, "captions": {"label": "Fig.", "bar": False}, "references": {"csl": "springer-basic-author-date"},
    "figures": {"types": [{"name": "Single column", "width_mm": 84.0}, {"name": "Double column", "width_mm": 174.0}],
                "depth_mm": 234.0, "note": "84 or 174 mm wide, up to 234 mm deep (Springer's figure sizes)",
                "source": "Springer's artwork guidelines"},
    "sources": [{"url": "https://link.springer.com/journal/11295/submission-guidelines", "what": "Submission guidelines"}],
}


def add(folder: str, journal: dict) -> dict:
    """Put a journal file in the library and list it (replacing an earlier version); its index entry."""
    journalfile.check(journal, journal.get("id", ""))
    rel = f"journals/{journal['id']}.json"
    data = journalfile.dumps(journal).encode("utf-8")
    os.makedirs(os.path.join(folder, "journals"), exist_ok=True)
    with open(os.path.join(folder, *rel.split("/")), "wb") as fh:
        fh.write(data)
    try:
        with open(os.path.join(folder, "index.json"), encoding="utf-8") as fh:
            items = json.load(fh).get("journals", [])
    except (OSError, ValueError):
        items = []
    entry = journallibrary.index_entry(journal, rel, data, updated="2026-11-17")
    items = [e for e in items if e.get("id") != journal["id"]] + [entry]
    with open(os.path.join(folder, "index.json"), "wb") as fh:
        fh.write(journallibrary.write_index(items))
    return entry


def make(folder, journals: list[dict] | None = None) -> str:
    folder = str(folder)
    os.makedirs(folder, exist_ok=True)
    for j in journals if journals is not None else [copy.deepcopy(TREE_GENETICS)]:
        add(folder, j)
    return folder

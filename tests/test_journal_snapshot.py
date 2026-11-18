"""The journals moved from the shared library's hand-kept table into journal files (its
builtin_journals, 2026-11-17) without changing anything they make mosaic do: tests/journal_snapshot.py
takes the snapshot it took before the move (tests/data/journal_snapshot.json) and it
must match byte for byte (taken again at main 1ab8079, with journal-groups' publishers): the journal list, each journal's Check and Export check on a sample page,
and the sample relabelled for each. Only RULES's keys are in another order (the files' order):
nothing reads it in order.

The snapshot was taken on a Mac, and Check names the font text is drawn in ("“Axis”: text in
Helvetica; Cell accepts only Arial"). A computer without the sample's fonts draws it in another
(Liberation Sans on Linux), so there those findings say something else, and are left out of the
comparison; everything else is still compared."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))


SAMPLE_FONTS = ("Helvetica", "Arial", "Times New Roman")   # (the sample page's: journal_snapshot.sample)
FONT_FINDING = re.compile(r"^“[^”]*”: text in [^;]+; ")      # Check's "text in <font>; <journal> accepts only…"


def sample_fonts_here() -> bool:
    """Whether this computer has the sample's fonts, as the Mac the snapshot was taken on did."""
    sys.path.insert(0, ROOT)
    from mosaic.fonts import resolve_face
    return all(resolve_face(f)[0].ref.family == f for f in SAMPLE_FONTS)


def test_every_journal_does_exactly_what_it_did_before_the_journal_files():
    import journal_snapshot
    now = json.loads(json.dumps(journal_snapshot.snapshot()))
    before = json.load(open(journal_snapshot.OUT, encoding="utf-8"))
    for snap in (now, before):
        snap["RULES"] = dict(sorted(snap["RULES"].items()))
        if not sample_fonts_here():   # (the findings naming the font text is drawn in: this computer's, not the Mac's)
            snap["check"] = {k: [f for f in v if not FONT_FINDING.match(f[1])] for k, v in snap["check"].items()}
    assert json.dumps(now, ensure_ascii=False) == json.dumps(before, ensure_ascii=False)

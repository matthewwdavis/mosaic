"""The journals moved from the shared library's hand-kept table into journal files (its
builtin_journals, 2026-11-17) without changing anything they make mosaic do: tests/journal_snapshot.py
takes the snapshot it took before the move (tests/data/journal_snapshot.json) and it
must match byte for byte (taken again at main 1ab8079, with journal-groups' publishers): the journal list, each journal's Check and Export check on a sample page,
and the sample relabelled for each. Only RULES's keys are in another order (the files' order):
nothing reads it in order."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))


def test_every_journal_does_exactly_what_it_did_before_the_journal_files():
    import journal_snapshot
    now = json.loads(json.dumps(journal_snapshot.snapshot()))
    before = json.load(open(journal_snapshot.OUT, encoding="utf-8"))
    for snap in (now, before):
        snap["RULES"] = dict(sorted(snap["RULES"].items()))
    assert json.dumps(now, ensure_ascii=False) == json.dumps(before, ensure_ascii=False)

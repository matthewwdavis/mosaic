"""What every journal makes mosaic do, as one JSON snapshot: the journal list (sizes, label looks,
figure rules), each journal's Check findings on a sample page, and the sample relabelled for each.

Taken before the journals moved into journal files (the shared library's builtin_journals,
2026-11-17) and kept as tests/data/journal_snapshot.json; tests/test_journal_snapshot.py makes it
again and compares, so the files give exactly what the hand-kept table gave.

    python tests/journal_snapshot.py --write      # take it again (after a deliberate change)
    python tests/journal_snapshot.py --compare    # say what differs
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "data", "journal_snapshot.json")


def _text(model, ident, text, x, y, size, font="Helvetica", bold=False, **kw):
    it = model.text_item(text, x, y, size=size, bold=bold, font=font)
    it["id"] = ident
    it.update(kw)
    return it


def sample(model, MM, journal: dict, width_mm: float, depth_mm: float) -> dict:
    """A page of a journal's size: two panel labels (one by the Label tool), small and large text,
    a thin and a thick line."""
    doc = model.new_document("sample")
    page = doc["pages"][0]
    page["width"], page["height"] = width_mm * MM, depth_mm * MM
    page["preset"] = {"journal": journal["name"], "type": journal["types"][0]["name"]}
    page["items"] = [
        _text(model, "la", "a", 10, 10, 8.0, bold=True),
        _text(model, "lb", "B", 120, 10, 12.0, font="Arial", panel_label=True),
        _text(model, "small", "Axis", 20, 60, 4.5),
        _text(model, "big", "Title", 20, 90, 14.0, font="Times New Roman"),
        {"id": "thin", "type": "line", "name": "Line", "points": [[20, 130], [120, 130]], "arrow_start": None, "arrow_end": None,
         "stroke": {"color": "#000000", "width": 0.1}},
        {"id": "thick", "type": "line", "name": "Line", "points": [[20, 150], [120, 150]], "arrow_start": None, "arrow_end": None,
         "stroke": {"color": "#000000", "width": 2.0}},
    ]
    return doc


def snapshot() -> dict:
    os.environ.setdefault("MOSAIC_HOME", tempfile.mkdtemp(prefix="mosaic-journal-snapshot-"))
    sys.path.insert(0, ROOT)
    from mosaic import journals, model, relabel
    from mosaic._labapp import journals as shared
    from mosaic.export.preflight import export_check, preflight
    MM = journals.MM
    out = {"JOURNALS": copy.deepcopy(journals.JOURNALS), "RULES": shared.RULES, "BUILT_IN": shared.BUILT_IN,
           "STANDARD_SIZES": journals.STANDARD_SIZES, "check": {}, "export_check": {}, "relabel": {}, "fit": {}}
    for j in list(journals.JOURNALS):
        name = j["name"]
        widest = shared.widest(j)
        for w, d in ((j["types"][0]["width_mm"], j["depth_mm"]), (widest + 5, j["depth_mm"] + 5), (j["types"][0]["width_mm"] + 3, 50)):
            out["fit"].setdefault(name, []).append(shared.size_fit(j, w, d))
        doc = sample(model, MM, j, j["types"][0]["width_mm"], min(j["depth_mm"], 120))
        res = preflight(doc, {"pages": [0]})
        out["check"][name] = [[f.get("level"), f.get("message")] for f in res["items"]]
        out["export_check"][name] = {fmt: export_check(doc, {"pages": [0], "formats": [fmt], "dpi": 300}) for fmt in ("pdf", "tiff", "svg")}
        other = sample(model, MM, journals.JOURNALS[0], 180.0, 120.0)
        counts = relabel.relabel(other, relabel.find_journal(name))
        out["relabel"][name] = {"counts": counts, "preset": other["pages"][0]["preset"],
                                "labels": [[r for p in it["text"]["paragraphs"] for r in p["runs"]] for it in other["pages"][0]["items"]
                                           if it["id"] in ("la", "lb")]}
    return json.loads(json.dumps(out))


def main() -> int:
    got = snapshot()
    text = json.dumps(got, indent=1, ensure_ascii=False) + "\n"
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {OUT} ({len(text) // 1024} KB)")
        return 0
    with open(OUT, encoding="utf-8") as fh:
        before = fh.read()
    if before == text:
        print("identical: byte for byte")
        return 0
    a = json.loads(before)
    for k in a:
        if a[k] != got.get(k):
            print(f"{k}: differs")
        elif json.dumps(a[k]) != json.dumps(got.get(k)):
            print(f"{k}: the same, in another order")
    return 1


if __name__ == "__main__":
    sys.exit(main())

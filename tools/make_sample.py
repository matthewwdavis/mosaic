"""Makes the sample figure mosaic opens the first time it runs (mosaic/data/sample.mosaic,
also Help > Open the Sample Figure): the four demo plots (demo/Figures/demo, from R's built-in
data) as panels a-d with their labels and a description, their files stored in the document.

    python tools/make_sample.py        # after re-running demo/demo_plots.R
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIGURES = os.path.join(ROOT, "demo", "Figures", "demo")
OUT = os.path.join(ROOT, "mosaic", "data", "sample.mosaic")
PANELS = [("iris_petal_scatter", "a"), ("tooth_length_bars", "b"), ("plant_weight_box", "c"), ("chick_weight_time_course", "d")]
MARGIN, GAP, LABEL = 14.0, 16.0, 9.0   # pt: round the page, between panels, a label's room above its plot
ALT = ("Four panels from R's built-in data. a, iris petal length against width by species. b, tooth length by "
       "supplement and dose. c, plant weight under a control and two treatments. d, chick weight over time on four diets.")


def build() -> dict:
    from mosaic import model
    from mosaic.assets import AssetCache, new_asset
    cache = AssetCache(os.path.join(tempfile.mkdtemp(prefix="mosaic-sample-"), "cache"))
    doc = model.new_document("Sample figure")
    page = doc["pages"][0]
    page["name"], page["alt"], page["background"] = "Figure 1", ALT, None
    page.pop("preset", None)
    placed = []
    for stem, _ in PANELS:
        aid, asset, warnings = new_asset(os.path.join(FIGURES, stem + ".pdf"), cache, link=False)
        if warnings:
            raise SystemExit(f"{stem}: {warnings}")
        asset["name"] = stem + ".pdf"
        doc["assets"][aid] = asset
        placed.append((aid, asset))
    # Two rows of two, each row as tall as its taller plot, each column as wide as its wider one
    w = [max(placed[i][1]["size_pt"][0] for i in col) for col in ((0, 2), (1, 3))]
    h = [max(placed[i][1]["size_pt"][1] for i in row) for row in ((0, 1), (2, 3))]
    for k, ((aid, asset), (_, letter)) in enumerate(zip(placed, PANELS)):
        col, row = k % 2, k // 2
        x = MARGIN + col * (w[0] + GAP)
        y = MARGIN + LABEL + row * (h[0] + GAP + LABEL)
        item = model.picture_item(aid, asset, x, y)
        item["name"] = f"Panel {letter}"
        label = model.text_item(letter, x, y - LABEL - 1, size=8.0, bold=True)
        label["name"] = f"Label {letter}"
        page["items"] += [item, label]
    page["width"] = 2 * MARGIN + w[0] + GAP + w[1]
    page["height"] = 2 * MARGIN + 2 * LABEL + h[0] + GAP + h[1]
    return doc, cache


if __name__ == "__main__":
    from mosaic import docfile
    doc, cache = build()
    warnings = docfile.save(doc, OUT, cache)
    if warnings:
        raise SystemExit(warnings)
    print(OUT, os.path.getsize(OUT), "bytes;", len(doc["assets"]), "plots;",
          f"{doc['pages'][0]['width']:.1f} x {doc['pages'][0]['height']:.1f} pt")

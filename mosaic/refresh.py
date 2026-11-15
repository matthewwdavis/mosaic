"""A document's linked pictures read again from their files, without the app: what Refresh All
Pictures (⌘⇧R) does in the editor, for `mosaic build` (cli.py) and scripts.

Every linked file is re-read whatever its date says, and copies of a plot saved beside it since
it was placed (the same name in another format, the same size) are taken in. A picture whose
file changed size keeps its place and its scale, as in the editor.
"""
from __future__ import annotations

import copy

from .assets import AssetCache, get_cache, refresh_asset, resolve_link
from .model import iter_items


def refresh_document(doc: dict, doc_dir: str | None = None, cache: AssetCache | None = None) -> dict:
    """Refresh doc's linked pictures in place. Returns {"changed": [names of pictures whose
    files had changed], "missing": [names whose files weren't found], "linked": how many are
    linked at all, "warnings": [...]}."""
    from .plottext import lifted
    cache = cache or get_cache()
    changed, missing, warnings, linked = [], [], [], 0
    for aid, asset in doc.get("assets", {}).items():
        variants = asset.get("variants", {})
        if not any(v.get("src") for v in variants.values()):
            continue   # (stored in the document only)
        linked += 1
        name = asset.get("name") or aid
        prim = variants.get(asset.get("primary")) or next(iter(variants.values()))
        if not resolve_link(prim, doc_dir):
            missing.append(name)
            continue
        before = copy.deepcopy(asset)
        try:
            kinds = refresh_asset(asset, cache, doc_dir, force=True)
        except Exception as exc:   # noqa: BLE001 (an unreadable file: the picture stays as it was)
            asset.clear()
            asset.update(before)
            warnings.append(f"{name}: couldn't be read again ({exc}); kept as it was")
            continue
        if not kinds:
            continue
        changed.append(name)
        (ow, oh), (nw, nh) = before["size_pt"], asset["size_pt"]
        for page in doc.get("pages", []):
            for it in iter_items(page.get("items", [])):
                if it.get("type") != "picture" or it.get("asset") != aid:
                    continue
                if (ow, oh) != (nw, nh) and ow and oh:   # its place and scale kept
                    f = it["frame"]
                    it["frame"] = [f[0], f[1], f[2] * nw / ow, f[3] * nh / oh]
                if lifted(it):
                    warnings.append(f"{name}: has texts lifted out in dangerous mode and its file changed; "
                                    "open the figure in mosaic to check them")
    return {"changed": changed, "missing": missing, "linked": linked, "warnings": warnings}

"""The .figasm document file: a zip of document.json plus a copy of every placed file.

document.json is stored uncompressed so `unzip -p figure.figasm document.json` shows it.
Embedded copies live under assets/<sha256><ext>; linked variants also record where their
file was (absolute, and relative to the document) so they can refresh on another machine
that has the same project folder.
"""
from __future__ import annotations

import json
import os
import time
import uuid
import zipfile

from . import __version__
from .assets import KIND_EXT, AssetCache, get_cache, resolve_link
from .model import FORMAT_VERSION, used_assets, validate

DOC_NAME = "document.json"
EXTENSION = ".figasm"


def save(doc: dict, path: str, cache: AssetCache | None = None, prune: bool = True) -> list[str]:
    """Write a document (atomically). Returns warnings about assets that couldn't be embedded."""
    cache = cache or get_cache()
    path = os.path.abspath(path)
    doc_dir = os.path.dirname(path)
    warnings: list[str] = []
    doc = json.loads(json.dumps(doc))   # never mutate the caller's copy
    doc["meta"]["modified"] = time.time()
    doc["meta"]["saved_by"] = __version__   # a newer FigAssemble's document warns when opened in an older one
    if prune:
        keep = used_assets(doc)
        doc["assets"] = {k: v for k, v in doc.get("assets", {}).items() if k in keep}
    files: dict[str, str] = {}
    for asset in doc["assets"].values():
        for kind, var in asset.get("variants", {}).items():
            if var.get("src"):
                try:
                    var["src_rel"] = os.path.relpath(var["src"], doc_dir)
                except ValueError:      # different drive on Windows
                    var.pop("src_rel", None)
            name = f"assets/{var['sha256']}{KIND_EXT.get(kind, '.' + kind)}"
            src = cache.path(var["sha256"], kind)
            if not os.path.exists(src):
                linked = resolve_link(var, doc_dir)
                if linked:
                    cache.put_file(linked, kind)
                else:
                    warnings.append(f"{asset.get('name')}: no copy of the {kind} file to embed")
                    continue
            files[name] = src
    tmp = path + f".{uuid.uuid4().hex[:6]}.tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo(DOC_NAME, date_time=time.localtime()[:6]),
                   json.dumps(doc, indent=1, ensure_ascii=False), compress_type=zipfile.ZIP_STORED)
        for name, src in sorted(files.items()):
            # SVG is text and shrinks a lot; PDF/PNG/JPEG are already compressed
            ctype = zipfile.ZIP_DEFLATED if name.endswith(".svg") else zipfile.ZIP_STORED
            z.write(src, name, compress_type=ctype)
    os.replace(tmp, path)
    return warnings


def load(path: str, cache: AssetCache | None = None) -> dict:
    """Read a document and make sure every embedded copy is in the cache."""
    cache = cache or get_cache()
    with zipfile.ZipFile(path) as z:
        doc = json.loads(z.read(DOC_NAME).decode("utf-8"))
        names = set(z.namelist())
        for asset in doc.get("assets", {}).values():
            for kind, var in asset.get("variants", {}).items():
                if cache.has(var["sha256"], kind):
                    continue
                name = f"assets/{var['sha256']}{KIND_EXT.get(kind, '.' + kind)}"
                if name in names:
                    cache.put_bytes(z.read(name), kind)
    fmt = doc.get("figassemble")
    if isinstance(fmt, int) and fmt > FORMAT_VERSION:
        by = (doc.get("meta") or {}).get("saved_by")
        raise ValueError(f"{os.path.basename(path)} was saved by a newer FigAssemble{f' ({by})' if by else ''}, "
                         f"in a form this one ({__version__}) can't read. Update FigAssemble to open it.")
    problems = validate(doc)
    if any("version" in p for p in problems):
        raise ValueError("; ".join(problems))
    return doc


def is_document(path: str) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as z:
        return DOC_NAME in z.namelist()


__all__ = ["save", "load", "is_document", "EXTENSION", "FORMAT_VERSION"]

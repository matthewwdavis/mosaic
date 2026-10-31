"""Placed files: probing, sibling variants, the content-addressed cache and export source choice.

An asset is one placed figure. It can have several *variants*: the same plot saved as PDF,
SVG and PNG under one name (R's ggsave habit). Each variant is copied into a cache keyed by
its SHA-256, so documents can embed it, and it remembers the file it came from so it can
refresh when that file changes.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

from lxml import etree

from .fonts import config_dir

EXT_KIND = {".pdf": "pdf", ".svg": "svg", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg",
            ".tif": "tiff", ".tiff": "tiff"}
KIND_EXT = {"pdf": ".pdf", "svg": ".svg", "png": ".png", "jpeg": ".jpg", "tiff": ".tif"}
RASTER_KINDS = ("png", "jpeg", "tiff")
VECTOR_KINDS = ("pdf", "svg")
DEFAULT_RASTER_DPI = 300.0   # used when an image file doesn't record its resolution
SIZE_TOLERANCE = 0.05        # points: siblings must agree on size this closely

# SVG length units in points
_UNIT_PT = {"pt": 1.0, "px": 0.75, "in": 72.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "pc": 12.0, "": 0.75}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def kind_of(path: str) -> str | None:
    return EXT_KIND.get(os.path.splitext(path)[1].lower())


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tool_path(name: str) -> str | None:
    """Find a helper executable on PATH or inside the running environment."""
    found = shutil.which(name)
    if found:
        return found
    for sub in ("bin", os.path.join("Library", "bin"), "Scripts"):
        cand = os.path.join(sys.prefix, sub, name + (".exe" if os.name == "nt" else ""))
        if os.path.exists(cand):
            return cand
    return None


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

def _svg_length(value: str | None) -> float | None:
    if not value:
        return None
    m = re.fullmatch(r"\s*([0-9.eE+-]+)\s*([a-z%]*)\s*", value)
    if not m or m.group(2) == "%":
        return None
    return float(m.group(1)) * _UNIT_PT.get(m.group(2), 0.75)


def svg_geometry(root) -> dict:
    """Size of an SVG in points and how its user units map onto that size."""
    vb = root.get("viewBox")
    vbox = [float(v) for v in re.split(r"[\s,]+", vb.strip())] if vb else None
    w = _svg_length(root.get("width"))
    h = _svg_length(root.get("height"))
    if vbox and len(vbox) == 4:
        if w is None and h is None:
            w, h = vbox[2] * 0.75, vbox[3] * 0.75
        elif w is None:
            w = h * vbox[2] / vbox[3]
        elif h is None:
            h = w * vbox[3] / vbox[2]
    if w is None or h is None:
        w, h = w or 300.0, h or 150.0
    if not vbox or len(vbox) != 4:
        # Without a viewBox, one user unit is one CSS pixel whatever unit the size uses
        vbox = [0.0, 0.0, w / 0.75, h / 0.75]
    return {"size_pt": [w, h], "viewbox": vbox, "par": root.get("preserveAspectRatio", "xMidYMid meet")}


def probe(path: str, kind: str | None = None) -> dict:
    kind = kind or kind_of(path)
    info: dict = {"kind": kind}
    if kind == "pdf":
        import pikepdf
        with pikepdf.open(path) as pdf:
            sizes = []
            for page in pdf.pages:
                x0, y0, x1, y1 = (float(v) for v in display_box(page))
                uu = float(page.obj.get("/UserUnit", 1.0))
                w, h = (x1 - x0) * uu, (y1 - y0) * uu
                if int(page.obj.get("/Rotate", 0)) % 180:
                    w, h = h, w
                sizes.append([w, h])
            info["page_sizes"] = sizes
            info["size_pt"] = sizes[0] if sizes else [100.0, 100.0]
            info["pages"] = len(sizes)
    elif kind == "svg":
        root = etree.parse(path, etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)).getroot()
        info.update(svg_geometry(root))
    elif kind in RASTER_KINDS:
        from PIL import Image
        with Image.open(path) as im:
            px = im.size
            dpi = im.info.get("dpi")
            cal = image_calibration(im)
            # ImageJ keeps pixels per micron (or per mm…) in the resolution tags: not a print size
            if cal and cal["from"] == "ImageJ":
                dpi = None
            if not dpi or not dpi[0] or float(dpi[0]) < 2:
                dpi = (DEFAULT_RASTER_DPI, DEFAULT_RASTER_DPI)
                info["dpi_assumed"] = True
            # PNG stores pixels per metre, so 600 dpi reads back as 599.9988: snap to the whole number
            dpi = tuple(round(float(v)) if abs(float(v) - round(float(v))) < 0.013 else float(v)
                        for v in (dpi[0], dpi[1] or dpi[0]))
            info["px"] = list(px)
            info["dpi"] = list(dpi)
            info["mode"] = im.mode
            if cal:
                info["calibration"] = cal
            info["size_pt"] = [px[0] / dpi[0] * 72.0, px[1] / dpi[1] * 72.0]
    else:
        raise ValueError(f"unsupported file type: {path}")
    return info


# Length units a calibration may name, as FigAssemble writes them
LENGTH_UNITS = {"nm": "nm", "nanometer": "nm", "nanometers": "nm", "µm": "µm", "um": "µm", "micron": "µm", "microns": "µm",
                "micrometer": "µm", "micrometers": "µm", "\\u00b5m": "µm", "mm": "mm", "millimeter": "mm", "cm": "cm",
                "centimeter": "cm", "m": "m", "meter": "m"}


def image_calibration(im) -> dict | None:
    """The real size of a pixel as microscopes and ImageJ/Fiji save it in a TIFF: OME-XML's
    PhysicalSizeX, or ImageJ's unit with the resolution as pixels per unit. A plain TIFF's
    resolution is the print resolution, not a measurement, so it isn't used."""
    tags = getattr(im, "tag_v2", None)
    if not tags:
        return None
    desc = tags.get(270) or ""
    if isinstance(desc, bytes):
        desc = desc.decode("utf-8", "replace")
    size = re.search(r'PhysicalSizeX="([0-9.eE+-]+)"', desc)
    if size:
        unit = re.search(r'PhysicalSizeXUnit="([^"]+)"', desc)
        u = LENGTH_UNITS.get((unit.group(1) if unit else "µm").strip().lower())
        if u and float(size.group(1)) > 0:
            return {"per_px": float(size.group(1)), "unit": u, "from": "OME-TIFF"}
    if desc.startswith("ImageJ="):
        unit = re.search(r"^unit=(.+)$", desc, re.M)
        u = LENGTH_UNITS.get(unit.group(1).strip().lower()) if unit else None
        res = tags.get(282)
        if u and res and float(res) > 0:
            return {"per_px": 1.0 / float(res), "unit": u, "from": "ImageJ"}
    return None


def display_box(page):
    """The box a viewer shows: CropBox clipped to MediaBox."""
    mb = [float(v) for v in page.obj.get("/MediaBox", [0, 0, 612, 792])]
    cb = page.obj.get("/CropBox")
    if cb is None:
        return mb
    cb = [float(v) for v in cb]
    x0, y0 = max(min(mb[0], mb[2]), min(cb[0], cb[2])), max(min(mb[1], mb[3]), min(cb[1], cb[3]))
    x1, y1 = min(max(mb[0], mb[2]), max(cb[0], cb[2])), min(max(mb[1], mb[3]), max(cb[1], cb[3]))
    return [x0, y0, x1, y1] if x1 > x0 and y1 > y0 else mb


def siblings(path: str) -> dict[str, str]:
    """Other formats of the same figure: same folder, same file name, different extension."""
    folder, name = os.path.split(os.path.abspath(path))
    stem = os.path.splitext(name)[0]
    out = {}
    try:
        entries = os.listdir(folder)
    except OSError:
        return {kind_of(path): os.path.abspath(path)}
    for entry in entries:
        s, ext = os.path.splitext(entry)
        k = EXT_KIND.get(ext.lower())
        if s == stem and k and k not in out:
            out[k] = os.path.join(folder, entry)
    out[kind_of(path)] = os.path.abspath(path)
    return out


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class AssetCache:
    """Content-addressed copies of placed files and of conversions made from them."""

    def __init__(self, root: str | None = None):
        self.root = root or os.path.join(config_dir(), "cache")
        os.makedirs(self.root, exist_ok=True)

    def path(self, sha: str, kind: str) -> str:
        return os.path.join(self.root, sha[:2], sha + KIND_EXT.get(kind, "." + kind))

    def has(self, sha: str, kind: str) -> bool:
        return os.path.exists(self.path(sha, kind))

    def put_file(self, src: str, kind: str | None = None) -> tuple[str, str]:
        kind = kind or kind_of(src)
        sha = sha256_file(src)
        dst = self.path(sha, kind)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + f".{uuid.uuid4().hex[:6]}.tmp"
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
        return sha, dst

    def put_bytes(self, data: bytes, kind: str) -> tuple[str, str]:
        sha = hashlib.sha256(data).hexdigest()
        dst = self.path(sha, kind)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + f".{uuid.uuid4().hex[:6]}.tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dst)
        return sha, dst

    def derived(self, key: str, ext: str) -> str:
        """Path for a file derived from cached content (conversions, previews)."""
        d = os.path.join(self.root, "derived", key[:2])
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, key + ext)


_cache: AssetCache | None = None


def get_cache() -> AssetCache:
    global _cache
    if _cache is None:
        _cache = AssetCache()
    return _cache


# ---------------------------------------------------------------------------
# Assets in a document
# ---------------------------------------------------------------------------

def make_variant(path: str, cache: AssetCache, link: bool = True) -> dict:
    kind = kind_of(path)
    sha, _ = cache.put_file(path, kind)
    st = os.stat(path)
    var = {"sha256": sha, "kind": kind, "bytes": st.st_size}
    var.update({k: v for k, v in probe(path, kind).items() if k != "kind"})
    if link:
        var["src"] = os.path.abspath(path)
        var["mtime"] = st.st_mtime
    return var


def new_asset(path: str, cache: AssetCache | None = None, link: bool = True,
              use_siblings: bool = True) -> tuple[str, dict, list[str]]:
    """Register a dropped file. Returns (asset id, asset record, warnings)."""
    cache = cache or get_cache()
    path = os.path.abspath(path)
    primary = kind_of(path)
    if primary is None:
        raise ValueError(f"unsupported file type: {os.path.basename(path)}")
    warnings: list[str] = []
    found = siblings(path) if use_siblings else {primary: path}
    variants = {primary: make_variant(path, cache, link)}
    ref = variants[primary]["size_pt"]
    for kind, p in found.items():
        if kind == primary or kind not in VECTOR_KINDS + ("png",):
            continue
        if kind in RASTER_KINDS and primary in VECTOR_KINDS:
            continue   # a vector plot exports from its vector copies; its PNG isn't needed
        try:
            var = make_variant(p, cache, link)
        except Exception as exc:   # an unreadable sibling shouldn't block the drop
            warnings.append(f"skipped {os.path.basename(p)}: {exc}")
            continue
        if abs(var["size_pt"][0] - ref[0]) > SIZE_TOLERANCE or abs(var["size_pt"][1] - ref[1]) > SIZE_TOLERANCE:
            warnings.append(f"{os.path.basename(p)} is {var['size_pt'][0]:.2f} x {var['size_pt'][1]:.2f} pt, "
                            f"not {ref[0]:.2f} x {ref[1]:.2f} pt like {os.path.basename(path)}; not used")
            continue
        variants[kind] = var
    asset = {
        "name": os.path.basename(path),
        "primary": primary,
        "size_pt": list(ref),
        "variants": variants,
        "auto_update": bool(link),
        "added": time.time(),
    }
    if "page_sizes" in variants[primary]:
        asset["page_sizes"] = variants[primary]["page_sizes"]
    return new_id("as"), asset, warnings


def new_asset_from_bytes(data: bytes, name: str, cache: AssetCache | None = None) -> tuple[str, dict]:
    """Register embedded content that has no file on disk (pasted or uploaded)."""
    cache = cache or get_cache()
    kind = kind_of(name) or "png"
    sha, path = cache.put_bytes(data, kind)
    var = {"sha256": sha, "kind": kind, "bytes": len(data)}
    var.update({k: v for k, v in probe(path, kind).items() if k != "kind"})
    asset = {"name": name, "primary": kind, "size_pt": list(var["size_pt"]), "variants": {kind: var},
             "auto_update": False, "added": time.time()}
    if "page_sizes" in var:
        asset["page_sizes"] = var["page_sizes"]
    return new_id("as"), asset


def resolve_link(var: dict, doc_dir: str | None) -> str | None:
    """Where a variant's source file is now: its absolute path, else relative to the document."""
    src = var.get("src")
    if src and os.path.exists(src):
        return src
    rel = var.get("src_rel")
    if rel and doc_dir:
        cand = os.path.normpath(os.path.join(doc_dir, rel))
        if os.path.exists(cand):
            return cand
    return None


def refresh_asset(asset: dict, cache: AssetCache, doc_dir: str | None = None) -> list[str]:
    """Re-read linked variants whose files changed. Returns the kinds that changed."""
    changed = []
    if not asset.get("auto_update"):
        return changed
    for kind, var in list(asset["variants"].items()):
        src = resolve_link(var, doc_dir)
        if not src:
            continue
        try:
            st = os.stat(src)
        except OSError:
            continue
        if var.get("mtime") == st.st_mtime and var.get("bytes") == st.st_size:
            continue
        new = make_variant(src, cache, link=True)
        if new["sha256"] != var["sha256"]:
            asset["variants"][kind] = new
            changed.append(kind)
        else:
            var["mtime"], var["bytes"] = st.st_mtime, st.st_size
    if changed:
        prim = asset["variants"][asset["primary"]]
        asset["size_pt"] = list(prim["size_pt"])
        if "page_sizes" in prim:
            asset["page_sizes"] = prim["page_sizes"]
    return changed


# ---------------------------------------------------------------------------
# Export sources
# ---------------------------------------------------------------------------

class SourceResolver:
    """Picks the stored variant that feeds each export format, converting only when forced."""

    def __init__(self, doc: dict, cache: AssetCache | None = None, doc_dir: str | None = None):
        self.doc = doc
        self.cache = cache or get_cache()
        self.doc_dir = doc_dir
        self.notes: list[str] = []

    def asset(self, asset_id: str) -> dict:
        return self.doc["assets"][asset_id]

    def file(self, asset_id: str, kind: str) -> str:
        """Path to the bytes of a stored variant (cache copy, else the linked file if unchanged)."""
        var = self.asset(asset_id)["variants"][kind]
        p = self.cache.path(var["sha256"], kind)
        if os.path.exists(p):
            return p
        src = resolve_link(var, self.doc_dir)
        if src and sha256_file(src) == var["sha256"]:
            return src
        raise FileNotFoundError(f"missing data for {self.asset(asset_id).get('name', asset_id)} ({kind})")

    def _pick(self, asset_id: str, prefer: tuple[str, ...], override: str) -> str:
        variants = self.asset(asset_id)["variants"]
        if override and override != "auto" and override in variants:
            return override
        for k in prefer:
            if k in variants:
                return k
        return next(iter(variants))

    def for_pdf(self, asset_id: str, override: str = "auto") -> tuple[str, str]:
        """(kind, path) of what to embed in a PDF: a PDF page or a raster image."""
        kind = self._pick(asset_id, ("pdf", "svg", "png", "tiff", "jpeg"), override)
        path = self.file(asset_id, kind)
        if kind == "svg":
            name = self.asset(asset_id).get("name", asset_id)
            self.notes.append(f"{name}: converted SVG to PDF (no PDF copy found)")
            return "pdf", self.svg_to_pdf(path, self.asset(asset_id)["variants"]["svg"]["sha256"])
        return kind, path

    def for_svg(self, asset_id: str, override: str = "auto") -> tuple[str, str]:
        """(kind, path) of what to place in an SVG: SVG markup or a raster image."""
        kind = self._pick(asset_id, ("svg", "pdf", "png", "tiff", "jpeg"), override)
        path = self.file(asset_id, kind)
        if kind == "pdf":
            name = self.asset(asset_id).get("name", asset_id)
            self.notes.append(f"{name}: converted PDF to SVG (no SVG copy found)")
            return "svg", self.pdf_to_svg(path, self.asset(asset_id)["variants"]["pdf"]["sha256"])
        return kind, path

    def svg_to_pdf(self, svg_path: str, sha: str) -> str:
        out = self.cache.derived(sha + ".rsvg", ".pdf")
        if not os.path.exists(out):
            exe = tool_path("rsvg-convert")
            if not exe:
                raise RuntimeError("rsvg-convert (librsvg) is needed to convert SVG to PDF")
            subprocess.run([exe, "-f", "pdf", "-o", out + ".tmp", svg_path], check=True, capture_output=True)
            os.replace(out + ".tmp", out)
        return out

    def pdf_to_svg(self, pdf_path: str, sha: str, page: int = 0) -> str:
        out = self.cache.derived(f"{sha}.p{page}.cairo", ".svg")
        if not os.path.exists(out):
            exe = tool_path("pdftocairo")
            if not exe:
                raise RuntimeError("pdftocairo (poppler) is needed to convert PDF to SVG")
            subprocess.run([exe, "-svg", "-f", str(page + 1), "-l", str(page + 1), pdf_path, out + ".tmp"],
                           check=True, capture_output=True)
            os.replace(out + ".tmp", out)
        return out

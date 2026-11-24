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
import threading
import time
import uuid

from lxml import etree

from .fonts import config_dir
from .geometry import Matrix

EXT_KIND = {".pdf": "pdf", ".svg": "svg", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg",
            ".tif": "tiff", ".tiff": "tiff"}
KIND_EXT = {"pdf": ".pdf", "svg": ".svg", "png": ".png", "jpeg": ".jpg", "tiff": ".tif"}
RASTER_KINDS = ("png", "jpeg", "tiff")
VECTOR_KINDS = ("pdf", "svg")
DEFAULT_RASTER_DPI = 300.0   # used when an image file doesn't record its resolution
DERIVED_DAYS = 30            # days an unused preview or conversion stays in the cache
SIZE_TOLERANCE = 0.05        # points: siblings must agree on size this closely
STABLE_TRIES = 5             # copies of a linked file taken while it's still changing, before the last is kept
STABLE_WAIT = 0.1            # s between them

# SVG length units in points
# PDFium can't be used from two threads at once (the editor's previews are drawn on the server's
# threads while the engine reads plots on another): every use of it holds this
PDFIUM_LOCK = threading.RLock()

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
    from ._labapp.platform import tool
    return tool(name, path_first=True)


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


def svg_user_matrix(geo: dict) -> Matrix:
    """An SVG's user units -> its source points (svg_geometry's size), honouring preserveAspectRatio."""
    (sw, sh), (vx, vy, vw, vh) = geo["size_pt"], geo["viewbox"]
    sx, sy = sw / vw, sh / vh
    ox = oy = 0.0
    par = (geo["par"] or "xMidYMid meet").split()
    if par[0] != "none":
        s = min(sx, sy) if (len(par) < 2 or par[1] == "meet") else max(sx, sy)
        align = par[0]
        ox = {"xMin": 0.0, "xMid": 0.5, "xMax": 1.0}.get(align[:4], 0.5) * (sw - vw * s)
        oy = {"YMin": 0.0, "YMid": 0.5, "YMax": 1.0}.get(align[4:], 0.5) * (sh - vh * s)
        sx = sy = s
    return Matrix(sx, 0.0, 0.0, sy, ox - vx * sx, oy - vy * sy)


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


# Length units a calibration may name, as mosaic writes them
LENGTH_UNITS = {"nm": "nm", "nanometer": "nm", "nanometers": "nm", "µm": "µm", "um": "µm", "micron": "µm", "microns": "µm",
                "micrometer": "µm", "micrometers": "µm", "\\u00b5m": "µm", "mm": "mm", "millimeter": "mm", "cm": "cm",
                "centimeter": "cm", "m": "m", "meter": "m",
                # (imperial, 2026-11-19: ImageJ's "inch", OME's "in", "ft", "yd", "mi")
                "in": "in", "inch": "in", "inches": "in", "ft": "ft", "foot": "ft", "feet": "ft", "yd": "yd", "yard": "yd",
                "yards": "yd", "mi": "mi", "mile": "mi", "miles": "mi"}


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

_SHA_RE = re.compile(r"[0-9a-f]{64}")
_KIND_RE = re.compile(r"[a-z0-9]{1,8}")


class AssetCache:
    """Content-addressed copies of placed files and of conversions made from them."""

    def __init__(self, root: str | None = None):
        self.root = root or os.path.join(config_dir(), "cache")
        os.makedirs(self.root, exist_ok=True)

    def path(self, sha: str, kind: str) -> str:
        # Both come from the document file when one is opened: anything but a SHA-256 and a
        # plain file kind could name a path outside the cache (written on open, embedded on save)
        if not (isinstance(sha, str) and _SHA_RE.fullmatch(sha)
                and isinstance(kind, str) and _KIND_RE.fullmatch(kind)):
            raise ValueError("This document names a placed file in a way mosaic doesn't accept "
                             f"({str(kind)[:40]!r}, {str(sha)[:40]!r}); it may be damaged or unsafe.")
        return os.path.join(self.root, sha[:2], sha + KIND_EXT.get(kind, "." + kind))

    def has(self, sha: str, kind: str) -> bool:
        return os.path.exists(self.path(sha, kind))

    def put_file(self, src: str, kind: str | None = None) -> tuple[str, str]:
        """src copied into the cache, named by the hash of the bytes copied. One read: the copy is made
        first and then hashed, so a copy's name always matches what's in it. (Hashing src and then
        copying it read it twice, and a plot re-saved in between, as R does while the app watches it,
        was kept under the earlier bytes' hash; a document then embedded the new picture under the old
        name, which a fresh cache couldn't match: found 2026-11-23.)"""
        kind = kind or kind_of(src)
        incoming = os.path.join(self.root, "incoming")
        os.makedirs(incoming, exist_ok=True)
        tmp = os.path.join(incoming, f"{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(src, tmp)
            sha = sha256_file(tmp)
            dst = self.path(sha, kind)
            if os.path.exists(dst):
                os.remove(tmp)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.replace(tmp, dst)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
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


    def prune_derived(self, days: float = DERIVED_DAYS) -> int:
        """Remove the derived files (previews, conversions, notes) nothing has read or written
        for `days` days; each is made again when next wanted. Returns the bytes freed."""
        root, freed, cutoff = os.path.join(self.root, "derived"), 0, time.time() - days * 86400
        for folder, _, names in os.walk(root):
            for n in names:
                p = os.path.join(folder, n)
                try:
                    st = os.stat(p)
                    if max(st.st_atime, st.st_mtime) < cutoff:
                        os.remove(p)   # one of mosaic's own derived files
                        freed += st.st_size
                except OSError:   # (in use, or gone already)
                    pass
        return freed


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
    # Copied while it holds still: its size and time looked at before and after each copy, and copied
    # again (up to STABLE_TRIES times) while they change, so a plot still being written isn't taken
    # half-way. If it never holds still, the time from before the last copy is kept, so the next look
    # (every 2 s in the editor) sees it changed and reads it again
    for _ in range(STABLE_TRIES):
        before = os.stat(path)
        sha, stored = cache.put_file(path, kind)
        after = os.stat(path)
        if (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns):
            break
        time.sleep(STABLE_WAIT)
    st = before
    var = {"sha256": sha, "kind": kind, "bytes": os.path.getsize(stored)}
    # (sizes read from the copy kept, not the file, which may have changed since)
    var.update({k: v for k, v in probe(stored, kind).items() if k != "kind"})
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


def refresh_asset(asset: dict, cache: AssetCache, doc_dir: str | None = None, force: bool = False) -> list[str]:
    """Re-read linked variants whose files changed. Returns the kinds that changed.

    `force` (Refresh All Pictures): re-read every linked file whatever its date says, and take in
    copies of the plot saved since it was placed (the same name, another format, the same size,
    as new_asset finds them); those count as changed too."""
    changed = []
    if not asset.get("auto_update") and not (force and any(v.get("src") for v in asset["variants"].values())):
        return changed
    for kind, var in list(asset["variants"].items()):
        src = resolve_link(var, doc_dir)
        if not src:
            continue
        try:
            st = os.stat(src)
        except OSError:
            continue
        if not force and var.get("mtime") == st.st_mtime and var.get("bytes") == st.st_size:
            continue
        new = make_variant(src, cache, link=True)
        if new["sha256"] != var["sha256"]:
            asset["variants"][kind] = new
            changed.append(kind)
        else:
            var["mtime"], var["bytes"] = st.st_mtime, st.st_size
    if force:
        changed += _new_copies(asset, cache, doc_dir)
    if changed:
        prim = asset["variants"][asset["primary"]]
        asset["size_pt"] = list(prim["size_pt"])
        if "page_sizes" in prim:
            asset["page_sizes"] = prim["page_sizes"]
    return changed


def _new_copies(asset: dict, cache: AssetCache, doc_dir: str | None) -> list[str]:
    """Copies of a linked plot saved beside its file since it was placed, added to its variants
    as new_asset would have (PDF and SVG copies; a PNG copy of a picture with no vector copy)."""
    primary = asset.get("primary")
    src = resolve_link(asset["variants"].get(primary) or {}, doc_dir)
    if not src:
        return []
    added = []
    ref = asset["variants"][primary]["size_pt"]
    for kind, path in siblings(src).items():
        if kind in asset["variants"] or kind not in VECTOR_KINDS + ("png",):
            continue
        if kind in RASTER_KINDS and (primary in VECTOR_KINDS or any(k in asset["variants"] for k in VECTOR_KINDS)):
            continue   # a vector plot exports from its vector copies
        try:
            var = make_variant(path, cache, link=True)
        except Exception:
            continue
        if abs(var["size_pt"][0] - ref[0]) <= SIZE_TOLERANCE and abs(var["size_pt"][1] - ref[1]) <= SIZE_TOLERANCE:
            asset["variants"][kind] = var
            added.append(kind)
    return added


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
        self.bleed: dict[str, dict] = {}   # asset id -> what cleaning its see-through pixels found (alphableed)

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
        sha = self.asset(asset_id)["variants"][kind]["sha256"]
        if kind == "svg":
            name = self.asset(asset_id).get("name", asset_id)
            self.notes.append(f"{name}: converted SVG to PDF (no PDF copy found)")
            kind, path, sha = "pdf", self.svg_to_pdf(path, sha), sha + ".rsvg"
        # The colour hidden under see-through pixels, filled from the visible ones (alphableed.py)
        from . import alphableed
        self.bleed[asset_id], clean = alphableed.cleaned(self.cache, sha, kind, path)
        return ("png" if clean != path and kind == "tiff" else kind), clean

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

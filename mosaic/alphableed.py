"""Cleaning the colour hidden under a picture's see-through parts, for export.

A picture with transparency keeps a colour in every pixel, also where it is fully see-through
(alpha 0). Most programs leave black there (Cairo, so R's cairo_pdf and svglite, rsvg-convert;
often PowerPoint). In a PDF the colour and the transparency are two separate images (the
picture and its soft mask, /SMask), and a renderer that scales them separately (PDFium: Chrome,
prose, mosaic's own PNG/TIFF/JPEG export and PDF previews) mixes that hidden black into the
picture's soft edges: thin grey outlines appear around light shapes. Apple's renderer (Preview)
combines them first, so nothing shows there.

The fix is "alpha bleeding", as game engines do for textures: every fully see-through pixel takes
the colour of the nearest visible pixels (a push-pull pyramid: averages of the visible pixels
around it, from 2x2 blocks up to the whole picture), so whatever a renderer mixes in at an edge
is the edge's own colour. Visible pixels (alpha above 0, also the half see-through ones) keep
their colour byte for byte, and the transparency is not touched, so the picture looks the same
everywhere it was drawn right before.

A soft mask with /Matte (the colour pre-multiplied by a matte colour) was tried instead: PDFium
draws it clean, but Apple's renderer ignores /Matte and draws the pre-multiplied colour as it is,
so the edges go dark in Preview instead (docs/alpha-bleed.md). Bleeding is clean in both.

Cleaning is done once per placed file (by its SHA-256) and kept in the cache's derived files:
`<sha>.bleed1.json` says what was found, `<sha>.bleed1.pdf` / `.png` is the cleaned copy when
anything changed. A picture with nothing to clean is exported from its own file as before.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
import zlib

import numpy as np

VERSION = "bleed1"   # (part of the cached files' names: a change in how cleaning works makes new ones)
CONTRAST = 32        # hidden colour this far (0-255, any channel) from the fill counts as contrasting
MIN_PIXELS = 1       # contrasting hidden pixels a picture needs before it is cleaned
EDGE = 2             # pixels from a visible one: a contrasting hidden pixel this close shows as an outline

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


# ---------------------------------------------------------------------------
# The fill
# ---------------------------------------------------------------------------

def fill_hidden(color: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """The colour with every fully see-through pixel (alpha 0) filled from the visible ones
    around it. color: (h, w, n) or (h, w) uint8; alpha: (h, w) uint8. Visible pixels are
    returned unchanged; a picture with no visible pixel (or none hidden) is returned as it is."""
    flat = color.ndim == 2
    c = color[..., None] if flat else color
    hidden = alpha == 0
    if not hidden.any() or hidden.all():
        return color
    w = alpha.astype(np.float32) / 255.0
    # Push: halve the picture until every block has something visible in it (sums weighted by alpha)
    cw = [c.astype(np.float32) * w[..., None]]
    ws = [w]
    while (ws[-1] <= 0).any() and max(ws[-1].shape) > 1:
        a, b = cw[-1], ws[-1]
        h, wd = b.shape
        ph, pw = h % 2, wd % 2
        if ph or pw:
            a = np.pad(a, ((0, ph), (0, pw), (0, 0)))
            b = np.pad(b, ((0, ph), (0, pw)))
        h2, w2 = b.shape[0] // 2, b.shape[1] // 2
        cw.append(a.reshape(h2, 2, w2, 2, -1).sum(axis=(1, 3)))
        ws.append(b.reshape(h2, 2, w2, 2).sum(axis=(1, 3)))
    # Pull: from the smallest level up, a block with nothing visible takes its parent's colour
    out = cw[-1] / np.maximum(ws[-1], 1e-12)[..., None]
    for level in range(len(cw) - 2, 0, -1):
        a, b = cw[level], ws[level]
        up = np.repeat(np.repeat(out, 2, axis=0), 2, axis=1)[:b.shape[0], :b.shape[1]]
        out = np.where((b > 0)[..., None], a / np.maximum(b, 1e-12)[..., None], up)
    # (the picture's own size: only the hidden pixels change, each from the block it is in)
    ys, xs = np.nonzero(hidden)
    filled = c.copy()
    filled[ys, xs] = np.clip(np.rint(out[ys // 2, xs // 2]), 0, 255).astype(np.uint8)
    return filled[..., 0] if flat else filled


def _near(mask: np.ndarray, r: int) -> np.ndarray:
    """mask grown by r pixels (a square: rows, then columns)."""
    out = mask.copy()
    for axis in (0, 1):
        grown = out.copy()
        for k in range(1, r + 1):
            a = np.roll(out, k, axis=axis)
            b = np.roll(out, -k, axis=axis)
            if axis == 0:
                a[:k], b[-k:] = False, False
            else:
                a[:, :k], b[:, -k:] = False, False
            grown |= a | b
        out = grown
    return out


def contrasting(color: np.ndarray, filled: np.ndarray, alpha: np.ndarray) -> tuple[int, int]:
    """(hidden pixels holding a colour clearly unlike the visible colour around them, and how
    many of those are next to a visible pixel, within EDGE pixels: what shows as an outline)."""
    hidden = alpha == 0
    if not hidden.any():
        return 0, 0
    d = np.abs(color.astype(np.int16) - filled.astype(np.int16))
    if d.ndim == 3:
        d = d.max(axis=2)
    far = (d > CONTRAST) & hidden
    n = int(far.sum())
    return n, (int((far & _near(~hidden, EDGE)).sum()) if n else 0)


def clean_arrays(color: np.ndarray, alpha: np.ndarray) -> tuple[np.ndarray, int, int]:
    """(cleaned colour, contrasting hidden pixels, those of them at an edge); the colour comes
    back as it was when there is nothing to clean."""
    filled = fill_hidden(color, alpha)
    n, edge = contrasting(color, filled, alpha) if filled is not color else (0, 0)
    return (filled if n >= MIN_PIXELS else color), n, edge


# ---------------------------------------------------------------------------
# Pictures (PNG, TIFF) and PDFs
# ---------------------------------------------------------------------------

def _empty() -> dict:
    """What cleaning found: pictures with transparency, pictures cleaned, contrasting hidden
    pixels in all, and pictures where those show as outlines (next to visible pixels)."""
    return {"images": 0, "cleaned": 0, "contrasting": 0, "edges": 0}


def _write_atomic(path: str, data: bytes) -> None:
    tmp = f"{path}.{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def clean_raster(src: str, dst: str) -> dict:
    """A PNG/TIFF with transparency: written to dst (PNG) cleaned if it needs it."""
    import io
    from PIL import Image
    with Image.open(src) as im:
        im.load()
        info = {k: im.info[k] for k in ("icc_profile", "dpi") if k in im.info}
        if (im.mode == "P" and "transparency" in im.info) or im.mode == "PA":
            im = im.convert("RGBA")
        if im.mode not in ("RGBA", "LA"):
            return _empty()
        arr = np.asarray(im)
    color, alpha = arr[..., :-1], arr[..., -1]
    if color.shape[2] == 1:
        color = color[..., 0]
    cleaned, n, edge = clean_arrays(color, alpha)
    result = {"images": 1, "cleaned": int(cleaned is not color), "contrasting": n, "edges": int(edge > 0)}
    if cleaned is not color:
        out = np.dstack([cleaned, alpha])
        buf = io.BytesIO()
        Image.fromarray(out, "RGBA" if out.shape[2] == 4 else "LA").save(buf, "PNG", compress_level=6, **info)
        _write_atomic(dst, buf.getvalue())
    return result


_UNDECODABLE = {"/DCTDecode", "/JPXDecode", "/JBIG2Decode", "/CCITTFaxDecode"}


def _components(cs) -> int | None:
    """Colour components of an image colour space mosaic can clean (not Indexed, not Separation)."""
    import pikepdf
    if isinstance(cs, pikepdf.Name):
        return {"/DeviceGray": 1, "/DeviceRGB": 3, "/DeviceCMYK": 4, "/CalGray": 1, "/CalRGB": 3}.get(str(cs))
    if isinstance(cs, pikepdf.Array) and len(cs):
        head = str(cs[0])
        if head == "/ICCBased":
            return int(cs[1].get("/N", 0)) or None
        if head in ("/CalGray", "/CalRGB", "/Lab"):
            return {"/CalGray": 1, "/CalRGB": 3, "/Lab": 3}[head]
    return None


def _filters(stream) -> list[str]:
    import pikepdf
    f = stream.get("/Filter")
    if f is None:
        return []
    return [str(x) for x in f] if isinstance(f, pikepdf.Array) else [str(f)]


def _plain_8bit(stream) -> bool:
    return (int(stream.get("/BitsPerComponent", 0)) == 8 and "/Decode" not in stream
            and not bool(stream.get("/ImageMask", False))
            and not any(f in _UNDECODABLE for f in _filters(stream)))


def clean_pdf(src: str, dst: str) -> dict:
    """Every image in a PDF with a soft mask: cleaned in a copy written to dst (only if any
    needed it). Images it can't read losslessly (JPEG and other lossy or special encodings,
    16-bit, Indexed colours, a /Matte already) are left as they are."""
    import pikepdf
    from pikepdf import Name
    result = _empty()
    with pikepdf.open(src) as pdf:
        for obj in pdf.objects:
            if not isinstance(obj, pikepdf.Stream) or obj.get("/Subtype") != Name.Image:
                continue
            smask = obj.get("/SMask")
            if not isinstance(smask, pikepdf.Stream):
                continue
            result["images"] += 1
            n = _components(obj.get("/ColorSpace"))
            w, h = int(obj.get("/Width", 0)), int(obj.get("/Height", 0))
            if (not n or not _plain_8bit(obj) or not _plain_8bit(smask) or "/Matte" in smask
                    or int(smask.get("/Width", 0)) != w or int(smask.get("/Height", 0)) != h or not w or not h):
                continue
            try:
                raw = obj.read_bytes()
                mraw = smask.read_bytes()
            except Exception:
                continue
            if len(raw) < w * h * n or len(mraw) < w * h:
                continue
            color = np.frombuffer(raw, np.uint8, w * h * n).reshape(h, w, n)
            alpha = np.frombuffer(mraw, np.uint8, w * h).reshape(h, w)
            cleaned, k, edge = clean_arrays(color if n > 1 else color[..., 0], alpha)
            result["contrasting"] += k
            result["edges"] += int(edge > 0)
            if k >= MIN_PIXELS:
                obj.write(_flate_up(cleaned.reshape(h, w, n)), filter=Name.FlateDecode,
                          decode_parms=pikepdf.Dictionary(Predictor=12, Colors=n, BitsPerComponent=8, Columns=w))
                result["cleaned"] += 1
        if result["cleaned"]:
            tmp = f"{dst}.{uuid.uuid4().hex[:6]}.tmp"
            pdf.save(tmp)
            os.replace(tmp, dst)
    return result


def _flate_up(arr: np.ndarray) -> bytes:
    """An 8-bit image compressed with the PNG "Up" predictor (each row as its difference from
    the one above): the filled areas are smooth, and compress far better so."""
    h, w, n = arr.shape
    rows = arr.reshape(h, w * n)
    diff = np.empty_like(rows)
    diff[0] = rows[0]
    diff[1:] = rows[1:] - rows[:-1]   # (uint8: wraps around, as the predictor expects)
    body = np.empty((h, w * n + 1), np.uint8)
    body[:, 0] = 2
    body[:, 1:] = diff
    return zlib.compress(body.tobytes(), 6)


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------

def cleaned(cache, key: str, kind: str, path: str) -> tuple[dict, str]:
    """(what was found, the path to export from) for a placed file: its cleaned copy, or its own
    path when nothing needed cleaning. key: the file's SHA-256 (plus anything that tells
    conversions apart); kind: "pdf", "png" or "tiff". Made once and kept in the cache."""
    if kind not in ("pdf", "png", "tiff"):
        return _empty(), path
    ext = ".pdf" if kind == "pdf" else ".png"
    note, out = cache.derived(f"{key}.{VERSION}", ".json"), cache.derived(f"{key}.{VERSION}", ext)
    with _lock(note):
        result = None
        if os.path.exists(note):
            try:
                with open(note, encoding="utf-8") as fh:
                    result = json.load(fh)
                os.utime(note)   # (still in use: kept by prune_derived)
            except (OSError, ValueError):
                result = None
        if result is not None and result.get("cleaned") and not os.path.exists(out):
            result = None   # (the copy was pruned: made again)
        if result is None:
            try:
                result = clean_pdf(path, out) if kind == "pdf" else clean_raster(path, out)
            except Exception as e:   # (a file mosaic can't read this way exports as it is)
                result = dict(_empty(), error=str(e)[:200])
            _write_atomic(note, json.dumps(result).encode("utf-8"))
    if result.get("cleaned"):
        try:
            os.utime(out)
        except OSError:
            pass
        return result, out
    return result, path


def check_note(sources, asset_id: str, source: str, name: str) -> str | None:
    """Check's note for a picture whose see-through parts hide a contrasting colour next to their
    edges (cleaning it now, as export would, so export finds it done). sources: the
    SourceResolver that exports use."""
    try:
        kind = sources.for_pdf(asset_id, source)[0]
    except Exception:   # (a missing or unreadable file: Check says so elsewhere)
        return None
    result = sources.bleed.get(asset_id) or {}
    n = result.get("edges", 0)
    if not result.get("cleaned") or not n:
        return None
    what = ("its see-through parts hide" if kind != "pdf"
            else f"{n} picture{'s' if n > 1 else ''} inside it hide{'' if n > 1 else 's'}")
    where = "" if kind != "pdf" else " under the see-through parts"
    return (f"{name}: {what} a contrasting colour{where}, which Chrome and prose show as thin grey "
            f"edges; export fills it in, so nothing else changes")

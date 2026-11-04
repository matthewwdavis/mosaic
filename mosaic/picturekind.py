"""What kind of picture a placed PNG, TIFF or JPEG is, for journals' resolution rules: a photo,
a photo with text or lines drawn on it ("combination" art), or line art (graphs, drawings).

The guess reads the pixels in 16 px blocks, on a copy cut down to about 800 px across by taking
every nth pixel, which keeps colours exact. A photo's blocks vary a little from pixel to pixel
everywhere (grain, gradients). Line art's are flat colour with sharp edges. Letters, arrows or a
scale bar drawn over a photo show up as one exact colour that meets the texture round it with a
sudden jump; where a photo reaches pure white or black (a highlight, a dark background) it gets
there gradually.

Tuned on 2026-11-04 with scikit-image's sample photos and micrographs, macOS's landscape
pictures, mosaic's example plots, and photos with letters, scale bars or axes drawn on them.
Every photo came out a photo and every plot line art; a plot saved as JPEG comes out line art
too (its blocks are judged with a little give for JPEG's noise). JPEG blurs letters drawn on a
photo, though, so a labelled photo saved as JPEG can pass for a plain one. The Picture tab can
set the kind when the guess is wrong.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

KINDS = ("photo", "combination", "line_art")
NAMES = {"photo": "a photo", "combination": "a photo with text or lines", "line_art": "line art"}
BLOCK = 16
CAP = 800
_KEY = np.array([65536, 256, 1])
_guesses: dict = {}


def _pixels(path: str) -> tuple[np.ndarray, bool]:
    """RGB pixels, every nth so the long side is at most CAP; True if JPEG-compressed."""
    with Image.open(path) as im:
        im.seek(0)
        jpeg = im.format == "JPEG"
        step = max(1, -(-max(im.size) // CAP))
        if im.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
            # 16-bit and float images (microscopes'): stretch to 8 bits instead of clipping at 255
            a = np.asarray(im, dtype=np.float64)[::step, ::step]
            hi = float(np.percentile(a, 99.9)) or 1.0
            a = np.clip(a / hi * 255, 0, 255).astype(np.int16)
            return np.repeat(a[:, :, None], 3, axis=2), jpeg
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            im = im.convert("RGBA")
            im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)
        a = np.asarray(im.convert("RGB"))[::step, ::step].astype(np.int16)
    return a, jpeg


def _drawn_on(b: np.ndarray, k: np.ndarray, value: int) -> bool:
    """Whether the pixels of one exact colour in a block meet the rest with a sudden jump (more
    than 64 in a channel) almost everywhere along their edge, as something drawn on top does."""
    m = k == value
    colour = np.array([value >> 16, (value >> 8) & 255, value & 255])
    diff = np.abs(b - colour).max(axis=2)
    edge = np.zeros(m.shape, bool)
    jump = np.zeros(m.shape, bool)
    for near, here in (((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                       ((slice(1, None), slice(None)), (slice(None, -1), slice(None)))):
        for there, at in ((near, here), (here, near)):   # each neighbour, both ways
            meets = m[at] & ~m[there]
            edge[at] |= meets
            jump[at] |= meets & (diff[there] > 64)
    return edge.sum() >= 4 and jump.sum() >= 0.6 * edge.sum()


def measure(a: np.ndarray, jpeg: bool = False) -> dict:
    """Block counts: blocks with any change in them, flat-with-edges ("graphic") ones, those also
    allowing JPEG's noise, and photo blocks with something of one exact colour drawn on them."""
    h, w, _ = a.shape
    key = a @ _KEY
    n = graphic = graphic_jpeg = overlay = 0
    for y in range(0, h - BLOCK + 1, BLOCK):
        for x in range(0, w - BLOCK + 1, BLOCK):
            b = a[y:y + BLOCK, x:x + BLOCK]
            d = np.concatenate([np.abs(b[:, 1:] - b[:, :-1]).max(axis=2).ravel(),
                                np.abs(b[1:] - b[:-1]).max(axis=2).ravel()])
            if not d.any():
                continue   # one colour throughout
            if jpeg and d.max() <= 8:
                continue   # (so is this, but for JPEG's noise)
            n += 1
            small, big = ((d > 0) & (d <= 24)).mean(), (d > 48).mean()
            if small < 0.35 and (d == 0).mean() >= 0.5 and big > 0:
                graphic += 1
            if jpeg and ((d > 8) & (d <= 24)).mean() < 0.35 and (d <= 8).mean() >= 0.5 and big > 0:
                graphic_jpeg += 1
            if small >= 0.2:
                # Something drawn over the photo: one of its commonest exact colours, far from the
                # block's middle colour, meeting the photo with a jump
                k = key[y:y + BLOCK, x:x + BLOCK]
                vals, counts = np.unique(k, return_counts=True)
                med = np.median(b.reshape(-1, 3), axis=0)
                for i in np.argsort(counts)[::-1][:3]:
                    share = counts[i] / k.size
                    if share < 0.04:
                        break
                    v = int(vals[i])
                    colour = np.array([v >> 16, (v >> 8) & 255, v & 255])
                    if share <= 0.6 and np.abs(colour - med).max() >= 80 and _drawn_on(b, k, v):
                        overlay += 1
                        break
    return {"blocks": n, "graphic": graphic, "graphic_jpeg": graphic_jpeg, "overlay": overlay}


def classify(m: dict, jpeg: bool = False) -> str:
    n = max(m["blocks"], 1)
    if m["graphic"] / n >= 0.6 or (jpeg and m["graphic_jpeg"] / n >= 0.6):
        return "line_art"
    if m["graphic"] / n >= 0.04 or m["overlay"] >= 1:
        return "combination"
    return "photo"


def guess(path: str) -> str | None:
    """The picture's kind, or None if it can't be read."""
    try:
        a, jpeg = _pixels(path)
    except Exception:
        return None
    if min(a.shape[:2]) < BLOCK:
        return "line_art" if len(np.unique(a.reshape(-1, 3) @ _KEY)) <= 16 else "photo"
    return classify(measure(a, jpeg), jpeg)


def asset_kind(asset: dict, cache) -> str | None:
    """The guess for a placed raster picture (cached by its content); None for PDFs and SVGs."""
    variants = asset.get("variants") or {}
    if any(k in variants for k in ("pdf", "svg")):
        return None
    var = next((variants[k] for k in ("png", "tiff", "jpeg") if k in variants), None)
    if var is None:
        return None
    if var["sha256"] not in _guesses:
        _guesses[var["sha256"]] = guess(cache.path(var["sha256"], var["kind"]))
    return _guesses[var["sha256"]]


def item_kind(item: dict, asset: dict, cache) -> tuple[str | None, bool]:
    """The kind a picture is checked as, and whether that's a guess (not set on its Picture tab)."""
    if item.get("picture_kind") in KINDS:
        return item["picture_kind"], False
    return asset_kind(asset, cache), True

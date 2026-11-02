"""Find the original figure files behind pictures pulled out of a PowerPoint deck.

PowerPoint rewrites SVGs on insert, so deck SVGs never byte-match the R files. They are
matched on what PowerPoint keeps: size, text, text positions, colours, embedded images and
the plotted coordinates (the approach of Matthew's earlier figure script). PDFs (from PowerPoint
for Mac's EMF wrappers) and images are matched by content hash first.
"""
from __future__ import annotations

import base64
import collections
import hashlib
import io
import os
import re

from lxml import etree

from ..assets import EXT_KIND, svg_geometry

MATCH_MIN = 4.0      # out of 5: how similar an SVG must be to count as the same plot
MATCH_TIE = 0.05     # the best match must beat the runner-up by this much
SIZE_TOL = 0.6       # points
_PARSER = etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)


def _png_size(b64: bytes):
    raw = base64.b64decode(b64[:64])
    return tuple(int.from_bytes(raw[i:i + 4], "big") for i in (16, 20)) if raw[:4] == b"\x89PNG" else None


def svg_signature(data: bytes) -> dict:
    root = etree.fromstring(data, _PARSER)
    w, h = svg_geometry(root)["viewbox"][2:]
    texts, spots = collections.Counter(), collections.Counter()
    for t in root.iter("{http://www.w3.org/2000/svg}text"):
        s = re.sub(r"\s+", " ", "".join(t.itertext()).replace("\xa0", " ")).strip()
        if not s:
            continue
        texts[s] += 1
        if t.get("x") and t.get("y"):
            try:
                spots[(s, round(float(t.get("x").rstrip("px"))), round(float(t.get("y").rstrip("px"))))] += 1
            except ValueError:
                pass
    colors = {c.upper() for c in re.findall(rb"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])", data)}
    rasters = collections.Counter(_png_size(m) for m in re.findall(rb"base64,([A-Za-z0-9+/=]{64})", data))
    drawing = re.sub(rb"base64,[A-Za-z0-9+/=]+", b"", data)
    numbers = collections.Counter(round(float(n), 1) for n in re.findall(rb"-?\d+\.\d+", drawing))
    return {"w": w, "h": h, "texts": texts, "spots": spots, "colors": colors, "rasters": rasters,
            "numbers": numbers, "md5": hashlib.md5(data).hexdigest()}


def _raster_pixels(data: bytes) -> collections.Counter:
    """Hashes of the decoded pixels of every image embedded in an SVG."""
    from PIL import Image
    out = collections.Counter()
    for b64 in re.findall(rb"base64,([A-Za-z0-9+/=]+)", data):
        try:
            im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
        except Exception:
            continue
        out[hashlib.md5(im.tobytes()).hexdigest()] += 1
    return out


def _jaccard(a, b) -> float:
    if not a and not b:
        return 1.0
    if isinstance(a, set):
        return len(a & b) / len(a | b)
    return sum((a & b).values()) / sum((a | b).values())


def _svg_viewbox_size(path: str):
    """viewBox width/height from the root tag only (fast)."""
    try:
        for _event, el in etree.iterparse(path, events=("start",), huge_tree=True, resolve_entities=False):
            g = svg_geometry(el)
            return tuple(g["viewbox"][2:])
    except Exception:
        return None
    return None


class CandidateIndex:
    """Figure files under the search folders, indexed lazily."""

    def __init__(self, dirs: list[str]):
        self.files: dict[str, list[str]] = collections.defaultdict(list)
        for d in dirs:
            for root, subdirs, names in os.walk(d):
                subdirs[:] = [s for s in subdirs if not s.startswith(".")]
                for n in names:
                    k = EXT_KIND.get(os.path.splitext(n)[1].lower())
                    if k:
                        self.files[k].append(os.path.join(root, n))
        self._hash: dict[str, str] = {}
        self._svg_size: dict[str, tuple] = {}
        self._svg_sig: dict[str, dict] = {}
        self._px: dict[str, collections.Counter] = {}

    def sha(self, path: str) -> str:
        if path not in self._hash:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            self._hash[path] = h.hexdigest()
        return self._hash[path]

    def by_hash(self, kind: str, data: bytes) -> str | None:
        digest = hashlib.sha256(data).hexdigest()
        size = len(data)
        for p in self.files.get(kind, []):
            try:
                if os.path.getsize(p) == size and self.sha(p) == digest:
                    return p
            except OSError:
                continue
        return None

    def _pixels(self, path: str) -> collections.Counter:
        if path not in self._px:
            with open(path, "rb") as fh:
                self._px[path] = _raster_pixels(fh.read())
        return self._px[path]

    def match_svg(self, data: bytes) -> tuple[str | None, dict]:
        sig = svg_signature(data)
        scored = []
        for p in self.files.get("svg", []):
            if p not in self._svg_size:
                self._svg_size[p] = _svg_viewbox_size(p)
            size = self._svg_size[p]
            if not size or abs(size[0] - sig["w"]) > SIZE_TOL or abs(size[1] - sig["h"]) > SIZE_TOL:
                continue
            if p not in self._svg_sig:
                try:
                    with open(p, "rb") as fh:
                        self._svg_sig[p] = svg_signature(fh.read())
                except Exception:
                    continue
            c = self._svg_sig[p]
            score = (_jaccard(sig["texts"], c["texts"]) + _jaccard(sig["spots"], c["spots"])
                     + _jaccard(sig["colors"], c["colors"]) + _jaccard(sig["rasters"], c["rasters"])
                     + _jaccard(sig["numbers"], c["numbers"]))
            scored.append((score, p))
        scored.sort(reverse=True)
        if not scored:
            return None, {"score": 0.0, "runner_up": 0.0}
        # Near-ties: also compare the pixels of the images embedded in the SVGs
        close = {p for s, p in scored if scored[0][0] - s <= MATCH_TIE}
        if len(close) > 1:
            mine = _raster_pixels(data)
            scored = sorted(((s + (_jaccard(mine, self._pixels(p)) if p in close else 0.0), p)
                             for s, p in scored), reverse=True)
        best_score, best = scored[0]
        rivals = [s for s, p in scored[1:] if self._svg_sig[p]["md5"] != self._svg_sig[best]["md5"]]
        runner = rivals[0] if rivals else 0.0
        info = {"score": round(best_score, 3), "runner_up": round(runner, 3)}
        if best_score >= MATCH_MIN and best_score - runner > MATCH_TIE:
            return best, info
        return None, info


def default_search_dirs(deck_path: str) -> list[str]:
    """The nearest enclosing 'Figures' folder (R output lives there), else the deck's folder."""
    d = os.path.dirname(os.path.abspath(deck_path))
    probe = d
    for _ in range(4):
        if os.path.basename(probe).lower() == "figures":
            return [probe]
        cand = os.path.join(probe, "Figures")
        if os.path.isdir(cand) and probe != d:
            return [cand]
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return [d]

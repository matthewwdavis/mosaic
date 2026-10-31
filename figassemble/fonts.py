"""Font discovery, fallback and metrics.

Fonts are found in the platform's font folders and indexed by family and style. Glyph
advances come straight from each font's hmtx table, so text measured here lands in exactly
the same place in every export format.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass

from fontTools.ttLib import TTCollection, TTFont

FONT_EXTS = {".ttf", ".otf", ".ttc", ".otc"}
DEFAULT_FAMILY = "Helvetica"

# Families tried in order when a requested family isn't installed. Arial has the same
# letter widths as Helvetica, so layout doesn't move when one stands in for the other.
_SANS = ["Helvetica", "Arial", "Liberation Sans", "TeX Gyre Heros", "Nimbus Sans", "Nimbus Sans L", "DejaVu Sans"]
_SERIF = ["Times New Roman", "Times", "Liberation Serif", "TeX Gyre Termes", "Nimbus Roman", "DejaVu Serif"]
_MONO = ["Courier New", "Courier", "Liberation Mono", "Nimbus Mono PS", "DejaVu Sans Mono"]
FALLBACKS = {
    "helvetica": _SANS,
    "arial": ["Arial"] + _SANS,
    "helvetica neue": ["Helvetica Neue"] + _SANS,
    "sans": _SANS,
    "sans-serif": _SANS,
    "times new roman": _SERIF,
    "times": ["Times"] + _SERIF,
    "serif": _SERIF,
    "courier new": _MONO,
    "courier": ["Courier"] + _MONO,
    "monospace": _MONO,
}
# Broad-coverage fonts searched for characters (Greek, symbols) a chosen font lacks
_GLYPH_FALLBACKS = ["Helvetica", "Arial", "Helvetica Neue", "Arial Unicode MS", "Apple Symbols",
                    "Segoe UI Symbol", "DejaVu Sans", "Symbol", "STIXGeneral"]


def font_dirs() -> list[str]:
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
                "/Library/Fonts", os.path.join(home, "Library", "Fonts")]
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        local = os.environ.get("LOCALAPPDATA", "")
        return [os.path.join(windir, "Fonts"), os.path.join(local, "Microsoft", "Windows", "Fonts")]
    return ["/usr/share/fonts", "/usr/local/share/fonts",
            os.path.join(home, ".fonts"), os.path.join(home, ".local", "share", "fonts")]


def config_dir() -> str:
    path = os.environ.get("FIGASSEMBLE_HOME") or os.path.join(os.path.expanduser("~"), ".figassemble")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass(frozen=True)
class FaceRef:
    path: str
    index: int
    family: str
    style: str
    weight: int
    italic: bool
    ps_name: str

    @property
    def bold(self) -> bool:
        return self.weight >= 600


def _name(tt: TTFont, *ids: int) -> str:
    table = tt["name"]
    for nid in ids:
        rec = table.getName(nid, 3, 1, 0x409) or table.getName(nid, 1, 0, 0)
        if rec is None:
            rec = next((r for r in table.names if r.nameID == nid), None)
        if rec is not None:
            try:
                return rec.toUnicode().strip()
            except Exception:
                continue
    return ""


def _describe(tt: TTFont, path: str, index: int) -> FaceRef | None:
    family = _name(tt, 16, 1)
    style = _name(tt, 17, 2) or "Regular"
    if not family:
        return None
    os2 = tt.get("OS/2")
    weight = getattr(os2, "usWeightClass", 400) if os2 is not None else 400
    fs_sel = getattr(os2, "fsSelection", 0) if os2 is not None else 0
    low = style.lower()
    italic = bool(fs_sel & 1) or "italic" in low or "oblique" in low
    if "bold" in low and weight < 600:
        weight = 700
    return FaceRef(path, index, family, style, int(weight), italic, _name(tt, 6) or family.replace(" ", ""))


class FontIndex:
    """Families and faces installed on this machine (cached in ~/.figassemble)."""

    def __init__(self, dirs: list[str] | None = None, cache_path: str | None = None):
        self.dirs = dirs if dirs is not None else font_dirs()
        self.cache_path = cache_path or os.path.join(config_dir(), "font-index.json")
        self._faces: list[FaceRef] | None = None
        self._lock = threading.Lock()

    def faces(self) -> list[FaceRef]:
        with self._lock:
            if self._faces is None:
                self._faces = self._scan()
            return self._faces

    def families(self) -> list[str]:
        return sorted({f.family for f in self.faces()}, key=str.lower)

    def _scan(self) -> list[FaceRef]:
        try:
            with open(self.cache_path, encoding="utf-8") as fh:
                cache = json.load(fh)
        except (OSError, ValueError):
            cache = {}
        files = {}
        for d in self.dirs:
            for root, _dirs, names in os.walk(d):
                for n in names:
                    if os.path.splitext(n)[1].lower() in FONT_EXTS:
                        files[os.path.join(root, n)] = None
        out: list[FaceRef] = []
        new_cache = {}
        for path in sorted(files):
            try:
                st = os.stat(path)
            except OSError:
                continue
            key = f"{st.st_mtime_ns}:{st.st_size}"
            entry = cache.get(path)
            if entry and entry.get("key") == key:
                faces = entry["faces"]
            else:
                faces = []
                try:
                    if path.lower().endswith((".ttc", ".otc")):
                        n_faces = len(TTCollection(path, lazy=True).fonts)
                    else:
                        n_faces = 1
                    for i in range(n_faces):
                        tt = TTFont(path, fontNumber=i, lazy=True)
                        ref = _describe(tt, path, i)
                        tt.close()
                        if ref is not None:
                            faces.append([ref.family, ref.style, ref.weight, ref.italic, ref.ps_name, i])
                except Exception:
                    faces = []
            new_cache[path] = {"key": key, "faces": faces}
            for fam, style, weight, italic, ps, i in faces:
                out.append(FaceRef(path, i, fam, style, weight, italic, ps))
        try:
            with open(self.cache_path, "w", encoding="utf-8") as fh:
                json.dump(new_cache, fh)
        except OSError:
            pass
        return out

    def family_faces(self, family: str) -> list[FaceRef]:
        fam = family.strip().lower()
        return [f for f in self.faces() if f.family.lower() == fam]

    def find(self, family: str | None, bold: bool = False, italic: bool = False) -> tuple[FaceRef, bool]:
        """Best installed face for a request: (face, needs_synthetic_italic)."""
        family = family or DEFAULT_FAMILY
        chain = [family] + [f for f in FALLBACKS.get(family.strip().lower(), _SANS) if f.lower() != family.lower()]
        for fam in chain:
            faces = self.family_faces(fam)
            if faces:
                return _best_face(faces, bold, italic)
        faces = self.faces()
        if not faces:
            raise RuntimeError("no fonts found on this system")
        return _best_face(faces[:1], bold, italic)


def _best_face(faces: list[FaceRef], bold: bool, italic: bool) -> tuple[FaceRef, bool]:
    def score(f: FaceRef) -> float:
        s = abs(f.weight - (700 if bold else 400)) / 100.0
        s += 0.0 if f.italic == italic else 10.0
        low = f.style.lower()
        if any(w in low for w in ("condensed", "narrow", "compressed", "extended", "expanded")):
            s += 5.0
        return s

    best = min(faces, key=score)
    return best, (italic and not best.italic)


class Face:
    """A loaded font face with the metrics text layout needs (em units unless noted)."""

    def __init__(self, ref: FaceRef):
        self.ref = ref
        tt = TTFont(ref.path, fontNumber=ref.index, lazy=True)
        self.upm = tt["head"].unitsPerEm
        self.cmap = tt.getBestCmap() or {}
        order = tt.getGlyphOrder()
        self._gid = {name: i for i, name in enumerate(order)}
        metrics = tt["hmtx"].metrics
        self._adv = [metrics[name][0] / self.upm if name in metrics else 0.0 for name in order]
        hhea = tt["hhea"]
        os2 = tt.get("OS/2")
        self.ascent = hhea.ascent / self.upm
        self.descent = -hhea.descent / self.upm
        self.line_gap = hhea.lineGap / self.upm
        cap = getattr(os2, "sCapHeight", 0) if os2 is not None else 0
        self.cap_height = cap / self.upm if cap else self.ascent * 0.93
        self.fs_type = getattr(os2, "fsType", 0) if os2 is not None else 0
        head = tt["head"]
        self.bbox = (head.xMin / self.upm, head.yMin / self.upm, head.xMax / self.upm, head.yMax / self.upm)
        post = tt["post"]
        self.italic_angle = float(post.italicAngle)
        self.underline_position = post.underlinePosition / self.upm
        self.underline_thickness = (post.underlineThickness or self.upm * 0.05) / self.upm
        self.is_cff = "CFF " in tt or "CFF2" in tt
        self.ps_name = ref.ps_name
        self.num_glyphs = len(order)
        tt.close()

    @property
    def key(self) -> tuple[str, int]:
        return (self.ref.path, self.ref.index)

    def gid(self, ch: str) -> int:
        name = self.cmap.get(ord(ch))
        return self._gid.get(name, 0) if name else 0

    def has(self, ch: str) -> bool:
        return ord(ch) in self.cmap

    def advance(self, gid: int) -> float:
        return self._adv[gid] if 0 <= gid < len(self._adv) else 0.0

    def text_width(self, text: str, size: float) -> float:
        return sum(self.advance(self.gid(ch)) for ch in text) * size

    @property
    def embeddable(self) -> bool:
        # fsType bit 1 (value 2) alone means "restricted license": no embedding allowed
        return (self.fs_type & 0x000F) != 0x0002


_index: FontIndex | None = None
_faces: dict[tuple[str, int], Face] = {}
_lock = threading.Lock()


def get_font_index() -> FontIndex:
    global _index
    with _lock:
        if _index is None:
            _index = FontIndex()
        return _index


def load_face(ref: FaceRef) -> Face:
    key = (ref.path, ref.index)
    with _lock:
        face = _faces.get(key)
        if face is None:
            face = Face(ref)
            _faces[key] = face
        return face


def resolve_face(family: str | None, bold: bool = False, italic: bool = False,
                 index: FontIndex | None = None) -> tuple[Face, bool]:
    """Load the best face for a family/style; also says whether italic must be synthesised."""
    ref, synth = (index or get_font_index()).find(family, bold, italic)
    return load_face(ref), synth


def glyph_fallback(ch: str, bold: bool, italic: bool, index: FontIndex | None = None) -> tuple[Face, bool] | None:
    """A face that has a glyph for `ch`, searched across broad-coverage families."""
    idx = index or get_font_index()
    for fam in _GLYPH_FALLBACKS:
        faces = idx.family_faces(fam)
        if not faces:
            continue
        ref, synth = _best_face(faces, bold, italic)
        face = load_face(ref)
        if face.has(ch):
            return face, synth
    return None

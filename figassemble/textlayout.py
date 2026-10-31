"""Text layout: paragraphs of styled runs -> positioned glyph runs.

The model follows PowerPoint text boxes (insets, wrap, anchor, autofit, line spacing) so
imported slides land where PowerPoint put them, and text behaves the way PowerPoint users
expect. The line metrics were calibrated against PowerPoint for Mac's own PDF export of
the Bushy_Top figures (170 text boxes, Helvetica 5-8 pt):

- one line at 100% spacing is LINE_FACTOR x (ascent + descent + gap) x size;
- an auto-fitted box is insets + lines + AUTOFIT_EXTRA tall;
- the first baseline sits half the extra leading plus the ascent below the top inset,
  and text under 6.5 pt sits SMALL_TEXT_SHIFT lower still (PowerPoint does this);
- PowerPoint snaps baselines to a 1/300 in grid, so it differs from this model by up to
  0.12 pt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fonts import Face, FontIndex, glyph_fallback, resolve_face

DEFAULT_INSETS = (7.2, 3.6, 7.2, 3.6)   # left, top, right, bottom: PowerPoint's 0.1 in / 0.05 in
LINE_FACTOR = 1.2 * 1.009765625         # 1.21171875
AUTOFIT_EXTRA = 9.0 / 128.0             # points added to every auto-fitted box
SMALL_TEXT_SIZE = 6.5
SMALL_TEXT_SHIFT = 0.75
SCRIPT_SCALE = 2.0 / 3.0                # super/subscript size relative to the run
SYNTHETIC_ITALIC_SKEW = 0.2126          # tan(12 degrees)

DEFAULT_RUN = {"font": "Helvetica", "size": 6.0, "bold": False, "italic": False,
               "color": "#000000", "opacity": 1.0, "baseline": 0.0, "underline": False}


@dataclass
class GlyphRun:
    """Glyphs of one face/size/colour on one line, positioned in frame coordinates."""

    face: Face
    size: float
    color: str
    opacity: float
    x: float                  # start of the run's baseline
    y: float                  # baseline
    text: str                 # characters, one per glyph
    gids: list[int]
    advances: list[float]     # in points
    underline: bool = False
    skew: float = 0.0         # synthetic italic shear (x += skew * height above baseline)

    @property
    def width(self) -> float:
        return sum(self.advances)


@dataclass
class TextLayout:
    runs: list[GlyphRun] = field(default_factory=list)
    content_width: float = 0.0     # widest line, points
    content_height: float = 0.0    # lines + paragraph spacing, points
    autofit_height: float = 0.0    # frame height an auto-fitted box would have
    autofit_width: float = 0.0     # frame width when wrapping is off and the box auto-fits
    overflow: bool = False


def run_style(run: dict, defaults: dict | None = None) -> dict:
    style = dict(DEFAULT_RUN)
    if defaults:
        style.update({k: v for k, v in defaults.items() if v is not None})
    style.update({k: v for k, v in run.items() if v is not None and k != "t"})
    return style


def line_height(face: Face, size: float) -> float:
    return LINE_FACTOR * size * (face.ascent + face.descent + face.line_gap)


def first_baseline(face: Face, size: float, height: float) -> float:
    """Baseline below the top of a line box of `height` (PowerPoint placement)."""
    ink = (face.ascent + face.descent) * size
    shift = SMALL_TEXT_SHIFT if size < SMALL_TEXT_SIZE else 0.0
    return (height - ink) / 2.0 + face.ascent * size + shift


@dataclass
class _Piece:
    """Characters sharing one face and style; the unit of line breaking."""

    text: str
    face: Face
    synth_italic: bool
    style: dict
    size: float       # drawn size (super/subscript already applied)
    rise: float       # baseline shift up, points
    advances: list[float]
    gids: list[int]


def _pieces(runs: list[dict], defaults: dict | None, index: FontIndex | None) -> list[_Piece]:
    out: list[_Piece] = []
    for run in runs:
        text = run.get("t", "")
        if not text:
            continue
        st = run_style(run, defaults)
        face, synth = resolve_face(st["font"], bool(st["bold"]), bool(st["italic"]), index)
        base = float(st.get("baseline") or 0.0)
        size = float(st["size"]) * (SCRIPT_SCALE if base else 1.0)
        rise = base * float(st["size"])
        for ch in text:
            f, s = face, synth
            if not face.has(ch) and ch not in "\n\t":
                fb = glyph_fallback(ch, bool(st["bold"]), bool(st["italic"]), index)
                if fb is not None:
                    f, s = fb
            gid = f.gid(ch)
            adv = f.advance(gid) * size
            last = out[-1] if out else None
            if last is not None and last.face is f and last.style is st and last.synth_italic == s:
                last.text += ch
                last.gids.append(gid)
                last.advances.append(adv)
            else:
                out.append(_Piece(ch, f, s, st, size, rise, [adv], [gid]))
    return out


def _break_lines(pieces: list[_Piece], max_width: float | None) -> list[list[_Piece]]:
    """Greedy line breaking after spaces and hyphens; overlong words break anywhere."""
    # Flatten to characters so breaks can fall inside a piece
    chars = [(p, i) for p in pieces for i in range(len(p.text))]
    lines: list[list[tuple[_Piece, int]]] = []
    line: list[tuple[_Piece, int]] = []
    width = 0.0
    last_break = -1   # index in `line` after which we may break
    for p, i in chars:
        ch = p.text[i]
        if ch == "\n":
            lines.append(line)
            line, width, last_break = [], 0.0, -1
            continue
        adv = p.advances[i]
        if max_width is not None and line and ch != " " and width + adv > max_width + 1e-6:
            if last_break >= 0:
                lines.append(line[: last_break + 1])
                line = line[last_break + 1:]
            else:
                lines.append(line)
                line = []
            width = sum(q.advances[j] for q, j in line)
            last_break = -1
        line.append((p, i))
        width += adv
        if ch in " -–—/":
            last_break = len(line) - 1
    lines.append(line)
    # Regroup characters into pieces per line
    out: list[list[_Piece]] = []
    for ln in lines:
        grouped: list[_Piece] = []
        for p, i in ln:
            if grouped and grouped[-1].face is p.face and grouped[-1].style is p.style and grouped[-1].rise == p.rise \
                    and grouped[-1].synth_italic == p.synth_italic and getattr(grouped[-1], "_src", None) is p:
                g = grouped[-1]
                g.text += p.text[i]
                g.gids.append(p.gids[i])
                g.advances.append(p.advances[i])
            else:
                g = _Piece(p.text[i], p.face, p.synth_italic, p.style, p.size, p.rise, [p.advances[i]], [p.gids[i]])
                g._src = p  # type: ignore[attr-defined]
                grouped.append(g)
        out.append(grouped)
    return out


def _trimmed_width(line: list[_Piece]) -> float:
    """Line width without trailing spaces (they don't count for alignment)."""
    total = sum(sum(p.advances) for p in line)
    for p in reversed(line):
        for ch, adv in zip(reversed(p.text), reversed(p.advances)):
            if ch == " ":
                total -= adv
            else:
                return total
    return total


def layout_text(body: dict, w: float, h: float, index: FontIndex | None = None,
                defaults: dict | None = None) -> TextLayout:
    """Lay out a text body inside a w x h text area (frame coordinates, before insets)."""
    lins, tins, rins, bins = body.get("insets") or DEFAULT_INSETS
    wrap = body.get("wrap", True)
    avail_w = w - lins - rins
    max_width = avail_w if wrap else None
    out = TextLayout()

    blocks = []   # (lines, paragraph) per paragraph
    y = 0.0
    first_line = True
    for para in body.get("paragraphs", []):
        pieces = _pieces(para.get("runs", []), defaults, index)
        if pieces:
            lines = _break_lines(pieces, max_width if max_width is None or max_width > 0 else 0.0)
        else:
            lines = [[]]
        spacing = para.get("line_spacing") or {"pct": 1.0}
        if not first_line:
            y += float(para.get("space_before", 0.0))
        para_lines = []
        for ln in lines:
            if ln:
                heights = [line_height(p.face, p.size / (SCRIPT_SCALE if p.rise else 1.0)) for p in ln]
                big = max(range(len(ln)), key=lambda k: heights[k])
                ref_face, ref_size = ln[big].face, ln[big].size / (SCRIPT_SCALE if ln[big].rise else 1.0)
            else:
                st = run_style({"size": para.get("end_size")} if para.get("end_size") else {}, defaults)
                ref_face, _ = resolve_face(st["font"], bool(st["bold"]), bool(st["italic"]), index)
                ref_size = float(st["size"])
            lh = line_height(ref_face, ref_size)
            if "pts" in spacing:
                box_h = float(spacing["pts"])
            else:
                box_h = lh * float(spacing.get("pct", 1.0))
            baseline = y + first_baseline(ref_face, ref_size, box_h) if "pts" not in spacing else \
                y + box_h - ref_face.descent * ref_size
            para_lines.append((ln, baseline, box_h))
            y += box_h
            first_line = False
        y += float(para.get("space_after", 0.0))
        blocks.append((para_lines, para))

    content_h = y
    out.content_height = content_h
    out.autofit_height = tins + content_h + bins + AUTOFIT_EXTRA
    avail_h = h - tins - bins
    anchor = body.get("anchor", "t")
    if anchor == "ctr":
        y0 = tins + (avail_h - content_h - AUTOFIT_EXTRA) / 2.0
    elif anchor == "b":
        y0 = h - bins - content_h - AUTOFIT_EXTRA
    else:
        y0 = tins
    out.overflow = content_h > avail_h + 0.01

    widest = 0.0
    for para_lines, para in blocks:
        align = para.get("align", "l")
        for ln, baseline, _box_h in para_lines:
            lw = _trimmed_width(ln)
            widest = max(widest, lw)
            if align == "ctr":
                x = lins + (avail_w - lw) / 2.0
            elif align == "r":
                x = w - rins - lw
            else:
                x = lins
            for p in ln:
                st = p.style
                out.runs.append(GlyphRun(
                    face=p.face, size=p.size, color=st.get("color", "#000000"),
                    opacity=float(st.get("opacity", 1.0)), x=x, y=y0 + baseline - p.rise,
                    text=p.text, gids=list(p.gids), advances=list(p.advances),
                    underline=bool(st.get("underline")),
                    skew=SYNTHETIC_ITALIC_SKEW if p.synth_italic else 0.0))
                x += sum(p.advances)
    out.content_width = widest
    out.autofit_width = lins + widest + rins
    return out

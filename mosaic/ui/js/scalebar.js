// Scale bars: a bar showing a real length on a picture with a scale. A picture's scale is
// picture.scale {per_pt, unit, how}: the real length of one point of its own source (a raster's
// pixel size converts to it; how: typed, measured or file). A picture measured also keeps
// picture.measured {line: [[x, y], [x, y]] in its source's points, length, unit}: the line drawn
// and the length typed, to show and start from when it's measured again. A scale bar {picture,
// length, unit, anchor {corner, dx, dy, seen}, rot, gap, ...} keeps its corner at that offset from
// the same corner of its picture (corners of its outline as turned), and its length in step with
// the picture's size and crop: followScaleBars sets its frame whenever anything changes, and the
// engine draws it from the frame. When the picture is as it was last time (seen: its frame and
// crop then), the bar may have been moved on its own, so its offset is measured again; a bar
// moved together with its picture moves once. Its label goes above, below, left or right of the
// bar (or none). Above or below, the frame is as long as the bar; left or right (2026-11-18), the
// frame also holds the gap and the letters, so the bar keeps its length as bar_w (in page points)
// and the letters' width as label_w (as the engine last measured them: canvas.js takes up a new
// width, and the frame makes room keeping its corner, as when the label changes side).

import { apply, frameMatrix, invert } from "./util.js";

// Lengths in metres: metric, then imperial (2026-11-19: inches, feet, yards and miles)
export const METRIC = [["nm", 1e-9], ["µm", 1e-6], ["mm", 1e-3], ["cm", 1e-2], ["m", 1]];
export const IMPERIAL = [["in", 0.0254], ["ft", 0.3048], ["yd", 0.9144], ["mi", 1609.344]];
export const UNITS = [...METRIC, ...IMPERIAL];
// The unit lists' choices, in two groups (selectField)
export const UNIT_CHOICES = [{ group: "Metric", options: METRIC.map(([u]) => [u, u]) },
  { group: "Imperial", options: IMPERIAL.map(([u]) => [u, u]) }];
const metres = (u) => (UNITS.find(([n]) => n === u) || [null, 1e-6])[1];
export const convert = (v, from, to) => (v * metres(from)) / metres(to);
// A length in another unit, exactly (the bar stays the same size): 50 mm is 1.9685039370078743 in,
// and back 50 mm. Kept to full precision, so a round trip comes back as it was, but tidied when
// it's really a short number (1 in is 25.4 mm, not 25.400000000000002)
export function convertLength(v, from, to) {
  const r = convert(v, from, to), tidy = +r.toPrecision(12);
  const digits = String(tidy).replace(/e.*$/, "").replace(/[-.]/g, "").replace(/^0+/, "").replace(/0+$/, "").length;
  return digits <= 9 ? tidy : r;
}
// A unit as typed: "um", "microns", "inches", "feet", ″ and ′ (and " and ') too
const SAID = { um: "µm", micron: "µm", microns: "µm", "µm": "µm", "μm": "µm", nm: "nm", mm: "mm", cm: "cm", m: "m",
  in: "in", inch: "in", inches: "in", '"': "in", "″": "in", ft: "ft", foot: "ft", feet: "ft", "'": "ft", "′": "ft",
  yd: "yd", yard: "yd", yards: "yd", mi: "mi", mile: "mi", miles: "mi" };
// "100 µm", "2 in", 3.5 (a number alone: unit null): {value, unit} or null
export function parseLength(text) {
  const m = /^\s*([0-9]*[.,]?[0-9]+(?:e[-+]?\d+)?)\s*([a-zµμ"'″′]*)\s*$/i.exec(text || "");
  const value = m && parseFloat(m[1].replace(",", "."));
  if (!(value > 0)) return null;
  const said = m[2].toLowerCase();
  if (said && !SAID[said]) return null;
  return { value, unit: said ? SAID[said] : null };
}
const GAP = 0.3, LINE = 1.2;   // label gap and line height, in text sizes (as the engine lays it out)

// Page points per point of the picture's source: its scale on the page
export function pageScale(pic, asset) {
  const [sw] = (asset.page_sizes && asset.page_sizes[pic.page_index || 0]) || asset.size_pt;
  const [l, , r] = pic.crop || [0, 0, 0, 0];
  return pic.frame[2] / Math.max(sw * (1 - l - r), 1e-9);
}
// A raster's pixels per point of its source (null for PDF and SVG, which have no pixels)
export function pxPerPt(asset) {
  const v = asset?.variants?.[asset.primary];
  return v?.px ? v.px[0] / asset.size_pt[0] : null;
}
// "1 pixel = 0.325 µm" (or per point of a PDF or SVG)
export function scaleText(pic, asset) {
  const s = pic.scale, ppp = pxPerPt(asset);
  if (!s?.per_pt) return "no scale";
  return `1 ${ppp ? "pixel" : "point of the original"} = ${+(ppp ? s.per_pt / ppp : s.per_pt).toPrecision(4)} ${s.unit}`;
}
// Whether a bar's label is beside it (left or right) rather than above or below
export const beside = (bar) => bar.label === "left" || bar.label === "right";
// The text a bar shows, "50 µm" (as the engine writes it), and a first guess at its letters' width
const labelText = (bar) => `${+Number(bar.length ?? 1).toPrecision(6)} ${bar.unit ?? "µm"}`;
const guessWidth = (bar) => (bar.size ?? 6) * 0.55 * labelText(bar).length;
// From the bar to the letters beside it: the gap set, or 0.3 text sizes
const sideGap = (bar) => (bar.gap == null ? (bar.size ?? 6) * GAP : Math.max(bar.gap, 0));
// The bar and its label's room: with a gap set (in pt, to the letters), the gap and a line of
// text; without one, as before gaps could be set, a line of text 0.3 text sizes from the bar.
// Beside the bar: a line of text, or the bar if it's thicker
export function barHeight(bar) {
  if (bar.label === "none") return bar.thickness ?? 2;
  const size = bar.size ?? 6;
  if (beside(bar)) return Math.max(bar.thickness ?? 2, size * LINE);
  return (bar.thickness ?? 2) + (bar.gap == null ? size * (GAP + LINE) : Math.max(bar.gap, 0) + size * LINE);
}
// The bar's own length on the page: as kept (bar_w) while its label is beside it, or the frame's
// length. A bar beside its label without one has just come from above or below, its frame as long
// as the bar; one above or below with one has just come from beside it
export const barLength = (bar) => bar.bar_w ?? bar.frame[2];
// The frame's size for a bar `len` long: with its label beside it, the bar, the gap and the letters
export function barSize(bar, len) {
  return [beside(bar) ? len + sideGap(bar) + (bar.label_w ?? guessWidth(bar)) : len, barHeight(bar)];
}
// Keep a bar beside its label ready for its frame: its length, and its letters' width (a guess
// until the engine measures them); a bar above or below has neither
function keepSizes(bar, len) {
  if (beside(bar)) {
    bar.bar_w = len;
    if (bar.label_w == null) bar.label_w = guessWidth(bar);
  } else {
    delete bar.bar_w;
    delete bar.label_w;
  }
}
// The outline a box makes on the page turned by `rot` about its middle: [x0, y0, x1, y1]
function turnedBox([x, y, w, h], rot) {
  const pts = [[0, 0], [w, 0], [w, h], [0, h]].map(([u, v]) => apply(frameMatrix([x, y, w, h], rot || 0), u, v));
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
// The bar's length on the page from its picture's scale (a picture without one: as it is)
export function lengthOn(bar, pic, asset) {
  const s = pic.scale;
  return s?.per_pt ? (convert(bar.length, bar.unit, s.unit) / s.per_pt) * pageScale(pic, asset) : barLength(bar);
}
// The bar's frame: its length from the picture's scale, the corner of its outline (as turned) at
// the anchor's offset from that corner of the picture
export function barFrame(bar, pic, asset, len = lengthOn(bar, pic, asset)) {
  const [w, h] = barSize(bar, len), [px, py, pw, ph] = pic.frame;
  const { corner = "br", dx = 0, dy = 0 } = bar.anchor || {};
  if (!(bar.rot % 360)) {
    const x = (corner.includes("r") ? px + pw - w : px) + dx, y = (corner.includes("b") ? py + ph - h : py) + dy;
    return [x, y, w, h];
  }
  const [x0, y0, x1, y1] = turnedBox([0, 0, w, h], bar.rot), [bw, bh] = [x1 - x0, y1 - y0];
  const bx = (corner.includes("r") ? px + pw - bw : px) + dx, by = (corner.includes("b") ? py + ph - bh : py) + dy;
  return [bx + bw / 2 - w / 2, by + bh / 2 - h / 2, w, h];
}
// The anchor that keeps a bar where it is when it goes with another corner of its picture
export function anchorFor(bar, pic, corner) {
  const [x0, y0, x1, y1] = turnedBox(bar.frame, bar.rot), [px, py, pw, ph] = pic.frame;
  return { corner, dx: x0 - (corner.includes("r") ? px + pw - (x1 - x0) : px), dy: y0 - (corner.includes("b") ? py + ph - (y1 - y0) : py) };
}
// Where the bar itself is in its frame: its middle (beside its label, along the far side)
function barMiddleIn(bar) {
  const [, , w, h] = bar.frame, t = bar.thickness ?? 2;
  if (beside(bar)) {
    const len = barLength(bar);
    return [bar.label === "right" ? len / 2 : w - len / 2, h / 2];
  }
  return [w / 2, bar.label === "above" ? h - t / 2 : t / 2];
}
// ... and on the page
const barMiddle = (bar) => apply(frameMatrix(bar.frame, bar.rot || 0), ...barMiddleIn(bar));
// A change to a bar's label (its gap) that keeps the bar where it is: the label moves, not the bar
export function keepBar(bar, fn) {
  const was = barMiddle(bar), len = barLength(bar);
  fn(bar);
  keepSizes(bar, len);
  bar.frame = [bar.frame[0], bar.frame[1], ...barSize(bar, len)];
  const now = barMiddle(bar);
  bar.frame = [bar.frame[0] + was[0] - now[0], bar.frame[1] + was[1] - now[1], bar.frame[2], bar.frame[3]];
}
// A bar's frame at another size, the corner of its outline (as turned) where it was
function resizeAt(bar, [w, h], corner = "br") {
  const [x0, y0, x1, y1] = turnedBox(bar.frame, bar.rot), [b0, c0, b1, c1] = turnedBox([0, 0, w, h], bar.rot);
  const [bw, bh] = [b1 - b0, c1 - c0];
  const bx = corner.includes("r") ? x1 - bw : x0, by = corner.includes("b") ? y1 - bh : y0;
  bar.frame = [bx + bw / 2 - w / 2, by + bh / 2 - h / 2, w, h];
}
// The label to another side (above, below, left, right or none): the bar keeps its length, and
// the frame its corner (the one it stays with on its picture), the bar moving over to make room
export function setLabelSide(bar, side) {
  const len = barLength(bar);
  bar.label = side;
  keepSizes(bar, len);
  resizeAt(bar, barSize(bar, len), bar.anchor?.corner);
}
// The bar's text gap, in frame coordinates: the bar's edge or end facing its label, and the way
// from it to the label ({y, dir: -1} above, {y, dir: 1} below, {x, dir: -1} left, {x, dir: 1} right)
export function gapEdge(bar) {
  const t = bar.thickness ?? 2, [, , w, h] = bar.frame;
  if (beside(bar)) return bar.label === "right" ? { x: barLength(bar), dir: 1 } : { x: w - barLength(bar), dir: -1 };
  return bar.label === "above" ? { y: h - t, dir: -1 } : { y: t, dir: 1 };
}
// Where the gap handle sits for a gap set, in frame coordinates: that far from the bar, halfway
// along it (above or below) or level with it (beside)
export function gapHandleAt(bar) {
  const e = gapEdge(bar), g = Math.max(bar.gap ?? 0, 0);
  return e.x !== undefined ? [e.x + e.dir * g, bar.frame[3] / 2] : [bar.frame[2] / 2, e.y + e.dir * g];
}
// A point of a picture's source (its points, uncropped) on the page, and back
function sourceMatrix(pic, asset) {
  const [sw, sh] = (asset.page_sizes && asset.page_sizes[pic.page_index || 0]) || asset.size_pt;
  const [l, t, r, b] = pic.crop || [0, 0, 0, 0], [, , w, h] = pic.frame;
  const sx = w / Math.max(sw * (1 - l - r), 1e-9), sy = h / Math.max(sh * (1 - t - b), 1e-9);
  const m = frameMatrix(pic.frame, pic.rot || 0, pic.flip_h, pic.flip_v);
  return [m[0] * sx, m[1] * sx, m[2] * sy, m[3] * sy, m[4] - (m[0] * sx * l * sw + m[2] * sy * t * sh), m[5] - (m[1] * sx * l * sw + m[3] * sy * t * sh)];
}
export const sourceToPage = (pic, asset, p) => apply(sourceMatrix(pic, asset), ...p);
export const pageToSource = (pic, asset, p) => apply(invert(sourceMatrix(pic, asset)), ...p);
// "100 µm": a measured length as typed
export const measuredText = (m) => `${+Number(m.length).toPrecision(6)} ${m.unit}`;
// A round length about a fifth of the picture's width: 1, 2 or 5 times a power of ten
export function niceLength(pic, asset, unit) {
  const across = convert((pic.frame[2] / pageScale(pic, asset)) * pic.scale.per_pt, pic.scale.unit, unit);
  const target = across / 5, p = 10 ** Math.floor(Math.log10(target));
  return [5, 2, 1].map((k) => k * p).find((v) => v <= target + 1e-12) || p;
}

// Drawing a bar (2026-11-19) ----------------------------------------------------------------
// The Scale bar tool: a drag across a picture draws a bar from where it starts. Level, or upright
// when the drag goes more up or down than across (free, Shift: at the drag's own angle); a round
// length (exact, ⌘: the length dragged, to 3 significant figures)

// A round length near v: 1, 2, 2.5 or 5 times a power of ten (2.5: 25 µm, a quarter inch)
export function roundLength(v) {
  if (!(v > 0)) return 0;
  const p = 10 ** Math.floor(Math.log10(v));
  const best = [1, 2, 2.5, 5, 10].map((k) => k * p).reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a));
  return +best.toPrecision(12);
}
// Which way a bar drawn from a to b points (dir: degrees clockwise from rightwards), and how its
// text turns (rot): level text, or reading upwards on an upright bar; at an angle, never upside down
export function drawnDirection(a, b, free = false) {
  const dx = b[0] - a[0], dy = b[1] - a[1], norm = (v) => ((v % 360) + 360) % 360;
  if (!free) {
    const level = Math.abs(dx) >= Math.abs(dy);
    return { dir: level ? (dx < 0 ? 180 : 0) : (dy < 0 ? 270 : 90), rot: level ? 0 : 270 };
  }
  const dir = norm((Math.atan2(dy, dx) * 180) / Math.PI), c = Math.cos((dir * Math.PI) / 180);
  return { dir, rot: norm(Math.abs(c) < 1e-6 ? 270 : c > 0 ? dir : dir + 180) };
}
// A drag from a to b on a picture with a scale, as a bar: its direction and turn, its length and
// unit (the picture's), and where it ends on the page; null for a picture without a scale
export function barPreview(pic, asset, a, b, { free = false, exact = false } = {}) {
  const s = pic?.scale;
  if (!s?.per_pt || !asset) return null;
  const { dir, rot } = drawnDirection(a, b, free), r = (dir * Math.PI) / 180;
  const along = Math.abs((b[0] - a[0]) * Math.cos(r) + (b[1] - a[1]) * Math.sin(r));
  const real = (along / pageScale(pic, asset)) * s.per_pt;   // (in the picture's unit)
  const length = exact ? +real.toPrecision(3) : roundLength(real);
  const onPage = (length / s.per_pt) * pageScale(pic, asset);
  return { dir, rot, length, unit: s.unit, end: [a[0] + Math.cos(r) * onPage, a[1] + Math.sin(r) * onPage] };
}
// A new bar (base: its length, unit and look) on a picture with a scale, starting at `start` and
// pointing `dir`, its text turned `rot`; it stays with the corner of the picture nearest it
export function drawnBar(base, pic, asset, start, dir, rot) {
  const bar = { ...base, rot, frame: [0, 0, 1, 1] };
  const len = lengthOn(bar, pic, asset);
  keepSizes(bar, len);
  const [w, h] = barSize(bar, len);
  bar.frame = [0, 0, w, h];
  const r = (dir * Math.PI) / 180, mid = [start[0] + (Math.cos(r) * len) / 2, start[1] + (Math.sin(r) * len) / 2];
  const now = barMiddle(bar);
  bar.frame = [mid[0] - now[0], mid[1] - now[1], w, h];
  const [px, py, pw, ph] = pic.frame;
  bar.anchor = anchorFor(bar, pic, `${mid[1] > py + ph / 2 ? "b" : "t"}${mid[0] > px + pw / 2 ? "r" : "l"}`);
  return bar;
}

// Every scale bar on the page follows its picture (one with no picture left stays where it is,
// its frame only making room for a label beside it or no longer beside it, keeping its corner)
export function followScaleBars(items, assets) {
  const all = [], walk = (its) => its.forEach((it) => { if (it.type === "group") walk(it.items); all.push(it); });
  walk(items);
  for (const bar of all.filter((it) => it.type === "scalebar")) {
    const pic = all.find((it) => it.id === bar.picture && it.type === "picture");
    const asset = pic && assets[pic.asset];
    if (!asset) {
      if (beside(bar) || bar.bar_w != null) {
        const len = barLength(bar);
        keepSizes(bar, len);
        const size = barSize(bar, len);
        if (size.some((v, i) => Math.abs(v - bar.frame[i + 2]) > 1e-9)) resizeAt(bar, size, bar.anchor?.corner);
      }
      continue;
    }
    const geom = [...pic.frame, ...(pic.crop || [0, 0, 0, 0])], seen = bar.anchor?.seen;
    if (!seen || geom.every((v, i) => Math.abs(v - seen[i]) <= 1e-9)) bar.anchor = anchorFor(bar, pic, bar.anchor?.corner || "br");
    bar.anchor.seen = geom;
    const len = lengthOn(bar, pic, asset);
    keepSizes(bar, len);
    const f = barFrame(bar, pic, asset, len);
    if (f.some((v, i) => Math.abs(v - bar.frame[i]) > 1e-9)) bar.frame = f;
  }
}

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
// moved together with its picture moves once.

import { apply, frameMatrix, invert } from "./util.js";

export const UNITS = [["nm", 1e-9], ["µm", 1e-6], ["mm", 1e-3], ["cm", 1e-2], ["m", 1]];
const metres = (u) => (UNITS.find(([n]) => n === u) || [null, 1e-6])[1];
export const convert = (v, from, to) => (v * metres(from)) / metres(to);
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
// The bar and its label's room: with a gap set (in pt, to the letters), the gap and a line of
// text; without one, as before gaps could be set, a line of text 0.3 text sizes from the bar
export function barHeight(bar) {
  if (bar.label === "none") return bar.thickness ?? 2;
  const size = bar.size ?? 6;
  return (bar.thickness ?? 2) + (bar.gap == null ? size * (GAP + LINE) : Math.max(bar.gap, 0) + size * LINE);
}
// The outline a box makes on the page turned by `rot` about its middle: [x0, y0, x1, y1]
function turnedBox([x, y, w, h], rot) {
  const pts = [[0, 0], [w, 0], [w, h], [0, h]].map(([u, v]) => apply(frameMatrix([x, y, w, h], rot || 0), u, v));
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
// The bar's frame: its length from the picture's scale, the corner of its outline (as turned) at
// the anchor's offset from that corner of the picture
export function barFrame(bar, pic, asset) {
  const s = pic.scale;
  const w = s?.per_pt ? (convert(bar.length, bar.unit, s.unit) / s.per_pt) * pageScale(pic, asset) : bar.frame[2];
  const h = barHeight(bar), [px, py, pw, ph] = pic.frame;
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
// Where the bar itself is: its middle, on the page
function barMiddle(bar) {
  const [, , w, h] = bar.frame, t = bar.thickness ?? 2;
  return apply(frameMatrix(bar.frame, bar.rot || 0), w / 2, bar.label === "above" ? h - t / 2 : t / 2);
}
// A change to a bar's label (its gap) that keeps the bar where it is: the label moves, not the bar
export function keepBar(bar, fn) {
  const was = barMiddle(bar);
  fn(bar);
  bar.frame = [bar.frame[0], bar.frame[1], bar.frame[2], barHeight(bar)];
  const now = barMiddle(bar);
  bar.frame = [bar.frame[0] + was[0] - now[0], bar.frame[1] + was[1] - now[1], bar.frame[2], bar.frame[3]];
}
// The bar's text gap, in frame coordinates: the bar's edge facing its label, and the way from it
// to the label ([0, -1] above, [0, 1] below)
export function gapEdge(bar) {
  const t = bar.thickness ?? 2, h = bar.frame[3];
  return bar.label === "above" ? { y: h - t, dir: -1 } : { y: t, dir: 1 };
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
// Every scale bar on the page follows its picture (one with no picture left stays where it is)
export function followScaleBars(items, assets) {
  const all = [], walk = (its) => its.forEach((it) => { if (it.type === "group") walk(it.items); all.push(it); });
  walk(items);
  for (const bar of all.filter((it) => it.type === "scalebar")) {
    const pic = all.find((it) => it.id === bar.picture && it.type === "picture");
    const asset = pic && assets[pic.asset];
    if (!asset) continue;
    const geom = [...pic.frame, ...(pic.crop || [0, 0, 0, 0])], seen = bar.anchor?.seen;
    if (!seen || geom.every((v, i) => Math.abs(v - seen[i]) <= 1e-9)) bar.anchor = anchorFor(bar, pic, bar.anchor?.corner || "br");
    bar.anchor.seen = geom;
    const f = barFrame(bar, pic, asset);
    if (f.some((v, i) => Math.abs(v - bar.frame[i]) > 1e-9)) bar.frame = f;
  }
}

// Scale bars: a bar showing a real length on a picture with a scale. A picture's scale is
// picture.scale {per_pt, unit, how}: the real length of one point of its own source (a raster's
// pixel size converts to it; how: typed, measured or file). A scale bar {picture, length, unit,
// anchor {corner, dx, dy}, ...} keeps its corner at that offset from the same corner of its
// picture, and its length in step with the picture's size and crop: followScaleBars sets its frame
// whenever anything changes, and the engine draws it from the frame.

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
export function barHeight(bar) {
  return (bar.thickness ?? 2) + (bar.label === "none" ? 0 : (bar.size ?? 6) * (GAP + LINE));
}
// The bar's frame: its length from the picture's scale, its corner at the anchor's offset
export function barFrame(bar, pic, asset) {
  const s = pic.scale;
  const w = s?.per_pt ? (convert(bar.length, bar.unit, s.unit) / s.per_pt) * pageScale(pic, asset) : bar.frame[2];
  const h = barHeight(bar), [px, py, pw, ph] = pic.frame;
  const { corner = "br", dx = 0, dy = 0 } = bar.anchor || {};
  const x = (corner.includes("r") ? px + pw - w : px) + dx, y = (corner.includes("b") ? py + ph - h : py) + dy;
  return [x, y, w, h];
}
// The anchor that keeps a bar where it is when it goes with another corner of its picture
export function anchorFor(bar, pic, corner) {
  const [x, y, w, h] = bar.frame, [px, py, pw, ph] = pic.frame;
  return { corner, dx: x - (corner.includes("r") ? px + pw - w : px), dy: y - (corner.includes("b") ? py + ph - h : py) };
}
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
    const f = barFrame(bar, pic, asset);
    if (f.some((v, i) => Math.abs(v - bar.frame[i]) > 1e-9)) bar.frame = f;
  }
}

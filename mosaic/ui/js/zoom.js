// Zoom insets: a box on a picture (a shape with zoom {picture, seen, circle, own_shapes}), an
// inset showing that area enlarged (a copy of the picture with inset {box}) and two lines joining
// them (zoomline {box, inset, which}). followZooms keeps them in step after every change:
// - the box stays over the same part of its picture when the picture moves, resizes or is
//   cropped (seen: the picture's frame and crop when last looked at), and stays put otherwise;
// - the inset shows whatever is in the box: its crop follows the box, its height the box's shape;
// - the inset is cropped to the box's shape (rectangle, rounded rectangle, ellipse or circle)
//   unless own_shapes says each has its own; a circle's box stays square;
// - the lines run along the outside of the callout, touching both shapes: between corners for
//   rectangles, or touching their rounded corners or ellipses.

export const ZOOM_ROUNDING = 0.2;   // a rounded rectangle's corner rounding to start with (20%)
// The shapes, for the Zoom inset button's menu and the panel's Shape list: [command, shape, name]
export const ZOOM_SHAPES = [["zoomInset", "rect", "Rectangle"], ["zoomInsetRound", "round", "Rounded rectangle"],
  ["zoomInsetEllipse", "ellipse", "Ellipse"], ["zoomInsetCircle", "circle", "Circle"]];

const flat = (items, out = []) => {
  for (const it of items) {
    out.push(it);
    if (it.type === "group") flat(it.items, out);
  }
  return out;
};
const sourceSize = (pic, asset) => (asset.page_sizes && asset.page_sizes[pic.page_index || 0]) || asset.size_pt;

// A page rectangle on a picture as a rectangle of its source (points), and back, for the
// picture's frame and crop in geom [x, y, w, h, l, t, r, b] (its turn isn't counted)
function toSource([px, py, pw, ph], geom, [sw, sh]) {
  const [x, y, w, h, l, t, r, b] = geom, vw = sw * (1 - l - r), vh = sh * (1 - t - b);
  const sx = (v) => l * sw + ((v - x) / w) * vw, sy = (v) => t * sh + ((v - y) / h) * vh;
  return [sx(px), sy(py), sx(px + pw), sy(py + ph)];
}
function fromSource([x0, y0, x1, y1], geom, [sw, sh]) {
  const [x, y, w, h, l, t, r, b] = geom, vw = sw * (1 - l - r), vh = sh * (1 - t - b);
  const px = (v) => x + ((v - l * sw) / vw) * w, py = (v) => y + ((v - t * sh) / vh) * h;
  return [px(x0), py(y0), px(x1) - px(x0), py(y1) - py(y0)];
}
const geomOf = (pic) => [...pic.frame, ...(pic.crop || [0, 0, 0, 0])];
const corners = ([x, y, w, h]) => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];

// The two corner pairs (same corner of box and inset) whose lines are on the outside: edges of
// the convex hull of all eight corners
export function calloutCorners(box, inset) {
  const pts = [...corners(box).map((p, k) => ({ p, k, of: "b" })), ...corners(inset).map((p, k) => ({ p, k, of: "i" }))]
    .sort((a, b) => a.p[0] - b.p[0] || a.p[1] - b.p[1]);
  const cross = (o, a, b) => (a.p[0] - o.p[0]) * (b.p[1] - o.p[1]) - (a.p[1] - o.p[1]) * (b.p[0] - o.p[0]);
  const half = (list) => {
    const h = [];
    for (const q of list) {
      while (h.length >= 2 && cross(h[h.length - 2], h[h.length - 1], q) <= 0) h.pop();
      h.push(q);
    }
    return h.slice(0, -1);
  };
  const hull = [...half(pts), ...half([...pts].reverse())];
  const found = [];
  hull.forEach((a, i) => {
    const b = hull[(i + 1) % hull.length];
    if (a.k === b.k && a.of !== b.of && !found.includes(a.k)) found.push(a.k);
  });
  return found.length >= 2 ? found.slice(0, 2) : [0, 2];
}

// A zoom box's shape, or an inset's: "rect", "round" (rounded corners), "ellipse" or "circle";
// "other" for a box given another shape in the Style tab
export function zoomShape(it) {
  if (it.zoom) {
    if (it.geom === "ellipse") return it.zoom.circle ? "circle" : "ellipse";
    if (it.geom === "rect") return it.rounding > 0 ? "round" : "rect";
    return "other";
  }
  const mk = it.mask;
  if (!mk) return "rect";
  if (mk.geom === "ellipse") return "ellipse";
  return mk.geom === "rect" ? (mk.rounding > 0 ? "round" : "rect") : "other";
}
// The crop to a shape that makes an inset the box's shape (none for a plain rectangle)
export function insetMask(box) {
  if (box.geom === "rect" && !(box.rounding > 0)) return null;
  return { geom: box.geom, ...(box.adj ? { adj: box.adj } : {}), ...(box.rounding > 0 ? { rounding: box.rounding } : {}) };
}

// A shape's outline for its lines: its corners, or points round its rounded corners or ellipse,
// close enough together that a line through two of them strays from the curve by under 0.01 pt
function outline([x, y, w, h], shape, rounding = 0) {
  if (shape === "ellipse" || shape === "circle") {
    return Array.from({ length: 720 }, (_, i) => [x + (w / 2) * (1 + Math.cos(i * Math.PI / 360)), y + (h / 2) * (1 + Math.sin(i * Math.PI / 360))]);
  }
  const r = shape === "round" ? (rounding * Math.min(w, h)) / 2 : 0;   // (as the engine rounds corners)
  if (!(r > 0)) return corners([x, y, w, h]);
  return [[x + w - r, y + r, -90], [x + w - r, y + h - r, 0], [x + r, y + h - r, 90], [x + r, y + r, 180]].flatMap(([cx, cy, a0]) =>
    Array.from({ length: 65 }, (_, k) => [cx + r * Math.cos((a0 + (90 * k) / 64) * Math.PI / 180), cy + r * Math.sin((a0 + (90 * k) / 64) * Math.PI / 180)]));
}
// The two lines along the outside of a box and an inset of any of the shapes: the edges of the
// convex hull of both outlines that go from one to the other, each [on the box, on the inset]
export function calloutLines(box, inset) {
  const [bs, is] = [zoomShape(box), zoomShape(inset)];
  if (bs !== "round" && bs !== "ellipse" && bs !== "circle" && is !== "round" && is !== "ellipse") {
    return calloutCorners(box.frame, inset.frame).map((k) => [corners(box.frame)[k], corners(inset.frame)[k]]);
  }
  const pts = [...outline(box.frame, bs, box.rounding).map((p) => ({ p, of: "b" })),
    ...outline(inset.frame, is, inset.mask?.rounding).map((p) => ({ p, of: "i" }))].sort((a, b) => a.p[0] - b.p[0] || a.p[1] - b.p[1]);
  const cross = (o, a, b) => (a.p[0] - o.p[0]) * (b.p[1] - o.p[1]) - (a.p[1] - o.p[1]) * (b.p[0] - o.p[0]);
  const half = (list) => {
    const h = [];
    for (const q of list) {
      while (h.length >= 2 && cross(h[h.length - 2], h[h.length - 1], q) <= 0) h.pop();
      h.push(q);
    }
    return h.slice(0, -1);
  };
  const hull = [...half(pts), ...half([...pts].reverse())];
  const found = [];
  hull.forEach((a, i) => {
    const b = hull[(i + 1) % hull.length];
    if (a.of !== b.of) found.push(a.of === "b" ? [a.p, b.p] : [b.p, a.p]);
  });
  if (found.length >= 2) return found.slice(0, 2);
  return [0, 2].map((k) => [corners(box.frame)[k], corners(inset.frame)[k]]);   // (one inside the other)
}

export function followZooms(items, assets) {
  const all = flat(items), byId = new Map(all.map((it) => [it.id, it]));
  for (const box of all.filter((it) => it.zoom && it.frame)) {
    const pic = byId.get(box.zoom.picture), asset = pic?.type === "picture" && assets[pic.asset];
    if (!asset) continue;
    const geom = geomOf(pic), seen = box.zoom.seen;
    if (seen && geom.some((v, i) => Math.abs(v - seen[i]) > 1e-9)) {
      box.frame = fromSource(toSource(box.frame, seen, sourceSize(pic, asset)), geom, sourceSize(pic, asset));
    }
    box.zoom.seen = geom;
    if (box.zoom.circle && Math.abs(box.frame[2] - box.frame[3]) > 1e-9) box.frame[3] = box.frame[2];   // (resized another way)
  }
  for (const inset of all.filter((it) => it.inset && it.type === "picture")) {
    const box = byId.get(inset.inset.box), pic = box?.zoom && byId.get(box.zoom.picture), asset = pic && assets[pic.asset];
    if (!asset || !(box.frame[2] > 0) || !(box.frame[3] > 0)) continue;
    const [sw, sh] = sourceSize(pic, asset), [x0, y0, x1, y1] = toSource(box.frame, geomOf(pic), [sw, sh]);
    const clamp = (v) => Math.min(Math.max(v, 0), 1);
    inset.asset = pic.asset;
    inset.page_index = pic.page_index || 0;
    inset.crop = [clamp(x0 / sw), clamp(y0 / sh), clamp(1 - x1 / sw), clamp(1 - y1 / sh)];
    inset.frame = [inset.frame[0], inset.frame[1], inset.frame[2], (inset.frame[2] * box.frame[3]) / box.frame[2]];
    if (!box.zoom.own_shapes) {
      const mask = insetMask(box);
      if (mask) inset.mask = mask;
      else delete inset.mask;
    }
  }
  for (const line of all.filter((it) => it.zoomline && it.type === "line")) {
    const box = byId.get(line.zoomline.box), inset = byId.get(line.zoomline.inset);
    if (!box?.frame || !inset?.frame) continue;
    line.points = calloutLines(box, inset)[line.zoomline.which || 0];
  }
}

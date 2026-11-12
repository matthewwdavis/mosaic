// Crops besides dragging the edges (canvas.startCrop): to an aspect ratio, to a typed width or
// height, and to a shape drawn over the picture; and the Crop menu (Figure tab, right-click) that
// offers them with Crop to shape. A crop never rescales a picture: it keeps its scale and stays
// where it lies on the page, and its frame shrinks to the part that shows (canvas.cropped)
import { rpc } from "./api.js";
import { canvas, findDeep } from "./canvas.js";
import { store } from "./store.js";
import { shapePicture } from "./pictures.js";
import { announce, apply, clamp, frameMatrix, invert, pathIcon, shapeCatalog, shapeName } from "./util.js";

// PowerPoint's Crop ▸ Aspect Ratio list, width to height
export const RATIOS = [
  ["Square", [[1, 1]]],
  ["Portrait", [[2, 3], [3, 4], [3, 5], [4, 5], [9, 16]]],
  ["Landscape", [[3, 2], [4, 3], [5, 3], [5, 4], [16, 9], [16, 10]]],
];

const tidy = (v) => (Math.abs(v) < 1e-9 ? 0 : v);

// A window uw × vh (the file's points) as near the middle (cu, cv) as the picture allows, as a
// crop [l, t, r, b]
function windowAt(sw, sh, cu, cv, uw, vh) {
  uw = Math.min(uw, sw);
  vh = Math.min(vh, sh);
  const u0 = clamp(cu - uw / 2, 0, sw - uw), v0 = clamp(cv - vh / 2, 0, sh - vh);
  return [u0 / sw, v0 / sh, 1 - (u0 + uw) / sw, 1 - (v0 + vh) / sh].map(tidy);
}
// The middle of what shows now, in the file's points
function middle(it, sw, sh) {
  const [l, t, r, b] = it.crop || [0, 0, 0, 0];
  return [sw * (l + (1 - l - r) / 2), sh * (t + (1 - t - b) / 2)];
}
function setCrop(label, id, crop, more = null) {
  store.update(label, (doc) => {
    const o = findDeep(doc.pages[store.pageIndex].items, id);
    if (!o) return;
    Object.assign(o, canvas.cropped(o, crop));
    more?.(o, doc);
  });
}
const picture = (id) => {
  const it = id && store.item(id);
  return it?.type === "picture" ? it : null;
};
export const selectedPicture = () => {
  const sel = store.selected();
  return sel.length === 1 && sel[0].type === "picture" ? sel[0] : null;
};

// The largest window of that shape the picture holds, about the middle of what shows now; then
// crop mode, with corners keeping the ratio
export function cropToRatio(id, rw, rh) {
  const it = picture(id);
  if (!it) { announce("Select a picture to crop"); return; }
  if (!(rw > 0 && rh > 0)) return;
  const ratio = rw / rh, name = `${+rw.toFixed(3)}:${+rh.toFixed(3)}`;
  const { sw, sh, scx, scy } = canvas.fullFrame(it);
  const W = sw * scx, H = sh * scy;
  const [pw, ph] = W / H > ratio ? [H * ratio, H] : [W, W / ratio];
  setCrop(`Crop to ${name}`, id, windowAt(sw, sh, ...middle(it, sw, sh), pw / scx, ph / scy));
  canvas.startCrop(id, { ratio, ratioName: name });
  announce(`Cropped to ${name}. Drag a corner to crop and keep it, a side or Shift to crop freely; Enter when done.`);
}
// A typed ratio: "7:5", "7/5", "7 x 5" or "1.4"
export function parseRatio(text) {
  const m = String(text || "").trim().match(/^(\d*\.?\d+)\s*(?:[:/x×]\s*(\d*\.?\d+))?$/i);
  if (!m) return null;
  const a = parseFloat(m[1]), b = m[2] === undefined ? 1 : parseFloat(m[2]);
  return a > 0 && b > 0 ? [a, b] : null;
}

// A typed width (i 2) or height (i 3) for what shows, in points: cropped equally from both sides
// (or uncropped), keeping the picture's scale; at an edge of the picture, the rest from the other
export function cropToSize(id, i, want) {
  const it = picture(id);
  if (!it || !(want > 0)) return;
  const { sw, sh, scx, scy } = canvas.fullFrame(it);
  const [l, t, r, b] = it.crop || [0, 0, 0, 0];
  let uw = sw * (1 - l - r), vh = sh * (1 - t - b);
  const full = i === 2 ? sw * scx : sh * scy;
  if (i === 2) uw = clamp(want / scx, 2 / scx, sw);
  else vh = clamp(want / scy, 2 / scy, sh);
  setCrop("Crop", id, windowAt(sw, sh, ...middle(it, sw, sh), uw, vh));
  if (want > full + 1e-6) announce(`The whole picture is only ${i === 2 ? "that wide" : "that high"}: uncropped that way`);
}

// The whole file again, at the same scale, its top-left corner where it is
export function resetCrop(id) {
  const it = picture(id);
  if (!it) { announce("Select a picture"); return; }
  const a = store.doc.assets[it.asset];
  const [sw, sh] = (a.page_sizes && a.page_sizes[it.page_index || 0]) || a.size_pt;
  store.update("Reset crop", (doc) => {
    const o = findDeep(doc.pages[store.pageIndex].items, id);
    if (!o) return;
    const sc = o.frame[2] / (sw * (1 - o.crop[0] - o.crop[2]));
    o.crop = [0, 0, 0, 0];
    o.frame[2] = sw * sc;
    o.frame[3] = sh * sc;
  });
}

// Crop to shape (PowerPoint's): a shape fitted to the frame, or none
export function cropToShape(id, geom) {
  if (!picture(id)) { announce("Select a picture"); return; }
  store.update(geom ? "Crop to shape" : "No shape crop", (doc) => {
    const o = findDeep(doc.pages[store.pageIndex].items, id);
    if (!o) return;
    if (geom) o.mask = { geom };
    else delete o.mask;
  });
}

// A picture and one shape, both selected: the shape to crop the picture to (or why not)
export function drawnPair() {
  const sel = store.selected();
  const pics = sel.filter((it) => it.type === "picture"), shapes = sel.filter((it) => it.type === "shape" && it.geom !== "region");
  if (sel.length !== 2 || pics.length !== 1 || shapes.length !== 1) return { why: "select a picture and a shape drawn over it" };
  if (pics[0].inset) return { why: "a zoom inset takes its shape from its box" };
  return { pic: pics[0], shape: shapes[0] };
}
const sameTurn = (a, b) => Math.abs((((a || 0) - (b || 0)) % 360 + 540) % 360 - 180) < 1e-6;

// Crop to shape drawn over it: the picture shows only inside the shape, where the two overlap,
// and the shape is used up (its line, if any, the picture's border). A preset shape square to the
// picture and wholly over it becomes the picture's own crop shape, adjustments and all; any other
// (turned, freeform, or reaching past the picture) its outline as it lies
export async function cropToDrawnShape() {
  const { pic, shape, why } = drawnPair();
  if (!pic) { announce(why[0].toUpperCase() + why.slice(1)); return; }
  const { m, sw, sh, scx, scy } = canvas.fullFrame(pic);
  const toSource = invert(m);   // (the page into the file's points)
  const out = await rpc("outline_in", shape, toSource);
  if (!out) { announce("That shape has no inside to crop to"); return; }
  let [u0, v0, u1, v1] = out.bbox;
  u0 = Math.max(u0, 0); v0 = Math.max(v0, 0); u1 = Math.min(u1, sw); v1 = Math.min(v1, sh);
  if (u1 - u0 < 1e-3 || v1 - v0 < 1e-3) { announce("The shape isn't over the picture"); return; }
  let mask = null;
  if (shape.geom !== "custom" && sameTurn(shape.rot, pic.rot) && !!shape.flip_h === !!pic.flip_h && !!shape.flip_v === !!pic.flip_v) {
    // Its frame's corners in the file's points: a rectangle, as the two are square to each other
    const [, , w, hh] = shape.frame, fm = frameMatrix(shape.frame, shape.rot || 0, shape.flip_h, shape.flip_v);
    const pts = [[0, 0], [w, 0], [0, hh], [w, hh]].map(([px, py]) => apply(toSource, ...apply(fm, px, py)));
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const box = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)], e = 1e-6 * Math.max(sw, sh);
    if (box[0] >= -e && box[1] >= -e && box[2] <= sw + e && box[3] <= sh + e) {
      [u0, v0, u1, v1] = [Math.max(box[0], 0), Math.max(box[1], 0), Math.min(box[2], sw), Math.min(box[3], sh)];
      mask = { geom: shape.geom };
      if (shape.adj && Object.keys(shape.adj).length) mask.adj = { ...shape.adj };
      if (shape.rounding) mask.rounding = shape.rounding;
    }
  }
  if (!mask) {
    // The outline in the new frame's own points (the frame's size goes with it, so it stretches
    // with the frame as a preset shape does)
    const fw = (u1 - u0) * scx, fh = (v1 - v0) * scy;
    const local = (seg) => [seg[0], ...seg.slice(1).map((v, k) => (k % 2 === 0 ? (v - u0) * scx : (v - v0) * scy))];
    mask = { geom: "custom", path: { subpaths: out.subpaths.map((cmds) => ({ w: fw, h: fh, cmds: cmds.map(local) })) } };
    if (out.even_odd) mask.even_odd = true;
  }
  const crop = [u0 / sw, v0 / sh, 1 - u1 / sw, 1 - v1 / sh].map(tidy);
  const line = shape.stroke && shape.stroke.width > 0 && shape.stroke.color && shape.stroke.color !== "none" ? shape.stroke : null;
  store.update("Crop to shape", (doc) => {
    const items = store.container(doc);
    const o = items.find((it) => it.id === pic.id);
    if (!o) return;
    Object.assign(o, canvas.cropped(o, crop));
    o.mask = mask;
    if (line) o.border = { color: line.color, width: line.width, ...(line.swatch ? { swatch: line.swatch } : {}) };
    const at = items.findIndex((it) => it.id === shape.id);
    if (at >= 0) items.splice(at, 1);
  }, { select: [pic.id] });
  announce(`Cropped the picture to the ${shape.geom === "custom" ? "shape" : shapeName(shape.geom).toLowerCase()}`);
}

// A picture of a drawn crop shape (mask geom custom), for the Picture tab's Crop to shape
export function drawnShapePicture(mask) {
  const d = (mask?.path?.subpaths || []).map((sub) => sub.cmds.map((seg) => seg[0] + seg.slice(1).map((v, k) =>
    (2 + (20 * v) / ((k % 2 === 0 ? sub.w : sub.h) || 1)).toFixed(2)).join(" ")).join("")).join("");
  return pathIcon(d || "M4 6h16v12H4z");
}

// The aspect ratios, as a menu's lines (the Crop menu's submenu, the right-click menu's)
export function ratioEntries(id, customRatio) {
  return [...RATIOS.flatMap(([heading, list]) => [{ heading }, ...list.map(([w, hh]) => ({
    label: `${w}:${hh}`, run: () => cropToRatio(id, w, hh) }))]),
  "-", { label: "Custom…", run: async () => {
    const text = await customRatio();
    if (text === null) return;
    const r = parseRatio(text);
    if (!r) { announce("Type a ratio such as 7:5"); return; }
    cropToRatio(id, ...r);
  } }];
}

// The Crop menu's lines (Figure tab, right-click): for the picture selected, or greyed out.
// customRatio: asks for a ratio (panels.promptDialog)
export function cropMenu(customRatio) {
  const it = selectedPicture(), pair = drawnPair(), none = it ? null : "select a picture";
  const off = { disabled: !it, note: none };
  // (a zoom inset shows what its box covers, in the box's shape: zoom.js)
  const own = it?.inset ? { disabled: true, note: "a zoom inset follows its box" } : off;
  const ratios = it && !it.inset ? ratioEntries(it.id, customRatio) : [];
  const geoms = shapeCatalog.groups.map((g) => [g.title, g.shapes.filter((geom) => shapeCatalog.shapes[geom]?.closed)])
    .filter(([, list]) => list.length);
  const now = it?.mask?.geom || "";
  const shapes = [{ label: "None (the whole frame)", picture: shapePicture(null), checked: !now, run: () => cropToShape(it.id, null) },
    ...geoms.flatMap(([heading, list]) => [{ heading }, ...list.map((geom) => ({ label: shapeName(geom), picture: shapePicture(geom),
      checked: now === geom, run: () => cropToShape(it.id, geom) }))])];
  return [
    { label: "Crop", keys: "Enter", ...off, run: () => canvas.startCrop(it.id) },
    { label: "Aspect ratio", ...own, items: ratios },
    { label: "Crop to shape", ...own, items: it && !it.inset ? shapes : [] },
    { label: "Crop to shape drawn over it", disabled: !pair.pic, note: pair.why, run: () => cropToDrawnShape() },
    "-",
    { label: "Reset crop", ...off, run: () => resetCrop(it.id) },
  ];
}

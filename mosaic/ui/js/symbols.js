// Symbols, as in Illustrator: objects kept once in the figure (doc.symbols: {id, name, items,
// size}, the items with their box's top left at 0, 0) and used as copies, items {type: "symbol",
// symbol, frame, rot, flip_h, flip_v}. The engine draws a copy's symbol scaled to its frame, lines
// and text with it, so every copy changes when the symbol does.
// - Make symbol turns the selected objects into a symbol and puts one copy where they were.
// - Editing in place: double-clicking a copy swaps it for a group of the symbol's objects at the
//   symbol's own size where the copy is (group.editing_symbol: {symbol, copy}), worked on inside
//   it like any group; leaving the group puts them back in the symbol (commitEdit).
// - Break link: a copy becomes its own objects, scaled, turned and flipped as it was.
import { rotateItem, shiftItem } from "./canvas.js";
import { itemsBBox, uid } from "./util.js";

const clone = (o) => JSON.parse(JSON.stringify(o));
export const symbolOf = (doc, id) => (doc.symbols || []).find((s) => s.id === id) || null;

// What a symbol can hold: anything but pictures and the things tied to them (scale bars, zoom
// boxes, insets and their lines)
export function canHold(it) {
  if (it.type === "group") return it.items.every(canHold);
  return !(it.type === "picture" || it.type === "scalebar" || it.zoom || it.inset || it.zoomline);
}

// Every copy of a symbol, on every page and in other symbols: [item, where]
export function copiesOf(doc, id) {
  const out = [];
  const walk = (items, where) => items.forEach((it) => {
    if (it.type === "group") walk(it.items, where);
    if (it.type === "symbol" && it.symbol === id) out.push([it, where]);
  });
  doc.pages.forEach((pg, i) => walk(pg.items, i));
  for (const s of doc.symbols || []) walk(s.items, s.id);
  return out;
}

// A symbol of these objects, and a copy of it where they were
export function makeSymbol(doc, items, name) {
  const b = itemsBBox(items);
  const kept = clone(items);
  for (const it of kept) shiftItem(it, clone(it), -b[0], -b[1]);
  // Line ends attached to objects left out let go
  const ids = new Set(), walk = (its) => its.forEach((it) => { ids.add(it.id); if (it.type === "group") walk(it.items); });
  walk(kept);
  const lines = [], walkLines = (its) => its.forEach((it) => { if (it.type === "group") walkLines(it.items); if (it.type === "line") lines.push(it); });
  walkLines(kept);
  for (const l of lines) for (const k of ["start_link", "end_link"]) if (l[k] && !ids.has(l[k].item)) delete l[k];
  for (const it of kept) delete it.attach;
  const sym = { id: uid("sym"), name: name || `Symbol ${(doc.symbols || []).length + 1}`, items: kept, size: [b[2] - b[0], b[3] - b[1]] };
  const copy = { id: uid("it"), type: "symbol", symbol: sym.id, name: "", frame: [b[0], b[1], sym.size[0], sym.size[1]],
    rot: 0, flip_h: false, flip_v: false };
  return { sym, copy };
}

// A copy's scale: its frame against its symbol's size
export const scaleOf = (copy, sym) => [copy.frame[2] / Math.max(sym.size[0], 1e-9), copy.frame[3] / Math.max(sym.size[1], 1e-9)];

// Resize an object's content with it, from 0, 0: places and sizes by (sx, sy); line widths, text
// sizes and the like by their mean
export function scaleContent(it, sx, sy) {
  const k = Math.sqrt(Math.abs(sx * sy));
  if (it.type === "group") { it.items.forEach((c) => scaleContent(c, sx, sy)); return; }
  if (it.frame) it.frame = [it.frame[0] * sx, it.frame[1] * sy, it.frame[2] * sx, it.frame[3] * sy];
  if (it.points) it.points = it.points.map(([x, y]) => [x * sx, y * sy]);
  if (it.stroke?.width) it.stroke = { ...it.stroke, width: it.stroke.width * k };
  if (it.outline?.width) it.outline = { ...it.outline, width: it.outline.width * k };
  if (it.text) {
    for (const p of it.text.paragraphs || []) for (const r of p.runs || []) if (r.size) r.size *= k;
    if (it.text.insets) it.text.insets = it.text.insets.map((v, i) => v * (i % 2 ? sy : sx));
  }
  if (it.type === "bracket") for (const key of ["size", "line_width", "tick"]) if (it[key]) it[key] *= k;
}

// A copy's objects as it shows them: scaled, put in its frame, turned and flipped about its middle
export function placedItems(copy, sym) {
  const [sx, sy] = scaleOf(copy, sym), [x, y, w, h] = copy.frame, cx = x + w / 2, cy = y + h / 2;
  const items = clone(sym.items).map((it) => {
    scaleContent(it, sx, sy);
    shiftItem(it, clone(it), x, y);
    return it;
  });
  const mirror = (it, axis) => {
    if (it.type === "group") { it.items.forEach((c) => mirror(c, axis)); if (it.rot) it.rot = 360 - it.rot; return; }
    if (it.points) it.points = it.points.map((p) => (axis ? [p[0], 2 * cy - p[1]] : [2 * cx - p[0], p[1]]));
    if (it.frame) {
      const f = it.frame;
      it.frame = axis ? [f[0], 2 * cy - f[1] - f[3], f[2], f[3]] : [2 * cx - f[0] - f[2], f[1], f[2], f[3]];
      const key = axis ? "flip_v" : "flip_h";
      it[key] = !it[key];
      it.rot = (360 - (it.rot || 0)) % 360;
    }
  };
  for (const it of items) {
    if (copy.flip_h) mirror(it, 0);
    if (copy.flip_v) mirror(it, 1);
    if (copy.rot) rotateItem(it, copy.rot, cx, cy);
  }
  // Fresh ids, kept consistent for attached line ends and area fills among them
  const ids = new Map();
  const reid = (it) => { const n = uid("it"); ids.set(it.id, n); it.id = n; if (it.type === "group") it.items.forEach(reid); };
  items.forEach(reid);
  const fix = (it) => {
    if (it.type === "group") it.items.forEach(fix);
    for (const k of ["start_link", "end_link"]) if (it[k]) { if (ids.has(it[k].item)) it[k].item = ids.get(it[k].item); else delete it[k]; }
    if (it.region?.items) it.region = { ...it.region, items: it.region.items.map((id) => ids.get(id) || id) };
  };
  items.forEach(fix);
  return items;
}

// Editing in place: the group that stands in for a copy while its symbol is edited
export function editGroup(copy, sym) {
  const items = clone(sym.items);
  for (const it of items) shiftItem(it, clone(it), copy.frame[0], copy.frame[1]);
  return { id: uid("it"), type: "group", name: `${sym.name} (editing)`, items, editing_symbol: { symbol: sym.id, copy: clone(copy) } };
}

// Leaving it: its objects become the symbol, and the copy comes back. Every copy keeps its
// objects where they were: when the symbol's box grows or moves, each copy's frame moves and
// grows with it, at that copy's own scale. Nothing left in it leaves the symbol as it was.
export function commitEdit(doc, group) {
  const { symbol, copy } = group.editing_symbol, sym = symbolOf(doc, symbol);
  const back = clone(copy);
  if (sym && group.items.length) {
    const b = itemsBBox(group.items) || [copy.frame[0], copy.frame[1], copy.frame[0] + sym.size[0], copy.frame[1] + sym.size[1]];
    const shift = [b[0] - copy.frame[0], b[1] - copy.frame[1]], size = [b[2] - b[0], b[3] - b[1]];
    const items = clone(group.items);
    for (const it of items) shiftItem(it, clone(it), -b[0], -b[1]);
    const old = sym.size.slice();
    const refit = (c) => {
      const sx = c.frame[2] / Math.max(old[0], 1e-9), sy = c.frame[3] / Math.max(old[1], 1e-9);
      c.frame = [c.frame[0] + shift[0] * sx, c.frame[1] + shift[1] * sy, size[0] * sx, size[1] * sy];
    };
    for (const [c] of copiesOf(doc, symbol)) refit(c);
    refit(back);
    sym.items = items;
    sym.size = size;
  }
  return back;
}

// Every group standing in for a copy that isn't being worked in (`open`: the groups the editor is
// inside) is put back: on leaving it, or a figure saved part way through
export function finishEdits(doc, open = []) {
  const walk = (items) => items.forEach((it, i) => {
    if (it.type !== "group") return;
    walk(it.items);
    if (it.editing_symbol && !open.includes(it.id)) items[i] = commitEdit(doc, it);
  });
  doc.pages.forEach((pg) => walk(pg.items));
  return doc;
}

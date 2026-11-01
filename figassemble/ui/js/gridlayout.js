// Grid layout: a group whose parts sit in rows and columns, laid out again whenever one changes.
// group.grid {cols, gap: [across, down], origin: [x, y], order: [ids], seen}. The parts keep their
// sizes: each column is as wide as its widest part and each row as tall as its tallest, gap
// apart, starting at origin, and each part sits at the top left of its cell, in `order` (row by
// row). The last part of a short last row reaches across the columns left (a wide panel under a
// row of narrower ones widens the last column, not its first). followGrids lays out every grid
// after each change, inner grids first.
// - A part dragged onto another cell moves there in the order: seen holds where each part was
//   put last time and the origin then, so a part that's moved on its own is told apart from the
//   whole grid moving (shiftItem moves the origin with it).
// - When every part has moved together (the grid resized or turned), the grid starts where they
//   now start.
import { shiftItem } from "./canvas.js";
import { itemBBox, itemsBBox } from "./util.js";

const near = (a, b) => Math.abs(a - b) <= 1e-6;
export const DEFAULT_GAP = 72 / 25.4 * 3;   // 3 mm

// The cells: the parts in order, and the columns' lefts and widths and rows' tops and heights
export function gridCells(g) {
  const byId = new Map(g.items.map((it) => [it.id, it])), listed = (g.grid.order || []).filter((id) => byId.has(id));
  const order = [...listed, ...g.items.map((it) => it.id).filter((id) => !listed.includes(id))];
  const cols = Math.max(1, Math.round(g.grid.cols || 1)), [gx, gy] = g.grid.gap || [DEFAULT_GAP, DEFAULT_GAP];
  const widths = Array(cols).fill(0), heights = Array(Math.ceil(order.length / cols)).fill(0);
  const across = order.length % cols ? order.length - 1 : -1;   // the last part of a short last row
  order.forEach((id, k) => {
    const b = itemBBox(byId.get(id)), c = k % cols, r = Math.floor(k / cols);
    if (k !== across) widths[c] = Math.max(widths[c], b[2] - b[0]);
    heights[r] = Math.max(heights[r], b[3] - b[1]);
  });
  if (across >= 0) {
    const b = itemBBox(byId.get(order[across])), c0 = across % cols;
    const room = widths.slice(c0).reduce((sum, w) => sum + w, 0) + gx * (cols - 1 - c0);
    if (b[2] - b[0] > room) widths[cols - 1] += b[2] - b[0] - room;
  }
  const lefts = [], tops = [];
  widths.reduce((x, w, c) => { lefts[c] = x; return x + w + gx; }, g.grid.origin[0]);
  heights.reduce((y, h, r) => { tops[r] = y; return y + h + gy; }, g.grid.origin[1]);
  return { order, byId, cols, gap: [gx, gy], widths, heights, lefts, tops };
}

// The cell (in reading order) whose column and row a point is in, or nearest to
function cellAt(cells, [x, y]) {
  const pick = (starts, gap, v) => starts.reduce((best, s, i) => (v >= s - gap / 2 ? i : best), 0);
  return Math.min(pick(cells.tops, cells.gap[1], y) * cells.cols + pick(cells.lefts, cells.gap[0], x), cells.order.length - 1);
}

export function followGrids(items) {
  for (const it of items) {
    if (it.type !== "group") continue;
    followGrids(it.items);
    if (it.grid && it.items.length) layOut(it);
  }
}

function layOut(g) {
  const grid = g.grid, seen = grid.seen;
  if (!grid.origin) grid.origin = (itemsBBox(g.items) || [0, 0]).slice(0, 2);
  let cells = gridCells(g);
  if (seen && near(seen.origin[0], grid.origin[0]) && near(seen.origin[1], grid.origin[1])) {
    const moved = cells.order.filter((id) => {
      const at = seen.at?.[id], b = itemBBox(cells.byId.get(id));
      return at && !(near(at[0], b[0]) && near(at[1], b[1]));
    });
    if (moved.length === 1) {
      // One part dragged: to the cell its middle is over
      const b = itemBBox(cells.byId.get(moved[0])), to = cellAt(cells, [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
      grid.order = cells.order.filter((id) => id !== moved[0]);
      grid.order.splice(to, 0, moved[0]);
      cells = gridCells(g);
    } else if (moved.length > 1 && moved.length === cells.order.length) {
      grid.origin = (itemsBBox(g.items) || grid.origin).slice(0, 2);
      cells = gridCells(g);
    }
  }
  grid.order = cells.order;
  const at = {};
  cells.order.forEach((id, k) => {
    const part = cells.byId.get(id), b = itemBBox(part);
    const x = cells.lefts[k % cells.cols], y = cells.tops[Math.floor(k / cells.cols)];
    if (!near(b[0], x) || !near(b[1], y)) shiftItem(part, JSON.parse(JSON.stringify(part)), x - b[0], y - b[1]);
    at[id] = [x, y];
  });
  grid.seen = { origin: grid.origin.slice(), at };
}

// A new grid for objects as they lie: rows from the top (a part starting above the middle of the
// row before joins it), each left to right, as many columns as the longest row; the gaps the
// median of the gaps between them, or 3 mm
export function gridFor(items) {
  const parts = items.map((it) => ({ id: it.id, b: itemBBox(it) })).sort((p, q) => p.b[1] - q.b[1]);
  const rows = [];
  for (const p of parts) {
    const last = rows[rows.length - 1];
    if (last && p.b[1] < last.mid) last.parts.push(p);
    else rows.push({ parts: [p], mid: (p.b[1] + p.b[3]) / 2 });
  }
  rows.forEach((r) => r.parts.sort((p, q) => p.b[0] - q.b[0]));
  const median = (v) => (v.length ? [...v].sort((a, b) => a - b)[Math.floor((v.length - 1) / 2)] : DEFAULT_GAP);
  const across = rows.flatMap((r) => r.parts.slice(1).map((p, i) => p.b[0] - r.parts[i].b[2])).filter((d) => d > 0);
  const down = rows.slice(1).map((r, i) => Math.min(...r.parts.map((p) => p.b[1])) - Math.max(...rows[i].parts.map((p) => p.b[3])))
    .filter((d) => d > 0);
  const box = itemsBBox(items);
  return { cols: Math.max(...rows.map((r) => r.parts.length)), gap: [median(across), median(down)], origin: [box[0], box[1]],
    order: rows.flatMap((r) => r.parts.map((p) => p.id)) };
}

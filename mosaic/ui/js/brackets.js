// Significance brackets: a bar with an end tick at each side and a label beyond it, drawn by the
// engine (resolve._bracket). Across (dir up or down) the ticks are as long as the frame leaves
// below (or above) the label's room, so that room must stay in step with the label and its size.
// The line is `stroke`, as a line's (dashes, ends, corners, transparency); brackets made before
// 2026-11-18 had color, line_width and swatch, and become stroke when a figure opens or they're
// pasted (upgradeItems). The label takes the line's colour.

export const STAR_LABELS = [["*", "*"], ["**", "**"], ["***", "***"], ["****", "****"], ["ns", "ns"]];
export const P_LABELS = ["p < 0.1", "p < 0.05", "p < 0.01", "p < 0.001", "p < 0.0001"].map((v) => [v, v]);
export const BRACKET_LABELS = [...STAR_LABELS, ...P_LABELS];
export const across = (it) => !["left", "right"].includes(it.dir || "up");
// The label's room across: a line of text and the gap (to the letters), or before gaps could be
// set, a line and 0.3 text sizes, as the engine lays it out
export const labelRoom = (it) => (!it.label ? 0 : (it.size ?? 6) * (it.gap == null ? 1.5 : 1.2) + Math.max(it.gap ?? 0, 0));

// A bracket's line as it is drawn (one from before brackets had a stroke: its colour and width)
export function bracketStroke(it) {
  return it.stroke || { color: it.color ?? "#000000", width: it.line_width ?? 0.75, dash: "solid", cap: "round", join: "miter", opacity: 1,
    ...(it.swatch ? { swatch: it.swatch } : {}) };
}
// Brackets from before 2026-11-18 (color, line_width, swatch) get the stroke they were drawn with
export function upgradeItems(items) {
  for (const it of items || []) {
    if (it.type === "group") upgradeItems(it.items);
    if (it.type === "bracket" && !it.stroke) {
      it.stroke = bracketStroke(it);
      delete it.color;
      delete it.line_width;
      delete it.swatch;
    }
  }
}
export function upgradeDoc(doc) {
  for (const pg of doc?.pages || []) upgradeItems(pg.items);
  for (const sym of doc?.symbols || []) upgradeItems(sym.items);
}
// The bar's edge facing the label, in frame coordinates, and the way to the label: across, a
// height (y) and up (-1) or down (1); upright, a distance across (x) and left (-1) or right (1)
export function bracketGapEdge(it) {
  const [, , w, h] = it.frame, half = (bracketStroke(it).width ?? 0.75) / 2, d = it.dir || "up";
  if (d === "up") return { y: labelRoom(it) - half, dir: -1 };
  if (d === "down") return { y: h - labelRoom(it) + half, dir: 1 };
  const tick = Math.min(it.tick ?? 4, w);
  return d === "right" ? { x: tick + half, dir: 1 } : { x: w - tick - half, dir: -1 };
}

// A change to a bracket's label or text size, keeping its bar where it is and its ticks as long
export function keepBar(it, change) {
  const room0 = labelRoom(it), tick = Math.max(it.frame[3] - room0, 0);
  change(it);
  if (!across(it)) return;
  const room1 = labelRoom(it);
  it.frame = [it.frame[0], (it.dir || "up") === "up" ? it.frame[1] + room0 - room1 : it.frame[1], it.frame[2], room1 + tick];
}

// Brackets pointing up in tidy levels: narrowest first, each on the lowest level where it doesn't
// overlap another; the lowest level's ticks end where the lowest bracket's did, and each level
// sits just above the one below it (2 pt between)
export function stackLevels(brackets) {
  const base = Math.max(...brackets.map((b) => b.frame[1] + b.frame[3]));
  const step = Math.max(...brackets.map((b) => b.frame[3])) + 2;
  const levels = [];
  const out = new Map();
  for (const b of [...brackets].sort((p, q) => p.frame[2] - q.frame[2])) {
    const [x0, x1] = [b.frame[0], b.frame[0] + b.frame[2]];
    let level = levels.findIndex((spans) => spans.every(([a, c]) => x1 + 1 < a || x0 - 1 > c));
    if (level < 0) { levels.push([]); level = levels.length - 1; }
    levels[level].push([x0, x1]);
    out.set(b.id, base - level * step - b.frame[3]);
  }
  return out;   // id -> new top
}

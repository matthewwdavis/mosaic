// Significance brackets: a bar with an end tick at each side and a label beyond it, drawn by the
// engine (resolve._bracket). Across (dir up or down) the ticks are as long as the frame leaves
// below (or above) the label's room, so that room must stay in step with the label and its size.

export const BRACKET_LABELS = [["*", "*"], ["**", "**"], ["***", "***"], ["****", "****"], ["ns", "ns"]];
export const across = (it) => !["left", "right"].includes(it.dir || "up");
export const labelRoom = (it) => (it.label ? (it.size ?? 6) * 1.5 : 0);   // line height + gap, as the engine lays it out

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

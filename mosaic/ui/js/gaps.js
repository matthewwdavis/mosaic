// The gaps between neighbours in a selection, for Arrange ▸ Spacing's Gap across and Gap down: what
// they are now, and where each object goes for a gap typed in. Boxes are [{id, b: [x0, y0, x1, y1]}];
// the axis is "h" (side by side: across) or "v" (above one another: down).
//
// An object's neighbour across is the nearest one beside it (overlapping it up and down) that starts
// and ends further right (one wholly within it, a panel on a background box, isn't beside it); down,
// the nearest one below it that overlaps it across. So a row of panels has a
// gap between each pair, a grid has its gaps across within each row and down within each column, and
// a tall panel beside two short ones has a gap to each of them.

const EPS = 1e-6;
const SAME = 1e-3;   // pt: neighbours starting this close together are both the nearest

function axes(axis) {
  return axis === "h" ? [0, 2, 1, 3] : [1, 3, 0, 2];
}

// [[a, c], ...]: c is a's neighbour (one of its nearest, after it along the axis)
export function neighbours(boxes, axis) {
  const [i0, i1, j0, j1] = axes(axis);
  const pairs = [];
  for (const a of boxes) {
    const beside = boxes.filter((c) => c !== a && c.b[i0] > a.b[i0] + EPS && c.b[i1] > a.b[i1] + EPS
      && Math.min(a.b[j1], c.b[j1]) - Math.max(a.b[j0], c.b[j0]) > EPS);
    if (!beside.length) continue;
    const first = Math.min(...beside.map((c) => c.b[i0]));
    for (const c of beside) if (c.b[i0] - first < SAME) pairs.push([a, c]);
  }
  return pairs;
}

// The gaps between neighbours now: {min, max, count} in pt (negative where they overlap), or null
// when none are beside one another that way
export function measureGaps(boxes, axis) {
  const [i0, i1] = axes(axis);
  const gaps = neighbours(boxes, axis).map(([a, c]) => c.b[i0] - a.b[i1]);
  return gaps.length ? { min: Math.min(...gaps), max: Math.max(...gaps), count: gaps.length } : null;
}

// Where each object starts along the axis (Map id -> pt) for exactly `gap` between neighbours: those
// with nothing before them stay put and the rest follow on (after the furthest of those before them,
// so nothing comes to overlap); with a key object, everything shifts so the key stays put. Null when
// none are beside one another that way
export function spacedStarts(boxes, axis, gap, keyId = null) {
  const [i0, i1] = axes(axis);
  const pairs = neighbours(boxes, axis);
  if (!pairs.length) return null;
  const before = new Map(boxes.map((x) => [x, []]));
  for (const [a, c] of pairs) before.get(c).push(a);
  const start = new Map();
  // (a neighbour always starts further along than the one before it, so this order has those first)
  for (const x of [...boxes].sort((p, q) => p.b[i0] - q.b[i0])) {
    const prev = before.get(x);
    start.set(x, prev.length ? Math.max(...prev.map((a) => start.get(a) + (a.b[i1] - a.b[i0]) + gap)) : x.b[i0]);
  }
  const key = keyId != null && boxes.find((x) => x.id === keyId);
  const shift = key ? start.get(key) - key.b[i0] : 0;
  return new Map(boxes.map((x) => [x.id, start.get(x) - shift]));
}

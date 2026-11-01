// Freeform paths as anchor points with Bezier handles: for the pen tool, and for editing the
// points of a freeform shape (geom "custom"). Its path, item.path.subpaths [{cmds, w, h, fill,
// stroke}] (commands M, L, C, Q and Z, in units scaled to its frame), becomes rings of nodes {p,
// hin, hout, smooth} in frame coordinates: each M starts a ring, kept with the subpath it was in
// (group), so a shape with a hole keeps its hole. A smooth node's handles stay in line.
import { apply, frameMatrix, invert } from "./util.js";

const near = (a, b, tol = 1e-6) => Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol;
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const len = (v) => Math.hypot(v[0], v[1]);
export const inLine = (a, p, b) => {
  const u = sub(a, p), v = sub(b, p), lu = len(u), lv = len(v);
  return lu > 1e-9 && lv > 1e-9 && Math.abs(u[0] * v[1] - u[1] * v[0]) / (lu * lv) < 0.02 && u[0] * v[0] + u[1] * v[1] < 0;
};

// A shape's own frame <-> the page
const matrixOf = (item) => frameMatrix(item.frame, item.rot || 0, item.flip_h, item.flip_v);
export const toLocal = (item, p) => apply(invert(matrixOf(item)), p[0], p[1]);
export const toPageOf = (item, q) => apply(matrixOf(item), q[0], q[1]);

export function ringsOf(item) {
  const [, , w, h] = item.frame, rings = [];
  (item.path?.subpaths || []).forEach((s, group) => {
    const kx = w / (s.w || w || 1), ky = h / (s.h || h || 1), P = (x, y) => [x * kx, y * ky];
    let ring = null;
    for (const [op, ...v] of s.cmds || []) {
      if (op === "M") {
        ring = { nodes: [{ p: P(v[0], v[1]), hin: null, hout: null }], closed: false, group, fill: s.fill ?? true, stroke: s.stroke ?? true };
        rings.push(ring);
      } else if (!ring) {
        continue;
      } else if (op === "L") {
        ring.nodes.push({ p: P(v[0], v[1]), hin: null, hout: null });
      } else if (op === "C" || op === "Q") {
        const last = ring.nodes[ring.nodes.length - 1];
        const [c1, c2, end] = op === "C" ? [P(v[0], v[1]), P(v[2], v[3]), P(v[4], v[5])]
          : [lerp(last.p, P(v[0], v[1]), 2 / 3), lerp(P(v[2], v[3]), P(v[0], v[1]), 2 / 3), P(v[2], v[3])];   // as a cubic
        last.hout = c1;
        ring.nodes.push({ p: end, hin: c2, hout: null });
      } else if (op === "Z") {
        ring.closed = true;
      }
    }
  });
  for (const r of rings) {
    // A closing segment drawn back to the start ends on the first node
    if (r.closed && r.nodes.length > 1 && near(r.nodes[0].p, r.nodes[r.nodes.length - 1].p, 1e-6)) r.nodes[0].hin = r.nodes.pop().hin;
    for (const n of r.nodes) {
      // A curve into or out of a corner has its control point on the corner: no handle there
      if (n.hin && near(n.hin, n.p, 1e-6)) n.hin = null;
      if (n.hout && near(n.hout, n.p, 1e-6)) n.hout = null;
      n.smooth = !!(n.hin && n.hout && inLine(n.hin, n.p, n.hout));
    }
  }
  return rings;
}

const segment = (a, b) => (a.hout || b.hin ? ["C", ...(a.hout || a.p), ...(b.hin || b.p), ...b.p] : ["L", ...b.p]);
export function pathOf(rings, w, h) {
  const groups = new Map();
  for (const r of rings) {
    if (!r.nodes.length) continue;
    const cmds = [["M", ...r.nodes[0].p]];
    for (let i = 1; i < r.nodes.length; i++) cmds.push(segment(r.nodes[i - 1], r.nodes[i]));
    if (r.closed) {
      if (r.nodes.length > 1) cmds.push(segment(r.nodes[r.nodes.length - 1], r.nodes[0]));
      cmds.push(["Z"]);
    }
    if (!groups.has(r.group)) groups.set(r.group, { cmds: [], w, h, fill: r.fill, stroke: r.stroke });
    groups.get(r.group).cmds.push(...cmds);
  }
  return { subpaths: [...groups.values()] };
}

// The segments of a ring: [start node, end node, index of the start]
export function segments(r) {
  const out = [];
  for (let i = 0; i < r.nodes.length - 1; i++) out.push([r.nodes[i], r.nodes[i + 1], i]);
  if (r.closed && r.nodes.length > 1) out.push([r.nodes[r.nodes.length - 1], r.nodes[0], r.nodes.length - 1]);
  return out;
}
const controls = (a, b) => [a.p, a.hout || a.p, b.hin || b.p, b.p];
export function bezier([p0, p1, p2, p3], t) {
  const u = 1 - t;
  return [u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]];
}

// The box round the rings: their ends and each curve's turning points
export function boundsOf(rings) {
  const xs = [], ys = [];
  for (const r of rings) {
    for (const n of r.nodes) { xs.push(n.p[0]); ys.push(n.p[1]); }
    for (const [a, b] of segments(r)) {
      if (!a.hout && !b.hin) continue;
      const c = controls(a, b);
      for (const k of [0, 1]) {
        // Where the curve's derivative along this axis is zero: a t^2 + b t + c = 0
        const [q0, q1, q2, q3] = c.map((p) => p[k]);
        const A = -q0 + 3 * q1 - 3 * q2 + q3, B = 2 * (q0 - 2 * q1 + q2), C = q1 - q0;
        const roots = Math.abs(A) < 1e-12 ? (Math.abs(B) > 1e-12 ? [-C / B] : [])
          : (() => { const d = B * B - 4 * A * C; return d < 0 ? [] : [(-B + Math.sqrt(d)) / (2 * A), (-B - Math.sqrt(d)) / (2 * A)]; })();
        for (const t of roots) if (t > 0 && t < 1) { const p = bezier(c, t); xs.push(p[0]); ys.push(p[1]); }
      }
    }
  }
  return xs.length ? [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] : null;
}

// The rings put back in the shape: its frame round them, so it stays where it is on the page
// (turned and flipped as it was)
export function writeRings(item, rings) {
  const b = boundsOf(rings);
  if (!b) return;
  const w = Math.max(b[2] - b[0], 0.5), h = Math.max(b[3] - b[1], 0.5);
  const c = toPageOf(item, [b[0] + w / 2, b[1] + h / 2]);
  const shift = (p) => (p ? [p[0] - b[0], p[1] - b[1]] : null);
  for (const r of rings) for (const n of r.nodes) { n.p = shift(n.p); n.hin = shift(n.hin); n.hout = shift(n.hout); }
  item.frame = [c[0] - w / 2, c[1] - h / 2, w, h];
  item.path = pathOf(rings, w, h);
}

// The point on the rings nearest q: {ring, seg (index of its start node), t, at, d}
export function nearestOn(rings, q) {
  let best = null;
  rings.forEach((r, ri) => {
    for (const [a, b, i] of segments(r)) {
      const c = controls(a, b);
      for (let s = 0; s <= 48; s++) {
        const t = s / 48, p = bezier(c, t), d = Math.hypot(p[0] - q[0], p[1] - q[1]);
        if (!best || d < best.d) best = { ring: ri, seg: i, t, at: p, d };
      }
    }
  });
  return best;
}

// A new node part way along a segment, the curve unchanged (de Casteljau)
export function splitAt(rings, ri, seg, t) {
  const r = rings[ri], a = r.nodes[seg], b = r.nodes[(seg + 1) % r.nodes.length];
  let node;
  if (a.hout || b.hin) {
    const [p0, p1, p2, p3] = controls(a, b);
    const q0 = lerp(p0, p1, t), q1 = lerp(p1, p2, t), q2 = lerp(p2, p3, t), r0 = lerp(q0, q1, t), r1 = lerp(q1, q2, t);
    a.hout = q0;
    b.hin = q2;
    node = { p: lerp(r0, r1, t), hin: r0, hout: r1, smooth: true };
  } else {
    node = { p: lerp(a.p, b.p, t), hin: null, hout: null, smooth: false };
  }
  r.nodes.splice(seg + 1, 0, node);
  return seg + 1;
}

// A corner made smooth (handles along the line between its neighbours, a third of the way to
// each), or a smooth point made a corner (no handles)
export function toggleSmooth(r, ni) {
  const n = r.nodes[ni], k = r.nodes.length;
  if (n.hin || n.hout) {
    n.hin = n.hout = null;
    n.smooth = false;
    return;
  }
  const prev = r.nodes[(ni - 1 + k) % k], next = r.nodes[(ni + 1) % k];
  const first = !r.closed && ni === 0, last = !r.closed && ni === k - 1;
  const from = first ? n.p : prev.p, to = last ? n.p : next.p, dir = sub(to, from), l = len(dir) || 1;
  const u = [dir[0] / l, dir[1] / l];
  const din = first ? 0 : len(sub(n.p, prev.p)) / 3, dout = last ? 0 : len(sub(next.p, n.p)) / 3;
  n.hin = first ? null : [n.p[0] - u[0] * din, n.p[1] - u[1] * din];
  n.hout = last ? null : [n.p[0] + u[0] * dout, n.p[1] + u[1] * dout];
  n.smooth = !!(n.hin && n.hout);
}

// A handle dragged to q: a smooth node's other handle turns to stay in line, keeping its length
// (unless `free`, which makes it a corner)
export function moveHandle(n, which, q, free) {
  n[which] = q;
  const other = which === "hin" ? "hout" : "hin";
  if (free) { n.smooth = false; return; }
  if (n.smooth && n[other]) {
    const d = sub(q, n.p), l = len(d), lo = len(sub(n[other], n.p));
    if (l > 1e-9) n[other] = [n.p[0] - (d[0] / l) * lo, n.p[1] - (d[1] / l) * lo];
  }
}

// An anchor moved by (dx, dy), its handles with it
export function moveNode(n, dx, dy) {
  const m = (p) => (p ? [p[0] + dx, p[1] + dy] : null);
  n.p = m(n.p);
  n.hin = m(n.hin);
  n.hout = m(n.hout);
}

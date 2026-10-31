// Small shared helpers: DOM building, units, matrices, hit testing, announcements.

export const PT_PER = { pt: 1, mm: 72 / 25.4, cm: 72 / 2.54, in: 72, px: 0.75 };
export const UNIT_LABEL = { pt: "pt", mm: "mm", cm: "cm", in: "in", px: "px" };
export const PX_PER_PT = 4 / 3;   // CSS px per point at 100% zoom: 100% is true size

export const toUnit = (pt, unit) => pt / PT_PER[unit];
export const fromUnit = (v, unit) => v * PT_PER[unit];

export function fmt(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  let s = Number(v).toFixed(digits);
  if (s.includes(".")) s = s.replace(/\.?0+$/, "");   // trailing zeros after the point only (300 stays 300)
  return s === "-0" ? "0" : s;
}

export function uid(prefix) {
  const bytes = crypto.getRandomValues(new Uint8Array(5));
  return `${prefix}_${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

export const clone = (o) => JSON.parse(JSON.stringify(o));
export const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
export const isMac = navigator.platform.toUpperCase().includes("MAC") || /Mac/.test(navigator.userAgent);
export const MOD = isMac ? "⌘" : "Ctrl+";

// A field's keydown: keys stay in the field, except ⌘/Ctrl + a letter, which goes on to the
// editor's shortcuts (in a field those run only Save, Open, New and Export; the rest are the field's)
export function keepFieldKeys(e) {
  if (!((e.metaKey || e.ctrlKey) && /^[a-z]$/i.test(e.key))) e.stopPropagation();
}

// Element builder: h("button", {class: "x", onclick: fn, "aria-label": "..."}, "text", child)
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = !!v;
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";
export function s(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
  return el;
}

// Matrices [a b c d e f], same convention as the Python engine
export const I = [1, 0, 0, 1, 0, 0];
export function mul(m, n) {
  return [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3],
    m[1] * n[2] + m[3] * n[3], m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
}
export const apply = (m, x, y) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
export function invert(m) {
  const det = m[0] * m[3] - m[1] * m[2];
  const a = m[3] / det, b = -m[1] / det, c = -m[2] / det, d = m[0] / det;
  return [a, b, c, d, -(a * m[4] + c * m[5]), -(b * m[4] + d * m[5])];
}
export const translate = (x, y) => [1, 0, 0, 1, x, y];
export const scale = (sx, sy = sx) => [sx, 0, 0, sy, 0, 0];
export function rotate(deg) {
  const q = deg / 90;
  let c, s;
  if (Math.abs(q - Math.round(q)) < 1e-12) [c, s] = [[1, 0], [0, 1], [-1, 0], [0, -1]][((Math.round(q) % 4) + 4) % 4];
  else { const r = (deg * Math.PI) / 180; c = Math.cos(r); s = Math.sin(r); }
  return [c, s, -s, c, 0, 0];
}
export function frameMatrix(frame, rot = 0, fh = false, fv = false) {
  const [x, y, w, h] = frame;
  return [translate(x + w / 2, y + h / 2), rotate(rot), scale(fh ? -1 : 1, fv ? -1 : 1), translate(-w / 2, -h / 2)]
    .reduce((acc, m) => mul(acc, m), I);
}
export const svgMatrix = (m) => `matrix(${m.map((v) => +v.toFixed(6)).join(" ")})`;

// Curved lines: a smooth curve through every point (centripetal Catmull-Rom as cubic
// Beziers), the same formula the engine draws with (geometry.smooth_path)
export const isCurved = (it) => it.type === "line" && it.curve === "smooth" && it.points.length >= 3;
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
export function smoothSegments(points, alpha = 0.5) {
  const pts = points.filter((p, i) => i === 0 || dist(p, points[i - 1]) > 1e-9);
  if (pts.length < 3) return pts.slice(1).map((p, i) => [pts[i], pts[i], p, p]);
  const n = pts.length;
  const ext = [[2 * pts[0][0] - pts[1][0], 2 * pts[0][1] - pts[1][1]], ...pts,
    [2 * pts[n - 1][0] - pts[n - 2][0], 2 * pts[n - 1][1] - pts[n - 2][1]]];
  const segs = [];
  for (let i = 1; i < ext.length - 2; i++) {
    const [p0, p1, p2, p3] = [ext[i - 1], ext[i], ext[i + 1], ext[i + 2]];
    const d1 = dist(p0, p1) ** alpha, d2 = dist(p1, p2) ** alpha, d3 = dist(p2, p3) ** alpha;
    const b1 = d1 < 1e-12 ? p1 : [0, 1].map((k) => (d1 * d1 * p2[k] - d2 * d2 * p0[k] + (2 * d1 * d1 + 3 * d1 * d2 + d2 * d2) * p1[k]) / (3 * d1 * (d1 + d2)));
    const b2 = d3 < 1e-12 ? p2 : [0, 1].map((k) => (d3 * d3 * p1[k] - d2 * d2 * p3[k] + (2 * d3 * d3 + 3 * d3 * d2 + d2 * d2) * p2[k]) / (3 * d3 * (d3 + d2)));
    segs.push([p1, b1, b2, p2]);
  }
  return segs;
}
export function bezPoint([p0, c1, c2, p3], t) {
  const m = 1 - t, a = m * m * m, b = 3 * m * m * t, c = 3 * m * t * t, d = t * t * t;
  return [a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0], a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]];
}
// Points along a line (densely along curves) for hit testing and bounds
export function lineSamples(it, per = 16) {
  if (!isCurved(it)) return it.points.map((p) => [p[0], p[1]]);
  const out = [it.points[0].slice()];
  for (const seg of smoothSegments(it.points)) for (let k = 1; k <= per; k++) out.push(bezPoint(seg, k / per));
  return out;
}
// The middle of each stretch between neighbouring points (on the curve, for curved lines)
export function lineMidpoints(it) {
  const segs = isCurved(it) ? smoothSegments(it.points) : null;
  const out = [];
  for (let i = 0; i < it.points.length - 1; i++) {
    const a = it.points[i], b = it.points[i + 1];
    const at = segs && segs.length === it.points.length - 1 ? bezPoint(segs[i], 0.5) : [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    out.push({ index: i, at });
  }
  return out;
}
// Which stretch of a line a page point is nearest (to insert a point there)
export function nearestStretch(it, p) {
  const segs = isCurved(it) ? smoothSegments(it.points) : null;
  let best = { index: 0, d: Infinity };
  for (let i = 0; i < it.points.length - 1; i++) {
    const samples = segs && segs.length === it.points.length - 1
      ? Array.from({ length: 17 }, (_, k) => bezPoint(segs[i], k / 16)) : [it.points[i], it.points[i + 1]];
    for (let k = 1; k < samples.length; k++) {
      const d = distToSegment(p, samples[k - 1], samples[k]);
      if (d < best.d) best = { index: i, d };
    }
  }
  return best;
}

// Geometry of items for selection and hit testing
export function itemCorners(it) {
  if (it.type === "line") return lineSamples(it);
  if (it.type === "group") return groupBBoxCorners(it);
  const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v);
  const [, , w, h] = it.frame;
  return [[0, 0], [w, 0], [w, h], [0, h]].map(([x, y]) => apply(m, x, y));
}
function groupBBoxCorners(g) {
  const b = itemsBBox(g.items);
  return b ? [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]] : [[0, 0], [0, 0], [0, 0], [0, 0]];
}
export function itemBBox(it) {
  const pts = itemCorners(it);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  let b = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  if (it.type === "line" && it.stroke) {
    const pad = (it.stroke.width || 1) / 2;
    b = [b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad];
  }
  return b;
}
export function itemsBBox(items) {
  const boxes = items.filter((i) => !i.hidden).map(itemBBox);
  if (!boxes.length) return null;
  return [Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3]))];
}
export function pointInPoly([x, y], poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-12) + xi) inside = !inside;
  }
  return inside;
}
export function distToSegment([px, py], [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay;
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1), 0, 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
export function hitItem(it, p, tol) {
  if (it.hidden) return false;
  if (it.type === "line") {
    const w = (it.stroke?.width || 1) / 2 + tol;
    const pts = lineSamples(it);
    for (let i = 1; i < pts.length; i++) if (distToSegment(p, pts[i - 1], pts[i]) <= w) return true;
    return false;
  }
  if (it.type === "group") return it.items.some((c) => hitItem(c, p, tol));
  const poly = itemCorners(it);
  if (pointInPoly(p, poly)) {
    // Open shapes without fill or text (arcs, brackets) are only hit near their frame edge
    return true;
  }
  return poly.some((q, i) => distToSegment(p, q, poly[(i + 1) % poly.length]) <= tol);
}

// Screen-reader announcements through the polite live region
let announceTimer = null;
export function announce(msg) {
  const el = document.getElementById("live");
  if (!el) return;
  clearTimeout(announceTimer);
  el.textContent = "";
  announceTimer = setTimeout(() => { el.textContent = msg; }, 60);
}

// The unit announcements use; main.js keeps it in step with the preference
export const display = { units: "cm" };
const UNIT_WORDS = { pt: "points", mm: "millimetres", cm: "centimetres", in: "inches", px: "pixels" };

// A length in that unit, e.g. "3.25 cm", or "3.25 centimetres" for announcements
export function lengthText(pt, words = false) {
  const u = display.units;
  return `${fmt(toUnit(pt, u), u === "cm" || u === "in" ? 2 : 1)} ${words ? UNIT_WORDS[u] || u : UNIT_LABEL[u] || u}`;
}

export function describeItem(it, doc) {
  const u = display.units;
  const n = (v) => fmt(toUnit(v, u), u === "cm" || u === "in" ? 2 : 1);
  const unit = UNIT_WORDS[u] || u;
  if (it.type === "picture") {
    const a = doc.assets[it.asset];
    return `Picture ${it.name || a?.name || ""}, ${n(it.frame[2])} by ${n(it.frame[3])} ${unit} at ${n(it.frame[0])}, ${n(it.frame[1])}`;
  }
  if (it.type === "line") {
    const [a, b] = [it.points[0], it.points[it.points.length - 1]];
    const kind = `${isCurved(it) ? "Curved " : ""}${it.arrow_end || it.arrow_start ? "arrow" : "line"}`;
    const via = it.points.length > 2 ? `, through ${it.points.length - 2} point${it.points.length === 3 ? "" : "s"}` : "";
    return `${kind[0].toUpperCase()}${kind.slice(1)} from ${n(a[0])}, ${n(a[1])} to ${n(b[0])}, ${n(b[1])}${via}`;
  }
  if (it.type === "group") return `Group of ${it.items.length} objects`;
  const text = itemText(it);
  if (text) return `Text "${text.slice(0, 60)}", at ${n(it.frame[0])}, ${n(it.frame[1])} ${unit}`;
  return `${shapeName(it.geom)}, ${n(it.frame[2])} by ${n(it.frame[3])} ${unit} at ${n(it.frame[0])}, ${n(it.frame[1])}`;
}
export const GEOM_NAMES = { rect: "Rectangle", roundRect: "Rounded rectangle", ellipse: "Ellipse", triangle: "Triangle",
  rtTriangle: "Right triangle", arc: "Arc", rightBracket: "Right bracket", leftBracket: "Left bracket", custom: "Freeform",
  region: "Area fill" };
// Every preset shape the engine draws: the Shapes menu's groups and each shape's name,
// adjustments and icon (main.js fills this in from the engine at start-up)
export const shapeCatalog = { groups: [], shapes: {} };
export const shapeName = (geom) => shapeCatalog.shapes[geom]?.name || GEOM_NAMES[geom] || "Shape";
export function itemText(it) {
  return (it.text?.paragraphs || []).map((p) => (p.runs || []).map((r) => r.t).join("")).join(" ").trim();
}
export function itemLabel(it, doc) {
  if (it.type === "picture") {
    // PowerPoint's default names ("Graphic 4") say less than the file name
    const generic = !it.name || /^(Graphic|Picture|Image|Content Placeholder) \d+$/.test(it.name);
    return (generic ? doc.assets[it.asset]?.name : it.name) || "Picture";
  }
  if (it.type === "line") return `${isCurved(it) ? "Curved " : ""}${it.arrow_end || it.arrow_start ? "arrow" : "line"}`.replace(/^./, (c) => c.toUpperCase());
  if (it.type === "group" && it.clip) return it.name || `Clipping mask (${it.items.length - 1})`;
  if (it.type === "group") return it.name && !/^Group \d+$/.test(it.name) ? it.name : `Group (${it.items.length})`;
  const t = itemText(it);
  return t ? `“${t.slice(0, 40)}”` : shapeName(it.geom);
}

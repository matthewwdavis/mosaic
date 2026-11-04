// Changes to text over all of it or part of it, for the Home tab's Text section (textribbon.js)
// and the properties panel. Part of a text is a range of characters between two positions
// [paragraph, character], counting the characters of each paragraph's runs (a line break is one).

import { clone } from "./util.js";

// The sizes the bigger and smaller buttons step through: PowerPoint's, with the half points
// figure text uses
export const SIZES = [4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44,
  48, 54, 60, 66, 72, 80, 88, 96];
export function nextSize(size, up) {
  if (up) return SIZES.find((s) => s > size + 1e-9) ?? Math.ceil(size + 1e-9) + 12;
  return [...SIZES].reverse().find((s) => s < size - 1e-9) ?? Math.max(0.5, size - 0.5);
}

const before = (a, b) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);
export const ordered = (r) => (before(r.end, r.start) ? { start: r.end, end: r.start } : r);
export const collapsed = (r) => r.start[0] === r.end[0] && r.start[1] === r.end[1];
export const paraLength = (p) => (p.runs || []).reduce((n, r) => n + (r.t || "").length, 0);

// A paragraph's runs split at characters `from` and `to`; returns the pieces between them
function cut(p, from, to) {
  const runs = [], inside = [];
  let at = 0;
  for (const r of p.runs || []) {
    const t = r.t || "", end = at + t.length;
    if (!t.length) { runs.push(r); continue; }
    const marks = [at, ...[from, to].filter((x) => x > at && x < end), end].sort((a, b) => a - b);
    for (let i = 0; i < marks.length - 1; i++) {
      if (marks[i] === marks[i + 1]) continue;
      const piece = { ...r, t: t.slice(marks[i] - at, marks[i + 1] - at) };
      runs.push(piece);
      if (marks[i] >= from && marks[i + 1] <= to) inside.push(piece);
    }
    at = end;
  }
  p.runs = runs;
  return inside;
}
// Neighbouring runs that look the same become one
function merge(p) {
  const out = [];
  for (const r of p.runs || []) {
    const last = out[out.length - 1];
    if (last && JSON.stringify({ ...last, t: 0 }) === JSON.stringify({ ...r, t: 0 })) last.t += r.t;
    else out.push({ ...r });
  }
  p.runs = out;
}

// Changes a text in place: run(r) for each run in the range (all of them with no range, an empty
// box's empty run too), para(p) for each paragraph it touches, body(text) for the text itself
export function formatText(text, range, { run, para, body } = {}) {
  const ps = text.paragraphs || [];
  const r = range ? ordered(range) : { start: [0, 0], end: [ps.length - 1, Infinity] };
  for (let i = Math.max(r.start[0], 0); i <= r.end[0] && i < ps.length; i++) {
    const p = ps[i];
    if (run) {
      const from = i === r.start[0] ? r.start[1] : 0, to = i === r.end[0] ? Math.min(r.end[1], paraLength(p)) : paraLength(p);
      const hit = range ? (from < to ? cut(p, from, to) : []) : p.runs || [];
      hit.forEach(run);
      merge(p);
    }
    if (para) para(p);
  }
  if (body) body(text);
  return text;
}

// The runs a range covers, as copies (none for a range with nothing in it)
export function runsIn(paragraphs, range) {
  const ps = clone(paragraphs), r = ordered(range), out = [];
  for (let i = Math.max(r.start[0], 0); i <= r.end[0] && i < ps.length; i++) {
    const from = i === r.start[0] ? r.start[1] : 0, to = i === r.end[0] ? r.end[1] : paraLength(ps[i]);
    if (from < to) out.push(...cut(ps[i], from, to));
  }
  return out;
}

// The one value all of them share, or undefined
export function common(values) {
  const keys = values.map((v) => JSON.stringify(v ?? null));
  return keys.length && keys.every((k) => k === keys[0]) ? values[0] : undefined;
}

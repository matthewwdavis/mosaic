// Panel labels stay with their panel. A label made with the Label tool on or near a picture or
// group is attached to it: label.attach {to, corner, dx, dy, seen}. The label's top left corner
// keeps the offset (dx, dy) from that corner of the panel's box, so it goes with the panel when
// the panel moves or changes size. followLabels runs after every change:
// - when the panel's box isn't what it was last time (seen), the label goes to its place by it;
// - otherwise the label may have been moved on its own, so it's measured again from the panel's
//   nearest corner, or attached to another panel it was moved onto (away from its own).
// Both moved together (selected together, or in one group) is the first case, so the label
// moves once. A label whose panel has gone is let go; Detach lets go of one by hand.
import { itemBBox } from "./util.js";

export const NEAR = 14;   // pt (about 5 mm): a label this close to a panel's box is on it
export const CORNER_NAMES = { tl: "top left", tr: "top right", bl: "bottom left", br: "bottom right" };

export const isPanel = (it) => (it.type === "picture" || it.type === "group") && !it.hidden;
const cornerOf = ([x0, y0, x1, y1], c) => [c[1] === "r" ? x1 : x0, c[0] === "b" ? y1 : y0];
const distTo = ([px, py], [x0, y0, x1, y1]) => Math.hypot(Math.max(x0 - px, 0, px - x1), Math.max(y0 - py, 0, py - y1));
export const middle = (f) => [f[0] + f[2] / 2, f[1] + f[3] / 2];
const holds = (group, it) => group.type === "group" && group.items.some((k) => k === it || holds(k, it));

// The panel point p is on or near among sibling objects: one it's inside (the smallest, if it's
// in several), else the nearest within NEAR
export function panelAt(items, p, { except = null, label = null } = {}) {
  let best = null, key = null;
  for (const it of items) {
    if (!isPanel(it) || it.id === except || (label && holds(it, label))) continue;
    const b = itemBBox(it), k = [distTo(p, b), (b[2] - b[0]) * (b[3] - b[1])];
    if (k[0] > NEAR) continue;
    if (!best || k[0] < key[0] - 1e-9 || (Math.abs(k[0] - key[0]) <= 1e-9 && k[1] < key[1])) [best, key] = [it, k];
  }
  return best;
}

export function nearestCorner(p, box) {
  const d = (c) => Math.hypot(cornerOf(box, c)[0] - p[0], cornerOf(box, c)[1] - p[1]);
  return Object.keys(CORNER_NAMES).reduce((a, c) => (d(c) < d(a) - 1e-9 ? c : a));
}

export function followLabels(items) {
  const byId = new Map(), siblings = new Map();
  const walk = (list) => list.forEach((it) => {
    byId.set(it.id, it);
    siblings.set(it.id, list);
    if (it.type === "group") walk(it.items);
  });
  walk(items);
  for (const label of [...byId.values()].filter((it) => it.attach && it.frame)) {
    let panel = byId.get(label.attach.to);
    if (!panel || !isPanel(panel) || holds(panel, label)) { delete label.attach; continue; }
    let box = itemBBox(panel);
    const seen = label.attach.seen;
    if (seen && box.some((v, i) => Math.abs(v - seen[i]) > 1e-9)) {
      const [cx, cy] = cornerOf(box, label.attach.corner);
      const x = cx + label.attach.dx, y = cy + label.attach.dy;
      if (Math.abs(x - label.frame[0]) > 1e-9 || Math.abs(y - label.frame[1]) > 1e-9) label.frame = [x, y, label.frame[2], label.frame[3]];
    } else {
      const p = middle(label.frame);
      const other = distTo(p, box) > NEAR && panelAt(siblings.get(label.id), p, { except: panel.id, label });
      if (other) [panel, box] = [other, itemBBox(other)];
      const corner = nearestCorner(p, box), [cx, cy] = cornerOf(box, corner);
      label.attach = { to: panel.id, corner, dx: label.frame[0] - cx, dy: label.frame[1] - cy };
    }
    label.attach.seen = box;
  }
}

// Panel labels in a journal's look -------------------------------------------------------
// A journal's labels (journals.py): {font, size, bold, case, form}, form being how a letter is
// written ("a", "(a)", "a."). A panel label is a text box made with the Label tool
// (panel_label), or one that's just a letter, bracketed or with a full stop.
const LETTER = /^\(?([A-Za-z])[).]?$/;
const RUN_DEFAULT = { font: "Helvetica", size: 6, bold: false };
export const textOf = (it) => (it.text?.paragraphs || []).map((p) => (p.runs || []).map((r) => r.t || "").join("")).join("\n").trim();
export const isPanelLabel = (it) => it?.type === "shape" && !!it.textbox && (!!it.panel_label || LETTER.test(textOf(it)));
export const labelLetter = (t) => t.match(LETTER)?.[1] || null;
const cased = (s, c) => (c === "upper" ? s.toUpperCase() : s.toLowerCase());
// A letter as labels are written: in the look's case and form
export const asLabel = (letter, look) => (look?.form || "a").replace("a", cased(letter, look?.case || "lower"));
// The labels' look on a page with a journal's size, or null
export const pageLabels = (page, journals) => (journals || []).find((j) => j.name === page?.preset?.journal)?.labels || null;

// Every panel label among items takes a journal's look: all of it where there was no journal
// before (from: null), else what still matches the journal before, so what was changed by hand
// in a label stays. Returns how many labels changed
export function restyleLabels(items, from, to) {
  let n = 0;
  const walk = (list) => {
    for (const it of list) {
      if (it.type === "group") walk(it.items);
      else if (isPanelLabel(it) && restyleLabel(it, from, to)) n++;
    }
  };
  walk(items);
  return n;
}
function restyleLabel(it, from, to) {
  const before = JSON.stringify(it.text), follows = (k, v) => !from || (v ?? RUN_DEFAULT[k]) === from[k];
  for (const r of it.text.paragraphs.flatMap((p) => p.runs || [])) {
    for (const k of ["font", "size", "bold"]) if (to[k] !== undefined && follows(k, r[k])) r[k] = to[k];
  }
  // The letter: its case and form; other text the Label tool made, just its case
  const t = textOf(it), letter = labelLetter(t);
  if (letter && it.text.paragraphs.length === 1 && (!from || t === asLabel(letter, from))) {
    const p = it.text.paragraphs[0], run = (p.runs || []).find((r) => (r.t || "").trim()) || p.runs[0];
    p.runs = [{ ...run, t: asLabel(letter, to) }];
  } else if (!letter && to.case && (!from || t === cased(t, from.case))) {
    for (const r of it.text.paragraphs.flatMap((p) => p.runs || [])) r.t = cased(r.t || "", to.case);
  }
  return JSON.stringify(it.text) !== before;
}

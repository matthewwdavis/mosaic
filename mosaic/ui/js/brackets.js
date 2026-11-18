// Significance brackets: a bar with an end tick at each side and a label beyond it, drawn by the
// engine (resolve._bracket). Across (dir up or down) the ticks are as long as the frame leaves
// below (or above) the label's room, so that room must stay in step with the label and its size.
// The line is `stroke`, as a line's (dashes, ends, corners, transparency); brackets made before
// 2026-11-18 had color, line_width and swatch, and become stroke when a figure opens or they're
// pasted (upgradeItems). The label takes the line's colour.

export const STAR_LABELS = [["*", "*"], ["**", "**"], ["***", "***"], ["****", "****"], ["ns", "ns"]];

// Labels: a plain `label`, or a rich one (`text`, a text box's paragraphs and runs, the runs
// holding only what differs from the whole label's font, size, bold and italic; `label` then its
// letters). A quick-set p-value is rich, its letter in italics, and keeps `pset` {v, sig} while
// it's as set, so it re-letters when the page's journal (or the figure's choice of p or P)
// changes; changed by hand (sig no longer its letters and their italics), it keeps what it is.
export const P_VALUES = ["0.1", "0.05", "0.01", "0.001", "0.0001"];
const P_DEFAULT = { letter: "p", italic: true, space: true, zero: true };
// How the page writes P values: its journal's house style (info.p_styles; lowercase where it
// doesn't say), with the figure's own choice of letter over it (doc.meta.p_letter)
export function pStyle(page, info, doc) {
  const js = (info?.p_styles || {})[page?.preset?.journal] || {};
  const st = { ...P_DEFAULT };
  for (const k of ["italic", "space", "zero"]) if (typeof js[k] === "boolean") st[k] = js[k];
  if (js.letter === "P") st.letter = "P";
  if (doc?.meta?.p_letter === "p" || doc?.meta?.p_letter === "P") st.letter = doc.meta.p_letter;
  return st;
}
export const pText = (v, st) => `${st.letter}${st.space ? " < " : "<"}${st.zero ? v : v.replace(/^0(?=\.)/, "")}`;
export const pLabels = (st) => P_VALUES.map((v) => [`p:${v}`, pText(v, st)]);
export const BRACKET_LABELS = [...STAR_LABELS];   // (the plain ones; p-values follow the page's style: pLabels)
// A rich label's letters, and its letters with whether each run is in italics (as drawn)
const runsOf = (it) => (it.text?.paragraphs || []).flatMap((p, i) => [...(i ? [{ t: "\n" }] : []), ...(p.runs || [])]).filter((r) => r.t);
export const plainOf = (it) => (it.text ? runsOf(it).map((r) => r.t).join("") : it.label || "");
const sigOf = (it) => JSON.stringify(runsOf(it).map((r) => [r.t, !!(r.italic ?? it.italic)]));
// A quick-set p-value: its letter in italics (as the style says), the rest as the whole label
export function setQuickP(it, v, st) {
  const letter = { t: st.letter, ...(st.italic ? { italic: true } : {}) };
  it.text = { paragraphs: [{ runs: [letter, { t: pText(v, st).slice(1) }] }] };
  it.label = plainOf(it);
  it.pset = { v, sig: sigOf(it) };
}
// A plain label (a star, ns, text typed with nothing formatted): no letter-by-letter formatting
export function setPlainLabel(it, label) {
  it.label = label;
  delete it.text;
  delete it.pset;
}
// Text typed in the panel: letters that stay as they were keep their formatting (what's typed
// takes the formatting of the letter before it); with no rich label, it stays plain
export function retext(it, label) {
  if (!it.text) return setPlainLabel(it, label);
  const runs = runsOf(it).flatMap((r) => [...r.t].map((ch) => ({ ...r, t: ch })));
  const was = runs.map((r) => r.t).join(""), now = [...label];
  let a = 0;
  while (a < runs.length && a < now.length && runs[a].t === now[a]) a++;
  let b = 0;
  while (b < runs.length - a && b < now.length - a && runs[runs.length - 1 - b].t === now[now.length - 1 - b]) b++;
  const like = (i) => ({ ...(runs[Math.max(i - 1, 0)] || {}) });
  const mid = now.slice(a, now.length - b).map((ch) => ({ ...like(a), t: ch }));
  const chars = [...runs.slice(0, a), ...mid, ...runs.slice(runs.length - b)];
  if (was === label) return;
  // Back into runs of one look, a paragraph per line
  const paragraphs = [{ runs: [] }];
  for (const c of chars) {
    if (c.t === "\n") { paragraphs.push({ runs: [] }); continue; }
    const runs1 = paragraphs.at(-1).runs, last = runs1.at(-1), { t, ...look } = c;
    if (last && JSON.stringify({ ...last, t: undefined }) === JSON.stringify({ ...look, t: undefined })) last.t += t;
    else runs1.push({ ...look, t });
  }
  it.text = { paragraphs };
  it.label = plainOf(it);
}
// A whole-label look (font, size, bold, italic) for the whole label: the bracket's, its letters'
// own taken off so they follow it
export function setLabelKey(it, k, v) {
  if (v === undefined || v === null) delete it[k];
  else it[k] = v;
  for (const p of it.text?.paragraphs || []) for (const r of p.runs || []) delete r[k];
}
// The whole label's look, for a rich label's runs while it's typed in
export const labelLook = (it) => ({ font: it.font || "Helvetica", size: it.size ?? 6, bold: !!it.bold, italic: !!it.italic });
// After typing: the runs keep only what differs from the whole label
export function trimRuns(it) {
  const look = labelLook(it);
  for (const p of it.text?.paragraphs || []) {
    delete p.style;
    for (const r of p.runs || []) for (const k of Object.keys(look)) if (r[k] === look[k]) delete r[k];
  }
}
// Every bracket among items (in groups too): its label kept as its rich label's letters, and a
// quick-set's link dropped once changed by hand (canvas.followLinks, on every change)
export function syncLabels(items) {
  for (const it of items || []) {
    if (it.type === "group") syncLabels(it.items);
    if (it.type !== "bracket") continue;
    if (it.text) it.label = plainOf(it);
    if (it.pset && sigOf(it) !== it.pset.sig) delete it.pset;
  }
}
// Quick-set p-values still as set, in the page's style now (a journal chosen, p or P switched):
// how many changed. The bar stays put
export function followPValues(items, st) {
  let n = 0;
  for (const it of items || []) {
    if (it.type === "group") n += followPValues(it.items, st);
    if (it.type !== "bracket" || !it.pset) continue;
    if (sigOf(it) !== it.pset.sig) { delete it.pset; continue; }
    if (plainOf(it) === pText(it.pset.v, st) && !!runsOf(it)[0]?.italic === !!st.italic) continue;
    const [first, ...rest] = runsOf(it), keep = { ...(rest.at(-1) || first || {}) }, lead = { ...(first || {}) };
    keepBar(it, (b) => {
      setQuickP(b, b.pset.v, st);
      const [l, r] = b.text.paragraphs[0].runs;
      b.text.paragraphs[0].runs = [{ ...lead, ...l, t: l.t, italic: l.italic }, { ...keep, t: r.t }];
      if (!st.italic) delete b.text.paragraphs[0].runs[0].italic;
      b.pset.sig = sigOf(b);
    });
    n++;
  }
  return n;
}
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

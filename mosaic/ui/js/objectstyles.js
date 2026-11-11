// Object styles: named looks for lines and shapes saved in the figure (doc.object_styles: [{id,
// name, stroke, fill, outline, arrow_start, arrow_end}], each with only what the object it was
// made from has: a line's style has no fill, a closed shape's no arrowheads). An object using one
// has object_style: id and keeps the look on itself. A change made to one object stays as an
// override: when the style changes, only what still matches the old style follows, part by part
// for the line, fill and outline (colour, width, dashes...), whole for the arrowheads.
import { clone, shapeCatalog } from "./util.js";

export const KEYS = ["stroke", "fill", "outline", "arrow_start", "arrow_end"];
const BY_PART = new Set(["stroke", "fill", "outline"]);
const PART_DEFAULTS = { opacity: 1, swatch: null, even_dashes: false, dash: "solid", dash_spacing: 1 };
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const samePart = (k, a, b) => JSON.stringify(a ?? PART_DEFAULTS[k] ?? null) === JSON.stringify(b ?? PART_DEFAULTS[k] ?? null);

// What an object's look can have: lines and shapes have a line (not area fills) and an outline;
// shapes a fill; lines and open shapes arrowheads
export function takes(it, key) {
  if (it.type !== "line" && it.type !== "shape") return false;
  if (key === "stroke") return it.geom !== "region";
  if (key === "fill") return it.type === "shape";
  if (key === "arrow_start" || key === "arrow_end") return it.type === "line" || it.geom === "custom" || !!shapeCatalog.shapes[it.geom]?.open;
  return true;
}

// A style's look, from an object
export function formatOf(it) {
  const f = {};
  for (const k of KEYS) if (takes(it, k)) f[k] = clone(it[k] ?? null);
  return f;
}

// An object takes a style's whole look (what it can have)
export function applyObjectStyle(it, style) {
  if (it.type === "group") { it.items.forEach((k) => applyObjectStyle(k, style)); return; }
  if (it.type !== "line" && it.type !== "shape") return;
  it.object_style = style.id;
  for (const k of KEYS) if (k in style && takes(it, k)) it[k] = clone(style[k]);
}

// Whether an object differs anywhere from its style
export function differs(it, style) {
  return KEYS.some((k) => {
    if (!(k in style) || !takes(it, k)) return false;
    const a = it[k] ?? null, s = style[k] ?? null;
    if (!BY_PART.has(k) || a === null || s === null) return !same(a, s);
    return [...new Set([...Object.keys(a), ...Object.keys(s)])].some((p) => !samePart(p, a[p], s[p]));
  });
}

// Every line and shape in the figure, symbols' objects included
export function styledObjects(doc) {
  const out = [];
  const walk = (items) => items.forEach((it) => { if (it.type === "group") walk(it.items); else out.push(it); });
  for (const pg of doc.pages || []) walk(pg.items);
  for (const sym of doc.symbols || []) walk(sym.items);
  return out;
}

// A style changed from `old` to `neu`: in the objects using it, what still matched the old style
// follows; overrides stay
export function restyle(doc, old, neu) {
  for (const it of styledObjects(doc)) {
    if (it.object_style !== old.id) continue;
    for (const k of KEYS) {
      if (!takes(it, k) || !(k in old || k in neu)) continue;
      const a = it[k] ?? null, o = old[k] ?? null, n = neu[k] ?? null;
      if (!BY_PART.has(k) || a === null || o === null || n === null) {
        if (same(a, o)) it[k] = clone(n);
        continue;
      }
      const next = { ...a };
      for (const p of new Set([...Object.keys(a), ...Object.keys(o), ...Object.keys(n)])) {
        if (!samePart(p, a[p], o[p])) continue;
        if (n[p] === undefined) delete next[p];
        else next[p] = clone(n[p]);
      }
      it[k] = next;
    }
  }
}

// "1 pt line, filled": a style's look in words
export function describeLook(st) {
  const parts = [];
  if ("stroke" in st) parts.push(st.stroke ? `${+(st.stroke.width ?? 1).toFixed(2)} pt ${st.stroke.dash && st.stroke.dash !== "solid" ? `${st.stroke.dash} ` : ""}line` : "no line");
  if ("fill" in st) parts.push(st.fill ? (st.fill.gradient ? "gradient fill" : "filled") : "no fill");
  if (st.outline?.width) parts.push("outlined");
  if (st.arrow_end || st.arrow_start) parts.push("arrowheads");
  return parts.join(", ");
}

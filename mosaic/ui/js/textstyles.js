// Text styles: named text formats saved in the figure (doc.text_styles: [{id, name, ...format}]).
// A paragraph using one has style: id and keeps the format on its own runs. A change made to one
// text stays as an override: when the style changes, only what still matches the old style follows.
// A scale bar's or bracket's label can use one too (text_style: id), taking its font, size, bold
// and italic (LABEL_FORMAT); its colour stays the bar's or line's, the object being one colour.
import { clone } from "./util.js";

export const RUN_FORMAT = ["font", "size", "bold", "italic", "underline", "color", "swatch"];
export const PARA_FORMAT = ["align", "line_spacing", "space_before", "space_after"];
export const LABEL_FORMAT = ["font", "size", "bold", "italic"];
const DEFAULTS = { bold: false, italic: false, underline: false, swatch: null, align: "l", line_spacing: null, space_before: 0,
  space_after: 0 };
const same = (k, a, b) => JSON.stringify(a ?? DEFAULTS[k] ?? null) === JSON.stringify(b ?? DEFAULTS[k] ?? null);

// Sets a format key, leaving it out when there's nothing to say
export function setFormat(o, k, v) {
  if (v === undefined || v === null || (k === "swatch" && !v)) delete o[k];
  else o[k] = clone(v);
}

// A style's format, from a text's first paragraph and run
export function formatOf(item) {
  const para = item.text?.paragraphs?.find((p) => p.runs?.length) || item.text?.paragraphs?.[0] || {};
  const run = para.runs?.[0] || {};
  const f = {};
  for (const k of RUN_FORMAT) if (run[k] !== undefined && run[k] !== null) f[k] = clone(run[k]);
  for (const k of PARA_FORMAT) if (para[k] !== undefined && para[k] !== null) f[k] = clone(para[k]);
  return f;
}

// A paragraph (or every paragraph of a text) takes a style's whole format
export function applyToParagraph(p, style) {
  p.style = style.id;
  for (const k of PARA_FORMAT) setFormat(p, k, style[k]);
  for (const r of p.runs || []) for (const k of RUN_FORMAT) setFormat(r, k, style[k]);
}
export function applyTextStyle(item, style) {
  for (const p of item.text?.paragraphs || []) applyToParagraph(p, style);
}

// A scale bar's or bracket's label takes a style's font, size, bold and italic; whether it differs
export function applyToLabel(bar, style) {
  bar.text_style = style.id;
  for (const k of LABEL_FORMAT) setFormat(bar, k, style[k]);
}
export const labelDiffers = (bar, style) => LABEL_FORMAT.some((k) => !same(k, bar[k], style[k]));

// Every scale bar and bracket in the document (their labels can use a text style)
export function labelItems(doc) {
  const out = [];
  const walk = (items) => items.forEach((it) => {
    if (it.type === "group") walk(it.items);
    else if (it.type === "scalebar" || it.type === "bracket") out.push(it);
  });
  for (const pg of doc.pages || []) walk(pg.items);
  for (const sym of doc.symbols || []) walk(sym.items);
  return out;
}

// Whether a paragraph differs anywhere from the style it uses
export function differs(p, style) {
  return PARA_FORMAT.some((k) => !same(k, p[k], style[k]))
    || (p.runs || []).some((r) => RUN_FORMAT.some((k) => !same(k, r[k], style[k])));
}

// Every paragraph in the document, with its text object
export function paragraphs(doc) {
  const out = [];
  const walk = (items) => {
    for (const it of items) {
      if (it.type === "group") walk(it.items);
      for (const p of it.text?.paragraphs || []) out.push([p, it]);
    }
  };
  for (const pg of doc.pages || []) walk(pg.items);
  for (const sym of doc.symbols || []) walk(sym.items);   // symbols' text too
  return out;
}

// A style changed from `old` to `neu`: in the paragraphs using it, what still matched the old
// style follows; overrides stay
export function restyle(doc, old, neu) {
  for (const [p] of paragraphs(doc)) {
    if (p.style !== old.id) continue;
    for (const k of PARA_FORMAT) if (same(k, p[k], old[k])) setFormat(p, k, neu[k]);
    for (const r of p.runs || []) for (const k of RUN_FORMAT) if (same(k, r[k], old[k])) setFormat(r, k, neu[k]);
  }
  for (const bar of labelItems(doc)) {
    if (bar.text_style === old.id) for (const k of LABEL_FORMAT) if (same(k, bar[k], old[k])) setFormat(bar, k, neu[k]);
  }
}

// "Helvetica 8 pt, bold, centred": a style's format in words
export function describeFormat(st) {
  const parts = [`${st.font || "Helvetica"} ${st.size || 6} pt`];
  if (st.bold) parts.push("bold");
  if (st.italic) parts.push("italic");
  if (st.underline) parts.push("underlined");
  if (st.align === "ctr") parts.push("centred");
  if (st.align === "r") parts.push("right-aligned");
  return parts.join(", ");
}

// Copying one object's look onto others (Copy style / Paste style, the Format Painter): whatever
// the target can take, as with PowerPoint's Format Painter. "No line" and "no fill" are copied too.
import { clone, shapeCatalog } from "./util.js";

const RUN_KEYS = ["font", "size", "bold", "italic", "color", "swatch", "underline"];
const PARA_KEYS = ["align", "line_spacing", "space_before", "space_after", "style"];   // with swatch and text style links

const takesEnds = (it) => it.type === "line" || it.geom === "custom" || !!shapeCatalog.shapes[it.geom]?.open;
const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o[k] !== undefined).map((k) => [k, clone(o[k])]));

// An object's style; a group's is its first part's that has one
export function styleOf(it) {
  if (it.type === "group") return it.items.map(styleOf).find(Boolean) || null;
  if (it.type === "scalebar" || it.type === "bracket") return null;
  if (it.type === "picture") return { opacity: it.opacity ?? 1 };
  const st = {};
  if (it.geom !== "region") st.stroke = clone(it.stroke ?? null);   // an area fill has no line to copy
  st.outline = clone(it.outline ?? null);
  if (it.type === "shape") {
    st.fill = clone(it.fill ?? null);
    if (it.geom !== "region") st.rounding = it.rounding || 0;
    const para = it.text?.paragraphs?.find((p) => p.runs?.length);
    if (para) st.text = { run: pick(para.runs[0], RUN_KEYS), para: pick(para, PARA_KEYS) };
  }
  if (takesEnds(it)) {
    st.arrow_start = clone(it.arrow_start ?? null);
    st.arrow_end = clone(it.arrow_end ?? null);
  }
  return st;
}

// Paints a style onto an object (a group's parts each)
export function applyStyle(it, st) {
  if (it.type === "scalebar" || it.type === "bracket") return;   // their look is set in their own tab
  if (it.type === "group") {
    it.items.forEach((k) => applyStyle(k, st));
    return;
  }
  if (it.type === "picture") {
    if (st.opacity !== undefined) it.opacity = st.opacity;
    return;
  }
  // A line keeps its own line rather than vanish; an area fill has none
  if (st.stroke !== undefined && it.geom !== "region" && (st.stroke || it.type !== "line")) it.stroke = clone(st.stroke);
  if (st.outline !== undefined) it.outline = clone(st.outline);
  if (it.type === "shape") {
    if (st.fill !== undefined) it.fill = clone(st.fill);
    if (st.rounding !== undefined && shapeCatalog.shapes[it.geom]?.corners) {
      if (st.rounding) it.rounding = st.rounding;
      else delete it.rounding;
    }
    if (st.text) {
      for (const p of it.text?.paragraphs || []) {
        for (const k of PARA_KEYS) {
          if (k in st.text.para) p[k] = clone(st.text.para[k]);
          else delete p[k];
        }
        for (const r of p.runs || []) {
          for (const k of RUN_KEYS) {
            if (k in st.text.run) r[k] = clone(st.text.run[k]);
            else delete r[k];
          }
        }
      }
    }
  }
  if (st.arrow_start !== undefined && takesEnds(it)) {
    it.arrow_start = clone(st.arrow_start);
    it.arrow_end = clone(st.arrow_end);
  }
}

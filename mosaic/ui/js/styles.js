// Copying one object's look onto others (Copy style / Paste style, the Format Painter): whatever
// the target can take, as with PowerPoint's Format Painter. "No line" and "no fill" are copied too.
// Between two scale bars or two brackets, the whole look; between them and lines and shapes, what
// they have in common: a line's colour and width (a scale bar's colour and thickness), the
// outline, and a label's font, size, bold and italic (from a text box's text too). Pictures copy
// their transparency, border and its outline to pictures.
import { clone, shapeCatalog } from "./util.js";
import { bracketStroke, keepBar, upgradeItems } from "./brackets.js";

const RUN_KEYS = ["font", "size", "bold", "italic", "color", "swatch", "underline"];
const PARA_KEYS = ["align", "line_spacing", "space_before", "space_after", "style"];   // with swatch and text style links

const takesEnds = (it) => it.type === "line" || it.geom === "custom" || !!shapeCatalog.shapes[it.geom]?.open;
const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o[k] !== undefined).map((k) => [k, clone(o[k])]));
const LABEL_KEYS = ["font", "size", "bold", "italic", "text_style", "gap"];   // a scale bar's or bracket's label
const BAR_KEYS = ["color", "swatch", "thickness", "ends", "opacity", "label"];   // a scale bar's own look
const put = (o, k, v) => { if (v === undefined || v === null) delete o[k]; else o[k] = clone(v); };
// A scale bar's or bracket's outline on a line or shape: round the lines, if it went round them
const lineOutline = (o) => {
  if (!o || o.lines === false) return null;
  const { lines, text, ...rest } = o;   // eslint-disable-line no-unused-vars
  return rest;
};

// An object's style; a group's is its first part's that has one
export function styleOf(it) {
  if (it.type === "group") return it.items.map(styleOf).find(Boolean) || null;
  if (it.type === "scalebar") {
    return { kind: "scalebar", bar: pick(it, BAR_KEYS), label: pick(it, LABEL_KEYS), outline: clone(it.outline ?? null),
      stroke: { color: it.color || "#ffffff", width: it.thickness ?? 2, ...(it.swatch ? { swatch: it.swatch } : {}) }, partial: true };
  }
  if (it.type === "bracket") {
    return { kind: "bracket", stroke: clone(bracketStroke(it)), outline: clone(it.outline ?? null), label: pick(it, LABEL_KEYS) };
  }
  if (it.type === "picture") return { opacity: it.opacity ?? 1, border: clone(it.border ?? null), outline: clone(it.outline ?? null) };
  const st = { object_style: it.object_style ?? null };   // with its object style's link
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
  if (it.type === "scalebar") return onScaleBar(it, st);
  if (it.type === "bracket") return onBracket(it, st);
  if (it.type === "group") {
    it.items.forEach((k) => applyStyle(k, st));
    return;
  }
  if (it.type === "picture") {
    if (st.opacity !== undefined) it.opacity = st.opacity;
    if (st.border !== undefined) {   // (from another picture)
      put(it, "border", st.border);
      put(it, "outline", st.border ? st.outline : null);
    }
    return;
  }
  if (st.kind) {   // a scale bar's or bracket's look on a line or shape: line colour and width, outline
    if (st.stroke && it.geom !== "region") {
      it.stroke = st.partial ? { color: "#000000", width: 1, dash: "solid", cap: "flat", join: "round", opacity: 1, ...(it.stroke || {}),
        ...clone(st.stroke) } : clone(st.stroke);
    }
    if (st.outline !== undefined) it.outline = lineOutline(st.outline);
    return;
  }
  if (st.object_style !== undefined) {
    if (st.object_style) it.object_style = st.object_style;
    else delete it.object_style;
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

// A label's look from a style: a scale bar's or bracket's whole, or a text box's font, size, bold
// and italic
function labelOf(st) {
  if (st.label) return { whole: true, look: st.label };
  const run = st.text?.run;
  return run ? { whole: false, look: pick(run, ["font", "size", "bold", "italic"]) } : null;
}
function putLabel(it, st) {
  const lab = labelOf(st);
  if (lab) for (const k of lab.whole ? LABEL_KEYS : Object.keys(lab.look)) put(it, k, lab.look[k]);
}
// Onto a scale bar: another's whole look, or a line's colour and width as its colour and thickness
function onScaleBar(it, st) {
  if (st.kind === "scalebar") for (const k of BAR_KEYS) put(it, k, st.bar[k]);
  else if (st.stroke) {
    it.color = st.stroke.color;
    put(it, "swatch", st.stroke.swatch);
    it.thickness = st.stroke.width;
  }
  if (st.outline !== undefined) it.outline = clone(st.outline);
  putLabel(it, st);
}
// Onto a bracket (its bar staying put): another's whole look, or a line's (it keeps a line)
function onBracket(it, st) {
  upgradeItems([it]);
  keepBar(it, (b) => {
    if (st.stroke) b.stroke = st.partial ? { ...b.stroke, ...clone(st.stroke) } : clone(st.stroke);
    if (st.outline !== undefined) b.outline = clone(st.outline);
    putLabel(b, st);
  });
}

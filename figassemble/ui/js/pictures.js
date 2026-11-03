// Small pictures of the Style tab's choices, for its picture menus (inspector.pictureField): a
// dash, a line's end or corner, an arrowhead, an outline's sides and gaps, a fill, a shape, in the
// object's own colours (grey where one is too faint to see against the menu). Dashes, arrowheads and
// outlines are drawn by the engine, exactly as on the page; ends, corners, fills and routes are
// simple drawings of the same thing.

import { rpc } from "./api.js";
import { luminance, parseHex, pathIcon, s, shapeCatalog } from "./util.js";

const LINE_BOX = [44, 14];       // a line's picture, points (shown at 1 px a point)
const SHAPE_BOX = [44, 18];
const FAINT = 2;                 // contrast with the menu below which a colour is too faint to see (white on white 1, black on white 21)
const FAINT_INK = "#fe01fd";     // stands in for currentColor in what the engine draws
const cache = new Map();         // what an engine picture draws (its item as JSON) -> its SVG
let queue = null, made = 0;

// The colour to draw something of the object's in: its own, or the menu's grey where that's too
// faint to see against the menu (black in a dark theme, white or pale yellow in a light one). The
// grey is currentColor, from .pic-ink in app.css, so a highlighted menu row's text colour takes over
function ink(color, faint = "currentColor") {
  const c = parseHex(color), bg = parseHex(getComputedStyle(document.documentElement).getPropertyValue("--panel"));
  if (!c || !bg) return color;
  const [a, b] = [luminance(c), luminance(bg)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) < FAINT ? faint : color;
}

// An item drawn by the engine in a box of points, filled in when the drawing arrives. Pictures
// asked for together go in one request, and each drawing is kept for next time
function enginePicture(item, [w, ht]) {
  const svg = s("svg", { viewBox: `0 0 ${w} ${ht}`, width: w, height: ht, class: "pic-svg pic-ink", "aria-hidden": "true" });
  const g = s("g");
  svg.append(g);
  const key = JSON.stringify(item);
  if (cache.has(key)) {
    g.innerHTML = cache.get(key);
    return svg;
  }
  if (!queue) {
    queue = new Map();
    queueMicrotask(async () => {
      const asked = [...queue.entries()];
      queue = null;
      let drawn = [];
      try { drawn = await rpc("resolve", {}, asked.map(([, a]) => ({ ...a.item, id: `pic${++made}` })), [], []); } catch { return; }
      asked.forEach(([k, a], i) => {
        const got = (drawn[i]?.svg || "").replaceAll(FAINT_INK, "currentColor");
        cache.set(k, got);
        for (const el of a.els) el.innerHTML = got;
      });
    });
  }
  const pending = queue.get(key) || { item, els: [] };
  pending.els.push(g);
  queue.set(key, pending);
  return svg;
}
function drawing([w, ht], ...parts) {
  const svg = s("svg", { viewBox: `0 0 ${w} ${ht}`, width: w, height: ht, class: "pic-svg", "aria-hidden": "true" });
  svg.append(...parts);
  return svg;
}
// A drawing in the object's colours, grey where they're too faint (ink)
function inkDrawing(box, ...parts) {
  const svg = drawing(box, ...parts);
  svg.classList.add("pic-ink");
  return svg;
}
// The object's line for a picture: its colour and dash, thick enough to see, thin enough to fit
const pictureStroke = (st, extra = {}) => ({ cap: "round", join: "round", ...(st || {}), opacity: 1,
  width: Math.min(Math.max(st?.width ?? 1, 0.75), 2.5), ...extra, color: ink(st?.color || "#000000", FAINT_INK) });
const colourOf = (st) => ink(st?.color || "#000000");
const across = () => ({ type: "line", points: [[4, LINE_BOX[1] / 2], [LINE_BOX[0] - 4, LINE_BOX[1] / 2]] });

export function dashPicture(st, dash) {
  return enginePicture({ ...across(), stroke: pictureStroke(st, { dash }) }, LINE_BOX);
}
// A thick stub ending at a hairline, so a round or square end shows how far past it it reaches
export function capPicture(st, cap) {
  return inkDrawing([40, 14], s("line", { x1: 8, y1: 7, x2: 28, y2: 7, stroke: colourOf(st), "stroke-width": 6,
    "stroke-linecap": cap === "flat" ? "butt" : cap }), s("line", { x1: 28, y1: 1, x2: 28, y2: 13, class: "pic-guide" }));
}
// A right-angled corner of a thick line, drawn as its outline with the inside lightly shaded, so a
// sharp corner is square, a round one rounded and a bevelled one cut across. (A solid line thin
// enough to look light can't show them apart: they differ only at the outer edge of a thick line.)
export function joinPicture(st, join) {
  const [x, y, half, bottom] = [14.25, 7.75, 5.5, 20];   // the corner, half the line's width, the picture's bottom
  const top = `M0 ${y - half}H${join === "miter" ? x + half : x}`
    + (join === "round" ? `A${half} ${half} 0 0 1 ${x + half} ${y}` : join === "bevel" ? `L${x + half} ${y}` : "");
  const colour = colourOf(st);
  return inkDrawing([22, 20], s("path", { d: `${top}V${bottom}H${x - half}V${y + half}H0Z`, fill: colour, "fill-opacity": 0.25 }),
    s("path", { d: `${top}V${bottom}M0 ${y + half}H${x - half}V${bottom}`, fill: "none", stroke: colour, "stroke-width": 1.5 }));
}
// A line with an arrowhead at the end the list is for, of the kind and size given
export function headPicture(it, end, type, size) {
  const head = type && type !== "none" ? { type, w: size, len: size, ...(it[end]?.rounding ? { rounding: it[end].rounding } : {}) } : null;
  return enginePicture({ ...across(), stroke: pictureStroke(it.stroke, { dash: "solid", width: 1.25 }),
    [end]: head, [end === "arrow_end" ? "arrow_start" : "arrow_end"]: null }, LINE_BOX);
}
// A small copy of the object wearing a look ({stroke, fill, outline, arrow_start, arrow_end}): a
// line across for something with no inside, else its own shape (a rounded box for a freeform)
function miniature(it, look, hasInside) {
  const stroke = look.stroke ? pictureStroke(look.stroke, { width: 1.5 }) : null;
  const outline = look.outline ? { ...look.outline, opacity: 1, width: Math.min(Math.max(look.outline.width ?? 1, 1.5), 2.5),
    color: ink(look.outline.color || "#ffffff", FAINT_INK) } : null;
  if (!hasInside) {
    return enginePicture({ ...across(), stroke, outline, arrow_start: look.arrow_start || null, arrow_end: look.arrow_end || null }, LINE_BOX);
  }
  const info = shapeCatalog.shapes[it.geom];
  const geom = it.geom !== "custom" && info?.closed ? it.geom : "roundRect";
  return enginePicture({ type: "shape", geom, adj: geom === it.geom ? it.adj : undefined, rounding: it.rounding, frame: [9, 4, 26, 10],
    rot: 0, fill: look.fill ? { ...look.fill, color: ink(look.fill.color, FAINT_INK) } : null, stroke, outline }, SHAPE_BOX);
}
// The object with its outline's sides and gaps as given, in its own dash, so gaps show
export function outlinePicture(it, type, hasInside) {
  return miniature(it, { stroke: it.stroke, fill: it.fill, outline: { ...it.outline, type } }, hasInside);
}
// The object with an object style's look (objectstyles.js), or its own with none
export function stylePicture(it, style) {
  const look = { stroke: it.stroke, fill: it.fill, outline: it.outline, arrow_start: it.arrow_start, arrow_end: it.arrow_end };
  for (const k of Object.keys(look)) if (style && k in style) look[k] = style[k];
  const inside = it.type === "shape" && (!!look.fill || it.geom === "custom" || !!shapeCatalog.shapes[it.geom]?.closed);
  return miniature(it, look, inside);
}
let gradients = 0;
// A square: no fill (crossed out), a colour, or a gradient across or out from a point
export function fillPicture(it, mode, center = null) {
  const g = it.fill?.gradient, stops = g?.stops || [{ pos: 0, color: it.fill?.color || "#4a90d9" }, { pos: 1, color: "#ffffff" }];
  const box = s("rect", { x: 1, y: 1, width: 14, height: 14, rx: 1.5, class: "pic-box" });
  if (mode === "none") {
    box.setAttribute("fill", "#ffffff");
    return drawing([16, 16], box, s("line", { x1: 3, y1: 13, x2: 13, y2: 3, class: "pic-none" }));
  }
  if (mode === "solid") box.setAttribute("fill", it.fill?.color || stops[0].color);
  else {
    const id = `pic-grad-${++gradients}`;
    const grad = mode === "radial"
      ? s("radialGradient", { id, cx: (center || g?.center || [0.5, 0.5])[0], cy: (center || g?.center || [0.5, 0.5])[1], r: 0.9 })
      : s("linearGradient", { id, x1: 0, y1: 0, x2: 0, y2: 1 });
    for (const st of stops) grad.append(s("stop", { offset: st.pos, "stop-color": st.color, "stop-opacity": st.opacity ?? 1 }));
    const defs = s("defs");
    defs.append(grad);
    box.setAttribute("fill", `url(#${id})`);
    return drawing([16, 16], defs, box);
  }
  return drawing([16, 16], box);
}
// A shape's line or none
export function linePicture(st, on) {
  return inkDrawing([16, 16], s("rect", { x: 2, y: 2, width: 12, height: 12, rx: 1.5, fill: "none",
    ...(on ? { stroke: colourOf(st || {}), "stroke-width": 2 } : { class: "pic-none-box" }) }));
}
export function routePicture(route) {
  return drawing([40, 14], route === "elbow"
    ? s("polyline", { points: "6,12 20,12 20,2 34,2", class: "pic-line" })
    : s("line", { x1: 6, y1: 12, x2: 34, y2: 2, class: "pic-line" }));
}
export function pathPicture(curve) {
  return drawing([40, 14], curve === "smooth"
    ? s("path", { d: "M5 11 C10 2 15 2 20 7 S30 12 35 3", class: "pic-line" })
    : s("polyline", { points: "5,11 15,3 25,11 35,3", class: "pic-line" }));
}
// A shape's icon, as in the Shapes menu
export function shapePicture(geom) {
  return geom ? pathIcon(shapeCatalog.shapes[geom]?.icon || "M4 6h16v12H4z") : drawing([16, 16], s("rect", { x: 2, y: 2,
    width: 12, height: 12, class: "pic-none-box" }));
}

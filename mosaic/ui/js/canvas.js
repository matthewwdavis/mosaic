// The page canvas: rendering, selection, direct manipulation, drawing tools, cropping, in-place
// text editing, the grid, guides and snapping. Page coordinates are points; 100% zoom is true size.

import { assetUrl, rpc } from "./api.js";
import { store } from "./store.js";
import { followGrids } from "./gridlayout.js";
import { followLabels, panelAt } from "./labels.js";
import { finishEdits } from "./symbols.js";
import { moveHandle, moveNode, nearestOn, ringsOf, segments, splitAt, toLocal, toPageOf, toggleSmooth, writeRings } from "./pen.js";
import { followScaleBars } from "./scalebar.js";
import { ZOOM_ROUNDING, followZooms } from "./zoom.js";
import { labelRoom } from "./brackets.js";
import { applyTextStyle } from "./textstyles.js";
import { collapsed, formatText, ordered, paraLength } from "./textformat.js";
import {
  PX_PER_PT, announce, apply, clamp, describeItem, distToSegment, edgeReach, emptyShape, frameMatrix, h, hitItem, invert, isMac,
  itemBBox, itemLabel, itemCorners, itemsBBox, keepFieldKeys, lengthText, lineMidpoints, lineSamples, mul, nearestStretch,
  pointInPoly, rotate, s, shapeCatalog, svgMatrix, translate, uid,
} from "./util.js";

const HANDLE = 8;             // handle size, CSS px
const SNAP_PX = 6;            // snapping distance, CSS px
const GUIDE_HIT = 4;          // how near (CSS px) the pointer must be to grab a guide
const SITE_PX = 8;            // how near (CSS px) a line end must come to attach to a connection point
const GRID_MIN_PX = 6;        // grid lines closer than this on screen aren't drawn, or snapped to
const ROT_OFFSET = 24;        // rotation handle distance above the frame, CSS px
const SEL_GAP = 6;            // the selection box and its handles stand this far outside the object, CSS px
const REACH = 64;             // scrolling stops with this much of the page and its objects still in view, CSS px
const HIT = document.createElement("canvas").getContext("2d");   // tells whether a point is on a shape's outline
HIT.lineJoin = HIT.lineCap = "round";
const SVG_PREVIEW_LIMIT = 8e6; // bigger SVGs preview as rendered PDFs for speed
const DEFAULT_SIZE = (72 / 2.54) * 2;   // a click (or Enter) with a drawing tool places a 2 cm object
// The notes over the page (a preview on, editing inside a group, a finished export): presses on
// them and their buttons are theirs, not the page's
const NOTES = ".cvd-note, .scope-note, .done-note";
// Colour vision previews: linear-RGB matrices, Machado, Oliveira & Fernandes 2009 at full strength
export const COLOUR_VISION = {
  deuteranopia: { name: "deuteranopia (red-green, no green cones)",
    rows: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]] },
  protanopia: { name: "protanopia (red-green, no red cones)",
    rows: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]] },
  tritanopia: { name: "tritanopia (blue-yellow, no blue cones)",
    rows: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]] },
  greyscale: { name: "greyscale", rows: [[0.2126, 0.7152, 0.0722], [0.2126, 0.7152, 0.0722], [0.2126, 0.7152, 0.0722]] },
};
// A preview's matrix as an feColorMatrix's values (alpha kept), or null for normal vision
export function visionMatrix(mode) {
  const m = COLOUR_VISION[mode];
  return m ? m.rows.map((r) => `${r.join(" ")} 0 0`).join(" ") + " 0 0 0 1 0" : null;
}
// The drawing tools that make preset shapes, and which preset each draws
const TOOL_GEOMS = { rect: "rect", roundrect: "roundRect", ellipse: "ellipse", triangle: "triangle", arc: "arc",
  bracket: "rightBracket" };
// The key held to add objects to the selection a click at a time: ⌘ on a Mac (where Control-click
// is a right-click), Ctrl elsewhere
const addKey = (e) => e.metaKey || (e.ctrlKey && !isMac);
// Whether any of the stretch from a to b lies in a box [x0, y0, x1, y1] (Liang-Barsky clipping)
function segInBox([ax, ay], [bx, by], [x0, y0, x1, y1]) {
  const dx = bx - ax, dy = by - ay;
  let t0 = 0, t1 = 1;
  for (const [p, q] of [[-dx, ax - x0], [dx, x1 - ax], [-dy, ay - y0], [dy, y1 - ay]]) {
    if (p === 0) {
      if (q < 0) return false;
      continue;
    }
    const r = q / p;
    if (p < 0) { if (r > t1) return false; t0 = Math.max(t0, r); }
    else { if (r < t0) return false; t1 = Math.min(t1, r); }
  }
  return true;
}

export const canvas = {
  zoom: 1,
  panX: 48,
  panY: 48,
  tool: "select",
  shapeGeom: null,           // the preset the Shapes menu's tool draws
  els: new Map(),            // item id -> {g, key, geomKey, origin}
  pending: new Map(),        // item id -> item awaiting the engine
  op: null,
  cropping: null,
  editing: null,
  spaceDown: false,
  snapGuides: [],
  reordering: false,         // objects are being dragged in the Objects list (panels.js)
  onToolChange: null,
  defaults: null,

  init(stage) {
    this.stage = stage;
    this.svg = s("svg", { class: "scene", "aria-hidden": "true" });
    this.view = s("g");
    this.pageShadow = s("rect", { class: "page-shadow" });
    this.pageRect = s("rect", { class: "page" });
    this.itemsLayer = s("g", { class: "items" });
    this.ghostLayer = s("g", { class: "ghost" });
    // The grid and guides lie over the objects (pictures would hide them) and under the handles
    this.gridLayer = s("g", { class: "grid" });
    this.guidesLayer = s("g", { class: "guides" });
    this.view.append(this.pageShadow, this.pageRect, this.ghostLayer, this.itemsLayer, this.gridLayer, this.guidesLayer);
    this.overlay = s("g", { class: "overlay" });
    this.cvdMatrix = s("feColorMatrix", { type: "matrix" });
    const cvd = s("filter", { id: "fa-cvd", "color-interpolation-filters": "linearRGB" });
    this.defs = s("defs");
    cvd.append(this.cvdMatrix);
    this.defs.append(cvd);
    this.svg.append(this.defs, this.view, this.overlay);
    stage.append(this.svg);
    this.cvdNote = h("div", { class: "cvd-note", role: "status", hidden: true });
    this.scopeNote = h("div", { class: "scope-note", role: "status", hidden: true });
    // Notes along the top of the page, one under another (an export's goes here too: panels.doneNote)
    this.notes = h("div", { class: "stage-notes" }, this.cvdNote);
    stage.append(this.notes, this.scopeNote);
    this.setRulers(this.defaults?.show_rulers !== false);
    store.afterChange = (doc) => this.followLinks(doc);
    this.editor = h("div", { class: "text-editor", contenteditable: "true", spellcheck: "false", hidden: true,
      role: "textbox", "aria-multiline": "true", "aria-label": "Text being edited" });
    stage.append(this.editor);
    new ResizeObserver(() => this.layout()).observe(stage);
    stage.addEventListener("pointerdown", (e) => this.pointerDown(e));
    stage.addEventListener("pointermove", (e) => this.pointerMove(e));
    stage.addEventListener("pointerup", (e) => this.pointerUp(e));
    stage.addEventListener("pointercancel", (e) => this.pointerUp(e, true));
    stage.addEventListener("dblclick", (e) => this.doubleClick(e));
    stage.addEventListener("wheel", (e) => this.wheel(e), { passive: false });
    stage.addEventListener("contextmenu", (e) => {
      if (this.editing && this.editor.contains(e.target)) return;   // text being typed keeps its own menu
      e.preventDefault();
      if (this.op || e.target.closest?.(NOTES)) return;
      if (this.editing) this.commitEdit();
      if (this.cropping) this.endCrop();
      this.onContextMenu?.(e.clientX, e.clientY);
    });
    this.editor.addEventListener("keydown", (e) => this.editorKey(e));
    // Typing after a change from the ribbon: ⌘Z is the text's own again (undoTyping)
    this.editor.addEventListener("input", () => { if (this.editing) this.editing.typed = true; });
    store.on((what, detail) => {
      if (what === "doc") { this.render(detail); this.loadPlotLines(); }
      else if (what === "selection") this.drawOverlay();
      else if (what === "page") { this.els.clear(); this.itemsLayer.replaceChildren(); this.fit(); }
    });
  },

  // View ------------------------------------------------------------------------

  get k() { return this.zoom * PX_PER_PT; },
  layout() {
    const r = this.stage.getBoundingClientRect();
    this.svg.setAttribute("width", r.width);
    this.svg.setAttribute("height", r.height);
    this.applyView();
  },
  applyView() {
    this.keepInReach();
    this.view.setAttribute("transform", `translate(${this.panX} ${this.panY}) scale(${this.k})`);
    this.drawGrid();
    this.drawOverlay();
    this.drawGuidePreview();
    this.updatePreviews();
    this.positionEditor();
    document.dispatchEvent(new CustomEvent("fa-zoom", { detail: this.zoom }));
  },
  fit() {
    if (!store.doc) return;
    const p = store.page();
    const r = this.stage.getBoundingClientRect();
    const z = Math.min((r.width - 64) / (p.width * PX_PER_PT), (r.height - 64) / (p.height * PX_PER_PT));
    this.zoom = clamp(z, 0.05, 32);
    this.panX = (r.width - p.width * this.k) / 2;
    this.panY = (r.height - p.height * this.k) / 2;
    this.applyView();
  },
  // Scrolling goes anywhere round the page, objects off it included, but stops while the last
  // REACH px of the page and its objects are still in view, so they can't be lost off the edge
  keepInReach() {
    if (!store.doc) return;
    const p = store.page(), r = this.stage.getBoundingClientRect(), k = this.k;
    let [x0, y0, x1, y1] = [0, 0, p.width, p.height];
    for (const it of p.items) {
      const b = itemBBox(it);
      [x0, y0, x1, y1] = [Math.min(x0, b[0]), Math.min(y0, b[1]), Math.max(x1, b[2]), Math.max(y1, b[3])];
    }
    this.panX = clamp(this.panX, REACH - x1 * k, r.width - REACH - x0 * k);
    this.panY = clamp(this.panY, REACH - y1 * k, r.height - REACH - y0 * k);
  },
  // The page in the middle of the view, at the zoom it has
  centre() {
    if (!store.doc) return;
    const p = store.page(), r = this.stage.getBoundingClientRect();
    this.panX = (r.width - p.width * this.k) / 2;
    this.panY = (r.height - p.height * this.k) / 2;
    this.applyView();
  },
  setZoom(z, cx, cy) {
    const r = this.stage.getBoundingClientRect();
    cx = cx ?? r.width / 2;
    cy = cy ?? r.height / 2;
    const [px, py] = this.toPage(cx, cy);
    this.zoom = clamp(z, 0.05, 32);
    this.panX = cx - px * this.k;
    this.panY = cy - py * this.k;
    this.applyView();
  },
  toPage(x, y) { return [(x - this.panX) / this.k, (y - this.panY) / this.k]; },
  toScreen(x, y) { return [this.panX + x * this.k, this.panY + y * this.k]; },
  eventPoint(e) {
    const r = this.stage.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  },

  // Rendering -------------------------------------------------------------------------

  render(detail = {}) {
    if (!store.doc) return;
    const page = store.page();
    this.pageRect.setAttribute("width", page.width);
    this.pageRect.setAttribute("height", page.height);
    this.pageRect.setAttribute("fill", page.background || "#ffffff");
    this.pageRect.classList.toggle("transparent", !page.background);
    this.pageShadow.setAttribute("width", page.width);
    this.pageShadow.setAttribute("height", page.height);
    const seen = new Set();
    this.syncChildren(this.itemsLayer, page.items, seen);
    for (const id of [...this.els.keys()]) if (!seen.has(id)) { this.els.get(id).g.remove(); this.els.delete(id); }
    this.markScope();
    this.flushResolve();
    this.drawGrid();
    this.drawGuides();
    this.drawOverlay();
    if (this.cropping) this.drawGhost();
    if (this.editing) this.positionEditor();   // (a box fitted to its text again, after a change from the ribbon)
  },
  // Inside a group being edited (isolation mode), everything outside it is faded, and a note
  // over the page names the group, with a button to leave it
  markScope() {
    for (const e of this.els.values()) e.g.classList.remove("outside-scope");
    let items = store.page().items;
    const names = [];
    for (const id of store.scope) {
      // (Not while objects are dragged in the Objects list, so the new order shows plainly)
      if (!this.reordering) for (const it of items) if (it.id !== id) this.els.get(it.id)?.g.classList.add("outside-scope");
      const g = items.find((it) => it.id === id);
      if (!g) break;
      names.push(itemLabel(g, store.doc));
      items = g.items;
    }
    this.scopeNote.hidden = !names.length;
    if (names.length && this.scopeNote.dataset.path !== store.scope.join("/")) {
      this.scopeNote.dataset.path = store.scope.join("/");
      this.scopeNote.replaceChildren(`Editing inside ${names.join(" › ")} `, h("button", { type: "button", class: "btn",
        onclick: () => { store.exitGroup(); announce("Left the group"); } }, "Leave group"));
    } else if (!names.length) this.scopeNote.dataset.path = "";
  },
  syncChildren(parent, items, seen) {
    items.forEach((it, i) => {
      seen.add(it.id);
      let e = this.els.get(it.id);
      if (!e) {
        e = { g: s("g", { "data-id": it.id }), key: null };
        this.els.set(it.id, e);
      }
      if (parent.children[i] !== e.g) parent.insertBefore(e.g, parent.children[i] || null);
      e.g.style.display = it.hidden ? "none" : "";
      if (it.type === "group") {
        e.g.removeAttribute("transform");
        this.syncChildren(e.g, it.items, seen);
        while (e.g.children.length > it.items.length) e.g.lastChild.remove();
        // A clipping mask: the top part's shape clips the rest and isn't drawn itself
        const mask = it.clip && it.items.length > 1 ? it.items[it.items.length - 1] : null;
        if (mask) this.els.get(mask.id).g.style.display = "none";
        this.clipTo(e, it.id, mask, false);
      } else if (it.type === "picture") {
        this.renderPicture(it, e);
      } else {
        this.renderVector(it, e);
      }
    });
  },
  // Pictures are drawn here directly: the frame maps the cropped source box
  renderPicture(it, e) {
    const asset = store.doc.assets[it.asset];
    if (!asset) return;
    const key = JSON.stringify([it.frame, it.crop, it.rot, it.flip_h, it.flip_v, it.opacity, it.page_index,
      asset.variants, this.previewBucket(it), it.mask, it.border]);
    if (e.key === key) return;
    e.key = key;
    const [sw, sh] = (asset.page_sizes && asset.page_sizes[it.page_index || 0]) || asset.size_pt;
    const [l, t, r, b] = it.crop || [0, 0, 0, 0];
    const x0 = l * sw, y0 = t * sh, x1 = sw - r * sw, y1 = sh - b * sh;
    const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v);
    const inner = s("svg", { x: 0, y: 0, width: Math.max(it.frame[2], 1e-3), height: Math.max(it.frame[3], 1e-3),
      viewBox: `${x0} ${y0} ${Math.max(x1 - x0, 1e-6)} ${Math.max(y1 - y0, 1e-6)}`, preserveAspectRatio: "none",
      overflow: "hidden" });
    const img = s("image", { width: sw, height: sh, preserveAspectRatio: "none", href: this.previewUrl(it, asset) });
    inner.append(img);
    // (a shape crop clips this, in the frame's own units: on the inner svg it would be in the file's)
    const framed = s("g");
    framed.append(inner);
    e.g.replaceChildren(framed);
    e.g.setAttribute("transform", svgMatrix(m));
    e.g.setAttribute("opacity", it.opacity ?? 1);
    // A border round the frame, or round the shape it's cropped to (once the engine sends it)
    e.borderEl = null;
    if (it.border?.width > 0) {
      e.borderEl = s(it.mask ? "path" : "rect", { class: "picture-border", fill: "none", stroke: it.border.color || "#000000",
        "stroke-width": it.border.width, x: 0, y: 0, width: it.frame[2], height: it.frame[3] });
      e.g.append(e.borderEl);
    }
    this.clipTo(e, it.id, it.mask ? it : null, true, framed);   // cropped to a shape, in its own frame
  },
  // A clip from the engine (area_path): a picture's crop shape in its frame, or a clipping
  // mask's shape on the page. Asked for again only when the shape changes
  clipTo(e, id, source, local, target = e.g) {
    const key = source ? JSON.stringify([local, source.type, source.geom, source.frame, source.rot, source.flip_h, source.flip_v,
      source.adj, source.rounding, source.path, source.mask, source.fill?.even_odd]) : null;
    const cid = `fa-area-${id}`;
    if (e.clipKey === key) {   // the same clip, put back on a redrawn picture
      if (key && e.clipD) {
        target.setAttribute("clip-path", `url(#${cid})`);
        if (e.borderEl?.tagName === "path") e.borderEl.setAttribute("d", e.clipD);
      }
      return;
    }
    e.clipKey = key;
    e.clipD = null;
    if (!key) {
      target.removeAttribute("clip-path");
      this.defs.querySelector(`[id="${cid}"]`)?.remove();
      return;
    }
    rpc("area_path", source, local).then((res) => {
      if (e.clipKey !== key) return;   // changed again meanwhile
      let cp = this.defs.querySelector(`[id="${cid}"]`);
      if (!cp) {
        cp = s("clipPath", { id: cid, clipPathUnits: "userSpaceOnUse" });
        cp.append(s("path"));
        this.defs.append(cp);
      }
      cp.firstChild.setAttribute("d", res?.d || "M0 0");
      cp.firstChild.setAttribute("clip-rule", res?.even_odd ? "evenodd" : "nonzero");
      e.clipD = res?.d || "M0 0";
      target.setAttribute("clip-path", `url(#${cid})`);
      if (e.borderEl?.tagName === "path") e.borderEl.setAttribute("d", e.clipD);
    }).catch((err) => console.error(err));
  },
  previewVariant(asset) {
    const v = asset.variants;
    if (v.svg && v.svg.bytes < SVG_PREVIEW_LIMIT) return v.svg;
    return v.pdf || v.svg || v.png || v.jpeg || v.tiff;
  },
  previewBucket(it) {
    const asset = store.doc.assets[it.asset];
    const v = asset && this.previewVariant(asset);
    if (!v || v.kind !== "pdf") return 0;
    const [sw] = asset.size_pt;
    const [l, , r] = it.crop || [0, 0, 0, 0];
    const pictureScale = it.frame[2] / Math.max(sw * (1 - l - r), 1e-6);
    const need = this.k * (window.devicePixelRatio || 1) * pictureScale;
    return Math.min(16, 2 ** Math.ceil(Math.log2(Math.max(need, 0.5))));
  },
  previewUrl(it, asset) {
    const v = this.previewVariant(asset);
    return assetUrl(v, this.previewBucket(it), it.page_index || 0);
  },
  updatePreviews() {
    if (!store.doc) return;
    const walk = (items) => items.forEach((it) => {
      if (it.type === "group") walk(it.items);
      else if (it.type === "picture") { const e = this.els.get(it.id); if (e) this.renderPicture(it, e); }
    });
    walk(store.items());
  },
  // Shapes, lines and text come from the engine as SVG (same code as SVG export)
  geomKey(it) {
    const c = JSON.parse(JSON.stringify(it));
    if (c.geom === "region") {
      // An area fill follows its lines and shapes: drawn again whenever they change. Its frame
      // and seed follow from them, so they don't count
      c.lines = (c.region?.items || []).map((id) => findDeep(store.items(), id) || null);
      c.region = { items: c.region?.items };
      delete c.frame; delete c.name; delete c.alt; delete c.locked;
      return [JSON.stringify(c), [0, 0]];
    }
    // A symbol's copy is drawn again whenever a symbol changes
    if (c.type === "symbol") c.symbols = store.doc.symbols || [];
    let origin = [0, 0];
    if (c.frame) { origin = [c.frame[0], c.frame[1]]; c.frame = [0, 0, c.frame[2], c.frame[3]]; }
    if (c.points) { origin = c.points[0].slice(); c.points = c.points.map((p) => [p[0] - origin[0], p[1] - origin[1]]); }
    delete c.name; delete c.alt; delete c.locked;
    return [JSON.stringify(c), origin];
  },
  // What an object covers as drawn (its line, arrowheads, text) where it is now: the engine's
  // box, moved along with it (only moved, it isn't drawn again), or else its frame's
  drawnBox(it) {
    const e = this.els.get(it.id), [gk, origin] = this.geomKey(it);
    if (!e?.bbox || !e.origin || e.geomKey !== gk) return itemBBox(it);
    const dx = origin[0] - e.origin[0], dy = origin[1] - e.origin[1];
    return [e.bbox[0] + dx, e.bbox[1] + dy, e.bbox[2] + dx, e.bbox[3] + dy];
  },
  renderVector(it, e) {
    const [gk, origin] = this.geomKey(it);
    if (e.geomKey === gk && e.origin) {
      // Only moved: shift what's drawn instead of asking the engine again
      const dx = origin[0] - e.origin[0], dy = origin[1] - e.origin[1];
      e.g.setAttribute("transform", dx || dy ? `translate(${dx} ${dy})` : "");
      return;
    }
    this.pending.set(it.id, it);
  },
  // One request to the engine at a time, always with the latest changes: during a drag the
  // drawing keeps up with the pointer without flooding the engine
  flushResolve() {
    if (!this.pending.size || this._resolveQueued) return;
    this._resolveQueued = true;
    queueMicrotask(() => { this._resolveQueued = false; this.resolveNow(); });
  },
  async resolveNow() {
    while (this._inflight) await this._inflight;
    const items = [...this.pending.values()];
    this.pending.clear();
    if (!items.length) return;
    this._inflight = this.resolveItems(items);
    try { await this._inflight; } finally { this._inflight = null; }
    if (this.pending.size) await this.resolveNow();
  },
  async resolveItems(items) {
    // What each item looked like when sent: if it changes meanwhile, it's drawn again
    const keys = items.map((it) => this.geomKey(it));
    // Area fills need the lines and shapes round them
    const sent = new Set(items.map((it) => it.id)), context = [];
    for (const it of items) {
      for (const id of it.geom === "region" ? it.region?.items || [] : []) {
        const b = !sent.has(id) && findDeep(store.items(), id);
        if (b) { sent.add(id); context.push(b); }
      }
    }
    let results;
    try {
      results = await rpc("resolve", this.assetSizes(), items, context, store.doc.symbols || []);
    } catch (err) { console.error(err); return; }
    const autofit = [], areas = [];
    results.forEach((r, i) => {
      if (!this.showDrawn(items[i], r, keys[i])) return;
      if (r.autofit_frame) autofit.push([r.id, r.autofit_frame]);
      if (r.region) areas.push([r.id, r.region]);
    });
    if (autofit.length || areas.length) {
      store.silent((doc) => {
        for (const [id, f] of autofit) {
          const it = findDeep(doc.pages[store.pageIndex].items, id);
          if (it) it.frame = f;
        }
        // An area fill's box and seed as its area is now; its path is kept for copying it
        for (const [id, a] of areas) {
          const it = findDeep(doc.pages[store.pageIndex].items, id);
          if (!it) continue;
          it.frame = a.frame;
          it.region = { ...it.region, seed: a.seed };
          const e = this.els.get(id);
          if (e) e.regionPath = a.path;
        }
      });
      this.render({});
    }
    this.drawOverlay();
  },

  assetSizes() {
    const assets = {};
    for (const [id, a] of Object.entries(store.doc.assets)) assets[id] = { size_pt: a.size_pt, page_sizes: a.page_sizes };
    return assets;
  },
  // Put what the engine drew for an item on the page; false if it's gone. `key` is the item
  // as it was drawn (geomKey), when it may have changed since
  showDrawn(it, r, key = this.geomKey(it)) {
    const e = this.els.get(r.id);
    if (!e) return false;
    const [gk, origin] = key;
    e.g.innerHTML = r.svg;
    e.g.removeAttribute("transform");
    e.geomKey = gk;
    e.origin = origin;
    e.bbox = r.bbox;
    e.handles = r.handles || null;
    e.outline = r.outline ? { fill: r.outline.fill.map((d) => new Path2D(d)), line: r.outline.line.map((d) => new Path2D(d)),
      evenOdd: r.outline.even_odd } : null;
    const before = JSON.stringify(e.sites || null);
    e.sites = r.sites || null;
    this.pending.delete(it.id);
    // Exact connection points just arrived: attached lines take them up
    if (JSON.stringify(e.sites) !== before && this.linkedTo(it.id)) queueMicrotask(() => { store.silent(() => {}); store.emit("doc", {}); });
    return true;
  },

  // Overlay (screen coordinates) ------------------------------------------------------

  drawOverlay() {
    if (!this.overlay || !store.doc) return;
    const o = this.overlay;
    o.replaceChildren();
    const sel = store.selected();
    if (this.pen) {
      this.drawSnapGuides(o);
      this.drawPen(o);
      return;
    }
    if (this.pointEdit && !(sel.length === 1 && sel[0].id === this.pointEdit.id && sel[0].geom === "custom")) this.pointEdit = null;
    if (this.op?.type === "draw") {
      this.drawPreview(o);
      this.drawSnapGuides(o);
      this.drawSites(o);
      return;
    }
    if (this.op?.type === "measure") {
      const [a, b] = [this.toScreen(...this.op.start), this.toScreen(...this.op.cur)];
      o.append(s("line", { class: "measure-line", x1: a[0], y1: a[1], x2: b[0], y2: b[1] }));
      return;
    }
    if (this.op?.type === "zoombox") {
      const [a, b] = [this.toScreen(...this.op.start), this.toScreen(...this.op.cur)];
      const [x, y, w, ht] = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1])];
      const shape = this.op.shape, r = shape === "round" ? (ZOOM_ROUNDING * Math.min(w, ht)) / 2 : 0;
      o.append(shape === "ellipse" || shape === "circle"
        ? s("ellipse", { class: "measure-line", cx: x + w / 2, cy: y + ht / 2, rx: w / 2, ry: ht / 2, fill: "none" })
        : s("rect", { class: "measure-line", x, y, width: w, height: ht, rx: r, fill: "none" }));
      return;
    }
    this.drawSnapGuides(o);
    this.drawSites(o);
    if (this.op?.type === "guide") this.drawGuideLabel(o);
    if (this.op?.type === "marquee") {
      const [ax, ay] = this.op.start, [bx, by] = this.op.cur;
      o.append(s("rect", { class: this.op.touch ? "marquee touch" : "marquee", x: Math.min(ax, bx), y: Math.min(ay, by),
        width: Math.abs(bx - ax), height: Math.abs(by - ay) }));
    }
    if (this.editing) return;
    if (sel.length === 1 && this.pointEdit) {
      this.drawPointEdit(o, sel[0]);
    } else if (sel.length === 1 && !this.cropping) {
      this.drawAttachment(o, sel[0]);
      this.drawHandles(sel[0]);
    } else if (sel.length > 1) {
      const key = this.keyObject?.();
      for (const it of sel) {
        const cls = it.id === key?.id ? "sel-outline key" : "sel-outline thin";
        o.append(it.type === "line" ? this.outline(itemCorners(it), cls) : this.outlineAround(itemCorners(it), cls));
      }
      const b = itemsBBox(sel);
      if (b) o.append(this.outlineAround([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], "sel-outline"));
    }
    if (this.cropping) this.drawCropHandles();
    if (this.altDown && !this.op && sel.length) this.drawDistances(o, sel);
  },
  // A selected panel label's panel, dashed, and a line from the corner it keeps to the label
  drawAttachment(o, it) {
    const panel = it.attach && findDeep(store.items(), it.attach.to);
    if (!panel || !it.frame) return;
    const b = itemBBox(panel), corner = it.attach.corner || "tl";
    o.append(this.outlineAround([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], "attach-target"));
    const c = this.toScreen(corner[1] === "r" ? b[2] : b[0], corner[0] === "b" ? b[3] : b[1]), l = this.toScreen(it.frame[0], it.frame[1]);
    o.append(s("line", { class: "attach-link", x1: c[0], y1: c[1], x2: l[0], y2: l[1] }),
      s("circle", { class: "attach-corner", cx: c[0], cy: c[1], r: 3 }));
  },
  // Option held with something selected: its distances to the object under the pointer, or to
  // the page's edges, as Figma shows them: the gap between them, or four inner distances when
  // one is inside the other
  drawDistances(o, sel) {
    const a = itemsBBox(sel);
    if (!a || !this.hoverAt) return;
    const under = this.itemAt(this.hoverAt);
    const target = under && !store.selection.includes(under.id) ? under : null;
    const page = store.page(), b = target ? itemBBox(target) : [0, 0, page.width, page.height];
    const segs = [];
    const inside = (p, q) => p[0] >= q[0] && p[2] <= q[2] && p[1] >= q[1] && p[3] <= q[3];
    if (!target || inside(a, b) || inside(b, a)) {
      const [inner, outer] = inside(a, b) || !target ? [a, b] : [b, a];
      const cx = (inner[0] + inner[2]) / 2, cy = (inner[1] + inner[3]) / 2;
      segs.push([outer[0], cy, inner[0], cy], [inner[2], cy, outer[2], cy], [cx, outer[1], cx, inner[1]], [cx, inner[3], cx, outer[3]]);
    } else {
      const ys = [Math.max(a[1], b[1]), Math.min(a[3], b[3])], xs = [Math.max(a[0], b[0]), Math.min(a[2], b[2])];
      const y = ys[0] <= ys[1] ? (ys[0] + ys[1]) / 2 : (a[1] + a[3]) / 2, x = xs[0] <= xs[1] ? (xs[0] + xs[1]) / 2 : (a[0] + a[2]) / 2;
      if (b[0] >= a[2]) segs.push([a[2], y, b[0], y]);
      else if (b[2] <= a[0]) segs.push([b[2], y, a[0], y]);
      if (b[1] >= a[3]) segs.push([x, a[3], x, b[1]]);
      else if (b[3] <= a[1]) segs.push([x, b[3], x, a[1]]);
      if (!segs.length) segs.push([a[0], y, b[0], y], [x, a[1], x, b[1]]);   // overlapping: between their left and top edges
    }
    if (target) o.append(this.outlineAround([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], "distance-target"));
    const said = [];
    for (const [x0, y0, x1, y1] of segs) {
      const len = Math.hypot(x1 - x0, y1 - y0);
      if (len < 0.01) continue;
      const [p0, p1] = [this.toScreen(x0, y0), this.toScreen(x1, y1)];
      o.append(s("line", { class: "distance", x1: p0[0], y1: p0[1], x2: p1[0], y2: p1[1] }));
      const text = lengthText(len), [mx, my] = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
      const w = text.length * 6.2 + 8;
      o.append(s("rect", { class: "distance-label", x: mx - w / 2, y: my - 8, width: w, height: 16, rx: 3 }));
      const t = s("text", { class: "distance-text", x: mx, y: my + 4, "text-anchor": "middle" });
      t.textContent = text;
      o.append(t);
      said.push(text);
    }
    const what = target ? itemLabel(target, store.doc) : "the page's edges";
    const key = `${target?.id || "page"}:${said.join(",")}`;
    if (this.saidDistances !== key) {
      this.saidDistances = key;
      announce(`To ${what}: ${said.join(", ")}`);
    }
  },
  // Option pressed or let go (main.js), for distances on hover
  setMeasureKey(down) {
    if (this.altDown === down) return;
    this.altDown = down;
    if (this.op?.type === "marquee") this.op.touch = down;   // a box takes what it touches while Option is held
    this.saidDistances = null;
    this.drawOverlay();
  },
  outline(pts, cls) {
    return s("polygon", { class: cls, points: pts.map(([x, y]) => this.toScreen(x, y).join(",")).join(" ") });
  },
  // A box's outline (its four corners in order, on the page) drawn SEL_GAP px outside it along
  // its own sides, so the object's edges show inside it
  outlineAround(corners, cls) {
    const [a, b, c, d] = corners.map(([x, y]) => this.toScreen(x, y));
    const unit = (p, q, fallback) => {
      const l = Math.hypot(q[0] - p[0], q[1] - p[1]);
      return l > 1e-9 ? [(q[0] - p[0]) / l, (q[1] - p[1]) / l] : fallback;
    };
    const ex = unit(a, b, [1, 0]), ey = unit(a, d, [-ex[1], ex[0]]);
    const out = (p, sx, sy) => [p[0] + SEL_GAP * (sx * ex[0] + sy * ey[0]), p[1] + SEL_GAP * (sx * ex[1] + sy * ey[1])];
    const pts = [out(a, -1, -1), out(b, 1, -1), out(c, 1, 1), out(d, -1, 1)];
    return s("polygon", { class: cls, points: pts.map((p) => p.join(",")).join(" ") });
  },
  handlesFor(it) {
    if (it.locked) return [];
    if (it.type === "line" && it.route === "elbow") {
      const n = it.points.length, ends = [0, n - 1].map((i) => ({ kind: "end", index: i, at: this.toScreen(...it.points[i]) }));
      const [p1, p2] = [it.points[1], it.points[2]];
      if (n === 4 && Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 1e-6) ends.push({ kind: "elbow", at: this.toScreen((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2) });
      return ends;
    }
    if (it.type === "line") {
      // Ends and middle points can be dragged; the hollow handle halfway along each stretch
      // adds a point there (dragging one on a straight arrow bends it into a curve)
      const n = it.points.length;
      const pts = it.points.map((p, i) => ({ kind: i === 0 || i === n - 1 ? "end" : "point", index: i,
        at: this.toScreen(p[0], p[1]) }));
      const mids = lineMidpoints(it).map((m) => ({ kind: "mid", index: m.index, at: this.toScreen(m.at[0], m.at[1]) }));
      return [...pts, ...mids];
    }
    if (it.type === "group" || it.geom === "region") return [];   // an area fill takes its shape from its lines
    if (it.type === "scalebar") return [];   // its length comes from its picture's scale
    const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v);
    const [, , w, h] = it.frame;
    const pts = { nw: [0, 0], n: [w / 2, 0], ne: [w, 0], e: [w, h / 2], se: [w, h], s: [w / 2, h], sw: [0, h], w: [0, h / 2] };
    // The shape's own adjust handles (PowerPoint's yellow ones) come first, so they win where
    // they sit on top of a resize handle
    const adjust = it.type === "shape" ? (this.els.get(it.id)?.handles || []).map(([x, y], index) => ({
      kind: "adjust", index, at: this.toScreen(...apply(m, x, y)) })) : [];
    // Resize handles stand SEL_GAP px out from the frame, along its own sides, so they don't
    // cover the object's corners and edges
    const o0 = this.toScreen(...apply(m, 0, 0)), o1 = this.toScreen(...apply(m, 1, 0)), o2 = this.toScreen(...apply(m, 0, 1));
    const norm = ([x, y]) => { const l = Math.hypot(x, y) || 1; return [x / l, y / l]; };
    const ex = norm([o1[0] - o0[0], o1[1] - o0[1]]), ey = norm([o2[0] - o0[0], o2[1] - o0[1]]);
    const out = [...adjust, ...Object.entries(pts).map(([dir, [x, y]]) => {
      const [sx, sy] = [dir.includes("w") ? -1 : dir.includes("e") ? 1 : 0, dir.includes("n") ? -1 : dir.includes("s") ? 1 : 0];
      const [px, py] = this.toScreen(...apply(m, x, y));
      return { kind: "resize", dir, at: [px + SEL_GAP * (sx * ex[0] + sy * ey[0]), py + SEL_GAP * (sx * ex[1] + sy * ey[1])] };
    })];
    // Rotation handle: above the top edge along the frame's own "up"
    const r = rotate(it.rot || 0);
    const [ux, uy] = apply(r, 0, -1);
    const [tx, ty] = this.toScreen(...apply(m, w / 2, 0));
    const up = (ROT_OFFSET + SEL_GAP) * (it.flip_v ? -1 : 1);
    out.push({ kind: "rotate", at: [tx + ux * up, ty + uy * up] });
    return out;
  },
  drawHandles(it) {
    const o = this.overlay;
    if (it.type === "line") {
      o.append(s("polyline", { class: "sel-outline line",
        points: lineSamples(it).map(([x, y]) => this.toScreen(x, y).join(",")).join(" ") }));
    } else {
      o.append(this.outlineAround(itemCorners(it), "sel-outline"));
    }
    for (const hd of this.handlesFor(it)) {
      if (hd.kind === "rotate") {
        o.append(s("circle", { class: "handle rot", cx: hd.at[0], cy: hd.at[1], r: HANDLE / 2 + 1 }));
      } else if (hd.kind === "point") {
        o.append(s("circle", { class: "handle point", cx: hd.at[0], cy: hd.at[1], r: HANDLE / 2 + 1 }));
      } else if (hd.kind === "end" && (hd.index === 0 ? it.start_link : it.end_link)) {
        // An attached end: a green dot, as in PowerPoint
        o.append(s("circle", { class: "handle end linked", cx: hd.at[0], cy: hd.at[1], r: HANDLE / 2 + 1 }));
      } else if (hd.kind === "mid") {
        o.append(s("circle", { class: "handle mid", cx: hd.at[0], cy: hd.at[1], r: HANDLE / 2 - 0.5 }));
      } else if (hd.kind === "elbow") {
        o.append(s("rect", { class: "handle elbow", x: hd.at[0] - HANDLE / 2, y: hd.at[1] - HANDLE / 2, width: HANDLE, height: HANDLE, rx: 2 }));
      } else if (hd.kind === "adjust") {
        const [x, y] = hd.at, d = HANDLE / 2 + 1;
        o.append(s("path", { class: "handle adjust", d: `M${x} ${y - d}L${x + d} ${y}L${x} ${y + d}L${x - d} ${y}Z` }));
      } else {
        o.append(s("rect", { class: `handle ${hd.kind}`, x: hd.at[0] - HANDLE / 2, y: hd.at[1] - HANDLE / 2,
          width: HANDLE, height: HANDLE }));
      }
    }
  },
  handleAt(pt) {
    const sel = store.selected();
    if (this.cropping) return this.cropHandleAt(pt);
    if (this.pointEdit) return null;
    if (sel.length !== 1) return null;
    for (const hd of this.handlesFor(sel[0])) {
      if (Math.abs(pt[0] - hd.at[0]) <= HANDLE && Math.abs(pt[1] - hd.at[1]) <= HANDLE) return hd;
    }
    return null;
  },
  itemAt(p) {
    const tol = 4 / this.k;
    const items = store.scopeItems();   // inside a group being edited, only its parts
    // Inside a clipping mask, its (undrawn) shape is picked only by its edge
    const parent = store.scope.length ? store.item(store.scope[store.scope.length - 1]) : null;
    const maskId = parent?.clip ? parent.items[parent.items.length - 1]?.id : null;
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i];
      if (it.locked) continue;
      if (it.id === maskId) {
        const poly = itemCorners(it);
        if (poly.some((q, j) => distToSegment(p, q, poly[(j + 1) % poly.length]) <= tol)) return it;
        continue;
      }
      if (it.geom === "region" ? this.inArea(it, p) : this.hits(it, p, tol)) return it;
    }
    return null;
  },
  // Whether a click at p picks an object: a shape by what's drawn of it, from the engine's outline
  // (inside its fill, or on its line as wide as it's drawn), and an empty one (no fill, or a clear
  // one) only on its line or its text, so a click inside it reaches what's under it. Text boxes,
  // pictures and the rest by their frames (hitItem)
  hits(it, p, tol) {
    if (it.hidden) return false;
    if (it.type === "group") return it.items.some((c) => this.hits(c, p, tol));
    if (it.type !== "shape" || it.textbox || it.geom === "region") return hitItem(it, p, tol);
    const empty = emptyShape(it), reach = tol + edgeReach(it), at = this.drawnAt(it, p);
    if (!at) {   // (not drawn as it is yet: by its frame)
      return empty ? itemCorners(it).some((q, i, poly) => distToSegment(p, q, poly[(i + 1) % poly.length]) <= reach) : hitItem(it, p, tol);
    }
    const { o, x, y } = at;
    if (!empty && o.fill.some((path) => HIT.isPointInPath(path, x, y, o.evenOdd ? "evenodd" : "nonzero"))) return true;
    HIT.lineWidth = 2 * reach;
    if (o.line.some((path) => HIT.isPointInStroke(path, x, y))) return true;
    return empty && !!it.text && [...this.els.get(it.id).g.querySelectorAll("text")].some((t) => {
      const b = t.getBBox(), m = t.transform.baseVal.consolidate()?.matrix;   // (the box is in the text's own units)
      const q = m ? new DOMPoint(x, y).matrixTransform(m.inverse()) : { x, y };
      return q.x >= b.x - tol && q.x <= b.x + b.width + tol && q.y >= b.y - tol && q.y <= b.y + b.height + tol;
    });
  },
  // Whether p is inside a shape's area (its fill paths as drawn, else its frame), filled or not
  inside(it, p) {
    const at = this.drawnAt(it, p);
    if (!at?.o.fill.length) return pointInPoly(p, itemCorners(it));
    return at.o.fill.some((path) => HIT.isPointInPath(path, at.x, at.y, at.o.evenOdd ? "evenodd" : "nonzero"));
  },
  // A shape's outline as the engine last drew it, and p where it was then (only moved since,
  // it isn't drawn again); null if it has changed otherwise
  drawnAt(it, p) {
    const e = this.els.get(it.id), [gk, origin] = this.geomKey(it);
    if (!e?.outline || e.geomKey !== gk || !e.origin) return null;
    return { o: e.outline, x: p[0] - (origin[0] - e.origin[0]), y: p[1] - (origin[1] - e.origin[1]) };
  },
  // Whether a box on the page [x0, y0, x1, y1] touches an object where a click would pick it: a
  // line within half its width, an area fill in its area, a group by its parts, anything else by
  // its frame (for an Option-drag box)
  touches(it, box) {
    if (it.hidden) return false;
    if (it.type === "group") return it.items.some((c) => this.touches(c, box));
    const mid = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2];
    const edgesIn = (poly) => poly.some((q, i) => segInBox(q, poly[(i + 1) % poly.length], box));
    if (it.type === "line") {
      const w = (it.stroke?.width || 1) / 2, wide = [box[0] - w, box[1] - w, box[2] + w, box[3] + w];
      const pts = lineSamples(it);
      return pts.some((q, i) => i > 0 && segInBox(pts[i - 1], q, wide));
    }
    if (it.geom === "region") {
      const rings = this.els.get(it.id)?.regionPath?.subpaths?.[0]?.cmds?.reduce((out, [op, ...v]) => {
        if (op === "M") out.push([]);
        if (op === "M" || op === "L") out[out.length - 1]?.push([v[0] + it.frame[0], v[1] + it.frame[1]]);
        return out;
      }, []) || [itemCorners(it)];
      return rings.some((r) => r.length > 1 && edgesIn(r)) || this.inArea(it, mid);
    }
    const poly = itemCorners(it);
    return edgesIn(poly) || pointInPoly(mid, poly);
  },
  // Inside an area fill's area as last drawn (its rings, even-odd, so holes don't count)
  inArea(it, p) {
    const sub = this.els.get(it.id)?.regionPath?.subpaths?.[0];
    if (!sub || it.hidden) return false;
    const [x, y] = [p[0] - it.frame[0], p[1] - it.frame[1]];
    let inside = false, start = null, prev = null;
    const edge = (a, b) => { if ((a[1] > y) !== (b[1] > y) && x < a[0] + ((y - a[1]) * (b[0] - a[0])) / (b[1] - a[1])) inside = !inside; };
    for (const [op, ...v] of sub.cmds) {
      if (op === "M") { if (prev && start) edge(prev, start); start = prev = v; }
      else if (op === "L") { edge(prev, v); prev = v; }
      else if (op === "Z" && prev && start) { edge(prev, start); prev = start; }
    }
    return inside;
  },

  // Pointer interaction ---------------------------------------------------------------

  pointerDown(e) {
    if (e.target.closest?.(NOTES)) return;
    if (this.editing && !this.editor.contains(e.target)) { this.commitEdit(); return; }
    if (this.editing) return;
    this.stage.focus({ preventScroll: true });
    const pt = this.eventPoint(e);
    const p = this.toPage(...pt);
    try { this.stage.setPointerCapture(e.pointerId); } catch { /* synthetic or already-released pointer */ }
    if (e.button === 1 || this.spaceDown) {
      this.op = { type: "pan", start: pt, pan: [this.panX, this.panY] };
      return;
    }
    if (e.button !== 0) return;
    if (isMac && e.ctrlKey && !e.metaKey) return;   // Control-click is a right-click: its menu opens from the contextmenu event
    if (this.tool === "fill") { this.onFillArea?.(p); return; }
    if (this.tool === "painter") { this.onPaint?.(this.itemAt(p)); return; }
    if (this.tool === "measure") { this.op = { type: "measure", start: p, cur: p }; return; }
    if (this.tool === "zoom") {   // a box dragged on a picture, for a zoom inset (under another's box, say)
      const pic = store.scopeItems().findLast((it) => it.type === "picture" && !it.locked && hitItem(it, p, 4 / this.k));
      if (pic?.type !== "picture") { announce("Drag on a picture to box the area to enlarge"); return; }
      this.op = { type: "zoombox", pic: pic.id, start: p, cur: p, shape: this.zoomShape || "rect" };
      return;
    }
    if (this.tool === "pen") return this.penDown(p, e);
    if (this.tool !== "select") return this.startDraw(p, e);
    if (this.pointEdit && this.pointDown(pt, p)) return;
    const hd = this.handleAt(pt);
    if (hd) return this.startHandle(hd, p, e);
    const hit = this.itemAt(p);
    if (this.cropping) {
      const it = store.item(this.cropping);
      if (it && hit && hit.id === it.id) return this.startCropMove(it, p);
      this.cropping = null;
      this.ghostLayer.replaceChildren();
    }
    // Inside a selected empty shape, a press without Shift: a drag moves the selection (with ⌘,
    // unsnapped, as for any ⌘-drag), and a click without one picks what's under it (⌘: adds it)
    const holder = !e.shiftKey && store.selected().find((it) => emptyShape(it) && !it.locked && this.inside(it, p));
    if (holder && hit?.id !== holder.id) {
      this.startMove(p, e);
      if (this.op?.type === "move") this.op.through = { id: hit?.id ?? null, add: addKey(e) };
      return;
    }
    // Objects come first; a guide can be dragged where nothing covers it, or by its mark on a ruler
    const guide = hit ? null : this.guideAt(pt);
    if (guide) return this.startGuide(guide.axis, guide.index);
    if (hit) {
      let sel = store.selection;
      const was = sel.includes(hit.id), oneOfSeveral = sel.length > 1 && was, add = addKey(e);
      // Shift-click adds or takes away at once. ⌘-click (Ctrl-click) adds at once, and takes away
      // only on letting go without a drag, so a ⌘-drag moves the selection (without snapping)
      if (e.shiftKey) sel = was ? sel.filter((i) => i !== hit.id) : [...sel, hit.id];
      else if (!was) sel = add ? [...sel, hit.id] : [hit.id];
      store.select(sel);
      if (!e.shiftKey || sel.includes(hit.id)) this.startMove(p, e);
      // Without a drag, a ⌘-click on a selected object takes it away, and a plain click on one of
      // several selected objects makes it the key object
      if (this.op?.type === "move" && !e.shiftKey) {
        if (add && was) this.op.takeAway = hit.id;
        else if (oneOfSeveral && !add) this.op.keyCandidate = hit.id;
      }
      announce(describeItem(hit, store.doc));
    } else {
      // A box from empty page; with Shift or ⌘ (Ctrl) it adds to the selection, so a ⌘-click
      // that misses keeps what was selected. With Option (Alt) it takes what it touches
      const add = e.shiftKey || addKey(e);
      if (!add) store.select([]);
      this.op = { type: "marquee", start: pt, cur: pt, add: add ? [...store.selection] : [], touch: e.altKey };
    }
  },
  pointerMove(e) {
    const pt = this.eventPoint(e);
    const p = this.toPage(...pt);
    document.dispatchEvent(new CustomEvent("fa-cursor", { detail: p }));
    const op = this.op;
    if (!op && e.altKey !== !!this.altDown) this.setMeasureKey(e.altKey);   // a key let go elsewhere
    if (!op && this.pen) { this.penHover = this.snapPoint(p, this.penTargets, e); return this.drawOverlay(); }
    if (!op) return this.hover(pt, p);
    if (op.type === "pen") return this.penDrag(p);
    if (op.type === "pointdrag") return this.pointDragTo(p, e);
    if (op.type === "pan") {
      this.panX = op.pan[0] + pt[0] - op.start[0];
      this.panY = op.pan[1] + pt[1] - op.start[1];
      return this.applyView();
    }
    if (op.type === "marquee") { op.cur = pt; op.touch = e.altKey; return this.drawOverlay(); }
    if (op.type === "zoombox" && op.shape === "circle") {   // a circle: as far as the pointer went either way
      const d = Math.max(Math.abs(p[0] - op.start[0]), Math.abs(p[1] - op.start[1]));
      op.cur = [op.start[0] + (p[0] < op.start[0] ? -d : d), op.start[1] + (p[1] < op.start[1] ? -d : d)];
      return this.drawOverlay();
    }
    if (op.type === "measure" || op.type === "zoombox") { op.cur = p; return this.drawOverlay(); }
    if (op.type === "move") return this.moveTo(p, e);
    if (op.type === "resize") return this.resizeTo(p, e);
    if (op.type === "rotate") return this.rotateTo(p, e);
    if (op.type === "end") return this.endTo(p, e);
    if (op.type === "adjust") return this.adjustTo(p);
    if (op.type === "elbow") return this.elbowTo(p);
    if (op.type === "guide") return this.guideTo(pt, e);
    if (op.type === "draw") return this.drawTo(p, e);
    if (op.type === "crop") return this.cropTo(p, e);
    if (op.type === "cropmove") return this.cropMoveTo(p, e);
  },
  pointerUp(e, cancelled = false) {
    const op = this.op;
    this.op = null;
    try { this.stage.releasePointerCapture(e.pointerId); } catch { /* not captured */ }
    this.snapGuides = [];
    if (!op) return;
    if (op.type === "pen") return;
    if (op.type === "pointdrag") {
      if (op.moved && !cancelled) store.endLive("Move point");
      else store.cancelLive();
      return this.drawOverlay();
    }
    if (op.type === "guide") return this.finishGuide(op, cancelled);
    if (op.type === "marquee") {
      const [ax, ay] = this.toPage(...op.start), [bx, by] = this.toPage(...op.cur);
      const box = [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)];
      if (box[2] - box[0] > 1e-6 || box[3] - box[1] > 1e-6) {
        const touch = e.altKey;   // (Option held as the box is let go)
        const inside = store.scopeItems().filter((it) => {
          if (it.locked || it.hidden) return false;
          if (touch) return this.touches(it, box);
          const b = itemBBox(it);
          return b[0] >= box[0] && b[1] >= box[1] && b[2] <= box[2] && b[3] <= box[3];
        }).map((it) => it.id);
        store.select([...op.add, ...inside]);
        if (inside.length) announce(`${store.selection.length} objects selected`);
      }
      return this.drawOverlay();
    }
    if (op.type === "adjust") {
      // The last pointer position may still be with the engine; finish when it answers
      op.done = true;
      op.cancelled = cancelled;
      if (cancelled) store.cancelLive();
      else if (!op.busy) this.finishAdjust(op);
      return;
    }
    this.sitePointer = this.siteActive = null;
    if (op.type === "zoombox") {
      this.setTool("select");
      this.drawOverlay();
      const box = [Math.min(op.start[0], op.cur[0]), Math.min(op.start[1], op.cur[1]),
        Math.abs(op.cur[0] - op.start[0]), Math.abs(op.cur[1] - op.start[1])];
      if (!cancelled && box[2] * this.k > 4 && box[3] * this.k > 4) this.onZoomBox?.(op.pic, box, op.shape);
      return;
    }
    if (op.type === "measure") {   // a known length drawn on a picture, for its scale
      this.setTool("select");
      this.drawOverlay();
      const len = Math.hypot(op.cur[0] - op.start[0], op.cur[1] - op.start[1]);
      if (!cancelled && len * this.k > 3) this.onMeasure?.(this.measuring, len);
      return;
    }
    if (cancelled) { store.cancelLive(); return; }
    if (op.type === "draw") return this.finishDraw(op);
    if (op.type === "end" && op.moved) {
      const it = store.item(op.orig.id);
      if (it && (op.index === 0 || op.index === it.points.length - 1)) {
        const key = op.index === 0 ? "start_link" : "end_link";
        if (op.link) it[key] = op.link; else delete it[key];
        if (op.link) announce(`Attached to ${this.siteLabel(op.link)}`);
      }
    }
    if (op.moved) this.noteTransform(op);
    if (op.moved) store.endLive(op.label);
    else store.cancelLive();
    if (!op.moved && op.keyCandidate) this.onKeyClick?.(op.keyCandidate);
    if (!op.moved && op.takeAway) {   // a ⌘-click on a selected object
      store.select(store.selection.filter((i) => i !== op.takeAway));
      const it = store.item(op.takeAway);
      if (it) announce(`Deselected ${itemLabel(it, store.doc)}; ${store.selection.length} selected`);
    }
    if (!op.moved && op.through) {   // a click inside a selected empty shape: what's under it
      const { id, add } = op.through;
      if (!add) store.select(id ? [id] : []);
      else if (id && !store.selection.includes(id)) store.select([...store.selection, id]);
    }
    if (op.moved && store.selection.length === 1) announce(describeItem(store.selected()[0], store.doc));
    this.drawOverlay();
  },
  // What a finished drag did, for Transform Again (⌘⇧D): a move (an Option-drag copies too),
  // a resize keeping the opposite side (or the middle) still, or a turn
  noteTransform(op) {
    const it = store.selected()[0], o = op.orig;
    if (op.type === "move") this.onTransform?.({ kind: "move", dx: op.dx || 0, dy: op.dy || 0, copy: op.label === "Duplicate" });
    else if (op.type === "resize" && it?.frame && o.frame[2] > 0 && o.frame[3] > 0) {
      const fixed = (lo, hi) => (op.alt ? 0.5 : op.dir.includes(lo) ? 1 : op.dir.includes(hi) ? 0 : 0.5);
      this.onTransform?.({ kind: "resize", sx: it.frame[2] / o.frame[2], sy: it.frame[3] / o.frame[3], anchor: [fixed("w", "e"), fixed("n", "s")] });
    } else if (op.type === "rotate" && it) {
      this.onTransform?.({ kind: "rotate", angle: ((((it.rot || 0) - (o.rot || 0)) % 360) + 540) % 360 - 180 });
    }
  },
  hover(pt, p) {
    this.hoverAt = p;
    if (this.altDown && store.selection.length) this.drawOverlay();
    if (["line", "arrow"].includes(this.tool)) {
      this.sitePointer = p;
      this.siteActive = this.siteNear(p);
      this.drawOverlay();
    } else if (this.sitePointer) {
      this.sitePointer = this.siteActive = null;
      this.drawOverlay();
    }
    let cursor = this.tool === "select" ? "default" : "crosshair";
    if (this.spaceDown) cursor = "grab";
    else if (this.tool === "select") {
      const hd = this.handleAt(pt);
      if (hd) {
        cursor = hd.kind === "rotate" ? "grab" : (hd.kind === "mid" || hd.kind === "adjust") ? "pointer"
          : (hd.kind === "end" || hd.kind === "point") ? "move" : resizeCursor(hd.dir, store.selected()[0]);
      }
      else if (this.itemAt(p)) cursor = "move";
      else {
        const guide = this.guideAt(pt);
        if (guide) cursor = guide.axis === "x" ? "col-resize" : "row-resize";
      }
    }
    this.stage.style.cursor = cursor;
  },
  wheel(e) {
    e.preventDefault();
    const pt = this.eventPoint(e);
    if (e.ctrlKey || e.metaKey) {
      this.setZoom(this.zoom * Math.exp(-e.deltaY * 0.01), pt[0], pt[1]);
    } else {
      this.panX -= e.deltaX;
      this.panY -= e.deltaY;
      this.applyView();
    }
  },
  doubleClick(e) {
    if (e.target.closest?.(NOTES)) return;
    const pt = this.eventPoint(e);
    const p = this.toPage(...pt);
    const sel = store.selected();
    if (this.pen) return this.finishPen(false);
    if (this.pointEdit) {
      const it = store.item(this.pointEdit.id), hit = it && this.pointHit(it, pt);
      if (hit?.kind === "node") {
        const rings = ringsOf(it);
        toggleSmooth(rings[hit.ri], hit.ni);
        const smooth = !!(rings[hit.ri].nodes[hit.ni].hin || rings[hit.ri].nodes[hit.ni].hout);
        store.update(smooth ? "Smooth point" : "Corner point", (doc) => writeRings(findDeep(doc.pages[store.pageIndex].items, it.id), rings));
        announce(smooth ? "A smooth point now" : "A corner now");
        return;
      }
    }
    if (sel.length === 1 && sel[0].type === "line" && !sel[0].locked) {
      // On a selected line: double-click a middle point to remove it, the line to add one
      const hd = this.handleAt(pt);
      if (hd?.kind === "point") return this.removePoint(sel[0].id, hd.index);
      if (!hd && hitItem(sel[0], p, 4 / this.k)) return this.insertPoint(sel[0].id, p);
    }
    const hit = this.itemAt(p);
    if (!hit) {   // a double-click outside the group being edited leaves it
      if (store.scope.length && store.exitGroup()) announce("Left the group");
      return;
    }
    if (hit.type === "group") this.enterGroup(hit.id);
    else if (hit.type === "symbol") this.onEditSymbol?.(hit.id);
    else if (hit.equation) this.onEditEquation?.(hit.id);
    else if (hit.type === "picture") this.startCrop(hit.id);
    else if (hit.geom === "custom") this.startPointEdit(hit.id);
    else if (hit.type === "shape") this.startEdit(hit.id);
  },
  // A zoom inset: the next drag boxes the area of a picture to enlarge
  // A zoom inset's box, dragged next: a rectangle, a rounded rectangle, an ellipse or a circle
  startZoom(shape = "rect") {
    this.zoomShape = shape;
    this.setTool("zoom");
    announce(`Drag ${{ rect: "a box", round: "a rounded box", ellipse: "an ellipse", circle: "a circle" }[shape] || "a box"} on a picture `
      + "around the area to enlarge");
  },
  // Measure a known length on a picture (for its scale): the next drag draws it
  startMeasure(id) {
    this.measuring = id;
    this.setTool("measure");
    announce("Drag along something of known length in the picture: a scale bar already in it, a ruler, a stage micrometer");
  },
  enterGroup(id) {
    const g = store.item(id);
    if (g && store.enterGroup(id)) {
      announce(`Editing inside ${itemLabel(g, store.doc)}: its parts can be picked on their own; Escape or a double-click outside leaves`);
    }
  },

  // Moving -------------------------------------------------------------------------

  startMove(p, e) {
    const sel = store.selected().filter((it) => !it.locked);
    if (!sel.length) return;
    store.beginLive();
    let items = withRegionLines(sel);
    if (e.altKey) {
      // Option/Alt-drag duplicates, like PowerPoint (an area fill with its lines and shapes)
      const copies = copyItems(items);
      store.silent((doc) => store.container(doc).push(...copies));
      store.selection = copies.slice(0, sel.length).map((c) => c.id);
      items = copies;
    }
    detachMoved(items);
    this.op = { type: "move", start: p, orig: items.map((it) => JSON.parse(JSON.stringify(it))), moved: false,
      label: e.altKey ? "Duplicate" : "Move", bbox: itemsBBox(items), targets: this.snapTargets(items.map((i) => i.id)),
      inner: this.innerSnaps(items) };
  },
  moveTo(p, e) {
    const op = this.op;
    let dx = p[0] - op.start[0], dy = p[1] - op.start[1];
    if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
    if (!op.moved && Math.hypot(dx, dy) * this.k < 2) return;
    op.moved = true;
    [dx, dy] = this.snapMove(op.bbox, dx, dy, op.targets, e, op.inner);
    [op.dx, op.dy] = [dx, dy];
    for (const o of op.orig) {
      const it = findDeep(store.items(), o.id);
      if (it) shiftItem(it, o, dx, dy);
    }
    store.live();
  },

  // Snapping -------------------------------------------------------------------------
  // While snapping is on, things snap to the page's edges and centre, to other objects' edges and
  // centres, to equal gaps between objects, and to guides and the grid while they're shown (never
  // to lines that can't be seen); the grid only when nothing else is near. The Snap button turns it
  // off; holding ⌘/Ctrl ignores it for one drag. Lines to snap to are {v, span}: span is the
  // stretch across that they belong to (null for guides, which cross everything).

  snapTargets(excludeIds, { guides = true } = {}) {
    const page = store.page(), d = this.defaults || {};
    const xs = [], ys = [], boxes = [];
    for (const v of [0, page.width / 2, page.width]) xs.push({ v, span: [0, page.height] });
    for (const v of [0, page.height / 2, page.height]) ys.push({ v, span: [0, page.width] });
    if (guides && d.show_guides !== false) {
      for (const v of page.guides?.x || []) xs.push({ v, span: null });
      for (const v of page.guides?.y || []) ys.push({ v, span: null });
    }
    // Inside a group being edited: its other parts, and the rest of the page (not the group itself)
    const pool = store.scope.length ? [...store.scopeItems(), ...store.items().filter((it) => it.id !== store.scope[0])] : store.items();
    for (const it of pool) {
      if (excludeIds.includes(it.id) || it.hidden) continue;
      const b = itemBBox(it);
      boxes.push(b);
      for (const v of [b[0], (b[0] + b[2]) / 2, b[2]]) xs.push({ v, span: [b[1], b[3]] });
      for (const v of [b[1], (b[1] + b[3]) / 2, b[3]]) ys.push({ v, span: [b[0], b[2]] });
      // Placed plots' axis and frame lines and the edges of their ink, in groups too
      for (const t of this.plotSnaps(it)) (t.axis ? ys : xs).push({ v: t.v, span: t.span });
    }
    return { xs, ys, boxes, grid: d.show_grid ? this.gridSteps().snap : null, size: [page.width, page.height] };
  },
  snapEnabled(e) { return (this.defaults?.snap ?? true) && !(e.metaKey || e.ctrlKey); },
  // Moving: the box's edges and centre snap to lines, or the box to equal gaps beside it; so do
  // the axis and frame lines and ink edges of plots being moved (inner: [xs, ys] where they start)
  snapMove(b, dx, dy, targets, e, inner = [[], []]) {
    this.snapGuides = [];
    if (!this.snapEnabled(e) || !b) return [dx, dy];
    const tol = SNAP_PX / this.k;
    const box = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy];
    const own = (i, d) => [...edges(box, i), ...inner[i].map((v) => v + d)];
    const shifts = [0, 1].map((i) => {
      const line = nearestSnap(own(i, i ? dy : dx), lines(targets, i), null, 0, tol);
      const gap = equalSpacing(box, i, targets.boxes, tol);
      let d = gap && (line === null || Math.abs(gap.d) < Math.abs(line)) ? gap.d : line;
      if (d === null) d = nearestSnap(edges(box, i), [], targets.grid, targets.size[i], tol);
      return { d, gap: gap && d !== null && Math.abs(gap.d - d) < 1e-9 ? gap : null };
    });
    if (shifts[0].d !== null) dx += shifts[0].d;
    if (shifts[1].d !== null) dy += shifts[1].d;
    const fin = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy];
    shifts.forEach(({ d, gap }, i) => {
      if (d === null) return;
      this.snapGuides.push(...snapLines(i, [...edges(fin, i), ...inner[i].map((v) => v + (i ? dy : dx))], targets, fin[1 - i], fin[3 - i]));
      if (gap) this.snapGuides.push(...gapMarks(i, gap.pairs, fin));
    });
    return [dx, dy];
  },
  // Placed plots (vectors.plot_lines): their axis and frame lines and ink box, read once per
  // file and page in the background, then snapped to like objects' edges
  loadPlotLines() {
    this.plotLines ||= new Map();
    const walk = (items) => items.forEach((it) => {
      if (it.type === "group") walk(it.items);
      if (it.type !== "picture") return;
      const key = `${it.asset}:${it.page_index || 0}`, asset = store.doc.assets[it.asset];
      if (this.plotLines.has(key) || !asset || !["pdf", "svg"].some((k) => asset.variants?.[k])) return;
      this.plotLines.set(key, null);
      rpc("plot_lines", asset, it.page_index || 0).then((d) => this.plotLines.set(key, d), () => {});
    });
    walk(store.items());
  },
  // A picture's plot lines on the page: only what its crop shows, mapped through its frame (none
  // for a turned picture); a group's pictures' too
  plotSnaps(it) {
    if (it.type === "group") return it.hidden ? [] : it.items.flatMap((k) => this.plotSnaps(k));
    const data = it.type === "picture" && !it.hidden && !((it.rot || 0) % 360) && this.plotLines?.get(`${it.asset}:${it.page_index || 0}`);
    if (!data) return [];
    const [sw, sh] = data.size, [x, y, w, h] = it.frame, [l, t, r, b] = it.crop || [0, 0, 0, 0];
    const lo = [l * sw, t * sh], hi = [(1 - r) * sw, (1 - b) * sh];
    const map = (v, i) => {
      const f = (v - lo[i]) / (hi[i] - lo[i] || 1);
      return i ? y + (it.flip_v ? 1 - f : f) * h : x + (it.flip_h ? 1 - f : f) * w;
    };
    const [ix0, iy0, ix1, iy1] = data.ink || [];
    const found = [...data.lines, ...(data.ink ? [[0, ix0, iy0, iy1], [0, ix1, iy0, iy1], [1, iy0, ix0, ix1], [1, iy1, ix0, ix1]] : [])];
    const out = [];
    for (const [axis, at, a, b2] of found) {
      const i = axis ? 1 : 0, j = 1 - i;   // the line is at `at` on axis i, running along axis j
      if (at < lo[i] - 1e-6 || at > hi[i] + 1e-6) continue;
      const s0 = Math.max(a, lo[j]), s1 = Math.min(b2, hi[j]);
      if (s1 < s0) continue;
      const ends = [map(s0, j), map(s1, j)].sort((p, q) => p - q);
      out.push({ axis: i, v: map(at, i), span: ends });
    }
    return out;
  },
  // Where the moving objects' plot lines start: [xs, ys]
  innerSnaps(items) {
    const found = items.flatMap((it) => this.plotSnaps(it));
    return [found.filter((t) => !t.axis).map((t) => t.v), found.filter((t) => t.axis).map((t) => t.v)];
  },
  // Line ends and drawing: the point snaps to lines
  snapPoint(p, targets, e) {
    this.snapGuides = [];
    if (!this.snapEnabled(e)) return p;
    const tol = SNAP_PX / this.k;
    const q = [p[0], p[1]];
    const snapped = [0, 1].map((i) => {
      const d = nearestSnap([q[i]], lines(targets, i), targets.grid, targets.size[i], tol);
      if (d !== null) q[i] += d;
      return d !== null;
    });
    snapped.forEach((on, i) => { if (on) this.snapGuides.push(...snapLines(i, [q[i]], targets, q[1 - i], q[1 - i])); });
    return q;
  },
  // A guide being dragged snaps to the page, objects' edges and centres and the grid
  snapGuide(v, i, targets, e) {
    this.snapGuides = [];
    if (!this.snapEnabled(e)) return v;
    const d = nearestSnap([v], lines(targets, i), targets.grid, targets.size[i], SNAP_PX / this.k);
    if (d === null) return v;
    this.snapGuides.push(...snapLines(i, [v + d], targets, Infinity, -Infinity));
    return v + d;
  },
  // What was snapped to: magenta lines along what lines up, and the equal gaps with their size
  drawSnapGuides(o) {
    for (const g of this.snapGuides) {
      if (g.gap) {
        const ends = [g.a, g.b].map((v) => this.toScreen(...(g.axis ? [g.at, v] : [v, g.at])));
        const [[ax, ay], [bx, by]] = ends, t = 4;
        o.append(s("path", { class: "snap-gap", d: g.axis ? `M${ax} ${ay}V${by}M${ax - t} ${ay}h${2 * t}M${bx - t} ${by}h${2 * t}`
          : `M${ax} ${ay}H${bx}M${ax} ${ay - t}v${2 * t}M${bx} ${by - t}v${2 * t}` }));
        const label = s("text", { class: "snap-label", x: g.axis ? ax + 7 : (ax + bx) / 2, y: g.axis ? (ay + by) / 2 : ay - 7,
          "text-anchor": g.axis ? "start" : "middle", "dominant-baseline": g.axis ? "middle" : "auto" });
        label.textContent = lengthText(g.b - g.a);
        o.append(label);
        continue;
      }
      // A line from the page's view of it, a little past what lines up (guides run right across)
      const [sx, sy] = this.toScreen(g.v, g.v);
      const lo = g.from === null ? -1e4 : this.toScreen(g.from, g.from)[1 - g.axis] - 8;
      const hi = g.to === null ? 1e5 : this.toScreen(g.to, g.to)[1 - g.axis] + 8;
      o.append(s("line", { class: "snap-guide", ...(g.axis ? { x1: lo, x2: hi, y1: sy, y2: sy } : { x1: sx, x2: sx, y1: lo, y2: hi }) }));
    }
  },

  // The grid -------------------------------------------------------------------------
  // Like graph paper over the page: squares of `spacing` divided into finer lines, which appear
  // only once zooming in leaves them GRID_MIN_PX apart; zoomed far out, every 2nd, 5th, 10th...
  // line is drawn instead. Only lines that are drawn are snapped to (`snap`, the finest).

  gridSteps() {
    const g = this.defaults?.grid || {};
    const spacing = g.spacing > 0 ? g.spacing : 72 / 2.54;
    const parts = Math.max(1, Math.round(g.subdivisions || 1));
    let major = spacing;
    for (const f of [2, 5, 10, 20, 50, 100, 200, 500, 1000]) {
      if (major * this.k >= GRID_MIN_PX) break;
      major = spacing * f;
    }
    const minor = parts > 1 && (spacing / parts) * this.k >= GRID_MIN_PX ? spacing / parts : null;
    return { major, minor, parts, snap: minor || major };
  },
  // The page as people with colour blindness see it (Machado, Oliveira & Fernandes 2009, full
  // strength, in linear RGB), or in grey; only the page and its objects, never an export
  setColourVision(mode) {
    const m = COLOUR_VISION[mode];
    this.colourVision = m ? mode : "normal";
    if (m) this.cvdMatrix.setAttribute("values", visionMatrix(mode));
    for (const el of [this.pageRect, this.ghostLayer, this.itemsLayer]) {
      if (m) el.setAttribute("filter", "url(#fa-cvd)");
      else el.removeAttribute("filter");
    }
    this.cvdNote.replaceChildren(...(m ? [`Previewing ${m.name} — never exported `,
      h("button", { type: "button", class: "btn", onclick: () => this.setColourVision("normal") }, "Stop")] : []));
    this.cvdNote.hidden = !m;
    document.dispatchEvent(new CustomEvent("fa-colour-vision", { detail: this.colourVision }));
  },

  drawGrid() {
    if (!this.gridLayer || !store.doc) return;
    const page = store.page();
    const st = this.defaults?.show_grid ? this.gridSteps() : null;
    const key = st ? JSON.stringify([st, page.width, page.height]) : "";
    if (key === this._gridKey) return;
    this._gridKey = key;
    this.gridLayer.replaceChildren();
    if (!st) return;
    const path = (step, skip) => {
      let d = "";
      for (let i = 1; i * step < page.width - 1e-6; i++) if (!skip || i % skip) d += `M${+(i * step).toFixed(4)} 0V${page.height}`;
      for (let i = 1; i * step < page.height - 1e-6; i++) if (!skip || i % skip) d += `M0 ${+(i * step).toFixed(4)}H${page.width}`;
      return d;
    };
    if (st.minor) this.gridLayer.append(s("path", { class: "minor", d: path(st.minor, st.parts) }));
    this.gridLayer.append(s("path", { class: "major", d: path(st.major, 0) }));
  },

  // Guides and rulers ------------------------------------------------------------------
  // Each page keeps its own guides: {x: [vertical guides' x], y: [horizontal guides' y]}. They're
  // drawn across the whole view, dragged out of the rulers, moved by dragging (where no object
  // covers them, or by their marks on the rulers) and removed by dragging them onto a ruler.

  // Rulers take room along the top and left; the page stays where it was on screen
  setRulers(on) {
    const wrap = this.stage.parentElement;
    if (wrap.classList.contains("rulers") === on) return;
    const before = this.stage.getBoundingClientRect();
    wrap.classList.toggle("rulers", on);
    const after = this.stage.getBoundingClientRect();
    this.panX += before.left - after.left;
    this.panY += before.top - after.top;
    this.layout();
  },
  // The page's guides, with the one being dragged where the pointer has it
  guideLines() {
    const g = store.page()?.guides || {};
    const out = { x: [...(g.x || [])], y: [...(g.y || [])], active: null, removing: false };
    const op = this.op;
    if (op?.type === "guide" && op.value !== null && !(op.index === null && op.remove)) {
      const i = op.index === null ? out[op.axis].push(op.value) - 1 : op.index;
      out[op.axis][i] = op.value;
      out.active = [op.axis, i];
      out.removing = op.remove;
    }
    return out;
  },
  drawGuides() {
    if (!this.guidesLayer || !store.doc) return;
    this.guidesLayer.replaceChildren();
    if (this.defaults?.show_guides === false) return;
    const g = this.guideLines();
    const line = (axis, v, cls) => this.guidesLayer.append(s("line", { class: cls, ...(axis === "x" ? { x1: v, x2: v, y1: -1e5, y2: 1e5 }
      : { x1: -1e5, x2: 1e5, y1: v, y2: v }) }));
    for (const axis of ["x", "y"]) {
      g[axis].forEach((v, i) => {
        const active = g.active?.[0] === axis && g.active[1] === i;
        line(axis, v, `guide${active ? " active" : ""}${active && g.removing ? " removing" : ""}`);
      });
    }
  },
  // Where a click on a ruler would put a guide, while the pointer is over it: a faint line, with its
  // position by the ruler (rulers.js); null takes it away. Drawn whether guides show or not
  setGuidePreview(preview) {
    if (JSON.stringify(preview) === JSON.stringify(this.guidePreview || null)) return;
    this.guidePreview = preview;
    this.drawGuidePreview();
  },
  drawGuidePreview() {
    this.previewLayer?.remove();
    this.previewLayer = null;
    const p = this.guidePreview;
    if (!p || !store.doc) return;
    const r = this.stage.getBoundingClientRect(), [sx, sy] = this.toScreen(p.value, p.value);
    this.previewLayer = s("g", { class: "guide-preview" });
    this.previewLayer.append(s("line", p.axis === "x" ? { x1: sx, x2: sx, y1: 0, y2: r.height } : { x1: 0, x2: r.width, y1: sy, y2: sy }));
    const label = s("text", { class: "guide-label", ...(p.axis === "x" ? { x: clamp(sx + 6, 4, r.width - 80), y: 16 }
      : { x: 6, y: clamp(sy - 6, 16, r.height - 6) }) });
    label.textContent = lengthText(p.value);
    this.previewLayer.append(label);
    this.svg.append(this.previewLayer);
  },
  // A guide added (a click on a ruler; none where the page has one already), one removed, or all
  // of the page's (a guide's right-click menu)
  addGuide(axis, value) {
    const kind = axis === "x" ? "vertical" : "horizontal", pi = store.pageIndex;
    if ((store.page().guides?.[axis] || []).some((v) => Math.abs(v - value) < 0.01)) {
      announce(`There's a ${kind} guide there already`);
      return false;
    }
    store.update("Add guide", (doc) => { pageGuides(doc.pages[pi])[axis].push(value); });
    announce(`Added a ${kind} guide, ${lengthText(value, true)} from the ${axis === "x" ? "left" : "top"} edge`);
    return true;
  },
  removeGuide(axis, index) {
    const pi = store.pageIndex, value = store.page().guides[axis][index];
    store.update("Remove guide", (doc) => { doc.pages[pi].guides[axis].splice(index, 1); });
    announce(`Removed the ${axis === "x" ? "vertical" : "horizontal"} guide ${lengthText(value, true)} from the `
      + `${axis === "x" ? "left" : "top"} edge`);
  },
  removeAllGuides() {
    const pi = store.pageIndex;
    store.update("Remove guides", (doc) => { doc.pages[pi].guides = { x: [], y: [] }; });
    announce("Removed every guide from this page");
  },
  guideAt(pt) {
    if (this.defaults?.show_guides === false || !store.doc) return null;
    const g = store.page().guides || {};
    let best = null;
    ["x", "y"].forEach((axis, i) => (g[axis] || []).forEach((v, index) => {
      const d = Math.abs(this.toScreen(v, v)[i] - pt[i]);
      if (d <= GUIDE_HIT && (!best || d < best.d)) best = { axis, index, d };
    }));
    return best;
  },
  // axis "x" is a vertical guide (its x position), "y" a horizontal one; index null for a new guide
  startGuide(axis, index) {
    this.op = { type: "guide", axis, index, value: index === null ? null : store.page().guides[axis][index],
      pt: null, moved: false, remove: false, targets: this.snapTargets([], { guides: false }) };
  },
  // pt is in stage coordinates. Past the stage's edge (over a ruler) a new guide isn't placed yet
  // and an existing one would be removed.
  guideTo(pt, e) {
    const op = this.op, i = op.axis === "x" ? 0 : 1;
    const r = this.stage.getBoundingClientRect();
    op.moved = true;
    op.pt = pt;
    op.remove = pt[i] < 0 || pt[i] > (i ? r.height : r.width);
    const v = this.toPage(...pt)[i];
    op.value = op.remove ? v : this.snapGuide(v, i, op.targets, e);
    if (op.remove) this.snapGuides = [];
    this.drawGuides();
    this.drawOverlay();
  },
  finishGuide(op, cancelled) {
    this.snapGuides = [];
    const pi = store.pageIndex, axis = op.axis;
    const kind = axis === "x" ? "vertical" : "horizontal";
    if (!cancelled && op.moved && op.value !== null) {
      if (op.remove && op.index !== null) {
        store.update("Remove guide", (doc) => { doc.pages[pi].guides[axis].splice(op.index, 1); });
        announce(`Removed the ${kind} guide`);
      } else if (!op.remove) {
        store.update(op.index === null ? "Add guide" : "Move guide", (doc) => {
          const g = pageGuides(doc.pages[pi]);
          if (op.index === null) g[axis].push(op.value);
          else g[axis][op.index] = op.value;
        });
        announce(`${op.index === null ? "Added a" : "Moved the"} ${kind} guide, ${lengthText(op.value, true)} from the `
          + `${axis === "x" ? "left" : "top"} edge`);
      }
    }
    this.drawGuides();
    this.drawOverlay();
  },
  // The guide's position beside the pointer while it's dragged
  drawGuideLabel(o) {
    const op = this.op;
    if (!op.pt || op.value === null || (op.remove && op.index === null)) return;
    const r = this.stage.getBoundingClientRect();
    const label = s("text", { class: `guide-label${op.remove ? " removing" : ""}`,
      x: clamp(op.pt[0] + 14, 4, r.width - 130), y: clamp(op.pt[1] - 12, 16, r.height - 6) });
    label.textContent = op.remove ? "Release to remove" : lengthText(op.value);
    o.append(label);
  },
  // Escape during a drag puts everything back as it was
  cancelDrag() {
    const op = this.op;
    if (!op) return false;
    this.op = null;
    this.snapGuides = [];
    if (op.type === "adjust") op.cancelled = true;
    if (!["pan", "marquee", "draw", "guide"].includes(op.type)) store.cancelLive();
    this.drawGuides();
    this.drawOverlay();
    return true;
  },

  // Resizing and rotating --------------------------------------------------------------

  startHandle(hd, p, e) {
    const it = store.selected()[0];
    if (hd.kind === "crop") return this.startCropHandle(hd, p);
    store.beginLive();
    const orig = JSON.parse(JSON.stringify(it));
    if (hd.kind === "resize") {
      // The handle stands outside the frame: the edge keeps its distance from the pointer, so it
      // doesn't jump out to where the handle was grabbed
      const local = apply(invert(frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v)), ...p);
      const [, , w, h] = it.frame, d = hd.dir;
      const grab = [d.includes("w") ? local[0] : d.includes("e") ? local[0] - w : 0,
        d.includes("n") ? local[1] : d.includes("s") ? local[1] - h : 0];
      this.op = { type: "resize", dir: d, orig, grab, moved: false, label: "Resize", targets: this.snapTargets([it.id]) };
    }
    else if (hd.kind === "rotate") this.op = { type: "rotate", orig, moved: false, label: "Rotate" };
    else if (hd.kind === "adjust") this.op = { type: "adjust", index: hd.index, orig, moved: false, label: "Adjust shape" };
    else if (hd.kind === "end" || hd.kind === "point") {
      this.op = { type: "end", index: hd.index, orig, moved: false, label: hd.kind === "end" ? "Move end" : "Move point",
        targets: this.snapTargets([it.id]) };
      if (hd.kind === "end") delete it[hd.index === 0 ? "start_link" : "end_link"];   // it attaches again where it's dropped
    }
    else if (hd.kind === "elbow") this.op = { type: "elbow", orig, moved: false, label: "Move elbow" };
    else if (hd.kind === "mid") {
      // A new point appears where the handle was and follows the pointer; nothing is kept
      // unless it actually moves
      const m = lineMidpoints(it)[hd.index];
      it.points.splice(hd.index + 1, 0, [m.at[0], m.at[1]]);
      const bending = orig.points.length === 2 && !orig.curve;
      if (bending) it.curve = "smooth";
      this.op = { type: "end", index: hd.index + 1, orig, moved: false, label: bending ? "Curve arrow" : "Add point",
        targets: this.snapTargets([it.id]) };
    }
  },
  // The middle stretch of an elbow connector dragged across: where it crosses, as a fraction of
  // the way between the ends (outside 0 to 1 takes it past them)
  elbowTo(p) {
    const op = this.op, it = findDeep(store.items(), op.orig.id);
    if (!it) return;
    const [a, p1, , b] = op.orig.points, level = Math.abs(p1[1] - a[1]) < 1e-9;
    const span = level ? b[0] - a[0] : b[1] - a[1];
    if (Math.abs(span) < 1e-9) return;
    op.moved = true;
    it.elbow = ((level ? p[0] - a[0] : p[1] - a[1]) / span);
    store.live();
  },
  removePoint(id, index) {
    const it = store.item(id);
    if (!it || it.type !== "line" || index <= 0 || index >= it.points.length - 1) return;
    store.update("Remove point", (doc) => { findDeep(doc.pages[store.pageIndex].items, id).points.splice(index, 1); });
    announce(`Removed a point; ${it.points.length - 2} middle point${it.points.length - 2 === 1 ? "" : "s"} left`);
  },
  insertPoint(id, p) {
    const it = store.item(id);
    if (!it || it.type !== "line") return;
    const { index } = nearestStretch(it, p);
    store.update("Add point", (doc) => {
      const x = findDeep(doc.pages[store.pageIndex].items, id);
      x.points.splice(index + 1, 0, [p[0], p[1]]);
      if (x.points.length === 3 && !x.curve) x.curve = "smooth";
    });
    announce("Added a point; drag it to reshape the line");
  },
  resizeTo(p, e) {
    const op = this.op, o = op.orig, it = store.selected()[0];
    const m = frameMatrix(o.frame, o.rot || 0, o.flip_h, o.flip_v);
    const local = apply(invert(m), ...p);
    local[0] -= op.grab?.[0] || 0;
    local[1] -= op.grab?.[1] || 0;
    const [, , w, h] = o.frame;
    let [x0, y0, x1, y1] = [0, 0, w, h];
    const dir = op.dir;
    if (dir.includes("w")) x0 = local[0];
    if (dir.includes("e")) x1 = local[0];
    if (dir.includes("n")) y0 = local[1];
    if (dir.includes("s")) y1 = local[1];
    if (o.zoom?.circle && dir.length === 1 && w > 0 && h > 0) {   // a circle's box from a side: the other way too, about its middle
      const d = dir === "e" || dir === "w" ? Math.abs(x1 - x0) : Math.abs(y1 - y0);
      if (dir === "e" || dir === "w") { y0 = h / 2 - d / 2; y1 = h / 2 + d / 2; } else { x0 = w / 2 - d / 2; x1 = w / 2 + d / 2; }
    }
    const keepAspect = o.zoom?.circle || ((o.type === "picture" || o.type === "symbol") !== e.shiftKey && dir.length === 2);
    if (keepAspect && dir.length === 2 && w > 0 && h > 0) {
      const sx = (x1 - x0) / w, sy = (y1 - y0) / h;
      const sc = Math.max(Math.abs(sx), Math.abs(sy));
      const nw = w * sc, nh = h * sc;
      if (dir.includes("w")) x0 = x1 - nw; else x1 = x0 + nw;
      if (dir.includes("n")) y0 = y1 - nh; else y1 = y0 + nh;
    }
    op.alt = e.altKey;
    if (e.altKey) {   // from the centre
      const cx = w / 2, cy = h / 2;
      const hw = Math.max(Math.abs(x1 - cx), Math.abs(x0 - cx)), hh = Math.max(Math.abs(y1 - cy), Math.abs(y0 - cy));
      if (dir.includes("w") || dir.includes("e")) { x0 = cx - hw; x1 = cx + hw; }
      if (dir.includes("n") || dir.includes("s")) { y0 = cy - hh; y1 = cy + hh; }
    }
    const nw = Math.max(Math.abs(x1 - x0), 0.5), nh = Math.max(Math.abs(y1 - y0), 0.5);
    const [cx, cy] = apply(m, (x0 + x1) / 2, (y0 + y1) / 2);
    it.frame = [cx - nw / 2, cy - nh / 2, nw, nh];
    if (it.text && it.text.autofit === "shape" && (dir.includes("e") || dir.includes("w"))) it.text.wrap = true;
    op.moved = true;
    store.live();
  },
  rotateTo(p, e) {
    const op = this.op, it = store.selected()[0], o = op.orig;
    const [x, y, w, h] = o.frame;
    let ang = (Math.atan2(p[1] - (y + h / 2), p[0] - (x + w / 2)) * 180) / Math.PI + 90;
    if (o.flip_v) ang += 180;
    if (e.shiftKey) ang = Math.round(ang / 15) * 15;
    it.rot = ((ang % 360) + 360) % 360;
    op.moved = true;
    store.live();
  },
  endTo(p, e) {
    const op = this.op, it = store.selected()[0];
    const isEnd = op.index === 0 || op.index === it.points.length - 1;
    // An end near a connection point attaches to it (hold ⌘/Ctrl to place it freely)
    const near = isEnd && !(e.metaKey || e.ctrlKey) ? this.siteNear(p, it.id) : null;
    op.link = near && { item: near.item, site: near.site };
    this.sitePointer = isEnd ? p : null;
    this.siteActive = near;
    let q = near ? near.at.slice() : this.snapPoint(p, op.targets, e);
    if (near) this.snapGuides = [];
    if (e.shiftKey && !near) {
      // Keep the stretch to the previous point at a multiple of 45 degrees
      const other = it.points[op.index === 0 ? 1 : op.index - 1];
      const ang = Math.round(Math.atan2(q[1] - other[1], q[0] - other[0]) / (Math.PI / 4)) * (Math.PI / 4);
      const len = Math.hypot(q[0] - other[0], q[1] - other[1]);
      q = [other[0] + Math.cos(ang) * len, other[1] + Math.sin(ang) * len];
    }
    it.points[op.index] = q;
    op.moved = true;
    store.live();
  },
  // Adjust handles: the engine works out the adjust values that bring the handle nearest the
  // pointer (each shape's formulas differ); one request at a time, always the latest position
  adjustTo(p) {
    const op = this.op, o = op.orig;
    op.target = apply(invert(frameMatrix(o.frame, o.rot || 0, o.flip_h, o.flip_v)), ...p);
    if (!op.busy) this.sendAdjust(op);
  },
  async sendAdjust(op) {
    op.busy = true;
    while (op.target && op.target !== op.sent && !op.cancelled) {
      const target = op.target;
      op.sent = target;
      const it = store.item(op.orig.id);
      if (!it) break;
      try {
        // The new adjust values and the shape drawn with them come back together
        const res = await rpc("adjust_shape", this.assetSizes(), it, op.index, target);
        if (op.cancelled) break;
        it.adj = res.adj;
        this.showDrawn(it, res.drawn, this.geomKey(it));
        op.moved = true;
        store.live();
      } catch (err) { console.error(err); break; }
    }
    op.busy = false;
    if (op.done && !op.cancelled) this.finishAdjust(op);
  },
  finishAdjust(op) {
    if (op.moved) store.endLive(op.label);
    else store.cancelLive();
    this.drawOverlay();
  },

  // Connections ------------------------------------------------------------------------
  // Line and arrow ends attach to objects' connection points (corners, side middles, ends,
  // dashes; connect.py) and follow them. A line keeps {item, site} in start_link / end_link.

  // An object's connection points on the page: [{key, at}]
  sitesOf(it) {
    const e = this.els.get(it.id);
    if (it.type === "line") {
      const out = [{ key: "e0", at: it.points[0] }, { key: "e1", at: it.points[it.points.length - 1] },
        { key: "m", at: pointAlong(lineSamples(it), 0.5) }];
      if (e?.sites && e.origin) {   // its dashes, as drawn (moved along with the line since)
        const dx = it.points[0][0] - e.origin[0], dy = it.points[0][1] - e.origin[1];
        for (const [key, x, y] of e.sites) out.push({ key, at: [x + dx, y + dy] });
      }
      return out;
    }
    if (it.type === "shape" && e?.sites) {
      const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v);
      return e.sites.map(([key, u, v]) => ({ key, at: apply(m, u * it.frame[2], v * it.frame[3]) }));
    }
    return boxSites(it);
  },
  // The connection point nearest p, within reach, on any object but `exceptId`
  siteNear(p, exceptId = null) {
    const reach = SITE_PX / this.k;
    let best = null;
    const visit = (items) => items.forEach((it) => {
      if (it.hidden || it.id === exceptId) return;
      if (it.type === "group") visit(it.items);
      for (const site of this.sitesOf(it)) {
        const d = Math.hypot(site.at[0] - p[0], site.at[1] - p[1]);
        if (d <= reach && (!best || d < best.d)) best = { item: it.id, site: site.key, at: site.at, d };
      }
    });
    visit(store.items());
    return best;
  },
  linkedTo(id) {
    return allLines(store.items()).some((l) => l.start_link?.item === id || l.end_link?.item === id);
  },
  // Attached ends go where their connection points are now (after every change, in its undo step);
  // a link whose object has gone is dropped, and one whose dash has gone takes the nearest dash
  followLinks(doc) {
    const items = doc.pages[store.pageIndex]?.items;
    if (!items) return;
    finishEdits(doc, store.scope);        // a symbol edited in place goes back once it's left (symbols.js)
    followGrids(items);                   // grid layouts put their parts in their cells
    followZooms(items, doc.assets);       // zoom insets show what's in their boxes
    followScaleBars(items, doc.assets);   // scale bars keep their length and place on their pictures
    followLabels(items);                  // panel labels go with their panels
    const lines = allLines(items).filter((l) => l.start_link || l.end_link);
    for (let pass = 0; pass < 3 && lines.length; pass++) {   // a few rounds for lines attached to lines
      let moved = false;
      for (const line of lines) {
        for (const [key, idx] of [["start_link", 0], ["end_link", line.points.length - 1]]) {
          const link = line[key];
          if (!link) continue;
          const target = findDeep(items, link.item);
          if (!target || target === line) { delete line[key]; continue; }
          const sites = this.sitesOf(target), p = line.points[idx];
          let site = sites.find((x) => x.key === link.site);
          if (!site) {
            const kind = link.site.replace(/\d.*$/, "");
            site = sites.filter((x) => x.key.replace(/\d.*$/, "") === kind)
              .sort((a, b) => Math.hypot(a.at[0] - p[0], a.at[1] - p[1]) - Math.hypot(b.at[0] - p[0], b.at[1] - p[1]))[0];
            if (!site) { delete line[key]; continue; }
            link.site = site.key;
          }
          if (Math.abs(p[0] - site.at[0]) > 1e-9 || Math.abs(p[1] - site.at[1]) > 1e-9) {
            line.points[idx] = [site.at[0], site.at[1]];
            moved = true;
          }
        }
      }
      if (!moved) break;
    }
    // Elbow connectors: their corners from their ends, square to the sides they're attached to
    for (const line of allLines(items).filter((l) => l.route === "elbow" && l.points.length >= 2)) {
      const a = line.points[0], b = line.points[line.points.length - 1];
      const pts = elbowRoute(a, b, this.attachedSide(line.start_link, items, a), this.attachedSide(line.end_link, items, b), line.elbow ?? 0.5);
      if (pts.length !== line.points.length || pts.some((q, i) => Math.abs(q[0] - line.points[i][0]) > 1e-9 || Math.abs(q[1] - line.points[i][1]) > 1e-9)) {
        line.points = pts;
      }
    }
  },
  // The way out of the side of an object an end is attached to: [dx, dy], or null
  attachedSide(link, items, at) {
    const target = link && findDeep(items, link.item);
    if (!target || target.type === "line") return null;
    const b = itemBBox(target), d = [at[0] - b[0], b[2] - at[0], at[1] - b[1], b[3] - at[1]];
    return [[-1, 0], [1, 0], [0, -1], [0, 1]][d.indexOf(Math.min(...d))];
  },
  // While a line end is being placed: the connection points of the objects near the pointer
  drawSites(o) {
    const p = this.sitePointer;
    if (!p) return;
    const pad = 24 / this.k;
    const visit = (items) => items.forEach((it) => {
      if (it.hidden || (this.op?.type === "end" && it.id === store.selection[0])) return;
      if (it.type === "group") visit(it.items);
      const b = itemBBox(it);
      if (p[0] < b[0] - pad || p[0] > b[2] + pad || p[1] < b[1] - pad || p[1] > b[3] + pad) return;
      for (const site of this.sitesOf(it)) {
        const dash = site.key[0] === "d";
        if (dash && Math.hypot(site.at[0] - p[0], site.at[1] - p[1]) > 4 * pad) continue;   // dashes only nearby
        const [x, y] = this.toScreen(...site.at);
        o.append(s("circle", { class: `site${dash ? " dash" : ""}`, cx: x, cy: y, r: dash ? 2.5 : 3.5 }));
      }
    });
    visit(store.items());
    if (this.siteActive) {
      const [x, y] = this.toScreen(...this.siteActive.at);
      o.append(s("circle", { class: "site active", cx: x, cy: y, r: 5.5 }));
    }
  },
  // "corner 2 of Rectangle", for announcements and the properties panel
  siteLabel(link) {
    const target = findDeep(store.items(), link.item);
    return `${siteName(link.site)} of ${target ? describeItem(target, store.doc).split(",")[0] : "an object"}`;
  },

  // Drawing tools ----------------------------------------------------------------------

  setTool(tool, geom = null) {
    if (this.pen && tool !== "pen") this.finishPen(false);
    if (tool !== "select") this.pointEdit = null;
    if (this.editing) this.commitEdit();
    if (tool === "shape" && geom) this.shapeGeom = geom;
    this.tool = tool;
    this.stage.style.cursor = tool === "select" ? "default" : tool === "painter" ? "copy" : "crosshair";
    if (this.onToolChange) this.onToolChange(tool);
  },
  startDraw(p, e) {
    const targets = this.snapTargets([]);
    const lineTool = ["line", "arrow"].includes(this.tool);
    const near = lineTool && !(e.metaKey || e.ctrlKey) ? this.siteNear(p) : null;
    const start = near ? near.at.slice() : this.snapPoint(p, targets, e);
    this.op = { type: "draw", tool: this.tool, start, cur: start, targets, moved: false,
      startLink: near && { item: near.item, site: near.site } };
  },
  drawTo(p, e) {
    const op = this.op;
    const lineTool = ["line", "arrow"].includes(op.tool);
    const near = lineTool && !(e.metaKey || e.ctrlKey) ? this.siteNear(p) : null;
    op.endLink = near && { item: near.item, site: near.site };
    this.sitePointer = lineTool ? p : null;
    this.siteActive = near;
    let q = near ? near.at.slice() : this.snapPoint(p, op.targets, e);
    if (near) this.snapGuides = [];
    if (e.shiftKey && !near) {
      const dx = q[0] - op.start[0], dy = q[1] - op.start[1];
      if (["line", "arrow"].includes(op.tool)) {
        const ang = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
        const len = Math.hypot(dx, dy);
        q = [op.start[0] + Math.cos(ang) * len, op.start[1] + Math.sin(ang) * len];
      } else {
        const d = Math.max(Math.abs(dx), Math.abs(dy));
        q = [op.start[0] + Math.sign(dx || 1) * d, op.start[1] + Math.sign(dy || 1) * d];
      }
    }
    op.cur = q;
    op.moved = Math.hypot(q[0] - op.start[0], q[1] - op.start[1]) * this.k > 3;
    this.drawOverlay();
  },
  // What's being drawn: a dashed line, or a box with the shape's outline in it (part of every
  // redraw of the overlay, so nothing wipes it mid-drag)
  drawPreview(o) {
    const op = this.op;
    const [ax, ay] = this.toScreen(...op.start), [bx, by] = this.toScreen(...op.cur);
    if (["line", "arrow"].includes(op.tool)) o.append(s("line", { class: "draw-preview", x1: ax, y1: ay, x2: bx, y2: by }));
    else if (op.tool === "sigbracket") {   // the span it will cover, across or upright
      const upright = Math.abs(by - ay) > Math.abs(bx - ax);
      o.append(s("line", { class: "draw-preview", x1: ax, y1: ay, x2: upright ? ax : bx, y2: upright ? by : ay }));
    }
    else {
      const box = [Math.min(ax, bx), Math.min(ay, by), Math.abs(bx - ax), Math.abs(by - ay)];
      o.append(s("rect", { class: "draw-preview", x: box[0], y: box[1], width: box[2], height: box[3] }));
      // The shape's outline (its menu icon, stretched over the box) shows what is being drawn
      const shape = shapeCatalog.shapes[this.toolGeom(op.tool)];
      if (shape?.icon && box[2] > 2 && box[3] > 2) {
        const [ix, iy, iw, ih] = shape.box;
        o.append(s("path", { class: "draw-preview shape", d: shape.icon,
          transform: `translate(${box[0]} ${box[1]}) scale(${box[2] / iw} ${box[3] / ih}) translate(${-ix} ${-iy})` }));
      }
    }
  },
  toolGeom(tool) { return tool === "shape" ? this.shapeGeom : TOOL_GEOMS[tool]; },
  // Enter with a drawing tool: one object in the middle of the view (off the page too)
  placeDefault() {
    if (this.tool === "fill") return announce("Click inside an area that lines and shapes enclose to fill it");
    if (this.tool === "painter") return this.onPaint?.(null, true);   // Enter paints what's selected
    const r = this.stage.getBoundingClientRect(), c = this.toPage(r.width / 2, r.height / 2);
    this.finishDraw({ type: "draw", tool: this.tool, start: c, cur: c, moved: false, centred: true });
  },
  finishDraw(op) {
    const d = this.defaults || {};
    const stroke = { color: "#000000", width: d.stroke_width || 1, dash: "solid", cap: "round", join: "round", opacity: 1 };
    let [ax, ay] = op.start, [bx, by] = op.cur;
    if (!op.moved && !["text", "label"].includes(op.tool)) {
      // A click (or Enter) without dragging: a 2 cm object from the click, or centred on the view
      const half = op.centred ? DEFAULT_SIZE / 2 : 0;
      const line = ["line", "arrow", "sigbracket"].includes(op.tool);
      [ax, ay] = [ax - half, line ? ay : ay - half];
      [bx, by] = [ax + DEFAULT_SIZE, line ? ay : ay + DEFAULT_SIZE];
    }
    const frame = [Math.min(ax, bx), Math.min(ay, by), Math.abs(bx - ax), Math.abs(by - ay)];
    let item = null;
    const tool = op.tool;
    if (tool === "text" || tool === "label") {
      const lab = tool === "label";
      const pl = d.panel_label || {};
      const run = { t: lab ? this.nextPanelLetter() : "", font: lab ? pl.font : d.text?.font || "Helvetica",
        size: lab ? pl.size || 8 : d.text?.size || 6, bold: lab ? !!pl.bold : false, italic: false, color: "#000000" };
      const boxed = op.moved && !lab;
      item = { id: uid("it"), type: "shape", geom: "rect", textbox: true, stroke: null, fill: null, rot: 0,
        frame: boxed ? frame : [ax, ay, 10, 10],
        text: { paragraphs: [{ align: "l", runs: [run] }], insets: boxed ? [7.2, 3.6, 7.2, 3.6] : [0, 0, 0, 0],
          wrap: boxed, anchor: "t", autofit: "shape" } };
      // A figure with a text style called Panel label gives it to new labels
      const labelStyle = lab && (store.doc.text_styles || []).find((x) => x.name.trim().toLowerCase() === "panel label");
      if (labelStyle) applyTextStyle(item, labelStyle);
      // A label put on or near a picture or group stays with it (labels.js)
      const panel = lab && panelAt(store.scopeItems(), [ax, ay]);
      if (panel) item.attach = { to: panel.id };
      store.update(lab ? "Add panel label" : "Add text", (doc) => store.container(doc).push(item), { select: [item.id] });
      this.setTool("select");
      if (!lab) setTimeout(() => this.startEdit(item.id, true), 30);
      return;
    }
    if (tool === "sigbracket") {
      // A significance bracket over the span dragged: across (bar at the drag's height, label
      // above) or, dragged upright, with its label to the right
      const upright = Math.abs(by - ay) > Math.abs(bx - ax);
      item = { id: uid("it"), type: "bracket", label: "*", size: 6, bold: false, line_width: 0.75, color: "#000000", rot: 0,
        dir: upright ? "right" : "up", tick: 4 };
      item.frame = upright ? [ax, Math.min(ay, by), 4 + 6 * 1.5 + 6, Math.max(Math.abs(by - ay), 1)]
        : [Math.min(ax, bx), ay - labelRoom(item), Math.max(Math.abs(bx - ax), 1), labelRoom(item) + 4];
      store.update("Add bracket", (doc) => store.container(doc).push(item), { select: [item.id] });
      announce("Added a significance bracket: choose its label in its own tab");
      this.setTool("select");
      return;
    }
    if (tool === "line" || tool === "arrow") {
      item = { id: uid("it"), type: "line", points: [[ax, ay], [bx, by]], stroke,
        arrow_start: null, arrow_end: tool === "arrow" ? { type: "triangle", w: "med", len: "med" } : null };
      if (op.startLink) item.start_link = op.startLink;
      if (op.endLink && op.moved) item.end_link = op.endLink;
    } else {
      const geom = this.toolGeom(tool);
      if (!geom) { this.drawOverlay(); return; }
      item = { id: uid("it"), type: "shape", geom, frame, rot: 0, flip_h: false, flip_v: false, stroke,
        fill: null, arrow_start: null, arrow_end: null };
    }
    store.update("Draw", (doc) => store.container(doc).push(item), { select: [item.id] });
    announce(`Added ${describeItem(item, store.doc)}`);
    this.setTool("select");
  },
  nextPanelLetter() {
    const used = new Set();
    const caseLower = (this.defaults?.panel_label?.case || "lower") === "lower";
    for (const it of store.items()) {
      const t = (it.text?.paragraphs?.[0]?.runs || []).map((r) => r.t).join("").trim();
      if (/^[a-zA-Z]$/.test(t)) used.add(t.toLowerCase());
    }
    for (let c = 97; c < 123; c++) {
      const ch = String.fromCharCode(c);
      if (!used.has(ch)) return caseLower ? ch : ch.toUpperCase();
    }
    return "a";
  },

  // The pen and point editing (pen.js) ------------------------------------------------
  // The pen: a click places a corner, a drag pulls out a smooth point's handles, a click on the
  // first point closes the shape; Enter, Escape or a double-click finishes an open path, and
  // Backspace takes back the last point. An open path of corners becomes a line.

  penDown(p, e) {
    this.penTargets ||= this.snapTargets([]);
    const q = this.snapPoint(p, this.penTargets, e), pen = this.pen ||= { nodes: [] };
    const first = pen.nodes[0];
    if (first && pen.nodes.length >= 2) {
      const [ax, ay] = this.toScreen(...first.p), [bx, by] = this.toScreen(...q);
      if (Math.hypot(ax - bx, ay - by) <= HANDLE) return this.finishPen(true);
    }
    pen.nodes.push({ p: q, hin: null, hout: null, smooth: false });
    this.op = { type: "pen" };
    this.drawOverlay();
  },
  penDrag(p) {
    const n = this.pen?.nodes[this.pen.nodes.length - 1];
    if (!n) return;
    if (Math.hypot(p[0] - n.p[0], p[1] - n.p[1]) * this.k < 3) Object.assign(n, { hin: null, hout: null, smooth: false });
    else Object.assign(n, { hout: p, hin: [2 * n.p[0] - p[0], 2 * n.p[1] - p[1]], smooth: true });
    this.penHover = null;
    this.drawOverlay();
  },
  finishPen(closed) {
    const pen = this.pen;
    this.pen = this.penHover = this.penTargets = null;
    // A double-click's second click lands on the last point again
    const nodes = (pen?.nodes || []).filter((n, i, all) => i === 0 || n.hin || Math.hypot(n.p[0] - all[i - 1].p[0], n.p[1] - all[i - 1].p[1]) > 0.01);
    if (nodes.length < 2) { this.drawOverlay(); return; }
    const d = this.defaults || {};
    const stroke = { color: "#000000", width: d.stroke_width || 1, dash: "solid", cap: "round", join: "round", opacity: 1 };
    let item;
    if (!closed && nodes.every((n) => !n.hin && !n.hout)) {
      item = { id: uid("it"), type: "line", points: nodes.map((n) => n.p), stroke, arrow_start: null, arrow_end: null };
    } else {
      item = { id: uid("it"), type: "shape", geom: "custom", frame: [0, 0, 1, 1], rot: 0, flip_h: false, flip_v: false, stroke, fill: null,
        arrow_start: null, arrow_end: null };
      writeRings(item, [{ nodes, closed, group: 0, fill: true, stroke: true }]);
    }
    store.update("Draw with the pen", (doc) => store.container(doc).push(item), { select: [item.id] });
    announce(`Drew ${closed ? "a closed shape" : item.type === "line" ? "a line" : "an open path"} of ${nodes.length} points; `
      + (item.type === "shape" ? "double-click it to edit its points" : "drag its points to change it"));
    this.setTool("select");
  },
  drawPen(o) {
    const pen = this.pen, S = (p) => this.toScreen(...p).join(" ");
    if (!pen?.nodes.length) return;
    let d = `M${S(pen.nodes[0].p)}`;
    pen.nodes.slice(1).forEach((n, i) => {
      const a = pen.nodes[i];
      d += a.hout || n.hin ? `C${S(a.hout || a.p)} ${S(n.hin || n.p)} ${S(n.p)}` : `L${S(n.p)}`;
    });
    o.append(s("path", { class: "pen-path", d }));
    const last = pen.nodes[pen.nodes.length - 1];
    if (this.penHover) {
      o.append(s("path", { class: "pen-next", d: `M${S(last.p)}${last.hout ? `C${S(last.hout)} ${S(this.penHover)} ` : "L"}${S(this.penHover)}` }));
    }
    for (const h0 of [last.hin, last.hout].filter(Boolean)) {
      const [x1, y1] = this.toScreen(...last.p), [x2, y2] = this.toScreen(...h0);
      o.append(s("line", { class: "pt-arm", x1, y1, x2, y2 }), s("circle", { class: "pt-handle", cx: x2, cy: y2, r: 3.5 }));
    }
    pen.nodes.forEach((n, i) => {
      const [x, y] = this.toScreen(...n.p), r = i === 0 && pen.nodes.length >= 2 ? 4.5 : 3.5;
      o.append(s("rect", { class: `pt-node${i === 0 ? " first" : ""}`, x: x - r, y: y - r, width: 2 * r, height: 2 * r }));
    });
  },

  // Editing a freeform shape's points: drag a point or a handle (Option for a corner), click the
  // outline to add a point, double-click a point for smooth or corner, Delete removes the one
  // picked, Escape or Enter when done
  startPointEdit(id) {
    const it = store.item(id);
    if (it?.geom !== "custom" || it.locked) return;
    store.select([id]);
    this.pointEdit = { id, sel: null };
    this.drawOverlay();
    announce("Editing points: drag a point or handle, click the outline to add a point, double-click a point to make it "
      + "smooth or a corner, Delete removes it, Escape when done");
  },
  endPointEdit() {
    if (!this.pointEdit) return false;
    this.pointEdit = null;
    this.drawOverlay();
    announce("Done editing points");
    return true;
  },
  // What's under the pointer: a handle, a point, or the outline
  pointHit(it, pt) {
    const rings = ringsOf(it), S = (q) => this.toScreen(...toPageOf(it, q));
    const close = (q, r) => { const [x, y] = S(q); return Math.hypot(x - pt[0], y - pt[1]) <= r; };
    for (let ri = 0; ri < rings.length; ri++) {
      for (let ni = 0; ni < rings[ri].nodes.length; ni++) {
        const n = rings[ri].nodes[ni];
        for (const kind of ["hin", "hout"]) if (n[kind] && close(n[kind], HANDLE)) return { kind, ri, ni };
      }
    }
    for (let ri = 0; ri < rings.length; ri++) {
      for (let ni = 0; ni < rings[ri].nodes.length; ni++) if (close(rings[ri].nodes[ni].p, HANDLE)) return { kind: "node", ri, ni };
    }
    const found = nearestOn(rings, toLocal(it, this.toPage(...pt)));
    if (found && close(found.at, 5)) return { kind: "seg", ...found };
    return null;
  },
  pointDown(pt, p) {
    const it = store.item(this.pointEdit.id);
    const hit = it && this.pointHit(it, pt);
    if (hit && hit.kind !== "seg") {
      this.pointEdit.sel = { ri: hit.ri, ni: hit.ni };
      store.beginLive();
      this.op = { type: "pointdrag", hit, start: p, item0: JSON.parse(JSON.stringify(it)), rings: ringsOf(it), moved: false,
        targets: this.snapTargets([it.id]) };
      this.drawOverlay();
      return true;
    }
    if (hit) {
      const rings = ringsOf(it), ni = splitAt(rings, hit.ring, hit.seg, hit.t);
      store.update("Add point", (doc) => writeRings(findDeep(doc.pages[store.pageIndex].items, it.id), rings));
      this.pointEdit.sel = { ri: hit.ring, ni };
      announce("Added a point");
      return true;
    }
    if (it && hitItem(it, p, 4 / this.k)) return true;   // inside the shape: nothing to do
    this.endPointEdit();
    return false;
  },
  pointDragTo(p, e) {
    const op = this.op, live = findDeep(store.items(), this.pointEdit?.id);
    if (!live || (!op.moved && Math.hypot(p[0] - op.start[0], p[1] - op.start[1]) * this.k < 2)) return;
    op.moved = true;
    const rings = JSON.parse(JSON.stringify(op.rings)), n = rings[op.hit.ri].nodes[op.hit.ni];
    if (op.hit.kind === "node") {
      const q = this.snapPoint(p, op.targets, e), [x0, y0] = toLocal(op.item0, op.start), [x1, y1] = toLocal(op.item0, q);
      moveNode(n, x1 - x0, y1 - y0);
    } else {
      moveHandle(n, op.hit.kind, toLocal(op.item0, p), e.altKey);
    }
    const tmp = JSON.parse(JSON.stringify(op.item0));
    writeRings(tmp, rings);
    live.frame = tmp.frame;
    live.path = tmp.path;
    store.live();
  },
  drawPointEdit(o, it) {
    const rings = ringsOf(it), S = (q) => this.toScreen(...toPageOf(it, q)), sel = this.pointEdit?.sel;
    let d = "";
    for (const r of rings) {
      d += `M${S(r.nodes[0].p).join(" ")}`;
      for (const [a, b] of segments(r)) {
        d += a.hout || b.hin ? `C${S(a.hout || a.p).join(" ")} ${S(b.hin || b.p).join(" ")} ${S(b.p).join(" ")}` : `L${S(b.p).join(" ")}`;
      }
      if (r.closed) d += "Z";
    }
    o.append(s("path", { class: "point-path", d }));
    rings.forEach((r, ri) => r.nodes.forEach((n, ni) => {
      const [x, y] = S(n.p);
      for (const h0 of [n.hin, n.hout].filter(Boolean)) {
        const [hx, hy] = S(h0);
        o.append(s("line", { class: "pt-arm", x1: x, y1: y, x2: hx, y2: hy }), s("circle", { class: "pt-handle", cx: hx, cy: hy, r: 3.5 }));
      }
      const picked = sel && sel.ri === ri && sel.ni === ni;
      o.append(s("rect", { class: `pt-node${picked ? " picked" : ""}${n.smooth ? " smooth" : ""}`, x: x - 3.5, y: y - 3.5, width: 7, height: 7 }));
    }));
  },
  // Keys while drawing with the pen or editing points (before the editor's shortcuts, so Delete
  // removes a point rather than the shape)
  penKey(e) {
    if (this.pen) {
      if (e.key === "Enter" || e.key === "Escape") { this.finishPen(false); return true; }
      if (e.key === "Backspace" || e.key === "Delete") {
        this.pen.nodes.pop();
        if (!this.pen.nodes.length) this.pen = null;
        this.drawOverlay();
        return true;
      }
      return false;
    }
    if (!this.pointEdit) return false;
    if (e.key === "Escape" || e.key === "Enter") return this.endPointEdit();
    if (e.key !== "Backspace" && e.key !== "Delete") return false;
    const it = store.item(this.pointEdit.id), sel = this.pointEdit.sel;
    if (!it || !sel) return true;
    const rings = ringsOf(it), r = rings[sel.ri];
    if (!r || r.nodes.length <= 2) { announce("A path needs at least two points"); return true; }
    r.nodes.splice(sel.ni, 1);
    store.update("Remove point", (doc) => writeRings(findDeep(doc.pages[store.pageIndex].items, it.id), rings));
    this.pointEdit.sel = null;
    announce("Removed the point");
    return true;
  },

  // Cropping ------------------------------------------------------------------------

  startCrop(id) {
    const it = store.item(id);
    if (!it || it.type !== "picture") return;
    store.select([id]);
    this.cropping = id;
    this.drawGhost();
    this.drawOverlay();
    announce("Cropping. Drag the edges to crop, drag the picture to move it inside the frame, press Enter when done.");
  },
  endCrop() {
    this.cropping = null;
    this.ghostLayer.replaceChildren();
    this.drawOverlay();
    announce("Done cropping");
  },
  // The whole uncropped picture, faint, behind the crop window
  fullFrame(it) {
    const asset = store.doc.assets[it.asset];
    const [sw, sh] = asset.size_pt;
    const [l, t, r, b] = it.crop;
    const scx = it.frame[2] / (sw * (1 - l - r)), scy = it.frame[3] / (sh * (1 - t - b));
    const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v);
    const full = mul(m, mul(translate(-l * sw * scx, -t * sh * scy), [scx, 0, 0, scy, 0, 0]));
    return { m: full, sw, sh, scx, scy };
  },
  drawGhost() {
    const it = store.item(this.cropping);
    this.ghostLayer.replaceChildren();
    if (!it) return;
    const asset = store.doc.assets[it.asset];
    const { m, sw, sh } = this.fullFrame(it);
    const g = s("g", { transform: svgMatrix(m), opacity: 0.35 });
    g.append(s("image", { width: sw, height: sh, preserveAspectRatio: "none", href: this.previewUrl(it, asset) }));
    this.ghostLayer.append(g);
  },
  drawCropHandles() {
    const it = store.item(this.cropping);
    if (!it) return;
    const { m, sw, sh } = this.fullFrame(it);
    this.overlay.append(this.outline([[0, 0], [sw, 0], [sw, sh], [0, sh]].map(([x, y]) => apply(m, x, y)), "crop-full"));
    this.overlay.append(this.outline(itemCorners(it), "sel-outline crop"));
    for (const hd of this.cropHandles(it)) {
      this.overlay.append(s("rect", { class: "handle crop", x: hd.at[0] - HANDLE / 2 - 1, y: hd.at[1] - HANDLE / 2 - 1,
        width: HANDLE + 2, height: HANDLE + 2 }));
    }
  },
  cropHandles(it) {
    const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v);
    const [, , w, h] = it.frame;
    const pts = { nw: [0, 0], n: [w / 2, 0], ne: [w, 0], e: [w, h / 2], se: [w, h], s: [w / 2, h], sw: [0, h], w: [0, h / 2] };
    return Object.entries(pts).map(([dir, [x, y]]) => ({ kind: "crop", dir, at: this.toScreen(...apply(m, x, y)) }));
  },
  cropHandleAt(pt) {
    const it = store.item(this.cropping);
    if (!it) return null;
    return this.cropHandles(it).find((hd) => Math.abs(pt[0] - hd.at[0]) <= HANDLE && Math.abs(pt[1] - hd.at[1]) <= HANDLE) || null;
  },
  startCropHandle(hd, p) {
    const it = store.item(this.cropping);
    store.beginLive();
    this.op = { type: "crop", dir: hd.dir, orig: JSON.parse(JSON.stringify(it)), moved: false, label: "Crop" };
  },
  cropTo(p) {
    const op = this.op, o = op.orig, it = store.item(this.cropping);
    const { m, sw, sh, scx, scy } = this.fullFrame(o);
    const [ux, uy] = apply(invert(m), ...p);     // pointer in source points
    let [l, t, r, b] = o.crop;
    const minW = 2 / scx, minH = 2 / scy;
    if (op.dir.includes("w")) l = clamp(ux / sw, 0, 1 - r - minW / sw);
    if (op.dir.includes("e")) r = clamp(1 - ux / sw, 0, 1 - l - minW / sw);
    if (op.dir.includes("n")) t = clamp(uy / sh, 0, 1 - b - minH / sh);
    if (op.dir.includes("s")) b = clamp(1 - uy / sh, 0, 1 - t - minH / sh);
    // Keep the picture's scale: the frame follows the crop window
    const [x0, y0] = apply(m, l * sw, t * sh);
    const nw = sw * (1 - l - r) * scx, nh = sh * (1 - t - b) * scy;
    const rm = frameMatrix([0, 0, nw, nh], o.rot || 0, o.flip_h, o.flip_v);
    const [ox, oy] = apply(rm, 0, 0);
    it.crop = [l, t, r, b];
    it.frame = [x0 - ox, y0 - oy, nw, nh];
    op.moved = true;
    store.live();
  },
  startCropMove(it, p) {
    store.beginLive();
    this.op = { type: "cropmove", start: p, orig: JSON.parse(JSON.stringify(it)), moved: false, label: "Move picture in crop" };
  },
  cropMoveTo(p) {
    const op = this.op, o = op.orig, it = store.item(this.cropping);
    const { m, sw, sh } = this.fullFrame(o);
    const inv = invert(m);
    const [ax, ay] = apply(inv, ...op.start), [bx, by] = apply(inv, ...p);
    const dx = (ax - bx) / sw, dy = (ay - by) / sh;   // moving the picture right shows more of its left
    let [l, t, r, b] = o.crop;
    const ddx = clamp(dx, -l, r), ddy = clamp(dy, -t, b);
    it.crop = [l + ddx, t + ddy, r - ddx, b - ddy];
    op.moved = true;
    store.live();
    this.drawGhost();
  },

  // Text editing ------------------------------------------------------------------------

  startEdit(id, isNew = false) {
    const it = store.item(id);
    if (!it || it.type !== "shape" || it.geom === "region") return;   // an area fill holds no text
    if (!it.text) it.text = { paragraphs: [{ align: "ctr", runs: [{ t: "", font: "Helvetica", size: 6 }] }],
      insets: [7.2, 3.6, 7.2, 3.6], wrap: true, anchor: "ctr", autofit: "none" };
    // (range: the words last highlighted, as positions; mine, top and redo: the undo steps changes
    // from the ribbon made while typing, and where the history stood after them; typed: since then)
    this.editing = { id, isNew, before: JSON.stringify(it.text), range: null, domRange: null, mine: 0,
      top: store.history.length, redo: 0, typed: false };
    const e = this.els.get(id);
    if (e) e.g.style.visibility = "hidden";
    const ed = this.editor;
    this.fillEditor(it.text);
    this.editing.parsed = JSON.stringify(parseEditor(ed, it.text));
    ed.hidden = false;
    this.positionEditor();
    ed.focus();
    const range = document.createRange();
    range.selectNodeContents(ed);
    if (!isNew) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }
    this.drawOverlay();
    announce("Editing text. Press Escape when done.");
    document.dispatchEvent(new CustomEvent("fa-editing", { detail: true }));
  },
  // The text in the editor: a line (div) per paragraph, holding its own settings in data-para,
  // and a span per run of one look (data-run)
  fillEditor(text) {
    this.editor.replaceChildren(...text.paragraphs.map((p) => {
      const own = { ...p };
      delete own.runs;
      delete own.align;
      const div = h("div", { "data-para": JSON.stringify(own), style: { textAlign: { l: "left", ctr: "center", r: "right" }[p.align || "l"] } });
      const runs = (p.runs || []).filter((r) => r.t !== undefined);
      if (!runs.length || runs.every((r) => !r.t)) div.append(h("br"));
      for (const r of runs) {
        const parts = r.t.split("\n");
        parts.forEach((part, i) => {
          if (i) div.append(h("br"));
          // Raised or lowered text sits in <sup> or <sub>, which the editor's own commands toggle
          const script = r.baseline > 0 ? h("sup", {}, part) : r.baseline < 0 ? h("sub", {}, part) : part;
          if (part) div.append(h("span", { "data-run": JSON.stringify({ ...r, t: undefined, baseline: undefined }), style: runCss(r) }, script));
        });
      }
      return div;
    }));
  },
  positionEditor() {
    if (!this.editing) return;
    const it = store.item(this.editing.id);
    if (!it) return;
    const [x, y, w, hgt] = it.frame;
    const ins = it.text.insets || [7.2, 3.6, 7.2, 3.6];
    const k = this.k;
    const [sx, sy] = this.toScreen(x, y);
    const ed = this.editor;
    Object.assign(ed.style, {
      left: `${sx}px`, top: `${sy}px`, width: `${Math.max(w * k, 20)}px`, minHeight: `${hgt * k}px`,
      padding: `${ins[1] * k}px ${ins[2] * k}px ${ins[3] * k}px ${ins[0] * k}px`,
      transform: `rotate(${it.rot || 0}deg)`, transformOrigin: `${(w * k) / 2}px ${(hgt * k) / 2}px`,
      fontSize: `${(it.text.paragraphs[0]?.runs?.[0]?.size || 6) * k}px`,
      whiteSpace: it.text.wrap === false ? "pre" : "pre-wrap",
    });
    ed.style.setProperty("--k", k);
    for (const span of ed.querySelectorAll("span[data-run]")) {
      const r = JSON.parse(span.dataset.run);
      span.style.fontSize = `${(r.size || 6) * k}px`;
    }
  },
  editorKey(e) {
    const mod = e.metaKey || e.ctrlKey;
    if (e.key === "Escape") { e.preventDefault(); this.commitEdit(); return; }
    // ⌘Z right after a change from the ribbon undoes it, and typing carries on (undoTyping); the
    // ribbon's keys that work while typing (bigger and smaller text) run its commands
    if (mod && !e.altKey && e.key.toLowerCase() === "z" && this.undoTyping(e.shiftKey)) { e.preventDefault(); return; }
    if (this.typingKey?.(e)) { e.preventDefault(); return; }
    if (mod && ["b", "i", "u"].includes(e.key.toLowerCase())) {
      e.preventDefault();
      document.execCommand({ b: "bold", i: "italic", u: "underline" }[e.key.toLowerCase()]);
    }
    // PowerPoint's keys: ⌘⇧= superscript, ⌘= subscript (they zoom only when not typing)
    if (mod && (e.key === "=" || e.key === "+")) {
      e.preventDefault();
      document.execCommand(e.shiftKey || e.key === "+" ? "superscript" : "subscript");
    }
    if (e.key === "Enter" && e.shiftKey) { e.preventDefault(); document.execCommand("insertLineBreak"); }
    keepFieldKeys(e);
  },
  commitEdit() {
    const ed = this.editing;
    if (!ed) return;
    this.editing = null;
    try {
      const it = store.item(ed.id);
      this.editor.hidden = true;
      const e = this.els.get(ed.id);
      if (e) e.g.style.visibility = "";
      if (!it) return;
      const paragraphs = parseEditor(this.editor, it.text);
      const empty = paragraphs.every((p) => p.runs.every((r) => !r.t.trim()));
      if (empty && it.textbox) {
        store.update(ed.isNew ? "Add text" : "Delete text", (doc) => {
          const items = store.container(doc);
          items.splice(items.findIndex((i) => i.id === ed.id), 1);
        }, { select: [] });
        return;
      }
      const after = { ...it.text, paragraphs };
      // (nothing typed since the text was put in the editor: the document already has it)
      if (JSON.stringify(paragraphs) !== ed.parsed && JSON.stringify(after) !== ed.before) {
        store.update("Edit text", (doc) => { findDeep(doc.pages[store.pageIndex].items, ed.id).text = after; });
      } else this.render({});
      this.stage.focus({ preventScroll: true });
      this.drawOverlay();
    } finally {
      document.dispatchEvent(new CustomEvent("fa-editing", { detail: false }));
    }
  },

  // Changes from the ribbon while typing (textribbon.js) ---------------------------------

  // The text as typed so far, as paragraphs of runs
  editorModel() {
    const it = this.editing && store.item(this.editing.id);
    return it ? parseEditor(this.editor, it.text) : [];
  },
  // The words highlighted in the text being typed, as positions [paragraph, character]: as they
  // are, or as they were when the text last had the focus (a field in the ribbon has it, say)
  editorRange() {
    const ed = this.editing, it = ed && store.item(ed.id);
    if (!it) return null;
    const sel = window.getSelection();
    if (sel.rangeCount && this.editor.contains(sel.anchorNode) && this.editor.contains(sel.focusNode)) {
      const read = readEditor(this.editor, it.text);
      ed.range = ordered({ start: toPosition(read, this.editor, sel.anchorNode, sel.anchorOffset),
        end: toPosition(read, this.editor, sel.focusNode, sel.focusOffset) });
      ed.domRange = sel.getRangeAt(0).cloneRange();
    }
    return ed.range;
  },
  setEditorRange(range) {
    const ed = this.editing, it = ed && store.item(ed.id);
    if (!it || !range) return;
    const read = readEditor(this.editor, it.text), last = read.paragraphs.length - 1;
    const fit = ([p, c]) => {
      const q = Math.min(Math.max(p, 0), last);
      return [q, Math.min(Math.max(c, 0), paraLength(read.paragraphs[q]))];
    };
    const r = { start: fit(range.start), end: fit(range.end) };
    const a = toPoint(read, r.start), b = toPoint(read, r.end);
    const sel = window.getSelection();
    sel.setBaseAndExtent(a[0], a[1], b[0], b[1]);
    ed.range = r;
    ed.domRange = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  },
  // The text's selection back, after a field or menu in the ribbon had the focus
  restoreSelection() {
    const ed = this.editing;
    if (!ed) return;
    this.editor.focus({ preventScroll: true });
    const sel = window.getSelection(), d = ed.domRange;
    if (d && this.editor.contains(d.startContainer) && this.editor.contains(d.endContainer)) {
      sel.removeAllRanges();
      sel.addRange(d);
    } else if (ed.range) this.setEditorRange(ed.range);
  },
  // The look of the text at the caret, which typing there takes (from the run before it)
  caretStyle() {
    const ed = this.editing, it = ed && store.item(ed.id);
    const base = { ...(it?.text?.paragraphs?.[0]?.runs?.[0] || { font: "Helvetica", size: 6 }) };
    delete base.t;
    delete base.baseline;
    const sel = window.getSelection();
    const live = sel.rangeCount && this.editor.contains(sel.getRangeAt(0).startContainer) ? sel.getRangeAt(0) : null;
    const r = live || ed?.domRange;
    if (!r || !this.editor.contains(r.startContainer)) return base;
    const inmost = (n, last) => {
      while (n && n.nodeType === 1 && n.tagName !== "BR" && n.childNodes.length) n = last ? n.lastChild : n.firstChild;
      return n;
    };
    let node = r.startContainer;
    if (node.nodeType === 1) node = inmost(node.childNodes[r.startOffset - 1], true) || inmost(node.childNodes[r.startOffset], false) || node;
    const chain = [];
    for (let n = node.nodeType === 1 && node.tagName !== "BR" ? node : node.parentNode; n && n !== this.editor; n = n.parentNode) chain.unshift(n);
    return chain.reduce((st, n) => nodeStyle(n, st), base);
  },
  // A change to the look with only the caret: it applies to what's typed next, from a marker at
  // the caret, a zero-width space in a span of the new look that typing goes into (the space is
  // taken out when the text is read back)
  pendingStyle(fn) {
    const ed = this.editing;
    if (!ed) return;
    this.restoreSelection();
    const sel = window.getSelection();
    if (!sel.rangeCount) return;
    const range = sel.getRangeAt(0);
    const run = this.caretStyle();
    fn(run);
    const at = range.startContainer.nodeType === 3 ? range.startContainer.parentNode : range.startContainer;
    let span = at.closest?.("span[data-pending]");
    if (span && span.textContent.replace(/​/g, "")) span = null;   // typed into already: a new marker for what follows
    if (!span) {
      span = h("span", { "data-pending": "" }, "​");
      // An empty line's placeholder break goes: the marker holds the line open now
      let line = at;
      while (line && line.parentNode !== this.editor) line = line.parentNode;
      if (line?.childNodes.length === 1 && line.firstChild.nodeName === "BR") line.firstChild.remove();
      range.insertNode(span);
    }
    span.dataset.run = JSON.stringify({ ...run, t: undefined, baseline: undefined });
    Object.assign(span.style, runCss(run));
    span.style.fontSize = `${(run.size || 6) * this.k}px`;
    sel.collapse(span.firstChild, span.firstChild.textContent.length);
    ed.domRange = sel.getRangeAt(0).cloneRange();
    this.editorRange();
  },
  // A change to the text being typed: what's been typed goes into the document as one undo step
  // and the change as another (formatText: over the range, or all of it with none). Typing then
  // carries on with the same words highlighted, and ⌘Z before any more typing undoes the change
  retype(label, change, range) {
    const ed = this.editing, it = ed && store.item(ed.id);
    if (!it) return;
    const keep = range || ed.range;
    const typed = parseEditor(this.editor, it.text);
    const save = (lbl, fn) => {
      store.update(lbl, (doc) => { const o = findDeep(doc.pages[store.pageIndex].items, ed.id); if (o) fn(o); });
      ed.mine++;
    };
    if (JSON.stringify(typed) !== ed.parsed) {
      save("Edit text", (o) => { o.text = { ...o.text, paragraphs: typed }; });
      ed.isNew = false;
    }
    save(label, (o) => formatText(o.text, range, change));
    ed.top = store.history.length;
    ed.redo = 0;
    this.refill(keep);
  },
  // The editor filled again from the box's text, with these words highlighted
  refill(range) {
    const ed = this.editing, it = ed && store.item(ed.id);
    if (!it) return;
    this.fillEditor(it.text);
    ed.before = JSON.stringify(it.text);
    ed.parsed = JSON.stringify(parseEditor(this.editor, it.text));
    ed.typed = false;
    ed.domRange = null;
    this.positionEditor();
    this.editor.focus({ preventScroll: true });
    if (range) this.setEditorRange(range);
  },
  // ⌘Z (⌘⇧Z) right after a change from the ribbon, before more typing: the change comes out of
  // (goes back into) the document, and typing carries on. Only this typing's own steps, and only
  // while nothing else has changed the document since
  undoTyping(redo) {
    const ed = this.editing;
    if (!ed || ed.typed || store.history.length !== ed.top) return false;
    if (redo ? !(ed.redo > 0 && store.future.length) : !(ed.mine > 0)) return false;
    const range = ed.range, label = redo ? store.redo() : store.undo();
    if (redo) { ed.mine++; ed.redo--; } else { ed.mine--; ed.redo++; }
    ed.top = store.history.length;
    this.refill(range);
    announce(`${redo ? "Redid" : "Undid"} ${label}`);
    return true;
  },
  // A change to text, from the ribbon or the properties panel. target: {typing, id, range, whole}
  // for the box being typed in (the words in range, or with only the caret what's typed next;
  // whole: all its text), or {ids} for the objects selected (all their text). Typing that ended
  // before the change came (a field's change on leaving it) gets it in the document, in its range
  changeText(label, change, target) {
    const ed = this.editing;
    if (target.typing && ed?.id === target.id) {
      const range = target.whole ? null : target.range || ed.range;
      if (change.run && !change.para && !change.body && range && collapsed(range)) return this.pendingStyle(change.run);
      return this.retype(label, change, range);
    }
    const ids = target.typing ? [target.id] : target.ids, range = target.typing && !target.whole ? target.range : null;
    store.update(label, (doc) => {
      for (const id of ids) {
        const it = findDeep(doc.pages[store.pageIndex].items, id);
        if (it?.text) formatText(it.text, range, change);
      }
    });
  },
};

// Helpers -------------------------------------------------------------------------------

function resizeCursor(dir, it) {
  const base = { n: 0, ne: 45, e: 90, se: 135, s: 180, sw: 225, w: 270, nw: 315 }[dir] ?? 0;
  const a = (((base + (it?.rot || 0)) % 180) + 180) % 180;
  return ["ns-resize", "nesw-resize", "ew-resize", "nwse-resize"][Math.round(a / 45) % 4];
}

export function shiftItem(it, orig, dx, dy) {
  if (it.type === "group") {
    if (it.grid?.origin && orig.grid?.origin) it.grid.origin = [orig.grid.origin[0] + dx, orig.grid.origin[1] + dy];
    it.items.forEach((c, i) => shiftItem(c, orig.items[i], dx, dy));
  } else if (it.type === "line") {
    it.points = orig.points.map((p) => [p[0] + dx, p[1] + dy]);
  } else {
    it.frame = [orig.frame[0] + dx, orig.frame[1] + dy, orig.frame[2], orig.frame[3]];
  }
}

// Turn an object by `angle` degrees (clockwise) about (cx, cy): a framed object's middle goes
// round and the object turns with it; a line's points turn; a group's parts each do
export function rotateItem(it, angle, cx, cy) {
  const r = (angle * Math.PI) / 180, c = Math.cos(r), s = Math.sin(r);
  const turn = ([x, y]) => [cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c];
  if (it.type === "group") it.items.forEach((k) => rotateItem(k, angle, cx, cy));
  else if (it.type === "line") it.points = it.points.map(turn);
  else {
    const [x, y, w, h] = it.frame;
    const [mx, my] = turn([x + w / 2, y + h / 2]);
    it.frame = [mx - w / 2, my - h / 2, w, h];
    it.rot = ((((it.rot || 0) + angle) % 360) + 360) % 360;
  }
}

// Resize an object by (sx, sy), keeping the point at (fx, fy) of its own box where it is (a
// turned object along its own sides; a line or group along the page's)
export function scaleItem(it, sx, sy, [fx, fy]) {
  if (it.frame && it.type !== "group") {
    const [, , w, h] = it.frame;
    const [px, py] = apply(frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v), fx * w, fy * h);
    const nw = Math.max(w * sx, 0.5), nh = Math.max(h * sy, 0.5);
    const q = apply(frameMatrix([0, 0, nw, nh], it.rot || 0, it.flip_h, it.flip_v), fx * nw, fy * nh);
    it.frame = [px - q[0], py - q[1], nw, nh];
    return;
  }
  const pts = itemCorners(it);
  const x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0]));
  const y0 = Math.min(...pts.map((p) => p[1])), y1 = Math.max(...pts.map((p) => p[1]));
  scaleAbout(it, sx, sy, x0 + fx * (x1 - x0), y0 + fy * (y1 - y0));
}
function scaleAbout(it, sx, sy, ax, ay) {
  if (it.type === "group") it.items.forEach((k) => scaleAbout(k, sx, sy, ax, ay));
  else if (it.type === "line") it.points = it.points.map(([x, y]) => [ax + (x - ax) * sx, ay + (y - ay) * sy]);
  else {
    const [x, y, w, h] = it.frame;
    const [cx, cy] = [ax + (x + w / 2 - ax) * sx, ay + (y + h / 2 - ay) * sy];
    const nw = Math.max(w * sx, 0.5), nh = Math.max(h * sy, 0.5);
    it.frame = [cx - nw / 2, cy - nh / 2, nw, nh];
  }
}

export function reid(it, ids = null) {
  const old = it.id;
  it.id = uid("it");
  if (ids) ids.set(old, it.id);
  if (it.type === "group") it.items.forEach((c) => reid(c, ids));
  return it;
}
// Copies of items with new ids; a copied line stays attached only to objects copied with it
export function copyItems(items) {
  const ids = new Map();
  // Area fills' paths as last drawn, by their old ids: one copied without its lines becomes an
  // ordinary shape of its area as it is
  const paths = new Map();
  for (const it of allRegions(items)) paths.set(it.id, canvas.els.get(it.id)?.regionPath);
  const copies = items.map((it) => reid(JSON.parse(JSON.stringify(it)), ids));
  for (const line of allLines(copies)) {
    for (const key of ["start_link", "end_link"]) {
      if (!line[key]) continue;
      if (ids.has(line[key].item)) line[key] = { ...line[key], item: ids.get(line[key].item) };
      else delete line[key];
    }
  }
  // A scale bar copied with its picture belongs to the copy, and so do zoom boxes, insets, their
  // lines and panel labels
  const remap = (o, key) => { if (o && ids.has(o[key])) o[key] = ids.get(o[key]); };
  const walk = (its) => its.forEach((it) => {
    if (it.type === "group") walk(it.items);
    if (it.type === "scalebar") remap(it, "picture");
    remap(it.zoom, "picture");
    remap(it.inset, "box");
    remap(it.zoomline, "box");
    remap(it.zoomline, "inset");
    remap(it.attach, "to");   // a label copied with its panel goes with the copy
  });
  walk(copies);
  const oldId = new Map([...ids].map(([o, n]) => [n, o]));
  for (const it of allRegions(copies)) {
    const lines = (it.region.items || []).map((id) => ids.get(id));
    if (lines.every(Boolean)) it.region = { ...it.region, items: lines };
    else detachRegion(it, paths.get(oldId.get(it.id)));
  }
  return copies;
}
export function allRegions(items, out = []) {
  for (const it of items) {
    if (it.type === "group") allRegions(it.items, out);
    else if (it.geom === "region") out.push(it);
  }
  return out;
}
// An area fill as an ordinary freeform shape of its area as last drawn, no longer following its
// lines (stays an area fill if it hasn't been drawn yet)
export function detachRegion(it, path) {
  if (!path) return false;
  it.geom = "custom";
  it.path = JSON.parse(JSON.stringify(path));
  it.fill = { ...(it.fill || { color: "#d9d9d9", opacity: 1 }), even_odd: true };
  delete it.region;
  return true;
}
// The items a move takes along: an area fill's lines and shapes go with it, as it follows them
export function withRegionLines(items) {
  const out = [...items], ids = new Set(items.map((it) => it.id));
  for (const it of allRegions(items)) {
    for (const id of it.region.items || []) {
      const b = !ids.has(id) && findDeep(store.items(), id);
      if (b && !b.locked) { ids.add(id); out.push(b); }
    }
  }
  return out;
}
// Lines being moved on their own let go of objects that aren't moving with them
export function detachMoved(items) {
  const moving = new Set();
  const collect = (list) => list.forEach((it) => { moving.add(it.id); if (it.type === "group") collect(it.items); });
  collect(items);
  for (const line of allLines(items)) {
    for (const key of ["start_link", "end_link"]) if (line[key] && !moving.has(line[key].item)) delete line[key];
  }
}
// An elbow connector's points, a to b in level and upright stretches: leaving a along da and
// reaching b against db (the ways out of the sides they're attached to; null when free, which
// goes the longer way first), the middle stretch at fraction f of the way. Always four points:
// an L-shaped route repeats its corner.
export function elbowRoute(a, b, da, db, f = 0.5) {
  const wide = Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1]);
  const startLevel = da ? da[0] !== 0 : db ? db[0] !== 0 : wide, endLevel = db ? db[0] !== 0 : startLevel;
  if (startLevel && endLevel) { const x = a[0] + (b[0] - a[0]) * f; return [a.slice(), [x, a[1]], [x, b[1]], b.slice()]; }
  if (!startLevel && !endLevel) { const y = a[1] + (b[1] - a[1]) * f; return [a.slice(), [a[0], y], [b[0], y], b.slice()]; }
  const c = startLevel ? [b[0], a[1]] : [a[0], b[1]];
  return [a.slice(), c, c.slice(), b.slice()];
}
export function allLines(items, out = []) {
  for (const it of items) {
    if (it.type === "group") allLines(it.items, out);
    else if (it.type === "line") out.push(it);
  }
  return out;
}
// The point a fraction f of the way along a polyline
function pointAlong(pts, f) {
  let total = 0;
  for (let i = 1; i < pts.length; i++) total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  let left = total * f;
  for (let i = 1; i < pts.length; i++) {
    const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (left <= l && l > 0) return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * (left / l), pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * (left / l)];
    left -= l;
  }
  return pts[pts.length - 1].slice();
}
// A frame's (or a group's box's) corners c0-c3 and side middles m0-m3, as for a rectangle
function boxSites(it) {
  let corners;
  if (it.frame) {
    const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v), [, , w, h] = it.frame;
    corners = [[0, 0], [w, 0], [w, h], [0, h]].map(([x, y]) => apply(m, x, y));
  } else {
    const b = itemBBox(it);
    corners = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
  }
  return [...corners.map((at, k) => ({ key: `c${k}`, at })),
    ...corners.map((a, k) => ({ key: `m${k}`, at: [(a[0] + corners[(k + 1) % 4][0]) / 2, (a[1] + corners[(k + 1) % 4][1]) / 2] }))];
}
// "corner 3", "middle of side 1", "dash 12, start"...
export function siteName(key) {
  const m = /^([a-z])(\d*)([sme]?)$/.exec(key || "");
  if (!m) return "a point";
  const n = Number(m[2]) + 1;
  if (m[1] === "c") return `corner ${n}`;
  if (m[1] === "m") return m[2] === "" ? "the middle" : `the middle of side ${n}`;
  if (m[1] === "p") return `point ${n}`;
  if (m[1] === "e") return m[2] === "0" ? "the start" : "the end";
  if (m[1] === "d") return `dash ${n}, ${{ s: "start", m: "middle", e: "end" }[m[3]] || "middle"}`;
  return "a point";
}

export function findDeep(items, id) {
  for (const it of items) {
    if (it.id === id) return it;
    if (it.type === "group") { const f = findDeep(it.items, id); if (f) return f; }
  }
  return null;
}

// A page's guides, made if it has none yet (pages from older files and imports)
export function pageGuides(page) {
  page.guides = { x: [...(page.guides?.x || [])], y: [...(page.guides?.y || [])] };
  return page.guides;
}
// Guides move with the page's objects when the page is fitted to them
export function shiftGuides(page, dx, dy) {
  if (!page.guides) return;
  page.guides = { x: (page.guides.x || []).map((v) => v + dx), y: (page.guides.y || []).map((v) => v + dy) };
}

// Snapping helpers. Axis i is 0 across (x) or 1 down (y); boxes are [x0, y0, x1, y1].
const edges = (r, i) => [r[i], (r[i] + r[i + 2]) / 2, r[i + 2]];
const lines = (targets, i) => (i ? targets.ys : targets.xs);

// The smallest shift (within tol) that puts one of `vals` on a line; failing that, on a grid line
// inside the page (`len` long on this axis). Lines placed on purpose (the page, guides, objects)
// win over the grid, whose lines are everywhere. Null if nothing is that near.
function nearestSnap(vals, list, grid, len, tol) {
  let best = null;
  const near = (d) => { if (Math.abs(d) <= tol && (best === null || Math.abs(d) < Math.abs(best))) best = d; };
  for (const v of vals) for (const t of list) near(t.v - v);
  if (best !== null || !grid) return best;
  for (const v of vals) {
    const c = Math.round(v / grid) * grid;
    if (c >= -1e-9 && c <= len + 1e-9) near(c - v);
  }
  return best;
}

// The lines `vals` now sit on, for drawing: each runs along what it belongs to and lo-hi across
function snapLines(i, vals, targets, lo, hi) {
  const found = new Map();
  const add = (v, span) => {
    const from = span ? Math.min(span[0], lo) : null, to = span ? Math.max(span[1], hi) : null;
    const had = found.get(v.toFixed(6));
    if (!had) found.set(v.toFixed(6), { axis: i, v, from, to });
    else if (had.from !== null && from === null) { had.from = null; had.to = null; }
    else if (had.from !== null) { had.from = Math.min(had.from, from); had.to = Math.max(had.to, to); }
  };
  for (const v of vals) {
    for (const t of lines(targets, i)) if (Math.abs(t.v - v) < 1e-6) add(t.v, t.span);
    if (targets.grid) {
      const c = Math.round(v / targets.grid) * targets.grid;
      if (Math.abs(c - v) < 1e-6 && c >= -1e-9 && c <= targets.size[i] + 1e-9) add(c, [0, targets.size[1 - i]]);
    }
  }
  return [...found.values()];
}

// Equal spacing along axis i among the boxes level with the moving box b: the shift that leaves
// equal gaps on both sides of it, or that repeats a gap already between two neighbouring boxes.
// Returns {d, pairs} (the boxes either side of each equal gap; null is the moving box) or null.
function equalSpacing(b, i, boxes, tol) {
  const a0 = i, a1 = i + 2, c0 = 1 - i, c1 = 3 - i;
  const level = boxes.filter((r) => r[c0] < b[c1] && r[c1] > b[c0]);
  const size = b[a1] - b[a0];
  let before = null, after = null;
  for (const r of level) {
    if (r[a1] <= b[a0] + tol && (!before || r[a1] > before[a1])) before = r;
    if (r[a0] >= b[a1] - tol && (!after || r[a0] < after[a0])) after = r;
  }
  const cands = [];
  if (before && after) {
    const start = (before[a1] + after[a0] - size) / 2;
    if (start >= before[a1]) cands.push({ d: start - b[a0], pairs: [[before, null], [null, after]] });
  }
  for (const p of level) {
    let q = null;
    for (const r of level) if (r[a0] >= p[a1] && (!q || r[a0] < q[a0])) q = r;
    const gap = q ? q[a0] - p[a1] : 0;
    if (gap < 0.01) continue;
    // (the gap from `before` to `after` is the one the moving box sits in, not one to repeat)
    if (before && before !== p) cands.push({ d: before[a1] + gap - b[a0], pairs: [[before, null], [p, q]] });
    if (after && after !== q) cands.push({ d: after[a0] - gap - size - b[a0], pairs: [[null, after], [p, q]] });
  }
  let best = null;
  for (const c of cands) if (Math.abs(c.d) <= tol && (!best || Math.abs(c.d) < Math.abs(best.d))) best = c;
  return best;
}

// Where to draw each equal gap: between the boxes either side, halfway along where they overlap
function gapMarks(i, pairs, fin) {
  const a1 = i + 2, c0 = 1 - i, c1 = 3 - i;
  return pairs.map(([u, v]) => {
    const p = u || fin, q = v || fin;
    const lo = Math.max(p[c0], q[c0]), hi = Math.min(p[c1], q[c1]);
    return { gap: true, axis: i, a: p[a1], b: q[i], at: lo <= hi ? (lo + hi) / 2 : (p[c0] + p[c1]) / 2 };
  });
}

function runCss(r) {
  const fam = r.font || "Helvetica";
  return { fontFamily: `"${fam}", Helvetica, Arial, sans-serif`, fontWeight: r.bold ? "700" : "400",
    fontStyle: r.italic ? "italic" : "normal", textDecoration: r.underline ? "underline" : "none",
    color: r.color || "#000000" };
}

// Raised and lowered text: its baseline as a fraction of the text size (PowerPoint's defaults)
export const SUPERSCRIPT = 0.3, SUBSCRIPT = -0.25;
// Read the edited text back into paragraphs of runs, keeping each run's other settings
function parseEditor(root, oldText) {
  return readEditor(root, oldText).paragraphs;
}
// The editor's paragraphs, and where their text came from for finding a selection in them
// (toPosition, toPoint): pieces[p] lists each text node and counted break with the character it
// starts at, and blocks gives the paragraph each of the editor's own children is in. Zero-width
// spaces (pendingStyle's markers) aren't text
function readEditor(root, oldText) {
  const firstRun = oldText.paragraphs?.[0]?.runs?.[0] || { font: "Helvetica", size: 6 };
  const paragraphs = [], pieces = [], blocks = new Map();
  const tops = [...root.childNodes].filter((n) => n.nodeType === 1 || (n.nodeType === 3 && n.textContent));
  const groups = [];
  let loose = [];
  for (const n of tops) {
    if (n.nodeType === 1 && ["DIV", "P"].includes(n.tagName)) {
      if (loose.length) { groups.push({ block: null, nodes: loose }); loose = []; }
      groups.push({ block: n, nodes: [...n.childNodes] });
    } else loose.push(n);
  }
  if (loose.length) groups.push({ block: null, nodes: loose });
  groups.forEach(({ block, nodes }, pi) => {
    for (const n of block ? [block] : nodes) blocks.set(n, pi);
    const oldP = oldText.paragraphs?.[pi] || oldText.paragraphs?.[oldText.paragraphs.length - 1] || {};
    const runs = [], here = [];
    let at = 0;
    const walk = (node, style) => {
      if (node.nodeType === 3) {
        const t = node.textContent.replace(/​/g, "").replace(/ /g, " ");
        here.push({ node, at, len: t.length });
        if (t) { runs.push({ ...style, t }); at += t.length; }
        return;
      }
      if (node.nodeType !== 1) return;
      if (node.tagName === "BR") {
        if (node.nextSibling || node.previousSibling) {
          here.push({ node, at, len: 1, br: true });
          runs.push({ ...style, t: "\n" });
          at += 1;
        }
        return;
      }
      const st = nodeStyle(node, style);
      for (const c of node.childNodes) walk(c, st);
    };
    const base = { ...firstRun };
    delete base.t;
    delete base.baseline;   // raised or lowered only inside <sup> or <sub>
    for (const n of nodes) walk(n, base);
    // Merge neighbours with identical settings
    const merged = [];
    for (const r of runs) {
      const last = merged[merged.length - 1];
      const same = last && JSON.stringify({ ...last, t: 0 }) === JSON.stringify({ ...r, t: 0 });
      if (same) last.t += r.t; else merged.push({ ...r });
    }
    // A line's own settings (fillEditor), which a new line made with Enter copies; else the old
    // paragraph's in its place
    const own = block?.dataset.para ? JSON.parse(block.dataset.para) : oldP;
    const align = block ? { left: "l", center: "ctr", right: "r" }[block.style.textAlign] : null;
    paragraphs.push({ ...own, align: align || own.align || "l", runs: merged.length ? merged : [{ ...base, t: "" }] });
    pieces.push(here);
  });
  if (!paragraphs.length) {
    paragraphs.push({ align: "l", runs: [{ ...firstRun, t: "" }] });
    pieces.push([]);
  }
  return { paragraphs, pieces, blocks };
}
// The look an element gives the text inside it, on top of what it's inside
function nodeStyle(node, style) {
  const st = { ...style };
  if (node.dataset?.run) Object.assign(st, JSON.parse(node.dataset.run));
  const tag = node.tagName;
  if (tag === "B" || tag === "STRONG") st.bold = true;
  if (tag === "I" || tag === "EM") st.italic = true;
  if (tag === "U") st.underline = true;
  if (tag === "SUP") st.baseline = SUPERSCRIPT;
  if (tag === "SUB") st.baseline = SUBSCRIPT;
  const css = node.style || {};
  if (css.verticalAlign === "super") st.baseline = SUPERSCRIPT;
  if (css.verticalAlign === "sub") st.baseline = SUBSCRIPT;
  if (css.fontWeight) st.bold = css.fontWeight === "bold" || Number(css.fontWeight) >= 600;
  if (css.fontStyle) st.italic = css.fontStyle === "italic";
  if (css.textDecorationLine || css.textDecoration) st.underline = (css.textDecorationLine || css.textDecoration).includes("underline");
  return st;
}
// A point in the editor (a node and an offset in it) as a position [paragraph, character]
function toPosition({ pieces, blocks }, root, node, offset) {
  let top = node === root ? root.childNodes[Math.min(offset, root.childNodes.length - 1)] : node;
  while (top && top.parentNode !== root) top = top.parentNode;
  const p = blocks.get(top) ?? pieces.length - 1, here = pieces[p] || [];
  if (node.nodeType === 3) {
    const piece = here.find((x) => x.node === node);
    if (piece) return [p, piece.at + node.textContent.slice(0, offset).replace(/​/g, "").length];
  }
  // Between nodes: where the first piece of text at or after it starts, else the paragraph's end
  const point = document.createRange();
  point.setStart(node, offset);
  for (const x of here) if (point.comparePoint(x.node, 0) >= 0) return [p, x.at];
  const last = here[here.length - 1];
  return [p, last ? last.at + last.len : 0];
}
// A position [paragraph, character] as a point in the editor: in the text it falls in (at the end
// of the text before it, where two meet), before a break, or at the end of an empty line
function toPoint({ pieces, blocks }, [p, c]) {
  const here = pieces[p] || [];
  for (const x of here) {
    if (x.br) {
      if (c <= x.at) return [x.node.parentNode, [...x.node.parentNode.childNodes].indexOf(x.node)];
    } else if (c <= x.at + x.len && x.len) {
      const raw = x.node.textContent;
      let i = 0;
      for (let seen = 0; i < raw.length && seen < c - x.at; i++) if (raw[i] !== "​") seen++;
      return [x.node, i];
    }
  }
  const last = here[here.length - 1];
  if (last && !last.br) return [last.node, last.node.textContent.length];
  if (last) return [last.node.parentNode, [...last.node.parentNode.childNodes].indexOf(last.node) + 1];
  const block = [...blocks].find(([, i]) => i === p)?.[0];
  return block ? [block, 0] : [blocks.keys().next().value || document.body, 0];
}

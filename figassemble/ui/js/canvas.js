// The page canvas: rendering, selection, direct manipulation, drawing tools, cropping, in-place
// text editing, the grid, guides and snapping. Page coordinates are points; 100% zoom is true size.

import { assetUrl, rpc } from "./api.js";
import { store } from "./store.js";
import {
  PX_PER_PT, announce, apply, clamp, describeItem, frameMatrix, h, hitItem, invert, itemBBox,
  itemCorners, itemsBBox, lengthText, lineMidpoints, lineSamples, mul, nearestStretch, rotate, s, shapeCatalog,
  svgMatrix, translate, uid,
} from "./util.js";

const HANDLE = 8;             // handle size, CSS px
const SNAP_PX = 6;            // snapping distance, CSS px
const GUIDE_HIT = 4;          // how near (CSS px) the pointer must be to grab a guide
const GRID_MIN_PX = 6;        // grid lines closer than this on screen aren't drawn, or snapped to
const ROT_OFFSET = 24;        // rotation handle distance above the frame, CSS px
const SVG_PREVIEW_LIMIT = 8e6; // bigger SVGs preview as rendered PDFs for speed
const DEFAULT_SIZE = (72 / 2.54) * 2;   // a click (or Enter) with a drawing tool places a 2 cm object
// The drawing tools that make preset shapes, and which preset each draws
const TOOL_GEOMS = { rect: "rect", roundrect: "roundRect", ellipse: "ellipse", triangle: "triangle", arc: "arc",
  bracket: "rightBracket" };

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
    this.svg.append(this.view, this.overlay);
    stage.append(this.svg);
    this.setRulers(this.defaults?.show_rulers !== false);
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
    this.editor.addEventListener("keydown", (e) => this.editorKey(e));
    store.on((what, detail) => {
      if (what === "doc") this.render(detail);
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
    this.view.setAttribute("transform", `translate(${this.panX} ${this.panY}) scale(${this.k})`);
    this.drawGrid();
    this.drawOverlay();
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
    this.flushResolve(detail.live);
    this.drawGrid();
    this.drawGuides();
    this.drawOverlay();
    if (this.cropping) this.drawGhost();
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
      asset.variants, this.previewBucket(it)]);
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
    e.g.replaceChildren(inner);
    e.g.setAttribute("transform", svgMatrix(m));
    e.g.setAttribute("opacity", it.opacity ?? 1);
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
    let origin = [0, 0];
    if (c.frame) { origin = [c.frame[0], c.frame[1]]; c.frame = [0, 0, c.frame[2], c.frame[3]]; }
    if (c.points) { origin = c.points[0].slice(); c.points = c.points.map((p) => [p[0] - origin[0], p[1] - origin[1]]); }
    delete c.name; delete c.alt; delete c.locked;
    return [JSON.stringify(c), origin];
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
  flushResolve(live) {
    if (!this.pending.size) return;
    clearTimeout(this._resolveTimer);
    this._resolveTimer = setTimeout(() => this.resolveNow(), live ? 30 : 0);
  },
  async resolveNow() {
    const items = [...this.pending.values()];
    this.pending.clear();
    if (!items.length) return;
    const assets = {};
    for (const [id, a] of Object.entries(store.doc.assets)) assets[id] = { size_pt: a.size_pt, page_sizes: a.page_sizes };
    let results;
    try {
      results = await rpc("resolve", assets, items);
    } catch (err) { console.error(err); return; }
    const autofit = [];
    results.forEach((r, i) => {
      const e = this.els.get(r.id);
      if (!e) return;
      const it = items[i];
      const [gk, origin] = this.geomKey(it);
      e.g.innerHTML = r.svg;
      e.g.removeAttribute("transform");
      e.geomKey = gk;
      e.origin = origin;
      e.bbox = r.bbox;
      e.handles = r.handles || null;
      if (r.autofit_frame) autofit.push([r.id, r.autofit_frame]);
    });
    if (autofit.length) {
      store.silent((doc) => {
        for (const [id, f] of autofit) {
          const it = findDeep(doc.pages[store.pageIndex].items, id);
          if (it) it.frame = f;
        }
      });
      this.render({});
    }
    this.drawOverlay();
  },

  // Overlay (screen coordinates) ------------------------------------------------------

  drawOverlay() {
    if (!this.overlay || !store.doc) return;
    const o = this.overlay;
    o.replaceChildren();
    const sel = store.selected();
    this.drawSnapGuides(o);
    if (this.op?.type === "guide") this.drawGuideLabel(o);
    if (this.op?.type === "marquee") {
      const [ax, ay] = this.op.start, [bx, by] = this.op.cur;
      o.append(s("rect", { class: "marquee", x: Math.min(ax, bx), y: Math.min(ay, by),
        width: Math.abs(bx - ax), height: Math.abs(by - ay) }));
    }
    if (this.editing) return;
    if (sel.length === 1 && !this.cropping) this.drawHandles(sel[0]);
    else if (sel.length > 1) {
      for (const it of sel) o.append(this.outline(itemCorners(it), "sel-outline thin"));
      const b = itemsBBox(sel);
      if (b) o.append(this.outline([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], "sel-outline"));
    }
    if (this.cropping) this.drawCropHandles();
  },
  outline(pts, cls) {
    return s("polygon", { class: cls, points: pts.map(([x, y]) => this.toScreen(x, y).join(",")).join(" ") });
  },
  handlesFor(it) {
    if (it.locked) return [];
    if (it.type === "line") {
      // Ends and middle points can be dragged; the hollow handle halfway along each stretch
      // adds a point there (dragging one on a straight arrow bends it into a curve)
      const n = it.points.length;
      const pts = it.points.map((p, i) => ({ kind: i === 0 || i === n - 1 ? "end" : "point", index: i,
        at: this.toScreen(p[0], p[1]) }));
      const mids = lineMidpoints(it).map((m) => ({ kind: "mid", index: m.index, at: this.toScreen(m.at[0], m.at[1]) }));
      return [...pts, ...mids];
    }
    if (it.type === "group") return [];
    const m = frameMatrix(it.frame, it.rot || 0, it.flip_h, it.flip_v);
    const [, , w, h] = it.frame;
    const pts = { nw: [0, 0], n: [w / 2, 0], ne: [w, 0], e: [w, h / 2], se: [w, h], s: [w / 2, h], sw: [0, h], w: [0, h / 2] };
    // The shape's own adjust handles (PowerPoint's yellow ones) come first, so they win where
    // they sit on top of a resize handle
    const adjust = it.type === "shape" ? (this.els.get(it.id)?.handles || []).map(([x, y], index) => ({
      kind: "adjust", index, at: this.toScreen(...apply(m, x, y)) })) : [];
    const out = [...adjust, ...Object.entries(pts).map(([dir, [x, y]]) => {
      const [px, py] = apply(m, x, y);
      return { kind: "resize", dir, at: this.toScreen(px, py) };
    })];
    // Rotation handle: above the top edge along the frame's own "up"
    const r = rotate(it.rot || 0);
    const [ux, uy] = apply(r, 0, -1);
    const [tx, ty] = this.toScreen(...apply(m, w / 2, 0));
    out.push({ kind: "rotate", at: [tx + ux * ROT_OFFSET * (it.flip_v ? -1 : 1), ty + uy * ROT_OFFSET * (it.flip_v ? -1 : 1)] });
    return out;
  },
  drawHandles(it) {
    const o = this.overlay;
    if (it.type === "line") {
      o.append(s("polyline", { class: "sel-outline line",
        points: lineSamples(it).map(([x, y]) => this.toScreen(x, y).join(",")).join(" ") }));
    } else {
      o.append(this.outline(itemCorners(it), "sel-outline"));
    }
    for (const hd of this.handlesFor(it)) {
      if (hd.kind === "rotate") {
        o.append(s("circle", { class: "handle rot", cx: hd.at[0], cy: hd.at[1], r: HANDLE / 2 + 1 }));
      } else if (hd.kind === "point") {
        o.append(s("circle", { class: "handle point", cx: hd.at[0], cy: hd.at[1], r: HANDLE / 2 + 1 }));
      } else if (hd.kind === "mid") {
        o.append(s("circle", { class: "handle mid", cx: hd.at[0], cy: hd.at[1], r: HANDLE / 2 - 0.5 }));
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
    if (sel.length !== 1) return null;
    for (const hd of this.handlesFor(sel[0])) {
      if (Math.abs(pt[0] - hd.at[0]) <= HANDLE && Math.abs(pt[1] - hd.at[1]) <= HANDLE) return hd;
    }
    return null;
  },
  itemAt(p) {
    const tol = 4 / this.k;
    const items = store.items();
    for (let i = items.length - 1; i >= 0; i--) if (!items[i].locked && hitItem(items[i], p, tol)) return items[i];
    return null;
  },

  // Pointer interaction ---------------------------------------------------------------

  pointerDown(e) {
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
    if (this.tool !== "select") return this.startDraw(p, e);
    const hd = this.handleAt(pt);
    if (hd) return this.startHandle(hd, p, e);
    const hit = this.itemAt(p);
    if (this.cropping) {
      const it = store.item(this.cropping);
      if (it && hit && hit.id === it.id) return this.startCropMove(it, p);
      this.cropping = null;
      this.ghostLayer.replaceChildren();
    }
    // Objects come first; a guide can be dragged where nothing covers it, or by its mark on a ruler
    const guide = hit ? null : this.guideAt(pt);
    if (guide) return this.startGuide(guide.axis, guide.index);
    if (hit) {
      let sel = store.selection;
      if (e.shiftKey) sel = sel.includes(hit.id) ? sel.filter((i) => i !== hit.id) : [...sel, hit.id];
      else if (!sel.includes(hit.id)) sel = [hit.id];
      store.select(sel);
      if (!e.shiftKey || sel.includes(hit.id)) this.startMove(p, e);
      announce(describeItem(hit, store.doc));
    } else {
      if (!e.shiftKey) store.select([]);
      this.op = { type: "marquee", start: pt, cur: pt, add: e.shiftKey ? [...store.selection] : [] };
    }
  },
  pointerMove(e) {
    const pt = this.eventPoint(e);
    const p = this.toPage(...pt);
    document.dispatchEvent(new CustomEvent("fa-cursor", { detail: p }));
    const op = this.op;
    if (!op) return this.hover(pt, p);
    if (op.type === "pan") {
      this.panX = op.pan[0] + pt[0] - op.start[0];
      this.panY = op.pan[1] + pt[1] - op.start[1];
      return this.applyView();
    }
    if (op.type === "marquee") { op.cur = pt; return this.drawOverlay(); }
    if (op.type === "move") return this.moveTo(p, e);
    if (op.type === "resize") return this.resizeTo(p, e);
    if (op.type === "rotate") return this.rotateTo(p, e);
    if (op.type === "end") return this.endTo(p, e);
    if (op.type === "adjust") return this.adjustTo(p);
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
    if (op.type === "guide") return this.finishGuide(op, cancelled);
    if (op.type === "marquee") {
      const [ax, ay] = this.toPage(...op.start), [bx, by] = this.toPage(...op.cur);
      const box = [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)];
      if (box[2] - box[0] > 1e-6 || box[3] - box[1] > 1e-6) {
        const inside = store.items().filter((it) => {
          if (it.locked || it.hidden) return false;
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
    if (cancelled) { store.cancelLive(); return; }
    if (op.type === "draw") return this.finishDraw(op);
    if (op.moved) store.endLive(op.label);
    else store.cancelLive();
    if (op.moved && store.selection.length === 1) announce(describeItem(store.selected()[0], store.doc));
    this.drawOverlay();
  },
  hover(pt, p) {
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
    const pt = this.eventPoint(e);
    const p = this.toPage(...pt);
    const sel = store.selected();
    if (sel.length === 1 && sel[0].type === "line" && !sel[0].locked) {
      // On a selected line: double-click a middle point to remove it, the line to add one
      const hd = this.handleAt(pt);
      if (hd?.kind === "point") return this.removePoint(sel[0].id, hd.index);
      if (!hd && hitItem(sel[0], p, 4 / this.k)) return this.insertPoint(sel[0].id, p);
    }
    const hit = this.itemAt(p);
    if (!hit) return;
    if (hit.type === "picture") this.startCrop(hit.id);
    else if (hit.type === "shape") this.startEdit(hit.id);
  },

  // Moving -------------------------------------------------------------------------

  startMove(p, e) {
    const sel = store.selected().filter((it) => !it.locked);
    if (!sel.length) return;
    store.beginLive();
    if (e.altKey) {
      // Option/Alt-drag duplicates, like PowerPoint
      const copies = sel.map((it) => reid(JSON.parse(JSON.stringify(it))));
      store.silent((doc) => doc.pages[store.pageIndex].items.push(...copies));
      store.selection = copies.map((c) => c.id);
    }
    const items = store.selected();
    this.op = { type: "move", start: p, orig: items.map((it) => JSON.parse(JSON.stringify(it))), moved: false,
      label: e.altKey ? "Duplicate" : "Move", bbox: itemsBBox(items), targets: this.snapTargets(items.map((i) => i.id)) };
  },
  moveTo(p, e) {
    const op = this.op;
    let dx = p[0] - op.start[0], dy = p[1] - op.start[1];
    if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
    if (!op.moved && Math.hypot(dx, dy) * this.k < 2) return;
    op.moved = true;
    [dx, dy] = this.snapMove(op.bbox, dx, dy, op.targets, e);
    const ids = op.orig.map((o) => o.id);
    store.selected().forEach((it) => {
      const o = op.orig[ids.indexOf(it.id)];
      shiftItem(it, o, dx, dy);
    });
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
    for (const it of store.items()) {
      if (excludeIds.includes(it.id) || it.hidden) continue;
      const b = itemBBox(it);
      boxes.push(b);
      for (const v of [b[0], (b[0] + b[2]) / 2, b[2]]) xs.push({ v, span: [b[1], b[3]] });
      for (const v of [b[1], (b[1] + b[3]) / 2, b[3]]) ys.push({ v, span: [b[0], b[2]] });
    }
    return { xs, ys, boxes, grid: d.show_grid ? this.gridSteps().snap : null, size: [page.width, page.height] };
  },
  snapEnabled(e) { return (this.defaults?.snap ?? true) && !(e.metaKey || e.ctrlKey); },
  // Moving: the box's edges and centre snap to lines, or the box to equal gaps beside it
  snapMove(b, dx, dy, targets, e) {
    this.snapGuides = [];
    if (!this.snapEnabled(e) || !b) return [dx, dy];
    const tol = SNAP_PX / this.k;
    const box = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy];
    const shifts = [0, 1].map((i) => {
      const line = nearestSnap(edges(box, i), lines(targets, i), null, 0, tol);
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
      this.snapGuides.push(...snapLines(i, edges(fin, i), targets, fin[1 - i], fin[3 - i]));
      if (gap) this.snapGuides.push(...gapMarks(i, gap.pairs, fin));
    });
    return [dx, dy];
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
    for (const axis of ["x", "y"]) {
      g[axis].forEach((v, i) => {
        const active = g.active?.[0] === axis && g.active[1] === i;
        const cls = `guide${active ? " active" : ""}${active && g.removing ? " removing" : ""}`;
        this.guidesLayer.append(s("line", { class: cls, ...(axis === "x" ? { x1: v, x2: v, y1: -1e5, y2: 1e5 }
          : { x1: -1e5, x2: 1e5, y1: v, y2: v }) }));
      });
    }
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
    if (hd.kind === "resize") this.op = { type: "resize", dir: hd.dir, orig, moved: false, label: "Resize",
      targets: this.snapTargets([it.id]) };
    else if (hd.kind === "rotate") this.op = { type: "rotate", orig, moved: false, label: "Rotate" };
    else if (hd.kind === "adjust") this.op = { type: "adjust", index: hd.index, orig, moved: false, label: "Adjust shape" };
    else if (hd.kind === "end" || hd.kind === "point") this.op = { type: "end", index: hd.index, orig, moved: false,
      label: hd.kind === "end" ? "Move end" : "Move point", targets: this.snapTargets([it.id]) };
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
    const [, , w, h] = o.frame;
    let [x0, y0, x1, y1] = [0, 0, w, h];
    const dir = op.dir;
    if (dir.includes("w")) x0 = local[0];
    if (dir.includes("e")) x1 = local[0];
    if (dir.includes("n")) y0 = local[1];
    if (dir.includes("s")) y1 = local[1];
    const keepAspect = (o.type === "picture") !== e.shiftKey && dir.length === 2;
    if (keepAspect && w > 0 && h > 0) {
      const sx = (x1 - x0) / w, sy = (y1 - y0) / h;
      const sc = Math.max(Math.abs(sx), Math.abs(sy));
      const nw = w * sc, nh = h * sc;
      if (dir.includes("w")) x0 = x1 - nw; else x1 = x0 + nw;
      if (dir.includes("n")) y0 = y1 - nh; else y1 = y0 + nh;
    }
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
    let q = this.snapPoint(p, op.targets, e);
    if (e.shiftKey) {
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
        const adj = await rpc("drag_handle", { geom: it.geom, frame: it.frame, adj: it.adj }, op.index, target);
        if (op.cancelled) break;
        it.adj = adj;
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

  // Drawing tools ----------------------------------------------------------------------

  setTool(tool, geom = null) {
    if (this.editing) this.commitEdit();
    if (tool === "shape" && geom) this.shapeGeom = geom;
    this.tool = tool;
    this.stage.style.cursor = tool === "select" ? "default" : "crosshair";
    if (this.onToolChange) this.onToolChange(tool);
  },
  startDraw(p, e) {
    const targets = this.snapTargets([]);
    const start = this.snapPoint(p, targets, e);
    this.op = { type: "draw", tool: this.tool, start, cur: start, targets, moved: false };
  },
  drawTo(p, e) {
    const op = this.op;
    let q = this.snapPoint(p, op.targets, e);
    if (e.shiftKey) {
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
    this.overlay.replaceChildren();
    const [ax, ay] = this.toScreen(...op.start), [bx, by] = this.toScreen(...q);
    if (["line", "arrow"].includes(op.tool)) this.overlay.append(s("line", { class: "draw-preview", x1: ax, y1: ay, x2: bx, y2: by }));
    else {
      const box = [Math.min(ax, bx), Math.min(ay, by), Math.abs(bx - ax), Math.abs(by - ay)];
      this.overlay.append(s("rect", { class: "draw-preview", x: box[0], y: box[1], width: box[2], height: box[3] }));
      // The shape's outline (its menu icon, stretched over the box) shows what is being drawn
      const shape = shapeCatalog.shapes[this.toolGeom(op.tool)];
      if (shape?.icon && box[2] > 2 && box[3] > 2) {
        const [ix, iy, iw, ih] = shape.box;
        this.overlay.append(s("path", { class: "draw-preview shape", d: shape.icon,
          transform: `translate(${box[0]} ${box[1]}) scale(${box[2] / iw} ${box[3] / ih}) translate(${-ix} ${-iy})` }));
      }
    }
    this.drawSnapGuides(this.overlay);
  },
  toolGeom(tool) { return tool === "shape" ? this.shapeGeom : TOOL_GEOMS[tool]; },
  // Enter with a drawing tool: one object in the middle of the view, on the page
  placeDefault() {
    const r = this.stage.getBoundingClientRect(), page = store.page();
    const [x, y] = this.toPage(r.width / 2, r.height / 2);
    const c = [clamp(x, 0, page.width), clamp(y, 0, page.height)];
    this.finishDraw({ type: "draw", tool: this.tool, start: c, cur: c, moved: false, centred: true });
  },
  finishDraw(op) {
    const d = this.defaults || {};
    const stroke = { color: "#000000", width: d.stroke_width || 1, dash: "solid", cap: "round", join: "round", opacity: 1 };
    let [ax, ay] = op.start, [bx, by] = op.cur;
    if (!op.moved && !["text", "label"].includes(op.tool)) {
      // A click (or Enter) without dragging: a 2 cm object from the click, or centred on the view
      const half = op.centred ? DEFAULT_SIZE / 2 : 0;
      const line = ["line", "arrow"].includes(op.tool);
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
      store.update(lab ? "Add panel label" : "Add text", (doc) => doc.pages[store.pageIndex].items.push(item), { select: [item.id] });
      this.setTool("select");
      if (!lab) setTimeout(() => this.startEdit(item.id, true), 30);
      return;
    }
    if (tool === "line" || tool === "arrow") {
      item = { id: uid("it"), type: "line", points: [[ax, ay], [bx, by]], stroke,
        arrow_start: null, arrow_end: tool === "arrow" ? { type: "triangle", w: "med", len: "med" } : null };
    } else {
      const geom = this.toolGeom(tool);
      if (!geom) { this.drawOverlay(); return; }
      item = { id: uid("it"), type: "shape", geom, frame, rot: 0, flip_h: false, flip_v: false, stroke,
        fill: null, arrow_start: null, arrow_end: null };
    }
    store.update("Draw", (doc) => doc.pages[store.pageIndex].items.push(item), { select: [item.id] });
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
    if (!it || it.type !== "shape") return;
    if (!it.text) it.text = { paragraphs: [{ align: "ctr", runs: [{ t: "", font: "Helvetica", size: 6 }] }],
      insets: [7.2, 3.6, 7.2, 3.6], wrap: true, anchor: "ctr", autofit: "none" };
    this.editing = { id, isNew, before: JSON.stringify(it.text) };
    const e = this.els.get(id);
    if (e) e.g.style.visibility = "hidden";
    const ed = this.editor;
    ed.replaceChildren(...it.text.paragraphs.map((p) => {
      const div = h("div", { style: { textAlign: { l: "left", ctr: "center", r: "right" }[p.align || "l"] } });
      const runs = (p.runs || []).filter((r) => r.t !== undefined);
      if (!runs.length || runs.every((r) => !r.t)) div.append(h("br"));
      for (const r of runs) {
        const parts = r.t.split("\n");
        parts.forEach((part, i) => {
          if (i) div.append(h("br"));
          if (part) div.append(h("span", { "data-run": JSON.stringify({ ...r, t: undefined }), style: runCss(r) }, part));
        });
      }
      return div;
    }));
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
    if (mod && ["b", "i", "u"].includes(e.key.toLowerCase())) {
      e.preventDefault();
      document.execCommand({ b: "bold", i: "italic", u: "underline" }[e.key.toLowerCase()]);
    }
    if (e.key === "Enter" && e.shiftKey) { e.preventDefault(); document.execCommand("insertLineBreak"); }
    e.stopPropagation();
  },
  commitEdit() {
    const ed = this.editing;
    if (!ed) return;
    this.editing = null;
    const it = store.item(ed.id);
    this.editor.hidden = true;
    const e = this.els.get(ed.id);
    if (e) e.g.style.visibility = "";
    if (!it) return;
    const paragraphs = parseEditor(this.editor, it.text);
    const empty = paragraphs.every((p) => p.runs.every((r) => !r.t.trim()));
    if (empty && it.textbox) {
      store.update(ed.isNew ? "Add text" : "Delete text", (doc) => {
        const items = doc.pages[store.pageIndex].items;
        items.splice(items.findIndex((i) => i.id === ed.id), 1);
      }, { select: [] });
      return;
    }
    const after = { ...it.text, paragraphs };
    if (JSON.stringify(after) !== ed.before) {
      store.update("Edit text", (doc) => { findDeep(doc.pages[store.pageIndex].items, ed.id).text = after; });
    } else this.render({});
    this.stage.focus({ preventScroll: true });
    this.drawOverlay();
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
    it.items.forEach((c, i) => shiftItem(c, orig.items[i], dx, dy));
  } else if (it.type === "line") {
    it.points = orig.points.map((p) => [p[0] + dx, p[1] + dy]);
  } else {
    it.frame = [orig.frame[0] + dx, orig.frame[1] + dy, orig.frame[2], orig.frame[3]];
  }
}

export function reid(it) {
  it.id = uid("it");
  if (it.type === "group") it.items.forEach(reid);
  return it;
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

// Read the edited text back into paragraphs of runs, keeping each run's other settings
function parseEditor(root, oldText) {
  const firstRun = oldText.paragraphs?.[0]?.runs?.[0] || { font: "Helvetica", size: 6 };
  const paragraphs = [];
  const blocks = [...root.childNodes].filter((n) => n.nodeType === 1 || (n.nodeType === 3 && n.textContent));
  const groups = [];
  let loose = [];
  for (const n of blocks) {
    if (n.nodeType === 1 && ["DIV", "P"].includes(n.tagName)) {
      if (loose.length) { groups.push(loose); loose = []; }
      groups.push([...n.childNodes]);
    } else loose.push(n);
  }
  if (loose.length) groups.push(loose);
  groups.forEach((nodes, pi) => {
    const oldP = oldText.paragraphs?.[pi] || oldText.paragraphs?.[oldText.paragraphs.length - 1] || {};
    const runs = [];
    const walk = (node, style) => {
      if (node.nodeType === 3) {
        if (node.textContent) runs.push({ ...style, t: node.textContent.replace(/ /g, " ") });
        return;
      }
      if (node.nodeType !== 1) return;
      if (node.tagName === "BR") {
        if (node.nextSibling || node.previousSibling) runs.push({ ...style, t: "\n" });
        return;
      }
      const st = { ...style };
      if (node.dataset?.run) Object.assign(st, JSON.parse(node.dataset.run));
      const tag = node.tagName;
      if (tag === "B" || tag === "STRONG") st.bold = true;
      if (tag === "I" || tag === "EM") st.italic = true;
      if (tag === "U") st.underline = true;
      const css = node.style || {};
      if (css.fontWeight) st.bold = css.fontWeight === "bold" || Number(css.fontWeight) >= 600;
      if (css.fontStyle) st.italic = css.fontStyle === "italic";
      if (css.textDecorationLine || css.textDecoration) st.underline = (css.textDecorationLine || css.textDecoration).includes("underline");
      for (const c of node.childNodes) walk(c, st);
    };
    const base = { ...firstRun };
    delete base.t;
    for (const n of nodes) walk(n, base);
    // Merge neighbours with identical settings
    const merged = [];
    for (const r of runs) {
      const last = merged[merged.length - 1];
      const same = last && JSON.stringify({ ...last, t: 0 }) === JSON.stringify({ ...r, t: 0 });
      if (same) last.t += r.t; else merged.push({ ...r });
    }
    const div = nodes[0]?.parentElement;
    const align = div && div !== root ? { left: "l", center: "ctr", right: "r" }[div.style.textAlign] : null;
    paragraphs.push({ ...oldP, align: align || oldP.align || "l", runs: merged.length ? merged : [{ ...base, t: "" }] });
  });
  return paragraphs.length ? paragraphs : [{ align: "l", runs: [{ ...firstRun, t: "" }] }];
}

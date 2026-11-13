// Rulers along the top and left of the page view, in the units positions are shown in, with 0 at
// the page's top-left corner like the X and Y fields. They shade the page and the selection and
// mark the pointer and the guides. Clicking a ruler puts a guide at that spot (the top ruler a
// vertical one), rounded to a fine step of its ticks, and pointing at a ruler shows where. Dragging
// out of a ruler makes a guide that follows the pointer; dragging a guide's mark along a ruler
// moves that guide (handy when objects cover it on the page), and right-clicking it gives its menu.

import { canvas } from "./canvas.js";
import { store } from "./store.js";
import { PT_PER, UNIT_LABEL, fmt, h, isMac, itemsBBox } from "./util.js";

const MARK_HIT = 5;      // how near (CSS px) to a guide's mark the pointer must be to grab it
const CLICK_SLOP = 4;    // a press that moves less than this (CSS px) before letting go is a click
const CLICK_PX = 2.5;    // clicks round to the finest step dividing the ruler's ticks that is this far apart (CSS px)

export const rulers = {
  wrap: null,
  cursor: null,          // the pointer on the page, marked on both rulers
  dragging: false,
  press: null,           // the press under way: where, on which ruler and mark, and whether it's become a drag
  onNeedGuides: null,    // set by main.js: shows hidden guides when a new one is dragged out
  onMenu: null,          // set by main.js: a guide's right-click menu, (axis, index, x, y)

  init(wrap) {
    this.wrap = wrap;
    this.top = h("canvas", { class: "ruler top", "aria-hidden": "true" });
    this.left = h("canvas", { class: "ruler left", "aria-hidden": "true" });
    this.corner = h("div", { class: "ruler-corner", "aria-hidden": "true" });
    wrap.append(this.top, this.left, this.corner);
    for (const [el, axis] of [[this.top, "x"], [this.left, "y"]]) {
      el.addEventListener("pointerdown", (e) => this.down(e, el, axis));
      el.addEventListener("pointermove", (e) => this.move(e, el, axis));
      el.addEventListener("pointerup", (e) => this.up(e, el, false));
      el.addEventListener("pointercancel", (e) => this.up(e, el, true));
      el.addEventListener("pointerleave", () => {
        if (this.dragging) return;
        this.cursor = null;
        canvas.setGuidePreview(null);
        this.schedule();
      });
      el.addEventListener("contextmenu", (e) => this.menu(e, axis));
      el.addEventListener("wheel", (e) => canvas.wheel(e), { passive: false });
    }
    new ResizeObserver(() => this.schedule()).observe(wrap);
    for (const name of ["fa-zoom", "fa-prefs", "fa-preview"]) document.addEventListener(name, () => this.schedule());
    document.addEventListener("fa-cursor", (e) => { this.cursor = e.detail; this.schedule(); });
    store.on(() => this.schedule());
    this.schedule();
  },
  schedule() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = null; this.draw(); });
  },
  stagePoint(e) {
    const r = canvas.stage.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  },

  // Dragging --------------------------------------------------------------------------

  // The guide whose mark is under the pointer: the top ruler (axis "x") marks vertical guides
  markAt(axis, pt) {
    if (!canvas.showsGuides()) return null;
    const i = axis === "x" ? 0 : 1;
    let best = null, bestD = MARK_HIT;
    (store.page().guides?.[axis] || []).forEach((v, index) => {
      const d = Math.abs(canvas.toScreen(v, v)[i] - pt[i]);
      if (d <= bestD) { best = index; bestD = d; }
    });
    return best;
  },
  // Where a click on the ruler along axis puts a guide, in points: at the pointer, rounded to the
  // finest step that divides the ruler's smallest ticks and is still CLICK_PX apart on screen (1 mm
  // at 100% in centimetres, the ticks there being 5 mm apart), so a click on a tick lands on it;
  // exactly there with ⌘ (Ctrl) held or snapping off
  clickStep() {
    const unit = canvas.defaults?.units || "cm", ppu = canvas.k * PT_PER[unit];
    const { minor } = rulerSteps(ppu, unit, parseFloat(getComputedStyle(document.documentElement).fontSize) * 0.66);
    const parts = unit === "in" ? [64, 32, 16, 8, 4, 2, 1] : [100, 50, 20, 10, 5, 2, 1];
    return (minor / (parts.find((n) => (minor / n) * ppu >= CLICK_PX) || 1)) * PT_PER[unit];
  },
  clickValue(axis, pt, e) {
    const v = canvas.toPage(...pt)[axis === "x" ? 0 : 1];
    if (!canvas.snapEnabled(e)) return v;
    const step = this.clickStep();
    return Math.round(v / step) * step;
  },
  down(e, el, axis) {
    if (e.button !== 0 || !store.doc || canvas.editing) return;
    if (isMac && e.ctrlKey && !e.metaKey) return;   // Control-click is a right-click: the menu opens from contextmenu
    e.preventDefault();
    try { el.setPointerCapture(e.pointerId); } catch { /* synthetic or already-released pointer */ }
    const mark = this.markAt(axis, this.stagePoint(e));
    this.press = { at: [e.clientX, e.clientY], axis, mark, drag: false };
    canvas.setGuidePreview(null);
    if (mark !== null) canvas.startGuide(axis, mark);
    else {
      if (!canvas.showsGuides()) this.onNeedGuides?.();   // (hidden, or Preview on)
      canvas.startGuide(axis === "x" ? "y" : "x", null);   // dragged out, a new guide runs along the ruler it came out of
    }
    this.dragging = true;
  },
  move(e, el, axis) {
    const pt = this.stagePoint(e);
    this.cursor = canvas.toPage(...pt);
    if (this.dragging) {
      // A press becomes a drag once it has moved a few pixels; until then letting go is a click
      const p = this.press;
      if (p && !p.drag && Math.hypot(e.clientX - p.at[0], e.clientY - p.at[1]) >= CLICK_SLOP) p.drag = true;
      if (canvas.op?.type === "guide" && p?.drag) canvas.guideTo(pt, e);
    } else {
      // Over a mark the guide moves along the ruler; elsewhere a click puts one at the spot shown,
      // and a drag brings a new one out across the ruler
      const onMark = this.markAt(axis, pt) !== null;
      el.style.cursor = (axis === "x") === onMark ? "col-resize" : "row-resize";
      canvas.setGuidePreview(onMark ? null : { axis, value: this.clickValue(axis, pt, e) });
    }
    this.schedule();
  },
  up(e, el, cancelled) {
    if (!this.dragging) return;
    this.dragging = false;
    try { el.releasePointerCapture(e.pointerId); } catch { /* not captured */ }
    const op = canvas.op, press = this.press;
    this.press = null;
    if (op?.type !== "guide") return;     // Escape cancelled it already
    canvas.op = null;
    if (press && !press.drag) {
      // A click: a guide where it was pressed, across the ruler (on a guide's mark, nothing)
      canvas.finishGuide(op, true);
      if (!cancelled && press.mark === null) {
        canvas.addGuide(press.axis, this.clickValue(press.axis, this.stagePoint({ clientX: press.at[0], clientY: press.at[1] }), e));
      }
    } else canvas.finishGuide(op, cancelled);
    this.schedule();
  },
  // Right-click (Control-click on a Mac) on a guide's mark: that guide's menu
  menu(e, axis) {
    e.preventDefault();
    const mark = store.doc && !canvas.editing ? this.markAt(axis, this.stagePoint(e)) : null;
    if (mark !== null) this.onMenu?.(axis, mark, e.clientX, e.clientY);
  },

  // Drawing ---------------------------------------------------------------------------

  draw() {
    if (!store.doc || !this.wrap?.classList.contains("rulers")) return;
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    const style = { bg: v("--ruler-bg"), page: v("--ruler-page"), tick: v("--ruler-tick"), text: v("--muted"),
      line: v("--line"), sel: v("--sel"), guide: v("--guide-line"), cursor: v("--text"), font: v("--font"),
      fontPx: parseFloat(css.fontSize) * 0.66 };
    const unit = canvas.defaults?.units || "cm";
    const ctx = { style, unit, steps: rulerSteps(canvas.k * PT_PER[unit], unit, style.fontPx), page: store.page(),
      sel: itemsBBox(store.selected()), guides: canvas.showsGuides() ? canvas.guideLines() : null };
    this.drawRuler(this.top, 0, ctx);
    this.drawRuler(this.left, 1, ctx);
    this.corner.textContent = UNIT_LABEL[unit];
  },
  // i = 0: the top ruler (x across), 1: the left ruler (y down)
  drawRuler(el, i, { style, unit, steps, page, sel, guides }) {
    const w = el.clientWidth, hgt = el.clientHeight;
    if (!w || !hgt) return;
    const dpr = window.devicePixelRatio || 1;
    if (el.width !== Math.round(w * dpr) || el.height !== Math.round(hgt * dpr)) {
      el.width = Math.round(w * dpr);
      el.height = Math.round(hgt * dpr);
    }
    const g = el.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const len = i ? hgt : w, thick = i ? w : hgt;
    // Positions along the ruler (a) and across it (c, from its outer edge)
    const fill = (a0, a1, c0, c1) => (i ? g.fillRect(c0, a0, c1 - c0, a1 - a0) : g.fillRect(a0, c0, a1 - a0, c1 - c0));
    const tick = (a, c0, c1) => { if (i) { g.moveTo(c0, a); g.lineTo(c1, a); } else { g.moveTo(a, c0); g.lineTo(a, c1); } };
    const origin = i ? canvas.panY : canvas.panX;
    const at = (pt) => origin + pt * canvas.k;
    g.fillStyle = style.bg;
    g.fillRect(0, 0, w, hgt);
    g.fillStyle = style.page;
    fill(at(0), at(i ? page.height : page.width), 0, thick);
    if (sel) {
      g.globalAlpha = 0.28;
      g.fillStyle = style.sel;
      fill(at(sel[i]), at(sel[i + 2]), 0, thick);
      g.globalAlpha = 1;
    }
    // Ticks: the full-length ones carry numbers, a middle one where the step halves evenly
    const ppu = canvas.k * PT_PER[unit];
    const first = Math.floor(-origin / ppu / steps.minor), last = Math.ceil((len - origin) / ppu / steps.minor);
    const labels = [];
    g.strokeStyle = style.tick;
    g.lineWidth = 1;
    g.beginPath();
    for (let n = first; n <= last; n++) {
      const a = Math.round(origin + n * steps.minor * ppu) + 0.5;
      const major = n % steps.per === 0;
      const half = !major && steps.per % 2 === 0 && n % (steps.per / 2) === 0;
      tick(a, major ? 0 : thick * (half ? 0.5 : 0.72), thick);
      if (major) labels.push([a, fmt(n * steps.minor, 4)]);
    }
    g.stroke();
    g.fillStyle = style.text;
    g.font = `${style.fontPx}px ${style.font}`;
    g.textBaseline = "top";
    for (const [a, text] of labels) {
      if (i) {
        // Turned to read upwards, starting just below its tick
        g.save();
        g.translate(2, a + 3);
        g.rotate(-Math.PI / 2);
        g.textAlign = "right";
        g.fillText(text, 0, 0);
        g.restore();
      } else {
        g.textAlign = "left";
        g.fillText(text, a + 3, 2);
      }
    }
    // Guides crossing this ruler: a mark at each, the one being dragged faded when it would go
    if (guides) {
      const axis = i ? "y" : "x", s = 4.5;
      g.fillStyle = style.guide;
      guides[axis].forEach((val, n) => {
        const a = at(val);
        g.globalAlpha = guides.removing && guides.active?.[0] === axis && guides.active[1] === n ? 0.35 : 1;
        g.beginPath();
        if (i) { g.moveTo(thick, a); g.lineTo(thick - s * 1.5, a - s); g.lineTo(thick - s * 1.5, a + s); }
        else { g.moveTo(a, thick); g.lineTo(a - s, thick - s * 1.5); g.lineTo(a + s, thick - s * 1.5); }
        g.closePath();
        g.fill();
      });
      g.globalAlpha = 1;
    }
    if (this.cursor) {
      g.strokeStyle = style.cursor;
      g.globalAlpha = 0.75;
      g.beginPath();
      tick(Math.round(at(this.cursor[i])) + 0.5, 0, thick);
      g.stroke();
      g.globalAlpha = 1;
    }
    // The edge against the page view
    g.fillStyle = style.line;
    if (i) g.fillRect(thick - 1, 0, 1, len);
    else g.fillRect(0, thick - 1, len, 1);
  },
};

// The numbered step (1, 2 or 5 times a power of ten, or a power of two for inches) is the smallest
// that leaves room for its numbers; finer ticks divide it while they stay 5 px apart
function rulerSteps(ppu, unit, fontPx) {
  const room = fontPx * 4.2;
  const options = [];
  if (unit === "in") for (let e = -4; e <= 8; e++) options.push([2 ** e, [8, 4, 2]]);
  else for (let e = -2; e <= 6; e++) for (const m of [1, 2, 5]) options.push([m * 10 ** e, { 1: [10, 5, 2], 2: [4, 2], 5: [5] }[m]]);
  const [step, parts] = options.find(([st]) => st * ppu >= room) || options[options.length - 1];
  const per = parts.find((n) => (step / n) * ppu >= 5) || 1;
  return { per, minor: step / per };
}

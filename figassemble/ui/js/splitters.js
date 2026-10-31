// The side panels' inner edges: drag one to make its panel wider or narrower, or focus it and use
// the arrow keys; double-click puts the panel back to its usual width. Widths are remembered,
// in rem so they follow the interface text size, and the page area always keeps some room.

import { h } from "./util.js";

const SIDES = {
  left: { name: "Pages and Objects panel", usual: 15, min: 10, max: 30, cssVar: "--left-w" },
  right: { name: "properties panel", usual: 19, min: 15, max: 34, cssVar: "--right-w" },
};
const PAGE_ROOM = 320;   // CSS px the page area keeps, however wide the panels

export const splitters = {
  init(app) {
    this.app = app;
    this.ws = document.querySelector(".workspace");
    this.bars = {};
    this.widths = { ...(app.prefs.panel_widths || {}) };
    for (const [side, cfg] of Object.entries(SIDES)) {
      const bar = h("div", { class: `splitter ${side}`, role: "separator", "aria-orientation": "vertical", tabindex: 0,
        "aria-label": `Width of the ${cfg.name}`, "aria-valuemin": cfg.min, "aria-valuemax": cfg.max,
        title: "Drag to resize the panel; double-click to put it back" });
      bar.addEventListener("pointerdown", (e) => this.down(e, side));
      bar.addEventListener("pointermove", (e) => this.move(e, side));
      bar.addEventListener("pointerup", (e) => this.up(e, side));
      bar.addEventListener("pointercancel", (e) => this.up(e, side));
      bar.addEventListener("dblclick", () => this.set(side, cfg.usual, true));
      bar.addEventListener("keydown", (e) => this.key(e, side));
      this.ws.append(bar);
      this.bars[side] = bar;
    }
    window.addEventListener("resize", () => this.show());
    document.addEventListener("fa-prefs", () => this.show());   // the interface text size changes rem
    this.show();
  },
  rem() { return parseFloat(getComputedStyle(document.documentElement).fontSize) || 14; },
  wanted(side) { return this.widths[side] ?? SIDES[side].usual; },
  // The width a panel can have: its limits, and room left for the page beside the other panel
  fit(side, w) {
    const cfg = SIDES[side], other = side === "left" ? "right" : "left", rem = this.rem();
    const toolbox = document.getElementById("toolbox")?.getBoundingClientRect().width || 0;
    const room = (this.ws.getBoundingClientRect().width - toolbox - PAGE_ROOM) / rem - this.wanted(other);
    return Math.max(cfg.min, Math.min(cfg.max, room, w));
  },
  show() {
    for (const side of Object.keys(SIDES)) {
      const w = this.fit(side, this.wanted(side));
      this.ws.style.setProperty(SIDES[side].cssVar, `${w}rem`);
      this.bars[side].setAttribute("aria-valuenow", String(Math.round(w)));
      this.bars[side].setAttribute("aria-valuetext", `${Math.round(w * this.rem())} pixels wide`);
    }
  },
  set(side, w, remember) {
    this.widths[side] = Math.round(this.fit(side, w) * 100) / 100;
    if (this.widths[side] === SIDES[side].usual) delete this.widths[side];
    this.show();
    if (remember) this.app.rememberUi({ panel_widths: { ...this.widths } });
  },
  down(e, side) {
    if (e.button !== 0) return;
    e.preventDefault();
    this.drag = side;
    try { this.bars[side].setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
    this.bars[side].classList.add("dragging");
    document.body.classList.add("resizing-panel");
  },
  move(e, side) {
    if (this.drag !== side) return;
    const r = this.ws.getBoundingClientRect();
    this.set(side, (side === "left" ? e.clientX - r.left : r.right - e.clientX) / this.rem(), false);
  },
  up(e, side) {
    if (this.drag !== side) return;
    this.drag = null;
    this.bars[side].classList.remove("dragging");
    document.body.classList.remove("resizing-panel");
    this.app.rememberUi({ panel_widths: { ...this.widths } });
  },
  // Arrow keys move the edge 1 rem (Shift: 4); Home and End go to the narrowest and widest
  key(e, side) {
    const cfg = SIDES[side], step = e.shiftKey ? 4 : 1, outward = side === "left" ? "ArrowRight" : "ArrowLeft";
    let w = null;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") w = this.wanted(side) + (e.key === outward ? step : -step);
    else if (e.key === "Home") w = cfg.min;
    else if (e.key === "End") w = cfg.max;
    if (w === null) return;
    e.preventDefault();
    e.stopPropagation();
    this.set(side, w, true);
  },
};

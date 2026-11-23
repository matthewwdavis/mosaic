// Liquid Glass (View > Glass): the ribbon, tool bar, side panels and status bar show what's behind
// the window through the Mac's own glass (Python: _labapp/glass.py puts it behind the window's web
// view), the canvas stays solid, and menus and dialogs are frosted (css/glass.css). Off, Subtle,
// Standard or Clear; the system's Reduce Transparency and the High contrast theme turn it off, and
// Increase Contrast makes it nearly solid. Windows and Linux get the page's own frosted imitation.
// (The same as prose's editor/src/glass.js, with mosaic's settings and themes.)

import { rpc } from "./api.js";

export const GLASS_LEVELS = [["off", "Off"], ["subtle", "Subtle"], ["standard", "Standard"], ["clear", "Clear"]];
export const GLASS_DEFAULT = "standard";
export const glassLevel = (v) => (GLASS_LEVELS.some(([k]) => k === v) ? v : GLASS_DEFAULT);

// A computed CSS colour as [r, g, b (0-255), a (0-1)]: rgb()/rgba(), or color(srgb …), which is
// how WebKit gives a color-mix()
export function rgba(css) {
  const s = String(css || "").trim();
  let m = /^rgba?\(([^)]*)\)$/i.exec(s);
  if (m) {
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(parseFloat);
    return [Math.round(p[0]), Math.round(p[1]), Math.round(p[2]), p.length > 3 ? Math.round(p[3] * 1000) / 1000 : 1];
  }
  m = /^color\(srgb\s+([^)]*)\)$/i.exec(s);
  if (m) {
    const p = m[1].split(/[\s/]+/).filter(Boolean).map(parseFloat);
    return [Math.round(p[0] * 255), Math.round(p[1] * 255), Math.round(p[2] * 255), p.length > 3 ? Math.round(p[3] * 1000) / 1000 : 1];
  }
  return null;
}

// The <html> attributes glass.css reads
export function paint(root, effective, material, contrast) {
  root.dataset.glass = effective;
  root.dataset.glassMaterial = material;
  if (contrast) root.dataset.glassContrast = "more";
  else delete root.dataset.glassContrast;
}

// The theme showing now: the chosen one, or the day or night theme by the system's mode
export function themeNow(prefs, dark = false) {
  const t = prefs?.theme || "system";
  return t === "system" ? (dark ? prefs?.theme_night || "dark" : prefs?.theme_day || "light") : t;
}

export const glass = {
  app: null,
  system: { reduceTransparency: false, increaseContrast: false },
  material: null,   // (what the app said last: glass, vibrancy or css)
  state: null,
  seq: 0,

  level() {
    const p = this.app?.prefs || {};
    let dark = false;
    try { dark = matchMedia("(prefers-color-scheme: dark)").matches; } catch { /* an old web view */ }
    return themeNow(p, dark) === "contrast" ? "off" : glassLevel(p.glass);   // (High contrast: solid)
  },

  // The ribbon's colour at a level, for the Mac's title bar above it (worked out without showing
  // it: nothing is drawn between setting the attributes and putting them back)
  tint(effective, material) {
    const root = document.documentElement, bar = document.querySelector(".topbar");
    if (!bar || effective === "off") return null;
    const was = [root.dataset.glass, root.dataset.glassMaterial, root.dataset.glassContrast];
    paint(root, effective, material, this.system.increaseContrast);
    const colour = rgba(getComputedStyle(bar).backgroundColor);
    if (was[0] === undefined) { delete root.dataset.glass; delete root.dataset.glassMaterial; delete root.dataset.glassContrast; }
    else paint(root, was[0], was[1], was[2]);
    return colour;
  },

  // The window's glass at the chosen level (and the theme's colours now), then the page to match
  async apply(app = this.app) {
    this.app = app;
    const seq = ++this.seq, level = this.level();
    const guess = this.material || (app?.info?.platform === "darwin" ? "glass" : "css");
    const effective = this.system.reduceTransparency ? "off" : level;
    let st = null;
    try { st = await rpc("set_glass", effective, this.tint(effective, guess)); } catch { st = null; }
    if (seq !== this.seq) return this.state;   // (a later change has gone after it)
    if (!st) st = { level, effective, material: "css", ...this.system };   // (no app behind the page: its own imitation)
    // (the system's settings as the app read them, until it tells this window they've changed)
    if (!this.told) this.system = { reduceTransparency: !!st.reduceTransparency, increaseContrast: !!st.increaseContrast };
    st = { ...st, level, ...this.system, effective: this.system.reduceTransparency ? "off" : st.effective };
    this.material = st.material;
    paint(document.documentElement, st.effective, st.material, this.system.increaseContrast);
    this.state = st;
    return st;
  },

  // The system's Reduce Transparency or Increase Contrast switched (the app tells each window)
  systemChanged(settings) {
    this.told = true;
    this.system = { reduceTransparency: !!settings?.reduceTransparency, increaseContrast: !!settings?.increaseContrast };
    return this.apply();
  },
};

// Toolbar, pages and objects lists, status bar and dialogs.

import { rpc } from "./api.js";
import { canvas } from "./canvas.js";
import { alignToField, button, colourVisionField, gapField, numField, selectField } from "./inspector.js";
import { findItem, store } from "./store.js";
import { PALETTES, colourHolders } from "./swatches.js";
import { copiesOf } from "./symbols.js";
import { describeLook, differs as looksDiffer, styledObjects } from "./objectstyles.js";
import { describeFormat, differs, paragraphs } from "./textstyles.js";
import { contextMenu } from "./contextmenu.js";
import { listDrag } from "./listdrag.js";
import { updates } from "./updates.js";
import { intoPlace, locate, moveItems, moveToPage, slotPlaces, treeRows } from "./layers.js";
import { UNIT_LABEL, announce, fmt, h, isMac, itemLabel, keepFieldKeys, s, shapeName, toUnit } from "./util.js";

// 24 x 24 stroke icons
const ICONS = {
  select: "M5 3l13 9-6 1.5L9.5 20z", text: "M5 6V4h14v2M12 4v16M9 20h6",
  label: "M4 4h16v16H4zM9 15l3-7 3 7M10 13h4", line: "M5 19L19 5", arrow: "M5 19L18 6M10 6h8v8",
  rect: "M4 6h16v12H4z", roundrect: "M8 5h8a4 4 0 014 4v6a4 4 0 01-4 4H8a4 4 0 01-4-4V9a4 4 0 014-4z",
  ellipse: "M12 5c5 0 9 3.1 9 7s-4 7-9 7-9-3.1-9-7 4-7 9-7z", triangle: "M12 4l9 16H3z",
  arc: "M5 18A10 10 0 0119 8", bracket: "M8 4c3 0 4 1 4 3v10c0 2-1 3-4 3",
  picture: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9h.01", undo: "M9 7L4 12l5 5M4 12h11a5 5 0 010 10h-2",
  redo: "M15 7l5 5-5 5M20 12H9a5 5 0 000 10h2", new: "M6 3h8l4 4v14H6zM14 3v4h4M12 11v6M9 14h6",
  open: "M3 7h6l2 2h10v10H3z", save: "M5 4h11l3 3v13H5zM8 4v5h7V4M8 20v-6h8v6",
  export: "M12 3v12M7 8l5-5 5 5M5 15v5h14v-5", check: "M4 12l5 5L20 6",
  zoomin: "M10 4a6 6 0 110 12 6 6 0 010-12zM15 15l5 5M10 7v6M7 10h6",
  zoomout: "M10 4a6 6 0 110 12 6 6 0 010-12zM15 15l5 5M7 10h6", fit: "M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5",
  centre: "M8 8h8v8H8zM12 2.5v3.5M12 18v3.5M2.5 12H6M18 12h3.5",
  bucket: "M19 11L11 3L3 11a2 2 0 000 2.8l5.2 5.2a2 2 0 002.8 0zM6 3l4 4M3 13h15M21.5 19.5a1.5 1.5 0 01-3 0c0-1.2 1.5-2 1.5-3.5 0 1.5 1.5 2.3 1.5 3.5z",
  gear: "M12 9a3 3 0 110 6 3 3 0 010-6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
  help: "M12 3a9 9 0 110 18 9 9 0 010-18zM9.5 9.5a2.5 2.5 0 015 0c0 2-2.5 2-2.5 4M12 17h.01",
  plus: "M12 5v14M5 12h14", duplicate: "M8 8h11v11H8zM5 5h11v3M5 5v11h3", trash: "M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13",
  again: "M17 2l4 4-4 4M3 11V9a3 3 0 013-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 01-3 3H3",
  sameWidth: "M5 6h14M5 4v4M19 4v4M5 15h14M5 13v4M19 13v4", sameHeight: "M6 5v14M4 5h4M4 19h4M15 5v14M13 5h4M13 19h4",
  scalebar: "M4 16h16v3H4zM7 9h10", measure: "M3 17L17 3l4 4L7 21zM7 13l2 2M10 10l2 2M13 7l2 2",
  zoomInset: "M3 4h8v6H3zM13 9h8v11h-8zM11 4l2 5M11 10l2 10",
  sigBracket: "M4 20v-6h16v6M10 9l2-4 2 4M8 7h8", stackBrackets: "M7 20v-3h10v3M4 13v-3h16v3M9 6h6",
  unite: "M4 4h10v6h6v10H10v-6H4z", minusFront: "M4 4h10v6h-4v4H4zM12 12h8v8h-8z",
  intersect: "M4 4h10v10H4zM10 10h10v10H10zM10 10h4v4h-4zM11 12h2M12 11v2", exclude: "M4 4h10v6h-4v4H4zM14 10h6v10H10v-6h4z",
  clip: "M4 4h16v16H4zM12 7a5 5 0 110 10 5 5 0 010-10z", unclip: "M4 4h9M4 4v9M20 20h-9M20 20v-9M14 4h6v6M4 14v6h6",
  swatches: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  textStyles: "M5 5h14M12 5v14M8 19h8M4 12h3M17 12h3",
  objectStyles: "M4 4h9v9H4zM9 15l5-6 6 10H8z",
  fonts: "M4 19l5-14h1l5 14M6 14h7M15 19l3-8h.5l3 8M16 16.5h4",
  brush: "M20 3l-7 7M11 9l4 4M10.5 10.5l3 3-3 3a3 3 0 01-4.2 0l-.3-.3a3 3 0 010-4.2zM6.6 16.6C6 18.6 4.6 20 3 20.5c2 .6 4.4.2 5.8-1.4",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 110 6 3 3 0 010-6z",
  eyeoff: "M3 3l18 18M10.6 5.1A10 10 0 0112 5c6 0 10 7 10 7a17 17 0 01-3 3.8M6.1 6.1C3.6 7.8 2 12 2 12s4 7 10 7a9.6 9.6 0 004-.9",
  lock: "M6 11h12v9H6zM8 11V8a4 4 0 018 0v3", unlock: "M6 11h12v9H6zM8 11V8a4 4 0 017.5-2",
  group: "M3 3h7v7H3zM14 14h7v7h-7zM7 10v4h7", import: "M12 15V3M7 10l5 5 5-5M5 17v3h14v-3",
  shapes: "M7 3l4.5 8h-9zM17 3.5a3.5 3.5 0 110 7 3.5 3.5 0 010-7zM8.5 13.5h7v7h-7z",
  cut: "M6 4.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5zM6 14.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5zM8.2 8.2L20 19M8.2 15.8L20 5",
  copy: "M9 9h11v11H9zM5 15V4h11", paste: "M9 3h6v3H9zM7 5H5v16h14V5h-2",
  ungroup: "M3 3h7v7H3zM14 14h7v7h-7zM14 6h4M6 14v4",
  front: "M12 21V7M6 12l6-6 6 6M5 3h14", forward: "M12 19V6M7 11l5-5 5 5", backward: "M12 5v13M7 13l5 5 5-5",
  back: "M12 3v14M6 12l6 6 6-6M5 21h14",
  alignLeft: "M4 3v18M7 6h10v4H7zM7 14h6v4H7z", alignCenter: "M12 3v18M6 6h12v4H6zM8 14h8v4H8z",
  alignRight: "M20 3v18M7 6h10v4H7zM11 14h6v4h-6z", alignTop: "M3 4h18M6 7h4v10H6zM14 7h4v6h-4z",
  alignMiddle: "M3 12h18M6 6h4v12H6zM14 8h4v8h-4z", alignBottom: "M3 20h18M6 7h4v10H6zM14 11h4v6h-4z",
  spaceH: "M3 4v16M21 4v16M7.5 8h3v8h-3zM13.5 8h3v8h-3z", spaceV: "M4 3h16M4 21h16M8 7.5h8v3H8zM8 13.5h8v3H8z",
  distLeft: "M4 3v18M11 3v18M18 3v18M4 7h5v4H4zM11 13h4v4h-4zM18 9h3v4h-3z",
  distCenter: "M5 3v18M12 3v18M19 3v18M2.5 7h5v4h-5zM10 13h4v4h-4zM17.5 9h3v4h-3z",
  distRight: "M6 3v18M13 3v18M20 3v18M1 7h5v4H1zM9 13h4v4H9zM17 9h3v4h-3z",
  distTop: "M3 4h18M3 11h18M3 18h18M7 4h4v5H7zM13 11h4v4h-4zM9 18h4v3H9z",
  distMiddle: "M3 5h18M3 12h18M3 19h18M7 2.5h4v5H7zM13 10h4v4h-4zM9 17.5h4v3H9z",
  distBottom: "M3 6h18M3 13h18M3 20h18M7 1h4v5H7zM13 9h4v4h-4zM9 17h4v3H9z",
  actual: "M5 5h14v14H5zM9 9.5l2-1.5v8M14 9.5l2-1.5v8",
  cells: "M4 4h7v6H4zM13 4h7v9h-7zM4 12h7v8H4zM13 15h7v5h-7z",
  pen: "M4 20l2.5-7.5L15 4l5 5-8.5 8.5zM4 20l5-5M15 4l5 5M11.5 9.5a1.5 1.5 0 102.1 2.1 1.5 1.5 0 00-2.1-2.1z",
  equation: "M3 13h2l3 6 4-15h9M14 9l6 8M20 9l-6 8",
  report: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 15.5h7M9 19h4",
  symbol: "M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8-4.3-4.1 5.9-.9z",
  symbols: "M8 3l1.8 3.6 4 .6-2.9 2.8.7 4L8 12.1 4.4 14l.7-4L2.2 7.2l4-.6zM17 10l1.4 2.8 3.1.5-2.3 2.2.6 3.1-2.8-1.5-2.8 1.5.6-3.1-2.3-2.2 3.1-.5z",
  ruler: "M3 8h18v8H3zM7 8v3M11 8v4.5M15 8v3M19 8v4.5", grid: "M4 4h16v16H4zM9.33 4v16M14.67 4v16M4 9.33h16M4 14.67h16",
  guides: "M9 8v13M8 15h13M6.5 3h5L9 6zM3 12.5v5l3-2.5z",
  magnet: "M5 4h4.5v7.5a2.5 2.5 0 005 0V4H19v7.5a7 7 0 01-14 0zM5 8h4.5M14.5 8H19",
  closed: "M9 6l6 6-6 6", open: "M6 9l6 6 6-6",
};

// Which text objects (and pages) use each font; text in symbols counts, on no page of its own
function fontUses(doc) {
  const uses = new Map();
  const walk = (items, page) => {
    for (const it of items) {
      if (it.type === "group") walk(it.items, page);
      for (const p of it.text?.paragraphs || []) {
        for (const r of p.runs || []) {
          if (!r.font || !(r.t || "").length) continue;
          if (!uses.has(r.font)) uses.set(r.font, { objects: new Set(), pages: new Set() });
          uses.get(r.font).objects.add(it.id);
          if (page !== null) uses.get(r.font).pages.add(page);
        }
      }
    }
  };
  doc.pages.forEach((pg, i) => walk(pg.items, i));
  for (const sym of doc.symbols || []) walk(sym.items, null);
  return uses;
}

export function icon(name) {
  return pathIcon(ICONS[name] || "");
}
// An icon from path data in a 24 x 24 box (the Shapes menu's icons come from the engine)
function pathIcon(d) {
  const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svgEl.setAttribute("viewBox", "0 0 24 24");
  svgEl.setAttribute("aria-hidden", "true");
  svgEl.setAttribute("class", "icon");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", d);
  svgEl.append(p);
  return svgEl;
}

export function sizeText(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Roving focus for toolbars and lists: arrow keys move between items, Tab leaves
function roving(container, selector, vertical = false) {
  container.addEventListener("keydown", (e) => {
    const keys = vertical ? ["ArrowUp", "ArrowDown"] : ["ArrowLeft", "ArrowRight"];
    if (!keys.includes(e.key) && e.key !== "Home" && e.key !== "End") return;
    const items = [...container.querySelectorAll(selector)].filter((el) => !el.disabled && el.offsetParent !== null);
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    let j = i;
    if (e.key === keys[0]) j = Math.max(0, i - 1);
    else if (e.key === keys[1]) j = Math.min(items.length - 1, i + 1);
    else if (e.key === "Home") j = 0;
    else j = items.length - 1;
    items[i].tabIndex = -1;
    items[j].tabIndex = 0;
    items[j].focus();
  });
}

// The item in the next row up or down of a wrapped grid, nearest in x
function verticalNeighbour(items, i, down) {
  if (i < 0) return items[0];
  const r = items[i].getBoundingClientRect(), cx = r.left + r.width / 2;
  const rows = items.map((b, k) => ({ k, q: b.getBoundingClientRect() }))
    .filter(({ q }) => (down ? q.top > r.top + r.height / 2 : q.top < r.top - r.height / 2));
  if (!rows.length) return items[i];
  const top = down ? Math.min(...rows.map(({ q }) => q.top)) : Math.max(...rows.map(({ q }) => q.top));
  const row = rows.filter(({ q }) => Math.abs(q.top - top) < 2);
  row.sort((a, b) => Math.abs(a.q.left + a.q.width / 2 - cx) - Math.abs(b.q.left + b.q.width / 2 - cx));
  return items[row[0].k];
}

export const panels = {
  init(app) {
    this.app = app;
    this.buildRibbon();
    this.buildToolbox();
    this.buildPages();
    this.buildLayers();
    this.buildStatus();
    store.on((what, detail) => {
      if (what === "doc" && detail?.live) return;   // mid-drag: the lists don't change
      if (["doc", "page", "saved"].includes(what)) { this.renderPages(); this.renderLayers(); this.renderSaveState(); }
      if (what === "selection") this.renderLayers();
    });
    canvas.onToolChange = (tool) => this.renderTools(tool);
    document.addEventListener("fa-prefs", () => { this.renderToggles(); this.renderNudge(); });
    document.addEventListener("fa-zoom", (e) => {
      for (const z of document.querySelectorAll(".zoom-label")) z.textContent = `${fmt(e.detail * 100, 0)}%`;
      this.renderNudge();
    });
    document.addEventListener("fa-cursor", (e) => {
      const u = app.prefs.units || "cm";
      const d = u === "cm" || u === "in" ? 2 : 1;
      this.cursor.textContent = `x ${fmt(toUnit(e.detail[0], u), d)}, y ${fmt(toUnit(e.detail[1], u), d)} ${UNIT_LABEL[u]}`;
    });
  },

  // Toolbar ----------------------------------------------------------------------------

  toolButton(cmd, iconName, { tool = null, primary = false } = {}) {
    const c = this.app.commands[cmd];
    const shortcut = c.keys ? ` (${c.keys})` : "";
    const b = h("button", { type: "button", class: `tool${primary ? " primary" : ""}`, title: `${c.label}${shortcut}`,
      "aria-label": c.label, "aria-keyshortcuts": c.aria || undefined, "data-cmd": cmd, tabindex: -1 },
    icon(iconName), h("span", { class: "tool-label" }, c.short || c.label));
    if (tool) { b.dataset.tool = tool; b.setAttribute("aria-pressed", "false"); }
    b.addEventListener("click", () => this.app.run(cmd));
    return b;
  },
  // A button that switches a setting on and off and shows which (Rulers, Grid, Guides, Snap)
  toggleButton(cmd, iconName, pref, hint = "") {
    const b = this.toolButton(cmd, iconName);
    const c = this.app.commands[cmd];
    b.dataset.pref = pref;
    b.setAttribute("aria-label", c.short);
    b.title = `${c.label} (${c.keys})${hint}`;
    b.setAttribute("aria-pressed", this.app.prefs[pref] ? "true" : "false");
    return b;
  },
  renderToggles() {
    for (const b of document.querySelectorAll("[data-pref]")) {
      b.setAttribute(b.getAttribute("role") === "menuitemcheckbox" ? "aria-checked" : "aria-pressed",
        this.app.prefs[b.dataset.pref] ? "true" : "false");
    }
  },

  // Ribbon: tabs of labelled groups, like PowerPoint's; Snap, Check, Export, Settings and Help
  // stay in view on the right ------------------------------------------------------------------

  buildRibbon() {
    const root = document.getElementById("ribbon");
    const t = (cmd, ic) => this.toolButton(cmd, ic);
    const group = (label, ...items) => {
      const id = `rgroup-${label.toLowerCase().replace(/\W+/g, "-")}`;
      return h("div", { class: "rgroup", role: "group", "aria-labelledby": id },
        h("div", { class: "rgroup-items" }, ...items), h("div", { class: "rgroup-label", id }, label));
    };
    const tabs = [
      ["home", "Home", [
        group("File", t("new", "new"), t("open", "open"), t("save", "save")),
        group("Edit", t("undo", "undo"), t("redo", "redo")),
        group("Clipboard", t("cut", "cut"), t("copy", "copy"), t("paste", "paste"), this.painterButton()),
        group("Objects", t("duplicate", "duplicate"), t("transformAgain", "again"), t("delete", "trash")),
        group("Page", t("addPage", "plus"), t("fitPage", "fit")),
        group("Styles", t("swatches", "swatches"), t("textStyles", "textStyles"), t("objectStyles", "objectStyles"), t("fonts", "fonts")),
      ]],
      ["arrange", "Arrange", this.arrangeGroups(group, t)],
      ["figure", "Figure", [
        group("Scale", t("addScaleBar", "scalebar"), t("measureScale", "measure")),
        group("Zoom", t("zoomInset", "zoomInset")),
        group("Significance", t("toolSigBracket", "sigBracket"), t("stackBrackets", "stackBrackets")),
        group("Symbols", t("makeSymbol", "symbol"), t("symbols", "symbols")),
        group("Maths", t("equation", "equation")),
        group("Report", t("figureReport", "report")),
      ]],
      ["combine", "Combine", [
        group("Pathfinder", t("unite", "unite"), t("minusFront", "minusFront"), t("intersect", "intersect"), t("exclude", "exclude")),
        group("Clipping mask", t("makeClipMask", "clip"), t("releaseClipMask", "unclip")),
      ]],
      ["view", "View", [
        group("Zoom", t("zoomOut", "zoomout"), h("span", { class: "zoom-label", "aria-live": "off" }, "100%"),
          t("zoomIn", "zoomin"), t("zoomFit", "fit"), t("zoom100", "actual"), t("centrePage", "centre")),
        group("Show", this.toggleButton("toggleRulers", "ruler", "show_rulers"),
          this.toggleButton("toggleGrid", "grid", "show_grid", ". Things snap to it while it shows"),
          this.toggleButton("toggleGuides", "guides", "show_guides", ". Drag a new one out of a ruler")),
        group("Grid", t("gridSettings", "gear")),
        group("Check colours", colourVisionField()),
      ]],
    ];
    const tabRow = h("div", { class: "ribbon-tabs", role: "tablist", "aria-label": "Command tabs" });
    this.ribbonTabs = {};
    const panelEls = tabs.map(([key, title, groups]) => {
      const tab = h("button", { type: "button", role: "tab", class: "rtab", id: `rtab-${key}`, "aria-controls": `rpanel-${key}`,
        "aria-selected": "false", tabindex: -1 }, title);
      tab.addEventListener("click", () => this.showTab(key));
      tabRow.append(tab);
      const panel = h("div", { class: "ribbon-panel", role: "tabpanel", id: `rpanel-${key}`, "aria-labelledby": `rtab-${key}`,
        hidden: true }, ...groups);
      const first = panel.querySelector("button.tool, select");
      if (first) first.tabIndex = 0;
      roving(panel, "button.tool, select");
      this.ribbonTabs[key] = { tab, panel };
      return panel;
    });
    // Left and right move between the tabs (and show them), as in any tab list
    tabRow.addEventListener("keydown", (e) => {
      const keys = Object.keys(this.ribbonTabs);
      const i = keys.indexOf(this.ribbonTab);
      const j = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: keys.length - 1 }[e.key];
      if (j === undefined) return;
      e.preventDefault();
      this.showTab(keys[(j + keys.length) % keys.length]);
      this.ribbonTabs[this.ribbonTab].tab.focus();
    });
    const quick = h("div", { class: "quick", role: "toolbar", "aria-label": "Always available" },
      this.toggleButton("toggleSnap", "magnet", "snap", `. Hold ${this.app.mod.replace("+", "")} while dragging to ignore it once`),
      t("preflight", "check"), this.toolButton("export", "export", { primary: true }), t("preferences", "gear"),
      t("shortcuts", "help"));
    quick.querySelector("button").tabIndex = 0;
    roving(quick, "button.tool");
    root.append(h("div", { class: "ribbon-bar" }, tabRow, h("div", { class: "spacer" }), quick), ...panelEls);
    this.showTab(this.ribbonTabs[this.app.prefs.ribbon_tab] ? this.app.prefs.ribbon_tab : "home", false);
  },
  arrangeGroups(group, t) {
    return [
      group("Align", t("alignLeft", "alignLeft"), t("alignCenter", "alignCenter"), t("alignRight", "alignRight"),
        t("alignTop", "alignTop"), t("alignMiddle", "alignMiddle"), t("alignBottom", "alignBottom")),
      group("Distribute", t("distributeLeft", "distLeft"), t("distributeCenter", "distCenter"), t("distributeRight", "distRight"),
        t("distributeTop", "distTop"), t("distributeMiddle", "distMiddle"), t("distributeBottom", "distBottom")),
      group("Spacing", t("distributeH", "spaceH"), t("distributeV", "spaceV"), gapField(this.app)),
      group("Align to", alignToField(this.app)),
      group("Match size", t("sameWidth", "sameWidth"), t("sameHeight", "sameHeight")),
      group("Group", t("group", "group"), t("ungroup", "ungroup"), t("gridLayout", "cells")),
      group("Order", t("bringToFront", "front"), t("bringForward", "forward"), t("sendBackward", "backward"),
        t("sendToBack", "back")),
    ];
  },
  showTab(key, remember = true) {
    this.ribbonTab = key;
    for (const [k, { tab, panel }] of Object.entries(this.ribbonTabs)) {
      tab.setAttribute("aria-selected", k === key ? "true" : "false");
      tab.tabIndex = k === key ? 0 : -1;
      panel.hidden = k !== key;
    }
    if (remember) this.app.rememberUi({ ribbon_tab: key });
  },

  // Drawing tools, down the side of the page as in Illustrator and Photoshop
  buildToolbox() {
    const box = document.getElementById("toolbox");
    const t = (cmd, ic, tool) => this.toolButton(cmd, ic, { tool });
    const sep = () => h("div", { class: "tool-sep", role: "separator" });
    box.append(t("toolSelect", "select", "select"), sep(),
      t("toolText", "text", "text"), t("toolLabel", "label", "label"), sep(),
      t("toolLine", "line", "line"), t("toolArrow", "arrow", "arrow"), t("toolPen", "pen", "pen"), sep(),
      t("toolRect", "rect", "rect"), t("toolRoundRect", "roundrect", "roundrect"), t("toolEllipse", "ellipse", "ellipse"),
      t("toolTriangle", "triangle", "triangle"), t("toolArc", "arc", "arc"), t("toolBracket", "bracket", "bracket"),
      this.shapeMenuButton(), sep(), t("toolFill", "bucket", "fill"), sep(), t("insertPicture", "picture"));
    box.querySelector("button.tool").tabIndex = 0;
    roving(box, "button.tool", true);
    this.renderTools("select");
  },
  // The Format Painter shows whether it's painting; a double-click keeps it painting
  painterButton() {
    const b = this.toolButton("formatPainter", "brush");
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("dblclick", () => this.app.formatPainter(true));
    return b;
  },
  renderTools(tool) {
    for (const b of document.querySelectorAll('[data-cmd="formatPainter"]')) b.setAttribute("aria-pressed", tool === "painter" ? "true" : "false");
    for (const b of document.querySelectorAll("#toolbox [data-tool]")) {
      b.setAttribute("aria-pressed", b.dataset.tool === tool ? "true" : "false");
    }
    if (this.shapeBtn) {
      const on = tool === "shape";
      this.shapeBtn.classList.toggle("active", on);
      this.shapeBtn.title = `Shapes (S)${on ? ` — drawing: ${shapeName(canvas.shapeGeom)}` : ""}`;
    }
  },

  // Shapes menu: every shape in groups, as a grid of icons ---------------------------------

  shapeMenuButton() {
    const cat = this.app.info.shapes || { groups: [], shapes: {} };
    const c = this.app.commands.shapesMenu;
    const btn = h("button", { type: "button", class: "tool", id: "shapes-button", title: `${c.label} (${c.keys})`,
      "aria-label": c.label, "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "shape-menu",
      "data-cmd": "shapesMenu", tabindex: -1 },
    icon("shapes"), h("span", { class: "tool-label" }, `${c.short} ▸`));
    btn.addEventListener("click", () => this.toggleShapeMenu());
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); this.openShapeMenu(); }
    });
    // The name of the shape under the pointer or focus, for anyone who doesn't know the icons
    const hint = h("p", { class: "shape-hint", "aria-hidden": "true" }, "Choose a shape, then drag on the page");
    const menu = h("div", { id: "shape-menu", class: "shape-menu", role: "menu", "aria-label": "Shapes", hidden: true },
      ...cat.groups.map((g) => h("div", { class: "shape-group", role: "group", "aria-label": g.title },
        h("div", { class: "shape-group-title", "aria-hidden": "true" }, g.title),
        h("div", { class: "shape-grid" }, ...g.shapes.map((geom) => {
          const name = cat.shapes[geom].name;
          const item = h("button", { type: "button", class: "shape-item", role: "menuitem", tabindex: -1,
            "data-geom": geom, "aria-label": name, title: name }, pathIcon(cat.shapes[geom].icon));
          const show = () => { hint.textContent = name; };
          item.addEventListener("click", () => this.chooseShape(geom));
          item.addEventListener("pointerenter", show);
          item.addEventListener("focus", show);
          return item;
        })))),
      hint);
    menu.addEventListener("keydown", (e) => this.shapeMenuKey(e));
    document.body.append(menu);
    document.addEventListener("pointerdown", (e) => {
      if (!menu.hidden && !menu.contains(e.target) && !btn.contains(e.target)) this.closeShapeMenu(false);
    }, true);
    window.addEventListener("resize", () => { if (!menu.hidden) this.placeShapeMenu(); });
    this.shapeBtn = btn;
    this.shapeMenu = menu;
    return btn;
  },
  placeShapeMenu() {
    const r = this.shapeBtn.getBoundingClientRect(), m = this.shapeMenu;
    m.style.maxHeight = `${window.innerHeight - 16}px`;
    m.style.left = `${Math.max(8, Math.min(r.right + 6, window.innerWidth - m.offsetWidth - 8))}px`;
    m.style.top = `${Math.max(8, Math.min(r.top, window.innerHeight - m.offsetHeight - 8))}px`;
  },
  openShapeMenu() {
    const m = this.shapeMenu;
    m.hidden = false;
    this.shapeBtn.setAttribute("aria-expanded", "true");
    this.placeShapeMenu();
    const items = [...m.querySelectorAll(".shape-item")];
    for (const b of items) b.toggleAttribute("aria-current", b.dataset.geom === canvas.shapeGeom);
    (items.find((b) => b.dataset.geom === canvas.shapeGeom) || items[0])?.focus();
  },
  closeShapeMenu(refocus = true) {
    if (this.shapeMenu.hidden) return;
    this.shapeMenu.hidden = true;
    this.shapeBtn.setAttribute("aria-expanded", "false");
    if (refocus) this.shapeBtn.focus();
  },
  toggleShapeMenu() {
    if (this.shapeMenu.hidden) this.openShapeMenu();
    else this.closeShapeMenu();
  },
  chooseShape(geom) {
    this.closeShapeMenu(false);
    canvas.setTool("shape", geom);
    canvas.stage.focus({ preventScroll: true });
    announce(`${shapeName(geom)}: drag on the page to draw it, click for a 2 cm one, or press Enter to place one in the middle`);
  },
  // Arrow keys move through the grid, typing jumps to a name, Enter chooses, Escape closes
  shapeMenuKey(e) {
    e.stopPropagation();
    const items = [...this.shapeMenu.querySelectorAll(".shape-item")];
    const i = items.indexOf(document.activeElement);
    const go = (j) => { e.preventDefault(); items[Math.max(0, Math.min(items.length - 1, j))]?.focus(); };
    if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); this.closeShapeMenu(); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (i >= 0) this.chooseShape(items[i].dataset.geom); }
    else if (e.key === "ArrowRight") go(i + 1);
    else if (e.key === "ArrowLeft") go(i - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(items.length - 1);
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") go(items.indexOf(verticalNeighbour(items, i, e.key === "ArrowDown")));
    else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      clearTimeout(this._typedTimer);
      this._typed = (this._typed || "") + e.key.toLowerCase();
      this._typedTimer = setTimeout(() => { this._typed = ""; }, 700);
      // One letter cycles through the names starting with it; more letters narrow the search
      const n = items.length;
      for (let k = this._typed.length > 1 ? 0 : 1; k <= n; k++) {
        const b = items[(i + k + n) % n];
        if (b.getAttribute("aria-label").toLowerCase().startsWith(this._typed)) { b.focus(); break; }
      }
    }
  },

  // Pages ------------------------------------------------------------------------------

  buildPages() {
    const root = document.getElementById("pages");
    this.pageList = h("ul", { class: "page-list", role: "listbox", "aria-label": "Pages", tabindex: 0 });
    root.append(
      h("div", { class: "panel-head" }, h("h2", { id: "pages-title" }, "Pages"),
        h("div", { class: "panel-actions" },
          button("Add a page", () => this.app.run("addPage"), icon("plus"), "icon-btn"),
          button("Duplicate this page", () => this.app.run("duplicatePage"), icon("duplicate"), "icon-btn"),
          button("Delete this page", () => this.app.run("deletePage"), icon("trash"), "icon-btn"))),
      this.pageList);
    this.pageList.addEventListener("keydown", (e) => {
      if (!store.doc) return;
      const n = store.doc.pages.length;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const d = e.key === "ArrowDown" ? 1 : -1;
        if (e.altKey) this.app.run(d > 0 ? "pageDown" : "pageUp");
        else store.setPage(Math.min(Math.max(store.pageIndex + d, 0), n - 1));
        announce(`Page ${store.pageIndex + 1} of ${n}: ${store.page().name}`);
      } else if (e.key === "F2" || e.key === "Enter") {
        e.preventDefault();
        this.renamePage(store.pageIndex);
      }
    });
    // Drag a page up or down the list to move it (listdrag.js)
    let from = null;
    listDrag(this.pageList, {
      rows: "li[data-index]",
      scroller: root.closest(".sidebar"),
      start: (li) => {
        from = Number(li.dataset.index);
        li.classList.add("drag-hidden");
        return { row: li, depth: 0, count: 1 };
      },
      places: (rows) => Array.from({ length: rows.length + 1 }, (_, k) => [{ depth: 0, place: k }]),
      drop: (t) => {
        this.app.movePage(from, t.place);
        this.renderPages();
        announce(`Page ${store.pageIndex + 1} of ${store.doc.pages.length}: ${store.page().name}`);
      },
      cancel: () => this.renderPages(),
    });
  },
  renderPages() {
    if (!store.doc || this.layerDrag) return;   // mid-drag the lists are the drag's
    const pu = this.app.prefs.page_units || "mm";
    this.pageList.replaceChildren(...store.doc.pages.map((p, i) => {
      const li = h("li", { role: "option", id: `page-opt-${i}`, "aria-selected": i === store.pageIndex ? "true" : "false",
        class: i === store.pageIndex ? "current" : "", "data-index": i },
      h("span", { class: "page-num" }, i + 1),
      h("span", { class: "page-name" }, p.name),
      h("span", { class: "page-size" }, `${fmt(toUnit(p.width, pu), 1)} × ${fmt(toUnit(p.height, pu), 1)} ${UNIT_LABEL[pu]}`));
      li.addEventListener("click", () => store.setPage(i));
      li.addEventListener("dblclick", () => this.renamePage(i));
      li.addEventListener("contextmenu", (e) => {
        if (e.target.closest("input")) return;   // the name being typed keeps its own menu
        e.preventDefault();
        this.pageMenu(i, e.clientX, e.clientY);
      });
      return li;
    }));
    this.pageList.setAttribute("aria-activedescendant", `page-opt-${store.pageIndex}`);
  },
  renamePage(i) {
    const li = this.pageList.children[i];
    if (!li) return;
    const name = li.querySelector(".page-name");
    const input = h("input", { type: "text", value: store.doc.pages[i].name, "aria-label": "Page name", class: "rename" });
    name.replaceWith(input);
    input.focus();
    input.select();
    const done = (save) => {
      if (save && input.value.trim()) store.update("Rename page", (d) => { d.pages[i].name = input.value.trim(); });
      else this.renderPages();
      this.pageList.focus();
    };
    input.addEventListener("keydown", (e) => {
      keepFieldKeys(e);
      if (e.key === "Enter") done(true);
      if (e.key === "Escape") done(false);
    });
    input.addEventListener("blur", () => done(true), { once: true });
  },
  // A page's right-click menu (it becomes the current page, as a click would make it)
  pageMenu(i, x, y) {
    store.setPage(i);
    const c = (name, opts) => this.app.menuEntry(name, opts);
    const n = store.doc.pages.length;
    contextMenu.show([
      c("addPage"), c("duplicatePage"), c("deletePage", { disabled: n < 2 }),
      "-",
      c("pageUp", { disabled: i === 0 }), c("pageDown", { disabled: i === n - 1 }),
      "-",
      { label: "Rename page", keys: "F2", run: () => this.renamePage(i) },
    ], x, y, this.pageList);
  },

  // Objects on the page ------------------------------------------------------------------
  // A tree (layers.js): the page's objects front to back, and under each open group its parts.
  // Picking a part works inside its group, as double-clicking it on the page does. Drag rows to
  // move objects in front of or behind others, into or out of groups (the row's indent follows
  // the pointer across), or onto a page in the Pages list; the page shows the new order as it
  // goes, and Escape puts it back (listdrag.js).

  buildLayers() {
    const root = document.getElementById("layers");
    this.openGroups = new Set();
    this.layerList = h("ul", { class: "layer-list", role: "tree", "aria-label": "Objects on this page, front to back",
      "aria-multiselectable": "true", tabindex: 0 });
    root.append(h("div", { class: "panel-head" }, h("h2", {}, "Objects"),
      h("span", { class: "hint" }, "front to back")), this.layerList);
    this.layerList.addEventListener("keydown", (e) => this.layerKey(e));
    const indent = (depth) => depth * parseFloat(getComputedStyle(document.documentElement).fontSize || "16");   // 1rem a level
    listDrag(this.layerList, {
      rows: "li[data-key]",
      scroller: root,
      start: (li) => this.startLayerDrag(li.dataset.key),
      places: (rows) => {
        const left = rows.map((li) => this.rows.get(li.dataset.key));
        return Array.from({ length: left.length + 1 }, (_, k) => slotPlaces(this.layerDrag.items, left, k, this.layerDrag.moving));
      },
      into: (li) => intoPlace(this.rows.get(li.dataset.key), this.layerDrag.moving),
      open: (li) => {
        this.openGroups.add(li.dataset.key);
        this.drawLayers(this.layerDrag.items);
        return true;
      },
      indent,
      outside: (el) => {
        const li = el.closest?.(".page-list li[data-index]"), i = li ? Number(li.dataset.index) : -1;
        return i >= 0 && i !== store.pageIndex ? { el: li, target: { page: i } } : null;
      },
      preview: (t) => this.previewLayerDrag(t),
      drop: (t) => this.dropLayerDrag(t),
      cancel: () => this.endLayerDrag(false),
    });
  },
  // The rows as the page is now (or as it was when a drag began); the groups being worked inside
  // are open
  layerRows(items = store.items()) {
    for (const id of store.scope) this.openGroups.add(id);
    return treeRows(items, (g) => this.openGroups.has(g.id));
  },
  renderLayers() {
    if (!store.doc || this.layerDrag) return;   // mid-drag the list is the drag's
    this.drawLayers();
  },
  drawLayers(items = store.items()) {
    const rows = this.layerRows(items);
    this.rows = new Map(rows.map((r) => [r.it.id, r]));
    if (!rows.length) {
      this.layerList.replaceChildren(h("li", { class: "empty" }, "Nothing on this page yet."));
      return;
    }
    // Rows being dragged (and their parts) are out of the list until they're dropped
    const away = this.layerDrag ? new Set(this.layerDrag.ids) : null;
    const sizes = new Map();
    for (const r of rows) sizes.set(r.path.join("/"), (sizes.get(r.path.join("/")) || 0) + 1);
    const seen = new Map();
    this.layerList.replaceChildren(...rows.map((r) => {
      const at = r.path.join("/");
      seen.set(at, (seen.get(at) || 0) + 1);
      const li = this.layerRow(r, sizes.get(at), seen.get(at));
      if (away && (away.has(r.it.id) || r.path.some((id) => away.has(id)))) li.classList.add("drag-hidden");
      return li;
    }));
    const active = store.selection[store.selection.length - 1];
    if (active && this.rows.has(active)) this.layerList.setAttribute("aria-activedescendant", `layer-opt-${active}`);
    else this.layerList.removeAttribute("aria-activedescendant");
  },
  layerRow(r, setSize, pos) {
    const { it } = r, group = it.type === "group";
    const here = r.path.join("/") === store.scope.join("/"), selected = here && store.selection.includes(it.id);
    // Inside a group being worked on, the rest of the page is faded here as on the page
    const inside = store.scope.every((id, i) => r.path[i] === id) || store.scope.includes(it.id);
    const li = h("li", { role: "treeitem", id: `layer-opt-${it.id}`, "data-key": it.id, "aria-level": r.depth + 1,
      "aria-setsize": setSize, "aria-posinset": pos, "aria-selected": selected ? "true" : "false",
      "aria-expanded": group ? String(r.open) : null, style: `--depth: ${r.depth}`,
      class: [selected && "selected", !inside && "outside-scope", r.mask && "mask"].filter(Boolean).join(" ") },
      h("span", { class: "twisty", "aria-hidden": "true",
        onclick: (e) => { e.stopPropagation(); if (group) this.toggleGroup(it.id); } }, group ? icon(r.open ? "open" : "closed") : null),
      h("span", { class: "layer-name" }, itemLabel(it, store.doc)),
      r.mask ? h("span", { class: "hint", title: "A clipping mask's shape: what's below it shows only inside it" }, "clips") : null,
      button(it.hidden ? "Show" : "Hide", (e) => {
        e.stopPropagation();
        store.update(it.hidden ? "Show" : "Hide", (d) => { findItem(d.pages[store.pageIndex].items, it.id).hidden = !it.hidden; });
      }, icon(it.hidden ? "eyeoff" : "eye"), "icon-btn small"),
      button(it.locked ? "Unlock" : "Lock", (e) => {
        e.stopPropagation();
        store.update(it.locked ? "Unlock" : "Lock", (d) => { findItem(d.pages[store.pageIndex].items, it.id).locked = !it.locked; });
      }, icon(it.locked ? "lock" : "unlock"), "icon-btn small"));
    li.addEventListener("click", (e) => this.pickRow(r, e));
    li.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      if (!selected) this.pickRow(r);
      this.app.objectListMenu(e.clientX, e.clientY);
    });
    return li;
  },
  toggleGroup(id, open = !this.openGroups.has(id)) {
    if (open) this.openGroups.add(id);
    else if (!store.scope.includes(id)) this.openGroups.delete(id);   // a group being worked inside stays open
    this.renderLayers();
  },
  // Pick a row: its object alone, or (Shift or ⌘) added or taken away. A row in another group
  // works inside that group, out of the one before
  pickRow(r, e = null) {
    const id = r.it.id;
    if (r.path.join("/") !== store.scope.join("/")) {
      store.setScope(r.path);
      store.select([id]);
    } else if (e && (e.shiftKey || e.metaKey || (e.ctrlKey && !isMac))) {
      // (On a Mac, Control-click is a right-click)
      store.select(store.selection.includes(id) ? store.selection.filter((x) => x !== id) : [...store.selection, id]);
    } else store.select([id]);
  },
  layerKey(e) {
    if (!store.doc) return;
    const rows = this.layerRows();
    if (!rows.length) return;
    const last = store.selection[store.selection.length - 1], cur = rows.findIndex((r) => r.it.id === last), r = rows[cur];
    const go = (j) => {
      const to = rows[Math.min(Math.max(j, 0), rows.length - 1)];
      this.pickRow(to);
      announce(`${itemLabel(to.it, store.doc)}${to.depth ? `, in ${itemLabel(to.parent, store.doc)}` : ""}`);
    };
    const arrow = { ArrowDown: 1, ArrowUp: -1 }[e.key];
    if (arrow && e.altKey) {
      e.preventDefault();
      if (cur >= 0) this.app.run(arrow > 0 ? "sendBackward" : "bringForward");
    } else if (arrow) {
      e.preventDefault();
      go(cur < 0 ? 0 : cur + arrow);
    } else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && e.altKey) {
      e.preventDefault();
      if (e.key === "ArrowRight") this.app.moveIntoGroupAbove();
      else this.app.moveOutOfGroup();
    } else if (e.key === "ArrowRight" && r?.it.type === "group") {
      // Open a group; once open, on to its first part
      e.preventDefault();
      if (!r.open) { this.toggleGroup(r.it.id, true); announce(`Opened ${itemLabel(r.it, store.doc)}`); }
      else if (rows[cur + 1]?.depth > r.depth) go(cur + 1);
    } else if (e.key === "ArrowLeft" && r) {
      // Close a group; from a part, back to its group
      e.preventDefault();
      if (r.open && !store.scope.includes(r.it.id)) { this.toggleGroup(r.it.id, false); announce(`Closed ${itemLabel(r.it, store.doc)}`); }
      else if (r.depth) go(rows.findIndex((x) => x.it.id === r.path[r.path.length - 1]));
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      go(e.key === "Home" ? 0 : rows.length - 1);
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      this.app.run("delete");
    }
  },

  // Dragging in the Objects list: the selection moves (the pressed row alone if it isn't
  // selected). The drag works on a copy of the page as it was, put back for each new place
  startLayerDrag(id) {
    let r = this.rows.get(id);
    if (!r || r.mask) return null;   // a clipping mask's shape stays on top
    if (r.path.join("/") !== store.scope.join("/") || !store.selection.includes(id)) this.pickRow(r);
    r = this.rows.get(id);
    const ids = store.selection.filter((x) => this.rows.has(x) && !this.rows.get(x).mask);
    if (!r || !ids.length) return null;
    const pages = JSON.stringify(store.doc.pages), items = JSON.parse(pages)[store.pageIndex].items;
    this.layerDrag = { ids, pages, items, moving: ids.map((x) => locate(items, x)?.it).filter(Boolean), scope: store.scope.slice() };
    store.beginLive();
    canvas.reordering = true;   // nothing faded while the order is shown
    this.drawLayers(items);
    return { row: document.getElementById(`layer-opt-${id}`), depth: r.depth, count: ids.length };
  },
  // The page as it would be with the objects dropped there (or as it was)
  applyLayerDrag(t) {
    const drag = this.layerDrag;
    store.doc.pages = JSON.parse(drag.pages);
    if (t?.place) return moveItems(store.doc.pages[store.pageIndex].items, drag.ids, t.place);
    if (t?.outside) return moveToPage(store.doc, store.pageIndex, t.outside.page, drag.ids);
    return null;
  },
  previewLayerDrag(t) {
    this.applyLayerDrag(t);
    store.live();
  },
  dropLayerDrag(t) {
    const drag = this.layerDrag, moved = this.applyLayerDrag(t);
    if (!moved || JSON.stringify(store.doc.pages) === drag.pages) return this.endLayerDrag(false);
    const what = moved.length === 1 ? itemLabel(moved[0], store.doc) : `${moved.length} objects`;
    let said;
    if (t.place) {
      // The moved objects stay selected, worked on where they are now
      store.scope = t.place.path.slice();
      store.selection = moved.map((it) => it.id);
      said = `Moved ${what} ${this.app.placeText(t.place, store.doc.pages[store.pageIndex].items)}`;
    } else {
      store.selection = [];
      const p = store.doc.pages[t.outside.page];
      said = `Moved ${what} to page ${t.outside.page + 1}, ${p.name}`;
    }
    store.fixScope();
    store.afterChange?.(store.doc);   // a symbol being edited goes back once it's been left
    this.endLayerDrag(true, t.place ? "Move in the Objects list" : "Move to another page");
    announce(said);
  },
  endLayerDrag(keep, label) {
    const drag = this.layerDrag;
    if (!drag) return;
    this.layerDrag = null;
    canvas.reordering = false;
    if (keep) store.endLive(label);
    else {
      store.cancelLive();
      store.scope = drag.scope;
    }
    store.emit("selection");
    this.renderPages();
    this.renderLayers();
  },

  // Status bar ----------------------------------------------------------------------------

  buildStatus() {
    const bar = document.getElementById("status");
    this.message = h("span", { id: "live", class: "message", role: "status", "aria-live": "polite" });
    this.cursor = h("span", { class: "cursor-pos", "aria-hidden": "true" });
    this.saveState = h("span", { class: "save-state" });
    const z = (cmd, ic) => button(`${this.app.commands[cmd].label} (${this.app.commands[cmd].keys})`, () => this.app.run(cmd),
      icon(ic), "icon-btn small");
    const zoom = h("span", { class: "status-zoom", role: "group", "aria-label": "Zoom" }, z("zoomOut", "zoomout"),
      h("span", { class: "zoom-label", "aria-live": "off" }, "100%"), z("zoomIn", "zoomin"), z("zoomFit", "fit"),
      z("centrePage", "centre"));
    // How far the arrow keys move the selection now; a click switches between following the zoom and 1 pt
    this.nudge = h("button", { type: "button", class: "btn toggle small nudge-step", "data-pref": "nudge_zoom",
      "aria-pressed": this.app.prefs.nudge_zoom ? "true" : "false" });
    this.nudge.addEventListener("click", () => this.app.run("toggleNudgeZoom"));
    bar.append(this.message, h("span", { class: "spacer" }), zoom, this.nudge, this.cursor, this.saveState);
    this.renderNudge();
  },
  renderNudge() {
    const s = this.app.nudgeStep(), on = !!this.app.prefs.nudge_zoom;
    this.nudge.textContent = `Arrows ${s.text}`;
    this.nudge.title = on ? `Arrow keys move the selection ${s.text} at this zoom: less zoomed in, more zoomed out (Shift: 10 times, `
      + `${isMac ? "Option" : "Alt"}: a tenth). Click for a fixed 1 pt.`
      : "Arrow keys move the selection 1 pt at every zoom. Click to make them follow the zoom.";
    this.nudge.setAttribute("aria-label", on ? `Arrow keys move ${s.text}, following the zoom` : "Arrow keys move 1 pt at every zoom");
  },
  renderSaveState() {
    if (!store.doc) return;
    const name = store.path ? store.path.split(/[\\/]/).pop() : "Not saved yet";
    this.saveState.textContent = `${name}${store.dirty ? " — unsaved changes" : store.path ? " — saved" : ""}`;
  },

  // Dialogs ------------------------------------------------------------------------------

  dialog(title, body, actions = [], closeLabel = null) {
    const id = `dlg-${Date.now()}`;
    const dlg = h("dialog", { class: "dialog", "aria-labelledby": id },
      h("form", { method: "dialog" },
        h("h2", { id }, title),
        h("div", { class: "dialog-body" }, body),
        h("div", { class: "dialog-actions" }, ...actions,
          h("button", { type: "submit", class: "btn", value: "close" }, closeLabel || (actions.length ? "Cancel" : "Close")))));
    dlg.addEventListener("close", () => dlg.remove());
    dlg.addEventListener("keydown", (e) => e.stopPropagation());
    document.body.append(dlg);
    dlg.showModal();
    // Start on the first control (Chrome and Edge would otherwise focus a body that scrolls)
    (dlg.querySelector(".dialog-body :is(input, select, textarea, button, summary)")
      || dlg.querySelector(".dialog-actions button"))?.focus();
    return dlg;
  },

  // An accessible yes/no question (focus starts on the safe choice)
  confirm(title, message, okLabel = "OK") {
    if (this.app.autoConfirm) return Promise.resolve(true);
    return new Promise((resolve) => {
      const ok = h("button", { type: "button", class: "btn primary" }, okLabel);
      const dlg = this.dialog(title, h("p", {}, message), [ok]);
      let answered = false;
      ok.addEventListener("click", () => { answered = true; resolve(true); dlg.close(); });
      dlg.addEventListener("close", () => { if (!answered) resolve(false); });
      dlg.querySelector("button[value=close]")?.focus();
    });
  },

  exportDialog() {
    const prefs = this.app.prefs;
    const saved = prefs.export || {};
    const formats = new Set(saved.formats || prefs.default_formats || ["pdf", "png"]);
    const check = (fmtName, label, extra = "") => {
      const id = `ex-${fmtName}`;
      return h("label", { class: "check-line", for: id },
        h("input", { type: "checkbox", id, value: fmtName, checked: formats.has(fmtName) }), h("span", {}, label),
        extra ? h("span", { class: "hint" }, extra) : null);
    };
    const dpiSel = selectField("Resolution for PNG, TIFF and JPEG", String(saved.dpi || prefs.default_dpi || 600),
      [["300", "300 dpi"], ["600", "600 dpi"], ["1200", "1200 dpi"], ["custom", "Custom…"]], (v) => { custom.hidden = v !== "custom"; });
    const custom = h("div", { hidden: true }, numField("Custom resolution", saved.dpi || 600, "dpi", () => {}, { min: 50, step: 50 }));
    const pages = selectField("Pages", "current", [["current", `This page (${store.page().name})`], ["all", `All ${store.doc.pages.length} pages`]], () => {});
    const bg = selectField("Background", saved.transparent === false ? "white" : "transparent",
      [["transparent", "Transparent"], ["white", "White"]], () => {});
    const advanced = h("details", { class: "advanced" }, h("summary", {}, "More options (CMYK, EPS, fonts)"),
      check("jpeg", "JPEG"), check("eps", "EPS", "transparency gets flattened"),
      h("label", { class: "check-line", for: "ex-cmyk" }, h("input", { type: "checkbox", id: "ex-cmyk", checked: !!saved.cmyk }),
        h("span", {}, "CMYK colour (TIFF, JPEG, PDF)"), h("span", { class: "hint" }, "only if the journal asks for it")),
      h("label", { class: "check-line", for: "ex-fonts" }, h("input", { type: "checkbox", id: "ex-fonts", checked: saved.embed_fonts !== false }),
        h("span", {}, "Embed fonts missing from placed PDFs"), h("span", { class: "hint" }, "R's pdf() leaves Helvetica out")));
    const results = h("div", { class: "results", role: "status", "aria-live": "polite" });
    const go = h("button", { type: "button", class: "btn primary" }, "Export…");
    const body = h("div", {},
      h("fieldset", { class: "formats" }, h("legend", {}, "Formats"),
        check("pdf", "PDF", "vector; placed PDFs go in unchanged"), check("svg", "SVG", "vector; placed SVGs go in unchanged"),
        check("png", "PNG"), check("tiff", "TIFF", "LZW-compressed"),
        check("pptx", "PowerPoint", "editable; what PowerPoint can't draw exactly goes in as pictures")),
      dpiSel, custom, pages, bg, advanced, results);
    const dlg = this.dialog("Export", body, [go]);
    go.addEventListener("click", async () => {
      const chosen = [...dlg.querySelectorAll(".formats input:checked, .advanced input[value]:checked")].map((i) => i.value);
      if (!chosen.length) { results.textContent = "Choose at least one format."; return; }
      let dpi = dpiSel.querySelector("select").value;
      dpi = dpi === "custom" ? parseFloat(custom.querySelector("input").value) : parseFloat(dpi);
      const opts = {
        formats: chosen, dpi, transparent: bg.querySelector("select").value === "transparent",
        cmyk: dlg.querySelector("#ex-cmyk").checked, embed_fonts: dlg.querySelector("#ex-fonts").checked,
        pages: pages.querySelector("select").value === "all" ? null : [store.pageIndex],
      };
      const base = await this.app.chooseExportBase();
      if (!base) return;
      go.disabled = true;
      results.replaceChildren(h("p", {}, "Exporting…"));
      try {
        const res = await rpc("export", store.doc, { ...opts, base, doc_path: store.path });
        this.app.savePrefs({ export: { formats: chosen, dpi, transparent: opts.transparent, cmyk: opts.cmyk, embed_fonts: opts.embed_fonts } });
        results.replaceChildren(h("p", {}, `Exported ${res.files.length} file${res.files.length === 1 ? "" : "s"}:`),
          h("ul", { class: "file-list" }, ...res.files.map((f) => h("li", {}, f.split(/[\\/]/).pop(), " ",
            this.app.info.native ? button(`Show ${f.split(/[\\/]/).pop()} in the Finder`, () => rpc("reveal", f), "Show") : null))),
          res.warnings.length ? h("ul", { class: "warnings" }, ...res.warnings.map((w) => h("li", {}, w))) : null);
        announce(`Exported ${res.files.length} files`);
      } catch (err) {
        results.replaceChildren(h("p", { class: "error" }, `Export failed: ${err.message}`));
      } finally { go.disabled = false; }
    });
  },

  // The figure report (report.py): the formats to write, none chosen to start with
  figureReportDialog() {
    const check = (fmtName, label, extra) => {
      const id = `rp-${fmtName}`;
      return h("label", { class: "check-line", for: id }, h("input", { type: "checkbox", id, value: fmtName }), h("span", {}, label),
        h("span", { class: "hint" }, extra));
    };
    const n = store.doc.pages.length;
    const pages = selectField("Pages", "all", n === 1 ? [["all", "The figure's one page"]]
      : [["all", `All ${n} pages`], ["current", `This page (${store.page().name})`]], () => {});
    const results = h("div", { class: "results", role: "status", "aria-live": "polite" });
    const go = h("button", { type: "button", class: "btn primary" }, "Write report…");
    const body = h("div", {},
      h("p", {}, "For each picture: where it comes from, its copies, its size and place on the page, its scale, crop and turns, "
        + "its resolution, and its calibration and scale bars."),
      h("fieldset", { class: "formats" }, h("legend", {}, "Formats"),
        check("html", "HTML", "a page to open in a browser"), check("md", "Markdown", "for notes or a README"),
        check("csv", "CSV", "for a spreadsheet: one row per picture"), check("pdf", "PDF", "to print or attach")),
      pages, results);
    const dlg = this.dialog("Figure report", body, [go]);
    go.addEventListener("click", async () => {
      const formats = [...dlg.querySelectorAll(".formats input:checked")].map((i) => i.value);
      if (!formats.length) { results.textContent = "Choose at least one format."; return; }
      const base = await this.app.chooseReportBase();
      if (!base) return;
      go.disabled = true;
      results.replaceChildren(h("p", {}, "Writing…"));
      try {
        const res = await rpc("figure_report", store.doc, { formats, base, units: this.app.prefs.units || "cm", doc_path: store.path,
          pages: pages.querySelector("select").value === "all" ? null : [store.pageIndex] });
        const name = (f) => f.split(/[\\/]/).pop();
        results.replaceChildren(h("p", {}, `Wrote ${res.files.length} file${res.files.length === 1 ? "" : "s"}:`),
          h("ul", { class: "file-list" }, ...res.files.map((f) => h("li", {}, name(f), " ",
            this.app.info.native ? button(`Show ${name(f)} in the Finder`, () => rpc("reveal", f), "Show") : null))));
        announce(`Wrote the figure report: ${res.files.map(name).join(", ")}`);
      } catch (err) {
        results.replaceChildren(h("p", { class: "error" }, `The report failed: ${err.message}`));
      } finally { go.disabled = false; }
    });
  },

  async preflightDialog() {
    // The page's size is compared with a journal's: the page's own journal size, else the one
    // chosen here last time
    const journals = this.app.info.journals || [];
    const start = store.page().preset?.journal || this.app.prefs.check_journal || "";
    const results = h("div", { class: "preflight-results", "aria-live": "polite" });
    const check = async (journal) => {
      results.replaceChildren(h("p", {}, "Checking…"));
      try {
        const res = await rpc("preflight", store.doc, { pages: [store.pageIndex], journal,
          units: this.app.prefs.page_units || "mm" });
        const items = res.items, { smallest_text_pt: text, thinnest_line_pt: line } = res.summary;
        const summary = [text ? `Smallest text on this page: ${text} pt.` : "", line ? `Thinnest line: ${line} pt.` : ""];
        results.replaceChildren(
          h("p", {}, summary.filter(Boolean).join(" ")),
          items.length ? h("ul", { class: "preflight" }, ...items.map((f) => {
            const li = h("li", { class: f.level },
              h("span", { class: "level" }, { warning: "⚠ Check", info: "ℹ Note", ok: "✓ OK" }[f.level] || f.level), " ", f.message);
            if (f.item) {
              li.append(" ", button("Select this object", () => { store.select([f.item]); }, "Select"));
            }
            return li;
          })) : h("p", {}, "✓ Nothing to flag on this page."));
      } catch (err) {
        results.replaceChildren(h("p", { class: "error" }, err.message));
      }
    };
    this.dialog("Check before export", h("div", {},
      selectField("Compare the page size with", start, [["", "No journal"], ...journals.map((j) => [j.name, j.name])],
        (v) => { this.app.savePrefs({ check_journal: v }); check(v); }),
      results,
      h("p", { class: "hint" }, "Fonts missing from placed PDFs are embedded automatically when you export."),
      h("div", { class: "button-row" }, button("See and replace the fonts the figure's text uses", () => this.fontsDialog(), "Fonts…"))));
    await check(start);
  },

  preferencesDialog() {
    const p = this.app.prefs;
    const set = (key) => (v) => this.app.savePrefs({ [key]: v });
    const unitOpts = [["pt", "Points"], ["mm", "Millimetres"], ["cm", "Centimetres"], ["in", "Inches"]];
    const scale = h("input", { type: "range", id: "pref-scale", min: 0.9, max: 2, step: 0.1, value: p.ui_scale || 1,
      "aria-valuetext": `${Math.round((p.ui_scale || 1) * 100)} percent` });
    scale.addEventListener("input", () => {
      scale.setAttribute("aria-valuetext", `${Math.round(scale.value * 100)} percent`);
      this.app.savePrefs({ ui_scale: parseFloat(scale.value) });
    });
    const chk = (key, label) => {
      const id = `pref-${key}`;
      const input = h("input", { type: "checkbox", id, checked: !!p[key] });
      input.addEventListener("change", () => this.app.savePrefs({ [key]: input.checked }));
      return h("label", { class: "check-line", for: id }, input, h("span", {}, label));
    };
    const label = p.panel_label || {};
    const grid = p.grid || {};
    const keys = (cmd) => this.app.commands[cmd].keys;
    this.dialog("Preferences", h("div", {},
      h("fieldset", {}, h("legend", {}, "Measurements"),
        selectField("Positions and sizes in", p.units || "cm", unitOpts, set("units")),
        selectField("Page sizes in", p.page_units || "mm", unitOpts, set("page_units"))),
      h("fieldset", {}, h("legend", {}, "Theme"), this.themeGallery()),
      h("fieldset", {}, h("legend", {}, "Interface"),
        h("div", { class: "field" }, h("label", { for: "pref-scale" }, "Interface text size"), scale),
        chk("show_tool_labels", "Show labels under toolbar buttons"),
        chk("reduced_motion", "Reduce motion")),
      h("fieldset", {}, h("legend", {}, "Rulers, grid and guides"),
        chk("show_rulers", `Show rulers (${keys("toggleRulers")})`),
        chk("show_grid", `Show the grid (${keys("toggleGrid")}); things snap to it while it shows`),
        chk("show_guides", `Show guides (${keys("toggleGuides")}); hidden guides don't snap`),
        chk("snap", `Snap to guides, the grid, the page and other objects (${keys("toggleSnap")}); `
          + `hold ${this.app.mod.replace("+", "")} while dragging to ignore it once`),
        numField("Grid spacing", grid.spacing || 72 / 2.54, p.units || "cm",
          (v) => this.app.savePrefs({ grid: { ...(this.app.prefs.grid || {}), spacing: Math.max(v, 0.5) } }), { min: 0 }),
        numField("Divide each grid square into", grid.subdivisions || 10, "parts",
          (v) => this.app.savePrefs({ grid: { ...(this.app.prefs.grid || {}), subdivisions: Math.max(1, Math.round(v)) } }),
          { min: 1, step: 1 }),
        h("p", { class: "hint" }, "The finer lines appear once you zoom in far enough to see them apart. "
          + "Things snap only to lines you can see.")),
      this.recoveryFieldset(),
      updates.settingsFieldset(),
      h("fieldset", {}, h("legend", {}, "New objects"),
        numField("Default text size", p.text?.size || 6, "pt", (v) => this.app.savePrefs({ text: { ...(p.text || {}), size: v } }), { step: 0.5 }),
        numField("Default line width", p.stroke_width || 1, "pt", set("stroke_width"), { step: 0.25 }),
        numField("Panel label size", label.size || 8, "pt", (v) => this.app.savePrefs({ panel_label: { ...label, size: v } }), { step: 0.5 }),
        selectField("Panel labels", label.case || "lower", [["lower", "a, b, c"], ["upper", "A, B, C"]],
          (v) => this.app.savePrefs({ panel_label: { ...label, case: v } }))),
      h("p", { class: "hint version" }, `FigAssemble ${this.app.info.version}`),
    ));
  },

  // Themes as preview tiles in groups; choosing one applies it at once. "Match the system"
  // switches between a day theme and a night theme. The page stays white in every theme
  themeGallery() {
    const themes = this.app.info.themes || [];
    const byId = Object.fromEntries(themes.map((t) => [t.id, t]));
    const groups = { FigAssemble: "FigAssemble", RStudio: "RStudio favourites", Crops: "Crops", Science: "Science" };
    const tiles = [];
    const preview = (c, x = 0, w = 72) => [
      s("rect", { x, width: w, height: 44, fill: c.stage }),
      s("rect", { x, width: w, height: 9, fill: c.panel }),
      s("rect", { x: x + w - 18, y: 2.5, width: 14, height: 4, rx: 2, fill: c.accent }),
      s("rect", { x, y: 9, width: Math.min(14, w), height: 35, fill: c.panel }),
      s("rect", { x: x + 3, y: 13, width: Math.min(8, w - 3), height: 2, fill: c.text }),
      s("rect", { x: x + 3, y: 18, width: Math.min(6, w - 3), height: 2, fill: c.muted }),
      s("rect", { x: x + 3, y: 23, width: Math.min(8, w - 3), height: 2, fill: c.text }),
    ];
    const page = (c) => [s("rect", { x: 24, y: 14, width: 34, height: 24, fill: "#ffffff" }),
      s("rect", { x: 28, y: 19, width: 15, height: 9, fill: "none", stroke: c.sel, "stroke-width": 1.4 })];
    const tile = (id, name, svgParts) => {
      const svg = s("svg", { viewBox: "0 0 72 44", "aria-hidden": "true" });
      svg.append(...svgParts);
      const b = h("button", { type: "button", class: "theme-tile", role: "radio", "data-theme-id": id, tabindex: -1,
        "aria-checked": "false" }, svg, h("span", {}, name));
      b.addEventListener("click", () => choose(id));
      tiles.push(b);
      return b;
    };
    const day = h("select", { id: "pref-theme-day" }), night = h("select", { id: "pref-theme-night" });
    for (const [sel, key] of [[day, "theme_day"], [night, "theme_night"]]) {
      for (const g of Object.keys(groups)) {
        const og = h("optgroup", { label: groups[g] });
        og.append(...themes.filter((t) => t.group === g).map((t) => h("option", { value: t.id }, t.name)));
        sel.append(og);
      }
      sel.value = this.app.prefs[key] || (key === "theme_day" ? "light" : "dark");
      sel.addEventListener("change", () => { this.app.savePrefs({ [key]: sel.value }).then(() => mark()); });
    }
    const dayNight = h("div", { class: "theme-daynight" },
      h("div", { class: "field" }, h("label", { for: "pref-theme-day" }, "By day"), day),
      h("div", { class: "field" }, h("label", { for: "pref-theme-night" }, "At night"), night));
    const systemPreview = () => {
      const d = byId[day.value] || byId.light, n = byId[night.value] || byId.dark;
      return [...preview(d.colors, 0, 36), ...preview(n.colors, 36, 36), ...page(d.colors)];
    };
    const mark = () => {
      const cur = this.app.prefs.theme || "system";
      for (const b of tiles) {
        const on = b.dataset.themeId === cur;
        b.setAttribute("aria-checked", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
      }
      dayNight.hidden = cur !== "system";
      const sys = tiles.find((b) => b.dataset.themeId === "system")?.querySelector("svg");
      if (sys) sys.replaceChildren(...systemPreview());
    };
    const choose = (id, focus = false) => {
      this.app.savePrefs({ theme: id }).then(() => mark());
      if (focus) tiles.find((b) => b.dataset.themeId === id)?.focus();
      announce(`Theme: ${id === "system" ? "match the system" : byId[id]?.name}`);
    };
    const gallery = h("div", { class: "theme-gallery", role: "radiogroup", "aria-label": "Theme" });
    for (const g of Object.keys(groups)) {
      const own = themes.filter((t) => t.group === g);
      if (!own.length) continue;
      const grid = h("div", { class: "theme-grid" });
      if (g === "FigAssemble") grid.append(tile("system", "Match the system", systemPreview()));
      grid.append(...own.map((t) => tile(t.id, t.name, [...preview(t.colors), ...page(t.colors)])));
      gallery.append(h("h3", { class: "theme-group" }, groups[g]), grid);
    }
    // Arrow keys move through the themes and choose as they go (a radio group)
    gallery.addEventListener("keydown", (e) => {
      const i = tiles.indexOf(document.activeElement);
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (i < 0 || !step) return;
      e.preventDefault();
      choose(tiles[(i + step + tiles.length) % tiles.length].dataset.themeId, true);
    });
    mark();
    return h("div", {}, gallery, dayNight,
      h("p", { class: "hint" }, "Themes colour the interface only: the page stays white, so figures look as they'll print."));
  },

  // Copies of unsaved documents from earlier sessions, kept to offer back after a crash
  recoveryFieldset() {
    const info = h("p", { class: "hint" }, "Checking for unsaved work…");
    const clear = h("button", { type: "button", class: "btn", disabled: true }, "Delete all…");
    let kept = [];
    const show = (items) => {
      kept = items;
      const size = items.reduce((n, s) => n + s.bytes, 0);
      info.textContent = items.length
        ? `${items.length} unsaved document${items.length === 1 ? "" : "s"} from earlier sessions (${sizeText(size)}).`
        : "No unsaved work from earlier sessions is kept.";
      clear.disabled = !items.length;
    };
    clear.addEventListener("click", async () => {
      if (!kept.length || !(await this.confirmDeleteRecovery(kept.length))) return;
      show(await rpc("delete_autosaves", kept.map((s) => s.path), store.autosaveKey));
      announce("Deleted the unsaved work from earlier sessions");
    });
    rpc("autosaved", store.autosaveKey).then(show).catch(() => { info.textContent = ""; });
    return h("fieldset", {}, h("legend", {}, "Unsaved work"),
      h("p", { class: "hint" }, "If FigAssemble closes before you save, it offers your work back next time."),
      info, clear);
  },
  confirmDeleteRecovery(n) {
    return this.confirm(n === 1 ? "Delete this unsaved document?" : `Delete ${n} unsaved documents?`,
      `${n === 1 ? "It is" : "They are"} the only copy of work that was never saved. Deleting can't be undone.`, "Delete");
  },

  shortcutsDialog() {
    const rows = Object.entries(this.app.commands).filter(([, c]) => c.keys).map(([, c]) =>
      h("tr", {}, h("td", {}, c.label), h("td", {}, h("kbd", {}, c.keys))));
    this.dialog("Keyboard shortcuts", h("div", {},
      h("table", { class: "shortcuts" }, h("thead", {}, h("tr", {}, h("th", {}, "Action"), h("th", {}, "Keys"))), h("tbody", {}, ...rows)),
      h("h3", {}, "On the canvas"),
      h("ul", { class: "plain" },
        h("li", {}, "Tab / Shift+Tab: select the next or previous object"),
        h("li", {}, "Arrow keys: move by a round step that follows the zoom (shown in the status bar; 1 pt when "
          + "switched off there); with Shift by 10 steps; with Option/Alt by a tenth of one"),
        h("li", {}, "Option/Alt+Shift+arrows: make the object one step wider, narrower, taller or shorter"),
        h("li", {}, "Enter: edit text, or crop a picture; Escape: finish"),
        h("li", {}, "With a drawing tool chosen, Enter places a 2 cm shape in the middle of the view"),
        h("li", {}, "Shapes menu (S): arrow keys move, typing a name jumps to it, Enter chooses, Escape closes"),
        h("li", {}, `Right-click${isMac ? " (or Control-click)" : ""}, the menu key or Shift+F10: a menu of commands for `
          + "the selection, the page, a page in the Pages list or an object in the Objects list"),
        h("li", {}, "Shift while dragging: keep straight lines, squares and proportions"),
        h("li", {}, "Option/Alt while dragging: duplicate; ⌘/Ctrl: don't snap, just this once"),
        h("li", {}, "Things snap to the page, other objects' edges and centres, equal gaps between objects, "
          + "and guides and the grid while they show. The Snap button turns snapping off"),
        h("li", {}, "Escape while dragging: cancel the drag"),
        h("li", {}, "Guides: drag one out of a ruler; drag it, or its mark on the ruler, to move it; "
          + "drag it back onto the ruler to remove it. With nothing selected, the Page panel lists them to type positions"),
        h("li", {}, "Space + drag, or scroll: move around; ⌘/Ctrl + scroll or pinch: zoom. While the whole page fits "
          + "in the view it stays centred"),
        h("li", {}, "Objects list: drag a row to put the object in front of or behind others, into or out of a group, "
          + "or onto a page in the Pages list (Escape puts it back). With the list focused, Option/Alt + ↑ or ↓ moves the "
          + "selection forward or backward, Option/Alt + → into the group above it, Option/Alt + ← out of its group; "
          + "→ and ← open and close groups"),
        h("li", {}, "Drag a side panel's inner edge to make it wider or narrower; double-click the edge to put it back"))));
  },

  // Fonts: every font the figure's text uses, how many text objects use it and whether it's on
  // this computer; Replace swaps one for another on every page (one undo step)
  fontsDialog() {
    const body = h("div", {});
    const listId = `font-list-${Date.now()}`;
    const render = () => {
      const uses = fontUses(store.doc);
      const installed = new Set((this.app.fonts || []).map((f) => f.toLowerCase()));
      const rows = [...uses].sort((a, b) => a[0].localeCompare(b[0])).map(([font, u]) => {
        const input = h("input", { type: "text", list: listId, placeholder: "Another font", "aria-label": `Replace ${font} with` });
        const go = button(`Replace ${font} with the font typed`, () => {
          const to = input.value.trim();
          if (!to || to === font) return;
          this.app.replaceFont(font, to);
          render();
          body.querySelector("input")?.focus();
        }, "Replace");
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go.click(); } });
        const have = installed.has(font.toLowerCase()) || !this.app.fonts?.length;
        return h("tr", {},
          h("td", {}, h("span", { class: "font-name", style: { fontFamily: `"${font}"` } }, font)),
          h("td", {}, `${u.objects.size} text object${u.objects.size === 1 ? "" : "s"}${u.pages.size > 1 ? ` on ${u.pages.size} pages` : ""}`),
          h("td", { class: have ? "" : "warning" }, have ? "On this computer" : "Not on this computer: drawn with a stand-in"),
          h("td", {}, h("div", { class: "button-row inline" }, input, go)));
      });
      body.replaceChildren(
        rows.length ? h("table", { class: "fonts" },
          h("thead", {}, h("tr", {}, h("th", {}, "Font"), h("th", {}, "Used by"), h("th", {}, "Status"), h("th", {}, "Replace with"))),
          h("tbody", {}, ...rows)) : h("p", {}, "No text in this figure yet."),
        h("datalist", { id: listId }, ...(this.app.fonts || []).map((f) => h("option", { value: f }))),
        h("p", { class: "hint" }, "Text inside placed pictures keeps its own fonts; fonts missing from placed PDFs are "
          + "embedded when you export."));
    };
    render();
    this.dialog("Fonts in this figure", body);
  },

  // Swatches: the figure's named colours (editing one recolours everything linked to it),
  // ready-made palettes, and palettes kept in your library for every figure
  // Symbols: each with how often it's used, to place another copy, rename or delete
  symbolsDialog() {
    const body = h("div", {});
    const render = () => {
      const all = store.doc.symbols || [];
      const rows = all.map((sym) => {
        const name = h("input", { type: "text", value: sym.name, "aria-label": `${sym.name}: name` });
        name.addEventListener("change", () => { if (name.value.trim()) this.app.renameSymbol(sym.id, name.value.trim()); });
        const uses = copiesOf(store.doc, sym.id).length;
        return h("li", { class: "swatch-row" }, name, h("span", { class: "hint" }, `${uses} cop${uses === 1 ? "y" : "ies"}`),
          button(`Place a copy of ${sym.name} in the middle of the view`, () => { this.app.placeSymbol(sym.id); render(); }, "Place a copy"),
          uses ? null : button(`Delete ${sym.name}`, () => { this.app.deleteSymbol(sym.id); render(); }, "Delete"));
      });
      body.replaceChildren(
        all.length ? h("ul", { class: "swatch-list" }, ...rows) : h("p", {}, "No symbols in this figure yet."),
        h("p", { class: "hint" }, `Select objects and click Make symbol to make one. Copy a copy (${this.app.mod}C, ${this.app.mod}V, `
          + `${this.app.mod}D) to use it again; resizing a copy scales its lines and text with it. Double-click any copy to `
          + "change the symbol, and every copy changes with it."));
    };
    render();
    this.dialog("Symbols", body);
  },

  swatchesDialog() {
    const body = h("div", {});
    const chips = (colours) => h("span", { class: "chips", "aria-hidden": "true" },
      ...colours.map(([, c]) => h("span", { class: "chip", style: { background: c } })));
    const render = () => {
      const all = store.doc.swatches || [], holders = colourHolders(store.doc);
      const rows = all.map((sw) => {
        const picker = h("input", { type: "color", value: sw.color, "aria-label": `${sw.name}: colour` });
        picker.addEventListener("change", () => { this.app.setSwatchColour(sw.id, picker.value); render(); });
        const name = h("input", { type: "text", value: sw.name, "aria-label": `${sw.name}: name` });
        name.addEventListener("change", () => { if (name.value.trim()) this.app.renameSwatch(sw.id, name.value.trim()); });
        const uses = holders.filter((c) => c.swatch === sw.id).length;
        return h("li", { class: "swatch-row" }, picker, name, h("span", { class: "hint" }, `${uses} use${uses === 1 ? "" : "s"}`),
          button(`Delete ${sw.name} (objects keep their colour)`, () => { this.app.deleteSwatch(sw.id); render(); }, "Delete"));
      });
      const add = (p) => button(`Add the ${p.name} colours to this figure`, () => { this.app.addPalette(p.colours, p.name); render(); },
        [p.name, " ", chips(p.colours)]);
      const lib = this.app.prefs.swatch_library || [];
      const saveName = h("input", { type: "text", placeholder: "Palette name", "aria-label": "Name for a palette in your library" });
      const save = button("Save this figure's swatches as a palette in your library", async () => {
        const n = saveName.value.trim();
        if (!n || !all.length) return;
        await this.app.savePalette(n);
        render();
      }, "Save as a palette");
      body.replaceChildren(
        all.length ? h("ul", { class: "swatch-list" }, ...rows) : h("p", {}, "No swatches in this figure yet."),
        h("div", { class: "button-row" },
          button("Add a new swatch", () => { this.app.addSwatch("#000000", "New colour"); render(); }, "Add a colour"),
          button("Add the colours this figure uses as swatches, linking the objects that use them",
            () => { this.app.addUsedColours(); render(); }, "Add the figure's colours")),
        h("p", { class: "hint" }, "A colour picked from a swatch stays linked to it: change the swatch here and every "
          + "object using it changes too. Picking or typing a colour by hand unlinks it."),
        h("h3", {}, "Ready-made palettes"),
        h("p", { class: "hint" }, "Okabe-Ito and Paul Tol's colours stay distinct for colour-blind readers; viridis is for "
          + "ordered values."),
        h("div", { class: "button-row palettes" }, ...PALETTES.map(add)),
        h("h3", {}, "My library"),
        lib.length ? h("ul", { class: "plain" }, ...lib.map((p) => h("li", {}, add(p), " ",
          button(`Remove ${p.name} from your library`, async () => { await this.app.deletePalette(p.name); render(); }, "Remove"))))
          : h("p", { class: "hint" }, "Palettes saved here are offered in every figure."),
        h("div", { class: "button-row inline" }, saveName, save));
    };
    render();
    this.dialog("Swatches", body);
  },

  // Text styles: rename or delete them, with what each looks like and how much text uses it
  // (changes to a style's format come from text: "Update the style to match" on the Text tab)
  textStylesDialog() {
    const body = h("div", {});
    const render = () => {
      const all = store.doc.text_styles || [], paras = paragraphs(store.doc);
      const rows = all.map((st) => {
        const name = h("input", { type: "text", value: st.name, "aria-label": `${st.name}: name` });
        name.addEventListener("change", () => { if (name.value.trim()) this.app.renameTextStyle(st.id, name.value.trim()); });
        const using = paras.filter(([p]) => p.style === st.id), objects = new Set(using.map(([, it]) => it.id)).size;
        const changed = using.filter(([p]) => differs(p, st)).length;
        const sample = h("span", { class: "style-sample", style: { fontFamily: `"${st.font || "Helvetica"}"`, fontWeight: st.bold ? "700" : "400",
          fontStyle: st.italic ? "italic" : "normal", color: st.color || "#000000" } }, "Aa");
        return h("li", { class: "swatch-row" }, sample, name,
          h("span", { class: "hint" }, `${describeFormat(st)}; ${objects} text object${objects === 1 ? "" : "s"}`
            + (changed ? `, ${changed} changed` : "")),
          button(`Delete ${st.name} (text keeps its format)`, () => { this.app.deleteTextStyle(st.id); render(); }, "Delete"));
      });
      body.replaceChildren(
        all.length ? h("ul", { class: "swatch-list" }, ...rows)
          : h("p", {}, "No text styles yet. Select some text, then New style from this text on the Text tab."),
        h("p", { class: "hint" }, "Text using a style follows it. To change a style, format one text as you want it and click "
          + "Update the style to match on its Text tab; text you've changed by hand keeps those changes. A style named "
          + "Panel label is used for new panel labels."));
    };
    render();
    this.dialog("Text styles", body);
  },
  // Object styles: rename or delete them, with what each looks like and how many objects use it
  // (changes to a style's look come from an object: "Update the style to match" on its Style tab)
  objectStylesDialog() {
    const body = h("div", {});
    const render = () => {
      const all = store.doc.object_styles || [], objects = styledObjects(store.doc);
      const rows = all.map((st) => {
        const name = h("input", { type: "text", value: st.name, "aria-label": `${st.name}: name` });
        name.addEventListener("change", () => { if (name.value.trim()) this.app.renameObjectStyle(st.id, name.value.trim()); });
        const using = objects.filter((it) => it.object_style === st.id), changed = using.filter((it) => looksDiffer(it, st)).length;
        const line = st.stroke ? { stroke: st.stroke.color || "#000000", "stroke-width": Math.min(Math.max(st.stroke.width ?? 1, 0.5), 4) } : { stroke: "none" };
        const sample = s("svg", { class: "style-sample", width: 30, height: 18, viewBox: "0 0 30 18", "aria-hidden": "true" },
          "fill" in st ? s("rect", { x: 3, y: 3, width: 24, height: 12, fill: st.fill?.color || (st.fill ? "#cccccc" : "none"), ...line })
            : s("line", { x1: 3, y1: 9, x2: 27, y2: 9, ...line }));
        return h("li", { class: "swatch-row" }, sample, name,
          h("span", { class: "hint" }, `${describeLook(st)}; ${using.length} object${using.length === 1 ? "" : "s"}`
            + (changed ? `, ${changed} changed` : "")),
          button(`Delete ${st.name} (objects keep their look)`, () => { this.app.deleteObjectStyle(st.id); render(); }, "Delete"));
      });
      body.replaceChildren(
        all.length ? h("ul", { class: "swatch-list" }, ...rows)
          : h("p", {}, "No object styles yet. Select a line or shape, then New style from this object on its Style tab."),
        h("p", { class: "hint" }, "Objects using a style follow it. To change a style, give one object the look you want and click "
          + "Update the style to match on its Style tab; objects you've changed by hand keep those changes."));
    };
    render();
    this.dialog("Object styles", body);
  },
  // A question with a typed answer (null if cancelled)
  promptDialog(title, labelText, value = "", placeholder = "") {
    return new Promise((resolve) => {
      const id = `prompt-${Date.now()}`;
      const input = h("input", { type: "text", id, value, placeholder, style: { width: "100%" } });
      const ok = h("button", { type: "button", class: "btn primary" }, "OK");
      const dlg = this.dialog(title, h("div", {}, h("label", { for: id }, labelText), input), [ok]);
      let answered = false;
      ok.addEventListener("click", () => { answered = true; resolve(input.value.trim() || null); dlg.close(); });
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); ok.click(); } });
      dlg.addEventListener("close", () => { if (!answered) resolve(null); });
      input.focus();
    });
  },

  // Command search (⌘/): type a few letters to find any command, then Enter runs it
  commandSearch() {
    if (document.querySelector("dialog.command-search")) return;
    const cmds = Object.entries(this.app.commands).filter(([name]) => name !== "commandSearch");
    // A plain text box: in a search box, Escape clears the text instead of closing the dialog
    const input = h("input", { type: "text", class: "cs-input", role: "combobox", "aria-expanded": "true", "aria-controls": "cs-list",
      "aria-autocomplete": "list", "aria-label": "Search commands", placeholder: "Type to find a command…", autocomplete: "off" });
    const list = h("ul", { id: "cs-list", class: "cs-list", role: "listbox", "aria-label": "Commands" });
    const dlg = h("dialog", { class: "dialog command-search", "aria-label": "Search commands" }, input, list);
    let shown = [], at = 0;
    const score = (c, q) => {
      if (!q) return 1;
      const text = `${c.label} ${c.short || ""}`.toLowerCase();
      if (text.split(/[\s:,(]+/).some((w) => w.startsWith(q))) return 3;
      if (text.includes(q)) return 2;
      let i = 0;   // the letters in order, in a button's short name ("rul" for Rulers), not the long ones
      for (const ch of (c.short || "").toLowerCase()) if (ch === q[i]) i++;
      return i === q.length ? 1 : 0;
    };
    const render = () => {
      const q = input.value.trim().toLowerCase();
      shown = cmds.map(([name, c]) => ({ name, c, s: score(c, q) })).filter((x) => x.s > 0)
        .sort((a, b) => b.s - a.s || a.c.label.length - b.c.label.length).slice(0, 40);
      at = Math.min(at, Math.max(shown.length - 1, 0));
      list.replaceChildren(...shown.map((x, i) => {
        const li = h("li", { id: `cs-${i}`, role: "option", class: "cs-item", "aria-selected": i === at ? "true" : "false" },
          h("span", {}, x.c.label), x.c.keys ? h("kbd", {}, x.c.keys) : null);
        li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(i); });
        return li;
      }), ...(shown.length ? [] : [h("li", { class: "cs-empty" }, "No command matches")]));
      input.setAttribute("aria-activedescendant", shown.length ? `cs-${at}` : "");
      list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
    };
    const choose = (i) => {
      const x = shown[i];
      dlg.close();
      if (x) this.app.run(x.name);
    };
    input.addEventListener("input", () => { at = 0; render(); });
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Escape") { e.preventDefault(); dlg.close(); return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        at = (at + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % Math.max(shown.length, 1);
        render();
      } else if (e.key === "Enter") { e.preventDefault(); choose(at); }
    });
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    render();
    input.focus();
  },

  reportDialog(title, lines) {
    this.dialog(title, h("ul", { class: "report" }, ...lines.map((l) => h("li", {}, l))));
  },

  // Choose among cards with a small picture each (a deck's slides; the deck dragged slides came
  // from), drawn one after another. Click picks one, Shift- or ⌘-click (Ctrl-click) several,
  // double-click picks one and goes; the arrow keys move, Space picks, Enter goes. Resolves to
  // the chosen cards' values in their order, or null.
  // {title, hint, label (the list's name), aspect (width / height of the pictures), one (pick
  // just one), all (an All slides button), verb(n) (the go button's words), cards: [{value,
  // label, sub, badge, thumb: () => Promise of a picture's URL}]}
  pickCards(opts) {
    return new Promise((resolve) => {
      const { cards } = opts, id = `pick-${Date.now()}`;
      let chosen = new Set(), focus = 0, anchor = 0, answered = false;
      const grid = h("ul", { class: "slide-grid", role: "listbox", tabindex: 0, "aria-label": opts.label,
        "aria-multiselectable": opts.one ? "false" : "true" });
      const lis = cards.map((c, i) => {
        const li = h("li", { role: "option", id: `${id}-${i}`, "aria-selected": "false" },
          h("span", { class: "slide-thumb-box", style: { aspectRatio: String(opts.aspect || 4 / 3) } },
            h("img", { class: "slide-thumb", alt: "", draggable: "false" })),
          h("span", { class: "slide-label" }, c.label, c.badge ? h("span", { class: "slide-badge" }, c.badge) : null),
          c.sub ? h("span", { class: "slide-sub", title: c.sub }, c.sub) : null);
        li.addEventListener("click", (e) => pick(i, e.shiftKey, e.metaKey || e.ctrlKey));
        li.addEventListener("dblclick", () => { chosen = new Set([i]); go(); });
        return li;
      });
      grid.append(...lis);
      const goBtn = h("button", { type: "button", class: "btn primary" }, opts.verb(0));
      const allBtn = opts.all && !opts.one ? h("button", { type: "button", class: "btn" }, "All slides") : null;
      const dlg = this.dialog(opts.title, h("div", {}, opts.hint ? h("p", { class: "hint" }, opts.hint) : null, grid),
        [allBtn, goBtn].filter(Boolean));
      dlg.classList.add("picker-dialog");
      const render = () => {
        lis.forEach((li, i) => {
          li.setAttribute("aria-selected", chosen.has(i) ? "true" : "false");
          li.classList.toggle("chosen", chosen.has(i));
          li.classList.toggle("focused", i === focus);
        });
        grid.setAttribute("aria-activedescendant", `${id}-${focus}`);
        goBtn.disabled = !chosen.size;
        goBtn.textContent = opts.verb(chosen.size);
      };
      const pick = (i, range, toggle) => {
        if (opts.one || (!range && !toggle)) chosen = new Set([i]);
        else if (range) {
          const [a, b] = [Math.min(anchor, i), Math.max(anchor, i)];
          if (!toggle) chosen = new Set();
          for (let k = a; k <= b; k++) chosen.add(k);
        } else if (chosen.has(i)) chosen.delete(i);
        else chosen.add(i);
        if (!range) anchor = i;
        focus = i;
        render();
        lis[i].scrollIntoView({ block: "nearest" });
      };
      const go = () => {
        if (!chosen.size) return;
        answered = true;
        resolve([...chosen].sort((a, b) => a - b).map((i) => cards[i].value));
        dlg.close();
      };
      grid.addEventListener("keydown", (e) => {
        const top = lis[0].offsetTop, cols = Math.max(1, lis.filter((li) => li.offsetTop === top).length);
        const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols }[e.key];
        const mod = e.metaKey || e.ctrlKey;
        if (step !== undefined || e.key === "Home" || e.key === "End") {
          e.preventDefault();
          const next = e.key === "Home" ? 0 : e.key === "End" ? cards.length - 1 : Math.min(Math.max(focus + step, 0), cards.length - 1);
          if (mod && !e.shiftKey) { focus = next; render(); lis[next].scrollIntoView({ block: "nearest" }); }   // ⌘ (Ctrl) + arrow: move without picking
          else pick(next, e.shiftKey, false);
        } else if (e.key === " ") {
          e.preventDefault();
          pick(focus, false, !opts.one);
        } else if (e.key === "Enter") {
          e.preventDefault();
          if (!chosen.size) chosen.add(focus);
          go();
        } else if (mod && e.key.toLowerCase() === "a" && !opts.one) {
          e.preventDefault();
          chosen = new Set(cards.map((_, i) => i));
          render();
        }
      });
      goBtn.addEventListener("click", go);
      allBtn?.addEventListener("click", () => { chosen = new Set(cards.map((_, i) => i)); render(); goBtn.focus(); });
      // Cancel, Escape or closing: nothing chosen (as soon as asked, not when the dialog's gone)
      const cancel = () => { if (!answered) { answered = true; resolve(null); } };
      dlg.querySelector("button[value=close]").addEventListener("click", cancel);
      dlg.addEventListener("cancel", cancel);
      dlg.addEventListener("close", cancel);
      render();
      grid.focus();
      // The pictures, one after another, while the dialog is open
      (async () => {
        for (let i = 0; i < cards.length && dlg.open; i++) {
          try {
            lis[i].querySelector("img").src = await cards[i].thumb();
            lis[i].classList.add("drawn");
          } catch { lis[i].classList.add("failed"); }
        }
      })();
    });
  },

  // A deck's slides to choose from (deck_slides): the chosen slide numbers, or null.
  // how: {verb: "Open" | "Add" | ..., where: words for where they'll go, e.g. "as pages after page 2"}
  slidePicker(deck, how) {
    const n = deck.slides.length;
    return this.pickCards({
      title: `${how.verb} slides from “${deck.name}”`,
      hint: `${n} slides${how.where ? `, to go ${how.where}` : ""}. Click a slide to choose it; Shift- or ${isMac ? "⌘" : "Ctrl"}-click to `
        + "choose several; double-click one to take just that slide.",
      label: `Slides in ${deck.name}`, aspect: deck.width / deck.height, all: true,
      verb: (k) => (k ? `${how.verb} ${k === n && n > 1 ? "all " : ""}${k} slide${k === 1 ? "" : "s"}` : how.verb),
      cards: deck.slides.map((s) => ({ value: s.n, label: `Slide ${s.n}`, sub: s.title, badge: s.hidden ? "Hidden" : "",
        thumb: () => rpc("deck_thumbnail", deck.key, s.n) })),
    });
  },

  pathDialog(title, placeholder, recent = []) {
    return new Promise((resolve) => {
      const input = h("input", { type: "text", id: "path-input", placeholder, style: { width: "100%" } });
      const ok = h("button", { type: "button", class: "btn primary" }, "OK");
      const dlg = this.dialog(title, h("div", {},
        h("label", { for: "path-input" }, "File path"), input,
        recent.length ? h("ul", { class: "recent" }, ...recent.map((r) => h("li", {}, button(`Open ${r}`, () => { input.value = r; }, r, "link")))) : null), [ok]);
      ok.addEventListener("click", () => { resolve(input.value.trim() || null); dlg.close(); });
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); ok.click(); } });
      dlg.addEventListener("close", () => resolve(null));
      input.focus();
    });
  },
};

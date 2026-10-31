// Toolbar, pages and objects lists, status bar and dialogs.

import { rpc } from "./api.js";
import { canvas } from "./canvas.js";
import { alignToField, button, gapField, numField, selectField } from "./inspector.js";
import { store } from "./store.js";
import { contextMenu } from "./contextmenu.js";
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
  gear: "M12 9a3 3 0 110 6 3 3 0 010-6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
  help: "M12 3a9 9 0 110 18 9 9 0 010-18zM9.5 9.5a2.5 2.5 0 015 0c0 2-2.5 2-2.5 4M12 17h.01",
  plus: "M12 5v14M5 12h14", duplicate: "M8 8h11v11H8zM5 5h11v3M5 5v11h3", trash: "M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13",
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
  ruler: "M3 8h18v8H3zM7 8v3M11 8v4.5M15 8v3M19 8v4.5", grid: "M4 4h16v16H4zM9.33 4v16M14.67 4v16M4 9.33h16M4 14.67h16",
  guides: "M9 8v13M8 15h13M6.5 3h5L9 6zM3 12.5v5l3-2.5z",
  magnet: "M5 4h4.5v7.5a2.5 2.5 0 005 0V4H19v7.5a7 7 0 01-14 0zM5 8h4.5M14.5 8H19",
};

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
    document.addEventListener("fa-prefs", () => this.renderToggles());
    document.addEventListener("fa-zoom", (e) => {
      for (const z of document.querySelectorAll(".zoom-label")) z.textContent = `${fmt(e.detail * 100, 0)}%`;
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
        group("Clipboard", t("cut", "cut"), t("copy", "copy"), t("paste", "paste")),
        group("Objects", t("duplicate", "duplicate"), t("delete", "trash")),
        group("Page", t("addPage", "plus"), t("fitPage", "fit")),
      ]],
      ["arrange", "Arrange", this.arrangeGroups(group, t)],
      ["view", "View", [
        group("Zoom", t("zoomOut", "zoomout"), h("span", { class: "zoom-label", "aria-live": "off" }, "100%"),
          t("zoomIn", "zoomin"), t("zoomFit", "fit"), t("zoom100", "actual")),
        group("Show", this.toggleButton("toggleRulers", "ruler", "show_rulers"),
          this.toggleButton("toggleGrid", "grid", "show_grid", ". Things snap to it while it shows"),
          this.toggleButton("toggleGuides", "guides", "show_guides", ". Drag a new one out of a ruler")),
        group("Grid", t("gridSettings", "gear")),
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
      group("Group", t("group", "group"), t("ungroup", "ungroup")),
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
      t("toolLine", "line", "line"), t("toolArrow", "arrow", "arrow"), sep(),
      t("toolRect", "rect", "rect"), t("toolRoundRect", "roundrect", "roundrect"), t("toolEllipse", "ellipse", "ellipse"),
      t("toolTriangle", "triangle", "triangle"), t("toolArc", "arc", "arc"), t("toolBracket", "bracket", "bracket"),
      this.shapeMenuButton(), sep(), t("insertPicture", "picture"));
    box.querySelector("button.tool").tabIndex = 0;
    roving(box, "button.tool", true);
    this.renderTools("select");
  },
  renderTools(tool) {
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
  },
  renderPages() {
    if (!store.doc) return;
    const pu = this.app.prefs.page_units || "mm";
    this.pageList.replaceChildren(...store.doc.pages.map((p, i) => {
      const li = h("li", { role: "option", id: `page-opt-${i}`, "aria-selected": i === store.pageIndex ? "true" : "false",
        class: i === store.pageIndex ? "current" : "", draggable: "true", "data-index": i },
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
      li.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/x-fa-page", String(i)); });
      li.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("text/x-fa-page")) e.preventDefault(); });
      li.addEventListener("drop", (e) => {
        const from = Number(e.dataTransfer.getData("text/x-fa-page"));
        if (Number.isNaN(from) || e.dataTransfer.files.length) return;
        e.preventDefault();
        e.stopPropagation();
        this.app.movePage(from, i);
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

  buildLayers() {
    const root = document.getElementById("layers");
    this.layerList = h("ul", { class: "layer-list", role: "listbox", "aria-label": "Objects on this page, front to back",
      "aria-multiselectable": "true", tabindex: 0 });
    root.append(h("div", { class: "panel-head" }, h("h2", {}, "Objects"),
      h("span", { class: "hint" }, "front to back")), this.layerList);
    this.layerList.addEventListener("keydown", (e) => {
      const items = store.items();
      if (!items.length) return;
      const order = [...items].reverse();
      const cur = order.findIndex((it) => store.selection.includes(it.id));
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const d = e.key === "ArrowDown" ? 1 : -1;
        if (e.altKey && cur >= 0) { this.app.run(d > 0 ? "sendBackward" : "bringForward"); return; }
        const j = Math.min(Math.max((cur < 0 ? -1 : cur) + d, 0), order.length - 1);
        store.select([order[j].id]);
        announce(itemLabel(order[j], store.doc));
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        this.app.run("delete");
      }
    });
  },
  renderLayers() {
    if (!store.doc) return;
    const order = [...store.items()].reverse();
    if (!order.length) {
      this.layerList.replaceChildren(h("li", { class: "empty" }, "Nothing on this page yet."));
      return;
    }
    this.layerList.replaceChildren(...order.map((it) => {
      const selected = store.selection.includes(it.id);
      const li = h("li", { role: "option", id: `layer-opt-${it.id}`, "aria-selected": selected ? "true" : "false",
        class: selected ? "selected" : "" },
        h("span", { class: "layer-name" }, itemLabel(it, store.doc)),
        button(it.hidden ? "Show" : "Hide", (e) => {
          e.stopPropagation();
          store.update(it.hidden ? "Show" : "Hide", (d) => { d.pages[store.pageIndex].items.find((x) => x.id === it.id).hidden = !it.hidden; });
        }, icon(it.hidden ? "eyeoff" : "eye"), "icon-btn small"),
        button(it.locked ? "Unlock" : "Lock", (e) => {
          e.stopPropagation();
          store.update(it.locked ? "Unlock" : "Lock", (d) => { d.pages[store.pageIndex].items.find((x) => x.id === it.id).locked = !it.locked; });
        }, icon(it.locked ? "lock" : "unlock"), "icon-btn small"));
      li.addEventListener("click", (e) => {
        // (On a Mac, Control-click is a right-click)
        if (e.shiftKey || e.metaKey || (e.ctrlKey && !isMac)) {
          store.select(selected ? store.selection.filter((x) => x !== it.id) : [...store.selection, it.id]);
        } else store.select([it.id]);
      });
      li.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        if (!store.selection.includes(it.id)) store.select([it.id]);
        this.app.objectListMenu(e.clientX, e.clientY);
      });
      return li;
    }));
    const active = store.selection[store.selection.length - 1];
    if (active) this.layerList.setAttribute("aria-activedescendant", `layer-opt-${active}`);
    else this.layerList.removeAttribute("aria-activedescendant");
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
      h("span", { class: "zoom-label", "aria-live": "off" }, "100%"), z("zoomIn", "zoomin"), z("zoomFit", "fit"));
    bar.append(this.message, h("span", { class: "spacer" }), zoom, this.cursor, this.saveState);
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
        check("png", "PNG"), check("tiff", "TIFF", "LZW-compressed")),
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

  async preflightDialog() {
    const body = h("div", {}, h("p", {}, "Checking…"));
    this.dialog("Check before export", body);
    try {
      const res = await rpc("preflight", store.doc, { pages: [store.pageIndex] });
      const items = res.items;
      const summary = res.summary.smallest_text_pt ? `Smallest text on this page: ${res.summary.smallest_text_pt} pt.` : "";
      body.replaceChildren(
        h("p", {}, summary),
        items.length ? h("ul", { class: "preflight" }, ...items.map((f) => {
          const li = h("li", { class: f.level },
            h("span", { class: "level" }, { warning: "⚠ Check", info: "ℹ Note", ok: "✓ OK" }[f.level] || f.level), " ", f.message);
          if (f.item) {
            li.append(" ", button("Select this object", () => { store.select([f.item]); }, "Select"));
          }
          return li;
        })) : h("p", {}, "✓ Nothing to flag on this page."),
        h("p", { class: "hint" }, "Fonts missing from placed PDFs are embedded automatically when you export."));
    } catch (err) {
      body.replaceChildren(h("p", { class: "error" }, err.message));
    }
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
        h("li", {}, "Arrow keys: move by 1 pt; with Shift by 10 pt; with Option/Alt by 0.1 pt"),
        h("li", {}, "Option/Alt+Shift+arrows: make the object 1 pt wider, narrower, taller or shorter"),
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
        h("li", {}, "Space + drag, or scroll: move around; ⌘/Ctrl + scroll or pinch: zoom"))));
  },

  reportDialog(title, lines) {
    this.dialog(title, h("ul", { class: "report" }, ...lines.map((l) => h("li", {}, l))));
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

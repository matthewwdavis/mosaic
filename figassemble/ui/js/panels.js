// Toolbar, pages and objects lists, status bar and dialogs.

import { rpc } from "./api.js";
import { canvas } from "./canvas.js";
import { button, numField, selectField } from "./inspector.js";
import { store } from "./store.js";
import { UNIT_LABEL, announce, fmt, h, itemLabel, shapeName, toUnit } from "./util.js";

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
    this.buildToolbar();
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
    document.addEventListener("fa-zoom", (e) => { this.zoomLabel.textContent = `${fmt(e.detail * 100, 0)}%`; });
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

  // View menu: show or hide the rulers, grid and guides ------------------------------------

  viewMenuButton() {
    const btn = h("button", { type: "button", class: "tool", id: "view-button", title: "Rulers, grid and guides",
      "aria-label": "View", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "view-menu", tabindex: -1 },
    icon("ruler"), h("span", { class: "tool-label" }, "View ▾"));
    const items = [["toggleRulers", "show_rulers"], ["toggleGrid", "show_grid"], ["toggleGuides", "show_guides"]].map(([cmd, pref]) => {
      const c = this.app.commands[cmd];
      const item = h("button", { type: "button", class: "menu-item", role: "menuitemcheckbox", tabindex: -1, "data-pref": pref,
        "aria-checked": this.app.prefs[pref] ? "true" : "false" },
      h("span", { class: "check", "aria-hidden": "true" }, "✓"), h("span", {}, c.short),
      h("kbd", { "aria-hidden": "true" }, c.keys));
      item.addEventListener("click", () => { this.closeViewMenu(); this.app.run(cmd); });
      return item;
    });
    const settings = h("button", { type: "button", class: "menu-item", role: "menuitem", tabindex: -1 },
      h("span", { class: "check", "aria-hidden": "true" }), h("span", {}, "Grid spacing and snapping…"));
    settings.addEventListener("click", () => { this.closeViewMenu(false); this.preferencesDialog(); });
    const menu = h("div", { id: "view-menu", class: "popup-menu", role: "menu", "aria-label": "View", hidden: true },
      ...items, h("div", { class: "menu-sep", role: "separator" }), settings);
    btn.addEventListener("click", () => (menu.hidden ? this.openViewMenu() : this.closeViewMenu()));
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); this.openViewMenu(); }
    });
    // Up and down move through the items, Enter or Space chooses (they're buttons), Escape closes
    menu.addEventListener("keydown", (e) => {
      e.stopPropagation();
      const list = [...menu.querySelectorAll(".menu-item")];
      const i = list.indexOf(document.activeElement);
      const go = (j) => { e.preventDefault(); list[(j + list.length) % list.length].focus(); };
      if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); this.closeViewMenu(); }
      else if (e.key === "ArrowDown") go(i + 1);
      else if (e.key === "ArrowUp") go(i - 1);
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(list.length - 1);
    });
    document.body.append(menu);
    document.addEventListener("pointerdown", (e) => {
      if (!menu.hidden && !menu.contains(e.target) && !btn.contains(e.target)) this.closeViewMenu(false);
    }, true);
    this.viewBtn = btn;
    this.viewMenu = menu;
    return btn;
  },
  openViewMenu() {
    const r = this.viewBtn.getBoundingClientRect(), m = this.viewMenu;
    m.hidden = false;
    this.viewBtn.setAttribute("aria-expanded", "true");
    m.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - m.offsetWidth - 8))}px`;
    m.style.top = `${r.bottom + 4}px`;
    m.querySelector(".menu-item")?.focus();
  },
  closeViewMenu(refocus = true) {
    if (this.viewMenu.hidden) return;
    this.viewMenu.hidden = true;
    this.viewBtn.setAttribute("aria-expanded", "false");
    if (refocus) this.viewBtn.focus();
  },
  buildToolbar() {
    const bar = document.getElementById("toolbar");
    const t = (cmd, ic, tool) => this.toolButton(cmd, ic, { tool });
    const group = (label, ...btns) => h("div", { class: "tool-group", role: "group", "aria-label": label }, ...btns);
    this.zoomLabel = h("span", { class: "zoom-label", "aria-live": "off" }, "100%");
    bar.append(
      group("File", t("new", "new"), t("open", "open"), t("save", "save")),
      group("Tools", t("toolSelect", "select", "select"), t("toolText", "text", "text"), t("toolLabel", "label", "label"),
        t("toolLine", "line", "line"), t("toolArrow", "arrow", "arrow"), t("toolRect", "rect", "rect"),
        t("toolRoundRect", "roundrect", "roundrect"), t("toolEllipse", "ellipse", "ellipse"),
        t("toolTriangle", "triangle", "triangle"), t("toolArc", "arc", "arc"), t("toolBracket", "bracket", "bracket"),
        this.shapeMenuButton(), t("insertPicture", "picture")),
      group("Edit", t("undo", "undo"), t("redo", "redo")),
      group("Zoom", t("zoomOut", "zoomout"), this.zoomLabel, t("zoomIn", "zoomin"), t("zoomFit", "fit")),
      group("Layout aids", this.viewMenuButton(),
        this.toggleButton("toggleSnap", "magnet", "snap", `. Hold ${this.app.mod.replace("+", "")} while dragging to ignore it once`)),
      h("div", { class: "spacer" }),
      group("Finish", t("preflight", "check"), this.toolButton("export", "export", { primary: true })),
      group("App", t("preferences", "gear"), t("shortcuts", "help")),
    );
    const first = bar.querySelector("button.tool");
    if (first) first.tabIndex = 0;
    roving(bar, "button.tool");
    this.renderTools("select");
  },
  renderTools(tool) {
    for (const b of document.querySelectorAll("#toolbar [data-tool]")) {
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
    icon("shapes"), h("span", { class: "tool-label" }, `${c.short} ▾`));
    btn.addEventListener("click", () => this.toggleShapeMenu());
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); this.openShapeMenu(); }
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
    m.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - m.offsetWidth - 8))}px`;
    m.style.top = `${r.bottom + 4}px`;
    m.style.maxHeight = `${Math.max(window.innerHeight - r.bottom - 16, 160)}px`;
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
      e.stopPropagation();
      if (e.key === "Enter") done(true);
      if (e.key === "Escape") done(false);
    });
    input.addEventListener("blur", () => done(true), { once: true });
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
        if (e.shiftKey || e.metaKey || e.ctrlKey) {
          store.select(selected ? store.selection.filter((x) => x !== it.id) : [...store.selection, it.id]);
        } else store.select([it.id]);
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
    bar.append(this.message, h("span", { class: "spacer" }), this.cursor, this.saveState);
  },
  renderSaveState() {
    if (!store.doc) return;
    const name = store.path ? store.path.split(/[\\/]/).pop() : "Not saved yet";
    this.saveState.textContent = `${name}${store.dirty ? " — unsaved changes" : store.path ? " — saved" : ""}`;
  },

  // Dialogs ------------------------------------------------------------------------------

  dialog(title, body, actions = []) {
    const id = `dlg-${Date.now()}`;
    const dlg = h("dialog", { class: "dialog", "aria-labelledby": id },
      h("form", { method: "dialog" },
        h("h2", { id }, title),
        h("div", { class: "dialog-body" }, body),
        h("div", { class: "dialog-actions" }, ...actions,
          h("button", { type: "submit", class: "btn", value: "close" }, actions.length ? "Cancel" : "Close"))));
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
      h("fieldset", {}, h("legend", {}, "Interface"),
        h("div", { class: "field" }, h("label", { for: "pref-scale" }, "Interface text size"), scale),
        selectField("Appearance", p.theme || "system", [["system", "Match the system"], ["light", "Light"], ["dark", "Dark"],
          ["contrast", "High contrast"]], set("theme")),
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
      h("fieldset", {}, h("legend", {}, "New objects"),
        numField("Default text size", p.text?.size || 6, "pt", (v) => this.app.savePrefs({ text: { ...(p.text || {}), size: v } }), { step: 0.5 }),
        numField("Default line width", p.stroke_width || 1, "pt", set("stroke_width"), { step: 0.25 }),
        numField("Panel label size", label.size || 8, "pt", (v) => this.app.savePrefs({ panel_label: { ...label, size: v } }), { step: 0.5 }),
        selectField("Panel labels", label.case || "lower", [["lower", "a, b, c"], ["upper", "A, B, C"]],
          (v) => this.app.savePrefs({ panel_label: { ...label, case: v } }))),
    ));
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

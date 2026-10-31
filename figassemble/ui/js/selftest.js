// Scripted run-through of the editor, loaded only with ?selftest=1 (used by tools/ui_selftest.py).
// Drives the real UI through pointer and keyboard events and reports through console.log.

import { rpc } from "./api.js";
import { canvas } from "./canvas.js";
import { inspector } from "./inspector.js";
import { store } from "./store.js";
import { lengthText, lineMidpoints } from "./util.js";

const MMPT = 72 / 25.4;
const near = (a, b, tol = 0.05) => Math.abs(a - b) < tol;
// Set a properties-panel dropdown by its label, as a person would
async function choose(label, value) {
  inspector.render();
  const l = [...document.querySelectorAll("#inspector label")].find((x) => x.textContent === label);
  const field = l && document.getElementById(l.htmlFor);
  if (!field) return false;
  field.value = value;
  field.dispatchEvent(new Event("change", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 60));
  return true;
}
const findItem = (doc, id) => doc.pages[store.pageIndex].items.find((i) => i.id === id);
const pageSize = () => `${(store.page().width / MMPT).toFixed(1)} × ${(store.page().height / MMPT).toFixed(1)} mm`;
function fieldByLabel(text) {
  inspector.render();
  const l = [...document.querySelectorAll("#inspector label")].find((x) => x.textContent === text);
  return l ? document.getElementById(l.htmlFor) : null;
}

const results = [];
const info = {};
const log = (ok, name, detail = "") => {
  results.push(ok ? { ok, name } : { ok, name, detail });
  console.log(`SELFTEST ${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};
const check = (cond, name, detail) => log(!!cond, name, cond ? "" : detail);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (cond, ms = 2000) => { for (let t = 0; t < ms && !cond(); t += 20) await wait(20); return cond(); };
const settle = async () => { await wait(60); await canvas.resolveNow(); await wait(60); };

function screenOf(px, py) {
  const r = canvas.stage.getBoundingClientRect();
  const [x, y] = canvas.toScreen(px, py);
  return [x + r.left, y + r.top];
}
function pointer(type, [x, y], opts = {}) {
  canvas.stage.dispatchEvent(new PointerEvent(type, { clientX: x, clientY: y, bubbles: true, button: 0, buttons: 1,
    pointerId: 1, pointerType: "mouse", ...opts }));
}
async function drag(fromPage, toPage, opts = {}, steps = 6) {
  const a = screenOf(...fromPage), b = screenOf(...toPage);
  pointer("pointerdown", a, opts);
  for (let i = 1; i <= steps; i++) pointer("pointermove", [a[0] + ((b[0] - a[0]) * i) / steps, a[1] + ((b[1] - a[1]) * i) / steps], opts);
  pointer("pointerup", b, opts);
  await settle();
}
function key(k, opts = {}) {
  canvas.stage.focus();
  canvas.stage.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...opts }));
}

export async function run(app, params) {
  let keepAids = false;
  const files = (params.get("files") || "").split(",").filter(Boolean);
  const out = params.get("out");
  app.autoConfirm = true;
  for (const dlg of document.querySelectorAll("dialog[open]")) dlg.close();   // e.g. a recovery offer
  try {
    // Start from the default layout aids, whatever an earlier run left switched on
    await app.savePrefs({ show_rulers: true, show_grid: false, show_guides: true, snap: true });
    store.setDoc(await rpc("new_document"));
    canvas.fit();
    await settle();
    check(store.items().length === 0, "new document is empty");
    // In a 1440 px window (the app's own size) each ribbon tab is one row, the drawing tools fit
    // down the side without scrolling, and nothing spills off the window
    const ribbonTabs = [...document.querySelectorAll(".rtab")];
    const openTab = ribbonTabs.find((t) => t.getAttribute("aria-selected") === "true");
    const tabRows = ribbonTabs.map((tab) => {
      tab.click();
      const groups = [...document.getElementById(tab.getAttribute("aria-controls")).children];
      info[`room${tab.textContent}`] = Math.round(groups[0].parentElement.clientWidth
        - groups.reduce((n, g) => n + g.getBoundingClientRect().width, 0));   // px left over
      return new Set(groups.map((g) => Math.round(g.getBoundingClientRect().top))).size;
    });
    openTab.click();
    const toolbox = document.getElementById("toolbox");
    check(ribbonTabs.length === 3 && tabRows.every((n) => n === 1) && toolbox.scrollHeight <= toolbox.clientHeight + 1
      && document.body.scrollWidth <= window.innerWidth + 1, "each ribbon tab fits on one row and the tools fit down the side",
    `rows ${tabRows}; tools ${toolbox.scrollHeight}/${toolbox.clientHeight}; width ${document.body.scrollWidth}`);
    check(near(store.page().width, 210 * MMPT) && near(store.page().height, 297 * MMPT), "new pages are A4", pageSize());
    canvas.setZoom(1);
    check(document.querySelector(".zoom-label")?.textContent === "100%", "zoom readout shows 100% at true size",
      document.querySelector(".zoom-label")?.textContent);
    canvas.fit();

    // Placing files keeps them linked and finds their other copies
    const placed = await rpc("add_files", files, false);
    app.placeResults(placed, [20, 20], "linked");
    await settle();
    const pics = store.items().filter((i) => i.type === "picture");
    check(pics.length === files.length, "files placed as pictures", `${pics.length} of ${files.length}`);
    const a0 = store.doc.assets[pics[0].asset];
    check(a0.variants.pdf && a0.variants.svg, "plot has PDF and SVG copies", Object.keys(a0.variants).join("+"));
    check(Math.abs(pics[0].frame[2] - a0.size_pt[0]) < 1e-6, "placed at true size");
    const img = canvas.els.get(pics[0].id)?.g.querySelector("image");
    check(img && img.getAttribute("href").includes("/asset/"), "picture preview rendered");
    store.select([pics[0].id]);
    inspector.render();
    const units = [...document.querySelectorAll("#inspector .unit")].map((u) => u.textContent);
    check(units.includes("cm") && !units.includes("pt"), "a picture's position and size show in centimetres", units.join(","));
    // Keep the pictures apart so pointer tests hit the one intended
    if (pics[1]) store.update("Arrange for test", (doc) => {
      const it = doc.pages[0].items.find((i) => i.id === pics[1].id);
      it.frame = [20, 250, it.frame[2], it.frame[3]];
    });

    // Drawing tools
    canvas.setTool("rect");
    await drag([300, 300], [360, 340], { metaKey: true, ctrlKey: true });   // ⌘: no snapping
    const rect = store.items().find((i) => i.geom === "rect");
    check(rect && Math.abs(rect.frame[2] - 60) < 0.6 && Math.abs(rect.frame[3] - 40) < 0.6, "rectangle drawn by dragging", JSON.stringify(rect?.frame));
    check(canvas.els.get(rect?.id)?.g.querySelector("path"), "rectangle drawn by the engine");
    canvas.setTool("arrow");
    await drag([300, 380], [400, 380], { metaKey: true, ctrlKey: true });
    const arrow = store.items().find((i) => i.type === "line");
    check(arrow?.arrow_end?.type === "triangle", "arrow drawn with a head");

    // Curving it: drag the hollow handle halfway along the arrow
    store.select([arrow.id]);
    const [ea, eb] = store.item(arrow.id).points.map((p) => p.slice());
    const mid = [(ea[0] + eb[0]) / 2, (ea[1] + eb[1]) / 2];
    await drag(mid, [mid[0], mid[1] - 30], { metaKey: true, ctrlKey: true });
    let bent = store.item(arrow.id);
    check(bent.points.length === 3 && bent.curve === "smooth" && Math.abs(bent.points[1][1] - (mid[1] - 30)) < 0.6,
      "dragging the middle handle bends the arrow into a curve", JSON.stringify(bent.points));
    const d = canvas.els.get(arrow.id)?.g.querySelector("path")?.getAttribute("d") || "";
    check(d.includes("C"), "the engine draws it as a curve", d.slice(0, 60));
    await drag(bent.points[1], [bent.points[1][0] + 10, bent.points[1][1] - 10], { metaKey: true, ctrlKey: true });
    bent = store.item(arrow.id);
    check(Math.abs(bent.points[1][0] - (mid[0] + 10)) < 0.6 && bent.points.length === 3, "the bend point follows the pointer");
    const m2 = lineMidpoints(bent)[1].at;
    await drag(m2, [m2[0] + 5, m2[1] + 20], { metaKey: true, ctrlKey: true });
    check(store.item(arrow.id).points.length === 4, "another hollow handle adds a second point (S-curve)");
    const rp = store.item(arrow.id).points[2];
    const [sx, sy] = screenOf(...rp);
    canvas.stage.dispatchEvent(new MouseEvent("dblclick", { clientX: sx, clientY: sy, bubbles: true }));
    await settle();
    check(store.item(arrow.id).points.length === 3, "double-clicking a point removes it");
    await app.run("straighten");
    check(store.item(arrow.id).points.length === 2, "Make straight removes the middle points");

    // A PowerPoint-style arc becomes a curve with points
    canvas.setTool("arc");
    await drag([420, 300], [480, 360], { metaKey: true, ctrlKey: true });
    const arcItem = store.items().find((i) => i.geom === "arc");
    store.select([arcItem.id]);
    await app.run("shapeToCurve");
    const conv = store.item(arcItem.id);
    check(conv?.type === "line" && conv.curve === "smooth" && conv.points.length === 3,
      "an arc turns into an editable curve", JSON.stringify(conv?.points));

    // The Shapes menu: open it from the toolbar, find the 5-point star by typing, choose it with Enter
    const shapesBtn = document.getElementById("shapes-button");
    const menu = document.getElementById("shape-menu");
    const menuKey = (k) => document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
    shapesBtn.click();
    const menuItems = menu.querySelectorAll('[role="menuitem"]');
    check(!menu.hidden && shapesBtn.getAttribute("aria-expanded") === "true" && menuItems.length >= 80,
      "the Shapes button opens a menu of every shape", `${menuItems.length} shapes, hidden=${menu.hidden}`);
    check(document.activeElement?.getAttribute("role") === "menuitem", "the menu takes the keyboard focus",
      document.activeElement?.outerHTML?.slice(0, 80));
    menuKey("Escape");
    check(menu.hidden && document.activeElement === shapesBtn, "Escape closes the menu and returns to its button");
    shapesBtn.click();
    menuKey("ArrowDown");
    check(document.activeElement?.dataset.geom && document.activeElement.dataset.geom !== "rect",
      "arrow keys move through the grid", document.activeElement?.dataset.geom);
    for (const k of ["5", "-"]) menuKey(k);
    check(document.activeElement?.dataset.geom === "star5", "typing a name jumps to that shape", document.activeElement?.dataset.geom);
    menuKey("Enter");
    check(menu.hidden && canvas.tool === "shape" && canvas.shapeGeom === "star5", "Enter makes it the drawing tool",
      `${canvas.tool} ${canvas.shapeGeom}`);
    await drag([100, 430], [160, 490], { metaKey: true, ctrlKey: true });
    const star = store.items().find((i) => i.geom === "star5");
    check(star && near(star.frame[2], 60, 0.6) && near(star.frame[3], 60, 0.6), "the star is drawn by dragging", JSON.stringify(star?.frame));
    check((canvas.els.get(star?.id)?.g.querySelector("path")?.getAttribute("d") || "").split("L").length === 10,
      "the engine draws its ten corners");

    // Its yellow handle sets the inner radius, in one undo step
    const hd = star && canvas.handlesFor(store.item(star.id)).find((x) => x.kind === "adjust");
    check(hd, "the star has a yellow adjust handle");
    if (hd) {
      const hp = canvas.toPage(...hd.at);
      await drag(hp, [hp[0], hp[1] + 8], { metaKey: true, ctrlKey: true });
      await wait(150);
      await settle();
      const inner = store.item(star.id).adj?.adj;
      check(inner > 0.05 && inner < 0.15, "dragging the handle towards the centre makes the star thinner", String(inner));
      app.run("undo");
      check(store.item(star.id).adj?.adj === undefined, "one undo puts the handle back", JSON.stringify(store.item(star.id).adj));
      // Each step of a handle drag is one request that brings back the shape already drawn (the
      // time per step is reported, not checked; it's only real in the app's own window)
      const h2 = canvas.handlesFor(store.item(star.id)).find((x) => x.kind === "adjust");
      const from = canvas.toPage(...h2.at), st = store.item(star.id);
      let t0 = performance.now();
      for (let k = 1; k <= 10; k++) await rpc("adjust_shape", canvas.assetSizes(), st, 0, [st.frame[2] / 2, k]);
      info.handleStepMs = Math.round((performance.now() - t0) * 10) / 100;
      t0 = performance.now();
      for (let k = 1; k <= 10; k++) {   // the two requests each step used to make
        const adj = await rpc("drag_handle", st, 0, [st.frame[2] / 2, k]);
        await rpc("resolve", canvas.assetSizes(), [{ ...st, adj }]);
      }
      info.handleStepBeforeMs = Math.round((performance.now() - t0) * 10) / 100;
      pointer("pointerdown", screenOf(...from), { metaKey: true, ctrlKey: true });
      for (let k = 1; k <= 10; k++) {
        pointer("pointermove", screenOf(from[0], from[1] + k * 0.8), { metaKey: true, ctrlKey: true });
        await until(() => !canvas.op?.busy, 2000);
      }
      pointer("pointerup", screenOf(from[0], from[1] + 8), { metaKey: true, ctrlKey: true });
      await settle();
      check(store.item(star.id).adj?.adj < 0.15 && canvas.els.get(star.id)?.geomKey === canvas.geomKey(store.item(star.id))[0],
        "a handle drag draws each step as it goes", `${JSON.stringify(store.item(star.id).adj)} ${info.handleStepMs} ms`);
      app.run("undo");
    }

    // Enter with a drawing tool places a 2 cm shape in the middle of the view, no pointer needed
    canvas.setTool("shape", "rightArrow");
    key("Enter");
    await settle();
    const centred = store.items().find((i) => i.geom === "rightArrow");
    check(centred && near(centred.frame[2], (2 * 72) / 2.54, 0.01) && canvas.tool === "select",
      "Enter places a 2 cm shape and goes back to selecting", JSON.stringify(centred?.frame));
    if (centred) { store.select([centred.id]); key("Delete"); }

    // Corner rounding on a triangle, and an adjustment typed beyond its range
    canvas.setTool("triangle");
    await drag([200, 430], [260, 490], { metaKey: true, ctrlKey: true });
    const tri = store.items().find((i) => i.geom === "triangle");
    await choose("Corner rounding", "30");
    await settle();
    const triD = canvas.els.get(tri?.id)?.g.querySelector("path")?.getAttribute("d") || "";
    check(store.item(tri.id).rounding === 0.3 && triD.includes("C"), "Corner rounding rounds a triangle's corners",
      `${store.item(tri.id).rounding} ${triD.slice(0, 60)}`);
    await choose("Apex position", "150");
    await wait(150);
    check(store.item(tri.id).adj?.adj === 1, "an adjustment is kept inside its range", JSON.stringify(store.item(tri.id).adj));

    // Rounded arrowheads
    store.select([arrow.id]);
    await choose("End rounding", "50");
    await settle();
    const headD = [...(canvas.els.get(arrow.id)?.g.querySelectorAll("path") || [])].pop()?.getAttribute("d") || "";
    check(store.item(arrow.id).arrow_end.rounding === 0.5 && headD.includes("C"), "an arrowhead's point can be rounded",
      `${JSON.stringify(store.item(arrow.id).arrow_end)} ${headD.slice(0, 60)}`);
    canvas.setTool("label");
    await drag([5, 5], [5, 5]);
    const label = store.items().find((i) => i.text?.paragraphs?.[0]?.runs?.[0]?.t === "a");
    check(label && label.text.paragraphs[0].runs[0].bold, "panel label 'a' added in bold");
    canvas.setTool("label");
    await drag([5, 200], [5, 200]);
    check(store.items().some((i) => i.text?.paragraphs?.[0]?.runs?.[0]?.t === "b"), "next panel label is 'b'");
    await settle();
    check(label && label.frame[3] > 5 && label.frame[3] < 15, "label box fitted to its text", JSON.stringify(label?.frame));

    // Moving with the pointer, then undo and redo
    store.select([pics[0].id]);
    const before = pics[0].frame.slice();
    const centre = [before[0] + before[2] / 2, before[1] + before[3] / 2];
    await drag(centre, [centre[0] + 30, centre[1] + 15], { metaKey: true, ctrlKey: true });
    const moved = store.item(pics[0].id).frame;
    check(Math.abs(moved[0] - before[0] - 30) < 0.6 && Math.abs(moved[1] - before[1] - 15) < 0.6, "picture moved by dragging", JSON.stringify(moved));
    app.run("undo");
    check(Math.abs(store.item(pics[0].id).frame[0] - before[0]) < 1e-6, "undo restores the position");
    app.run("redo");
    check(Math.abs(store.item(pics[0].id).frame[0] - moved[0]) < 1e-6, "redo moves it again");

    // Resizing from a corner keeps a picture's proportions
    const f = store.item(pics[0].id).frame.slice();
    await drag([f[0] + f[2], f[1] + f[3]], [f[0] + f[2] * 1.5, f[1] + f[3] * 1.2], { metaKey: true, ctrlKey: true });
    const g = store.item(pics[0].id).frame;
    check(Math.abs(g[2] / g[3] - f[2] / f[3]) < 1e-3 && g[2] > f[2] * 1.4, "corner resize keeps proportions", JSON.stringify(g));
    app.run("undo");

    // Keyboard: nudge, cycle selection, duplicate, delete
    const openDialog = document.querySelector("dialog[open]");
    check(!openDialog && !canvas.editing, "no dialog or text editor in the way of the keyboard",
      openDialog ? openDialog.textContent.slice(0, 200) : `editing=${!!canvas.editing}`);
    store.select([rect.id]);
    const rx = store.item(rect.id).frame[0];
    key("ArrowRight");
    check(Math.abs(store.item(rect.id).frame[0] - rx - 1) < 1e-6, "arrow key nudges 1 pt");
    key("ArrowRight", { shiftKey: true });
    check(Math.abs(store.item(rect.id).frame[0] - rx - 11) < 1e-6, "Shift+arrow nudges 10 pt");
    key("Tab");
    check(store.selection.length === 1 && store.selection[0] !== rect.id, "Tab selects the next object");
    store.select([rect.id]);
    const n0 = store.items().length;
    app.run("duplicate");
    check(store.items().length === n0 + 1, "duplicate adds a copy");
    key("Delete");
    check(store.items().length === n0, "Delete removes the selection");

    // Align, distribute, group, ungroup
    store.select([rect.id, arrow.id, pics[1]?.id].filter(Boolean));
    app.run("alignLeft");
    const lefts = store.selected().map((i) => (i.frame ? i.frame[0] : Math.min(...i.points.map((p) => p[0]))));
    check(Math.max(...lefts) - Math.min(...lefts) < 0.6, "align left lines up left edges", lefts.map((v) => v.toFixed(2)).join(","));
    const toGroup = store.selection.length;
    app.run("group");
    const grp = store.items().find((i) => i.type === "group");
    check(grp && grp.items.length === toGroup && store.selection[0] === grp.id, "group made", `${grp?.items.length} of ${toGroup}`);
    app.run("ungroup");
    check(!store.items().some((i) => i.type === "group"), "ungroup restores the objects");

    // Right-click menus: an object's commands with their shortcuts, Group once two are selected,
    // the page's own menu, a page's menu in the Pages list, and the same from the keyboard
    const menuEl = () => document.querySelector(".context-menu");
    const menuItem = (label) => [...(menuEl()?.querySelectorAll(".menu-item") || [])]
      .find((b) => b.querySelector(".menu-label").textContent === label);
    const middleOf = (id) => { const fr = store.item(id).frame; return screenOf(fr[0] + fr[2] / 2, fr[1] + fr[3] / 2); };
    const middleOfEl = (el) => { const r = el.getBoundingClientRect(); return [r.left + Math.min(20, r.width / 2), r.top + r.height / 2]; };
    // (Menus open once the clipboard has been looked at, so each right-click waits for its menu)
    async function rightClick(at, target = canvas.stage) {
      if (target === canvas.stage) {
        pointer("pointerdown", at, { button: 2, buttons: 2 });
        pointer("pointerup", at, { button: 2, buttons: 0 });
      }
      target.dispatchEvent(new MouseEvent("contextmenu", { clientX: at[0], clientY: at[1], bubbles: true, cancelable: true, button: 2 }));
      await until(() => menuEl());
    }
    const picA = pics[0].id, picB = (pics[1] || rect).id;
    store.select([]);
    await rightClick(middleOf(picA));
    check(menuEl() && store.selection.length === 1 && store.selection[0] === picA, "right-click selects the object and opens its menu",
      `menu=${!!menuEl()} selection=${store.selection}`);
    check(menuItem("Group")?.getAttribute("aria-disabled") === "true" && menuItem("Copy")?.querySelector("kbd")?.textContent === app.commands.copy.keys,
      "the menu shows shortcuts, and Group waits for two objects");
    check(menuItem("Crop picture") && menuItem("Replace picture…"), "a picture's menu can crop and replace it");
    const mr = menuEl()?.getBoundingClientRect();
    check(mr && mr.left >= 0 && mr.top >= 0 && mr.right <= window.innerWidth && mr.bottom <= window.innerHeight,
      "the menu stays inside the window", JSON.stringify(mr));
    check(document.activeElement?.closest(".context-menu"), "the menu takes the keyboard focus");
    menuKey("Escape");
    check(!menuEl() && document.activeElement === canvas.stage, "Escape closes it, back to the page");
    store.select([picA, picB]);
    await rightClick(middleOf(picB));
    check(store.selection.length === 2 && menuItem("Group")?.getAttribute("aria-disabled") !== "true",
      "right-click on one of two selected objects keeps both, and Group is on");
    menuItem("Group")?.click();
    const menuGroup = store.items().find((i) => i.type === "group");
    check(!menuEl() && menuGroup?.items.length === 2, "Group from the menu groups them");
    key("F10", { shiftKey: true });
    await until(() => menuEl());
    check(menuEl() && document.activeElement?.closest(".context-menu"), "Shift+F10 opens the menu for the selection");
    menuKey("u");
    check(document.activeElement?.querySelector(".menu-label")?.textContent === "Ungroup", "typing U jumps to Ungroup",
      document.activeElement?.textContent);
    menuKey("Enter");
    check(!menuEl() && !store.items().some((i) => i.type === "group"), "Enter chooses it: ungrouped");
    // Lock from the menu; the Objects list's menu shows it locked, and unlocks it
    store.select([picA]);
    await rightClick(middleOf(picA));
    menuItem("Lock position")?.click();
    check(store.item(picA).locked, "Lock position locks it");
    const lockedRow = document.getElementById(`layer-opt-${picA}`);
    if (lockedRow) await rightClick(middleOfEl(lockedRow), lockedRow);
    check(menuItem("Lock position")?.getAttribute("aria-checked") === "true", "the Objects list's menu shows it locked");
    menuItem("Lock position")?.click();
    check(!store.item(picA).locked, "and unlocks it");
    // Empty page: the page's own menu, with the rulers, grid and guides as they are
    const menuPage = store.page();
    const emptyAt = [[menuPage.width - 12, menuPage.height - 12], [menuPage.width - 12, 12], [12, menuPage.height - 12]].find((pt) => !canvas.itemAt(pt));
    await rightClick(screenOf(...emptyAt));
    check(menuEl() && store.selection.length === 0 && menuItem("Rulers")?.getAttribute("aria-checked") === "true"
      && menuItem("Grid")?.getAttribute("aria-checked") === "false", "right-click on empty page: the page's menu, rulers shown, grid hidden");
    menuItem("Select all")?.click();
    check(store.selection.length > 1 && store.selection.length === store.items().filter((i) => !i.locked).length, "Select all from it");
    // A page's menu in the Pages list: duplicate the page, then delete the copy
    const pageRow = (i) => document.querySelector(`.page-list li[data-index="${i}"]`);
    const [pageAt, pageCount, itemCount] = [store.pageIndex, store.doc.pages.length, store.items().length];
    await rightClick(middleOfEl(pageRow(pageAt)), pageRow(pageAt));
    menuItem("Duplicate page")?.click();
    check(store.doc.pages.length === pageCount + 1, "Duplicate page from a page's menu");
    await rightClick(middleOfEl(pageRow(store.pageIndex)), pageRow(store.pageIndex));
    check(menuItem("Move page up")?.getAttribute("aria-disabled") !== "true", "a later page can move up");
    menuItem("Delete page")?.click();
    await until(() => store.doc.pages.length === pageCount);
    store.setPage(pageAt);
    check(store.doc.pages.length === pageCount && store.items().length === itemCount, "Delete page from its menu removes the copy");
    if (navigator.platform.toUpperCase().includes("MAC")) {
      // Control-click is a right-click on a Mac: it starts no drag, and the menu opens
      store.select([]);
      const at = middleOf(picA), fr0 = store.item(picA).frame.slice();
      pointer("pointerdown", at, { ctrlKey: true });
      pointer("pointermove", [at[0] + 30, at[1] + 20], { ctrlKey: true });
      pointer("pointerup", [at[0] + 30, at[1] + 20], { ctrlKey: true, buttons: 0 });
      canvas.stage.dispatchEvent(new MouseEvent("contextmenu", { clientX: at[0], clientY: at[1], bubbles: true, cancelable: true, ctrlKey: true }));
      await until(() => menuEl());
      check(menuEl() && store.selection[0] === picA && store.item(picA).frame[0] === fr0[0], "Control-click opens the menu without moving anything");
      menuKey("Escape");
    }

    // Pasting what other apps copied (a test clipboard stands in for the system's): text keeps
    // bold, italic and paragraphs in the default font; a picture lands at true size in the middle
    // of the view; PDF data stays a vector; copied files are placed linked; with text and a
    // picture, ⌘V takes the text and the menu's Paste as picture the picture
    const pasteKey = () => key("v", { metaKey: true, ctrlKey: true });
    const pastedIds = [];
    async function pasteOne(contents, how = pasteKey) {
      const before = new Set(store.items().map((i) => i.id));
      if (contents) await rpc("clipboard_fake", contents);
      await how();
      await until(() => store.items().some((i) => !before.has(i.id)), 4000);
      const fresh = store.items().filter((i) => !before.has(i.id));
      pastedIds.push(...fresh.map((i) => i.id));
      return fresh.length === 1 ? fresh[0] : null;
    }
    const pastedText = await pasteOne({ text: "Plain and bold\nSecond line",
      html: "<p>Plain and <b>bold</b></p><p><i>Second</i> line</p>" });
    const paras = pastedText?.text?.paragraphs;
    check(pastedText?.textbox && paras?.length === 2 && paras[0].runs.map((r) => `${r.bold ? "*" : ""}${r.t}`).join("|") === "Plain and |*bold"
      && paras[1].runs[0].italic && paras[1].runs[0].t === "Second" && paras[0].runs[0].size === (canvas.defaults?.text?.size || 6),
      "⌘V pastes text as a text box, keeping bold, italic and paragraphs, in the default size", JSON.stringify(paras));
    const pastedPic = await pasteOne({ png: { size: [288, 144], dpi: 144 } });
    const view = canvas.stage.getBoundingClientRect(), viewMid = canvas.toPage(view.width / 2, view.height / 2);
    check(pastedPic?.type === "picture" && near(pastedPic.frame[2], 144, 0.01) && near(pastedPic.frame[3], 72, 0.01)
      && near(pastedPic.frame[0] + 72, viewMid[0], 0.5) && near(pastedPic.frame[1] + 36, viewMid[1], 0.5),
      "a pasted image lands at true size (288 px at 144 dpi: 2 in), in the middle of the view", JSON.stringify(pastedPic?.frame));
    const pdfFile = files.find((f) => f.toLowerCase().endsWith(".pdf")), svgFile = files.find((f) => f.toLowerCase().endsWith(".svg"));
    if (pdfFile) {
      const p = await pasteOne({ pdf: pdfFile });
      const a = p && store.doc.assets[p.asset];
      check(p?.type === "picture" && a?.primary === "pdf" && !a.variants.pdf.src, "pasted PDF data stays a vector PDF, kept in the document",
        JSON.stringify(a && { primary: a.primary, kinds: Object.keys(a.variants) }));
    }
    if (svgFile) {
      const p = await pasteOne({ files: [svgFile], text: svgFile });
      const a = p && store.doc.assets[p.asset];
      check(a && Object.values(a.variants).some((v) => v.src) && a.auto_update !== false, "copied files are placed linked, as when dropped",
        JSON.stringify(a && Object.keys(a.variants)));
    }
    const caption = await pasteOne({ text: "A caption", png: { size: [100, 50], dpi: 300 } });
    check(caption?.textbox && caption.text.paragraphs[0].runs[0].t === "A caption", "with text and a picture copied, ⌘V takes the text");
    const page0 = store.page();
    const freeAt = [[page0.width - 40, page0.height - 40], [page0.width - 40, 20], [20, page0.height - 40]].find((pt) => !canvas.itemAt(pt))
      || [page0.width - 40, page0.height - 40];
    const asPicture = await pasteOne(null, async () => {
      await rightClick(screenOf(...freeAt));
      check(menuItem("Paste as picture"), "and the menu offers Paste as picture");
      menuItem("Paste as picture")?.click();
    });
    const onePixel = 1.01 / canvas.k;   // the click's position comes in whole pixels
    check(asPicture?.type === "picture" && near(asPicture.frame[0], freeAt[0], onePixel) && near(asPicture.frame[1], freeAt[1], onePixel),
      "Paste as picture puts the picture where the page was right-clicked", JSON.stringify(asPicture?.frame));
    await rpc("clipboard_fake", { png: { size: [10, 10] } });
    await rightClick(screenOf(...freeAt));
    check(menuItem("Paste") && !menuItem("Paste as picture"), "with only a picture copied, the menu has just Paste");
    menuKey("Escape");
    // FigAssemble's own copy pastes as objects while it's the newest thing; anything copied
    // after it in another app wins
    store.select([pastedPic?.id].filter(Boolean));
    app.run("copy");
    const own = await pasteOne(null, () => app.run("paste"));
    check(own?.type === "picture" && own.asset === pastedPic?.asset, "FigAssemble's own copy pastes as objects");
    const newer = await pasteOne({ text: "Newer" }, () => app.run("paste"));
    check(newer?.textbox, "text copied in another app afterwards wins over FigAssemble's older copy");
    store.update("Remove the pasted test objects", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      items.splice(0, items.length, ...items.filter((i) => !pastedIds.includes(i.id)));
    }, { select: [] });

    // Themes: the Settings gallery applies one at once, the arrow keys choose the next, and
    // Match the system uses the day or the night theme as the system is light or dark
    const panelVar = () => getComputedStyle(document.documentElement).getPropertyValue("--panel").trim();
    const themeColors = Object.fromEntries((app.info.themes || []).map((t) => [t.id, t.colors]));
    const themeTile = (id) => document.querySelector(`.theme-tile[data-theme-id="${id}"]`);
    app.run("preferences");
    await until(() => themeTile("dracula"));
    check(document.querySelectorAll(".theme-tile").length === (app.info.themes || []).length + 1,
      "the gallery shows every theme, and Match the system");
    themeTile("dracula")?.click();
    await until(() => panelVar() === themeColors.dracula?.panel, 4000);
    check(panelVar() === themeColors.dracula?.panel && themeTile("dracula")?.getAttribute("aria-checked") === "true",
      "choosing Dracula in the gallery applies it at once", panelVar());
    themeTile("dracula")?.focus();
    themeTile("dracula")?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true }));
    await until(() => panelVar() === themeColors.cobalt?.panel, 4000);
    check(app.prefs.theme === "cobalt" && document.activeElement === themeTile("cobalt"), "the arrow keys choose the next theme",
      app.prefs.theme);
    themeTile("system")?.click();
    await until(() => !document.querySelector(".theme-daynight")?.hidden);
    for (const [sel, id] of [["pref-theme-day", "pistachio"], ["pref-theme-night", "walnut"]]) {
      const el = document.getElementById(sel);
      el.value = id;
      el.dispatchEvent(new Event("change"));
      await until(() => app.prefs[sel === "pref-theme-day" ? "theme_day" : "theme_night"] === id);
    }
    const night = matchMedia("(prefers-color-scheme: dark)").matches;
    await until(() => panelVar() === themeColors[night ? "walnut" : "pistachio"]?.panel, 4000);
    check(panelVar() === themeColors[night ? "walnut" : "pistachio"]?.panel,
      `Match the system uses the ${night ? "night" : "day"} theme here`, panelVar());
    await app.savePrefs({ theme: "system", theme_day: "light", theme_night: "dark" });
    await until(() => panelVar() === themeColors[night ? "dark" : "light"]?.panel, 4000);
    for (const dlg of document.querySelectorAll("dialog[open]")) dlg.close();

    // The selection box stands 6 px outside the object, and so do its handles; dragging a handle
    // moves the edge just as far as the pointer moves (no jump out to where it was grabbed)
    store.select([rect.id]);
    await settle();
    const boxFrame = store.item(rect.id).frame.slice();
    const boxPts = document.querySelector(".overlay .sel-outline")?.getAttribute("points")?.split(" ").map((q) => q.split(",").map(Number));
    const [nwx, nwy] = canvas.toScreen(boxFrame[0], boxFrame[1]);
    check(boxPts && near(boxPts[0][0], nwx - 6, 0.01) && near(boxPts[0][1], nwy - 6, 0.01),
      "the selection box stands 6 px outside the object", JSON.stringify(boxPts?.[0]));
    const seHandle = canvas.handlesFor(store.item(rect.id)).find((hd) => hd.dir === "se");
    const stageBox = canvas.stage.getBoundingClientRect();
    const grabAt = [stageBox.left + seHandle.at[0], stageBox.top + seHandle.at[1]];
    pointer("pointerdown", grabAt);
    pointer("pointermove", [grabAt[0] + 15, grabAt[1] + 10]);
    pointer("pointermove", [grabAt[0] + 30, grabAt[1] + 20]);
    pointer("pointerup", [grabAt[0] + 30, grabAt[1] + 20]);
    await settle();
    const boxFrame2 = store.item(rect.id).frame;
    check(near(boxFrame2[2] - boxFrame[2], 30 / canvas.k, 0.01) && near(boxFrame2[3] - boxFrame[3], 20 / canvas.k, 0.01),
      "dragging a handle moves the edge as far as the pointer, without a jump", `${boxFrame} -> ${boxFrame2}`);
    app.run("undo");

    // While the whole page fits, it stays centred and scrolling can't move it; zoomed in,
    // scrolling moves around, and Centre page (⌘⇧0) brings it back to the middle
    canvas.fit();
    const viewBox = canvas.stage.getBoundingClientRect();
    const pageCentred = () => {
      const [mx, my] = canvas.toScreen(store.page().width / 2, store.page().height / 2);
      return near(mx, viewBox.width / 2, 0.5) && near(my, viewBox.height / 2, 0.5);
    };
    const scroll = () => canvas.stage.dispatchEvent(new WheelEvent("wheel", { deltaX: 40, deltaY: 60, bubbles: true,
      cancelable: true, clientX: viewBox.left + 100, clientY: viewBox.top + 100 }));
    scroll();
    check(pageCentred(), "while the whole page fits, scrolling leaves it centred");
    canvas.setZoom(canvas.zoom * 4);
    const zoomedIn = canvas.zoom;
    scroll();
    check(!pageCentred(), "zoomed in, scrolling moves around");
    key("0", { metaKey: true, ctrlKey: true, shiftKey: true });
    check(pageCentred() && near(canvas.zoom, zoomedIn, 1e-9), "Centre page (⌘⇧0) centres it, keeping the zoom");
    canvas.fit();

    // The side panels' inner edges: drag to resize, arrow keys on a focused edge, double-click
    // to put a panel back; the widths are remembered
    const leftPanel = document.querySelector(".sidebar.left"), rightPanel = document.getElementById("inspector");
    const panelEdge = (side) => document.querySelector(`.splitter.${side}`);
    const lw0 = leftPanel.getBoundingClientRect().width, rw0 = rightPanel.getBoundingClientRect().width;
    const dragEdge = (side, dx) => {
      const b = panelEdge(side), r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + 200;
      const ev = (type, cx) => b.dispatchEvent(new PointerEvent(type, { clientX: cx, clientY: y, bubbles: true, button: 0,
        buttons: type === "pointerup" ? 0 : 1, pointerId: 7, pointerType: "mouse" }));
      ev("pointerdown", x);
      ev("pointermove", x + dx / 2);
      ev("pointermove", x + dx);
      ev("pointerup", x + dx);
    };
    dragEdge("left", 60);
    dragEdge("right", -40);
    await settle();
    check(near(leftPanel.getBoundingClientRect().width - lw0, 60, 1.5) && near(rightPanel.getBoundingClientRect().width - rw0, 40, 1.5),
      "dragging the panels' inner edges widens them", `${leftPanel.getBoundingClientRect().width - lw0}, ${rightPanel.getBoundingClientRect().width - rw0}`);
    check(app.prefs.panel_widths?.left > 15 && app.prefs.panel_widths?.right > 19, "and their widths are remembered",
      JSON.stringify(app.prefs.panel_widths));
    for (const side of ["left", "right"]) panelEdge(side).dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    await settle();
    check(near(leftPanel.getBoundingClientRect().width, lw0, 1) && near(rightPanel.getBoundingClientRect().width, rw0, 1),
      "double-clicking an edge puts its panel back");
    panelEdge("left").focus();
    panelEdge("left").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true }));
    await settle();
    const remPx = parseFloat(getComputedStyle(document.documentElement).fontSize);
    check(near(leftPanel.getBoundingClientRect().width - lw0, remPx, 1), "the arrow keys move a focused edge",
      `${leftPanel.getBoundingClientRect().width - lw0} vs ${remPx}`);
    panelEdge("left").dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    await settle();

    // Outline: a contour in a second colour around the shape, with its own transparency
    store.select([rect.id]);
    fieldByLabel("Outline around it")?.click();
    await settle();
    const ro = store.item(rect.id).outline;
    check(ro && ro.color === "#ffffff" && ro.width === 1, "Outline adds a white contour around a black shape", JSON.stringify(ro));
    const firstPath = canvas.els.get(rect.id)?.g.querySelector("path")?.getAttribute("style") || "";
    check(firstPath.includes("stroke:#ffffff") && firstPath.includes("stroke-width:3"),
      "the outline is drawn underneath, 1 pt beyond the line on each side", firstPath);
    await choose("Outline transparency", "50");
    await settle();
    check(store.item(rect.id).outline.opacity === 0.5 && canvas.els.get(rect.id)?.g.innerHTML.includes('opacity="0.5"'),
      "outline transparency fades the contour as one piece", JSON.stringify(store.item(rect.id).outline));
    // Outline types: Both sides of the line goes over the fill and under the line
    store.update("Fill for the test", (doc) => { findItem(doc, rect.id).fill = { color: "#cfe3ff", opacity: 1 }; });
    await choose("Outline type", "both");
    await settle();
    const layered = [...(canvas.els.get(rect.id)?.g.querySelectorAll("path") || [])].map((p) => p.getAttribute("style") || "");
    check(store.item(rect.id).outline.type === "both" && layered.length === 3 && layered[0].includes("fill:#cfe3ff")
      && layered[1].includes("stroke:#ffffff"), "Both sides of the line draws the outline over the fill, under the line",
      layered.join(" | "));
    await choose("Outline type", "outside");
    store.update("Unfill", (doc) => { findItem(doc, rect.id).fill = null; });

    // Gradient fills: linear, then radial from a corner; stops can be added and reversed
    store.select([rect.id]);
    await choose("Fill", "linear");
    await settle();
    let gf = store.item(rect.id).fill;
    check(gf?.gradient?.type === "linear" && gf.gradient.stops.length === 2 && canvas.els.get(rect.id)?.g.innerHTML.includes("linearGradient"),
      "Fill: Linear gradient fills the shape with a gradient, drawn by the engine", JSON.stringify(gf));
    await choose("Fill", "radial");
    await choose("Gradient from", "tl");
    await settle();
    gf = store.item(rect.id).fill;
    check(gf.gradient.type === "radial" && gf.gradient.center.join() === "0,0" && canvas.els.get(rect.id)?.g.innerHTML.includes("radialGradient"),
      "a radial gradient can start from a corner", JSON.stringify(gf.gradient));
    const insButton = (text) => { inspector.render(); return [...document.querySelectorAll("#inspector button")].find((b) => b.textContent === text); };
    insButton("Add stop")?.click();
    await settle();
    gf = store.item(rect.id).fill;
    check(gf.gradient.stops.length === 3 && gf.gradient.stops[1].pos === 0.5, "Add stop puts a colour stop in the widest gap",
      JSON.stringify(gf.gradient.stops));
    const firstColour = gf.gradient.stops[0].color;
    insButton("Reverse")?.click();
    await settle();
    gf = store.item(rect.id).fill;
    check(gf.gradient.stops[2].color === firstColour && gf.gradient.stops[0].pos === 0, "Reverse swaps the ends",
      JSON.stringify(gf.gradient.stops));
    await choose("Fill", "none");

    // Hex codes next to colour pickers
    inspector.render();
    let hex = document.querySelector('#inspector input[aria-label="Line colour hex code"]');
    hex.value = "d62728";
    hex.dispatchEvent(new Event("change"));
    await settle();
    check(store.item(rect.id).stroke.color === "#d62728", "typing a hex code sets the colour", store.item(rect.id).stroke.color);
    inspector.render();
    hex = document.querySelector('#inspector input[aria-label="Line colour hex code"]');
    check(hex.value === "#D62728" && document.getElementById(hex.id.replace(/-hex$/, ""))?.value === "#d62728",
      "the hex field and picker show the current colour", hex.value);
    hex.value = "not a colour";
    hex.dispatchEvent(new Event("change"));
    check(store.item(rect.id).stroke.color === "#d62728" && hex.value === "#D62728", "an invalid hex code is refused", hex.value);

    // Even dashes: a dotted outline gets a dot on every corner and even spacing along each side;
    // unticked, PowerPoint's pattern runs on regardless of corners
    await choose("Dash", "sysDot");
    await settle();
    const dotsD = [...(canvas.els.get(rect.id)?.g.querySelectorAll("path") || [])].pop()?.getAttribute("d") || "";
    const dotAt = [...dotsD.matchAll(/M\s*(-?[\d.]+)[ ,]+(-?[\d.]+)/g)].map((m) => [parseFloat(m[1]), parseFloat(m[2])]);
    const rf = store.item(rect.id).frame;
    const rectCorners = [[rf[0], rf[1]], [rf[0] + rf[2], rf[1]], [rf[0] + rf[2], rf[1] + rf[3]], [rf[0], rf[1] + rf[3]]];
    check(!canvas.els.get(rect.id)?.g.innerHTML.includes("stroke-dasharray")
      && rectCorners.every((c) => dotAt.some((p) => Math.hypot(p[0] - c[0], p[1] - c[1]) < 0.05)),
    "a dotted outline has a dot on every corner", `${dotAt.length} dots; corners ${JSON.stringify(rectCorners)}`);
    const topXs = dotAt.filter((p) => Math.abs(p[1] - rf[1]) < 0.01).map((p) => p[0]).sort((a, b) => a - b);
    const topSteps = topXs.slice(1).map((x, i) => x - topXs[i]);
    check(topSteps.length > 3 && Math.max(...topSteps) - Math.min(...topSteps) < 0.02, "with the dots evenly spaced along each side",
      topSteps.map((v) => v.toFixed(3)).join(","));
    fieldByLabel("Even dashes: one on every corner and end")?.click();
    await settle();
    check(store.item(rect.id).stroke.even_dashes === false && canvas.els.get(rect.id)?.g.innerHTML.includes("stroke-dasharray"),
      "unticking Even dashes gives PowerPoint's spacing", JSON.stringify(store.item(rect.id).stroke));
    await choose("Dash", "solid");

    // Text: create, type, commit
    canvas.setTool("text");
    await drag([250, 100], [250, 100]);
    await wait(80);
    check(canvas.editing, "text tool opens the text editor");
    canvas.editor.innerHTML = "<div>Hello <b>bold</b> world</div>";
    canvas.commitEdit();
    await settle();
    const tb = store.items().find((i) => (i.text?.paragraphs?.[0]?.runs || []).some((r) => r.t.includes("Hello")));
    const runs = tb?.text.paragraphs[0].runs || [];
    check(runs.length === 3 && runs[1].bold && !runs[0].bold, "typed text keeps bold runs", JSON.stringify(runs.map((r) => [r.t, !!r.bold])));
    check(canvas.els.get(tb?.id)?.g.querySelector("text"), "text drawn by the engine");

    // Cropping: drag the left crop handle inwards
    const p0 = store.item(pics[0].id);
    canvas.startCrop(p0.id);
    const pf = p0.frame.slice();
    await drag([pf[0], pf[1] + pf[3] / 2], [pf[0] + pf[2] * 0.25, pf[1] + pf[3] / 2]);
    const cropped = store.item(pics[0].id);
    check(cropped.crop[0] > 0.2 && cropped.crop[0] < 0.3 && Math.abs(cropped.frame[2] - pf[2] * (1 - cropped.crop[0])) < 0.6,
      "crop handle crops without rescaling", JSON.stringify(cropped.crop));
    canvas.endCrop();

    // Pages
    app.run("addPage");
    check(store.doc.pages.length === 2 && store.pageIndex === 1, "page added");
    store.setPage(0);
    app.run("duplicatePage");
    check(store.doc.pages.length === 3 && store.page().items.length === store.doc.pages[0].items.length, "page duplicated with its objects");
    app.movePage(1, 2);
    await app.run("deletePage");
    store.setPage(0);
    check(store.doc.pages.length === 2, "page deleted");

    // Journal page sizes from the Page panel
    store.select([]);
    await choose("Journal", "Nature");
    check(near(store.page().width, 180 * MMPT) && near(store.page().height, 170 * MMPT),
      "Nature starts at a double-column page, 180 × 170 mm", pageSize());
    await choose("Figure type", "Single column");
    check(near(store.page().width, 90 * MMPT) && near(store.page().height, 170 * MMPT), "Nature single column is 90 mm wide", pageSize());
    await choose("Journal", "Science");
    await choose("Figure type", "2 columns");
    check(near(store.page().width, 121 * MMPT) && near(store.page().height, 199 * MMPT), "Science 2 columns is 121 × 199 mm", pageSize());
    await choose("Journal", "Cell");
    check(near(store.page().width, 174 * MMPT) && near(store.page().height, 200 * MMPT), "Cell full width is 174 × 200 mm", pageSize());
    await app.run("fitPage");
    check(near(store.page().width, 174 * MMPT) && store.page().height < 200 * MMPT,
      "Fit to content on a journal page keeps the column width", pageSize());
    await choose("Standard size", "A4");
    check(near(store.page().width, 210 * MMPT) && near(store.page().height, 297 * MMPT), "Standard size goes back to A4", pageSize());

    // Rulers, guides, the grid and snapping, on a page of their own
    app.run("addPage");
    await settle();
    canvas.fit();
    const aidsPage = store.pageIndex;
    const pg = () => store.page();
    const rulerTop = document.querySelector(".ruler.top"), rulerLeft = document.querySelector(".ruler.left");
    check(rulerTop?.offsetHeight > 10 && rulerLeft?.offsetWidth > 10 && rulerTop.width > 0,
      "rulers run along the top and left of the page", `${rulerTop?.offsetHeight} ${rulerLeft?.offsetWidth}`);
    // While the page fits it stays centred in the view the rulers leave; zoomed in, it stays put
    const midOnScreen = () => {
      const r = canvas.stage.getBoundingClientRect(), [mx, my] = canvas.toScreen(pg().width / 2, pg().height / 2);
      return [mx - r.width / 2, my - r.height / 2];
    };
    key("r", { metaKey: true, ctrlKey: true });
    await until(() => !rulerTop.offsetParent);
    await settle();
    const off = midOnScreen();
    check(!rulerTop.offsetParent && near(off[0], 0, 0.5) && near(off[1], 0, 0.5),
      "⌘R hides the rulers, and a page that fits stays centred", `${off}`);
    key("r", { metaKey: true, ctrlKey: true });
    await until(() => rulerTop.offsetParent);
    check(rulerTop.offsetParent && app.prefs.show_rulers, "⌘R shows them again");
    canvas.setZoom(canvas.zoom * 4);
    const corner0 = screenOf(0, 0);
    key("r", { metaKey: true, ctrlKey: true });
    await until(() => !rulerTop.offsetParent);
    await settle();
    const corner1 = screenOf(0, 0);
    check(near(corner0[0], corner1[0], 0.5) && near(corner0[1], corner1[1], 0.5),
      "zoomed in, the page stays where it was as the rulers go", `${corner0} -> ${corner1}`);
    key("r", { metaKey: true, ctrlKey: true });
    await until(() => rulerTop.offsetParent);
    canvas.fit();

    // A guide dragged out of the top ruler runs across the page where it's dropped
    const rulerPointer = (type, x, y) => rulerTop.dispatchEvent(new PointerEvent(type, { clientX: x, clientY: y, bubbles: true,
      button: 0, buttons: 1, pointerId: 2, pointerType: "mouse", metaKey: true, ctrlKey: true }));
    let rr = rulerTop.getBoundingClientRect();
    const drop = screenOf(100, 150);
    rulerPointer("pointerdown", drop[0], rr.top + rr.height / 2);
    rulerPointer("pointermove", drop[0], rr.top + rr.height / 2 + 2);
    check(!document.querySelector(".guides line"), "a new guide doesn't appear while it's still over its ruler");
    rulerPointer("pointermove", drop[0], (rr.bottom + drop[1]) / 2);
    rulerPointer("pointermove", drop[0], drop[1]);
    check(document.querySelector(".guide-label")?.textContent === lengthText(150), "the guide's position shows beside the pointer",
      document.querySelector(".guide-label")?.textContent);
    rulerPointer("pointerup", drop[0], drop[1]);
    await settle();
    check(pg().guides.y.length === 1 && near(pg().guides.y[0], 150, 0.6), "dragging out of the top ruler adds a horizontal guide",
      JSON.stringify(pg().guides));
    app.run("undo");
    check(pg().guides.y.length === 0, "undo takes the new guide away");
    app.run("redo");
    check(pg().guides.y.length === 1, "redo puts it back");
    store.update("Guide for test", (doc) => { doc.pages[store.pageIndex].guides.y = [150]; });

    // An object dragged near the guide snaps onto it; ⌘ while dragging, Snap off or hidden guides leave it free
    canvas.setTool("rect");
    await drag([40, 40], [80, 80], { metaKey: true, ctrlKey: true });
    const box = store.items().find((i) => i.geom === "rect");
    const boxAt = () => store.item(box.id).frame;
    const grab = [60, 60];
    await drag(grab, [grab[0] + 30, grab[1] + 108]);      // its top edge 2 pt short of the guide
    check(near(boxAt()[1], 150, 1e-6), "a dragged object snaps to a guide", JSON.stringify(boxAt()));
    app.run("undo");
    await drag(grab, [grab[0] + 30, grab[1] + 108], { metaKey: true, ctrlKey: true });
    check(near(boxAt()[1], 148, 0.6), "holding ⌘ while dragging ignores snapping", JSON.stringify(boxAt()));
    app.run("undo");
    const snapBtn = document.querySelector('.quick [data-cmd="toggleSnap"]');
    check(snapBtn?.getAttribute("aria-pressed") === "true", "the Snap button shows snapping is on");
    snapBtn.click();
    await until(() => app.prefs.snap === false);
    check(snapBtn.getAttribute("aria-pressed") === "false", "the Snap button turns snapping off and shows it",
      snapBtn.getAttribute("aria-pressed"));
    await drag(grab, [grab[0] + 30, grab[1] + 108]);
    check(near(boxAt()[1], 148, 0.6), "with Snap off, nothing snaps", JSON.stringify(boxAt()));
    app.run("undo");
    key(";", { metaKey: true, ctrlKey: true, shiftKey: true });
    await until(() => app.prefs.snap === true);
    check(snapBtn.getAttribute("aria-pressed") === "true", "⇧⌘; turns snapping back on");
    key(";", { metaKey: true, ctrlKey: true });
    await until(() => app.prefs.show_guides === false);
    check(!document.querySelector(".guides line"), "⌘; hides the guides");
    await drag(grab, [grab[0] + 30, grab[1] + 108]);
    check(near(boxAt()[1], 148, 0.6), "hidden guides don't snap", JSON.stringify(boxAt()));
    app.run("undo");
    key(";", { metaKey: true, ctrlKey: true });
    await until(() => app.prefs.show_guides === true);

    // Dragging the guide itself: it snaps to the object's bottom edge; Escape cancels; the ruler removes it
    await drag([300, 150], [300, 82]);
    check(near(pg().guides.y[0], 80, 1e-6), "a dragged guide snaps to an object's edge", JSON.stringify(pg().guides));
    const g0 = screenOf(300, 80);
    pointer("pointerdown", g0);
    pointer("pointermove", [g0[0], g0[1] + 40]);
    key("Escape");
    pointer("pointerup", [g0[0], g0[1] + 40]);
    await settle();
    check(near(pg().guides.y[0], 80, 1e-6) && !canvas.op, "Escape cancels dragging a guide", JSON.stringify(pg().guides));
    rr = rulerTop.getBoundingClientRect();
    pointer("pointerdown", g0);
    pointer("pointermove", [g0[0], (g0[1] + rr.top) / 2]);
    pointer("pointermove", [g0[0], rr.top + 4]);
    check(document.querySelector(".guide-label")?.textContent === "Release to remove", "over the ruler, a guide says it will go",
      document.querySelector(".guide-label")?.textContent);
    pointer("pointerup", [g0[0], rr.top + 4]);
    await settle();
    check(pg().guides.y.length === 0, "dropping a guide onto a ruler removes it", JSON.stringify(pg().guides));
    app.run("undo");
    check(pg().guides.y.length === 1, "undo brings it back");

    // The Page panel lists the guides, to add, place exactly and remove without a pointer
    store.select([]);
    inspector.render();
    const pageButton = (text) => [...document.querySelectorAll("#inspector button")].find((b) => b.textContent === text);
    pageButton("Add vertical")?.click();
    await settle();
    check(pg().guides.x.length === 1 && near(pg().guides.x[0], pg().width / 2, 1e-6), "Add vertical puts a guide down the middle",
      JSON.stringify(pg().guides));
    const vf = fieldByLabel("Vertical guide 1");
    check(vf && document.activeElement === vf, "its position field takes the focus, ready to type", document.activeElement?.outerHTML?.slice(0, 80));
    vf.value = "3";
    vf.dispatchEvent(new Event("change"));
    vf.blur();
    check(near(pg().guides.x[0], (3 * 72) / 2.54, 1e-6), "typing a position moves the guide (3 cm from the left)", JSON.stringify(pg().guides));
    // Its mark on the top ruler drags it too (for guides that objects cover)
    rr = rulerTop.getBoundingClientRect();
    const markX = screenOf((3 * 72) / 2.54, 0)[0], toX = screenOf(200, 0)[0], onRuler = rr.bottom - 3;
    rulerPointer("pointerdown", markX, onRuler);
    rulerPointer("pointermove", (markX + toX) / 2, onRuler);
    rulerPointer("pointermove", toX, onRuler);
    rulerPointer("pointerup", toX, onRuler);
    await settle();
    check(near(pg().guides.x[0], 200, 0.6), "dragging a guide's mark along the ruler moves the guide", JSON.stringify(pg().guides));

    // The grid: while it shows, things snap to it; hidden, they don't
    key("'", { metaKey: true, ctrlKey: true });
    await until(() => app.prefs.show_grid === true);
    await settle();
    check(document.querySelector(".grid path.major"), "⌘' shows the grid over the page");
    const step = canvas.gridSteps().snap, gridX = Math.round(70 / step) * step;
    const along = [grab[0] + gridX + 1 - boxAt()[0], grab[1]];
    await drag(grab, along);
    check(near(boxAt()[0], gridX, 1e-6), "a dragged object snaps to the grid", `${boxAt()[0]} vs ${gridX}`);
    app.run("undo");
    key("'", { metaKey: true, ctrlKey: true });
    await until(() => app.prefs.show_grid === false);
    await drag(grab, along);
    check(near(boxAt()[0], gridX + 1, 0.6) && !document.querySelector(".grid path"), "with the grid hidden, nothing snaps to it",
      String(boxAt()[0]));
    app.run("undo");

    // Equal gaps: a box between two others snaps halfway and shows both gaps; one beyond repeats the gap
    const mk = (id, x, y) => ({ id, type: "shape", geom: "rect", frame: [x, y, 40, 40], rot: 0, flip_h: false, flip_v: false,
      stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 }, fill: null });
    store.update("Boxes for test", (doc) => doc.pages[store.pageIndex].items.push(mk("eqA", 330, 500), mk("eqC", 450, 500),
      mk("eqB", 392, 600), mk("eqD", 560, 600)));
    await settle();
    const dragShowing = async (from, to) => {
      pointer("pointerdown", screenOf(...from));
      for (const f of [0.4, 0.8, 1]) pointer("pointermove", screenOf(from[0] + (to[0] - from[0]) * f, from[1] + (to[1] - from[1]) * f));
      const shown = { gaps: document.querySelectorAll(".snap-gap").length,
        labels: [...document.querySelectorAll(".snap-label")].map((t) => t.textContent) };
      pointer("pointerup", screenOf(...to));
      await settle();
      return shown;
    };
    let shown = await dragShowing([412, 620], [412, 521]);
    check(near(store.item("eqB").frame[0], 390, 1e-6) && near(store.item("eqB").frame[1], 500, 1e-6),
      "a box between two others snaps to equal gaps", JSON.stringify(store.item("eqB").frame));
    check(shown.gaps === 2 && shown.labels.length === 2 && shown.labels.every((t) => t === lengthText(20)),
      "both gaps show while dragging, with their size", JSON.stringify(shown));
    shown = await dragShowing([580, 620], [531, 521]);
    check(near(store.item("eqD").frame[0], 510, 1e-6), "a box beyond a row snaps to repeat the row's gap", JSON.stringify(store.item("eqD").frame));
    check(shown.gaps === 2, "the matching gaps show", JSON.stringify(shown));
    // With the grid showing, zoomed in so its millimetre lines are in play, lining up with other
    // objects and equal gaps still wins over the nearest grid line
    key("'", { metaKey: true, ctrlKey: true });
    await until(() => app.prefs.show_grid === true);
    canvas.setZoom(2.2, ...canvas.toScreen(420, 520));
    const fine = canvas.gridSteps();
    await drag([410, 520], [411.5, 521.2]);
    check(fine.minor && near(store.item("eqB").frame[0], 390, 1e-6) && near(store.item("eqB").frame[1], 500, 1e-6),
      "objects and equal gaps win over the grid", `${JSON.stringify(store.item("eqB").frame)} minor=${fine.minor}`);
    key("'", { metaKey: true, ctrlKey: true });
    await until(() => app.prefs.show_grid === false);
    canvas.fit();

    // Align and distribute as in Illustrator: by centres, to a key object, with an exact gap, to the page
    const fr = (id) => store.item(id).frame;
    store.update("Spread for test", (doc) => { findItem(doc, "eqB").frame[0] = 400; findItem(doc, "eqD").frame[0] = 600; });
    store.select(["eqA", "eqB", "eqC"]);
    check(document.querySelector('#rpanel-arrange [data-cmd="distributeCenter"]') && document.querySelector('#rpanel-arrange [data-sync="spacing_gap"]')
      && document.querySelector('#rpanel-arrange [data-sync="align_to"]'), "the Arrange tab has distribute, spacing and align-to controls");
    app.run("distributeCenter");
    check(near(fr("eqB")[0], 390, 1e-6) && near(fr("eqA")[0], 330, 1e-6) && near(fr("eqC")[0], 450, 1e-6),
      "Distribute centres spaces the centres evenly between the outer two", `${fr("eqA")[0]} ${fr("eqB")[0]} ${fr("eqC")[0]}`);
    const cAt = screenOf(fr("eqC")[0] + 20, fr("eqC")[1] + 20);
    pointer("pointerdown", cAt);
    pointer("pointerup", cAt);
    await settle();
    check(app.prefs.align_to === "key" && app.keyObject()?.id === "eqC" && store.selection.length === 3,
      "clicking one of the selected objects makes it the key object", `${app.prefs.align_to} ${app.keyObject()?.id} ${store.selection}`);
    store.update("Nudge for test", (doc) => { findItem(doc, "eqA").frame[1] = 470; findItem(doc, "eqB").frame[1] = 530; });
    app.run("alignTop");
    check(near(fr("eqA")[1], 500, 1e-6) && near(fr("eqB")[1], 500, 1e-6) && near(fr("eqC")[1], 500, 1e-6),
      "Align tops lines them up with the key object, which stays put", `${fr("eqA")[1]} ${fr("eqB")[1]} ${fr("eqC")[1]}`);
    const gapIn = document.querySelector('#rpanel-arrange [data-sync="spacing_gap"]');
    gapIn.value = "0.5";
    gapIn.dispatchEvent(new Event("change"));
    app.run("distributeH");
    const g05 = (0.5 * 72) / 2.54;
    check(near(fr("eqC")[0], 450, 1e-6) && near(fr("eqB")[0], 450 - g05 - 40, 1e-6) && near(fr("eqA")[0], 450 - 2 * (g05 + 40), 1e-6),
      "a set gap spaces them exactly that far apart, counted out from the key object", `${fr("eqA")[0]} ${fr("eqB")[0]} ${fr("eqC")[0]}`);
    gapIn.value = "";
    gapIn.dispatchEvent(new Event("change"));
    const toSel = document.querySelector('#rpanel-arrange [data-sync="align_to"]');
    toSel.value = "page";
    toSel.dispatchEvent(new Event("change"));
    store.select(["eqA", "eqB"]);
    app.run("alignRight");
    check(near(fr("eqA")[0] + 40, pg().width, 1e-6) && near(fr("eqB")[0] + 40, pg().width, 1e-6) && app.prefs.spacing_gap == null,
      "aligning to the page puts their right edges on the page's edge", `${fr("eqA")[0]} ${fr("eqB")[0]}`);
    app.setAlignTo("selection");

    // A new page starts with this page's guides; Remove all clears them
    const guidesNow = JSON.stringify(pg().guides);
    app.run("addPage");
    check(JSON.stringify(pg().guides) === guidesNow, "a new page starts with the same guides", `${JSON.stringify(pg().guides)} vs ${guidesNow}`);
    await app.run("deletePage");
    store.setPage(aidsPage);
    inspector.render();
    pageButton("Remove all")?.click();
    check(pg().guides.x.length + pg().guides.y.length === 0, "Remove all clears the page's guides", JSON.stringify(pg().guides));

    // The View tab shows and hides the rulers, grid and guides
    document.getElementById("rtab-view").click();
    const gridBtn = document.querySelector('#rpanel-view [data-pref="show_grid"]');
    check(!document.getElementById("rpanel-view").hidden && gridBtn?.getAttribute("aria-pressed") === "false",
      "the View tab shows the grid is off");
    gridBtn.click();
    // (Waiting for the drawing itself: a hidden window's timers can lag well behind the setting)
    await until(() => gridBtn.getAttribute("aria-pressed") === "true" && document.querySelector(".grid path"), 5000);
    check(gridBtn.getAttribute("aria-pressed") === "true" && document.querySelector(".grid path"), "its Grid button shows the grid",
      `pressed=${gridBtn.getAttribute("aria-pressed")} grid=${!!document.querySelector(".grid path")} pref=${app.prefs.show_grid}`);
    gridBtn.click();
    await until(() => app.prefs.show_grid === false);
    document.getElementById("rtab-home").click();
    keepAids = ["guides", "guidelist"].includes(params.get("finalSelect"));
    if (!keepAids) { store.setPage(aidsPage); await app.run("deletePage"); }
    store.setPage(0);

    // Connectors: line ends attach to corners, side middles and dashes, and follow their objects
    app.run("addPage");
    await settle();
    canvas.fit();
    const cnPage = store.pageIndex;
    const asset0 = store.doc.assets[pics[0].asset];
    store.update("Objects for test", (doc) => doc.pages[cnPage].items.push(
      { id: "cnR", type: "shape", geom: "rect", frame: [100, 100, 80, 50], rot: 0, flip_h: false, flip_v: false, fill: null,
        stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 } },
      { id: "cnD", type: "shape", geom: "rect", frame: [100, 300, 100, 60], rot: 0, flip_h: false, flip_v: false, fill: null,
        stroke: { color: "#000000", width: 2, dash: "sysDot", cap: "round", join: "round", opacity: 1 } },
      { id: "cnP", type: "picture", name: "pic", asset: pics[0].asset, page_index: 0, frame: [320, 120, ...asset0.size_pt],
        crop: [0, 0, 0, 0], rot: 0, flip_h: false, flip_v: false, opacity: 1, source: "auto" }));
    await settle();
    canvas.setTool("arrow");
    await drag([181, 126], [250, 210]);
    const cn = store.items().find((i) => i.type === "line");
    const cnAt = (k) => store.item(cn.id).points[k === 0 ? 0 : store.item(cn.id).points.length - 1];
    check(cn?.start_link?.item === "cnR" && cn.start_link.site === "m1" && near(cnAt(0)[0], 180, 1e-6) && near(cnAt(0)[1], 125, 1e-6),
      "an arrow drawn from a rectangle's side attaches to its middle", JSON.stringify(cn?.start_link) + JSON.stringify(cn?.points));
    await drag([140, 112], [160, 122], { metaKey: true, ctrlKey: true });   // move the rectangle
    check(near(cnAt(0)[0], 200, 1e-6) && near(cnAt(0)[1], 135, 1e-6), "the attached end follows when the rectangle moves",
      JSON.stringify(cnAt(0)));
    store.select(["cnR"]);
    await choose("Width", String((120 * 2.54) / 72));
    await choose("Rotation", "90");
    await settle();
    const rr2 = store.item("cnR").frame, cx2 = rr2[0] + rr2[2] / 2, cy2 = rr2[1] + rr2[3] / 2;
    check(near(cnAt(0)[0], cx2, 1e-3) && near(cnAt(0)[1], cy2 + rr2[2] / 2, 1e-3),
      "and when it is resized and turned (the side's middle turns with it)", `${JSON.stringify(cnAt(0))} vs ${cx2}, ${cy2 + rr2[2] / 2}`);
    // The arrow's end onto the picture's top-left corner, with the connection points showing on the way
    store.select([cn.id]);
    const pf0 = store.item("cnP").frame;
    pointer("pointerdown", screenOf(...cnAt(1)));
    pointer("pointermove", screenOf(pf0[0] + 20, pf0[1] + 20));
    pointer("pointermove", screenOf(pf0[0] + 1, pf0[1] + 1));
    const markers = document.querySelectorAll(".overlay .site").length, active = !!document.querySelector(".overlay .site.active");
    pointer("pointerup", screenOf(pf0[0] + 1, pf0[1] + 1));
    await settle();
    check(markers >= 8 && active, "connection points show while an end is dragged", `${markers} ${active}`);
    check(store.item(cn.id).end_link?.item === "cnP" && store.item(cn.id).end_link.site === "c0" && near(cnAt(1)[0], pf0[0], 1e-6),
      "dropping the end on a picture's corner attaches it there", JSON.stringify(store.item(cn.id).end_link));
    await drag([pf0[0] + 30, pf0[1] + 30], [pf0[0] + 60, pf0[1] + 50], { metaKey: true, ctrlKey: true });   // move the picture
    check(near(cnAt(1)[0], store.item("cnP").frame[0], 1e-6) && near(cnAt(1)[1], store.item("cnP").frame[1], 1e-6),
      "the end follows the picture", JSON.stringify(cnAt(1)));
    store.select([cn.id]);
    inspector.render();
    check(/Start: attached to the middle of side 2 of Rectangle/.test(document.getElementById("inspector").textContent),
      "the panel says where each end is attached", document.querySelector("#inspector .link-row")?.textContent);
    // ⌘ drops an end without attaching; dragging the arrow itself lets go of both objects
    const pf1 = store.item("cnP").frame;
    await drag(cnAt(1), [pf1[0] + 1, pf1[1] + 1], { metaKey: true, ctrlKey: true });
    check(!store.item(cn.id).end_link, "holding ⌘ drops an end without attaching it", JSON.stringify(store.item(cn.id).end_link));
    app.run("undo");
    // (a quarter of the way along: the middle is the handle that bends it)
    const cnMid = [cnAt(0)[0] + (cnAt(1)[0] - cnAt(0)[0]) / 4, cnAt(0)[1] + (cnAt(1)[1] - cnAt(0)[1]) / 4];
    await drag(cnMid, [cnMid[0] + 15, cnMid[1] + 40], { metaKey: true, ctrlKey: true });
    check(!store.item(cn.id).start_link && !store.item(cn.id).end_link, "moving the arrow on its own detaches it");
    app.run("undo");
    check(store.item(cn.id).start_link && store.item(cn.id).end_link, "undo attaches it again");
    // Dashed outlines: an end can attach to a dot
    const dot = canvas.sitesOf(store.item("cnD")).find((x) => x.key.startsWith("d") && x.key !== "d0m");
    await drag(cnAt(1), [dot.at[0] + 0.5, dot.at[1] + 0.5]);
    check(store.item(cn.id).end_link?.item === "cnD" && /^d\d+m$/.test(store.item(cn.id).end_link.site)
      && near(cnAt(1)[0], dot.at[0], 1e-6), "an end attaches to a dot of a dotted outline", JSON.stringify(store.item(cn.id).end_link));
    // Copies: alone, a copied arrow lets go; copied with its object, it holds the copy
    app.run("duplicate");
    const lone = store.selected()[0];
    check(lone.type === "line" && !lone.start_link && !lone.end_link, "a duplicated arrow on its own isn't attached");
    app.run("delete");
    store.select([cn.id, "cnR"]);
    app.run("duplicate");
    const copies = store.selected(), cLine = copies.find((i) => i.type === "line"), cRect = copies.find((i) => i.geom === "rect");
    check(cLine?.start_link?.item === cRect?.id && !cLine.end_link, "duplicated with its rectangle, the copy holds the copy",
      JSON.stringify(cLine?.start_link));
    store.setPage(cnPage);
    await app.run("deletePage");
    store.setPage(0);

    // Unsaved work from earlier sessions: delete one copy, then all, from the recovery offer
    await rpc("autosave", store.doc, "selftest-old-1");
    await rpc("autosave", store.doc, "selftest-old-2");
    app.offerRecovery(await rpc("autosaved", store.autosaveKey));
    const recDlg = [...document.querySelectorAll("dialog[open]")].pop();
    const recCount = () => recDlg?.querySelectorAll(".recovery-list li").length;
    check(recCount() === 2 && /2 pages|1 page/.test(recDlg.textContent), "the recovery offer lists unsaved documents and what's in them",
      recDlg?.textContent.slice(0, 200));
    recDlg.querySelector('.recovery-list button[aria-label^="Delete"]').click();
    await until(() => recCount() === 1);
    check(recCount() === 1, "Delete removes one copy (after a warning)");
    [...recDlg.querySelectorAll("button")].find((b) => b.textContent === "Delete all").click();
    await until(() => !recDlg.open);
    check(!recDlg.open && (await rpc("autosaved", store.autosaveKey)).length === 0, "Delete all removes the rest and closes the offer");
    await rpc("autosave", store.doc, "selftest-old-3");
    await app.run("preferences");
    const prefDlg = [...document.querySelectorAll("dialog[open]")].pop();
    await until(() => /1 unsaved document/.test(prefDlg.textContent));
    check(/1 unsaved document from earlier sessions/.test(prefDlg.textContent), "Settings says how much unsaved work is kept");
    [...prefDlg.querySelectorAll("button")].find((b) => b.textContent === "Delete all…").click();
    await until(() => /No unsaved work/.test(prefDlg.textContent));
    check(/No unsaved work/.test(prefDlg.textContent) && (await rpc("autosaved", store.autosaveKey)).length === 0,
      "and Delete all there clears it");
    prefDlg.close();

    // Export, save and reopen
    if (out) {
      const res = await rpc("export", store.doc, { base: `${out}/selftest`, formats: ["pdf", "svg", "png"], dpi: 150,
        transparent: true, pages: [0], doc_path: null });
      check(res.files.length === 3, "export wrote PDF, SVG and PNG", res.files.join(", "));
      const saved = await rpc("save_document", store.doc, `${out}/selftest.figasm`);
      const reopened = await rpc("open_document", saved.path);
      check(reopened.doc.pages[0].items.length === store.doc.pages[0].items.length, "saved document reopens with every object");
      const pf2 = await rpc("preflight", store.doc, { pages: [0] });
      check(pf2.summary.smallest_text_pt > 0, "pre-export check reports the smallest text", JSON.stringify(pf2.summary));
    }
    store.select([]);
    canvas.fit();
    if (params.get("finalSelect") === "curve") {
      // Leave a curve selected so a screenshot shows its handles
      const curve = store.items().find((i) => i.type === "line" && i.curve === "smooth" && i.points.length > 2);
      if (curve) { store.select([curve.id]); canvas.setZoom(3, ...canvas.toScreen(curve.points[1][0], curve.points[1][1])); }
    }
    if (["star", "shapes"].includes(params.get("finalSelect"))) {
      // Leave the star selected (its yellow handle and Shape settings showing), and the Shapes
      // menu open for "shapes"
      const s = store.items().find((i) => i.geom === "star5");
      if (s) { store.select([s.id]); canvas.setZoom(4, ...canvas.toScreen(s.frame[0] + 30, s.frame[1] + 30)); }
      if (params.get("finalSelect") === "shapes") setTimeout(() => document.getElementById("shapes-button").click(), 300);
    }
    // The View menu open, or Preferences (its rulers, grid and guides settings)
    if (params.get("finalSelect") === "viewmenu") document.getElementById("rtab-view").click();
    if (params.get("finalSelect") === "arrange") {
      // Two objects selected, with the Arrange tab open in the ribbon and the panel
      store.select(store.items().filter((i) => i.type === "shape" && !i.textbox).slice(0, 2).map((i) => i.id));
      document.getElementById("rtab-arrange").click();
    }
    if (params.get("finalSelect") === "prefs") setTimeout(() => app.run("preferences"), 300);
    if (params.get("finalSelect") === "connect") {
      // An arrow joining a rectangle to an ellipse, and another on its way to a dotted triangle
      app.run("addPage");
      await settle();
      const sk = { color: "#000000", width: 1.5, dash: "solid", cap: "round", join: "round", opacity: 1 };
      store.update("Connect shot", (doc) => doc.pages[store.pageIndex].items.push(
        { id: "shA", type: "shape", geom: "rect", frame: [80, 120, 110, 70], rot: 0, fill: null, stroke: sk },
        { id: "shB", type: "shape", geom: "ellipse", frame: [300, 100, 100, 100], rot: 0, fill: null, stroke: sk },
        { id: "shC", type: "shape", geom: "triangle", frame: [180, 290, 130, 110], rot: 0, fill: null,
          stroke: { ...sk, width: 2, dash: "sysDot" } }));
      await settle();
      canvas.setZoom(1.6, ...canvas.toScreen(250, 250));
      canvas.setTool("arrow");
      await drag([190.5, 155.5], [300.5, 150.5]);
      store.select([]);
      canvas.setTool("arrow");
      pointer("pointerdown", screenOf(350.4, 200.4));
      for (const f of [0.3, 0.7, 1]) pointer("pointermove", screenOf(350 + (246 - 350) * f, 200 + (292 - 200) * f));
    }
    if (params.get("finalSelect") === "recovery") {
      await rpc("autosave", store.doc, "selftest-shot-1");
      await rpc("autosave", store.doc, "selftest-shot-2");
      app.offerRecovery(await rpc("autosaved", store.autosaveKey));
    }
    if (keepAids) {
      // Leave the layout-aids page with the grid and guides showing: "guides" mid-way through
      // dragging a box into an equal gap, "guidelist" with the Page panel's list of guides
      store.setPage(aidsPage);
      await app.savePrefs({ show_grid: true });
      store.update("Guides for screenshot", (doc) => { doc.pages[aidsPage].guides = { x: [330, 490], y: [500, 540] }; });
      await settle();
      if (params.get("finalSelect") === "guides") {
        canvas.setZoom(2.2, ...canvas.toScreen(420, 520));
        const from = [410, 520];
        pointer("pointerdown", screenOf(...from));
        for (const f of [0.3, 0.6, 1]) pointer("pointermove", screenOf(from[0] + 2.5 * f, from[1] + 30 + 2 * f));
        pointer("pointermove", screenOf(from[0] + 1.5, from[1] + 1.2));
      } else canvas.fit();
    }
    await settle();
  } catch (err) {
    log(false, "self-test crashed", `${err.message} ${err.stack}`);
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`SELFTEST DONE ${results.length - failed}/${results.length} passed`);
  window.__selftest = { results, failed, info };
  document.body.dataset.selftest = failed ? "fail" : "pass";
}

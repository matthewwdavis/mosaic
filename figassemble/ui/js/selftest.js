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
    // In a 1440 px window (the app's own size) the toolbar is one row and nothing spills off the side
    const bar = document.getElementById("toolbar");
    const rowTops = new Set([...bar.children].map((g) => Math.round(g.getBoundingClientRect().top)));
    const used = [...bar.children].reduce((sum, g) => sum + (g.classList.contains("spacer") ? 0 : g.getBoundingClientRect().width), 0);
    info.toolbarRoom = Math.round(bar.clientWidth - used);    // px left over on the row
    check(rowTops.size === 1 && document.body.scrollWidth <= window.innerWidth + 1, "the toolbar fits the window on one row",
      `${rowTops.size} rows; groups ` + [...bar.children].map((g) => `${g.getAttribute("aria-label") || g.className}:`
        + Math.round(g.getBoundingClientRect().width)).join(" "));
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
    const corner0 = screenOf(0, 0);
    key("r", { metaKey: true, ctrlKey: true });
    await until(() => !rulerTop.offsetParent);
    const corner1 = screenOf(0, 0);
    check(!rulerTop.offsetParent && near(corner0[0], corner1[0], 0.5) && near(corner0[1], corner1[1], 0.5),
      "⌘R hides the rulers, and the page stays where it was", `${corner0} -> ${corner1}`);
    key("r", { metaKey: true, ctrlKey: true });
    await until(() => rulerTop.offsetParent);
    check(rulerTop.offsetParent && app.prefs.show_rulers, "⌘R shows them again");

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
    const snapBtn = document.querySelector('#toolbar [data-cmd="toggleSnap"]');
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

    // A new page starts with this page's guides; Remove all clears them
    const guidesNow = JSON.stringify(pg().guides);
    app.run("addPage");
    check(JSON.stringify(pg().guides) === guidesNow, "a new page starts with the same guides", `${JSON.stringify(pg().guides)} vs ${guidesNow}`);
    await app.run("deletePage");
    store.setPage(aidsPage);
    inspector.render();
    pageButton("Remove all")?.click();
    check(pg().guides.x.length + pg().guides.y.length === 0, "Remove all clears the page's guides", JSON.stringify(pg().guides));

    // The View menu shows and hides the rulers, grid and guides
    const viewBtn = document.getElementById("view-button"), viewMenu = document.getElementById("view-menu");
    viewBtn.click();
    check(!viewMenu.hidden && document.activeElement?.getAttribute("role") === "menuitemcheckbox", "the View menu opens with the focus in it");
    const gridItem = viewMenu.querySelector('[data-pref="show_grid"]');
    check(gridItem?.getAttribute("aria-checked") === "false", "it shows the grid is off");
    gridItem.click();
    await until(() => app.prefs.show_grid === true);
    check(viewMenu.hidden && gridItem.getAttribute("aria-checked") === "true", "choosing Grid shows the grid and closes the menu");
    key("'", { metaKey: true, ctrlKey: true });
    await until(() => app.prefs.show_grid === false);
    keepAids = ["guides", "guidelist"].includes(params.get("finalSelect"));
    if (!keepAids) { store.setPage(aidsPage); await app.run("deletePage"); }
    store.setPage(0);

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
    if (params.get("finalSelect") === "viewmenu") setTimeout(() => document.getElementById("view-button").click(), 300);
    if (params.get("finalSelect") === "prefs") setTimeout(() => app.run("preferences"), 300);
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

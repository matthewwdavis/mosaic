// Scripted run-through of the editor, loaded only with ?selftest=1 (used by tools/ui_selftest.py).
// Drives the real UI through pointer and keyboard events and reports through console.log.

import { rpc } from "./api.js";
import { canvas, findDeep, visionMatrix } from "./canvas.js";
import { inspector } from "./inspector.js";
import { panels } from "./panels.js";
import { rulers } from "./rulers.js";
import { store } from "./store.js";
import { pageScale } from "./scalebar.js";
import { apply, frameMatrix, isMac, itemBBox, itemsBBox, lengthText, lineMidpoints, luminance, parseHex, shapeCatalog, toUnit } from "./util.js";
import { restyle } from "./textstyles.js";
import { sameCommand } from "./selectsame.js";
import { ringsOf, toLocal, toPageOf } from "./pen.js";
import { cropMenu, cropToDrawnShape, cropToRatio, cropToSize, parseRatio, resetCrop } from "./crop.js";

const MMPT = 72 / 25.4;
const gRectFor = (id, x, y, w, hh) => ({ id, type: "shape", geom: "rect", frame: [x, y, w, hh], rot: 0, flip_h: false, flip_v: false,
  stroke: { color: "#000000", width: 1, dash: "solid", cap: "flat", join: "miter", opacity: 1 }, fill: null });
const near = (a, b, tol = 0.05) => Math.abs(a - b) < tol;
// The publishers every journal list is grouped by, in order, as prose's Journal menu has them
// (your own journals, "My journals", left out: the self-test may run with some)
const PUBLISHER_GROUPS = "AAAS (Science),BMC (Springer Nature),Cell Press,Cold Spring Harbor Laboratory Press,"
  + "Genetics Society of America,In house,National Academy of Sciences,Oxford University Press,PLOS,Springer Nature,Wiley";
const groupsOf = (select) => [...(select?.querySelectorAll("optgroup") || [])].map((g) => g.label).filter((g) => g !== "My journals");
const optionsIn = (select, group) => [...([...(select?.querySelectorAll("optgroup") || [])].find((g) => g.label === group)?.children || [])]
  .map((o) => o.value);
// Set a properties-panel dropdown by its label, as a person would: a picture menu by opening it and
// clicking the choice (a greyed-out one does nothing)
async function choose(label, value) {
  inspector.render();
  const l = [...document.querySelectorAll("#inspector label")].find((x) => x.textContent === label);
  const field = l && document.getElementById(l.htmlFor);
  if (!field) return false;
  if (field.classList.contains("pic-select")) {
    field.click();
    [...document.querySelectorAll(".context-menu .menu-item")].find((b) => b.dataset.value === String(value))?.click();
    document.querySelector(".context-menu") && document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  } else {
    field.value = value;
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }
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
const ONLY = Symbol("only");   // ?only=objects runs one part on its own
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

// The Objects list is a tree. Dragging a row moves the object: the row follows the pointer, the
// others slide apart and the page draws the new order as it goes. Rows go into and out of groups
// (Option+arrows too), onto a page in the Pages list, and not in front of a clipping mask's
// shape. The Pages list drags the same way.
async function objectsListChecks(app) {
  const startPage = store.pageIndex, pageCount = store.doc.pages.length;
  app.run("addPage");
  await settle();
  const page = store.pageIndex, olRect = (id, x, y) => ({ ...gRectFor(id, x, y, 60, 40), fill: { color: "#e69f00", opacity: 1 } });
  store.update("Objects list parts", (doc) => doc.pages[page].items.push(olRect("olA", 40, 40), olRect("olB", 70, 60), olRect("olC", 100, 80)));
  await settle();
  const list = document.querySelector(".layer-list"), row = (id) => document.getElementById(`layer-opt-${id}`);
  const ids = () => store.items().map((i) => i.id).join(), shown = () => [...list.querySelectorAll("li[data-key]")].map((li) => li.dataset.key).join();
  const drawn = () => [...canvas.itemsLayer.children].map((g) => g.dataset.id).join();
  const mid = (el, fy = 0.5) => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height * fy]; };
  const ptr = (el, type, [x, y], opts = {}) => el.dispatchEvent(new PointerEvent(type, { clientX: x, clientY: y, bubbles: true,
    cancelable: true, button: 0, buttons: type === "pointerup" ? 0 : 1, pointerId: 1, pointerType: "mouse", ...opts }));
  // Press a row (in its middle) and move to a point in steps, without letting go. The moves
  // follow each other at once: a hidden window's slow timers would otherwise open a closed group
  // held over for a moment
  const hold = async (el, to, steps = 6) => {
    const from = mid(el);
    ptr(el, "pointerdown", from);
    for (let i = 1; i <= steps; i++) ptr(list, "pointermove", [from[0] + ((to[0] - from[0]) * i) / steps, from[1] + ((to[1] - from[1]) * i) / steps]);
  };
  const letGo = async (to) => { ptr(list, "pointerup", to); await settle(); };
  check(shown() === "olC,olB,olA", "the Objects list shows the page's objects front to back", shown());

  // To the front: the rows slide apart, the page shows the new order, one undo step
  const above = mid(row("olC"), -0.2);
  await hold(row("olA"), above);
  const gapOf = (li) => parseFloat(/translateY\(([\d.]+)px\)/.exec(li?.style.transform || "")?.[1] || 0);
  const slid = [...list.querySelectorAll("li[data-key]")].filter((li) => Math.abs(gapOf(li) - row("olB").offsetHeight) < 1).length;
  check(document.querySelector(".drag-held") && row("olA").classList.contains("drag-hidden") && slid === 2 && drawn() === "olB,olC,olA",
    "dragging a row: it follows the pointer, the other rows slide apart and the page draws the new order", `slid=${slid} drawn=${drawn()}`);
  const steps = store.history.length;
  await letGo(above);
  check(ids() === "olB,olC,olA" && store.history.length === steps + 1 && store.history[steps].label === "Move in the Objects list"
    && store.selection.join() === "olA" && shown() === "olA,olC,olB" && !document.querySelector(".drag-held"),
  "letting go there brings it to the front, in one undo step, still selected", `${ids()} ${store.history[steps]?.label}`);
  await app.run("undo");
  check(ids() === "olA,olB,olC", "Undo puts it back", ids());
  // Escape cancels: as it was, with nothing to undo
  await hold(row("olC"), mid(row("olA"), 0.9));
  const cancelSteps = store.history.length, wasDrawn = drawn();
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  await settle();
  check(wasDrawn === "olC,olA,olB" && ids() === "olA,olB,olC" && drawn() === "olA,olB,olC" && store.history.length === cancelSteps
    && !document.querySelector(".drag-held") && shown() === "olC,olB,olA", "Escape cancels the drag: the order and the page as they were",
  `${wasDrawn} ${ids()} ${drawn()}`);

  // Groups open in the list; a row dragged between a group's parts goes into the group
  store.select(["olB", "olC"]);
  await app.run("group");
  const gid = store.items()[1]?.id, grp = () => store.items().find((i) => i.id === gid);
  check(row(gid)?.getAttribute("aria-expanded") === "false" && !row("olB"), "a group is one row, closed", shown());
  row(gid).querySelector(".twisty").click();
  check(shown() === `${gid},olC,olB,olA` && row("olC").getAttribute("aria-level") === "2", "its triangle opens it, its parts indented under it", shown());
  const intoGap = mid(row("olB"));
  await hold(row("olA"), intoGap);
  await letGo(intoGap);
  check(grp()?.items.map((i) => i.id).join() === "olB,olA,olC" && store.items().length === 1 && store.scope.join() === gid
    && store.selection.join() === "olA" && !canvas.els.get("olA")?.g.classList.contains("outside-scope"),
  "dragged between a group's parts, it goes into the group there, picked inside it", `${grp()?.items.map((i) => i.id)} scope=${store.scope}`);
  // Out again: below the group's last part, and over to the left
  const below = mid(row("olB"), 1.5);
  await hold(row("olA"), [below[0] - 24, below[1]]);
  await letGo([below[0] - 24, below[1]]);
  check(ids() === `olA,${gid}` && grp()?.items.map((i) => i.id).join() === "olB,olC" && !store.scope.length && store.selection.join() === "olA",
    "dragged below the group and to the left, it comes out, just behind the group", `${ids()} ${grp()?.items.map((i) => i.id)}`);
  // Held over the middle of a closed group: into it, in front of its parts
  row(gid).querySelector(".twisty").click();
  const onGroup = mid(row(gid), 1);
  await hold(row("olA"), onGroup);
  const marked = row(gid)?.classList.contains("drop-into");
  await letGo(onGroup);
  check(marked && grp()?.items.map((i) => i.id).join() === "olB,olC,olA", "held over a closed group's middle, it goes in, in front of its parts",
    `${marked} ${grp()?.items.map((i) => i.id)}`);
  // Option+Left: out of its group, just behind it; Option+Right: into the group above, at its back
  const listKey = (k, opts = {}) => { list.focus(); list.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...opts })); };
  listKey("ArrowLeft", { altKey: true });
  await settle();
  check(ids() === `olA,${gid}` && !store.scope.length && store.selection.join() === "olA", "Option+Left in the list moves it out of its group", ids());
  listKey("ArrowRight", { altKey: true });
  await settle();
  check(grp()?.items.map((i) => i.id).join() === "olA,olB,olC" && store.scope.join() === gid, "Option+Right moves it into the group above, at the back",
    grp()?.items.map((i) => i.id).join());
  // A closed group held over for a moment opens, so it can go anywhere among the parts
  listKey("ArrowLeft", { altKey: true });
  await settle();
  row(gid).querySelector(".twisty").click();
  await hold(row("olA"), mid(row(gid), 1));
  await wait(900);
  const opened = row(gid)?.getAttribute("aria-expanded") === "true" && row("olC") && !row("olC").classList.contains("drag-hidden");
  const gapAt = [mid(row("olB"))[0], list.getBoundingClientRect().top + row("olB").offsetTop + row("olB").offsetHeight / 2];
  for (let i = 1; i <= 4; i++) { ptr(list, "pointermove", gapAt); await wait(16); }
  await letGo(gapAt);
  check(opened && grp()?.items.map((i) => i.id).join() === "olB,olA,olC", "a closed group held over opens, and takes it among its parts",
    `${opened} ${grp()?.items.map((i) => i.id)}`);

  // A clipping mask's shape stays on top: dropped onto the mask's row, an object goes in just
  // under the shape; no gap opens above the shape; Bring to front leaves it on top; it doesn't drag
  store.select([]);
  store.update("Clip parts", (doc) => doc.pages[page].items.push(olRect("olZ", 180, 190), { id: "olClip", type: "group", name: "", clip: true,
    items: [olRect("olX", 200, 200), olRect("olY", 220, 210), { ...olRect("olM", 210, 205), geom: "ellipse" }] }));
  await settle();
  const clip = () => store.items().find((i) => i.id === "olClip")?.items.map((i) => i.id).join();
  const onClip = mid(row("olClip"), 1);
  await hold(row("olZ"), onClip);
  await letGo(onClip);
  check(clip() === "olX,olY,olZ,olM" && store.scope.join() === "olClip", "dropped onto a clipping mask's row, it goes in just under its shape", clip());
  await hold(row("olX"), mid(row("olM"), 0.2));
  const slidRow = (id) => gapOf(row(id)) > 0, aboveShape = slidRow("olM") && !slidRow("olClip");
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  await settle();
  check(!aboveShape && clip() === "olX,olY,olZ,olM", "no gap opens above a clipping mask's shape inside it", clip());
  store.select(["olY"]);
  await app.run("bringToFront");
  check(clip() === "olX,olZ,olY,olM", "Bring to front inside a clipping mask leaves its shape on top", clip());
  await hold(row("olM"), mid(row("olX"), 1.5));
  await letGo(mid(row("olX"), 1.5));
  check(clip() === "olX,olZ,olY,olM" && !document.querySelector(".drag-held"), "the shape itself doesn't drag", clip());

  // Onto another page in the Pages list: it goes there, in front, where it was on the page;
  // a label attached to something left behind lets go
  app.run("addPage");
  await settle();
  const other = store.pageIndex;
  store.setPage(page);
  await settle();
  store.update("Label", (doc) => doc.pages[page].items.push({ ...olRect("olLabel", 30, 20), attach: { to: gid, corner: "tl", dx: -10, dy: -20 } }));
  await settle();
  const before = JSON.stringify(store.item("olLabel").frame), pageRow = () => document.querySelector(`.page-list li[data-index="${other}"]`);
  await hold(row("olLabel"), mid(pageRow()), 8);
  const target = pageRow().classList.contains("drop-target"), gone = !drawn().includes("olLabel");
  await letGo(mid(pageRow()));
  const moved = store.doc.pages[other].items.find((i) => i.id === "olLabel");
  check(target && gone && moved && JSON.stringify(moved.frame) === before && !moved.attach && !store.item("olLabel") && store.pageIndex === page,
    "dropped on another page in the Pages list, it moves there, where it was, and lets go of its panel", `${target} ${gone} ${JSON.stringify(moved)}`);
  await app.run("undo");
  check(store.item("olLabel") && !store.doc.pages[other].items.length, "and Undo brings it back", ids());

  // The Pages list: drag a page above another
  const names = () => store.doc.pages.map((p) => p.name).join("|"), namesBefore = names();
  const firstRow = document.querySelector(`.page-list li[data-index="${page}"]`), onFirst = mid(firstRow, 0.2);
  await hold(pageRow(), onFirst);
  const pageSlid = [...document.querySelectorAll(".page-list li")].some((li) => Math.abs(gapOf(li) - firstRow.offsetHeight) < 1);
  await letGo(onFirst);
  const want = store.doc.pages.length === pageCount + 2 && namesBefore.split("|");
  if (want) want.splice(page, 0, want.splice(other, 1)[0]);
  check(pageSlid && want && names() === want.join("|") && store.pageIndex === page, "dragging a page in the Pages list moves it, the pages sliding apart",
    `${pageSlid} ${names()}`);
  await app.run("undo");
  // Leave as found
  for (const p of [...store.doc.pages].slice(pageCount).reverse()) {
    store.setPage(store.doc.pages.indexOf(p));
    await app.run("deletePage");
  }
  store.setPage(startPage);
  await settle();
}

// Selecting several objects: ⌘-click (Ctrl-click) adds an object, or takes a selected one away if
// let go without a drag; a ⌘-drag carries the whole selection without snapping; a ⌘-click that
// misses keeps the selection, and a ⌘-drag on empty page adds a box's objects. With Option (Alt)
// a box takes what it touches. Select Same picks what shares a look: from the right-click menu's
// submenu (by pointer and by keyboard), the Mac menu bar's Edit menu and command search.
async function selectionChecks(app) {
  const startPage = store.pageIndex;
  app.run("addPage");
  await settle();
  const page = store.pageIndex;
  const black = (width) => ({ color: "#000000", width, dash: "solid", cap: "flat", join: "miter", opacity: 1 });
  const box = (id, geom, x, y, fill, stroke) => ({ id, type: "shape", geom, frame: [x, y, 60, 40], rot: 0, flip_h: false,
    flip_v: false, stroke, fill: fill ? { color: fill, opacity: 1 } : null });
  const label = (id, y, t, font, size, color) => ({ id, type: "shape", geom: "rect", textbox: true, frame: [300, y, 80, 20], rot: 0,
    flip_h: false, flip_v: false, stroke: null, fill: null, text: { paragraphs: [{ align: "l", runs: [{ t, font, size, bold: false,
      italic: false, color }] }], insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" } });
  store.update("Objects to select", (doc) => doc.pages[page].items.push(
    box("sA", "rect", 40, 40, "#e69f00", black(1)), box("sB", "rect", 140, 40, "#E69F00", black(1)),
    box("sC", "rect", 260, 40, "#56b4e9", black(2)), box("sE", "ellipse", 400, 330, "#e69f00", null),
    { id: "sL", type: "line", points: [[40, 160], [200, 260]], arrow_start: null, arrow_end: null, stroke: black(1) },
    label("sT", 160, "Red label", "Helvetica", 7, "#cc0000"), label("sU", 200, "Small label", "Helvetica", 6, "#000000"),
    label("sV", 240, "Arial label", "Arial", 7, "#000000")), { select: [] });
  canvas.fit();
  await settle();
  const add = isMac ? { metaKey: true } : { ctrlKey: true };   // ⌘ on a Mac, where Control-click is a right-click
  const sel = () => store.selection.join();
  const clickAt = (pt, opts = {}) => {
    pointer("pointerdown", screenOf(...pt), opts);
    pointer("pointerup", screenOf(...pt), { ...opts, buttons: 0 });
  };
  const mid = (id) => { const f = store.item(id).frame; return [f[0] + f[2] / 2, f[1] + f[3] / 2]; };
  const left = (id) => store.item(id).frame[0];
  const empty = [220, 120];

  clickAt(mid("sA"));
  clickAt(mid("sB"), add);
  check(sel() === "sA,sB", "⌘-click (Ctrl-click) adds an object to the selection", sel());
  clickAt(mid("sA"), add);
  check(sel() === "sB", "⌘-click on a selected object takes it away", sel());
  // A guide 1 pt beside where they land catches a plain drag, not a ⌘-drag (each pressed on sA
  // away from the guide, which lies over its middle: there a plain press would take the guide)
  const dx = 30.3, [a0, b0] = [left("sA"), left("sB")], grab = () => [left("sA") + 10, mid("sA")[1]];
  store.update("A guide", (doc) => { doc.pages[page].guides = { x: [a0 + dx + 1], y: [] }; });
  await settle();
  await drag(grab(), [grab()[0] + dx, grab()[1]], add);
  check(sel() === "sB,sA" && near(left("sA"), a0 + dx, 0.01) && near(left("sB"), b0 + dx, 0.01),
    "⌘-drag on another object adds it and moves them together, without snapping", `${sel()} ${left("sA")} ${left("sB")}`);
  await app.run("undo");
  await drag(grab(), [grab()[0] + dx, grab()[1]]);
  check(sel() === "sB,sA" && near(left("sA"), a0 + dx + 1, 0.01) && near(left("sB"), b0 + dx + 1, 0.01),
    "the same drag without ⌘ snaps to the guide", `${sel()} ${left("sA")} ${left("sB")}`);
  await app.run("undo");
  store.update("No guide", (doc) => { doc.pages[page].guides = { x: [], y: [] }; });
  await drag(mid("sA"), [mid("sA")[0] + 20, mid("sA")[1]], add);
  check(sel() === "sB,sA" && near(left("sA"), a0 + 20, 0.01) && near(left("sB"), b0 + 20, 0.01),
    "⌘-drag on a selected object moves the selection, and keeps it selected", `${sel()} ${left("sA")} ${left("sB")}`);
  await app.run("undo");
  clickAt(empty, add);
  check(sel() === "sB,sA", "a ⌘-click that misses keeps the selection", sel());
  clickAt(empty);
  check(sel() === "", "a plain click on empty page clears it", sel());
  clickAt(mid("sA"));
  await drag([250, 30], [330, 90], add);
  check(sel() === "sA,sC", "⌘-drag on empty page adds what the box holds", sel());

  // With Option (Alt), a box takes what it touches: a slanted line only where the box crosses it
  const boxed = async (from, to, opts = {}) => {
    clickAt(empty);
    await drag(from, to, opts);
    return sel();
  };
  check(await boxed([90, 30], [170, 90]) === "", "a box takes only what's wholly inside it", sel());
  clickAt(empty);
  pointer("pointerdown", screenOf(90, 30), { altKey: true });
  pointer("pointermove", screenOf(170, 90), { altKey: true });
  const solid = !!document.querySelector(".marquee.touch");
  pointer("pointerup", screenOf(170, 90), { altKey: true, buttons: 0 });
  await settle();
  check(solid && sel() === "sA,sB", "with Option (Alt) it takes what it touches, its edge drawn solid meanwhile", `${solid} ${sel()}`);
  check(await boxed([170, 165], [195, 185], { altKey: true }) === "", "a box beside a slanted line, within its bounds, doesn't touch it", sel());
  check(await boxed([110, 190], [130, 215], { altKey: true }) === "sL", "a box across the line does", sel());

  // Select Same
  const same = async (ids, what) => { store.select(ids); await app.run(sameCommand(what)); return sel(); };
  check(await same(["sA"], "fill") === "sA,sB,sE", "Select same fill colour: the shapes filled the same", sel());
  check(await same(["sA", "sC"], "fill") === "sA,sB,sC,sE", "with two selected, the fills of either", sel());
  check(await same(["sA"], "line") === "sA,sB,sC,sL", "line colour: shapes and lines in black", sel());
  check(await same(["sA"], "width") === "sA,sB,sL", "line width: the 1 pt ones", sel());
  check(await same(["sA"], "fillLine") === "sA,sB", "fill and line: both the same", sel());
  check(await same(["sT"], "font") === "sT,sU", "font: the texts in Helvetica", sel());
  check(await same(["sT"], "size") === "sT,sV", "font size: the 7 pt texts", sel());
  check(await same(["sU"], "textColour") === "sU,sV", "text colour: the black texts", sel());
  const kinds = [await same(["sA"], "kind"), await same(["sT"], "kind"), await same(["sL"], "kind")];
  check(kinds.join(" ") === "sA,sB,sC sT,sU,sV sL", "kind of object: rectangles, text boxes, lines", kinds.join(" "));
  const noText = await same(["sL"], "font");
  await wait(100);
  check(noText === "sL" && document.getElementById("live").textContent === "Nothing selected has text",
    "with nothing selected that has it, the selection stays and it says so", `${noText} ${document.getElementById("live").textContent}`);
  store.update("Lock and hide", (doc) => { findItem(doc, "sB").locked = true; findItem(doc, "sE").hidden = true; });
  check(await same(["sA"], "fill") === "sA", "locked and hidden objects are left out", sel());
  store.update("Unlock and show", (doc) => { delete findItem(doc, "sB").locked; delete findItem(doc, "sE").hidden; });
  store.select(["sB", "sC"]);
  await app.run("group");
  const grp = store.selection[0];
  const outside = await same(["sA"], "fill");
  canvas.enterGroup(grp);
  const inside = await same(["sB"], "kind");
  store.exitGroup();
  await app.run("undo");
  check(outside === "sA,sE" && inside === "sB,sC", "a group's parts are compared only while working inside it", `${outside} | ${inside}`);

  // From the right-click menu: Select same ▸ opens beside it
  const menuEl = () => document.querySelector(".context-menu:not(.submenu)"), subEl = () => document.querySelector(".context-menu.submenu");
  const itemIn = (m, text) => [...(m?.querySelectorAll(".menu-item") || [])].find((b) => b.querySelector(".menu-label").textContent === text);
  const menuKey = (k) => document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  const hover = (el) => el?.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, pointerType: "mouse" }));
  store.select([]);
  const at = screenOf(...mid("sA"));
  pointer("pointerdown", at, { button: 2, buttons: 2 });
  pointer("pointerup", at, { button: 2, buttons: 0 });
  canvas.stage.dispatchEvent(new MouseEvent("contextmenu", { clientX: at[0], clientY: at[1], bubbles: true, cancelable: true, button: 2 }));
  await until(() => menuEl());
  const sameLine = itemIn(menuEl(), "Select same");
  check(sameLine?.getAttribute("aria-haspopup") === "menu" && sameLine.querySelector(".submenu-arrow"), "an object's menu has Select same ▸");
  hover(sameLine);
  const sr = subEl()?.getBoundingClientRect(), mr = menuEl()?.getBoundingClientRect();
  const beside = !!sr && (Math.abs(sr.left - mr.right) < 6 || Math.abs(sr.right - mr.left) < 6) && sr.top >= 0 && sr.bottom <= window.innerHeight;
  const names = [...(subEl()?.querySelectorAll(".menu-label") || [])].map((l) => l.textContent).join("|");
  check(sameLine?.getAttribute("aria-expanded") === "true" && beside
    && names === "Fill colour|Line colour|Line width|Fill and line|Font|Font size|Text colour|Kind of object",
  "pointing at it opens its submenu beside the menu", `${beside} ${names}`);
  hover(itemIn(menuEl(), "Copy style"));
  await until(() => !subEl(), 1000);
  check(!subEl() && sameLine?.getAttribute("aria-expanded") === "false", "pointing at another line closes it after a moment");
  hover(sameLine);
  menuKey("ArrowDown");
  check(!subEl() && document.activeElement === itemIn(menuEl(), "Copy style"), "and so does moving on with the arrow keys");
  sameLine?.click();
  check(subEl() && document.activeElement === itemIn(subEl(), "Fill colour"), "clicking it opens it, ready for the keyboard");
  itemIn(subEl(), "Fill colour")?.click();
  check(!menuEl() && !subEl() && sel() === "sA,sB,sE", "choosing Fill colour selects the shapes filled the same and closes the menus", sel());
  store.select(["sT"]);
  key("F10", { shiftKey: true });
  await until(() => menuEl());
  menuKey("s");
  const onSame = document.activeElement === itemIn(menuEl(), "Select same");
  menuKey("ArrowRight");
  const inSub = document.activeElement === itemIn(subEl(), "Fill colour");
  menuKey("ArrowLeft");
  const leftOut = !subEl() && document.activeElement === itemIn(menuEl(), "Select same");
  menuKey("ArrowRight");
  menuKey("End");
  const last = document.activeElement === itemIn(subEl(), "Kind of object");
  menuKey("Escape");
  const escaped = !subEl() && !!menuEl() && document.activeElement === itemIn(menuEl(), "Select same");
  menuKey("Enter");
  menuKey("End");
  menuKey("Enter");
  check(onSame && inSub && leftOut && last && escaped && !menuEl() && sel() === "sT,sU,sV" && document.activeElement === canvas.stage,
    "by keyboard: S, then → opens it, ← and Escape come back, Enter chooses", `${onSame} ${inSub} ${leftOut} ${last} ${escaped} ${sel()}`);
  // The Mac menu bar's Edit menu, and command search
  const editSame = app.menuSpec().find((m) => m.title === "Edit").items.find((it) => it.title === "Select Same");
  check(editSame?.items.map((it) => it.title).join("|") === "Fill Colour|Line Colour|Line Width|Fill and Line|Font|Font Size|Text Colour|Kind of Object"
    && editSame.items.every((it) => app.commands[it.action]), "Edit ▸ Select Same lists them in the Mac menu bar",
  editSame?.items.map((it) => it.title).join("|"));
  app.run("commandSearch");
  const search = document.querySelector("dialog.command-search .cs-input");
  search.value = "select same";
  search.dispatchEvent(new Event("input", { bubbles: true }));
  const found = [...document.querySelectorAll("dialog.command-search .cs-item span:first-child")].map((s) => s.textContent);
  document.querySelector("dialog.command-search")?.close();
  check(found.length === 8 && found.includes("Select same fill colour"), "command search finds them", found.join("|"));

  // Leave as found
  store.setPage(page);
  await app.run("deletePage");
  store.setPage(startPage);
  await settle();
}

// Linked pictures follow their files: one re-saved under the same name, as R does, updates by
// itself (the editor looks every 2 s while its window shows), keeping its place and scale. Undo
// puts back the version before, which stays until the file is saved again; redo takes the update
// back. (Whether the window shows is set here, so this runs the same in the smoke test's hidden
// window; and waits are in elapsed time, since a hidden window's timers run slowly.)
// Help > Report a Problem: the dialog says what the report holds and takes a note; the Help dialog
// leads to it. (The report file itself is checked by tests/test_diagnostics.py: saving one here
// would leave a file on the Desktop.)
// Size > My Journals…: a journal of your own (a name, widths and a depth) is kept, listed with the
// others, sizes a page, says what's wrong with one that can't be kept, and goes when deleted
async function myJournalsChecks(app) {
  const top = () => [...document.querySelectorAll("dialog[open]")].at(-1);
  const press = (dlg, label) => [...dlg.querySelectorAll("button")].find((b) => b.textContent === label)?.click();
  const before = (await rpc("user_journals")) || [], confirming = app.autoConfirm;
  try {
    await rpc("user_journals_save", []);
    panels.journalsDialog();
    await until(() => top()?.querySelector("h2")?.textContent === "My journals");
    const listDlg = top();
    check(/None yet/.test(listDlg.textContent), "My Journals starts with none");
    const fill = (el, v) => { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })); };
    {
      // Add a Journal ▸ Start from a Journal's Reference Style…, then its figure sizes from the guidelines
      press(listDlg, "Add a Journal…");
      await until(() => top()?.querySelector("h2")?.textContent === "Add a journal");
      const start = top();
      press(start, "Start from a Journal's Reference Style…");
      await until(() => top()?.querySelector("h2")?.textContent === "Start from a journal's reference style");
      const styles = top();
      fill(styles.querySelector("input[type=search]"), "1614-2942");
      await until(() => /Tree Genetics/.test(styles.querySelector(".csl-results")?.textContent || ""));
      check(/Tree Genetics & Genomes/.test(styles.querySelector(".csl-result")?.textContent || ""),
        "Start from a Journal's Reference Style finds Tree Genetics by its ISSN", styles.querySelector(".csl-results").textContent);
      styles.querySelector(".csl-pick").click();
      await until(() => top() === start && start.querySelector("input[type=text]").value);
      check(start.querySelector("input[type=text]").value === "Tree Genetics & Genomes" && /tree-genetics-and-genomes/.test(start.querySelector(".journal-start").textContent),
        "choosing it fills in the journal's name and keeps its reference style and ISSN", start.querySelector(".journal-start").textContent);
      press(start, "Read Figure Sizes from the Author Guidelines…");
      await until(() => top()?.querySelector("h2")?.textContent === "Figure sizes from the author guidelines");
      const guide = top();
      fill(guide.querySelector("input[type=url]"), "http://127.0.0.1:9/author-guidelines");
      press(guide, "Read the Page");
      const said = () => guide.querySelector("[role=status]").textContent;
      await until(() => said() && said() !== "Reading…", 15000);
      check(/couldn't be read/.test(said()) && guide.querySelector("button.primary").disabled,
        "a guidelines page that can't be reached says so in words and offers nothing to use", said());
      guide.close();
      start.close();
      await until(() => top() === listDlg);
    }
    press(listDlg, "Add a Journal…");
    await until(() => top()?.querySelector("h2")?.textContent === "Add a journal");
    let form = top();
    press(form, "Save");   // (nothing filled in)
    await until(() => form.querySelector("[role=alert]").textContent);
    check(/name/i.test(form.querySelector("[role=alert]").textContent) && top() === form,
      "a journal without a name isn't kept, and the form says why", form.querySelector("[role=alert]").textContent);
    fill(form.querySelector("input[type=text]"), "Selftest Journal");
    const rows = form.querySelectorAll(".journal-width");
    fill(rows[0].querySelector("input[type=number]"), "84");
    fill(rows[1].querySelector("input[type=number]"), "174");
    fill(form.querySelector("input[id$=-depth]"), "230");
    press(form, "Save");
    await until(() => top() === listDlg && /Selftest Journal/.test(listDlg.textContent));
    const j = (app.info.journals || []).find((x) => x.name === "Selftest Journal");
    check(j && j.user && j.depth_mm === 230 && j.types.map((t) => t.width_mm).join() === "84,174",
      "a journal of your own is kept and listed with the others", JSON.stringify(j));
    {
      store.select([]);
      const list = fieldByLabel("Journal");
      const all = [...list.querySelectorAll("optgroup")].map((g) => g.label);
      check(optionsIn(list, "My journals").join() === "Selftest Journal" && all.indexOf("My journals") === all.indexOf("In house") + 1,
        "your own journals are listed in a group of their own, My journals, as prose lists them", all.join());
      panels.pageSizeMenu();   // (over the My journals window, which stays open)
      [...document.querySelectorAll(".context-menu .menu-item")].find((b) => b.querySelector(".menu-label").textContent === "Journal")?.click();
      const heads = [...document.querySelectorAll(".context-menu.submenu .menu-heading")].map((x) => x.textContent);
      const next = [...document.querySelectorAll(".context-menu.submenu .menu-heading")].find((x) => x.textContent === "My journals")
        ?.nextElementSibling?.querySelector(".menu-label")?.textContent || "";
      check(heads.includes("My journals") && /^Selftest Journal: /.test(next), "and under a My journals heading in Size ▸ Journal", `${heads.join()}; ${next}`);
      document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));   // (a press elsewhere closes the menu)
    }
    inspector.setJournalSize("Selftest Journal", "Double column");
    await settle();
    const pg = store.page(), mm = 72 / 25.4;
    check(Math.abs(pg.width - 174 * mm) < 0.01 && Math.abs(pg.height - 230 * mm) < 0.01 && pg.preset?.journal === "Selftest Journal",
      "and sizes a page: its width and depth", `${pg.width} x ${pg.height}`);
    press(listDlg, "Add a Journal…");
    await until(() => top()?.querySelector("h2")?.textContent === "Add a journal");
    form = top();
    fill(form.querySelector("input[type=text]"), "Nature");
    fill(form.querySelector(".journal-width input[type=number]"), "90");
    fill(form.querySelector("input[id$=-depth]"), "170");
    press(form, "Save");
    await until(() => form.querySelector("[role=alert]").textContent);
    check(/already listed/.test(form.querySelector("[role=alert]").textContent), "one named like a listed journal isn't kept",
      form.querySelector("[role=alert]").textContent);
    form.close();
    app.autoConfirm = true;
    press(listDlg, "Delete");
    await until(() => /None yet/.test(listDlg.textContent));
    check(!(app.info.journals || []).some((x) => x.user), "deleting it takes it off the lists");
    check(Math.abs(store.page().width - 174 * mm) < 0.01, "a page sized by it keeps its size");
  } finally {
    app.autoConfirm = confirming;   // (as it was: the whole self-test may be answering for itself)
    for (const d of document.querySelectorAll("dialog[open]")) d.close();
    const got = await rpc("user_journals_save", before);
    app.info.journals.splice(0, app.info.journals.length, ...got.journals);
    store.setDoc(await rpc("new_document"));
    await settle();
  }
}

// Size > Find a Journal… (journalfind.js): a journal library in a scratch folder; Tree Genetics &
// Genomes found by its ISSN with its Community badge, fetched the first time it's chosen, listed
// under From the library, and sizing a page; PNAS found by its full name, in mosaic already
async function findJournalChecks(app) {
  const prefs = app.info.prefs?.journal_library || "";
  try {
    await rpc("selftest_journal_library", true);
    let dlg = panels.findJournalDialog("1614-2950");
    await until(() => dlg.querySelector(".journal-find-row"), 5000);
    const row = dlg.querySelector(".journal-find-row");
    check(row && /Tree Genetics & Genomes/.test(row.textContent) && /from the library/.test(row.textContent)
      && row.querySelector(".journal-badge-community")?.textContent === "Community",
      "Find a Journal finds Tree Genetics & Genomes by its ISSN in the library, with its Community badge", row?.textContent);
    row.querySelector(".journal-find-use").click();
    await until(() => dlg.querySelector(".journal-find-type"), 5000);
    const j = app.info.journals.find((x) => x.name === "Tree Genetics & Genomes");
    check(j && j.library && j.verified === "community" && j.publisher === "From the library" && j.types.map((t) => t.width_mm).join() === "84,174",
      "a journal from the library is fetched the first time it's chosen and listed From the library", JSON.stringify(j));
    [...dlg.querySelectorAll(".journal-find-type")].find((b) => /^Double column/.test(b.textContent)).click();
    await settle();
    const pg = store.page(), mm = 72 / 25.4;
    check(Math.abs(pg.width - 174 * mm) < 0.01 && Math.abs(pg.height - 234 * mm) < 0.01 && pg.preset?.journal === "Tree Genetics & Genomes",
      "and sizes a page by its figure type", `${pg.width} x ${pg.height}`);
    dlg = panels.findJournalDialog("Proceedings of the National Academy of Sciences");
    await until(() => /PNAS/.test(dlg.querySelector(".journal-find-row")?.textContent || ""), 5000);
    const first = dlg.querySelector(".journal-find-row");
    check(/PNAS/.test(first?.textContent || "") && /in mosaic/.test(first.textContent) && !!first.querySelector(".journal-badge-verified"),
      "a built-in journal is found by its full name, Verified", first?.textContent);
    dlg.close();
  } finally {
    for (const d of document.querySelectorAll("dialog[open]")) d.close();
    const back = await rpc("selftest_journal_library", false);
    app.info.journals.splice(0, app.info.journals.length, ...back.journals);
    if (prefs) await rpc("prefs_set", { journal_library: prefs });
    store.setDoc(await rpc("new_document"));
    await settle();
  }
}

// Any dialog moves by its title (dragdialog.js): dragged, it follows the pointer and what's behind
// is no longer dimmed; it can't be lost off the window; a click on the title or a drag from its
// body doesn't move it; a double-click on the title puts it back in the middle
async function dialogDragChecks(app) {
  const fire = (el, type, x, y) => el.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 7 }));
  try {
    app.run("shortcuts");
    await until(() => document.querySelector("dialog[open] h2"));
    const dlg = [...document.querySelectorAll("dialog[open]")].at(-1), title = dlg.querySelector("h2");
    const r0 = dlg.getBoundingClientRect();
    const tx = r0.left + 40, ty = title.getBoundingClientRect().top + 8;
    fire(title, "pointerdown", tx, ty);
    fire(document, "pointerup", tx, ty);
    check(!dlg.classList.contains("dialog-moved") && Math.abs(dlg.getBoundingClientRect().left - r0.left) < 1, "a click on a dialog's title doesn't move it");
    fire(title, "pointerdown", tx, ty);
    fire(document, "pointermove", tx - 150, ty + 90);
    fire(document, "pointerup", tx - 150, ty + 90);
    const r1 = dlg.getBoundingClientRect();
    check(Math.abs(r1.left - (r0.left - 150)) < 2 && Math.abs(r1.top - (r0.top + 90)) < 2 && dlg.classList.contains("dialog-moved"),
      "a dialog dragged by its title moves with the pointer", `${r0.left},${r0.top} -> ${r1.left},${r1.top}`);
    check(dlg.open && Math.abs(r1.width - r0.width) < 1 && getComputedStyle(dlg, "::backdrop").backgroundColor === "rgba(0, 0, 0, 0)",
      "it stays open at its size, and what's behind it is no longer dimmed", getComputedStyle(dlg, "::backdrop").backgroundColor);
    fire(title, "pointerdown", r1.left + 40, r1.top + 8);
    fire(document, "pointermove", 5000, 5000);
    fire(document, "pointerup", 5000, 5000);
    const r2 = dlg.getBoundingClientRect();
    check(r2.left <= window.innerWidth - 80 && r2.top <= window.innerHeight - 40 && r2.top >= 0, "it can't be dragged out of reach", `${r2.left},${r2.top}`);
    const inBody = dlg.querySelector(".dialog-body");
    fire(inBody, "pointerdown", r2.left + 30, r2.top + 120);
    fire(document, "pointermove", r2.left - 200, r2.top - 100);
    fire(document, "pointerup", r2.left - 200, r2.top - 100);
    check(Math.abs(dlg.getBoundingClientRect().left - r2.left) < 1, "a drag from its body doesn't move it");
    title.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    const r3 = dlg.getBoundingClientRect();
    check(!dlg.classList.contains("dialog-moved") && Math.abs(r3.left - r0.left) < 2 && Math.abs(r3.top - r0.top) < 2, "a double-click on its title puts it back in the middle");
  } finally {
    for (const d of document.querySelectorAll("dialog[open]")) d.close();
  }
}

async function problemReportChecks(app) {
  const top = () => [...document.querySelectorAll("dialog[open]")].at(-1);
  try {
    app.run("reportProblem");
    await until(() => top()?.querySelector("textarea"));
    const dlg = top();
    check(dlg?.querySelector("h2")?.textContent === "Report a problem" && dlg.querySelector("textarea")
      && [...dlg.querySelectorAll("button")].some((b) => b.textContent === "Save Report"),
      "Report a Problem asks what happened and offers to save a report", dlg?.textContent.slice(0, 200));
    check(/none of your figures/.test(dlg?.textContent || ""), "the dialog says no figures or file names go in the report");
    dlg?.close();
    app.run("shortcuts");
    await until(() => top()?.querySelector("table.shortcuts"));
    const report = [...(top()?.querySelectorAll("button") || [])].find((b) => b.textContent === "Report a Problem…");
    report?.click();
    await until(() => top()?.querySelector("textarea"));
    check(report && top()?.querySelector("h2")?.textContent === "Report a problem", "the Help dialog leads to Report a Problem");
    for (const d of document.querySelectorAll("dialog[open]")) d.close();
    // Help > Open the Sample Figure: four plots as panels a-d with their labels, unsaved and not dirty
    store.setDoc(await rpc("new_document"));
    await app.openSample();
    await settle();
    const items = store.items();
    check(items.filter((it) => it.type === "picture").length === 4 && items.filter((it) => it.textbox).length === 4
      && !store.path && !store.dirty && store.doc.meta.title === "Sample figure" && /Four panels/.test(store.page().alt || ""),
      "the sample figure opens as an unsaved figure with four plots, their labels and a description",
      JSON.stringify({ n: items.length, path: store.path, dirty: store.dirty, title: store.doc.meta.title }));
    store.setDoc(await rpc("new_document"));
    await settle();
  } finally {
    for (const d of document.querySelectorAll("dialog[open]")) d.close();
  }
}

async function linkedFileChecks(app) {
  const showing = (on) => Object.defineProperty(document, "hidden", { get: () => !on, configurable: true });
  const soon = async (cond, ms) => { const t0 = performance.now(); while (!cond() && performance.now() - t0 < ms) await wait(50); return cond(); };
  try {
    showing(true);
    store.setDoc(await rpc("new_document"));
    canvas.fit();
    await settle();
    const plot = (w, colour, label) => btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}pt" height="50pt" viewBox="0 0 ${w} 50">`
      + `<rect x="5" y="5" width="${w - 10}" height="30" fill="${colour}"/><text x="5" y="46" font-size="8">${label}</text></svg>`);
    const path = await rpc("selftest_scratch", "linked_plot.svg", plot(100, "#336699", "first"));
    await app.placeFiles([path], [80, 120], false);
    const id = store.items().find((it) => it.type === "picture")?.id;
    if (!id) return log(false, "a figure file is placed linked", path);
    const asset = () => store.doc.assets[store.item(id).asset];
    const frame = () => store.item(id).frame.map((v) => +v.toFixed(3)).join();
    const live = () => document.getElementById("live").textContent;
    store.update("Scale the plot", (doc) => { findItem(doc, id).frame = [80, 120, 150, 75]; });   // at 150%
    const status = (await rpc("link_status", { [store.item(id).asset]: asset() }, null))[store.item(id).asset];
    // Re-saved by R, wider and in another colour, while the window is hidden (minimised): it waits
    showing(false);
    await rpc("selftest_scratch", "linked_plot.svg", plot(140, "#993333", "second"));
    await wait(3000);   // more than one 2 s look
    const whileHidden = asset().size_pt.join();
    showing(true);
    await soon(() => asset().size_pt[0] === 140 && live() === "Updated linked_plot.svg from its file", 8000);
    check(status === "linked" && whileHidden === "100,50" && asset().size_pt.join() === "140,50" && frame() === "80,120,210,75"
      && live() === "Updated linked_plot.svg from its file",
    "a linked picture whose file is re-saved under the same name updates by itself once the window shows, keeping its place and scale",
    `${status}; hidden ${whileHidden}; ${asset().size_pt}; ${frame()}; ${live()}`);
    // Undo asks first, naming the picture, since it rolls it back to a version its file no longer
    // has: Cancel, where focus starts, keeps the update; Roll back rolls it back
    app.autoConfirm = false;
    const asking = async () => { await soon(() => document.querySelector("dialog[open]"), 2000); return document.querySelector("dialog[open]"); };
    let undone = app.run("undo");
    let dlg = await asking();
    const words = dlg?.textContent || "", cancelFirst = document.activeElement?.value === "close";
    dlg?.close();
    await undone;
    check(!!dlg && words.includes("Roll back a picture to before its file changed?") && words.includes("linked_plot.svg") && cancelFirst
      && asset().size_pt.join() === "140,50" && store.history.at(-1)?.label === "Update from file",
    "undoing an update from its file asks first, naming the picture; Cancel, where focus starts, keeps the update",
    `${words}; Cancel focused ${cancelFirst}; ${asset().size_pt}; ${store.history.at(-1)?.label}`);
    undone = app.run("undo");
    dlg = await asking();
    dlg?.querySelector(".dialog-actions .btn.primary")?.click();
    await undone;
    app.autoConfirm = true;
    // Rolled back: the version before stays, though the file on disk is newer
    await wait(5000);   // the editor looks at the file at least twice meanwhile
    check(asset().size_pt.join() === "100,50" && frame() === "80,120,150,75" && store.history.at(-1)?.label === "Scale the plot",
      "undo puts back the version before, and it stays until the file is saved again",
      `${asset().size_pt}; ${frame()}; ${store.history.at(-1)?.label}`);
    app.run("redo");
    const redone = asset().size_pt.join();
    app.run("undo");
    await rpc("selftest_scratch", "linked_plot.svg", plot(120, "#339933", "third"));
    await soon(() => asset().size_pt[0] === 120, 8000);
    check(redone === "140,50" && asset().size_pt.join() === "120,50" && frame() === "80,120,180,75",
      "redo takes the update back, and the file saved again comes in", `${redone}; ${asset().size_pt}; ${frame()}`);
  } finally {
    delete document.hidden;   // the browser's own again
    app.autoConfirm = true;
  }
}

// Refresh All Pictures (⌘⇧R): every linked picture read again now, even while the window is
// hidden (when the regular look waits) and after an update was undone (which the regular look
// keeps undone); in the Home tab, the File menu and the page's menu
async function refreshAllChecks(app) {
  const showing = (on) => Object.defineProperty(document, "hidden", { get: () => !on, configurable: true });
  const soon = async (cond, ms) => { const t0 = performance.now(); while (!cond() && performance.now() - t0 < ms) await wait(50); return cond(); };
  const said = () => document.getElementById("live").textContent;
  try {
    showing(true);
    store.setDoc(await rpc("new_document"));
    canvas.fit();
    await settle();
    const plot = (w, colour) => btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}pt" height="50pt" viewBox="0 0 ${w} 50">`
      + `<rect x="5" y="5" width="${w - 10}" height="30" fill="${colour}"/></svg>`);
    const path = await rpc("selftest_scratch", "refresh_plot.svg", plot(100, "#336699"));
    await app.placeFiles([path], [80, 120], false);
    const id = store.items().find((it) => it.type === "picture")?.id;
    if (!id) return check(false, "a figure is placed linked for Refresh All", path);
    const size = () => store.doc.assets[store.item(id).asset].size_pt.join();
    const menu = app.menuSpec().find((m) => m.title === "File").items.find((x) => x.title === "Refresh All Pictures");
    check(document.querySelector('#rpanel-home [data-cmd="refreshAll"]') && menu?.action === "refreshAll"
      && app.commands.refreshAll.keys === `${isMac ? "⌘" : "Ctrl+"}${isMac ? "⇧" : "Shift+"}R`
      && app.pageMenu({}).some((x) => x && x.label === "Refresh all pictures"),
    "Refresh All Pictures is in the Home tab, the File menu and the page's menu, with ⌘⇧R",
    `${menu?.action}; ${app.commands.refreshAll.keys}`);
    // Saved again while the window is hidden: the regular look waits, Refresh takes it now
    showing(false);
    await rpc("selftest_scratch", "refresh_plot.svg", plot(140, "#993333"));
    await app.run("refreshAll");
    await soon(() => said().startsWith("Refreshed"), 2000);
    check(size() === "140,50" && near(store.item(id).frame[2], 140) && said() === "Refreshed 1 linked picture: refresh_plot.svg updated",
      "Refresh All reads a re-saved file at once, keeping its picture's place and scale", `${size()}; ${said()}`);
    // Undone, the update stays undone for the regular look; Refresh All takes it again
    showing(true);
    await app.run("undo");
    await wait(3000);
    const undone = size();
    await app.run("refreshAll");
    await soon(() => size() === "140,50", 3000);
    check(undone === "100,50" && size() === "140,50", "after an update is undone, Refresh All takes the file's version again",
      `${undone}; ${size()}`);
    // Nothing new: it says so
    await app.run("refreshAll");
    await soon(() => said().includes("all up to date"), 2000);
    check(said() === "Refreshed 1 linked picture: all up to date" && store.history.at(-1)?.label === "Update from file",
      "with nothing new, Refresh All says all is up to date and adds no undo step", said());
  } finally {
    delete document.hidden;
  }
}

// Dangerous mode (liftedtext.js): off at first; on, a double-click on a placed plot's text lifts it
// out as a text box over the plot, which is then drawn without it; the boxes go with the picture;
// Put back deletes one and the plot's text shows again; a copy of the picture alone shows its
// texts; R saving the file again drops edits whose text isn't there any more; Check notes both
async function dangerousModeChecks(app) {
  const showing = (on) => Object.defineProperty(document, "hidden", { get: () => !on, configurable: true });
  const soon = async (cond, ms) => { const t0 = performance.now(); while (!cond() && performance.now() - t0 < ms) await wait(50); return cond(); };
  try {
    showing(true);
    store.setDoc(await rpc("new_document"));
    canvas.fit();
    await settle();
    const plot = (title) => btoa("<svg xmlns='http://www.w3.org/2000/svg' width='200pt' height='120pt' viewBox='0 0 200 120'>"
      + "<rect x='20' y='10' width='170' height='80' style='fill: none; stroke: #000000;'/>"
      + `<text x='105' y='110' text-anchor='middle' style='font-size: 8px; font-family: "Helvetica";'>${title}</text>`
      + "<text transform='translate(10,50) rotate(-90)' text-anchor='middle' style='font-size: 8px; font-family: \"Helvetica\";'>Height</text>"
      + "<text x='17' y='92' text-anchor='end' style='font-size: 6px; font-family: \"Helvetica\"; fill: #993333;'>0</text></svg>");
    const path = await rpc("selftest_scratch", "danger_plot.svg", plot("Days after sowing"));
    await app.placeFiles([path], [60, 60], false);
    const picId = store.items().find((it) => it.type === "picture")?.id;
    if (!picId) return check(false, "a plot is placed for dangerous mode", path);
    const pic = () => store.item(picId);
    const at = (x, y) => { const [fx, fy, fw] = pic().frame, k = fw / 200; return [fx + x * k, fy + y * k]; };
    const dbl = (p) => { const [sx, sy] = screenOf(...p); canvas.stage.dispatchEvent(new MouseEvent("dblclick", { clientX: sx, clientY: sy, bubbles: true })); };
    const boxes = () => store.items().filter((it) => it.lifted);
    const words = (it) => it.text.paragraphs.map((q) => q.runs.map((r) => r.t).join("")).join("\n");
    check(!app.dangerous && !app.menuChecks().toggleDangerous && panels.dangerBadge?.hidden,
      "dangerous mode is off when mosaic opens, unticked in the View menu, no badge", `${app.dangerous}; ${panels.dangerBadge?.hidden}`);
    await app.run("toggleDangerous");
    check(app.dangerous && app.menuChecks().toggleDangerous && !panels.dangerBadge.hidden && canvas.stage.classList.contains("dangerous")
      && panels.dangerButton.getAttribute("aria-pressed") === "true",
      "View ▸ Dangerous Mode turns it on: ticked, pressed in the View tab, and a red badge in the status bar says so",
      `${panels.dangerBadge.hidden}; ${panels.dangerButton.getAttribute("aria-pressed")}`);
    // Over a plot, its texts are outlined, the one under the pointer solid
    pointer("pointermove", screenOf(...at(105, 107.5)), { buttons: 0 });
    await soon(() => canvas.overlay.querySelectorAll(".plot-text").length === 3, 3000);
    const hot = canvas.overlay.querySelectorAll(".plot-text.hot").length;
    check(canvas.overlay.querySelectorAll(".plot-text").length === 3 && hot === 1,
      "over a plot, dangerous mode outlines its texts, the one under the pointer solid",
      `${canvas.overlay.querySelectorAll(".plot-text").length} outlined, ${hot} solid`);
    // The x axis title, lined up in the middle: a text box in its font, size and colour, being edited
    dbl(at(105, 107.5));
    await soon(() => boxes().length === 1 && canvas.editing, 4000);
    const box = boxes()[0], run = box?.text.paragraphs[0].runs[0];
    const k = pic().frame[2] / 200;
    check(box && words(box) === "Days after sowing" && run.font === "Helvetica" && near(run.size, 8 * k, 0.001) && box.text.paragraphs[0].align === "ctr"
      && box.rot === 0 && canvas.editing?.id === box.id && store.selection.join() === box.id
      && pic().lifted_text?.hidden?.length === 1 && pic().lifted_text.hidden[0].box === box.id
      && near(box.frame[0] + box.frame[2] / 2, at(105, 0)[0], 0.05) && store.items().indexOf(box) === store.items().indexOf(pic()) + 1,
    "a double-click on a plot's text lifts it out: a text box just above the picture, in its font and size, centred where it was, being edited",
    JSON.stringify([box && words(box), run, box?.frame, box?.rot, canvas.editing?.id]));
    document.execCommand("selectAll");
    document.execCommand("insertText", false, "Days after planting");
    canvas.commitEdit();
    await settle();
    check(words(store.item(box.id)) === "Days after planting", "its text is edited like any other", words(store.item(box.id)));
    // The plot is now drawn from a copy without that text
    const own = store.doc.assets[pic().asset].variants.svg.sha256;
    const href = () => canvas.els.get(picId)?.g.querySelector("image")?.getAttribute("href") || "";
    await soon(() => href() && !href().includes(own), 4000);
    const copy = await rpc("lifted_copy", store.doc.assets[pic().asset], 0, pic().lifted_text.hidden);
    const left = await rpc("plot_texts", { ...store.doc.assets[pic().asset], variants: copy.variants }, 0, "svg");
    check(!href().includes(own) && left.texts.map((t) => t.text).join() === "Height,0" && !copy.missing.svg.length,
      "the picture is drawn from a copy of its file without the lifted text", `${href().slice(-30)}; ${left.texts.map((t) => t.text)}`);
    // The y axis title, turned: its box is turned too
    dbl(at(5, 50));
    await soon(() => boxes().length === 2, 4000);
    canvas.commitEdit();
    await settle();
    const turned = boxes().find((b) => words(b) === "Height");
    // (its letters stand left of the baseline at x 10: the box's middle is a little left of it)
    check(turned && turned.rot === 270 && near(turned.frame[0] + turned.frame[2] / 2, at(7.6, 0)[0], 1.5 * k)
      && near(turned.frame[1] + turned.frame[3] / 2, at(0, 50)[1], 0.05),
      "a turned text comes out as a turned text box", JSON.stringify([turned?.rot, turned?.frame]));
    // The boxes go with their picture: moved, then scaled (sizes too)
    const before = boxes().map((b) => [...b.frame]);
    store.update("Move plot", (doc) => { findDeep(doc.pages[store.pageIndex].items, picId).frame[0] += 20; });
    const moved = boxes().every((b, i) => near(b.frame[0], before[i][0] + 20, 1e-6) && near(b.frame[1], before[i][1], 1e-6));
    store.update("Scale plot", (doc) => { const o = findDeep(doc.pages[store.pageIndex].items, picId); o.frame[2] *= 1.5; o.frame[3] *= 1.5; });
    const grown = store.item(box.id).text.paragraphs[0].runs[0].size;
    check(moved && near(grown, 8 * k * 1.5, 1e-6) && near(store.item(box.id).frame[0] + store.item(box.id).frame[2] / 2, at(105, 0)[0], 0.05),
      "lifted text boxes move and scale with their picture", `${moved}; ${grown}`);
    // Put back: the box goes and the plot shows its own text again
    store.select([turned.id]);
    await app.run("putBackText");
    await settle();
    check(!store.item(turned.id) && pic().lifted_text.hidden.length === 1 && boxes().length === 1,
      "Put Back in Plot deletes the box and the plot shows that text again", JSON.stringify(pic().lifted_text));
    // A copy of the picture alone shows the texts whose boxes weren't copied with it
    store.select([picId]);
    await app.run("duplicate");
    const dup = store.selected()[0];
    check(dup?.type === "picture" && dup.id !== picId && !(dup.lifted_text?.hidden || []).length,
      "a copy of the picture without its lifted boxes shows its own text", JSON.stringify(dup?.lifted_text));
    store.update("Delete copy", (doc) => { const items = doc.pages[store.pageIndex].items; items.splice(items.findIndex((it) => it.id === dup.id), 1); });
    // Check says what was lifted
    const notes = (await rpc("preflight", store.doc, {})).items.map((f) => f.message);
    check(notes.some((m) => m.includes("1 text lifted out in dangerous mode (“Days after sowing”)")),
      "Check notes the text lifted out of the plot", notes.join(" | "));
    // R saves the file again with another title: that edit is dropped, its box goes, Check says so
    await rpc("selftest_scratch", "danger_plot.svg", plot("Days"));
    await soon(() => !boxes().length && (pic().lifted_text?.dropped || []).length === 1, 9000);
    await soon(() => document.getElementById("live").textContent.includes("danger_plot"), 1000);   // (announce waits 60 ms)
    const said = document.getElementById("live").textContent;
    const dropped = pic().lifted_text?.dropped?.[0];
    const notes2 = (await rpc("preflight", store.doc, {})).items.map((f) => f.message);
    check(!boxes().length && !hiddenCount(pic()) && dropped?.text === "Days after sowing" && dropped.box_text === "Days after planting"
      && said.includes("1 edited text isn't in the new file, so its edit was dropped")
      && notes2.some((m) => m.includes("the edit to “Days after sowing” was dropped when its file changed")),
    "when R saves the file again without that text, its edit is dropped and Check says so",
    `boxes ${boxes().length}; hidden ${hiddenCount(pic())}; dropped ${dropped?.text} / ${dropped?.box_text}; `
      + `${said}; ${notes2.filter((m) => m.includes("dropped")).join(" | ")}`);
    // Off: a double-click crops again, and the badge goes
    await app.run("toggleDangerous");
    store.select([]);
    dbl(at(100, 60));
    await settle();
    check(!app.dangerous && panels.dangerBadge.hidden && canvas.cropping && !boxes().length,
      "with dangerous mode off, a double-click on a plot crops it as before",
      `on ${app.dangerous}; badge hidden ${panels.dangerBadge.hidden}; cropping ${!!canvas.cropping}; boxes ${boxes().length}`);
    if (canvas.cropping) canvas.endCrop();
  } finally {
    delete document.hidden;
    if (app.dangerous) app.toggleDangerous(false);
  }
}
const hiddenCount = (it) => (it?.lifted_text?.hidden || []).length;

// Updates (updates.py looks, downloads and installs; here, with the updater saying what each case
// needs, what the editor shows): the status bar's note when a version is ready, What's new and
// Restart now (unsaved work saved first, or kept as a copy to recover), Ask me first with Skip
// this version, a failed install, signing in to GitHub, Preferences > Updates, What's new after
// an update, and a document saved by a newer mosaic
async function updateChecks(app) {
  const { updates } = await import("./updates.js");
  const notes = "What's new:\n\n- Exports twice as fast\n- Arrows snap to more places";
  const v = { version: "9.9.9", notes, prerelease: false, env_changed: false, approved: false, go_back: false };
  const base = { kind: "installed", mode: "auto", channel: "stable", access: "public", configured: true, error: null, busy: null,
    failed: null, update: null, staged: null, previous: null, updated: null, installing: false, checked: Date.now() / 1000 };
  const fake = async (st) => { await rpc("selftest_update", { ...base, ...st }); await updates.poll(); };
  const chip = () => document.querySelector(".update-chip");
  const dialog = () => [...document.querySelectorAll("dialog[open]")].at(-1);
  const closeAll = () => { for (const d of document.querySelectorAll("dialog[open]")) d.close(); };
  const buttonIn = (el, text) => [...(el?.querySelectorAll("button") || [])].find((b) => b.textContent === text);
  const soon = async (cond, ms = 4000) => { for (let t = 0; t < ms; t += 100) { if (await cond()) return true; await wait(100); } return !!(await cond()); };
  const restarting = async () => (await rpc("update_status")).restarting;
  const keepDelay = updates.restartDelay;
  updates.restartDelay = 50;
  try {
    store.setDoc(await rpc("new_document"));
    // A downloaded update, with automatic updates: the status bar says so; What's new; Restart now
    await fake({ staged: v, update: v });
    check(!chip().hidden && chip().textContent === "mosaic 9.9.9 is ready" && /installs when you quit/.test(chip().title),
      "a downloaded update shows in the status bar, saying it installs when mosaic quits", `${chip().hidden} ${chip().textContent}; ${chip().title}`);
    chip().click();
    let dlg = dialog();
    check(dlg?.querySelector("h2")?.textContent === "mosaic 9.9.9" && dlg.querySelectorAll(".release-notes li").length === 2
      && buttonIn(dlg, "Restart now") && /installs when you quit/.test(dlg.textContent),
    "clicking it shows what's new in the version, with Restart now", dlg?.textContent);
    buttonIn(dlg, "Restart now")?.click();
    check(await soon(restarting) && /closes now and opens again/.test(dialog()?.textContent || ""),
      "Restart now says mosaic closes and opens again with the update, and has it do so", dialog()?.textContent);
    closeAll();
    // With unsaved changes: save first, or restart without saving, keeping a copy to recover
    await fake({ staged: v, update: v });
    store.update("A change before updating", (doc) => { doc.pages[store.pageIndex].items.push(gRectFor("updRect", 10, 10, 20, 20)); });
    const installing = updates.install("update");
    await until(() => dialog()?.querySelector("h2")?.textContent === "Unsaved changes");
    dlg = dialog();
    const asked = !!(buttonIn(dlg, "Save and restart") && buttonIn(dlg, "Restart without saving"));
    buttonIn(dlg, "Restart without saving")?.click();
    await installing;
    const kept = (await rpc("autosaved", null)).some((c) => c.path.includes(store.autosaveKey));
    check(asked && kept && await restarting(), "with unsaved changes it asks first; restarting without saving keeps a copy to recover",
      `${asked} ${kept}`);
    closeAll();
    await rpc("discard_autosave", store.autosaveKey);
    store.dirty = false;
    // Ask me first: the newer version is out; Skip this version
    await fake({ mode: "ask", update: { version: "9.9.9", notes, prerelease: false } });
    check(chip().textContent === "mosaic 9.9.9 is out", "with Ask me first, a newer version shows as out", chip().textContent);
    chip().click();
    dlg = dialog();
    const choices = !!(buttonIn(dlg, "Update now") && buttonIn(dlg, "Skip this version"));
    buttonIn(dlg, "Skip this version")?.click();
    check(choices && await soon(async () => (await rpc("update_status")).skip === "9.9.9"),
      "its What's new has Update now and Skip this version, which skips it", dlg?.textContent);
    await rpc("update_skip", null);
    // A failed install
    await fake({ staged: v, failed: { version: "9.9.9", error: "the tools mosaic uses couldn't be updated" }, tries: 2, max_tries: 2 });
    check(chip().textContent === "The update didn't install" && chip().classList.contains("warn"),
      "an update that didn't install shows in the status bar", chip().textContent);
    chip().click();
    dlg = dialog();
    check(/couldn't be updated/.test(dlg?.textContent) && /won't try again by itself/.test(dlg?.textContent)
      && buttonIn(dlg, "Try again now") && buttonIn(dlg, "Show the log"), "it says why, and offers Try again now and the log", dlg?.textContent);
    closeAll();
    // Signing in to GitHub, while the repository is private: a code to enter on GitHub
    await fake({ access: "sign_in" });
    check(chip().textContent === "Sign in for updates", "while a sign-in is needed, the status bar offers it", chip().textContent);
    chip().click();
    await until(() => dialog()?.querySelector(".signin-code"));
    dlg = dialog();
    const shown = dlg?.querySelector(".signin-code")?.textContent === "WDJB-MJHT" && !!buttonIn(dlg, "Copy the code and open GitHub");
    await rpc("selftest_update", { ...base, signin: { state: "done", login: "early-adopter" }, signed_in: "early-adopter" });
    check(shown && await soon(() => /Signed in as early-adopter/.test(dlg.textContent)),
      "signing in shows GitHub's code with a button to copy it and open GitHub, then who's signed in", dlg?.textContent);
    closeAll();
    // Preferences > Updates: the setting, test versions, what's going on, Go back
    await fake({ staged: v, update: v, previous: { version: "9.9.8", notes: "", prerelease: false } });
    await app.run("preferences");
    const fs = [...document.querySelectorAll("dialog[open] fieldset")].find((f) => f.querySelector("legend")?.textContent === "Updates");
    const sel = fs?.querySelector("select");
    check(sel?.value === "auto" && fs.querySelector("input[type=checkbox]") && /9\.9\.9 is ready/.test(fs.querySelector(".update-status")?.textContent)
      && buttonIn(fs, "Restart now") && buttonIn(fs, "Go back to 9.9.8"),
    "Preferences has Updates: the setting, test versions, the version ready, Restart now and Go back", fs?.textContent);
    if (sel) {
      sel.value = "ask";
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }
    check(await soon(() => app.prefs.updates === "ask"), "choosing Ask me first keeps the setting", app.prefs.updates);
    await app.savePrefs({ updates: "auto" });
    closeAll();
    // After an update: What's new, once
    await rpc("selftest_update", { ...base, updated: { version: "9.9.9", from: "0.1.0", notes, go_back: false } });
    await updates.poll(true);
    dlg = dialog();
    check(dlg?.querySelector("h2")?.textContent === "Updated to mosaic 9.9.9" && dlg.querySelectorAll(".release-notes li").length === 2,
      "after an update, mosaic shows what's new", dlg?.textContent);
    closeAll();
    // A document saved by a newer mosaic
    updates.newerDocument("99.0.0");
    dlg = dialog();
    check(dlg?.querySelector("h2")?.textContent === "Saved by a newer mosaic" && /99\.0\.0/.test(dlg.textContent) && /Save As/.test(dlg.textContent),
      "a document saved by a newer mosaic warns that saving over it could lose things", dlg?.textContent);
  } finally {
    closeAll();
    updates.restartDelay = keepDelay;
    await rpc("selftest_update", null);
    await updates.poll();
  }
}

// PowerPoint slides into a figure: Open goes through the slide picker (pictures of the slides,
// one or several chosen by click, Shift-, ⌘-click, double-click or keys); a deck dropped on the
// page puts the chosen slides' objects there, dropped in the Pages list makes them pages in the
// gap, with a line showing where meanwhile; slides and shapes copied in PowerPoint paste as
// objects where they were on the slide (or as a picture); slides dragged out of PowerPoint come
// from their deck as saved, asking which deck when several have them. `ppt`: a deck (and
// another), PowerPoint's copied slide (.slides) and shapes (.gvml).
async function slidesChecks(app, ppt) {
  const [deck, other = deck] = ppt.filter((f) => f.endsWith(".pptx"));
  const slidesFile = ppt.find((f) => f.endsWith(".slides")), rectFile = ppt.find((f) => f.endsWith("_rect.gvml"));
  if (!deck || !slidesFile || !rectFile) return log(false, "PowerPoint test files given", ppt.join(", "));
  const shown = () => document.querySelector("dialog.picker-dialog[open]");
  const picker = async () => { await until(shown, 8000); return shown(); };
  const cards = (dlg) => [...dlg.querySelectorAll(".slide-grid li")];
  const go = (dlg) => dlg.querySelector(".dialog-actions .btn.primary");
  const click = (el, o = {}) => el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, ...o }));
  const gridKey = (dlg, k, o = {}) => dlg.querySelector(".slide-grid").dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...o }));
  const closeAll = () => { for (const d of document.querySelectorAll("dialog[open]")) d.close(); };
  const names = () => store.doc.pages.map((p) => p.name).join(", ");
  const mod = /Mac/.test(navigator.platform) ? { metaKey: true } : { ctrlKey: true };

  // Open: the picker, with a picture, title and Hidden for each slide; nothing chosen yet
  let opening = app.open(deck);
  let dlg = await picker();
  check(dlg && cards(dlg).length === 4 && cards(dlg).map((li) => li.querySelector(".slide-label").firstChild.textContent).join() === "Slide 1,Slide 2,Slide 3,Slide 4"
    && cards(dlg)[0].querySelector(".slide-sub")?.textContent === "Example figures" && cards(dlg)[3].querySelector(".slide-badge")?.textContent === "Hidden"
    && go(dlg).disabled && go(dlg).textContent === "Open", "Open shows a deck's slides to choose from, titled, with hidden ones marked",
  dlg ? `${cards(dlg).map((li) => li.textContent).join(" | ")}; button ${go(dlg).textContent} ${go(dlg).disabled}` : "no picker");
  if (!dlg) return;
  // (and decoded: a hidden window can mark a picture drawn before its image is read)
  await until(() => cards(dlg).every((li) => li.classList.contains("drawn") && li.querySelector("img").naturalWidth), 15000);
  check(cards(dlg).every((li) => li.querySelector("img").naturalWidth === 320 && li.querySelector("img").naturalHeight === 180),
    "and draws each slide small", cards(dlg).map((li) => `${li.className} ${li.querySelector("img").naturalWidth}`).join("; "));
  click(cards(dlg)[1]);
  click(cards(dlg)[3], { shiftKey: true });
  const ranged = go(dlg).textContent;
  click(cards(dlg)[2], mod);
  check(ranged === "Open 3 slides" && go(dlg).textContent === "Open 2 slides"
    && cards(dlg).map((li) => li.getAttribute("aria-selected")).join() === "false,true,false,true",
  `Shift-click chooses a run of slides, ${mod.metaKey ? "⌘" : "Ctrl"}-click one more or one fewer`, `${ranged}; ${go(dlg).textContent}`);
  click(dlg.querySelector(".dialog-actions .btn:not(.primary)"));   // All slides
  const allWords = go(dlg).textContent;
  click(cards(dlg)[1]);
  click(cards(dlg)[3], mod);
  click(go(dlg));
  await opening;
  await settle();
  const report = [...document.querySelectorAll("dialog[open]")].pop();
  const pic = store.doc.pages[0]?.items.find((it) => it.type === "picture");
  const picSrc = pic && Object.values(store.doc.assets[pic.asset].variants).find((v) => v.src)?.src;
  check(allWords === "Open all 4 slides" && names() === "Slide 2, Slide 4" && !store.path && /example_scatter\.(png|pdf|svg)$/.test(picSrc || "")
    && report?.querySelector("h2")?.textContent === "Imported from PowerPoint",
  "only the slides chosen open, their pictures linked to the original files, with the import report",
  `${allWords}; pages ${names()}; picture ${picSrc}; ${report?.querySelector("h2")?.textContent}`);
  closeAll();

  // Double-click takes one slide straight away; the keys work too; Cancel leaves the figure be
  opening = app.open(deck);
  dlg = await picker();
  cards(dlg)[2].dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
  await opening;
  closeAll();
  const oneByDouble = names();
  opening = app.open(deck);
  dlg = await picker();
  gridKey(dlg, "ArrowRight");
  gridKey(dlg, "ArrowRight", { shiftKey: true });
  gridKey(dlg, "Enter");
  await opening;
  closeAll();
  const byKeys = names();
  opening = app.open(deck);
  dlg = await picker();
  click(dlg.querySelector("button[value=close]"));   // Cancel
  await opening;
  check(oneByDouble === "Slide 3" && byKeys === "Slide 2, Slide 3" && names() === byKeys,
    "double-click opens one slide, the arrow keys and Shift choose, Enter opens; cancelling opens nothing",
    `${oneByDouble}; ${byKeys}; after cancel ${names()}`);

  // A deck dropped on a blank page: the page becomes the chosen slide, at the slide's size, with
  // its objects where they were on the slide; more slides become pages after it
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const blank = { ...store.page(), items: [] }, [slide3] = (await rpc("deck_pages", deck, [3])).pages;
  // (where each object is: its top-left corner; text boxes fit their height to the text once drawn)
  const boxes = (items) => items.map((it) => itemBBox(it).slice(0, 2).map((v) => v.toFixed(1)).join(" ")).join("; ");
  const [px, py] = screenOf(100, 150);
  window.FA.onNativeDrag({ kind: "deck", x: px, y: py });
  const overBlank = document.querySelector(".drop-hint").textContent;
  window.FA.onNativeDrag(null);
  let dropping = window.FA.onNativeDrop({ paths: [deck], x: px, y: py });
  dlg = await picker();
  const blankHint = dlg?.querySelector(".hint")?.textContent || "";
  click(cards(dlg)[2]);
  click(go(dlg));
  await dropping;
  closeAll();
  await settle();
  check(overBlank === "Drop to make this blank page the slide, at its size" && blankHint.includes("onto this blank page, which takes the slide size")
    && store.page().width === 960 && store.page().height === 540 && !store.page().preset && store.page().name === blank.name
    && boxes(store.items()) === boxes(slide3.items) && store.doc.pages.length === 1,
  "a deck dropped on a blank page makes the page the chosen slide: its size, its objects where they were",
  `‹${overBlank}› ‹${blankHint}› ${pageSize()} ${store.page().name} ${store.doc.pages.length} ${store.page().preset}; ${boxes(store.items())} vs ${boxes(slide3.items)}`);
  store.undo();
  check(store.items().length === 0 && store.page().width === blank.width && store.page().height === blank.height
    && store.page().preset?.standard === blank.preset?.standard, "and one undo puts the blank page back", `${store.items().length}; ${pageSize()}`);
  dropping = window.FA.onNativeDrop({ paths: [deck], x: px, y: py });
  dlg = await picker();
  click(cards(dlg)[1]);
  click(cards(dlg)[3], { shiftKey: true });
  click(go(dlg));
  await dropping;
  closeAll();
  await settle();
  check(names() === `${blank.name}, Slide 3, Slide 4` && store.pageIndex === 0 && store.items().length === 6
    && store.doc.pages.every((p) => p.width === 960 && p.height === 540),
  "several slides onto a blank page: it takes the first, and the rest become pages after it", `${names()} at ${store.pageIndex}; ${store.items().length}`);
  store.undo();
  check(names() === blank.name && store.items().length === 0, "all in one undo step", names());

  // On a page with objects already: the slide's objects go there, at the drop point (one undo step)
  store.update("A box for the test", (doc) => doc.pages[0].items.push(gRectFor("keep", 400, 600, 40, 40)));
  canvas.fit();   // (the view was fitted to the slide-sized page)
  await settle();
  const before = pageSize(), [qx, qy] = screenOf(100, 150);
  window.FA.onNativeDrag({ kind: "deck", x: qx, y: qy });
  const overPage = document.body.classList.contains("dropping") && document.querySelector(".drop-hint").textContent.includes("slides");
  window.FA.onNativeDrag(null);
  dropping = window.FA.onNativeDrop({ paths: [deck], x: qx, y: qy });
  dlg = await picker();
  const hint = dlg?.querySelector(".hint")?.textContent || "";
  click(cards(dlg)[2]);
  click(go(dlg));
  await dropping;
  closeAll();
  await settle();
  const dropped = itemsBBox(store.selected());
  check(overPage && hint.includes("onto this page") && store.items().length === 4 && near(dropped[0], 100, 0.5) && near(dropped[1], 150, 0.5)
    && store.selection.length === 3 && pageSize() === before, "a deck dropped on a page with objects puts the chosen slide's objects at the drop point, selected",
  `hint ${overPage} ‹${hint}›; ${store.items().map((it) => it.type).join(",")} at ${dropped?.map((v) => v.toFixed(1))}; ${pageSize()} ${before}`);
  store.undo();
  check(store.items().length === 1, "and one undo takes them away", `${store.items().length}`);
  store.undo();

  // In the Pages list: a line shows the gap, and the slides go in there as pages
  app.addPage();
  store.setPage(0);
  await settle();
  const rows = () => [...document.querySelectorAll(".page-list li[data-index]")];
  const r2 = rows()[1].getBoundingClientRect(), [lx, ly] = [r2.left + 20, r2.top + 4];
  window.FA.onNativeDrag({ kind: "deck", x: lx, y: ly });
  const line = document.querySelector(".page-list .slide-drop-line");
  const lineAt = line && Math.abs(parseFloat(line.style.top) - rows()[1].offsetTop) < 1 && !document.body.classList.contains("dropping");
  window.FA.onNativeDrag(null);
  const cleared = !document.querySelector(".slide-drop-line");
  dropping = window.FA.onNativeDrop({ paths: [deck], x: lx, y: ly });
  dlg = await picker();
  const listHint = dlg?.querySelector(".hint")?.textContent || "";
  click(cards(dlg)[1]);
  click(cards(dlg)[2], { shiftKey: true });
  click(go(dlg));
  await dropping;
  closeAll();
  check(lineAt && cleared && listHint.includes("as pages before page 2") && names() === "Page 1, Slide 2, Slide 3, Page 2"
    && store.pageIndex === 1 && store.page().items.length === 6,
  "dropped in the Pages list, the slides go in as pages where the line showed", `line ${lineAt} ${cleared}; "${listHint}"; ${names()} at ${store.pageIndex}`);
  store.undo();
  check(names() === "Page 1, Page 2", "and one undo takes them out", names());

  // Pasting slides and shapes copied in PowerPoint: objects where they were on the slide (and on
  // a blank page, the page takes the slide's size)
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await rpc("clipboard_fake", { slides: slidesFile, png: { size: [40, 20], dpi: 144 } });
  await app.paste();
  await settle();
  const pastedPic = store.items().find((it) => it.type === "picture");
  check(store.items().map((it) => it.type).join() === "picture,shape,shape,line,shape,group" && near(pastedPic.frame[0], 60) && near(pastedPic.frame[1], 80)
    && store.page().width === 960 && store.page().height === 540 && !document.querySelector("dialog[open]"),
  "a slide copied in PowerPoint pastes as its objects, where they were on the slide, a blank page taking the slide's size",
  `${store.items().map((it) => it.type).join()}; picture at ${pastedPic?.frame}; page ${pageSize()}`);
  const entries = app.pasteEntries(await app.clipboardKinds(), null).filter(Boolean).map((e) => e.label);
  await app.paste("picture");
  check(entries.includes("Paste as picture") && store.items().at(-1).type === "picture" && store.items().length === 7,
    "or as a picture of it", `${entries.join(", ")}; ${store.items().length}`);
  await rpc("clipboard_fake", { shapes: rectFile });
  await app.paste();
  const rect = store.items().at(-1);
  await app.paste("auto", [20, 30]);
  const atPoint = store.items().at(-1);
  check(rect?.geom === "roundRect" && near(rect.frame[0], 260) && near(rect.frame[1], 90) && rect.text?.paragraphs[0].runs[0].t === "Treated"
    && near(atPoint.frame[0], 20) && near(atPoint.frame[1], 30),
  "shapes copied in PowerPoint paste as editable shapes, where they were or where right-clicked", `${rect?.geom} ${rect?.frame}; ${atPoint?.frame}`);

  // Slides dragged out of PowerPoint: from the deck as saved; asking which deck when two have them
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  app.testDecks = [deck];
  dropping = window.FA.onNativeDrop({ pptSlides: [{ doc: "x", slide: 258 }], x: px, y: py });
  const busy = document.body.classList.contains("drop-busy") && document.querySelector(".drop-hint").textContent;
  await dropping;
  const savedNote = [...document.querySelectorAll("dialog[open] li")].map((li) => li.textContent).join(" ");
  closeAll();
  const fromSaved = store.items().length, draggedSize = pageSize();
  check(busy === "Bringing in the slide from PowerPoint…" && !document.body.classList.contains("drop-busy"),
    "while dragged slides are read, the page says so", `${busy}; ${document.body.className}`);
  app.testDecks = [deck, other];
  dropping = window.FA.onNativeDrop({ pptSlides: [{ doc: "x", slide: 257 }], x: px, y: py });
  dlg = await picker();
  const question = dlg?.querySelector("h2")?.textContent;
  click(cards(dlg)[1]);
  click(go(dlg));
  await dropping;
  closeAll();
  app.testDecks = [];
  await window.FA.onNativeDrop({ pptSlides: [{ doc: "x", slide: 257 }], x: px, y: py });
  const notFound = [...document.querySelectorAll("dialog[open] h2")].map((h2) => h2.textContent).join();
  closeAll();
  delete app.testDecks;
  check(fromSaved === 3 && draggedSize === "338.7 × 190.5 mm" && savedNote.includes("as last saved") && question === "Which deck are the slides from?"
    && store.items().length === 9 && notFound === "Those slides weren't found",
  "slides dragged out of PowerPoint come from their saved deck (onto a blank page, at the slide's size), asking which deck if two have them",
  `${fromSaved} ${draggedSize} "${savedNote.slice(0, 80)}"; ${question}; ${store.items().length}; ${notFound}`);

  // PowerPoint's web data for dragged slides (what a Chromium web view may be handed) comes in too
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  store.update("A box for the test", (doc) => doc.pages[0].items.push(gRectFor("keep", 400, 600, 40, 40)));
  await settle();
  const web = new DataTransfer(), [wx, wy] = [Math.round(px), Math.round(py)];   // (events have whole pixels)
  web.setData("ppt/slides", JSON.stringify({ isDataCompressed: "False", data: await rpc("selftest_read", slidesFile) }));
  document.dispatchEvent(new DragEvent("drop", { dataTransfer: web, clientX: wx, clientY: wy, bubbles: true, cancelable: true }));
  await until(() => store.items().length === 7, 4000);
  // (the slide's top-left object is a text box at 40, 60, so its picture at 60, 80 lands 20, 20 on)
  const sr = canvas.stage.getBoundingClientRect(), [ex, ey] = canvas.toPage(wx - sr.left, wy - sr.top);
  const webPic = store.items().find((it) => it.type === "picture");
  check(store.items().length === 7 && near(webPic.frame[0], ex + 20) && near(webPic.frame[1], ey + 20),
    "slides dropped as PowerPoint's web data come in at the drop point", `${store.items().length}; picture at ${webPic?.frame}; drop ${ex}, ${ey}`);
  closeAll();
}

// The Mac menu bar's side in the editor (macmenu.py builds the menus): what it describes, and
// what its items do: the commands, nothing while a dialog is open, a text field's own editing
async function macMenuChecks(app) {
  const spec = app.menuSpec(), all = [];
  const walk = (items) => items.forEach((it) => { if (it.items) walk(it.items); else if (it !== "-") all.push(it); });
  spec.forEach((m) => walk(m.items || []));
  const special = (a) => a === "pastePicture" || a.startsWith("vision:");
  const unknown = all.filter((it) => it.action && !app.commands[it.action] && !special(it.action)).map((it) => it.action);
  const wrongKeys = all.filter((it) => it.action && app.commands[it.action] && it.keys !== app.commands[it.action].keys);
  check(spec.map((m) => m.title).join() === "File,Edit,View,Window,Help" && !unknown.length && !wrongKeys.length
    && all.find((it) => it.title === "Save")?.keys === app.commands.save.keys, "the Mac menus run the editor's commands, with their shortcuts",
  `${spec.map((m) => m.title)}; unknown ${unknown}; keys ${wrongKeys.map((it) => it.title)}`);
  const grid = !!app.prefs.show_grid;
  await app.menu("toggleGrid");
  const switched = !!app.prefs.show_grid !== grid && app.menuChecks().toggleGrid === !grid;
  await app.menu("toggleGrid");
  app.run("shortcuts");
  await app.menu("toggleGrid");
  const withDialog = !!app.prefs.show_grid === grid;
  for (const d of document.querySelectorAll("dialog[open]")) d.close();
  canvas.setColourVision("greyscale");
  const vision = app.menuChecks()["vision:greyscale"] && !app.menuChecks()["vision:normal"];
  await app.menu("vision:normal");
  check(switched && withDialog && vision && canvas.colourVision === "normal",
    "a menu item does what its command does and is ticked to match, and does nothing while a dialog is open",
    `${switched} ${withDialog} ${vision} ${canvas.colourVision}`);
  store.select([]);
  document.activeElement?.blur();
  const pageAll = !app.menuEdit("selectAll") && store.selection.length === store.scopeItems().filter((i) => !i.locked).length;
  store.select([]);
  inspector.render();
  const field = document.querySelector("#inspector input[type=text]");
  field.focus();
  const fieldOwn = app.menuEdit("selectAll") === true && store.selection.length === 0;
  field.blur();
  check(pageAll && fieldOwn, "Edit > Select All selects the page's objects, but leaves a text field to select its own text",
    `${pageAll} ${fieldOwn}`);
}

// Several windows: New and Open open another window unless this one is blank, the second of two
// documents opened at once gets a window of its own, each window keeps its own view switches,
// and a mosaic document dropped on the page adds its pages with what they use. The windows themselves
// are the app's (macopen.smoke checks those): openWindow is stood in for here
async function windowChecks(app, out) {
  const opened = [], realOpen = app.openWindow, realWindows = app.info.windows;
  app.info.windows = true;
  app.openWindow = async (path = null, slides = null) => { opened.push([path, slides]); return true; };
  const copy = (o) => JSON.parse(JSON.stringify(o));
  try {
    store.setDoc(await rpc("new_document"));
    await settle();
    check(app.isBlank(), "a new figure is blank");
    await app.newDocument();
    check(!opened.length && app.isBlank(), "New in a blank window replaces its figure, opening no window", JSON.stringify(opened));
    store.update("Something on the page", (doc) => doc.pages[0].items.push(gRectFor("wRect", 20, 20, 40, 30)));
    const inUse = store.doc;
    check(!app.isBlank(), "a figure with an object on it isn't blank");
    await app.newDocument();
    check(opened.length === 1 && opened[0][0] === null && store.doc === inUse, "New in a window in use opens a new window",
      JSON.stringify(opened));
    const empty = await rpc("new_document");
    const emptyPath = (await rpc("save_document", empty, `${out}/selftest-empty.mosaic`)).path;
    const secondPath = (await rpc("save_document", { ...empty, meta: { ...empty.meta, title: "Second" } }, `${out}/selftest-second.mosaic`)).path;
    opened.length = 0;
    await app.open(emptyPath);
    check(opened.length === 1 && opened[0][0] === emptyPath && store.doc === inUse, "Open in a window in use opens the document in a new window",
      JSON.stringify(opened));
    opened.length = 0;
    await app.open("/no/such/deck.pptx", { slides: [2, 3] });
    check(opened.length === 1 && opened[0][1]?.join() === "2,3", "a deck's chosen slides open in a new window when this one is in use",
      JSON.stringify(opened));
    // Two documents double-clicked at once, this window blank: the first here, the second in a
    // window of its own (though the first, saved with nothing on it, leaves this window blank)
    store.setDoc(await rpc("new_document"));
    opened.length = 0;
    await app.openFromSystem([emptyPath, secondPath]);
    check(store.path === emptyPath && app.isBlank() && opened.length === 1 && opened[0][0] === secondPath,
      "two documents opened at once: the first in the blank window, the second in a window of its own", `${store.path} ${JSON.stringify(opened)}`);
    const d = document.body.appendChild(document.createElement("dialog"));
    d.show();
    const busy = !app.isBlank();
    d.close();
    d.remove();
    check(busy && app.isBlank(), "a window with a dialog open isn't blank (a document from the Finder goes to a new window)");
    // View switches are each window's own; the app's settings are shared
    const before = { grid: !!app.prefs.show_grid, guides: app.prefs.show_guides !== false, dpi: app.prefs.default_dpi };
    await rpc("prefs_set", { show_grid: !before.grid, default_dpi: 301 });   // as another window saves them
    await app.savePrefs({ check_journal: app.prefs.check_journal || "" });
    check(!!app.prefs.show_grid === before.grid && app.prefs.default_dpi === 301,
      "saving a setting keeps this window's view switches, and takes the app's settings another window saved", JSON.stringify(app.prefs));
    await rpc("prefs_set", { show_guides: !before.guides, default_dpi: 302 });
    await app.refreshPrefs();
    check((app.prefs.show_guides !== false) === before.guides && app.prefs.default_dpi === 302,
      "coming to the front, a window takes the settings changed in another, not its view switches", JSON.stringify(app.prefs));
    await rpc("prefs_set", { show_grid: before.grid, show_guides: before.guides, default_dpi: before.dpi });
    Object.assign(app.prefs, { show_grid: before.grid, show_guides: before.guides, default_dpi: before.dpi });
    // A mosaic document dropped: its pages, with the swatches and symbols they use
    store.setDoc(await rpc("new_document"));
    store.update("Swatches and a symbol here", (doc) => {
      doc.swatches = [{ id: "sw_same", name: "Same", color: "#112233" }, { id: "sw_clash", name: "Here", color: "#445566" }];
      doc.symbols = [{ id: "sym_clash", name: "Here", items: [], size: [10, 10] }];
      doc.pages[0].items.push(gRectFor("wHere", 10, 10, 20, 20));
    });
    const got = { name: "Other", assets: {}, text_styles: [], object_styles: [], pages: [
      { id: "pg_o1", name: "Page 1", width: 300, height: 200, background: null, guides: { x: [5], y: [] }, items: [
        { ...gRectFor("o1", 10, 10, 30, 30), fill: { color: "#112233", opacity: 1, swatch: "sw_same" } },
        { ...gRectFor("o2", 50, 10, 30, 30), fill: { color: "#778899", opacity: 1, swatch: "sw_clash" } },
        { id: "o3", type: "symbol", symbol: "sym_clash", name: "", frame: [90, 10, 20, 20], rot: 0, flip_h: false, flip_v: false }] },
      { id: "pg_o2", name: "Page 2", width: 300, height: 200, background: null, guides: { x: [], y: [] }, items: [] }],
    symbols: [{ id: "sym_clash", name: "Theirs", items: [gRectFor("so", 0, 0, 20, 20)], size: [20, 20] },
      { id: "sym_unused", name: "Unused", items: [], size: [1, 1] }],
    swatches: [{ id: "sw_same", name: "Same", color: "#112233" }, { id: "sw_clash", name: "Theirs", color: "#778899" },
      { id: "sw_unused", name: "Unused", color: "#000000" }] };
    app.addFigurePages(copy(got), { list: false });
    const added = store.doc.pages[1], sw = store.doc.swatches, theirs = sw.find((s) => s.name === "Theirs");
    const sym = (store.doc.symbols || []).find((s) => s.name === "Theirs");
    check(store.doc.pages.length === 3 && store.pageIndex === 1 && added.width === 300 && added.id !== "pg_o1"
      && added.items.every((it) => !["o1", "o2", "o3"].includes(it.id)), "a mosaic document dropped on a page in use adds its pages after it, with new ids",
    `${store.doc.pages.length} pages, on ${store.pageIndex}`);
    check(sw.length === 3 && added.items[0].fill.swatch === "sw_same" && theirs && theirs.id !== "sw_clash"
      && added.items[1].fill.swatch === theirs.id && !sw.some((s) => s.id === "sw_unused"),
    "its swatches come too: one the same here is shared, one whose id means something else here gets a new id, unused ones don't",
    JSON.stringify(sw));
    check(sym && sym.id !== "sym_clash" && added.items[2].symbol === sym.id && !store.doc.symbols.some((s) => s.name === "Unused"),
      "and the symbols it uses, under a new id where this figure has one with theirs", JSON.stringify(store.doc.symbols));
    await app.undo();
    check(store.doc.pages.length === 1 && store.doc.swatches.length === 2 && store.doc.symbols.length === 1, "adding them is one undo step");
    store.setDoc(await rpc("new_document"));
    app.addFigurePages(copy(got), { list: false });
    const first = store.doc.pages[0];
    check(store.doc.pages.length === 2 && first.width === 300 && first.items.length === 3 && first.guides.x.join() === "5",
      "dropped on a blank page, the page takes the first one's place (with its guides, having none of its own)",
      `${store.doc.pages.length} pages; ${first.width} wide; ${first.items.length} objects`);
    app.addFigurePages(copy(got), { list: true, pageAt: 0 });
    check(store.doc.pages.length === 4 && store.pageIndex === 0 && store.doc.pages[0].width === 300 && store.doc.pages[2].items.length === 3,
      "dropped in the Pages list, they go in where it was dropped", `${store.doc.pages.length} pages, on ${store.pageIndex}`);
    await window.FA.onNativeDrop({ paths: [secondPath], x: 700, y: 450 });
    check(store.doc.pages.length === 5, "a mosaic document dropped on the window adds its pages", `${store.doc.pages.length} pages`);
    // The close question's Save (closing.py): saved, the window may close; the Save dialog
    // cancelled or the save failing, it stays open, saying why
    const closePath = (await rpc("save_document", empty, `${out}/selftest-close.mosaic`)).path;
    store.setDoc(await rpc("new_document"), closePath);
    store.update("Something to save", (doc) => doc.pages[0].items.push(gRectFor("wClose", 10, 10, 20, 20)));
    const saved = await app.saveToClose();
    check(saved && !store.dirty && (await rpc("open_document", closePath)).doc.pages[0].items.length === 1,
      "the close question's Save saves the figure, and then the window may close");
    store.update("Something unsaved", (doc) => doc.pages[0].items.push(gRectFor("wClose2", 40, 10, 20, 20)));
    const realSave = app.save;
    try {
      app.save = async () => {};   // (the Save dialog cancelled)
      const cancelled = await app.saveToClose();
      app.save = async () => { throw new Error("the disk is full"); };
      const failed = await app.saveToClose();
      const said = [...document.querySelectorAll("dialog[open]")].pop();
      check(!cancelled && !failed && store.dirty && /Couldn't save/.test(said?.textContent) && /the disk is full/.test(said?.textContent),
        "if that's cancelled or fails, the window stays open, saying why", said?.textContent);
      said?.close();
    } finally {
      app.save = realSave;
    }
  } finally {
    app.info.windows = realWindows;
    app.openWindow = realOpen;
  }
}

// Page sizes: slides and posters beside paper in the Page panel's list, the Home tab's Size menu
// (whatever is selected, journals' sizes too, Swap and Custom size), and the size new documents
// start at, from Settings
async function pageSizeChecks(app) {
  const menuItem = (text, sub = false) => [...document.querySelectorAll(`.context-menu${sub ? ".submenu" : ""} .menu-item`)]
    .find((b) => b.querySelector(".menu-label").textContent.startsWith(text));
  const sizeIs = (wmm, hmm) => near(store.page().width, wmm * MMPT, 0.01) && near(store.page().height, hmm * MMPT, 0.01);
  store.setDoc(await rpc("new_document"));
  await settle();
  store.select([]);
  const list = fieldByLabel("Standard size");
  const groups = [...list.querySelectorAll("optgroup")].map((g) => `${g.label}: ${[...g.children].map((o) => o.value).join(", ")}`);
  check(groups.join("; ") === "Paper: A4, US Letter; Slides: Slide 16:9, Slide 4:3, Slide 16:10; Posters: Poster 48 × 36 in, Poster A0",
    "the Page panel's Standard size list has paper, slides and posters, in groups", groups.join("; "));
  const journalList = fieldByLabel("Journal");
  check(groupsOf(journalList).join() === PUBLISHER_GROUPS && optionsIn(journalList, "Springer Nature").join() === "Heredity,Nature"
    && optionsIn(journalList, "In house").join() === "bioRxiv" && journalList.options[0].value === "",
  "the Page panel's Journal list groups the journals by publisher, as prose's Journal menu does",
  `${groupsOf(journalList).join()}; ${optionsIn(journalList, "Springer Nature")}`);
  await choose("Standard size", "Slide 4:3");
  check(sizeIs(254, 190.5) && store.page().preset?.standard === "Slide 4:3", "a 4:3 slide is 254 × 190.5 mm (10 × 7.5 in)", pageSize());
  await choose("Standard size", "Slide 16:9");
  check(near(store.page().width, 960, 0.01) && near(store.page().height, 540, 0.01), "a 16:9 slide is PowerPoint's 960 × 540 pt", pageSize());

  // The Size menu, with an object selected: the page's size ticked, a poster chosen, the selection kept
  store.update("Box", (doc) => doc.pages[store.pageIndex].items.push(gRectFor("szBox", 40, 40, 80, 50)), { select: ["szBox"] });
  await settle();
  const sizeBtn = document.querySelector('#rpanel-home [data-cmd="pageSize"]');
  document.getElementById("rtab-view").click();
  sizeBtn.click();
  const ticked = [...document.querySelectorAll(".context-menu .menu-item[aria-checked=true]")].map((b) => b.textContent);
  check(!document.getElementById("rpanel-home").hidden, "Size shows the Home tab, where it is (from command search, say)",
    document.getElementById("rpanel-home").hidden);
  check(document.querySelector(".context-menu") && ticked.length === 1 && /Slide 16:9/.test(ticked[0]) && menuItem("Poster A0")
    && menuItem("Journal")?.getAttribute("aria-haspopup") === "menu", "Size (Home tab) lists the sizes with the page's own ticked, and the journals",
    ticked.join() || "no menu");
  menuItem("Poster A0").click();
  check(sizeIs(841, 1189) && store.selection.join() === "szBox" && !document.querySelector(".context-menu"),
    "choosing one sizes the page, keeping the selection", `${pageSize()}; ${store.selection}`);
  sizeBtn.click();
  menuItem("Journal").click();
  const nature = menuItem("Nature: Double column", true);
  // (each journal's figure types, and "any size" for one that takes any width: bioRxiv)
  const allTypes = (app.info.journals || []).reduce((n, j) => n + j.types.length + (j.any_width ? 1 : 0), 0);
  check(nature && allTypes >= 35 && document.querySelectorAll(".context-menu.submenu .menu-item").length === allTypes,
    "its Journal submenu has every journal's figure types", `${document.querySelectorAll(".context-menu.submenu .menu-item").length} of ${allTypes}`);
  {
    const subEl = document.querySelector(".context-menu.submenu");
    const heads = [...subEl.querySelectorAll(".menu-heading")].map((x) => x.textContent).filter((g) => g !== "My journals");
    // (the lines under Springer Nature's heading, up to the next line between groups)
    const under = [];
    for (let el = [...subEl.querySelectorAll(".menu-heading")].find((x) => x.textContent === "Springer Nature")?.nextElementSibling;
      el && el.classList.contains("menu-item"); el = el.nextElementSibling) under.push(el.querySelector(".menu-label").textContent.split(":")[0]);
    check(heads.join() === PUBLISHER_GROUPS && [...new Set(under)].join() === "Heredity,Nature",
      "the Journal submenu has a heading for each publisher, its journals under it, as prose's Journal menu groups them",
      `${heads.join()}; Springer Nature: ${[...new Set(under)]}`);
    const first = document.activeElement;
    first?.dispatchEvent(new KeyboardEvent("keydown", { key: "n", bubbles: true, cancelable: true }));
    const jumped = document.activeElement?.querySelector(".menu-label")?.textContent || "";
    check(subEl.contains(first) && /^Nature: /.test(jumped), "a letter still jumps to the first journal starting with it, past the headings",
      `${first?.textContent} -> ${jumped}`);
  }
  nature?.click();
  check(sizeIs(180, 170) && store.page().preset?.journal === "Nature", "a journal's figure type from the menu", pageSize());
  sizeBtn.click();
  menuItem("Swap width and height").click();
  check(sizeIs(170, 180), "Swap width and height turns the page", pageSize());
  sizeBtn.click();
  menuItem("Custom size").click();
  const dlg = document.querySelector("dialog[open]");
  const widthLabel = dlg && [...dlg.querySelectorAll("label")].find((l) => l.textContent === "Width");
  const widthField = widthLabel && document.getElementById(widthLabel.htmlFor);
  widthField.value = "100";
  widthField.dispatchEvent(new Event("change", { bubbles: true }));
  check(sizeIs(100, 180) && !store.page().preset, "Custom size… types the page's width and height", pageSize());
  dlg.close();
  await until(() => !document.querySelector("dialog[open]"));
  // bioRxiv takes a figure of any size within a US Letter page's text area (7 × 9.5 in): from the Size
  // menu a page that fits keeps its size; a width typed in keeps the journal; Fit to content crops all round
  sizeBtn.click();
  menuItem("Journal").click();
  menuItem("bioRxiv: any size up to", true)?.click();
  const pre = () => JSON.stringify(store.page().preset);
  check(sizeIs(100, 180) && store.page().preset?.journal === "bioRxiv" && !store.page().preset?.type,
    "bioRxiv from the Size menu keeps a page within its 7 × 9.5 in text area at its own size", `${pageSize()}; ${pre()}`);
  inspector.setPageWidth(120 * MMPT);
  check(sizeIs(120, 180) && store.page().preset?.journal === "bioRxiv" && !store.page().preset?.type,
    "a width typed in keeps a bioRxiv page bioRxiv's (any width up to 7 in)", `${pageSize()}; ${pre()}`);
  inspector.setPageWidth(85.7 * MMPT);
  check(store.page().preset?.type === "One column", "at 85.7 mm it's bioRxiv's one-column preset", pre());
  await app.run("fitPage");
  await settle();
  check(store.page().width < 85 * MMPT && store.page().height < 60 * MMPT && store.page().preset?.journal === "bioRxiv" && !store.page().preset?.type,
    "Fit to content crops a bioRxiv page all round, and it stays bioRxiv's", `${pageSize()}; ${pre()}`);

  // Settings: the size new documents start at
  await app.run("preferences");
  const prefs = document.querySelector("dialog[open]");
  const sizeLabel = [...prefs.querySelectorAll("label")].find((l) => l.textContent === "Page size");
  const startSize = sizeLabel && document.getElementById(sizeLabel.htmlFor);
  const journalsListed = startSize ? [...startSize.querySelectorAll("optgroup")].map((g) => g.label) : [];
  startSize.value = JSON.stringify({ standard: "Slide 16:10" });
  startSize.dispatchEvent(new Event("change", { bubbles: true }));
  await until(() => app.prefs.new_page?.standard === "Slide 16:10");
  prefs.close();
  await until(() => !document.querySelector("dialog[open]"));
  await app.newDocument();
  check(journalsListed.slice(0, 4).join() === "Paper,Slides,Posters,AAAS (Science)"
    && journalsListed.slice(3).filter((g) => g !== "My journals").join() === PUBLISHER_GROUPS && sizeIs(254, 158.75)
    && store.page().preset?.standard === "Slide 16:10", "Settings gives new documents a size (journals' sizes in their publishers' groups): a 16:10 slide, 254 × 158.75 mm",
  `${journalsListed}; ${pageSize()}`);
  await app.savePrefs({ new_page: { standard: "A4" } });
  store.setDoc(await rpc("new_document"));
  check(sizeIs(210, 297), "and back to A4", pageSize());

  // Deleting the only page (from its menu in the Pages list): an empty page like it takes its
  // place, with its size, background and guides (asked first, as for any page with objects; the
  // self-test answers yes), and one undo brings it back
  store.update("Only page", (doc) => {
    Object.assign(doc.pages[0], { name: "Figure 3", width: 960, height: 540, background: "#ffffff",
      preset: { standard: "Slide 16:9" }, guides: { x: [100], y: [] } });
    doc.pages[0].items.push(gRectFor("onlyBox", 40, 40, 80, 50));
  });
  await settle();
  const before = JSON.stringify(store.doc.pages);
  document.querySelector('.page-list li[data-index="0"]').dispatchEvent(new MouseEvent("contextmenu",
    { clientX: 40, clientY: 150, bubbles: true, cancelable: true, button: 2 }));
  await until(() => document.querySelector(".context-menu"));
  const del = menuItem("Delete page"), offered = !!del && del.getAttribute("aria-disabled") !== "true";
  del?.click();
  await until(() => !store.items().length);
  const pg = store.page();
  check(offered && store.doc.pages.length === 1 && !pg.items.length && pg.name === "Page 1" && pg.width === 960 && pg.height === 540
    && pg.background === "#ffffff" && pg.preset?.standard === "Slide 16:9" && pg.guides.x.join() === "100"
    && pg.id !== JSON.parse(before)[0].id, "deleting the only page leaves an empty page of its size, background and guides",
  `${offered} ${JSON.stringify(pg)}`);
  await app.undo();
  check(JSON.stringify(store.doc.pages) === before, "and one undo brings it back", JSON.stringify(store.doc.pages[0]).slice(0, 200));
  store.setDoc(await rpc("new_document"));
}

// Exporting: once it works, the window closes and a note over the page names the files (with Show
// in Finder in the app). It goes after a while, not while pointed at; with warnings it stays,
// listing them, until closed. The figure report's window closes the same way. A press on the note
// stays off the page. (The note's 10 seconds are shortened here, for headless Chrome's time budget)
async function exportNoteChecks(app, out) {
  if (!out) return;
  const realExport = app.chooseExportBase, realReport = app.chooseReportBase, realSeconds = panels.noteSeconds;
  app.chooseExportBase = async () => `${out}/selftest-note`;
  app.chooseReportBase = async () => `${out}/selftest-note-report`;
  panels.noteSeconds = 0.4;
  const note = () => document.querySelector(".done-note");
  const lastDialog = () => [...document.querySelectorAll("dialog[open]")].pop();
  const press = (dlg, text) => [...dlg.querySelectorAll(".dialog-actions button")].find((b) => b.textContent === text).click();
  try {
    store.setDoc(await rpc("new_document"));
    store.update("Box", (doc) => doc.pages[0].items.push(gRectFor("exBox", 40, 40, 80, 50)), { select: ["exBox"] });
    await settle();
    await app.run("export");
    let dlg = lastDialog();
    for (const i of dlg.querySelectorAll(".formats input, .advanced input[value]")) i.checked = ["pdf", "svg"].includes(i.value);
    press(dlg, "Export…");
    await panels.writing;
    const text = note()?.querySelector("span")?.textContent || "", show = !!note()?.querySelector('button[aria-label^="Show in"]');
    check(!dlg.open && text === "Exported selftest-note.pdf and selftest-note.svg" && show === !!app.info.native
      && !note()?.querySelector(".warnings"), "a successful export closes its window, and a note over the page names the files",
    `open ${dlg.open}; ‹${text}›; show ${show}`);
    const span = note().querySelector("span"), r = span.getBoundingClientRect();
    const at = { clientX: r.left + 4, clientY: r.top + 4, bubbles: true, button: 0, buttons: 1, pointerId: 1, pointerType: "mouse" };
    span.dispatchEvent(new PointerEvent("pointerdown", at));
    span.dispatchEvent(new PointerEvent("pointerup", { ...at, buttons: 0 }));
    check(store.selection.join() === "exBox" && !canvas.op, "a press on the note doesn't reach the page", `${store.selection} ${canvas.op?.type}`);
    note().dispatchEvent(new PointerEvent("pointerenter"));
    await wait(panels.noteSeconds * 1000 + 300);
    const stayed = !!note();
    note()?.dispatchEvent(new PointerEvent("pointerleave"));
    await until(() => !note(), 5000);
    check(stayed && !note(), "it stays while pointed at, and goes a while after", `stayed ${stayed}; there ${!!note()}`);

    // Warnings (a second page of another size: PowerPoint has one slide size) go in the note, which stays
    await app.run("addPage");
    store.update("Wider page", (doc) => { doc.pages[1].width = 900; });
    await app.run("export");
    dlg = lastDialog();
    for (const i of dlg.querySelectorAll(".formats input, .advanced input[value]")) i.checked = i.value === "pptx";
    const pagesLabel = [...dlg.querySelectorAll("label")].find((l) => l.textContent === "Pages");
    document.getElementById(pagesLabel.htmlFor).value = "all";
    press(dlg, "Export…");
    await panels.writing;
    const warned = [...(note()?.querySelectorAll(".warnings li") || [])].map((li) => li.textContent);
    await wait(panels.noteSeconds * 1000 + 300);
    check(!dlg.open && /selftest-note\.pptx/.test(note()?.textContent || "") && warned.some((w) => /one slide size/.test(w)),
      "with warnings it closes too, and the note lists them and stays", `open ${dlg.open}; ${warned.join(" | ") || "no note"}`);
    note()?.querySelector(".done-note-close").click();
    check(!note(), "its × closes it");
    // A plain note (fonts embedded for placed PDFs) is a plain line, and doesn't keep the note open
    panels.doneNote("Exported selftest.pdf", [`${out}/selftest.pdf`], [], ["embedded fonts the placed PDFs lacked: Helvetica"]);
    const plain = note()?.querySelector(".notes li")?.textContent, warned2 = !!note()?.querySelector(".warnings");
    await until(() => !note(), 5000);
    check(plain === "Embedded fonts the placed PDFs lacked: Helvetica" && !warned2 && !note(),
      "fonts embedded for placed PDFs show as a plain line, and the note still goes by itself", `‹${plain}› warned ${warned2}`);

    await app.run("figureReport");
    dlg = lastDialog();
    dlg.querySelector('.formats input[value="csv"]').checked = true;
    press(dlg, "Write report…");
    await panels.writing;
    check(!dlg.open && note()?.querySelector("span")?.textContent === "Wrote the figure report: selftest-note-report.csv",
      "the figure report's window closes the same way", note()?.textContent || "no note");
    note()?.querySelector(".done-note-close").click();
  } finally {
    app.chooseExportBase = realExport;
    app.chooseReportBase = realReport;
    panels.noteSeconds = realSeconds;
    for (const d of document.querySelectorAll("dialog[open]")) d.close();
  }
}

// Picture menus: the Style tab's lists show the choice as a picture (drawn by the engine for a dash,
// an arrowhead or an outline) with its name, and open a menu with a picture beside every choice,
// starting on the ticked one; the keyboard opens and closes them. A list that changes nothing yet
// is greyed out, saying why; a line's outline has its left and right sides; shapes come in groups
async function pictureMenuChecks(app) {
  const line = (id) => ({ id, type: "line", points: [[60, 80], [260, 80]], rot: 0, arrow_end: { type: "triangle", w: "med", len: "med" },
    stroke: { color: "#1f3a93", width: 1.5, dash: "solid", cap: "round", join: "round", opacity: 1 } });
  store.setDoc(await rpc("new_document"));
  store.update("Picture menus", (doc) => doc.pages[0].items.push(line("pmLine"), { id: "pmStar", type: "shape", geom: "star5",
    frame: [300, 40, 80, 80], rot: 0, flip_h: false, flip_v: false, fill: { color: "#cfe3ff", opacity: 1 },
    stroke: { color: "#1f3a93", width: 1.5, dash: "solid", cap: "round", join: "round", opacity: 1 } }), { select: ["pmLine"] });
  await settle();
  inspector.render();
  document.getElementById("itab-style")?.click();
  const drawnIn = (el) => !!el?.querySelector(".pic-svg g")?.childElementCount;
  const items = () => [...document.querySelectorAll(".context-menu .menu-item")];
  const closeMenu = () => document.querySelector(".context-menu") && document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  let dash = fieldByLabel("Dash");
  await until(() => drawnIn(dash), 4000);
  check(dash?.classList.contains("pic-select") && dash.value === "solid" && dash.textContent.includes("Solid") && drawnIn(dash),
    "the Dash list shows its choice as a picture drawn by the engine, with its name", dash?.outerHTML.slice(0, 160));
  dash.click();
  await until(() => items().length && items().every((b) => drawnIn(b)), 4000);
  check(items().length === 9 && items().every((b) => drawnIn(b)) && document.activeElement === items()[0]
    && items()[0].getAttribute("aria-checked") === "true", "its menu has a picture beside every dash, starting on the ticked one",
  `${items().length} items, ${items().filter((b) => drawnIn(b)).length} drawn, focus on ${document.activeElement?.textContent}`);
  items().find((b) => b.dataset.value === "lgDash")?.click();
  await settle();
  check(store.item("pmLine").stroke.dash === "lgDash" && !document.querySelector(".context-menu"), "choosing one sets it",
    store.item("pmLine").stroke.dash);
  inspector.render();
  dash = fieldByLabel("Dash");
  dash.focus();
  dash.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
  const onTicked = document.activeElement?.dataset.value === "lgDash";
  document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  check(onTicked && !document.querySelector(".context-menu") && document.activeElement === dash,
    "↓ opens it on the ticked choice, and Escape closes it, back on the list", `${onTicked} ${document.activeElement?.className}`);
  const startSize = fieldByLabel("Start size");
  startSize.click();
  check(startSize.getAttribute("aria-disabled") === "true" && !document.querySelector(".context-menu")
    && /Choose an arrowhead first/.test(startSize.closest(".field").textContent), "a list that changes nothing yet is greyed out, says why, and doesn't open",
  `${startSize.getAttribute("aria-disabled")} ${startSize.closest(".field").textContent}`);
  fieldByLabel("End").click();
  await until(() => items().length && items().every((b) => drawnIn(b)), 4000);
  check(items().length === 10 && items().every((b) => drawnIn(b)), "the arrowheads have pictures too", `${items().length}`);
  closeMenu();
  // Five sizes, extra small to extra large, each pictured whole (an extra large head is 16 pt across)
  fieldByLabel("End size").click();
  await until(() => items().length && items().every((b) => drawnIn(b)), 4000);
  const fits = (b) => {
    const svg = b.querySelector(".pic-svg"), box = svg.querySelector("g").getBBox(), [, , w, ht] = svg.getAttribute("viewBox").split(" ").map(Number);
    return box.height > 0 && box.x >= 0 && box.y >= 0 && box.x + box.width <= w && box.y + box.height <= ht;
  };
  const sizes = items().map((b) => b.dataset.value);
  const heights = items().map((b) => Math.round(b.querySelector(".pic-svg g").getBBox().height * 10) / 10);
  check(sizes.join() === "xs,sm,med,lg,xl" && items().every((b) => drawnIn(b) && fits(b)) && heights.every((v, i) => !i || v > heights[i - 1]),
    "the End size list goes from Extra small to Extra large, each pictured whole and bigger than the last",
    `${sizes.join()} heights ${heights.join()} fit ${items().map(fits).join()}`);
  items().find((b) => b.dataset.value === "xl")?.click();
  await settle();
  const xl = store.item("pmLine").arrow_end;
  check(xl.w === "xl" && xl.len === "xl" && fieldByLabel("End size").textContent.includes("Extra large"),
    "choosing Extra large sets the head's width and length", JSON.stringify(xl));
  await app.undo();
  closeMenu();
  fieldByLabel("Outline around it")?.click();
  await settle();
  fieldByLabel("Sides").click();
  await until(() => items().length && items().every((b) => drawnIn(b)), 4000);
  check(items().map((b) => b.dataset.value).join() === "left,right,both" && items().every((b) => drawnIn(b))
    && items().slice(0, 2).every((b) => b.querySelector("clipPath")), "a line's outline Sides are its left and right and both, each pictured",
  items().map((b) => `${b.dataset.value} ${drawnIn(b)}`).join());
  closeMenu();
  store.select(["pmStar"]);
  inspector.render();
  fieldByLabel("Shape").click();
  const headings = [...document.querySelectorAll(".context-menu .menu-heading")].map((x) => x.textContent);
  check(headings.length === shapeCatalog.groups.length && document.activeElement?.dataset.value === "star5"
    && items().every((b) => b.querySelector(".menu-pic svg")), "the Shape list comes in its groups, each shape with its icon, starting on its own",
  `${headings.length} groups; on ${document.activeElement?.dataset.value}`);
  closeMenu();
  store.select(["pmLine"]);
  inspector.render();
  fieldByLabel("Corners").click();
  const corners = items().map((b) => b.querySelector(".menu-pic path")?.getAttribute("d"));
  check(new Set(corners).size === 3 && items().every((b) => b.querySelectorAll(".menu-pic path").length === 2),
    "the Corners pictures are a thick line's outline, its corner square, rounded or cut across", corners.join(" | "));
  closeMenu();
  // A colour too faint to see against the menu is pictured grey (on the menu's highlighted row, in
  // that row's text colour); one that stands out keeps its own
  const panel = getComputedStyle(document.documentElement).getPropertyValue("--panel").trim();
  const strong = luminance(parseHex(panel) || "#ffffff") > 0.18 ? "#000000" : "#ffffff";
  const recolour = async (color) => {
    store.update("Line colour", (doc) => {
      const l = doc.pages[0].items.find((i) => i.id === "pmLine");
      l.stroke = { ...l.stroke, color };
    }, { select: ["pmLine"] });
    await settle();
    inspector.render();
    await until(() => drawnIn(fieldByLabel("Dash")), 4000);
    return fieldByLabel("Dash").querySelector(".pic-svg");
  };
  const faint = await recolour(panel);
  check(faint.classList.contains("pic-ink") && faint.innerHTML.includes("currentColor") && !faint.innerHTML.includes(panel)
    && fieldByLabel("Corners").querySelector("path")?.getAttribute("fill") === "currentColor",
  "a line the colour of the menu is pictured grey", faint.innerHTML.slice(0, 160));
  fieldByLabel("Dash").click();
  await until(() => items().length && items().every((b) => drawnIn(b)), 4000);
  const probe = document.body.appendChild(document.createElement("span"));
  probe.style.color = "var(--muted)";
  const grey = getComputedStyle(probe).color, colour = (el) => el && getComputedStyle(el).color;
  probe.remove();
  const [on, off] = [document.activeElement, items().find((b) => b !== document.activeElement)];
  check(colour(off?.querySelector(".pic-ink")) === grey && (!on?.matches(":focus") || colour(on.querySelector(".pic-ink")) === colour(on)),
    "in its menu too, the highlighted row's in that row's text colour",
    `${colour(off?.querySelector(".pic-ink"))} vs ${grey}; ${colour(on?.querySelector(".pic-ink"))} vs ${colour(on)}`);
  closeMenu();
  const own = await recolour(strong);
  check(own.innerHTML.includes(strong) && !own.innerHTML.includes("currentColor"), "a line that stands out against the menu keeps its colour",
    own.innerHTML.slice(0, 160));
  // Changing to a theme it's faint in pictures it grey at once (dark for a black line, light for a white one)
  const keep = { theme: app.prefs.theme, theme_day: app.prefs.theme_day, theme_night: app.prefs.theme_night };
  const other = strong === "#000000" ? "dark" : "light", panelNow = () => getComputedStyle(document.documentElement).getPropertyValue("--panel").trim();
  await app.savePrefs({ theme: other });
  await until(() => panelNow() === (app.info.themes || []).find((t) => t.id === other)?.colors.panel, 4000);
  const greyNow = () => fieldByLabel("Dash")?.querySelector(".pic-svg")?.innerHTML.includes("currentColor");
  await until(() => greyNow(), 4000);
  check(greyNow(), `changing to the ${other === "dark" ? "Dark" : "Light"} theme, where it's faint, pictures it grey at once`,
    fieldByLabel("Dash")?.querySelector(".pic-svg")?.innerHTML.slice(0, 160));
  await app.savePrefs(keep);
  await until(() => panelNow() === panel, 4000);
  // Fill reaches: the middle of the line, its inner edge or its outer edge, for a dashed line;
  // greyed out, saying why, for a solid one
  store.update("A dashed box", (doc) => doc.pages[store.pageIndex].items.push({ id: "pmBox", type: "shape", geom: "rect",
    frame: [400, 300, 100, 60], rot: 0, flip_h: false, flip_v: false, fill: { color: "#cccccc", opacity: 1 },
    stroke: { color: "#000000", width: 6, dash: "dash", cap: "flat", join: "miter", opacity: 1 } }), { select: ["pmBox"] });
  inspector.render();
  document.getElementById("itab-style")?.click();
  await choose("Fill reaches", "inner");
  await settle();
  const boxPath = canvas.els.get("pmBox")?.g.querySelector("path")?.getAttribute("d") || "";
  check(store.item("pmBox").fill_reach === "inner" && boxPath.startsWith("M403"),
    "Fill reaches: Inner edge stops a dashed box's fill at its line's inner edge", `${store.item("pmBox").fill_reach} ${boxPath.slice(0, 40)}`);
  store.update("Solid line", (doc) => { findItem(doc, "pmBox").stroke.dash = "solid"; });
  const reachList = fieldByLabel("Fill reaches");
  check(reachList?.getAttribute("aria-disabled") === "true" && /dashed, dotted or see-through/.test(reachList.closest(".field").textContent),
    "with a solid line it's greyed out, saying it's for dashed, dotted or see-through lines", reachList?.closest(".field").textContent);
}

// Clicks pick shapes by what's drawn of them: an empty one (no fill, or a clear one) only by its
// line or its text, a click inside it reaching what's under it; an ellipse inside its curve, not at
// its frame's corners. A selected empty shape drags from inside, and a click there picks what's under
// An area fill whose lines are nudged or have an end dragged a little off a corner keeps its fill
// (small gaps bridged); dragged well away, it has no area: selected, its last outline shows
// dashed and the panel says why; Undo brings it back
async function areaGapChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const snapWas = app.prefs.snap;
  await app.savePrefs({ snap: false });
  const lineItem = (id, a, b) => ({ id, type: "line", points: [a, b], arrow_start: null, arrow_end: null,
    stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 } });
  store.update("Triangle", (doc) => doc.pages[store.pageIndex].items.push(lineItem("gp1", [100, 300], [200, 120]),
    lineItem("gp2", [200, 120], [300, 300]), lineItem("gp3", [300, 300], [100, 300])), { select: [] });
  await settle();
  key("f");
  pointer("pointerdown", screenOf(200, 250));
  pointer("pointerup", screenOf(200, 250), { buttons: 0 });
  await until(() => store.items().some((i) => i.geom === "region"), 4000);
  await settle();
  const area = () => store.items().find((i) => i.geom === "region");
  const drawn = () => !!canvas.els.get(area()?.id)?.g.querySelector("path");
  await until(drawn, 3000);
  store.select(["gp3"]);
  key("ArrowDown");
  await settle();
  await settle();
  const moved = store.item("gp3").points[0][1] > 300.5;
  check(moved && drawn(), "a line nudged off its corners with an arrow key keeps the fill", JSON.stringify(store.item("gp3").points));
  app.run("undo");
  await settle();
  store.select(["gp3"]);
  await settle();
  await drag([300, 300], [302, 302.5]);
  await settle();
  await settle();
  check(drawn() && !canvas.areaLost(area().id), "an end dragged a couple of points off its corner keeps the fill",
    JSON.stringify(store.item("gp3").points));
  await drag([302, 302.5], [340, 340]);
  await until(() => canvas.areaLost(area().id), 3000);
  store.select([area().id]);
  await settle();
  inspector.render();
  check(!drawn() && canvas.overlay.querySelector(".area-lost") && document.querySelector("#inspector .area-lost-note"),
    "dragged well away, the fill has no area: selected, its last outline shows dashed and the panel says why");
  app.run("undo");
  await until(() => drawn(), 3000);
  await settle();
  inspector.render();
  check(drawn() && !canvas.areaLost(area().id) && !canvas.overlay.querySelector(".area-lost") && !document.querySelector("#inspector .area-lost-note"),
    "Undo brings the fill back, and the note goes");
  await app.savePrefs({ snap: snapWas });
  store.select([]);
}

// Crops besides dragging edges (crop.js): to an aspect ratio (then crop mode, corners keeping
// it), to a typed width or height from the middle, to a shape drawn over the picture; never
// rescaling the picture or moving what it shows
async function cropChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const plot = btoa('<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="120pt" viewBox="0 0 200 120">'
    + '<rect x="0" y="0" width="200" height="120" fill="#336699"/><circle cx="100" cy="60" r="30" fill="#e69f00"/></svg>');
  const path = await rpc("selftest_scratch", "crop_plot.svg", plot);
  await app.placeFiles([path], [60, 80], false);
  const id = store.items().find((it) => it.type === "picture")?.id;
  if (!id) return log(false, "a picture is placed for the crops", path);
  const pic = () => store.item(id);
  const placement = () => canvas.fullFrame(pic()).m.map((v) => +v.toFixed(6)).join(",");
  const scale = () => pic().frame[2] / (200 * (1 - pic().crop[0] - pic().crop[2]));
  const mid = () => [pic().frame[0] + pic().frame[2] / 2, pic().frame[1] + pic().frame[3] / 2];
  const placed = placement(), [x0, y0] = pic().frame;
  store.select([id]);

  // Aspect ratio: the largest square the picture holds, about its middle, then crop mode
  cropToRatio(id, 1, 1);
  await settle();
  let f = pic().frame, c = pic().crop;
  check(near(f[2], 120, 1e-6) && near(f[3], 120, 1e-6) && near(c[0], c[2], 1e-9) && near(c[0], 0.2, 1e-9) && placement() === placed
    && near(scale(), 1, 1e-9) && canvas.cropping === id && canvas.cropRatio === 1,
  "1:1 crops to the largest square, from the middle, at the same scale and place, and opens crop mode", JSON.stringify([f, c]));
  // A corner keeps the ratio while cropping; Shift crops freely
  await drag([f[0] + f[2], f[1] + f[3]], [f[0] + f[2] - 30, f[1] + f[3] - 10]);
  f = pic().frame;
  check(near(f[2], 90, 1e-6) && near(f[3], 90, 1e-6) && near(f[0], x0 + 40, 1e-6) && placement() === placed,
    "dragging a corner keeps the square, following the way the pointer changed it more", JSON.stringify(f));
  await drag([f[0] + f[2], f[1] + f[3]], [f[0] + f[2] - 30, f[1] + f[3] - 10], { shiftKey: true });
  f = pic().frame;
  check(near(f[2], 60, 1e-6) && near(f[3], 80, 1e-6), "with Shift, a corner crops freely", JSON.stringify(f));
  await drag([f[0] + f[2], f[1] + f[3] / 2], [f[0] + f[2] + 20, f[1] + f[3] / 2]);
  check(near(pic().frame[2], 80, 1e-6) && near(pic().frame[3], 80, 1e-6), "a side crops freely", JSON.stringify(pic().frame));
  app.run("crop");   // (Enter, or the Crop button: already cropping, it stays so)
  canvas.endCrop();
  check(canvas.cropRatio === null && !canvas.cropping, "finishing the crop lets the ratio go");
  // Landscape 16:9 on a 5:3 picture: as wide as it is, centred on what showed
  cropToRatio(id, 16, 9);
  await settle();
  f = pic().frame;
  check(near(f[2], 200, 1e-6) && near(f[3], 112.5, 1e-6) && near(f[2] / f[3], 16 / 9, 1e-9) && placement() === placed,
    "16:9 on a wider-than-tall picture takes its whole width", JSON.stringify(f));
  canvas.endCrop();
  check(JSON.stringify(parseRatio("7:5")) === "[7,5]" && JSON.stringify(parseRatio(" 1.5 ")) === "[1.5,1]"
    && JSON.stringify(parseRatio("16 x 10")) === "[16,10]" && parseRatio("wide") === null && parseRatio("0:3") === null,
  "a typed ratio reads 7:5, 1.5 and 16 x 10, and nothing else");

  // A typed width or height: from the middle, the same scale and place; past the picture, all of it
  resetCrop(id);
  await settle();
  check(JSON.stringify(pic().crop) === "[0,0,0,0]" && near(pic().frame[2], 200, 1e-6), "Reset crop shows all of it again");
  const before = mid();
  const width = fieldByLabel("Crop to width");
  width.value = toUnit(100, inspector.units());
  width.dispatchEvent(new Event("change"));
  await settle();
  f = pic().frame;
  check(near(f[2], 100, 1e-3) && near(f[3], 120, 1e-6) && near(mid()[0], before[0], 1e-3) && near(mid()[1], before[1], 1e-6)
    && placement() === placed && near(scale(), 1, 1e-9),
  "the Picture tab's Crop to width crops from the middle, at the same scale and place", JSON.stringify(f));
  cropToSize(id, 3, 500);
  await settle();
  check(near(pic().frame[3], 120, 1e-6) && placement() === placed, "a height past the picture's shows all of it that way");
  cropToSize(id, 2, 190);   // (from the middle, 150 → 190 runs into no edge; then 100 off-centre at the left edge)
  await settle();
  store.update("Off-centre", (doc) => { const o = findDeep(doc.pages[store.pageIndex].items, id); Object.assign(o, canvas.cropped(o, [0, 0, 0.6, 0])); });
  await settle();
  cropToSize(id, 2, 120);
  await settle();
  check(near(pic().crop[0], 0, 1e-9) && near(pic().frame[2], 120, 1e-6) && placement() === placed,
    "at the picture's edge, the rest comes from the other side", JSON.stringify(pic().crop));
  resetCrop(id);
  await settle();

  // The ribbon's Crop button and menu
  const menu = () => cropMenu(async () => null).filter((e) => e !== "-").map((e) => `${e.label}${e.disabled ? " (off)" : ""}`).join(", ");
  store.select([id]);
  const withPic = menu();
  store.select([]);
  const without = menu();
  check(document.querySelector('#rpanel-figure [data-cmd="crop"]') && withPic === "Crop, Aspect ratio, Crop to shape, "
    + "Crop to shape drawn over it (off), Reset crop" && without.startsWith("Crop (off), Aspect ratio (off)"),
  "the Figure tab has Crop, and ▾ beside it offers aspect ratios, shapes, a shape drawn over it and Reset crop", `${withPic} | ${without}`);

  // A shape drawn over it: a preset square to the picture and wholly over it becomes its crop
  // shape (adjustments and all), its line the picture's border, and it's used up
  const red = { color: "#d55e00", width: 1.5, dash: "solid", cap: "round", join: "round", opacity: 1 };
  store.update("Ellipse", (doc) => doc.pages[store.pageIndex].items.push({ ...gRectFor("cE", x0 + 50, y0 + 30, 70, 50),
    geom: "roundRect", adj: { adj: 0.3 }, stroke: red }), { select: [id, "cE"] });
  await settle();
  check(menu().includes("Crop to shape drawn over it,") && !menu().includes("drawn over it (off)"),
    "with a picture and a shape selected, Crop to shape drawn over it is offered");
  await cropToDrawnShape();
  await settle();
  f = pic().frame;
  check(near(f[0], x0 + 50, 1e-6) && near(f[1], y0 + 30, 1e-6) && near(f[2], 70, 1e-6) && near(f[3], 50, 1e-6)
    && pic().mask?.geom === "roundRect" && pic().mask.adj?.adj === 0.3 && pic().border?.color === "#d55e00" && pic().border.width === 1.5
    && !store.item("cE") && placement() === placed && JSON.stringify(store.selection) === JSON.stringify([id]),
  "a rounded rectangle over it: the picture cropped to it where it lies, its corners and line kept, the shape used up",
  JSON.stringify([f, pic().mask, pic().border]));
  const clipped = !!canvas.els.get(id)?.g.querySelector("[clip-path]");
  check(clipped, "and the picture is drawn clipped to it");
  app.run("undo");
  await settle();
  check(store.item("cE") && !pic().mask && near(pic().frame[2], 200, 1e-6), "Undo brings the shape back and the picture whole");
  // Turned, and reaching past the picture: its outline, where the two overlap
  store.update("Star", (doc) => {
    doc.pages[store.pageIndex].items = doc.pages[store.pageIndex].items.filter((it) => it.id !== "cE");
    doc.pages[store.pageIndex].items.push({ ...gRectFor("cS", x0 + 150, y0 + 20, 80, 80), geom: "star5", rot: 20, stroke: null });
  }, { select: [id, "cS"] });
  await settle();
  await cropToDrawnShape();
  await settle();
  f = pic().frame;
  const sub = pic().mask?.path?.subpaths?.[0];
  check(pic().mask?.geom === "custom" && sub && near(sub.w, f[2], 1e-9) && near(f[0] + f[2], x0 + 200, 1e-6) && f[0] > x0 + 140
    && f[1] >= y0 && f[1] + f[3] <= y0 + 120 + 1e-6 && !pic().border && !store.item("cS") && placement() === placed,
  "a turned star past the picture's right edge: its outline, the frame where it and the picture overlap", JSON.stringify([f, sub?.w]));
  const drawnD = (await rpc("area_path", pic(), true))?.d || "";
  check(drawnD.length > 20 && !!canvas.els.get(id)?.g.querySelector("[clip-path]"), "and the picture is clipped to that outline", drawnD.slice(0, 40));
  inspector.render();
  const shapeField = fieldByLabel("Crop to shape");
  check(shapeField && /drawn over it/.test(shapeField.textContent + (shapeField.getAttribute("aria-label") || "") + (shapeField.title || "")),
    "the Picture tab's Crop to shape names it as the shape drawn over it", shapeField?.textContent);
  // A shape away from the picture changes nothing
  store.update("Away", (doc) => { const o = findDeep(doc.pages[store.pageIndex].items, id); delete o.mask; Object.assign(o, canvas.cropped(o, [0, 0, 0, 0]));
    doc.pages[store.pageIndex].items.push({ ...gRectFor("cA", o.frame[0] + o.frame[2] + 60, o.frame[1], 40, 40), geom: "ellipse" }); },
  { select: [id, "cA"] });
  await settle();
  const was = JSON.stringify(pic());
  await cropToDrawnShape();
  await settle();
  check(JSON.stringify(pic()) === was && !!store.item("cA"), "a shape that isn't over the picture changes nothing", Object.keys(pic()).filter((k) => JSON.stringify(pic()[k]) !== JSON.stringify(JSON.parse(was)[k])).map((k) => `${k}: ${JSON.stringify(JSON.parse(was)[k])} to ${JSON.stringify(pic()[k])}`).join("; ").replace(/"/g, "'"));
  store.select([]);
}

// The Freeform tool: clicks place corners joined by straight lines, a drag draws freehand, fitted
// with a few smooth curves that keep close to where the pointer went; a click on the first point,
// or a drag let go there, closes the shape; Backspace takes a freehand stretch back whole
async function freeformChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const snapWas = app.prefs.snap;
  await app.savePrefs({ snap: false });
  const along = async (pts) => {
    pointer("pointerdown", screenOf(...pts[0]));
    for (const q of pts.slice(1)) pointer("pointermove", screenOf(...q));
    pointer("pointerup", screenOf(...pts.at(-1)));
    await settle();
  };
  // A wave down the page, from a point, as a hand would drag it (a little wobble too)
  const wave = (x, y0, y1, n = 80) => Array.from({ length: n + 1 }, (_, i) =>
    [x + 25 * Math.sin((2 * Math.PI * i) / n) + 0.3 * Math.sin(i * 2.7), y0 + ((y1 - y0) * i) / n]);
  const tol = () => Math.max(0.5, 2 / canvas.k) + 0.05;
  const cubicPts = (item) => {
    const r = ringsOf(item)[0], out = [], P = (q) => toPageOf(item, q);
    const segs = r.nodes.map((a, i) => [a, r.nodes[(i + 1) % r.nodes.length]]).slice(0, r.closed ? r.nodes.length : r.nodes.length - 1);
    for (const [a, b] of segs) {
      const c = [a.p, a.hout || a.p, b.hin || b.p, b.p].map(P);
      for (let k = 0; k <= 60; k++) {
        const t = k / 60, u = 1 - t;
        out.push([0, 1].map((d) => u * u * u * c[0][d] + 3 * u * u * t * c[1][d] + 3 * u * t * t * c[2][d] + t * t * t * c[3][d]));
      }
    }
    return out;
  };
  const farthest = (pts, onPath) => Math.max(...pts.map((p) => Math.min(...onPath.map((q) => Math.hypot(p[0] - q[0], p[1] - q[1])))));

  canvas.setTool("freeform");
  check(document.querySelector('#toolbox [data-tool="freeform"]')?.getAttribute("aria-pressed") === "true",
    "the Freeform tool is in the drawing tools");
  await drag([100, 100], [100, 100]);
  await drag([200, 100], [200, 100]);
  const w = wave(200, 100, 260);
  await along(w);
  const during = canvas.pen?.nodes.length;
  await drag([100, 100], [100, 100]);
  const shape = store.selected()[0], ring = shape && ringsOf(shape)[0];
  const curve = shape ? farthest(w, cubicPts(shape)) : Infinity;
  check(shape?.geom === "custom" && ring.closed && canvas.tool === "select" && during >= 4 && during < 20,
    "clicks and a freehand drag make a closed freeform shape, the drag a few smooth curves",
    `${shape?.geom} closed=${ring?.closed} nodes while drawing=${during}`);
  check(curve < tol() && near(ring.nodes[0].p[0], toLocal(shape, [100, 100])[0], 1e-6),
    "the curves keep within half a point (or two pixels) of where the pointer went, and the clicks are corners",
    `${curve.toFixed(3)} pt (tolerance ${tol().toFixed(3)})`);
  const sides = cubicPts(shape).filter((p) => Math.abs(p[1] - 100) < 1e-6 && p[0] > 101 && p[0] < 199);
  check(sides.length > 10, "between two clicks the line is straight");
  // A drag let go on the first point closes the shape
  canvas.setTool("freeform");
  await drag([300, 300], [300, 300]);
  await along([[400, 300], ...Array.from({ length: 40 }, (_, i) => [400 - 2.5 * (i + 1), 300 + 40 * Math.sin((Math.PI * (i + 1)) / 40)])]);
  const loop = store.selected()[0];
  check(loop?.id !== shape.id && loop?.geom === "custom" && ringsOf(loop)[0].closed, "a freehand drag let go on the first point closes the shape");
  // Backspace takes back a whole freehand stretch; clicks alone make a line
  canvas.setTool("freeform");
  await drag([100, 400], [100, 400]);
  await along(wave(150, 400, 500));
  const before = canvas.pen?.nodes.length;
  key("Backspace");
  const after = canvas.pen?.nodes.length;
  key("Enter");
  const line = store.selected()[0];
  check(before > 3 && after === 2 && line?.type === "line" && line.points.length === 2,
    "Backspace takes back the whole freehand stretch; corners alone make an ordinary line", `${before} -> ${after}, ${line?.type}`);
  await app.savePrefs({ snap: snapWas });
  store.select([]);
}

// Several objects' Style tab: shapes, an arrow and a line inside a group selected together show
// what they share, blank ("Mixed") where they differ, and a change goes to every one that can
// take it, the line in the group too, as one undo step; a group selected alone has the tab too
async function multiLookChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  const black = (w) => ({ color: "#000000", width: w, dash: "solid", cap: "round", join: "round", opacity: 1 });
  store.update("Objects", (doc) => {
    doc.pages[store.pageIndex].items.push(
      { ...gRectFor("mR1", 40, 40, 80, 40), stroke: black(1), fill: { color: "#ff0000", opacity: 1 } },
      { ...gRectFor("mR2", 140, 40, 80, 40), stroke: black(2), fill: { color: "#0000ff", opacity: 1 } },
      { id: "mA", type: "line", points: [[40, 120], [200, 120]], arrow_start: null, arrow_end: { type: "triangle", w: "med", len: "med" },
        stroke: black(1) },
      { id: "mG", type: "group", items: [{ id: "mGL", type: "line", points: [[40, 160], [200, 160]], arrow_start: null, arrow_end: null,
        stroke: black(0.5) }, { ...gRectFor("mGR", 40, 180, 40, 20), fill: { color: "#ff0000", opacity: 1 } }] });
  }, { select: ["mR1", "mR2", "mA", "mG"] });
  await settle();
  inspector.render();
  document.getElementById("itab-style")?.click();
  const fieldFor = (text) => {
    const l = [...document.querySelectorAll("#inspector label")].find((x) => x.textContent === text);
    return l ? document.getElementById(l.htmlFor) : null;
  };
  const width = fieldFor("Line width"), colour = fieldFor("Line colour");
  check(document.getElementById("itab-style") && width && width.value === "" && width.placeholder === "Mixed"
    && document.getElementById(`${colour?.id}-hex`)?.value === "#000000",
  "several objects have a Style tab: widths that differ are blank (Mixed), the colour they share shows", `${width?.value} ${width?.placeholder}`);
  const steps = store.history.length;
  await choose("Line width", "0.75");
  const widths = ["mR1", "mR2", "mA", "mGL", "mGR"].map((id) => store.item(id).stroke.width);
  check(widths.every((w) => w === 0.75) && store.history.length === steps + 1,
    "a width typed in goes to every line and shape, those in the group too, as one undo step", widths.join(" "));
  inspector.render();
  const fillHex = document.getElementById(`${fieldFor("Fill colour")?.id}-hex`);
  check(fillHex && fillHex.value === "" && fillHex.placeholder === "Mixed", "fill colours that differ are blank", fillHex?.value);
  fillHex.value = "#00ff00";
  fillHex.dispatchEvent(new Event("change"));
  await settle();
  check(["mR1", "mR2", "mGR"].every((id) => store.item(id).fill?.color === "#00ff00") && !("fill" in store.item("mA")),
    "a fill colour goes to the shapes; the lines don't get a fill", JSON.stringify(store.item("mR1").fill));
  inspector.render();
  const endWas = fieldFor("End")?.querySelector(".pic-label")?.textContent;
  await choose("End", "stealth");
  check(endWas === "Mixed" && store.item("mA").arrow_end?.type === "stealth" && store.item("mGL").arrow_end?.type === "stealth"
    && !store.item("mR1").arrow_end, "arrowheads that differ read Mixed; a choice goes to the lines (not the rectangles)", endWas);
  await choose("Dash", "dash");
  check(["mR1", "mR2", "mA", "mGL", "mGR"].every((id) => store.item(id).stroke.dash === "dash"), "a dash goes to them all");
  await choose("Corner rounding", "20");
  check(["mR1", "mR2", "mGR"].every((id) => store.item(id).rounding === 0.2), "corner rounding goes to every rectangle");
  // A line never loses its line
  await choose("Line", "none");
  check(store.item("mR1").stroke === null && store.item("mA").stroke && store.item("mGL").stroke,
    "No line takes the shapes' lines away and leaves the lines theirs");
  store.select(["mG"]);
  await settle();
  inspector.render();
  check(!!document.getElementById("itab-style") && fieldFor("Line width")?.value === "0.75",
    "a group selected alone has the Style tab too, showing what its objects share", fieldFor("Line width")?.value);
  store.select([]);
}

// Dash spacing: the gaps between dashes and dots as a percentage of the style's, in the Line
// section; the Dash menu's pictures are drawn at 2 pt so dots show
async function dashSpacingChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  store.update("Line", (doc) => doc.pages[store.pageIndex].items.push({ id: "dL", type: "line", points: [[40, 100], [300, 100]],
    arrow_start: null, arrow_end: null, stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 } }),
  { select: ["dL"] });
  await settle();
  inspector.render();
  document.getElementById("itab-style")?.click();
  const fieldFor = (text) => {
    const lab = [...document.querySelectorAll("#inspector label")].find((l) => l.textContent === text);
    return lab ? document.getElementById(lab.htmlFor) : null;
  };
  check(!fieldFor("Dash spacing"), "a solid line has no dash spacing");
  store.update("Dotted", (doc) => { findItem(doc, "dL").stroke.dash = "sysDot"; });
  await settle();
  inspector.render();
  const spacing = fieldFor("Dash spacing");
  check(spacing && spacing.value === "100", "a dotted line's Line section has Dash spacing, at 100%", spacing?.value);
  spacing.value = "50";
  spacing.dispatchEvent(new Event("change"));
  await settle();
  check(store.item("dL").stroke.dash_spacing === 0.5, "50% halves the gaps", JSON.stringify(store.item("dL").stroke));
  inspector.render();
  fieldFor("Dash spacing").value = "100";
  fieldFor("Dash spacing").dispatchEvent(new Event("change"));
  await settle();
  check(!("dash_spacing" in store.item("dL").stroke), "back to 100% is the style as it was", JSON.stringify(store.item("dL").stroke));
  inspector.render();
  // (dots as filled circles, as wide as the line: the Mac app leaves out some of the engine's
  // 0.001 pt dots on a 1x screen; with PowerPoint's spacing too, since the pictures space them evenly)
  store.update("PowerPoint spacing", (doc) => { findItem(doc, "dL").stroke.even_dashes = false; });
  await settle();
  inspector.render();
  fieldFor("Dash").click();
  const pics = () => [...document.querySelectorAll(".context-menu .menu-item .pic-svg g")];
  await until(() => pics().length === 9 && pics().every((p) => p.childElementCount), 4000);
  const widths = pics().flatMap((p) => [...p.querySelectorAll("path")].map((x) => x.getAttribute("style")?.match(/stroke-width:([\d.]+)/)?.[1]));
  const radii = pics().flatMap((p) => [...p.querySelectorAll("circle")].map((c) => c.getAttribute("r")));
  check(widths.length >= 7 && widths.every((w) => w === "2") && radii.length && radii.every((r) => r === "1"),
    "the Dash menu draws every style at 2 pt", `${widths.join(" ")}; dots ${radii.join(" ")}`);
  const pic = (v) => document.querySelector(`.context-menu .menu-item[data-value="${v}"] .pic-svg g`);
  const count = (v, sel) => pic(v)?.querySelectorAll(sel).length;
  const stub = (d) => (d.match(/M[^M]*/g) || []).some((sub) => {
    const n = (sub.match(/-?[\d.]+/g) || []).map(Number);
    return n.length === 4 && Math.hypot(n[2] - n[0], n[3] - n[1]) < 0.01;
  });
  const stubs = pics().some((p) => [...p.querySelectorAll("path")].some((x) => stub(x.getAttribute("d") || "")));
  check(count("sysDot", "circle") === 10 && !count("sysDot", "path") && count("dot", "circle") === 6
    && count("lgDashDotDot", "circle") === 2 && count("lgDashDotDot", "path") === 1 && count("dash", "circle") === 0
    && !stubs && !pics().some((p) => p.innerHTML.includes("dasharray")),
  "its dots are filled circles, even for a line with PowerPoint's spacing, so the Mac app draws every one",
  ["sysDot", "dot", "lgDashDotDot", "dash"].map((v) => `${v}: ${count(v, "circle")} dots, ${count(v, "path")} paths`).join("; "));
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  store.select([]);
}

// Position and size above the properties panel's tabs, whatever tab is open: the numbers follow
// a drag as it happens, and typed ones move and resize; a group's width scales everything in it,
// keeping its proportions. Lines have none
async function sizeStripChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  store.update("Objects", (doc) => {
    doc.pages[store.pageIndex].items.push(gRectFor("sR", 40, 40, 100, 50),
      { id: "sG", type: "group", items: [gRectFor("sG1", 200, 40, 40, 20), gRectFor("sG2", 260, 80, 40, 40)] },
      { id: "sLn", type: "line", points: [[40, 200], [200, 260]], arrow_start: null, arrow_end: null,
        stroke: { color: "#000000", width: 1, dash: "solid", cap: "flat", join: "miter", opacity: 1 } });
  }, { select: [] });
  await settle();
  const u = app.prefs.units || "cm", shown = (pt) => Number(toUnit(pt, u).toFixed(3));
  const field = (key) => document.querySelector(`#inspector .insp-strip [data-bind="${key}"]`);
  const type = async (key, pt) => {
    const f = field(key);
    f.value = String(toUnit(pt, u));
    f.dispatchEvent(new Event("change"));
    await settle();
    inspector.render();
  };
  store.select(["sR"]);
  await settle();
  inspector.render();
  document.getElementById("itab-style")?.click();
  const w = field("w"), r = w?.getBoundingClientRect();
  check(w && r.height > 0 && near(Number(w.value), shown(100), 0.01) && near(Number(field("h").value), shown(50), 0.01)
    && document.querySelectorAll('#inspector [data-bind="w"]').length === 1,
    "a shape's X, Y, width and height show above the tabs with its Style tab open (and only there)", `${w?.value} ${r?.height}`);
  // While a handle is dragged, the numbers follow
  store.beginLive();
  store.item("sR").frame[2] = 160;
  store.live();
  const during = field("w").value;
  store.cancelLive();
  await settle();
  inspector.render();
  check(near(Number(during), shown(160), 0.01), "the width follows a drag as it happens", during);
  await type("w", 120);
  await type("y", 60);
  const fr = store.item("sR").frame;
  check(near(fr[2], 120, 0.01) && near(fr[3], 50, 0.01) && near(fr[1], 60, 0.01) && near(fr[0], 40, 0.01),
    "a width typed in resizes it (a shape's height stays), a Y moves it", JSON.stringify(fr));
  // A group: its outline's numbers; a width scales it all from the top-left, keeping proportions
  store.select(["sG"]);
  await settle();
  inspector.render();
  const gw = field("w");
  check(gw && near(Number(gw.value), shown(100), 0.01) && near(Number(field("h").value), shown(80), 0.01)
    && near(Number(field("x").value), shown(200), 0.01), "a group shows its outline's position and size", gw?.value);
  await type("w", 150);
  const [a, b] = store.item("sG").items.map((it) => it.frame);
  check(near(a[0], 200, 0.01) && near(a[1], 40, 0.01) && near(a[2], 60, 0.01) && near(b[0], 290, 0.01) && near(b[1], 100, 0.01)
    && near(b[2], 60, 0.01) && near(b[3], 60, 0.01) && near(Number(field("h").value), shown(120), 0.01),
    "a group's width typed in scales everything in it from its top-left corner, keeping its proportions",
    `${JSON.stringify(a)} ${JSON.stringify(b)}`);
  await type("x", 210);
  check(near(store.item("sG").items[0].frame[0], 210, 0.01) && near(store.item("sG").items[1].frame[0], 300, 0.01),
    "a group's X moves it", JSON.stringify(store.item("sG").items.map((it) => it.frame[0])));
  store.select(["sLn"]);
  await settle();
  inspector.render();
  check(!field("x") && !field("w") && field("angle"), "a line's strip has its angle, no position or size (its points are in the Arrange tab)");
  store.select([]);
}

// Typing in a duplicated text box, then double-clicking in it to highlight words: what's typed
// stays (the canvas's double-click started typing in the box again, from its text before)
async function dupTypeChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  store.update("Text", (doc) => doc.pages[store.pageIndex].items.push({ id: "dT", type: "shape", geom: "rect", textbox: true,
    frame: [60, 60, 160, 24], rot: 0, flip_h: false, flip_v: false, stroke: null, fill: null, text: { paragraphs: [{ align: "l",
      runs: [{ t: "Hello", font: "Helvetica", size: 12, kern: true }] }], insets: [7.2, 3.6, 7.2, 3.6], wrap: true, anchor: "t",
      autofit: "shape" } }), { select: ["dT"] });
  await settle();
  app.duplicate();
  await settle();
  const copy = store.selection[0];
  canvas.startEdit(copy);
  await settle();
  document.execCommand("selectAll");
  document.execCommand("insertText", false, "World");
  await settle();
  const typed = canvas.editor.textContent;
  // (a double-click on a word, then a third click: the browser highlights it, and the line)
  const r = canvas.editor.firstChild.getBoundingClientRect(), at = { bubbles: true, clientX: r.left + 8, clientY: (r.top + r.bottom) / 2 };
  const target = canvas.editor.querySelector("span") || canvas.editor.firstChild;
  for (const detail of [1, 2]) {
    target.dispatchEvent(new PointerEvent("pointerdown", { ...at, detail, pointerId: 1, button: 0, buttons: 1 }));
    target.dispatchEvent(new PointerEvent("pointerup", { ...at, detail, pointerId: 1, button: 0 }));
  }
  target.dispatchEvent(new MouseEvent("dblclick", { ...at, detail: 2 }));
  document.execCommand("selectAll");
  await settle();
  const after = canvas.editor.textContent;
  check(typed === "World" && after === "World" && canvas.editing?.id === copy,
    "typing in a duplicated text box, then double-clicking in it to highlight, keeps what was typed", `${typed} → ${after}`);
  canvas.commitEdit();
  await settle();
  check(store.item(copy).text.paragraphs[0].runs.map((r) => r.t).join("") === "World" &&
    store.item("dT").text.paragraphs[0].runs.map((r) => r.t).join("") === "Hello", "and the copy keeps it, the original its own");
  store.select([]);
}

// Typing in a shape: the text being typed sits where it will be drawn, in the middle of the shape
// for text in the middle (a new shape's text too), at the top or bottom for text there; text
// taller than its shape spills out both ways from the middle, as it's drawn
async function editAnchorChecks() {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const para = (s) => ({ align: "ctr", runs: [{ t: s, font: "Helvetica", size: 12, kern: true }] });
  const boxed = (id, y, hgt, anchor, lines = ["Middle"]) => ({ ...gRectFor(id, 100, y, 160, hgt), text: {
    paragraphs: lines.map(para), insets: [7.2, 3.6, 7.2, 3.6], wrap: true, anchor, autofit: "none" } });
  store.update("Shapes", (doc) => doc.pages[store.pageIndex].items.push(boxed("eC", 60, 80, "ctr"), boxed("eT", 160, 80, "t"),
    boxed("eB", 260, 80, "b"), boxed("eO", 400, 20, "ctr", ["One", "Two", "Three"]), gRectFor("eN", 100, 460, 160, 80)), { select: [] });
  await settle();
  const k = canvas.k;
  const frameAt = (id) => {
    const f = store.item(id).frame, a = screenOf(f[0], f[1]), b = screenOf(f[0] + f[2], f[1] + f[3]);
    return { top: a[1], bottom: b[1], mid: (a[1] + b[1]) / 2 };
  };
  const typed = () => {
    const divs = [...canvas.editor.children], top = divs[0].getBoundingClientRect().top, bottom = divs.at(-1).getBoundingClientRect().bottom;
    return { top, bottom, mid: (top + bottom) / 2 };
  };
  const editing = async (id, fn) => {
    store.select([id]);
    canvas.startEdit(id);
    await settle();
    const out = fn();
    canvas.commitEdit();
    await settle();
    return out;
  };
  // (the drawn words, before typing starts)
  const drawn = [...(canvas.els.get("eC")?.g.querySelectorAll("text") || [])].map((x) => x.getBoundingClientRect());
  const drawnMid = drawn.length ? (Math.min(...drawn.map((r) => r.top)) + Math.max(...drawn.map((r) => r.bottom))) / 2 : NaN;
  const [c, f] = await editing("eC", () => [typed(), frameAt("eC")]);
  check(near(c.mid, f.mid, 1), "typing in a shape whose text is in the middle, the text sits in its middle",
    `${c.mid} vs ${f.mid}`);
  check(near(c.mid, drawnMid, 2), "where it's drawn once typing stops", `${c.mid} vs drawn ${drawnMid}`);
  const [tt, ft] = await editing("eT", () => [typed(), frameAt("eT")]);
  check(near(tt.top, ft.top + 3.6 * k, 1), "text at the top is typed at the top", `${tt.top} vs ${ft.top + 3.6 * k}`);
  const [tb, fb] = await editing("eB", () => [typed(), frameAt("eB")]);
  check(near(tb.bottom, fb.bottom - (3.6 + 9 / 128) * k, 1), "text at the bottom is typed at the bottom",
    `${tb.bottom} vs ${fb.bottom - 3.6 * k}`);
  const [to, fo] = await editing("eO", () => [typed(), frameAt("eO")]);
  check(to.bottom - to.top > fo.bottom - fo.top && near(to.mid, fo.mid, 1) && to.top < fo.top,
    "text taller than its shape spills out both ways from the middle while typing, as it's drawn", `${JSON.stringify(to)} vs ${JSON.stringify(fo)}`);
  const [tn, fn] = await editing("eN", () => [typed(), frameAt("eN")]);
  check(near(tn.mid, fn.mid, 1), "typing into a shape with no text yet starts in its middle", `${tn.mid} vs ${fn.mid}`);
  // Clicking off finishes it and the editor goes (it lays out middle text, and must still hide)
  store.select(["eC"]);
  canvas.startEdit("eC");
  await settle();
  const shownWhileTyping = getComputedStyle(canvas.editor).display !== "none";
  pointer("pointerdown", screenOf(400, 700));
  pointer("pointerup", screenOf(400, 700));
  await settle();
  check(shownWhileTyping && !canvas.editing && getComputedStyle(canvas.editor).display === "none"
    && canvas.els.get("eC")?.g.style.visibility !== "hidden",
    "clicking off a shape being typed in finishes it, and the editor goes away", getComputedStyle(canvas.editor).display);
  store.select([]);
}

// Turning: the rotation handle pulls onto 0°, 45°, 90°… within 4° (not with ⌘, Shift's 15° steps
// or the Snap button off), with the angle beside the pointer; Rotation typed in the strip above
// the tabs, for a shape (with its flips), a group as a whole, a line (its Angle) and several
// objects together
async function angleChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const ln = (id, points, more = {}) => ({ id, type: "line", points, arrow_start: null, arrow_end: null,
    stroke: { color: "#000000", width: 1, dash: "solid", cap: "flat", join: "miter", opacity: 1 }, ...more });
  store.update("Objects", (doc) => {
    doc.pages[store.pageIndex].items.push(gRectFor("aR", 120, 120, 100, 50),
      { id: "aG", type: "group", items: [gRectFor("aG1", 300, 100, 40, 20), gRectFor("aG2", 360, 140, 40, 40)] },
      gRectFor("aT", 20, 280, 40, 40), ln("aLn", [[60, 300], [160, 300]]),
      ln("aEl", [[300, 300], [360, 300], [360, 360], [420, 360]], { route: "elbow" }),
      gRectFor("aM1", 300, 500, 40, 20), gRectFor("aM2", 380, 500, 40, 20));
  }, { select: [] });
  await settle();
  // (the line's start on the square's right side's middle, once the engine has given its points)
  store.update("Attach", (doc) => { findItem(doc, "aLn").start_link = { item: "aT", site: "m1" }; });
  await settle();
  // The handle dragged round to `deg` (what the frame's top would point to), letting go or not
  const turnTo = async (deg, opts = {}, letGo = true) => {
    store.select(["aR"]);
    await settle();
    const it = store.item("aR"), hd = canvas.handlesFor(it).find((x) => x.kind === "rotate");
    const sr = canvas.stage.getBoundingClientRect(), [x, y, w, h] = it.frame;
    const a = ((deg - 90) * Math.PI) / 180, r = 80;
    pointer("pointerdown", [hd.at[0] + sr.left, hd.at[1] + sr.top]);
    for (const k of [0.5, 1]) {
      const d = ((deg * k - 90) * Math.PI) / 180;
      pointer("pointermove", screenOf(x + w / 2 + Math.cos(k === 1 ? a : d) * r, y + h / 2 + Math.sin(k === 1 ? a : d) * r), opts);
    }
    if (letGo) {
      pointer("pointerup", screenOf(x + w / 2 + Math.cos(a) * r, y + h / 2 + Math.sin(a) * r), opts);
      await settle();
    }
    return store.item("aR").rot;
  };
  const unturn = () => store.update("Unturn", (doc) => { findItem(doc, "aR").rot = 0; });
  let rot = await turnTo(47, {}, false);
  const label = canvas.overlay.querySelector(".guide-label")?.textContent, guide = !!canvas.overlay.querySelector(".snap-guide");
  pointer("pointerup", screenOf(0, 0));
  await settle();
  check(near(rot, 45, 1e-9) && label === "45°" && guide,
    "turning by the handle pulls onto 45° from 2° off, with the angle beside the pointer and a guide", `${rot} ${label} ${guide}`);
  unturn();
  rot = await turnTo(52);
  check(near(rot, 52, 0.01), "and turns freely more than 4° from one", `${rot}`);
  unturn();
  rot = await turnTo(-3);
  check(near(rot, 0, 1e-9), "it pulls onto 0° from either side", `${rot}`);
  unturn();
  rot = await turnTo(93);
  check(near(rot, 90, 1e-9), "and onto 90°", `${rot}`);
  unturn();
  rot = await turnTo(47, { metaKey: true, ctrlKey: true });
  check(near(rot, 47, 0.01), "holding ⌘ turns it freely for that drag", `${rot}`);
  unturn();
  rot = await turnTo(58, { shiftKey: true });
  check(near(rot, 60, 1e-9), "Shift still keeps to 15° steps", `${rot}`);
  unturn();
  await app.run("toggleSnap");
  rot = await turnTo(47);
  await app.run("toggleSnap");
  check(near(rot, 47, 0.01) && app.prefs.snap, "with the Snap button off it turns freely", `${rot}`);
  unturn();
  store.select(["aR"]);
  await turnTo(47, {}, false);
  key("Escape");
  await settle();
  check(near(store.item("aR").rot || 0, 0, 1e-9) && !canvas.overlay.querySelector(".guide-label"),
    "Escape puts it back and the angle goes", `${store.item("aR").rot}`);
  if (canvas.op) { pointer("pointerup", screenOf(0, 0)); await settle(); }

  // Typed in the strip above the tabs, whatever tab is open
  const field = (key) => document.querySelector(`#inspector .insp-strip [data-bind="${key}"]`);
  const typeIn = async (input, v) => {
    input.value = String(v);
    input.dispatchEvent(new Event("change"));
    await settle();
    inspector.render();
  };
  store.select(["aR"]);
  await settle();
  inspector.render();
  document.getElementById("itab-style")?.click();
  const rf = field("rot");
  check(rf && rf.getBoundingClientRect().height > 0 && document.querySelectorAll('#inspector [data-bind="rot"]').length === 1
    && document.querySelector('#inspector .insp-strip [aria-label^="Flip horizontally"]'),
    "a shape's Rotation and flips show above the tabs with its Style tab open (and only there)");
  await typeIn(rf, 30);
  check(near(store.item("aR").rot, 30, 1e-9), "a typed Rotation turns it", `${store.item("aR").rot}`);
  store.beginLive();
  store.item("aR").rot = 75;
  store.live();
  const during = field("rot").value;
  store.cancelLive();
  await settle();
  check(during === "75", "the Rotation follows a drag as it happens", during);

  // A group remembers its angle and turns as a whole about its middle
  store.select(["aG"]);
  await settle();
  inspector.render();
  const gf = field("rot");
  check(gf && gf.value === "0", "a group shows a Rotation of 0 to start with", gf?.value);
  const gb = itemsBBox(store.item("aG").items), gc = [(gb[0] + gb[2]) / 2, (gb[1] + gb[3]) / 2];
  await typeIn(gf, 90);
  const [g1, g2] = store.item("aG").items, mid1 = [g1.frame[0] + 20, g1.frame[1] + 10];
  check(near(store.item("aG").rot, 90, 1e-9) && near(g1.rot, 90, 1e-9) && near(g2.rot, 90, 1e-9)
    && near(mid1[0], gc[0] - (110 - gc[1]), 1e-6) && near(mid1[1], gc[1] + (320 - gc[0]), 1e-6) && field("rot").value === "90",
    "a typed Rotation turns a group as a whole about its middle, and it shows the new angle",
    `${store.item("aG").rot} ${JSON.stringify(mid1)} vs ${gc}`);
  await app.run("transformAgain");
  check(near(store.item("aG").rot, 180, 1e-9) && near(store.item("aG").items[0].rot, 180, 1e-9),
    "Transform Again turns it on by as much and its angle keeps count", `${store.item("aG").rot}`);
  store.undo();
  await settle();
  check(near(store.item("aG").rot, 90, 1e-9), "one undo step takes the turn back", `${store.item("aG").rot}`);

  // A line's Angle: start to end, clockwise from pointing right; typed, it turns about its middle
  store.select(["aLn"]);
  await settle();
  inspector.render();
  const lf = field("angle");
  const lineNow = () => store.item("aLn").points;
  check(lf && lf.value === "0" && store.item("aLn").start_link, "a line's Angle shows the way from its start to its end", lf?.value);
  const lmid = [(lineNow()[0][0] + lineNow()[1][0]) / 2, (lineNow()[0][1] + lineNow()[1][1]) / 2];
  await typeIn(lf, 90);
  const lp = lineNow();
  check(near(lp[0][0], lmid[0], 1e-9) && near(lp[1][0], lmid[0], 1e-9) && near(lp[1][1] - lp[0][1], 100, 1e-9)
    && near((lp[0][1] + lp[1][1]) / 2, lmid[1], 1e-9) && field("angle").value === "90",
    "a typed Angle of 90 turns the line about its middle to point straight down", JSON.stringify(lp));
  check(!store.item("aLn").start_link, "and its end attached to a shape that didn't turn lets go", JSON.stringify(store.item("aLn").start_link));
  await typeIn(field("angle"), 45);
  const lq = lineNow();
  check(near(Math.atan2(lq[1][1] - lq[0][1], lq[1][0] - lq[0][0]) * 180 / Math.PI, 45, 1e-6), "and 45 points it down and right",
    JSON.stringify(lq));
  store.select(["aEl"]);
  await settle();
  inspector.render();
  check(!field("angle"), "an elbow connector has no Angle (its stretches stay level and upright)");

  // Several objects: their shared angle, turning together; blank when they differ
  store.select(["aM1", "aM2"]);
  await settle();
  inspector.render();
  const mf = () => fieldByLabel("Rotation");
  check(mf() && mf().value === "0" && mf().closest(".insp-strip"), "several objects show the angle they share above the tabs", mf()?.value);
  const mb = itemsBBox([store.item("aM1"), store.item("aM2")]), mc = [(mb[0] + mb[2]) / 2, (mb[1] + mb[3]) / 2];
  await typeIn(mf(), 90);
  const m1 = store.item("aM1"), m1mid = [m1.frame[0] + 20, m1.frame[1] + 10];
  check(near(m1.rot, 90, 1e-9) && near(store.item("aM2").rot, 90, 1e-9) && near(m1mid[0], mc[0] - (510 - mc[1]), 1e-6)
    && near(m1mid[1], mc[1] + (320 - mc[0]), 1e-6) && mf().value === "90",
    "a typed Rotation turns them together about their middle", `${m1.rot} ${JSON.stringify(m1mid)} vs ${mc}`);
  store.update("Turn one", (doc) => { findItem(doc, "aM2").rot = 120; });
  await settle();
  inspector.render();
  check(mf().value === "" && mf().placeholder === "Mixed" && /different angles/.test(document.querySelector("#inspector .insp-strip").textContent),
    "at different angles it's blank (Mixed) and says what typing does", mf().value);
  await typeIn(mf(), 10);
  check(near(store.item("aM1").rot, 100, 1e-9) && near(store.item("aM2").rot, 130, 1e-9),
    "and a typed angle turns them all by that much", `${store.item("aM1").rot} ${store.item("aM2").rot}`);
  store.update("Lock one", (doc) => { findItem(doc, "aM2").locked = true; });
  store.select(["aM1", "aM2"]);
  await settle();
  inspector.render();
  await typeIn(mf(), 0);
  check(near(store.item("aM1").rot, 0, 1e-9) && near(store.item("aM2").rot, 130, 1e-9), "a locked one stays put",
    `${store.item("aM1").rot} ${store.item("aM2").rot}`);
  store.select([]);
}

// Selecting several objects shows the Arrange tab, and the tab before comes back once one or
// none is selected (a tab picked meanwhile stays). Text boxes count too; one text box shows Home.
// The group Group makes keeps Arrange showing; Settings turns it off
async function arrangeTabChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const textBox = (id, y) => ({ id, type: "shape", geom: "rect", textbox: true, frame: [40, y, 160, 24], rot: 0, flip_h: false,
    flip_v: false, stroke: null, fill: null, text: { paragraphs: [{ align: "l", runs: [{ t: id, font: "Helvetica", size: 6,
      bold: false, italic: false, color: "#000000" }] }], insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" } });
  store.update("Objects", (doc) => {
    doc.pages[store.pageIndex].items.push(gRectFor("aA", 40, 120, 60, 40), gRectFor("aB", 140, 120, 60, 40),
      textBox("aT", 40), textBox("aU", 80));
  }, { select: [] });
  await settle();
  const showing = () => panels.ribbonTab;
  const pickTab = (key) => document.getElementById(`rtab-${key}`).click();
  const stageTops = Object.keys(panels.ribbonTabs).map((k) => { pickTab(k); return [k, canvas.stage.getBoundingClientRect().top]; });
  check(stageTops.every(([, top]) => top === stageTops[0][1]), "every ribbon tab is as tall, so the page doesn't jump as the tab changes",
    stageTops.map(([k, top]) => `${k} ${top}`).join(", "));

  pickTab("view");
  store.select(["aA"]);
  const one = showing();
  store.select(["aA", "aB"]);
  const two = showing();
  store.select(["aA", "aB", "aT"]);
  const three = showing();
  store.select(["aA"]);
  const back = showing();
  check(one === "view" && two === "arrange" && three === "arrange" && back === "view",
    "one object leaves the tab alone; two show Arrange, and back to one brings the tab before back", `${one}, ${two}, ${three}, ${back}`);
  store.select(["aT"]);
  const text = showing();
  store.select(["aT", "aU"]);
  const texts = showing();
  store.select(["aU"]);
  const oneText = showing();
  store.select([]);
  check(text === "home" && texts === "arrange" && oneText === "home" && showing() === "view",
    "one text box shows Home, two text boxes Arrange, one again Home; none brings the tab before back",
    `${text}, ${texts}, ${oneText}, ${showing()}`);
  store.select(["aA", "aB"]);
  pickTab("figure");
  store.select([]);
  const kept = showing();
  store.select(["aA", "aB"]);
  check(kept === "figure" && showing() === "arrange", "a tab picked while several are selected stays; several selected later show Arrange again",
    `${kept}, then ${showing()}`);
  await app.run("group");
  await settle();
  const grouped = store.selected().length === 1 && store.selected()[0].type === "group" && showing() === "arrange";
  store.select([]);
  const after = showing();
  store.select([store.page().items.find((it) => it.type === "group").id]);
  check(grouped && after === "figure" && showing() === "figure",
    "Group keeps Arrange showing for the group it makes; a group selected by itself leaves the tab alone", `${after}, ${showing()}`);
  store.select([]);
  await app.savePrefs({ several_arrange_tab: false });
  store.select(["aT", "aU"]);
  const off = showing();
  store.select([]);
  await app.savePrefs({ several_arrange_tab: true });
  check(off === "home", "with Settings' switch off, several objects leave the tab alone (several text boxes still show Home)", off);
  pickTab("home");
}

// The Home tab's Text section: what the text boxes selected share, changes to all of them, and
// while typing to the highlighted words only (with only the caret, to what's typed next), each an
// undo step that ⌘Z takes back without ending the typing. Selecting text shows the Home tab and
// the tab before comes back; shapes with text and mixed selections don't count
async function textRibbonChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const box = (id, y, paragraphs) => ({ id, type: "shape", geom: "rect", textbox: true, frame: [40, y, 160, 24], rot: 0,
    flip_h: false, flip_v: false, stroke: null, fill: null,
    text: { paragraphs: paragraphs.map((runs) => ({ align: "l", runs: runs.map(([t, more]) => ({ t, font: "Helvetica", size: 6,
      bold: false, italic: false, color: "#000000", ...more })) })), insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" } });
  store.update("Text", (doc) => {
    doc.pages[store.pageIndex].items.push(box("tA", 40, [[["Hello world"]]]), box("tB", 90, [[["Second", { size: 8 }]]]),
      { ...gRectFor("rC", 40, 150, 80, 40), text: { paragraphs: [{ align: "ctr", runs: [{ t: "Shape", font: "Helvetica", size: 6 }] }],
        insets: [4, 4, 4, 4], wrap: true, anchor: "ctr" } },
      box("tD", 220, [[["Hello world"]], [["Line two"]]]));
    doc.swatches = [{ id: "swRed", name: "Vermilion", color: "#d55e00" }];
    doc.text_styles = [{ id: "tsAxis", name: "Axis", font: "Arial", size: 5 }];
  }, { select: [] });
  await settle();
  const mod = isMac ? { metaKey: true } : { ctrlKey: true };
  const group = document.querySelector("#rpanel-home .text-group"), btn = (cmd) => group?.querySelector(`[data-cmd="${cmd}"]`);
  const font = group?.querySelector(".text-font"), size = group?.querySelector(".text-size"), style = group?.querySelector(".text-style");
  const runs = (id) => store.item(id).text.paragraphs.flatMap((p) => p.runs);
  const pressed = (cmd) => btn(cmd).getAttribute("aria-pressed") === "true";
  const pick = async (cmd, label) => {
    btn(cmd).click();
    [...document.querySelectorAll(".context-menu .menu-item")].find((b) => b.textContent.includes(label))?.click();
    await settle();
  };
  // A field typed into and Enter pressed, as a person would
  const typeIn = async (field, value) => {
    field.focus();
    field.value = value;
    field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await settle();
  };
  const showing = () => panels.ribbonTab;
  const pickTab = (key) => document.getElementById(`rtab-${key}`).click();

  store.select([]);
  check(group && btn("textBold").disabled && font.disabled && size.disabled && style.disabled,
    "the Home tab has a Text section, greyed out with no text selected");
  pickTab("arrange");
  store.select(["tA"]);
  const switched = showing();
  store.select([]);
  check(switched === "home" && showing() === "arrange", "selecting a text box shows the Home tab; deselecting it brings back the tab before",
    `${switched}, then ${showing()}`);
  store.select(["tA"]);
  pickTab("view");
  store.select([]);
  const kept = showing();
  store.select(["tA"]);
  check(kept === "view" && showing() === "home", "a tab picked while text is selected stays; text selected later shows Home again",
    `${kept}, then ${showing()}`);
  store.select([]);
  pickTab("arrange");
  store.select(["rC"]);
  const shapeTab = showing(), shapeOff = btn("textBold").disabled;
  store.select(["tA", "rC"]);
  check(shapeTab === "arrange" && shapeOff && showing() === "arrange" && btn("textBold").disabled,
    "a shape with text, or a text box selected with something else, isn't text for it: the tab stays and the section is greyed out");
  store.select([]);
  await app.savePrefs({ text_home_tab: false });
  store.select(["tA"]);
  const off = showing();
  store.select([]);
  await app.savePrefs({ text_home_tab: true });
  check(off === "arrange", "with Settings' switch off, selecting text leaves the tab alone", off);

  // Several boxes at once
  store.select(["tA", "tB"]);
  await settle();
  check(font.value === "Helvetica" && size.value === "" && !btn("textBold").disabled,
    "with two boxes selected it shows what they share: their font, and no size (they differ)", `${font.value} | ${size.value}`);
  const steps = store.history.length;
  await typeIn(size, "7");
  check(runs("tA").every((r) => r.size === 7) && runs("tB").every((r) => r.size === 7) && size.value === "7"
    && store.history.length === steps + 1, "a size typed in changes every box selected, as one undo step", JSON.stringify(runs("tB")));
  await app.run("textBigger");
  const bigger = runs("tA")[0].size;
  key("<", { ...mod, shiftKey: true });
  await settle();
  check(bigger === 7.5 && runs("tB")[0].size === 7, `Bigger text steps to the next size (7 → 7.5); ${isMac ? "⌘⇧<" : "Ctrl+Shift+<"} steps back`,
    `${bigger}, ${runs("tB")[0].size}`);
  btn("textBold").click();
  await settle();
  const allBold = [...runs("tA"), ...runs("tB")].every((r) => r.bold) && pressed("textBold");
  key("b", mod);
  await settle();
  check(allBold && [...runs("tA"), ...runs("tB")].every((r) => !r.bold) && !pressed("textBold"),
    `Bold puts it on for all of them, and ${isMac ? "⌘B" : "Ctrl+B"} takes it off again`);
  btn("textCentre").click();
  btn("textBottom").click();
  await settle();
  const texts = [store.item("tA").text, store.item("tB").text];
  check(texts.every((x) => x.paragraphs.every((p) => p.align === "ctr") && x.anchor === "b") && pressed("textCentre") && pressed("textBottom"),
    "centring and bottom place every box's text, the buttons showing it");
  await pick("lineSpacing", "1.5");
  check(texts.length && [store.item("tA"), store.item("tB")].every((it) => it.text.paragraphs.every((p) => p.line_spacing?.pct === 1.5)),
    "Line spacing 1.5 from its menu", JSON.stringify(store.item("tA").text.paragraphs[0].line_spacing));
  await pick("textColour", "Vermilion");
  check([...runs("tA"), ...runs("tB")].every((r) => r.color === "#d55e00" && r.swatch === "swRed")
    && group.querySelector(".colour-bar").style.background !== "", "a swatch from the colour menu colours the text, linked to it");
  style.value = "tsAxis";
  style.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  const styled = [store.item("tA"), store.item("tB")].every((it) => it.text.paragraphs.every((p) => p.style === "tsAxis"))
    && runs("tA").every((r) => r.font === "Arial" && r.size === 5);
  await app.undo();
  await settle();
  check(styled && runs("tA").every((r) => r.font === "Helvetica" && r.size === 7) && style.value !== "tsAxis",
    "a text style from the list, and one undo takes it back");

  // Typing: only the words highlighted
  store.select(["tD"]);
  canvas.startEdit("tD");
  await settle();
  const textNode = (s) => [...canvas.editor.querySelectorAll("span")].map((sp) => sp.firstChild).find((n) => n?.textContent.includes(s));
  const highlight = async (s, from, to) => {
    const n = textNode(s), sel = window.getSelection();
    sel.setBaseAndExtent(n, from, n, to);
    await settle();
  };
  await highlight("Hello world", 6, 11);
  const before = store.history.length;
  await typeIn(size, "9");
  const live = !!canvas.editing && window.getSelection().toString() === "world";
  const undoKey = (shift = false) => canvas.editor.dispatchEvent(new KeyboardEvent("keydown", { key: "z", ...mod, shiftKey: shift,
    bubbles: true, cancelable: true }));
  check(live && canvas.editorModel()[0].runs.map((r) => `${r.t}:${r.size}`).join() === "Hello :6,world:9"
    && store.history.length === before + 1, "while typing, a size changes only the highlighted word, which stays highlighted",
  JSON.stringify(canvas.editorModel()[0].runs.map((r) => [r.t, r.size])));
  undoKey();
  await settle();
  const undone = canvas.editorModel()[0].runs.map((r) => `${r.t}:${r.size}`).join();
  undoKey(true);
  await settle();
  check(!!canvas.editing && undone === "Hello world:6" && canvas.editorModel()[0].runs.map((r) => r.size).join() === "6,9",
    `${isMac ? "⌘Z" : "Ctrl+Z"} right after it takes just that back and typing carries on; ${isMac ? "⌘⇧Z" : "Ctrl+Shift+Z"} puts it back`, undone);
  await highlight("Hello", 0, 5);
  canvas.editor.dispatchEvent(new KeyboardEvent("keydown", { key: ">", ...mod, shiftKey: true, bubbles: true, cancelable: true }));
  await settle();
  btn("textBold").click();
  await settle();
  const hello = canvas.editorModel()[0].runs[0];
  check(hello.t === "Hello" && hello.size === 6.5 && hello.bold && pressed("textBold"),
    `${isMac ? "⌘⇧>" : "Ctrl+Shift+>"} and Bold work on the highlighted word while typing`, JSON.stringify(hello));
  // Only the caret, at the end: the colour goes to what's typed next
  const tail = textNode("world");
  window.getSelection().collapse(tail, tail.textContent.length);
  await settle();
  await pick("textColour", "Vermilion");
  const barShows = group.querySelector(".colour-bar").style.background !== "";
  document.execCommand("insertText", false, "!");
  await settle();
  const typed = canvas.editorModel()[0].runs;
  check(barShows && typed.at(-1).t === "!" && typed.at(-1).color === "#d55e00" && typed.find((r) => r.t.includes("world"))?.color === "#000000",
    "with only the caret, the colour goes to what's typed next, and the section shows it", JSON.stringify(typed.map((r) => [r.t, r.color])));
  // Alignment while typing: the lines the words are in
  await highlight("Line two", 0, 4);
  btn("textRight").click();
  await settle();
  const aligned = canvas.editorModel().map((p) => p.align).join();
  // The properties panel while typing: through the text being typed, so it stays when typing ends
  inspector.render();
  [...document.querySelectorAll("#inspector button")].find((b) => b.getAttribute("aria-label") === "Italic")?.click();
  await settle();
  canvas.commitEdit();
  await settle();
  const ps = store.item("tD").text.paragraphs;
  check(aligned === "l,r" && ps.map((p) => p.align).join() === "l,r" && ps.flatMap((p) => p.runs).every((r) => r.italic)
    && ps[0].runs.map((r) => r.t).join("") === "Hello world!" && ps[0].runs[0].bold,
  "alignment while typing goes to the line the words are in; the properties panel's Italic, all of it; all kept when typing ends",
  JSON.stringify(ps.map((p) => [p.align, p.runs.map((r) => [r.t, r.size, r.bold, r.italic, r.color])])));
  store.select([]);
  pickTab("home");
}

// Panel labels follow the page's journal: choosing one restyles the labels already there (the
// Label tool's and lone letters, not other text) in one undo step; switching journals again keeps
// what was changed by hand; new labels take the journal's look and its way of writing letters
async function journalLabelChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  // Two journals whose labels look different (journals.py), in case first
  const js = (app.info.journals || []).filter((j) => j.labels);
  const look = (j) => JSON.stringify(j.labels);
  const j1 = js.find((j) => j.labels.case === "lower") || js[0];
  const j2 = js.find((j) => j.labels.case !== j1.labels.case) || js.find((j) => look(j) !== look(j1));
  check(j1 && j2, "two journals with different panel labels to test with", js.map((j) => `${j.name} ${look(j)}`).join("; "));
  if (!j1 || !j2) return;
  const box = (id, t, y, extra = {}) => ({ id, type: "shape", geom: "rect", textbox: true, frame: [40, y, 20, 12], rot: 0,
    flip_h: false, flip_v: false, stroke: null, fill: null, text: { paragraphs: [{ align: "l", runs: [{ t, font: "Times New Roman",
      size: 11, bold: false, italic: false, color: "#000000" }] }], insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" }, ...extra });
  store.update("Labels", (doc) => doc.pages[0].items.push(box("lA", "a", 40), box("lB", "(B)", 80), box("lC", "c", 120, { panel_label: true }),
    box("tX", "Axis", 160)), { select: [] });
  await settle();
  const runOf = (id) => store.item(id).text.paragraphs[0].runs[0];
  const textOf = (id) => store.item(id).text.paragraphs.map((p) => p.runs.map((r) => r.t).join("")).join("\n");
  const written = (letter, l) => (l.form || "a").replace("a", l.case === "upper" ? letter.toUpperCase() : letter.toLowerCase());
  const styled = (id, l) => { const r = runOf(id); return r.font === l.font && r.size === l.size && !!r.bold === !!l.bold; };
  const steps = store.history.length;
  inspector.setJournalSize(j1.name);
  await settle();
  check(["lA", "lB", "lC"].every((id) => styled(id, j1.labels)) && textOf("lA") === written("a", j1.labels)
    && textOf("lB") === written("b", j1.labels) && runOf("tX").font === "Times New Roman" && runOf("tX").size === 11
    && store.history.length === steps + 1, `choosing ${j1.name} gives the page's panel labels its look, as one undo step; other text stays`,
  ["lA", "lB", "lC", "tX"].map((id) => `${textOf(id)} ${JSON.stringify(runOf(id))}`).join(" | "));
  store.update("Bigger", (doc) => { doc.pages[0].items.find((i) => i.id === "lA").text.paragraphs[0].runs[0].size = 13; });
  inspector.setJournalSize(j2.name);
  await settle();
  const kept = runOf("lA").size === 13 && runOf("lA").font === j2.labels.font && textOf("lA") === written("a", j2.labels);
  check(kept && styled("lB", j2.labels) && textOf("lC") === written("c", j2.labels),
    `switching to ${j2.name} restyles them again, a size changed by hand staying`, `${textOf("lA")} ${JSON.stringify(runOf("lA"))}`);
  // A new label takes the journal's look and the next letter, written its way
  canvas.setTool("label");
  const at = screenOf(200, 60);
  pointer("pointerdown", at);
  pointer("pointerup", at, { buttons: 0 });
  await settle();
  const made = store.selected()[0];
  check(made?.panel_label && styled(made.id, j2.labels) && textOf(made.id) === written("d", j2.labels),
    `the Label tool's next label is ${written("d", j2.labels)}, in ${j2.name}'s look`, made && `${textOf(made.id)} ${JSON.stringify(runOf(made.id))}`);
  const flagged = (await rpc("preflight", store.doc, { pages: [0] })).items.map((f) => f.message);
  check(flagged.some((m) => m.includes(`“${written("a", j2.labels)}” isn't in ${j2.name}'s style`))
    && !flagged.some((m) => m.includes(`“${written("d", j2.labels)}” isn't`)), "Check says which panel labels aren't in the journal's style",
  flagged.join(" | "));
}

// Journal checks: a placed PNG's kind (guessed from its pixels, or set on its Picture tab) decides
// the resolution its page's journal asks for, the journal's thinnest line replaces mosaic's
// 0.25 pt, and the Export window says what the journal takes and flags settings it doesn't
async function journalCheckChecks(app) {
  const js = (app.info.journals || []).filter((j) => j.pictures?.line_art > 300 && j.lines?.min_pt > 0.25 && j.export);
  const j = js.find((x) => !x.export.formats.includes("svg")) || js[0];
  check(j, "a journal with line, resolution and export rules to test with", (app.info.journals || []).map((x) => x.name).join(", "));
  if (!j) return;
  store.setDoc(await rpc("new_document"));
  inspector.setJournalSize(j.name);
  canvas.fit();
  await settle();
  // A plot drawn as a PNG (it records no resolution, so it's read as 300 dpi) and a 0.25 pt rule
  const c = document.createElement("canvas");
  c.width = 600;
  c.height = 300;
  const g = c.getContext("2d");
  g.fillStyle = "#ffffff";
  g.fillRect(0, 0, 600, 300);
  g.lineWidth = 2;
  g.beginPath();
  g.moveTo(40, 10);
  g.lineTo(40, 270);
  g.lineTo(590, 270);
  g.stroke();
  g.fillStyle = "#4682b4";
  [120, 200, 90, 160].forEach((bar, i) => { g.fillRect(70 + i * 120, 270 - bar, 70, bar); g.strokeRect(70 + i * 120, 270 - bar, 70, bar); });
  const up = await rpc("add_upload", "selftest-chart.png", c.toDataURL("image/png").split(",")[1]);
  const [w, hh] = up.asset.size_pt;
  store.update("Chart", (doc) => {
    doc.assets[up.asset_id] = up.asset;
    doc.pages[0].items.push({ id: "jcPic", type: "picture", name: "Chart", asset: up.asset_id, page_index: 0, frame: [20, 20, w, hh],
      crop: [0, 0, 0, 0], rot: 0, flip_h: false, flip_v: false, opacity: 1, source: "auto" },
    { id: "jcLine", type: "line", name: "Rule", points: [[20, 200], [120, 200]], rot: 0, arrow_start: null, arrow_end: null,
      stroke: { color: "#000000", width: 0.25, dash: "solid", cap: "flat", join: "miter", opacity: 1 } });
  }, { select: ["jcPic"] });
  await settle();
  inspector.render();
  const kind = () => {   // (without drawing the panel again, which asks for the guess again)
    const l = [...document.querySelectorAll("#inspector label")].find((x) => x.textContent === "Kind");
    return l && document.getElementById(l.htmlFor);
  };
  await until(() => /looks like/.test(kind()?.selectedOptions[0]?.textContent || ""), 6000);
  check(kind()?.value === "auto" && kind()?.selectedOptions[0]?.textContent === "Automatic (looks like line art)",
    "a placed PNG's Picture tab has a Kind list, its Automatic choice naming the Check's guess", kind()?.selectedOptions[0]?.textContent);
  const flagged = async () => (await rpc("preflight", store.doc, { pages: [0] })).items;
  const dpiOf = (found) => found.find((f) => f.item === "jcPic" && /dpi at its placed size/.test(f.message));
  let found = await flagged();
  let d = dpiOf(found);
  check(d?.level === "warning" && d.message === `Chart: 300 dpi at its placed size; ${j.name} asks for at least ${j.pictures.line_art} dpi `
    + "for line art (kind guessed from the picture; its Picture tab can set it)", `Check holds it to ${j.name}'s resolution for line art`, d?.message);
  const ruled = found.find((f) => f.item === "jcLine");
  check(ruled?.level === (j.lines.about ? "info" : "warning") && ruled.message === `Rule: its line is 0.25 pt; ${j.name} asks for at least `
    + `${j.lines.min_pt} pt`, `and the 0.25 pt rule to ${j.name}'s thinnest line, not mosaic's 0.25 pt`, ruled?.message);
  const steps = store.history.length;
  await choose("Kind", "photo");
  check(store.item("jcPic").picture_kind === "photo" && store.history.length === steps + 1, "choosing Photo sets its kind, as one undo step",
    `${store.item("jcPic").picture_kind} ${store.history.length - steps}`);
  d = dpiOf(await flagged());
  check(d?.level === (300 < j.pictures.photo - 0.5 ? "warning" : "ok") && d.message === `Chart: 300 dpi at its placed size; ${j.name} asks for `
    + `at least ${j.pictures.photo} dpi for a photo`, "Check then holds it to the journal's resolution for photos, as set rather than guessed", d?.message);
  await app.run("undo");
  await settle();
  check(!("picture_kind" in store.item("jcPic")), "undo puts it back to Automatic", JSON.stringify(store.item("jcPic")));
  // The Export window: what the journal takes, then a format it doesn't and too low a resolution
  await app.run("export");
  const dlg = [...document.querySelectorAll("dialog[open]")].pop();
  try {
    await panels.reviewing;
    const flags = () => [...dlg.querySelectorAll(".journal-export li")].map((li) => li.textContent);
    check(flags().some((t) => t.startsWith(`ℹ Note ${j.name} takes `)), "the Export window says what the page's journal takes", flags().join(" | "));
    const names = { pdf: "PDF", svg: "SVG", png: "PNG", tiff: "TIFF", jpeg: "JPEG", eps: "EPS", pptx: "PowerPoint" };
    const refused = ["svg", "pptx", "png", "jpeg", "eps"].find((f) => !j.export.formats.includes(f));
    const raster = ["tiff", "png", "jpeg"].find((f) => j.export.formats.includes(f));
    for (const i of dlg.querySelectorAll(".formats input, .advanced input[value]")) i.checked = [refused, raster].includes(i.value);
    const dpiLabel = [...dlg.querySelectorAll("label")].find((l) => l.textContent === "Resolution for PNG, TIFF and JPEG");
    const dpi = document.getElementById(dpiLabel.htmlFor);
    dpi.value = "300";
    dpi.dispatchEvent(new Event("change", { bubbles: true }));
    await panels.reviewing;
    check(!refused || flags().includes(`⚠ Check ${j.name} doesn't take ${names[refused]} files for final figures`),
      `ticking ${names[refused]} is flagged: ${j.name} doesn't take it`, flags().join(" | "));
    check(!raster || flags().includes(`⚠ Check ${names[raster]} at 300 dpi: ${j.name} asks for at least ${j.pictures.line_art} dpi for line art`),
      `and ${names[raster]} at 300 dpi of a page of line art`, flags().join(" | "));
  } finally { dlg.close(); }
  // The Page panel: what the journal asks for, folded under one line that stays open once opened
  store.select([]);
  inspector.render();
  const folded = () => document.querySelector("#inspector .journal-rules");
  const shut = folded() && !folded().open;
  folded()?.querySelector("summary").click();
  await wait(60);
  inspector.render();
  const said = [...(folded()?.querySelectorAll(".hint") || [])].map((p) => p.textContent);
  check(shut && folded()?.open && folded().querySelector("summary").textContent === `What ${j.name} asks for`
    && said.some((t) => t.startsWith(`Lines ${j.lines.max_pt ? "" : "at least "}${j.lines.min_pt}`))
    && said.some((t) => t.startsWith("Pictures at least 300 dpi for photos")) && said.some((t) => t.startsWith("Files: ")),
  `the Page panel folds what ${j.name} asks for under one line, which stays open once opened`, `${shut} ${said.join(" | ")}`);
}

async function clickThroughChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const line = { color: "#000000", width: 1, dash: "solid", cap: "flat", join: "miter", opacity: 1 };
  const shape = (id, geom, frame, fill, extra = {}) => ({ id, type: "shape", geom, frame, rot: 0, flip_h: false, flip_v: false,
    fill, stroke: line, ...extra });
  const text = { paragraphs: [{ align: "ctr", runs: [{ t: "Label", font: "Helvetica", size: 12, bold: false, italic: false,
    color: "#000000" }] }], insets: [4, 4, 4, 4], wrap: true, anchor: "ctr" };
  store.update("Shapes", (doc) => doc.pages[store.pageIndex].items.push(
    shape("under", "rect", [100, 100, 80, 60], { color: "#56b4e9", opacity: 1 }), shape("box", "rect", [80, 80, 160, 120], null),
    shape("clear", "rect", [300, 100, 100, 80], { color: "#e69f00", opacity: 0 }),
    shape("faint", "rect", [450, 100, 100, 80], { color: "#e69f00", opacity: 0.5 }),
    shape("ring", "ellipse", [100, 300, 120, 80], null), shape("disc", "ellipse", [300, 300, 120, 80], { color: "#009e73", opacity: 1 }),
    shape("labelled", "rect", [450, 300, 120, 80], null, { text })), { select: [] });
  await settle();
  const clickAt = async (x, y) => {
    store.select([]);
    const pt = screenOf(x, y);
    pointer("pointerdown", pt);
    pointer("pointerup", pt, { buttons: 0 });
    await settle();
    return store.selection.join();
  };
  const picks = async (list) => { const got = []; for (const [x, y] of list) got.push(await clickAt(x, y)); return got.join("|"); };
  let got = await picks([[140, 130], [80, 140]]);
  check(got === "under|box", "a click inside an empty box picks the shape under it, and one on its line picks the box", got);
  got = await picks([[350, 140], [500, 140]]);
  check(got === "|faint", "a fully clear fill lets clicks through too; one you can see catches them", got);
  const deg45 = [160 + 60 * Math.SQRT1_2, 340 + 40 * Math.SQRT1_2];   // (on the empty ellipse's curve)
  got = await picks([[103, 303], [160, 340], deg45, [303, 303], [360, 340]]);
  check(got === "||ring||disc", "an ellipse is picked by its curve (and a filled one inside it), not at its frame's corners", got);
  got = await picks([[510, 341], [458, 308]]);
  check(got === "labelled|", "an empty box with text is picked on its text, and clicks elsewhere inside go through", got);
  // Selected, an empty box drags from inside; a click inside picks what's under it
  store.select(["box"]);
  await drag([220, 180], [250, 210]);
  check(store.selection.join() === "box" && store.item("box").frame[0] > 100, "a selected empty box drags from inside it",
    JSON.stringify(store.item("box").frame));
  store.select(["box"]);
  const pt = screenOf(150, 140);   // (in the shape under it, away from the moved box's line)
  pointer("pointerdown", pt);
  pointer("pointerup", pt, { buttons: 0 });
  await settle();
  check(store.selection.join() === "under", "and a click inside it, without a drag, picks the shape under it", store.selection.join());
}

// A page dragged out of the window from the Pages list is offered to the window under the pointer
// (app.pageAway while it's away, app.copyPageAway on letting go: a copy, the page staying here);
// a page dragged in from another window shows where it would go, and goes there
async function pageDragChecks(app) {
  store.setDoc(await rpc("new_document"));
  app.addPage();
  panels.renderPages();
  await settle();
  const calls = [], keep = { pageAway: app.pageAway, copyPageAway: app.copyPageAway };
  app.pageAway = (on) => calls.push(["away", on]);
  app.copyPageAway = (i) => calls.push(["copy", i]);
  try {
    const row = panels.pageList.querySelector('li[data-index="1"]'), r = row.getBoundingClientRect(), y = r.top + r.height / 2;
    const ev = (type, x) => row.dispatchEvent(new PointerEvent(type, { clientX: x, clientY: y, screenX: x + 100, screenY: y + 100, bubbles: true,
      button: 0, buttons: type === "pointerup" ? 0 : 1, pointerId: 9, pointerType: "mouse" }));
    ev("pointerdown", r.left + 30);
    ev("pointermove", r.left + 40);
    ev("pointermove", -40);   // out of the window
    ev("pointerup", -40);
    await settle();
  } finally {
    Object.assign(app, keep);
  }
  check(calls.some(([k, on]) => k === "away" && on) && JSON.stringify(calls.at(-1)) === '["copy",[1]]' && store.doc.pages.length === 2,
    "a page dragged out of the window is offered to the window under the pointer, as a copy", JSON.stringify(calls));
  const first = panels.pageList.querySelector("li[data-index]").getBoundingClientRect();
  const at = [first.left + 20, first.top + first.height * 0.75];   // (its lower half: after it)
  window.FA.pageDragOver(...at);
  const line = !!panels.pageList.querySelector(".slide-drop-line");
  window.FA.pageDragOver(null, null);
  const gone = !panels.pageList.querySelector(".slide-drop-line");
  const page = { ...JSON.parse(JSON.stringify(store.doc.pages[0])), id: "pgElsewhere", name: "From elsewhere" };
  const name = window.FA.pageDrop({ name: "Another figure", pages: [page], assets: {}, symbols: [], swatches: [], text_styles: [], object_styles: [] }, ...at);
  check(line && gone && store.doc.pages.length === 3 && store.doc.pages[1].name === "From elsewhere" && store.pageIndex === 1
    && typeof name === "string" && name.length > 0,
  "a page dragged in from another window shows a line where it would go, and a copy goes there", `${line} ${gone} ${store.doc.pages.map((p) => p.name)}`);
}

// Several pages selected in the Pages list: ⌘-click (Ctrl-click) adds or takes away one, Shift-click
// and Shift+arrows a run, ⌘A all (the list focused). Duplicate, Delete, a drag, Copy, Cut and
// Paste (here or in another window), a drop in another window and Export take them all, each one
// undo step
async function pageSelectChecks(app) {
  store.setDoc(await rpc("new_document"));
  for (let k = 0; k < 4; k++) app.addPage();   // (5 pages)
  store.update("Name the pages", (doc) => doc.pages.forEach((p, i) => { p.name = "ABCDE"[i]; }));
  store.setPage(0);
  panels.renderPages();
  await settle();
  const li = (i) => panels.pageList.querySelector(`li[data-index="${i}"]`);
  const click = (i, opts = {}) => li(i).dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0,
    ...(opts.mod ? (isMac ? { metaKey: true } : { ctrlKey: true }) : {}), shiftKey: !!opts.shift }));
  const names = () => store.doc.pages.map((p) => p.name).join("");
  const sel = () => store.selectedPages().map((i) => store.doc.pages[i].name).join("");
  click(1);
  click(3, { mod: true });
  const two = sel() === "BD" && store.pageIndex === 3 && li(1).classList.contains("selected") && li(3).classList.contains("current")
    && li(1).getAttribute("aria-selected") === "true" && li(2).getAttribute("aria-selected") === "false";
  click(4, { shift: true });   // (from D, the page last clicked)
  const run = sel();
  click(4, { mod: true });
  check(two && run === "DE" && sel() === "D" && store.pageIndex === 3, "⌘-click adds a page, Shift-click a run, ⌘-click takes one away",
    `${two} ‹${run}› ‹${sel()}› ${store.pageIndex}`);
  click(0);
  panels.pageList.focus();
  panels.pageList.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", shiftKey: true, bubbles: true }));
  panels.pageList.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", shiftKey: true, bubbles: true }));
  const keys = sel();
  panels.pageList.focus();
  await app.run("selectAll");   // (⌘A with the Pages list focused)
  const all = sel();
  click(2);
  check(keys === "ABC" && store.pageIndex === 2 && all === "ABCDE" && sel() === "C", "Shift+arrows and ⌘A select pages; a plain click, one",
    `${keys} ${all} ${sel()}`);
  // Duplicate and Delete take every selected page
  click(1);
  click(2, { mod: true });
  let undos = store.history.length;
  await app.run("duplicatePage");
  const dup = names(), dupSel = sel(), dupUndo = store.history.length - undos;
  app.undo();
  check(dup === "ABCB copyC copyDE" && dupSel === "B copyC copy" && dupUndo === 1 && names() === "ABCDE",
    "Duplicate copies the selected pages after them, selected, one undo step",
  `${dup} / ${dupSel} / ${dupUndo}`);
  click(1);
  click(3, { mod: true });
  undos = store.history.length;
  app.autoConfirm = true;
  await app.run("deletePage");
  const del = names(), delUndo = store.history.length - undos;
  app.undo();
  check(del === "ACE" && delUndo === 1 && names() === "ABCDE", "Delete deletes the selected pages, one undo step", `${del} ${delUndo} ${names()}`);
  // A drag takes them all, keeping their order, and they stay selected
  click(0);
  click(2, { mod: true });
  panels.renderPages();
  const row = li(0), r = row.getBoundingClientRect(), last = li(4).getBoundingClientRect();
  const ev = (type, y) => row.dispatchEvent(new PointerEvent(type, { clientX: r.left + 30, clientY: y, bubbles: true, button: 0,
    buttons: type === "pointerup" ? 0 : 1, pointerId: 11, pointerType: "mouse" }));
  ev("pointerdown", r.top + r.height / 2);
  ev("pointermove", r.top + r.height / 2 + 8);
  ev("pointermove", last.bottom - 2);
  ev("pointerup", last.bottom - 2);
  await settle();
  check(names() === "BDEAC" && sel() === "AC" && store.doc.pages[store.pageIndex].name === "C", "dragging selected pages moves them all, in order",
    `${names()} ‹${sel()}›`);
  app.undo();
  // Copy and Paste (and Cut): after the page showing, the pasted pages selected
  click(1);
  click(2, { mod: true });
  panels.pageList.focus();
  await app.run("copy");
  const copied = app.clipboard?.pages?.map((p) => p.name).join("");
  click(4);
  panels.pageList.focus();
  await app.run("paste");
  await settle();
  const pasted = names(), pastedSel = sel();
  app.undo();
  click(3);
  click(4, { mod: true });
  panels.pageList.focus();
  await app.run("cut");
  await settle();
  const cutNames = names();
  click(0);
  await app.run("paste");
  await settle();
  check(copied === "BC" && pasted === "ABCDEBC" && pastedSel === "BC" && cutNames === "ABC" && names() === "ADEBC",
    "Copy and Paste put the selected pages after the page showing; Cut takes them away", `${copied} ${pasted} ‹${pastedSel}› ${cutNames} ${names()}`);
  // Another window's drop, and its packet: several pages, with what they use
  store.setDoc(await rpc("new_document"));
  for (let k = 0; k < 2; k++) app.addPage();
  store.update("Name the pages", (doc) => doc.pages.forEach((p, i) => { p.name = "XYZ"[i]; }));
  store.selectPages([0, 2], 0);
  const packet = app.pagesPacket(store.selectedPages());
  const first = panels.pageList.querySelector("li[data-index]").getBoundingClientRect();
  window.FA.pageDrop(packet, first.left + 20, first.top + first.height * 0.75);   // (its lower half: after it)
  check(packet.pages.map((p) => p.name).join("") === "XZ" && names() === "XXZYZ" && sel() === "XZ" && store.pageIndex === 1
    && new Set(store.doc.pages.map((p) => p.id)).size === 5, "pages dropped from another window go in together, selected, with ids of their own",
  `${names()} ‹${sel()}›`);
  // Export offers the selected pages, and exports those
  await app.run("export");
  const dlg = [...document.querySelectorAll("dialog[open]")].pop();
  const pageSel = [...dlg.querySelectorAll("select")].find((x) => [...x.options].some((o) => o.value === "selected"));
  check(pageSel?.value === "selected" && pageSel.selectedOptions[0].textContent === "The 2 selected pages",
    "Export offers the selected pages, chosen at first", pageSel ? [...pageSel.options].map((o) => o.textContent).join(" | ") : "no choice");
  dlg.close();
}

// Around the page: scrolling goes past it, as far as keeps something in view; an object outside it
// is picked by a click there (by all that shows of it: a thick line's outer half too), is drawn
// there by a drag or Enter, and stays there wholly off the page (left out of exports)
async function pasteboardChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const r = canvas.stage.getBoundingClientRect(), page = store.page();
  const shape = (id, frame, extra = {}) => ({ id, type: "shape", geom: "rect", frame, rot: 0, flip_h: false, flip_v: false,
    fill: { color: "#cc79a7", opacity: 1 }, stroke: null, ...extra });
  store.update("Off the page", (doc) => doc.pages[store.pageIndex].items.push(shape("half", [-60, 40, 120, 60]),
    shape("thick", [100, 200, 80, 50], { fill: null, stroke: { color: "#000000", width: 24, dash: "solid", cap: "flat", join: "miter",
      opacity: 1 } })), { select: [] });
  await settle();
  const clickAt = async (x, y) => {
    const pt = screenOf(x, y);
    pointer("pointerdown", pt);
    pointer("pointerup", pt, { buttons: 0 });
    await settle();
  };
  await clickAt(-30, 70);
  check(store.selection.join() === "half", "a click on the part of an object outside the page picks it", store.selection.join());
  store.select([]);
  await clickAt(90, 225);   // 10 pt outside the frame, on the 24 pt line's outer half (past a click's own 4 px)
  check(store.selection.join() === "thick", "so does a click on the outer half of a thick line, outside its frame", store.selection.join());
  store.select([]);
  // Scrolling moves the page even while it all fits, and stops with the last 64 px in view
  const wheel = (dx, dy) => canvas.stage.dispatchEvent(new WheelEvent("wheel", { deltaX: dx, deltaY: dy, bubbles: true, cancelable: true,
    clientX: r.left + 100, clientY: r.top + 100 }));
  const corner = screenOf(0, 0);
  wheel(30, 20);
  const moved = screenOf(0, 0);
  check(near(moved[0], corner[0] - 30, 0.5) && near(moved[1], corner[1] - 20, 0.5), "scrolling moves around the page while it all fits",
    `${corner} -> ${moved}`);
  for (let i = 0; i < 40; i++) wheel(500, 0);
  const rightEdge = canvas.toScreen(page.width, 0)[0];   // (the page reaches furthest right)
  for (let i = 0; i < 40; i++) wheel(-500, 0);
  const leftEdge = canvas.toScreen(-60, 0)[0];   // ("half" reaches furthest left)
  check(near(rightEdge, 64, 0.5) && near(leftEdge, r.width - 64, 0.5),
    "scrolling stops with the last 64 px of the page and what's beside it still in view", `${rightEdge} ${leftEdge} of ${r.width}`);
  canvas.fit();
  await settle();
  // Drawn beside the page, by a drag, or Enter with the middle of the view off the page
  canvas.setTool("rect");
  await drag([-150, 300], [-80, 360], { metaKey: true, ctrlKey: true });
  const drawn = store.selected()[0];
  check(drawn?.geom === "rect" && near(drawn.frame[0], -150, 0.5) && near(drawn.frame[2], 70, 0.5),
    "a rectangle dragged out beside the page is made there", JSON.stringify(drawn?.frame));
  canvas.panX = r.width / 2 - -250 * canvas.k;
  canvas.applyView();
  canvas.setTool("rect");
  key("Enter");
  await settle();
  const placed = store.selected()[0];
  check(placed && placed.id !== drawn?.id && placed.frame[0] + placed.frame[2] / 2 < 0,
    "Enter with a drawing tool places it in the middle of the view, off the page too", JSON.stringify(placed?.frame));
  // Moved wholly off the page, it stays (saved with the document); exports leave it out
  store.select(["half"]);
  app.nudge(-300, 0);
  check(store.item("half") && store.item("half").frame[0] + store.item("half").frame[2] < 0 && store.doc.pages[0].items.some((i) => i.id === "half"),
    "an object moved wholly off the page stays there in the document", JSON.stringify(store.item("half")?.frame));
  app.fitPage();   // (only the thick-lined box is on the page now: 80 x 50 pt, its 24 pt line half outside)
  check(near(store.page().width, 104, 0.5) && near(store.page().height, 74, 0.5), "Fit page to content leaves out objects parked off the page",
    `${store.page().width} x ${store.page().height}`);
  app.run("undo");
  canvas.fit();
}

// The page's edge and what's off it: the edge drawn over the objects (Page Edge) and what's past
// it dimmed (Dim Off the Page), saved switches that start on, in the View menu, the ribbon and the
// page's right-click menu. Preview (W) cuts the objects off at the page's edge and hides guides and
// the grid, which then don't snap; a click off the page picks nothing; its note's Stop button
// turns it off, and so does dragging a guide out of a ruler
async function offPageChecks(app) {
  await app.savePrefs({ show_rulers: true, show_guides: true, show_grid: true, snap: true, show_page_edge: true, dim_off_page: true });
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const page = store.page();
  store.update("Past the edge", (doc) => {
    const pg = doc.pages[store.pageIndex];
    pg.items.push({ id: "past", type: "shape", geom: "rect", frame: [page.width - 40, 40, 100, 60], rot: 0, flip_h: false, flip_v: false,
      fill: { color: "#56b4e9", opacity: 1 }, stroke: null });
    pg.guides = { x: [page.width / 2], y: [] };
  }, { select: [] });
  await settle();
  const { pageEdge: edge, offPageVeil: veil, itemsLayer } = canvas;
  const shown = (el) => getComputedStyle(el).display !== "none";
  const layers = [...canvas.view.children];
  check(shown(edge) && shown(veil) && layers.indexOf(edge) > layers.indexOf(itemsLayer) && layers.indexOf(veil) > layers.indexOf(itemsLayer)
    && layers.indexOf(edge) > layers.indexOf(veil) && near(+edge.getAttribute("width"), page.width) && near(+edge.getAttribute("height"), page.height),
  "the page's edge and the dimming off the page are drawn over the objects, at the page's size",
  `${shown(edge)} ${shown(veil)} ${layers.map((l) => l.getAttribute("class"))} ${edge.getAttribute("width")}`);
  const ctx = document.createElement("canvas").getContext("2d"), area = new Path2D(veil.getAttribute("d"));
  check(!ctx.isPointInPath(area, page.width - 20, 70, "evenodd") && ctx.isPointInPath(area, page.width + 30, 70, "evenodd")
    && ctx.isPointInPath(area, -5, -5, "evenodd"), "the dimming covers what's off the page and leaves the page clear", veil.getAttribute("d"));
  const rgb = (hex) => { const c = parseHex(hex); return `rgb(${[1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16)).join(", ")})`; };
  const edgeColour = getComputedStyle(document.documentElement).getPropertyValue("--page-edge").trim();
  check(edgeColour && getComputedStyle(edge).stroke === rgb(edgeColour), "the edge is drawn in the theme's page-edge colour",
    `${getComputedStyle(edge).stroke} vs ${edgeColour}`);
  const pressed = (cmd) => [...document.querySelectorAll(`[data-cmd="${cmd}"]`)].map((b) => b.getAttribute("aria-pressed"));
  check(app.menuChecks().togglePageEdge && app.menuChecks().toggleDimOffPage && !app.menuChecks().togglePreview
    && pressed("togglePageEdge").every((v) => v === "true") && pressed("toggleDimOffPage").every((v) => v === "true")
    && pressed("togglePreview").every((v) => v === "false"), "the View menu and the ribbon show the page edge and dimming on, Preview off",
  `${JSON.stringify(app.menuChecks())} ${pressed("togglePageEdge")} ${pressed("toggleDimOffPage")} ${pressed("togglePreview")}`);
  await app.menu("togglePageEdge");
  await app.menu("toggleDimOffPage");
  const bothOff = !shown(edge) && !shown(veil) && app.prefs.show_page_edge === false && app.prefs.dim_off_page === false
    && !app.menuChecks().togglePageEdge && pressed("togglePageEdge").every((v) => v === "false");
  await app.menu("togglePageEdge");
  await app.menu("toggleDimOffPage");
  check(bothOff && shown(edge) && shown(veil), "View > Page Edge and Dim Off the Page switch them off and on", `${bothOff}`);
  // The page's right-click menu has all three
  app.contextMenuAt(...screenOf(page.width / 4, page.height - 10));   // (beside the guide)
  await until(() => document.querySelector(".context-menu"));
  const labels = [...document.querySelectorAll(".context-menu .menu-label")].map((l) => l.textContent);
  document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  check(["Page edge", "Dim off the page", "Preview"].every((l) => labels.includes(l)), "the page's right-click menu has Page edge, Dim and Preview",
    labels.join(", "));

  key("w");
  await settle();
  const pgGuides = () => canvas.guidesLayer.childElementCount;
  check(canvas.preview && itemsLayer.getAttribute("clip-path") === "url(#fa-page-clip)" && !shown(veil) && shown(edge)
    && !canvas.gridLayer.childElementCount && !pgGuides() && !canvas.previewNote.hidden && app.menuChecks().togglePreview
    && pressed("togglePreview").every((v) => v === "true"),
  "W turns Preview on: objects cut off at the page's edge, no dimming, guides or grid, and a note saying so",
  `${canvas.preview} ${itemsLayer.getAttribute("clip-path")} ${shown(veil)} grid ${canvas.gridLayer.childElementCount} guides ${pgGuides()}`);
  const clip = document.querySelector("#fa-page-clip rect");
  check(near(+clip.getAttribute("width"), page.width) && near(+clip.getAttribute("height"), page.height), "Preview cuts at the page's size",
    `${clip.getAttribute("width")} x ${clip.getAttribute("height")}`);
  const targets = canvas.snapTargets([]);
  check(!targets.xs.some((t) => t.span === null) && targets.grid === null && rulers.markAt("x", canvas.toScreen(page.width / 2, 0)) === null,
    "in Preview, guides and the grid neither show on the rulers nor snap", JSON.stringify(targets.xs.filter((t) => t.span === null)));
  const clickAt = async (x, y) => {
    const pt = screenOf(x, y);
    pointer("pointerdown", pt);
    pointer("pointerup", pt, { buttons: 0 });
    await settle();
  };
  await clickAt(page.width + 30, 70);
  const offClick = store.selection.join();
  await clickAt(page.width - 20, 70);
  check(offClick === "" && store.selection.join() === "past", "in Preview, a click off the page picks nothing; on it, the object",
    `off: ‹${offClick}› on: ‹${store.selection.join()}›`);
  store.select([]);
  canvas.previewNote.querySelector("button").click();
  await settle();
  check(!canvas.preview && !itemsLayer.hasAttribute("clip-path") && shown(veil) && pgGuides() === 1 && canvas.gridLayer.childElementCount
    && canvas.previewNote.hidden && !app.menuChecks().togglePreview, "the note's Stop button turns Preview off, guides and grid back",
  `${canvas.preview} guides ${pgGuides()} grid ${canvas.gridLayer.childElementCount}`);
  key("w");
  await settle();
  const left = document.querySelector(".ruler.left"), lr = left.getBoundingClientRect(), [, gy] = screenOf(0, page.height / 3);
  for (const type of ["pointerdown", "pointerup"]) {
    left.dispatchEvent(new PointerEvent(type, { clientX: lr.left + lr.width / 2, clientY: gy, bubbles: true, button: 0,
      buttons: type === "pointerdown" ? 1 : 0, pointerId: 3, pointerType: "mouse" }));   // (a click: a guide there)
  }
  await settle();
  check(!canvas.preview && store.page().guides.y.length === 1 && pgGuides() === 2, "a guide from a ruler ends Preview, and shows",
    `${canvas.preview} ${JSON.stringify(store.page().guides)}`);
  await app.savePrefs({ show_grid: false });
}

// Renaming the document's file (File > Rename…; on a Mac also the title bar, mactitle.py): its
// name selected without the extension and the folder shown; a name taken or not allowed is
// refused in the dialog, which stays open; a rename keeps unsaved changes unsaved and the title,
// Open Recent and the file follow; Cancel changes nothing. A document never saved is named and
// then saved (the Save dialog, here a stand-in, with that name)
async function renameChecks(app, out) {
  store.setDoc(await rpc("new_document"));
  const run = Date.now().toString(36);   // (names of this run's own: the output folder can be an earlier run's)
  const ext = app.info.doc_ext;   // (.mff: save_document gives a name without one the new documents' extension)
  const first = (await rpc("save_document", store.doc, `${out}/selftest-rename-a-${run}`)).path;
  await rpc("save_document", store.doc, `${out}/selftest-rename-taken-${run}`);
  store.markSaved(first);
  store.update("Something to save", (doc) => doc.pages[store.pageIndex].items.push(gRectFor("rn", 10, 10, 40, 30)));
  await settle();
  const file = (spec) => spec.find((m) => m.title === "File").items;
  check(file(app.menuSpec()).some((it) => it.title === "Rename…" && it.action === "rename"), "File > Rename… is in the Mac menu bar");
  const open = () => [...document.querySelectorAll("dialog[open]")].pop();
  const begin = async () => {
    const running = app.run("rename");
    await until(() => open()?.querySelector("#rename-input"));
    const dlg = open();
    return { running, dlg, input: dlg.querySelector("#rename-input"), ok: dlg.querySelector(".dialog-actions .btn.primary"),
      error: dlg.querySelector("#rename-error") };
  };
  const attempt = async (d, name) => {
    d.input.value = name;
    d.input.dispatchEvent(new Event("input"));
    d.ok.click();
    await until(() => !d.dlg.open || !d.error.hidden);
  };
  let d = await begin();
  check(d.input.value === `selftest-rename-a-${run}` && d.input.selectionStart === 0 && d.input.selectionEnd === d.input.value.length
    && first.endsWith(`selftest-rename-a-${run}.mff`) && d.dlg.querySelector(".rename-ext")?.textContent === ".mff"
    && d.dlg.querySelector("#rename-where").textContent.startsWith("In ")
    && d.ok.textContent === "Rename", "Rename shows the name selected, without .mff, and the folder it's in",
  `‹${d.input.value}› ${d.input.selectionStart}-${d.input.selectionEnd} ${d.dlg.querySelector("#rename-where").textContent}`);
  await attempt(d, `selftest-rename-taken-${run}`);
  const taken = d.dlg.open && !d.error.hidden && /already a file/.test(d.error.textContent) && store.path === first;
  await attempt(d, "bad/name");
  check(taken && d.dlg.open && !d.error.hidden && /contain/.test(d.error.textContent) && store.path === first,
    "a name already taken in the folder, or with a /, is refused there, the dialog open to put it right", d.error.textContent);
  await attempt(d, `selftest-rename-b-${run}${ext}`);   // (typing the extension too is fine)
  await d.running;
  const renamed = store.path;
  const recent = (await rpc("prefs_get")).recent || [];
  let oldGone = false;
  try { await rpc("open_document", first); } catch { oldGone = true; }
  const reopened = await rpc("open_document", renamed).catch(() => null);
  check(!d.dlg.open && renamed.endsWith(`selftest-rename-b-${run}${ext}`) && oldGone && reopened
    && recent.includes(renamed) && !recent.includes(first), "Rename renames the file where it is, and Open Recent follows",
  `${renamed}; old gone ${oldGone}; recent ${recent.slice(0, 3)}`);
  check(store.dirty && document.title.startsWith(`selftest-rename-b-${run}${ext} — edited`),
    "unsaved changes stay unsaved, and the title shows the new name", document.title);
  d = await begin();
  d.dlg.querySelector("button[value=close]").click();
  await d.running;
  check(store.path === renamed && !open(), "Cancel changes nothing", store.path);
  // Never saved: named, then the Save dialog with that name
  store.setDoc(await rpc("new_document"));
  const save = app.save;
  let asked = null;
  app.save = async (as) => { asked = { as, suggested: store.suggested }; };
  try {
    d = await begin();
    const label = `${d.dlg.querySelector("h2").textContent} / ${d.ok.textContent}`;
    await attempt(d, "My figure.mff");
    await d.running;
    check(label === "Name and save / Save…" && asked?.as === true && /(^|[\\/])My figure\.mff$/.test(asked.suggested || "") && !store.path,
      "renaming a document never saved names it and opens Save with that name", `${label}; ${JSON.stringify(asked)}`);
  } finally {
    app.save = save;
  }
  await extensionChecks(app, out);
}

// The document's extension (docfile.py): a new document is saved as .mff; one with an older
// extension (.mosaic, .figasm) opens, Save keeps it under its own name, Rename keeps its
// extension, and Save As offers .mff; each is opened by File > Open's filter and added by a drop
async function extensionChecks(app, out) {
  const run = Date.now().toString(36);
  const ext = app.info.doc_ext, legacy = (app.info.doc_exts || []).filter((e) => e !== ext);
  check(ext === ".mff" && app.info.doc_exts[0] === ".mff" && legacy.join() === ".mosaic,.figasm",
    "new documents are .mff, and older .mosaic and .figasm documents are still mosaic's", JSON.stringify(app.info.doc_exts));
  store.setDoc(await rpc("new_document"));
  const fresh = (await rpc("save_document", store.doc, `${out}/selftest-ext-new-${run}`)).path;
  check(fresh.endsWith(`selftest-ext-new-${run}.mff`), "a new document is saved as .mff", fresh);
  const pathDialog = panels.pathDialog, native = app.info.native;
  for (const old of legacy) {
    const oldPath = (await rpc("save_document", await rpc("new_document"), `${out}/selftest-ext-old-${run}${old}`)).path;
    store.setDoc(await rpc("new_document"));
    const opened = await app.open(oldPath);
    store.update("Something to save", (doc) => doc.pages[0].items.push(gRectFor(`ext${old.slice(1)}`, 10, 10, 20, 20)));
    await app.save();
    const reread = await rpc("open_document", oldPath).catch(() => null);
    check(opened && oldPath.endsWith(`selftest-ext-old-${run}${old}`) && store.path === oldPath && !store.dirty
      && reread?.doc.pages[0].items.length === 1 && reread.path === oldPath,
    `a ${old} document opens, and Save saves it in place under its ${old} name`, `${store.path}; ${store.dirty}`);
    const d = app.run("rename");
    await until(() => document.querySelector("dialog[open] .rename-ext"));
    const dlg = [...document.querySelectorAll("dialog[open]")].pop();
    const shown = `${dlg.querySelector("#rename-input").value}|${dlg.querySelector(".rename-ext").textContent}`;
    dlg.querySelector("button[value=close]").click();
    await d;
    const renamed = await rpc("rename_document", oldPath, `selftest-ext-renamed-${run}`);
    check(shown === `selftest-ext-old-${run}|${old}` && renamed.path?.endsWith(`selftest-ext-renamed-${run}${old}`),
      `Rename keeps a ${old} document's extension`, `${shown}; ${JSON.stringify(renamed)}`);
    store.markSaved(renamed.path);
    let suggested = null;
    panels.pathDialog = async (title, given) => { suggested = given; return null; };
    app.info.native = false;   // (the Save dialog stood in for, in the app's window too)
    try {
      await app.save(true);
    } finally {
      panels.pathDialog = pathDialog;
      app.info.native = native;
    }
    check(/(^|[\\/])selftest-ext-renamed-[a-z0-9]+\.mff$/.test(suggested || "") && store.path === renamed.path,
      `Save As on a ${old} document offers its name as .mff, and the ${old} file stays as it was`, suggested);
    store.setDoc(await rpc("new_document"));
    store.update("Something here", (doc) => doc.pages[0].items.push(gRectFor(`extHere${old.slice(1)}`, 10, 10, 20, 20)));   // (not a blank page, which a drop replaces)
    const pages = store.doc.pages.length;
    await window.FA.onNativeDrop({ paths: [renamed.path], x: 700, y: 450 });
    check(store.doc.pages.length === pages + 1, `a ${old} document dropped on the window adds its pages`, `${store.doc.pages.length} pages`);
  }
  store.setDoc(await rpc("new_document"));
  store.update("Something here", (doc) => doc.pages[0].items.push(gRectFor("extHereMff", 10, 10, 20, 20)));
  const pages = store.doc.pages.length;
  await window.FA.onNativeDrop({ paths: [fresh], x: 700, y: 450 });
  check(store.doc.pages.length === pages + 1, "a .mff document dropped on the window adds its pages", `${store.doc.pages.length} pages`);
  store.setDoc(await rpc("new_document"));
}

// Keeping work safe: a recovery copy (saying which file it's of) 10 s after the last change, and
// at once when the window loses focus; AutoSave (the status bar's switch, File > AutoSave) saves
// into the file instead, keeping the file it saves over as an earlier version; Browse Versions
// puts one back as one undo step; a recovery copy recovers as the document it was of, or as an
// earlier copy of it
async function keepingChecks(app, out) {
  const run = Date.now().toString(36);
  store.setDoc(await rpc("new_document"));
  const path = (await rpc("save_document", store.doc, `${out}/selftest-keep-${run}.mosaic`)).path;
  store.markSaved(path);
  const key = store.autosaveKey, file = path.split(/[\\/]/).pop();
  const ours = async (k = key) => (await rpc("autosaved")).find((c) => c.key === k);
  const box = (id, x) => store.update(`Box ${id}`, (doc) => doc.pages[0].items.push(gRectFor(id, x, 10, 30, 20)));
  box("kp1", 10);
  const early = app.keptVersion === store.version;
  await until(() => app.keptVersion === store.version, 20000);
  const copy = await ours();
  check(!early && copy?.doc_path === path && copy.title === file && copy.objects === 1,
    "a recovery copy is kept 10 s after the last change, saying which file it's of", JSON.stringify(copy));
  box("kp2", 50);
  window.dispatchEvent(new Event("blur"));
  await until(() => app.keptVersion === store.version, 3000);   // (well before 10 s)
  check(app.keptVersion === store.version && (await ours())?.objects === 2, "switching to another app keeps it at once");
  // AutoSave: saved into the file as you work; its recovery copy goes
  const sw = document.querySelector(".autosave-toggle");
  sw.click();
  await until(() => !store.dirty && store.doc.meta?.autosave);
  const on = !store.dirty && sw.getAttribute("aria-pressed") === "true" && app.menuChecks().toggleAutoSave
    && app.menuSpec().find((m) => m.title === "File").items.some((it) => it.action === "toggleAutoSave" && it.check);
  box("kp3", 90);
  const dirtyAfter = store.dirty;
  await until(() => !store.dirty, 20000);
  const saved = (await rpc("open_document", path)).doc;
  check(on && dirtyAfter && !store.dirty && saved.pages[0].items.length === 3 && saved.meta.autosave === true && !(await ours()),
    "AutoSave saves into the file as you work, and the recovery copy goes", `${on} ${dirtyAfter} ${store.dirty} ${saved.pages[0].items.length}`);
  // Browse Versions: the file as it was before AutoSave saved over it, put back as one undo step
  await app.run("browseVersions");
  const dlg = [...document.querySelectorAll("dialog[open]")].pop();
  const lists = [...dlg.querySelectorAll(".versions-list")];
  const versionRows = lists[0]?.querySelectorAll("li").length || 0, historyRows = lists[1]?.querySelectorAll("li").length || 0;
  lists[0]?.querySelector("li:last-child button").click();   // (the oldest: the empty figure first saved)
  await until(() => store.items().length === 0);
  const putBack = store.items().length === 0 && !dlg.open && store.doc.meta.autosave === true;
  app.undo();
  check(versionRows >= 1 && historyRows >= 1 && putBack && store.items().length === 3,
    "Browse Versions lists the file's earlier versions and the copies kept, and puts one back as one undo step",
    `${versionRows} versions, ${historyRows} copies; ${putBack}; ${store.items().length}`);
  sw.click();   // AutoSave off: saved once more, as off
  await until(() => !store.doc.meta?.autosave && !store.dirty);
  check(!(await rpc("open_document", path)).doc.meta.autosave && sw.getAttribute("aria-pressed") === "false",
    "turning AutoSave off saves the figure once more, off");
  // A recovery copy of a saved figure recovers as that figure, or as an earlier copy of it
  const other = `doc-selftest${run}`, twoBoxes = JSON.parse(JSON.stringify(store.doc));
  twoBoxes.pages[0].items = twoBoxes.pages[0].items.slice(0, 2);
  await rpc("autosave", twoBoxes, other, path);
  app.offerRecovery([await ours(other)]);
  const rec = [...document.querySelectorAll("dialog[open]")].pop();
  const earlierBtn = [...rec.querySelectorAll("button")].find((b) => b.textContent === "Earlier copies…");
  earlierBtn.click();
  await until(() => rec.querySelector(".recovery-earlier li"));
  const earlier = rec.querySelectorAll(".recovery-earlier li button").length;
  [...rec.querySelectorAll("button")].find((b) => b.textContent === "Recover").click();
  await until(() => store.autosaveKey === other && store.items().length === 2);
  check(earlier === 1 && store.path === path && store.dirty && store.items().length === 2 && document.title.startsWith(`${file} — edited`),
    "a recovery copy recovers as the document it was of (Save puts it back), with its earlier copies offered", `${earlier} ${store.path}`);
  store.markSaved(path);
  await rpc("discard_autosave", other);
}

// A long job shows its progress: the Export window's settings greyed out and a bar at the top,
// filling, with what it's on and (after a while) about how long is left; Keep working closes the
// window and the bar carries on over the page; Stop stops it and says its files were removed. One
// left to run closes the window as before. Refresh all pictures shows a bar over the page after a
// moment, whose Stop changes nothing. (Headless Chrome's clock stands still while a request is
// out, so the engine's side is stood in for here: the export held open, its progress made up;
// tests/test_progress.py has the engine's own)
async function exportProgressChecks(app, out) {
  const run = Date.now().toString(36), realBase = app.chooseExportBase, realFetch = window.fetch;
  let state = null, held = null, stopped = false;
  window.fetch = async (url, init) => {
    const method = (() => { try { return JSON.parse(init?.body || "{}").method; } catch { return null; } })();
    const reply = (result) => new Response(JSON.stringify({ result }), { headers: { "Content-Type": "application/json" } });
    if (method === "job_progress") return reply(state);
    if (method === "cancel_job") { stopped = true; held?.({ cancelled: true }); return reply(true); }
    if (held === null && ["export", "refresh_assets"].includes(method)) {
      return new Promise((resolve) => { held = (result) => { held = undefined; resolve(reply(result)); }; });
    }
    return realFetch(url, init);
  };
  app.chooseExportBase = async () => `${out}/selftest-progress-${run}`;
  try {
    store.setDoc(await rpc("new_document"));
    store.update("A box", (doc) => doc.pages[0].items.push(gRectFor("pgBox", 20, 20, 300, 200)));
    const begin = async ({ all = false, dpi = null } = {}) => {
      await app.run("export");
      const dlg = [...document.querySelectorAll("dialog[open]")].pop();
      for (const i of dlg.querySelectorAll(".formats input, .advanced input[value]")) i.checked = ["pdf", "png"].includes(i.value);
      const field = (text) => document.getElementById([...dlg.querySelectorAll("label")].find((l) => l.textContent === text).htmlFor);
      if (all) field("Pages").value = "all";
      if (dpi) {
        const res = field("Resolution for PNG, TIFF and JPEG");
        res.value = "custom";
        res.dispatchEvent(new Event("change", { bubbles: true }));
        field("Custom resolution").value = dpi;
      }
      [...dlg.querySelectorAll(".dialog-actions button")].find((b) => b.textContent === "Export…").click();
      await until(() => dlg.querySelector(".progress-view") || !dlg.open);   // (a quick one may be done already)
      return dlg;
    };
    let dlg = await begin();
    const buttons = () => [...dlg.querySelectorAll(".dialog-actions button")].filter((b) => !b.hidden).map((b) => b.textContent).join(",");
    const greyed = dlg.querySelector("fieldset.plain-fieldset").disabled && buttons() === "Keep working,Stop"
      && dlg.querySelector(".dialog-body").firstElementChild.classList.contains("progress-view");
    state = { fraction: 0.25, label: "Building the PDF, page 1 of 2", cancelled: false };
    await until(() => near(dlg.querySelector(".progress-view progress").value, 0.25, 1e-6));
    const early = dlg.querySelector(".progress-line").textContent;
    await wait(2200);
    state = { fraction: 0.5, label: "Drawing PNG at 600 dpi, page 1 of 2", cancelled: false };
    await until(() => near(dlg.querySelector(".progress-view progress").value, 0.5, 1e-6));
    const later = dlg.querySelector(".progress-line").textContent, pct = dlg.querySelector(".progress-pct").textContent;
    check(greyed && early === "Building the PDF, page 1 of 2" && /^Drawing PNG at 600 dpi, page 1 of 2 · (about \d+ s|a few seconds) left$/.test(later) && pct === "50%",
      "a long export greys out its settings and shows a bar filling at the top, with what it's on and, after a while, the time left",
    `greyed ${greyed} (${buttons()}); ‹${early}› ‹${later}› ${pct}`);
    [...dlg.querySelectorAll(".dialog-actions button")].find((b) => b.textContent === "Keep working").click();
    const note = () => document.querySelector(".progress-note");
    state = { fraction: 0.75, label: "Writing PNG, page 2 of 2", cancelled: false };
    await until(() => near(note()?.querySelector("progress").value ?? 0, 0.75, 1e-6));
    const carried = !dlg.open && /Writing PNG, page 2 of 2/.test(note()?.querySelector(".progress-line").textContent || "");
    note()?.querySelector(".progress-row button").click();   // Stop
    await panels.writing;
    const said = document.querySelector(".done-note:not(.progress-note)")?.textContent || "";
    check(carried && stopped && !note() && /Export stopped: the files it had written were removed/.test(said),
      "Keep working carries the bar on over the page; its Stop stops the export and says the files were removed", `${carried} ${stopped} ‹${said}›`);
    document.querySelector(".done-note-close")?.click();
    // Left to run (the engine's own export this time): the window closes and names the files
    held = undefined;
    state = null;
    dlg = await begin();
    await panels.writing;
    const done = document.querySelector(".done-note:not(.progress-note)")?.textContent || "";
    check(!dlg.open && !document.querySelector(".progress-view") && /Exported selftest-progress/.test(done),
      "an export left to run closes its window and names the files, as before",
    `open ${dlg.open} ‹${dlg.querySelector(".results")?.textContent}› notes ${[...document.querySelectorAll(".done-note")].map((n) => n.textContent).join(" | ")}`);
    document.querySelector(".done-note-close")?.click();
    // Refresh all pictures: a bar over the page after a moment; Stop changes nothing
    held = null;
    stopped = false;
    store.doc.assets.selftestLinked = { name: "linked plot", primary: "svg", variants: { svg: { kind: "svg", src: "/nowhere/plot.svg", sha256: "0" } } };
    const assetsBefore = JSON.stringify(store.doc.assets);
    const refreshing = app.refreshAll();
    state = { fraction: 0, label: "Reading linked plot (1 of 1)", cancelled: false };
    await until(() => note()?.querySelector(".progress-line")?.textContent.startsWith("Reading linked plot"));
    const shown = note()?.querySelector(".progress-title")?.textContent;
    note()?.querySelector(".progress-row button").click();
    await refreshing;
    const live = () => document.getElementById("live").textContent;
    await until(() => /Refresh stopped/.test(live()));   // (announcements show a moment later)
    check(shown === "Refreshing pictures…" && stopped && !note() && JSON.stringify(store.doc.assets) === assetsBefore
      && /Refresh stopped: no pictures were changed/.test(live()),
    "Refresh all pictures shows a bar over the page, and its Stop changes nothing", `‹${shown}› ${stopped} ${!note()} ‹${live()}›`);
    delete store.doc.assets.selftestLinked;
    // In the app's own window (whose clock runs while the engine works): a real export's bar fills
    // from the engine's own progress, 4 pages at 1200 dpi
    if (!/HeadlessChrome/.test(navigator.userAgent)) {
      window.fetch = realFetch;
      for (let k = 0; k < 3; k++) app.addPage();
      store.update("Boxes", (doc) => doc.pages.forEach((pg, i) => pg.items.push(gRectFor(`pgr${i}`, 20, 20, 300, 200))));
      dlg = await begin({ all: true, dpi: 1200 });
      const seen = [];
      await until(() => {
        const v = dlg.querySelector(".progress-view progress")?.value, t = dlg.querySelector(".progress-line")?.textContent;
        if (v) seen.push([v, t]);
        return !dlg.open;
      }, 120000);
      await panels.writing;
      const labels = new Set(seen.map(([, t]) => t.split(" · ")[0]));
      check(seen.some(([v]) => v > 0 && v < 1) && [...labels].some((t) => /page \d of 4/.test(t)) && !dlg.open,
        "in the app's window, a real export's bar fills from the engine's own progress", `${seen.length} looks; ${[...labels].slice(0, 4).join(" | ")}`);
      document.querySelector(".done-note-close")?.click();
    }
  } finally {
    window.fetch = realFetch;
    app.chooseExportBase = realBase;
  }
}

// Zoom inset shapes: the Zoom inset button's ▾ menu offers a rounded rectangle, an ellipse and a
// circle beside the rectangle a plain click makes; the inset takes its box's shape, and the lines
// run along the outside, touching both; the Zoom shape list changes both, or one alone with Same
// shape unticked (ticked again, the other takes its shape); a circle's box stays round
// Scale bars (2026-11-17): measuring a picture again (from the bar's own tab too), with the line and
// length from last time kept; removing a scale; the label's gap to the letters (typed, or by its
// handle, the bar staying put), font, italic and text style; turning a bar, its outline keeping its
// corner of the picture
async function scaleBarChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const plot = btoa('<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="120pt" viewBox="0 0 200 120">'
    + '<rect x="0" y="0" width="200" height="120" fill="#223344"/><rect x="20" y="20" width="100" height="4" fill="#ffffff"/></svg>');
  const path = await rpc("selftest_scratch", "scalebar_plot.svg", plot);
  await app.placeFiles([path], [60, 80], false);
  const pic = () => store.items().find((it) => it.type === "picture");
  if (!pic()) return log(false, "a picture is placed for the scale bars", path);
  const picId = pic().id, asset = () => store.doc.assets[pic().asset];
  app.setPictureScale(picId, 0.5, "µm", "typed");
  app.addScaleBar(picId);
  const barId = store.selected()[0]?.id, bar = () => store.item(barId);
  await settle();
  const buttonText = (text) => { inspector.render(); return [...document.querySelectorAll("#inspector button")].find((b) => b.textContent === text); };
  const barMid = () => {
    const b = bar(), [, , w, h] = b.frame, t = b.thickness ?? 2;
    return apply(frameMatrix(b.frame, b.rot || 0), w / 2, b.label === "above" ? h - t / 2 : t / 2);
  };
  const typeIn = (label, v) => {
    const f = fieldByLabel(label);
    if (!f) return false;
    f.value = v;
    f.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  };
  const engineGap = () => canvas.els.get(barId)?.labelGap;

  // The gap: a bar from before says where its letters are; typed or dragged, the bar stays put
  const legacy = engineGap();
  // (as bars were: about 2 pt with the Mac's Helvetica, 0.8 pt with what Windows has for it)
  check(bar()?.type === "scalebar" && bar().gap === undefined && legacy > 0 && legacy < 6 && near(+fieldByLabel("Gap to text")?.value, legacy, 0.006),
    "a scale bar's Gap to text shows how far its letters are from the bar, as the engine drew them", `${legacy}`);
  const mid0 = barMid();
  typeIn("Gap to text", "0.5");
  await settle();
  check(bar().gap === 0.5 && near(barMid()[0], mid0[0], 1e-6) && near(barMid()[1], mid0[1], 1e-6) && near(engineGap(), 0.5, 0.005),
    "a typed gap puts the letters that far from the bar (to their outline), the bar staying put", JSON.stringify([bar().frame, engineGap()]));
  const gapHandle = canvas.handlesFor(bar()).find((hd) => hd.kind === "gap");
  check(gapHandle && canvas.handlesFor(bar()).map((hd) => hd.kind).join() === "gap,rotate",
    "a scale bar has a gap handle and a rotation handle, and no resize handles", JSON.stringify(canvas.handlesFor(bar())));
  {
    const [x, y, w, h] = bar().frame, at = [x + w / 2, y + h - 2 - 0.5];
    await drag(at, [at[0], at[1] - 2]);
  }
  check(near(bar().gap, 2.5, 0.15) && near(barMid()[1], mid0[1], 1e-6) && near(engineGap(), bar().gap, 0.005),
    "dragging the gap handle 2 pt up moves the letters 2 pt further from the bar, which stays put", JSON.stringify([bar().gap, engineGap()]));
  await app.run("undo");
  check(bar().gap === 0.5, "and Undo puts the gap back", `${bar().gap}`);

  // Font and italic, and a text style the label follows
  typeIn("Font", "Courier");
  [...document.querySelectorAll("#inspector button")].find((b) => b.getAttribute("aria-label") === "Italic")?.click();
  await settle();
  check(bar().font === "Courier" && bar().italic === true && near(engineGap(), 0.5, 0.005),
    "a scale bar's label takes a font and italic, its letters still at the gap", JSON.stringify([bar().font, bar().italic, engineGap()]));
  store.update("A text style", (doc) => { doc.text_styles = [...(doc.text_styles || []), { id: "tsBar", name: "Bar label", font: "Helvetica", size: 8, bold: true }]; });
  await choose("Text style", "tsBar");
  check(bar().text_style === "tsBar" && bar().font === "Helvetica" && bar().size === 8 && bar().bold === true && !bar().italic,
    "a text style gives the label its font, size, bold and italic", JSON.stringify(bar()));
  store.update("Restyle", (doc) => {
    const st = doc.text_styles.find((x) => x.id === "tsBar"), old = JSON.parse(JSON.stringify(st));
    st.size = 9;
    restyle(doc, old, st);
  });
  check(bar().size === 9, "the label follows its style when the style changes", `${bar().size}`);
  typeIn("Text size", "7");
  const clear = buttonText("Clear changes");
  clear?.click();
  check(clear && bar().size === 9, "a label changed by hand can be put back to its style", `${bar().size}`);
  app.deleteTextStyle("tsBar");
  check(bar().text_style === undefined && bar().size === 9, "deleting the style leaves the label as it was", JSON.stringify(bar()));

  // Turning: the label turns with the bar; its outline keeps its corner of the picture
  store.select([barId]);
  typeIn("Rotation", "270");
  await settle();
  const outline = () => itemBBox(bar()), pf = () => pic().frame;
  const off = () => [outline()[2] - (pf()[0] + pf()[2]), outline()[3] - (pf()[1] + pf()[3])];
  const drawn = canvas.els.get(barId)?.bbox;
  check(bar().rot === 270 && drawn && drawn[3] - drawn[1] > drawn[2] - drawn[0],
    "a scale bar turns (Rotation 270°), its label with it", JSON.stringify([bar().rot, drawn]));
  const off0 = off(), len0 = bar().frame[2];
  store.update("Bigger picture", (doc) => { const pp = findItem(doc, picId); pp.frame[2] *= 1.5; pp.frame[3] *= 1.5; });
  check(near(bar().frame[2], len0 * 1.5, 1e-6) && near(off()[0], off0[0], 1e-6) && near(off()[1], off0[1], 1e-6),
    "a turned bar's length follows its picture, its outline keeping its place from the picture's corner", JSON.stringify([off0, off()]));
  app.run("rotateRight90");
  check(!(bar().rot % 360), "Rotate right 90° turns a scale bar", `${bar().rot}`);
  app.run("flipHorizontal");
  check(!bar().flip_h, "but flipping leaves it alone (its length would read backwards)", JSON.stringify(bar()));

  // Measuring again: from the bar's tab; the line and length kept, shown and offered next time
  check(buttonText("Measure again…") === undefined && buttonText("Measure scale again…"), "the scale bar's tab offers to measure its picture again");
  buttonText("Measure scale again…").click();
  check(canvas.tool === "measure" && canvas.measuring === picId, "which measures on its picture", `${canvas.tool} ${canvas.measuring}`);
  const p0 = pf().slice(), ps = () => pageScale(pic(), asset());
  const answer = async (v) => {
    await until(() => [...document.querySelectorAll("dialog[open] input")].length);
    const dlg = [...document.querySelectorAll("dialog[open]")].pop(), input = dlg.querySelector("input"), was = input.value;
    input.value = v;
    [...dlg.querySelectorAll("button")].find((b) => b.textContent === "OK").click();
    return was;
  };
  await drag([p0[0] + 10, p0[1] + 20], [p0[0] + 110, p0[1] + 20]);
  const first = await answer("50 µm");
  await until(() => pic().scale?.how === "measured");
  const line = pic().measured?.line || [[0, 0], [0, 0]];
  check(first === "" && pic().measured?.length === 50 && pic().measured.unit === "µm"
    && near(Math.hypot(line[1][0] - line[0][0], line[1][1] - line[0][1]), 100 / ps(), 1e-6) && near(pic().scale.per_pt, 50 / (100 / ps()), 1e-9)
    && near(bar().frame[2], (bar().length / pic().scale.per_pt) * ps(), 1e-6),
  "measuring keeps the line drawn (in the picture's own points) and the length typed; the bar follows the new scale", JSON.stringify(pic().measured));
  canvas.startMeasure(picId);
  const before = canvas.overlay.querySelector(".measure-line.before"), want = canvas.toScreen(p0[0] + 10, p0[1] + 20);
  check(before && near(+before.getAttribute("x1"), want[0], 0.01) && near(+before.getAttribute("y1"), want[1], 0.01),
    "measuring again shows the line measured last time", before?.outerHTML);
  await drag([p0[0] + 10, p0[1] + 40], [p0[0] + 60, p0[1] + 40]);
  const second = await answer("25");
  await until(() => pic().measured?.length === 25);
  check(second === "50 µm" && pic().measured?.unit === "µm" && near(pic().scale.per_pt, 25 / (50 / ps()), 1e-9),
    "and starts from the length typed last time (a number alone keeps its unit)", JSON.stringify([second, pic().measured]));
  store.select([picId]);
  check(fieldByLabel("Measured line's length")?.value === "25 µm" && buttonText("Measure again…"),
    "the picture's tab shows the measured length, and Measure again…", fieldByLabel("Measured line's length")?.value);
  const per0 = pic().scale.per_pt;
  typeIn("Measured line's length", "50");
  check(near(pic().scale.per_pt, per0 * 2, 1e-12) && pic().measured.length === 50, "a corrected length re-scales from the same line", JSON.stringify(pic().scale));
  const w0 = bar().frame[2];
  buttonText("Remove scale")?.click();
  check(!pic().scale && !pic().measured && near(bar().frame[2], w0, 1e-9) && buttonText("Measure…"),
    "Remove scale starts over: no scale and no line kept; its bar stays as it was", JSON.stringify(pic()));
  // (ends with the bar selected on its own tab, for a screenshot of the run)
  app.setPictureScale(picId, 0.5, "µm", "typed");
  store.select([barId]);
  inspector.render();
  document.getElementById("itab-scalebar")?.click();
}

async function zoomShapeChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.fit();
  await settle();
  const plot = btoa('<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="120pt" viewBox="0 0 200 120">'
    + '<rect x="10" y="10" width="180" height="100" fill="#336699"/><circle cx="100" cy="60" r="30" fill="#e69f00"/></svg>');
  const path = await rpc("selftest_scratch", "zoom_plot.svg", plot);
  await app.placeFiles([path], [60, 80], false);
  const pic = store.items().find((it) => it.type === "picture");
  if (!pic) return log(false, "a picture is placed for the zoom insets", path);
  const [px, py] = pic.frame;
  let boxId = null;   // the zoom inset made last (it comes selected: its inset)
  const made = () => { boxId = store.selected()[0]?.inset?.box; };
  const parts = () => {
    const all = store.items(), box = all.find((it) => it.id === boxId);
    return { box, inset: all.find((it) => it.inset?.box === boxId), lines: all.filter((it) => it.zoomline?.box === boxId) };
  };
  // Points along a shape's edge (a rounded rectangle's corners as arcs), to measure the lines by
  const edge = ([x, y, w, h], shape, rounding = 0) => {
    if (shape === "ellipse") return Array.from({ length: 1440 }, (_, i) => [x + (w / 2) * (1 + Math.cos(i * Math.PI / 720)), y + (h / 2) * (1 + Math.sin(i * Math.PI / 720))]);
    const r = (rounding * Math.min(w, h)) / 2;
    return [[x + w - r, y + r, -90], [x + w - r, y + h - r, 0], [x + r, y + h - r, 90], [x + r, y + r, 180]].flatMap(([cx, cy, a0]) =>
      Array.from({ length: 361 }, (_, k) => [cx + r * Math.cos((a0 + k / 4) * Math.PI / 180), cy + r * Math.sin((a0 + k / 4) * Math.PI / 180)]));
  };
  const shapeOf = (it) => (it.zoom ? (it.geom === "ellipse" ? "ellipse" : "rect") : it.mask?.geom === "ellipse" ? "ellipse" : "rect");
  const roundingOf = (it) => (it.zoom ? it.rounding : it.mask?.rounding) || 0;
  // Each line starts on the box's edge and ends on the inset's, with both shapes wholly on one side of it
  const touching = () => {
    const { box, inset, lines } = parts(), be = edge(box.frame, shapeOf(box), roundingOf(box)), ie = edge(inset.frame, shapeOf(inset), roundingOf(inset));
    return lines.length === 2 && lines.every(({ points: [a, b] }) => {
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]), side = (p) => ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / len;
      const gap = (p, pts) => Math.min(...pts.map((q) => Math.hypot(q[0] - p[0], q[1] - p[1])));
      const sides = [...be, ...ie].map(side);
      return gap(a, be) < 0.05 && gap(b, ie) < 0.05 && (Math.max(...sides) < 0.02 || Math.min(...sides) > -0.02);
    });
  };
  const fromMenu = async (label) => {
    document.querySelector('#rpanel-figure .tool-more[aria-label="Zoom inset shapes"]').click();
    const items = [...document.querySelectorAll(".context-menu .menu-item")];
    const shown = items.map((b) => b.textContent.trim()).join(", "), pictured = items.every((b) => b.querySelector(".menu-pic svg"));
    items.find((b) => b.textContent.trim().endsWith(label))?.click();
    return { shown, pictured };
  };

  const menu = await fromMenu("Circle");
  check(menu.shown === "Rectangle, Rounded rectangle, Ellipse, Circle" && menu.pictured && canvas.tool === "zoom",
    "Zoom inset's ▾ menu has a rectangle, a rounded rectangle, an ellipse and a circle, each pictured", menu.shown);
  await drag([px + 40, py + 20], [px + 90, py + 50]);
  made();
  let { box, inset } = parts();
  check(box?.geom === "ellipse" && box.zoom.circle && near(box.frame[2], 50, 1e-6) && near(box.frame[3], 50, 1e-6)
    && inset?.mask?.geom === "ellipse" && near(inset.frame[2], inset.frame[3], 1e-6),
  "a circle dragged wider than tall stays a circle, and its inset is a circle too", JSON.stringify([box?.frame, box?.zoom, inset?.mask]));
  check(touching(), "the two lines run along the outside of the circles, touching both", JSON.stringify(parts().lines.map((l) => l.points)));
  const insetEl = canvas.els.get(inset.id)?.g;
  await until(() => insetEl?.querySelector(":scope > g[clip-path] > svg"), 3000);   // (the clip comes from the engine)
  check(insetEl?.querySelector(":scope > g[clip-path] > svg") && !insetEl.querySelector("svg[clip-path]"),
    "an inset (scaled and cropped) is clipped to its shape in its frame's units, not the file's", insetEl?.innerHTML.slice(0, 200));
  // Resized another way (one side only), it stays round; the Width field changes both
  store.update("Wider", (doc) => { findItem(doc, box.id).frame[2] = 70; });
  check(near(parts().box.frame[3], 70, 1e-6), "a circle's box made wider grows taller too", JSON.stringify(parts().box.frame));
  store.select([box.id]);
  document.getElementById("itab-arrange")?.click();
  const width = fieldByLabel("Width");
  if (width) {
    width.value = String(toUnit(60, app.prefs.units || "cm"));
    width.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();
  }
  check(near(parts().box.frame[2], 60, 0.01) && near(parts().box.frame[3], 60, 0.01), "and its Width field keeps it round",
    JSON.stringify(parts().box.frame));

  await fromMenu("Rounded rectangle");
  await drag([px + 100, py + 30], [px + 160, py + 70]);
  made();
  ({ box, inset } = parts());
  check(box?.geom === "rect" && near(box.rounding, 0.2, 1e-9) && inset?.mask?.geom === "rect" && near(inset.mask.rounding, 0.2, 1e-9),
    "a rounded rectangle (dragged from the circle's edge) starts at 20% rounding, its inset rounded the same",
    JSON.stringify([box?.rounding, inset?.mask]));
  check(touching(), "the lines touch the rounded corners, not the corners of the frames", JSON.stringify(parts().lines.map((l) => l.points)));

  // The Zoom shape list: both change while they share the shape; unticked, the inset alone
  store.select([box.id]);
  document.getElementById("itab-arrange")?.click();
  await choose("Zoom shape", "ellipse");
  ({ box, inset } = parts());
  check(box.geom === "ellipse" && !box.zoom.circle && inset.mask?.geom === "ellipse" && touching(),
    "Zoom shape on the box makes both ellipses, the lines still touching both", JSON.stringify([box.geom, inset.mask]));
  store.select([inset.id]);
  document.getElementById("itab-picture")?.click();
  const sameBox = fieldByLabel("Same shape as the box");
  sameBox?.click();
  await settle();
  await choose("Zoom shape", "rect");
  ({ box, inset } = parts());
  check(sameBox && box.zoom.own_shapes && box.geom === "ellipse" && !inset.mask && touching(),
    "with Same shape unticked, the inset alone becomes a rectangle", JSON.stringify([box.geom, box.zoom, inset.mask]));
  fieldByLabel("Same shape as the box")?.click();
  await settle();
  ({ box, inset } = parts());
  check(!box.zoom.own_shapes && box.geom === "rect" && !box.rounding && !inset.mask,
    "ticked again on the inset, the box takes the inset's shape", JSON.stringify([box.geom, box.zoom, inset.mask]));
  await choose("Zoom shape", "round");
  await choose("Corner rounding", "50");
  ({ box, inset } = parts());
  check(near(box.rounding, 0.5, 1e-9) && near(inset.mask?.rounding, 0.5, 1e-9),
    "Corner rounding on the inset rounds both, by the same share of their sizes", JSON.stringify([box.rounding, inset.mask]));
}

// Guides from the rulers: pointing at a ruler shows where a click would put a guide, rounded to a
// fine step of its ticks (1 mm at 100%); a click puts it there (the top ruler a vertical guide, the
// left a horizontal one; ⌘ exactly where clicked; on a guide's mark, nothing), and a drag still
// brings one out across the page. A guide's right-click menu, on the page where no object covers
// it or on its mark on a ruler, removes it, removes them all, or hides the guides
async function rulerGuideChecks(app) {
  const keepUnits = app.prefs.units;
  await app.savePrefs({ show_rulers: true, show_guides: true, snap: true, units: "cm" });
  store.setDoc(await rpc("new_document"));
  canvas.zoom = 1;
  canvas.panX = 60;
  canvas.panY = 60;
  canvas.applyView();
  await settle();
  const MM = 72 / 25.4, pg = () => store.page();
  const top = document.querySelector(".ruler.top"), left = document.querySelector(".ruler.left");
  const tr = top.getBoundingClientRect(), lr = left.getBoundingClientRect(), onTop = tr.top + tr.height / 2, onLeft = lr.left + lr.width / 2;
  const ptr = (el, type, x, y, opts = {}) => el.dispatchEvent(new PointerEvent(type, { clientX: x, clientY: y, bubbles: true,
    button: 0, buttons: type === "pointerdown" || type === "pointermove" && opts.held ? 1 : 0, pointerId: 3, pointerType: "mouse", ...opts }));
  const click = (el, x, y, opts = {}) => { ptr(el, "pointerdown", x, y, opts); ptr(el, "pointerup", x, y, opts); };
  const rightClick = async (el, x, y) => {
    el.dispatchEvent(new MouseEvent("contextmenu", { clientX: x, clientY: y, bubbles: true, cancelable: true, button: 2 }));
    await until(() => document.querySelector(".context-menu"));
    return [...document.querySelectorAll(".context-menu .menu-label")].map((l) => l.textContent);
  };
  const menuItem = (text) => [...document.querySelectorAll(".context-menu .menu-item")]
    .find((b) => b.querySelector(".menu-label").textContent === text);
  const sx = (v) => screenOf(v, 0)[0], sy = (v) => screenOf(0, v)[1];

  ptr(top, "pointermove", sx(52.3 * MM), onTop);
  const label = document.querySelector(".guide-preview text")?.textContent;
  check(near(rulers.clickStep(), MM, 1e-9) && canvas.guidePreview?.axis === "x" && near(canvas.guidePreview.value, 52 * MM, 1e-6)
    && label === lengthText(52 * MM), "pointing at the top ruler shows where a click would put a vertical guide, to the nearest 1 mm at 100%",
  `step ${rulers.clickStep() / MM} mm; ${JSON.stringify(canvas.guidePreview)} ‹${label}›`);
  top.dispatchEvent(new PointerEvent("pointerleave"));
  check(!document.querySelector(".guide-preview"), "leaving the ruler takes the line away");
  click(top, sx(52.3 * MM), onTop);
  await settle();
  check(pg().guides.x.length === 1 && near(pg().guides.x[0], 52 * MM, 1e-6) && !pg().guides.y.length,
    "clicking the top ruler puts a vertical guide at that spot", JSON.stringify(pg().guides));
  click(left, onLeft, sy(31.7 * MM));
  await settle();
  check(pg().guides.y.length === 1 && near(pg().guides.y[0], 32 * MM, 1e-6), "clicking the left ruler puts a horizontal guide there",
    JSON.stringify(pg().guides));
  click(top, sx(80.3 * MM), onTop, { metaKey: true, ctrlKey: true });
  await settle();
  const exact = pg().guides.x[1];
  check(pg().guides.x.length === 2 && Math.abs(exact - 80.3 * MM) < 0.6 && Math.abs(exact - 80 * MM) > 0.5,
    "⌘-click puts it exactly where clicked", `${exact / MM} mm`);
  click(top, sx(52 * MM), onTop);
  await settle();
  check(pg().guides.x.length === 2, "clicking a guide's mark adds nothing", JSON.stringify(pg().guides));
  // A drag out of the top ruler still brings out a horizontal guide (⌘: not snapped)
  const to = screenOf(120 * MM, 150);
  ptr(top, "pointerdown", to[0], onTop, { metaKey: true, ctrlKey: true });
  ptr(top, "pointermove", to[0], onTop + 2, { held: true, metaKey: true, ctrlKey: true });
  ptr(top, "pointermove", to[0], (onTop + to[1]) / 2, { held: true, metaKey: true, ctrlKey: true });
  ptr(top, "pointermove", to[0], to[1], { held: true, metaKey: true, ctrlKey: true });
  ptr(top, "pointerup", to[0], to[1], { metaKey: true, ctrlKey: true });
  await settle();
  check(pg().guides.y.length === 2 && near(pg().guides.y[1], 150, 0.6) && pg().guides.x.length === 2,
    "a drag out of the top ruler still brings a horizontal guide down the page", JSON.stringify(pg().guides));

  // The guide's own menu, on the page and on its mark on a ruler
  const labels = await rightClick(canvas.stage, ...screenOf(52 * MM, 120));
  check(labels.join() === "Remove guide,Remove all guides,Hide guides", "right-clicking a guide on the page gives its menu", labels.join());
  menuItem("Remove guide").click();
  check(pg().guides.x.length === 1 && !pg().guides.x.some((v) => near(v, 52 * MM, 1e-6)), "Remove guide removes that guide",
    JSON.stringify(pg().guides));
  await app.undo();
  check(pg().guides.x.some((v) => near(v, 52 * MM, 1e-6)), "and undo puts it back", JSON.stringify(pg().guides));
  const onMark = await rightClick(left, onLeft, sy(32 * MM));
  menuItem("Remove all guides")?.click();
  check(onMark.join() === "Remove guide,Remove all guides,Hide guides" && !pg().guides.x.length && !pg().guides.y.length,
    "right-clicking a guide's mark on a ruler gives the same menu; Remove all guides empties the page", JSON.stringify(pg().guides));
  await app.undo();
  check(pg().guides.x.length === 2 && pg().guides.y.length === 2, "one undo brings them all back", JSON.stringify(pg().guides));
  store.update("Box over the guide", (doc) => doc.pages[store.pageIndex].items.push({ ...gRectFor("gBox", 40 * MM, 90, 30 * MM, 60),
    fill: { color: "#dddddd", opacity: 1 } }));   // (filled: an empty one lets clicks through to the guide)
  await settle();
  const covered = await rightClick(canvas.stage, ...screenOf(52 * MM, 120));
  check(covered.join() === "Remove guide,Remove all guides,Hide guides", "where an object covers the guide, right-clicking it still gives the guide's menu",
    covered.join());
  document.querySelector(".context-menu") && document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  await guideOverChecks(app, { MM, pg, ptr, rightClick });
  store.select([]);
  await rightClick(canvas.stage, ...screenOf(52 * MM, 300));
  menuItem("Hide guides").click();
  await until(() => app.prefs.show_guides === false);
  check(app.prefs.show_guides === false && !document.querySelector(".guides line"), "Hide guides hides them", app.prefs.show_guides);
  await app.savePrefs({ show_guides: true, units: keepUnits || "cm" });
  canvas.setGuidePreview(null);
}

// A guide lies over the objects (from rulerGuideChecks: a vertical guide at 52 mm across the filled
// box gBox, horizontal ones at 32 mm and 150 pt): on it the pointer shows the guide's cursor and a
// drag moves the guide, not the box. Shift, ⌘ or Option on it go to the object, and so does a rule
// lying along a guide (no room to grab it beside the guide)
async function guideOverChecks(app, { MM, pg, ptr, rightClick }) {
  const on = screenOf(52 * MM, 120), boxFrame = () => store.item("gBox").frame.join();
  const frame0 = boxFrame(), guides0 = JSON.stringify(pg().guides);
  store.select([]);
  ptr(canvas.stage, "pointermove", ...on);
  const cursorOn = canvas.stage.style.cursor;
  ptr(canvas.stage, "pointermove", on[0] + 20, on[1]);
  const cursorBox = canvas.stage.style.cursor;
  check(cursorOn === "col-resize" && cursorBox === "move", "over a box, the pointer on a guide shows the guide's cursor, beside it the box's",
    `${cursorOn} ${cursorBox}`);
  const to = screenOf(60 * MM, 120);
  ptr(canvas.stage, "pointerdown", ...on);
  ptr(canvas.stage, "pointermove", on[0] + 3, on[1], { held: true });
  ptr(canvas.stage, "pointermove", ...to, { held: true });
  ptr(canvas.stage, "pointerup", ...to);
  await settle();
  check(near(pg().guides.x[0], 60 * MM, 0.6) && boxFrame() === frame0 && !store.selection.length,
    "a drag on a guide over a box moves the guide; the box stays put and unselected", `${pg().guides.x[0] / MM} mm; ${boxFrame()}`);
  await app.undo();
  check(JSON.stringify(pg().guides) === guides0, "and undo puts the guide back", JSON.stringify(pg().guides));

  // Shift-click and ⌘-drag there are for the box
  ptr(canvas.stage, "pointerdown", ...on, { shiftKey: true });
  ptr(canvas.stage, "pointerup", ...on, { shiftKey: true });
  await settle();
  check(store.selection.join() === "gBox" && JSON.stringify(pg().guides) === guides0, "Shift-click on the guide over the box selects the box",
    store.selection.join());
  const cmd = { metaKey: true, ctrlKey: !isMac };
  ptr(canvas.stage, "pointerdown", ...on, cmd);
  ptr(canvas.stage, "pointermove", on[0] + 3, on[1], { held: true, ...cmd });
  ptr(canvas.stage, "pointermove", on[0] + 30, on[1], { held: true, ...cmd });
  ptr(canvas.stage, "pointerup", on[0] + 30, on[1], cmd);
  await settle();
  check(boxFrame() !== frame0 && JSON.stringify(pg().guides) === guides0, "a ⌘-drag on the guide moves the box, not the guide",
    `${boxFrame()} ${JSON.stringify(pg().guides)}`);
  await app.undo();
  store.select([]);

  // A 0.25 pt rule lying along the 32 mm guide: a click on it picks the rule, and so does a right-click
  store.update("A rule on the guide", (doc) => doc.pages[store.pageIndex].items.push({ id: "gRule", type: "line",
    points: [[150, 32 * MM], [210, 32 * MM]], arrow_start: null, arrow_end: null,
    stroke: { color: "#000000", width: 0.25, dash: "solid", cap: "flat", join: "miter", opacity: 1 } }));
  await settle();
  const onRule = screenOf(180, 32 * MM);
  ptr(canvas.stage, "pointermove", ...onRule);
  const cursorRule = canvas.stage.style.cursor;
  ptr(canvas.stage, "pointerdown", ...onRule);
  ptr(canvas.stage, "pointerup", ...onRule);
  await settle();
  check(store.selection.join() === "gRule" && cursorRule === "move" && JSON.stringify(pg().guides) === guides0,
    "a click on a rule lying along a guide picks the rule", `${store.selection.join()} ${cursorRule}`);
  const ruleMenu = await rightClick(canvas.stage, ...onRule);
  check(!ruleMenu.includes("Remove guide"), "and right-clicking it gives the rule's menu", ruleMenu.join());
  document.querySelector(".context-menu") && document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  await app.undo();
  check(!store.item("gRule"), "(the rule taken away again)");
}

// Rotate right or left 90° and Flip horizontally or vertically, for every kind of object: in the
// Arrange tab (one row still), the right-click menu and the strip above the panel's tabs. The
// selection turns or flips as a whole, flips as it looks on the page, text boxes keep reading the
// right way, brackets stay level or upright, and lines left out keep their ends where the objects
// still have a point
async function turnFlipChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.zoom = 1;
  canvas.panX = 40;
  canvas.panY = 40;
  canvas.applyView();
  const ready = async () => { await settle(); await wait(250); await settle(); };
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const run = async (cmd, ids) => { store.select(ids); await settle(); await app.run(cmd); await ready(); };
  const said = async () => { await wait(120); return document.getElementById("live")?.textContent || ""; };
  const eq = (a, b, tol = 1e-6) => a.length === b.length && a.every((v, i) => (Array.isArray(v) ? eq(v, b[i], tol) : Math.abs(v - b[i]) < tol));
  const stroke = (dash = "solid") => ({ color: "#000000", width: 1, dash, cap: "flat", join: "miter", opacity: 1 });
  const ln = (id, pts, extra = {}) => ({ id, type: "line", points: pts, arrow_start: null, arrow_end: null, stroke: stroke(), ...extra });
  const text = (id, x, y, rot = 0) => ({ id, type: "shape", geom: "rect", textbox: true, frame: [x, y, 40, 10], rot, stroke: null, fill: null,
    text: { paragraphs: [{ align: "l", runs: [{ t: "Label", font: "Helvetica", size: 6, bold: false, italic: false, color: "#000000" }] }],
      insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "none" } });
  store.update("Objects", (doc) => doc.pages[0].items.push(
    { ...gRectFor("tfT", 60, 60, 60, 40), geom: "rtTriangle", rot: 30 },
    ln("tfL", [[200, 60], [260, 90], [240, 120]]),
    gRectFor("tfA", 60, 200, 40, 30), gRectFor("tfB", 160, 220, 20, 20),
    text("tfX", 300, 60), text("tfY", 300, 100, 30),
    { id: "tfG", type: "group", rot: 20, items: [gRectFor("tfG1", 60, 320, 40, 20), ln("tfG2", [[110, 320], [150, 350]])] },
    { id: "tfK", type: "bracket", label: "*", size: 6, bold: false, line_width: 0.75, color: "#000000", rot: 0, dir: "up", tick: 4,
      frame: [300, 200, 60, 6 * 1.5 + 4] }), { select: [] });
  await ready();

  // 1. The Arrange tab has the four, still in one row; the right-click menu has them under Rotate and flip
  const arrange = document.getElementById("rpanel-arrange"), cmds = ["rotateLeft90", "rotateRight90", "flipHorizontal", "flipVertical"];
  document.getElementById("rtab-arrange")?.click();
  const tops = new Set([...arrange.children].map((g) => Math.round(g.getBoundingClientRect().top)));
  check(cmds.every((c) => arrange.querySelector(`[data-cmd="${c}"]`)) && tops.size === 1,
    "the Arrange tab has Rotate right and left 90° and Flip horizontally and vertically, and stays one row",
    `${tops.size} rows; groups ${[...arrange.children].map((g) => Math.round(g.getBoundingClientRect().width)).join(" ")} in ${arrange.clientWidth} px`);
  store.select(["tfA"]);
  const entry = app.objectMenu({}).find((e) => e?.label === "Rotate and flip");
  check(entry && !entry.disabled && entry.items.filter((e) => e !== "-").map((e) => e.label).join(", ")
    === "Rotate right 90°, Rotate left 90°, Flip horizontally, Flip vertically", "the right-click menu has them under Rotate and flip",
  JSON.stringify(entry?.items?.map((e) => e.label)));

  // 2. A turned shape flips as it looks on the page: flipped, its turn reversed, in the same place;
  // the panel's flip shows it, and flipping again puts it back
  const t0 = clone(store.item("tfT"));
  await run("flipHorizontal", ["tfT"]);
  let t = store.item("tfT");
  check(t.flip_h === true && !t.flip_v && near(t.rot, 330, 1e-6) && eq(t.frame, t0.frame),
    "a shape turned 30° flips horizontally as it looks on the page: flipped, at 330°, where it was", `${t.flip_h} ${t.rot} ${t.frame}`);
  inspector.render();
  const panelFlip = document.querySelector('#inspector .turn-flip [aria-label^="Flip horizontally"]');
  check(panelFlip?.getAttribute("aria-pressed") === "true" && document.querySelectorAll("#inspector .turn-flip button").length === 4,
    "the panel's strip has the four buttons, its flip showing the shape is flipped", panelFlip?.outerHTML);
  panelFlip?.click();
  await ready();
  t = store.item("tfT");
  check(!t.flip_h && near(t.rot, 30, 1e-6) && eq(t.frame, t0.frame), "flipped again from the panel, it's back as it was", `${t.flip_h} ${t.rot}`);
  await run("flipVertical", ["tfT"]);
  t = store.item("tfT");
  check(t.flip_v === true && near(t.rot, 330, 1e-6), "flipped vertically: flipped, its turn reversed", `${t.flip_v} ${t.rot}`);
  await app.undo();
  await ready();

  // 3. A line: its points mirror about its middle, and turn a quarter exactly; one undo step each
  const l0 = clone(store.item("tfL").points), depth = store.history.length;
  await run("flipHorizontal", ["tfL"]);
  check(eq(store.item("tfL").points, l0.map(([x, y]) => [460 - x, y])) && store.history.length === depth + 1,
    "a line flips horizontally about its middle, one undo step", JSON.stringify(store.item("tfL").points));
  await app.undo();
  await run("rotateRight90", ["tfL"]);
  check(eq(store.item("tfL").points, l0.map(([x, y]) => [230 - (y - 90), 90 + (x - 230)])),
    "a line turns right 90° about its middle, exactly", JSON.stringify(store.item("tfL").points));
  await app.undo();
  await ready();
  store.select(["tfL"]);
  inspector.render();
  check(document.querySelectorAll("#inspector .turn-flip button").length === 4 && !document.querySelector("#inspector .turn-flip [aria-pressed]"),
    "a line's strip has the four buttons beside its Angle, the flips with nothing to show");

  // 4. Several objects flip and turn as a whole: their places mirror (or swing round) about their middle
  const a0 = clone(store.item("tfA").frame), b0 = clone(store.item("tfB").frame);
  await run("flipHorizontal", ["tfA", "tfB"]);
  check(eq(store.item("tfA").frame, [140, 200, 40, 30]) && eq(store.item("tfB").frame, [60, 220, 20, 20])
    && store.item("tfA").flip_h && store.item("tfB").flip_h, "two objects flip horizontally as a whole: they swap sides, each flipped",
  `${store.item("tfA").frame} ${store.item("tfB").frame}`);
  await app.undo();
  await run("rotateRight90", ["tfA", "tfB"]);
  // (their outline is 60..180 × 200..240, its middle 120, 220: tfA's middle (80, 215) goes to (125, 180))
  const fa = store.item("tfA").frame;
  check(eq([fa[0] + fa[2] / 2, fa[1] + fa[3] / 2], [125, 180]) && near(store.item("tfA").rot, 90, 1e-6) && near(store.item("tfB").rot, 90, 1e-6),
    "two objects turn right 90° together about their middle", `${fa} ${store.item("tfA").rot}`);
  await app.undo();
  await ready();
  check(eq(store.item("tfA").frame, a0) && eq(store.item("tfB").frame, b0), "(undone)");
  store.select(["tfA", "tfB"]);
  inspector.render();
  check(document.querySelectorAll("#inspector .turn-flip button").length === 4, "several objects' strip has the four buttons beside Rotation");

  // 5. Text boxes keep reading the right way: a level one alone is the same flipped (no undo step, and
  // why); a slanted one among others takes the mirrored slant, unflipped
  const d0 = store.history.length;
  await run("flipVertical", ["tfX"]);
  const why = await said();
  check(store.history.length === d0 && !store.item("tfX").flip_v && /keep reading the right way/.test(why),
    "a level text box flipped on its own stays as it is, and says why", why);
  await run("flipHorizontal", ["tfX", "tfY"]);
  const y1 = store.item("tfY");
  check(!y1.flip_h && !y1.flip_v && near(y1.rot, 330, 1e-6) && !store.item("tfX").flip_h,
    "text boxes flipped with others move and mirror their slant but don't flip", `${y1.flip_h} ${y1.rot}`);
  await app.undo();
  await ready();

  // 6. A group: its parts mirror about the middle of its outline (60 to 150.5 across, its line's
  // stroke included, so it stays where it was), and its turn reverses
  const g0 = clone(store.item("tfG"));
  await run("flipHorizontal", ["tfG"]);
  const g = store.item("tfG");
  check(near(g.rot, 340, 1e-6) && g.items[0].flip_h && eq(g.items[0].frame, [110.5, 320, 40, 20])
    && eq(g.items[1].points, [[100.5, 320], [60.5, 350]]) && eq(itemsBBox(g.items), itemsBBox(g0.items)),
  "a group flips: its parts mirror about its middle, its outline where it was, its turn reverses",
  `${g.rot} ${g.items[0].frame} ${JSON.stringify(g.items[1].points)}`);
  store.select(["tfG"]);
  inspector.render();
  check(document.querySelectorAll("#inspector .turn-flip button").length === 4, "a group's strip has the four buttons");
  await app.undo();
  await ready();
  check(eq(store.item("tfG").items[0].frame, g0.items[0].frame), "(undone)");

  // 7. A bracket stays level or upright: a flip along its bar changes nothing, across it the label
  // changes side; a quarter turn takes the label to the next side round, the ticks as long
  const room = 6 * 1.5, k0 = clone(store.item("tfK"));
  await run("flipHorizontal", ["tfK"]);
  check(eq(store.item("tfK").frame, k0.frame) && store.item("tfK").dir === "up", "a bracket flipped along its bar is the same");
  await run("flipVertical", ["tfK"]);
  check(eq(store.item("tfK").frame, k0.frame) && store.item("tfK").dir === "down", "flipped across its bar, its label goes below",
    store.item("tfK").dir);
  await app.undo();
  await run("rotateRight90", ["tfK"]);
  let k = store.item("tfK");
  check(k.dir === "right" && eq(k.frame, [330 - 6.5, 206.5 - 30, 13, 60]) && near(k.tick, 4, 1e-6),
    "turned right 90°, its label goes to the right, its ticks 4 pt", `${k.dir} ${k.frame} ${k.tick}`);
  await run("rotateRight90", ["tfK"]);
  k = store.item("tfK");
  check(k.dir === "down" && near(k.frame[2], 60) && near(k.frame[3], room + 4, 1e-6) && near(k.frame[1], 206.5 - 6.5, 1e-6),
    "turned right again: label below, ticks still 4 pt, from where they end", `${k.dir} ${k.frame}`);
  store.select(["tfK"]);
  inspector.render();
  check(!fieldByLabel("Rotation") && document.querySelectorAll("#inspector .turn-flip button").length === 4,
    "a bracket's strip has the four buttons and no Rotation (it stays level or upright)");
  await app.undo();
  await app.undo();
  await ready();
  // (one drawn upright, label right, is as wide as its ticks and label: turned right it's as tall as
  // the label's room and its ticks, from the top, where they end)
  store.update("Upright bracket", (doc) => doc.pages[0].items.push({ ...clone(k0), id: "tfK2", dir: "right", frame: [400, 200, 19, 50] }));
  await run("rotateRight90", ["tfK2"]);
  const k2 = store.item("tfK2");
  check(k2.dir === "down" && eq(k2.frame, [384.5, 215.5, 50, room + 4]), "an upright bracket turned right: label below, ticks 4 pt from the top",
    `${k2.dir} ${k2.frame}`);
  await app.undo();
  await app.undo();
  await ready();

  // 8. Lines left out: where the flipped object still has a point there, their end stays, attached;
  // otherwise it goes with its point. A line flipped with the object keeps its end on it; one
  // flipped without it lets go
  store.update("Level", (doc) => { findDeep(doc.pages[0].items, "tfT").rot = 0; });
  await ready();
  const sites = () => canvas.sitesOf(store.item("tfT"));
  const at = (key) => sites().find((x) => x.key === key)?.at;
  const cornerAt = (p) => sites().find((x) => /^c\d+$/.test(x.key) && eq(x.at, p, 1e-6))?.key;
  store.update("Corner lines", (doc) => doc.pages[0].items.push(
    ln("tfE1", [[20, 40], [60, 60]], { end_link: { item: "tfT", site: cornerAt([60, 60]) } }),
    ln("tfE2", [[20, 120], [60, 100]], { end_link: { item: "tfT", site: cornerAt([60, 100]) } }),
    ln("tfE3", [[200, 160], [200, 200]], { end_link: { item: "tfA", site: "c0" } })));
  await ready();
  const e1 = clone(store.item("tfE1").points.at(-1)), e2 = clone(store.item("tfE2").points.at(-1));
  check(cornerAt([60, 60]) && cornerAt([60, 100]) && eq(e1, [60, 60]) && eq(e2, [60, 100]),
    "(two lines on the right triangle's top-left and bottom-left corners)", `${e1} ${e2} ${JSON.stringify(sites())}`);
  await run("flipHorizontal", ["tfT"]);
  const s1 = store.item("tfE1").end_link, s2 = store.item("tfE2").end_link;
  check(s2?.item === "tfT" && eq(store.item("tfE2").points.at(-1), e2) && eq(at(s2.site), e2),
    "flipped, the triangle still has a corner at the bottom left: that line's end stays there, attached",
    `${JSON.stringify(s2)} ${store.item("tfE2").points.at(-1)}`);
  check(s1?.item === "tfT" && eq(store.item("tfE1").points.at(-1), [120, 60]),
    "its top-left corner went to the top right: that line's end goes with it", `${JSON.stringify(s1)} ${store.item("tfE1").points.at(-1)}`);
  await app.undo();
  await ready();
  const both = itemsBBox([store.item("tfT"), store.item("tfE1")]), mid = (both[0] + both[2]) / 2;
  await run("flipHorizontal", ["tfT", "tfE1"]);
  const end1 = store.item("tfE1").points.at(-1), link1 = store.item("tfE1").end_link;
  check(link1?.item === "tfT" && eq(end1, [2 * mid - 60, 60]) && eq(end1, at(link1.site)),
    "a line flipped with the shape stays attached to it, at the mirrored corner", `${link1?.site} ${end1} mid ${mid}`);
  await app.undo();
  await run("flipVertical", ["tfE3"]);
  check(!store.item("tfE3").end_link, "a line flipped without the shape it's attached to lets go of it");
  await app.undo();
  await ready();
  // An end on a dashed line's dash: the line flipped, the end goes to the mirrored dash point
  store.update("Dashed line", (doc) => doc.pages[0].items.push({ ...ln("tfD", [[60, 420], [260, 470]]), stroke: stroke("dash") }));
  await ready();
  const dashes = canvas.sitesOf(store.item("tfD")).filter((x) => /^d\d+m$/.test(x.key));
  const pick = dashes[Math.floor(dashes.length / 4)];
  store.update("On a dash", (doc) => doc.pages[0].items.push(ln("tfH", [[40, 380], pick.at.slice()],
    { end_link: { item: "tfD", site: pick.key, at: canvas.linkLocal(store.item("tfD"), pick.at) } })));
  await ready();
  await run("flipVertical", ["tfD"]);
  const hEnd = store.item("tfH").points.at(-1);
  check(dashes.length > 4 && store.item("tfH").end_link?.item === "tfD" && eq(hEnd, [pick.at[0], 890 - pick.at[1]], 1e-6),
    "an end on a dashed line's dash goes to the mirrored dash point when the line flips", `${pick.key} ${pick.at} -> ${hEnd}`);
  await app.undo();
  await app.undo();
  await app.undo();
  await ready();

  // 9. Locked objects stay put; with only them selected the menu's entry is greyed out
  store.update("Lock", (doc) => { findDeep(doc.pages[0].items, "tfB").locked = true; });
  await run("flipHorizontal", ["tfA", "tfB"]);
  check(store.item("tfA").flip_h && !store.item("tfB").flip_h && eq(store.item("tfB").frame, b0) && eq(store.item("tfA").frame, a0),
    "a locked object stays put while the others flip (here about their own middle)", `${store.item("tfA").frame}`);
  store.select(["tfB"]);
  check(app.objectMenu({}).find((e) => e?.label === "Rotate and flip")?.disabled === true, "with only a locked object selected, Rotate and flip is greyed out");
  await app.undo();
  await app.undo();
  await ready();

  // 10. The Rotation field still turns a shape about its middle, and Transform Again repeats a quarter turn
  store.select(["tfA"]);
  inspector.render();
  const rotField = fieldByLabel("Rotation");
  rotField.value = "45";
  rotField.dispatchEvent(new Event("change", { bubbles: true }));
  await ready();
  check(near(store.item("tfA").rot, 45, 1e-6) && eq(store.item("tfA").frame, a0), "the Rotation field turns a shape about its middle",
    `${store.item("tfA").rot} ${store.item("tfA").frame}`);
  await run("rotateRight90", ["tfA"]);
  await app.run("transformAgain");
  await ready();
  check(near(store.item("tfA").rot, 225, 1e-6), "Rotate right 90° counts for Transform Again", store.item("tfA").rot);
}

// Where line ends attach. Near a corner of a dashed shape an end takes the corner, not a dash's
// point beside it; where two lines meet at a shape's corner each attaches to the shape (moving one
// doesn't carry the other). An end on a dash's point is held by place: when the dashes change it
// takes the dash point nearest where it was (with no dashes, the nearest main point), old links
// without a place included. Until a shape's own points are back from the engine, ends wait rather
// than going to its frame's corners
async function linkChecks(app) {
  store.setDoc(await rpc("new_document"));
  canvas.zoom = 1;
  canvas.panX = 40;
  canvas.panY = 40;
  canvas.applyView();
  const pg = () => store.doc.pages[store.pageIndex].items;
  const stroke = (dash, width = 1) => ({ color: "#000000", width, dash, cap: "flat", join: "miter", opacity: 1 });
  const line = (id, y) => ({ id, type: "line", points: [[20, y], [60, y]], arrow_start: null, arrow_end: null, stroke: stroke("solid", 0.5) });
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const endOf = (id) => store.item(id).points.at(-1).slice();
  const px = 1 / canvas.k;
  const ready = async () => { await settle(); await wait(250); await settle(); };
  store.update("Shapes", (doc) => doc.pages[0].items.push(
    { ...gRectFor("lkD", 150, 120, 160, 100), stroke: stroke("dash") },
    { ...gRectFor("lkS", 400, 120, 100, 80), stroke: stroke("solid") },
    line("lkA", 20), line("lkB", 30), line("lkC", 40), line("lkE", 50)), { select: [] });
  await ready();
  const sitesD = () => canvas.sitesOf(store.item("lkD"));
  const mains = (sites) => sites.filter((x) => !/^d\d+[sme]$/.test(x.key));
  const dragEnd = async (id, to, opts = {}) => { store.select([id]); await settle(); await drag(endOf(id), to, opts, 8); await ready(); };

  // 1. Dropped 3 px along the top from a dashed rectangle's corner, nearer a dash's end there: the
  // corner, not the dash's point
  const corner = sitesD().find((x) => x.key === "c1"), drop = [corner.at[0] - 3 * px, corner.at[1] + 0.3 * px];
  const nearer = sitesD().filter((x) => /^d\d+[sme]$/.test(x.key) && dist(x.at, drop) < dist(corner.at, drop));
  await dragEnd("lkA", drop);
  check(store.item("lkA").end_link?.site === "c1" && dist(endOf("lkA"), corner.at) < 1e-6,
    "an end dropped near a dashed shape's corner attaches to the corner, though a dash's point is nearer",
    `${store.item("lkA").end_link?.site}; nearer dash points ${nearer.map((x) => x.key).join(" ") || "none"}`);
  check(nearer.length > 0, "(the drop was nearer a dash's point than the corner)");

  // 2. On a dash's middle partway along a side, then other dashes: the nearest dash middle, not dash N
  const far = (x) => mains(sitesD()).every((m) => dist(m.at, x.at) > 20 * px);
  const dashMid = sitesD().find((x) => /^d\d+m$/.test(x.key) && far(x) && x.at[1] < 125);
  await dragEnd("lkB", [dashMid.at[0] + 0.5 * px, dashMid.at[1] + 0.5 * px]);
  const onDash = endOf("lkB"), linkB = { ...store.item("lkB").end_link };
  check(/^d\d+m$/.test(linkB.site) && dist(onDash, dashMid.at) < 1e-6 && linkB.at?.length === 2,
    "away from the main points an end attaches to a dash's middle, keeping where it is on the shape",
    `${linkB.site} at ${linkB.at}; end ${onDash.map((v) => v.toFixed(2))} vs ${dashMid.key} ${dashMid.at.map((v) => v.toFixed(2))}`);
  store.update("Move it", (doc) => { const f = findDeep(doc.pages[0].items, "lkD").frame; f[0] += 37; f[1] += 23; });
  await ready();
  const moved = endOf("lkB");
  check(near(moved[0] - onDash[0], 37, 1e-6) && near(moved[1] - onDash[1], 23, 1e-6) && store.item("lkB").end_link.site === linkB.site,
    "moved further than a dash's length, the shape takes the end with it on the same dash", `${moved[0] - onDash[0]}, ${moved[1] - onDash[1]}`);
  await app.undo();
  await ready();
  store.update("Long dashes", (doc) => { findDeep(doc.pages[0].items, "lkD").stroke.dash = "lgDash"; });
  await ready();
  const afterDash = endOf("lkB"), linkB2 = store.item("lkB").end_link;
  check(/^d\d+m$/.test(linkB2?.site || "") && dist(afterDash, onDash) < 6 && linkB2.item === "lkD",
    "when the dashes change it moves to the dash middle nearest where it was, not to dash N's new place",
    `${linkB.site} → ${linkB2?.site}, moved ${dist(afterDash, onDash).toFixed(2)} pt`);
  store.update("Solid", (doc) => { findDeep(doc.pages[0].items, "lkD").stroke.dash = "solid"; });
  await ready();
  const linkB3 = store.item("lkB").end_link, nearestMain = mains(sitesD()).reduce((a, b) => (dist(b.at, afterDash) < dist(a.at, afterDash) ? b : a));
  check(linkB3?.item === "lkD" && linkB3.site === nearestMain.key && !linkB3.at && dist(endOf("lkB"), nearestMain.at) < 1e-6,
    "made solid, it takes the nearest main point and stays attached", `${JSON.stringify(linkB3)} nearest ${nearestMain.key}`);
  await app.undo();
  await app.undo();
  await ready();

  // 3. Two lines meeting at a corner, the first behind the shape: the second attaches to the shape,
  // and moving the first one's end doesn't carry it along
  const cS = canvas.sitesOf(store.item("lkS")).find((x) => x.key === "c0");
  await dragEnd("lkC", cS.at);
  store.update("Behind", (doc) => { const items = doc.pages[0].items, i = items.findIndex((x) => x.id === "lkC"); items.unshift(...items.splice(i, 1)); });
  await ready();
  await dragEnd("lkE", [cS.at[0] + 0.3 * px, cS.at[1] + 0.3 * px]);
  check(store.item("lkE").end_link?.item === "lkS" && store.item("lkE").end_link.site === "c0",
    "where a line's end and a shape's corner are one spot, a new end attaches to the shape", JSON.stringify(store.item("lkE").end_link));
  const eWas = endOf("lkE");
  await dragEnd("lkC", [cS.at[0] - 60, cS.at[1] - 40], { metaKey: true, ctrlKey: !isMac });
  check(dist(endOf("lkE"), eWas) < 1e-6 && dist(endOf("lkC"), eWas) > 30, "and dragging the other line's end away leaves it be",
    `${JSON.stringify(endOf("lkE"))} ${JSON.stringify(endOf("lkC"))}`);

  // 4. A link from before (a dash's point by number, no place): it stays where it's drawn, then
  // holds by place
  const old = sitesD().find((x) => /^d\d+s$/.test(x.key) && far(x) && x.at[1] > 210);
  store.update("Old link", (doc) => { const l = findDeep(doc.pages[0].items, "lkA"); l.points[1] = old.at.slice(); l.end_link = { item: "lkD", site: old.key }; });
  await ready();
  const oldLink = store.item("lkA").end_link;
  check(oldLink.site === old.key && oldLink.at?.length === 2 && dist(endOf("lkA"), old.at) < 1e-6,
    "a dash link from an older file stays where it's drawn, and takes its place on the shape", JSON.stringify(oldLink));
  store.update("Long dashes", (doc) => { findDeep(doc.pages[0].items, "lkD").stroke.dash = "lgDash"; });
  await ready();
  check(dist(endOf("lkA"), old.at) < 6, "then follows the dashes by place too", `${dist(endOf("lkA"), old.at).toFixed(2)} pt`);

  // 5. Before a shape's own points are back (just opened, or a page just shown), a change leaves
  // its ends alone: a triangle's corner isn't its frame's corner
  store.update("Triangle", (doc) => doc.pages[0].items.push({ ...gRectFor("lkT", 150, 300, 100, 80), geom: "triangle" },
    { ...line("lkF", 60), end_link: { item: "lkT", site: "c0" } }));
  await ready();
  const apex = endOf("lkF");
  canvas.els.clear();
  canvas.itemsLayer.replaceChildren();
  canvas.render();
  store.update("A change at once", () => {});
  const atOnce = endOf("lkF");
  await ready();
  check(dist(atOnce, apex) < 1e-6 && dist(endOf("lkF"), apex) < 1e-6 && store.item("lkF").end_link?.site === "c0",
    "a change before a shape's points are back leaves its ends where they are", `${JSON.stringify(apex)} → ${JSON.stringify(atOnce)}`);
  store.select([]);
}

// Colour vision side by side: the page five ways at once, each view through its own filter over a
// copy of the page's objects (not the page's own preview, no ids), and a click keeps one on the
// page. Command search finds the views by "colour blind", "color blind" or a kind's name
async function visionChecks(app) {
  store.setDoc(await rpc("new_document"));
  const box = (id, x, colour) => ({ ...gRectFor(id, x, 60, 70, 70), fill: { color: colour, opacity: 1 } });
  store.update("Colours", (doc) => doc.pages[0].items.push(box("cvRed", 40, "#d55e00"), box("cvGreen", 130, "#009e73")));
  await settle();
  canvas.setColourVision("protanopia");
  document.querySelector('#rpanel-view [data-cmd="compareVision"]').click();
  await until(() => document.querySelector("dialog.cvd-dialog"), 4000);
  const dlg = document.querySelector("dialog.cvd-dialog");
  const views = [...(dlg?.querySelectorAll(".cvd-view") || [])];
  const filterOf = (v) => v.querySelector("svg > g")?.getAttribute("filter");
  const matrixOf = (v) => v.querySelector("feColorMatrix")?.getAttribute("values") || null;
  const copies = views.map((v) => v.querySelector("g.items"));
  check(views.map((v) => v.dataset.mode).join() === "normal,deuteranopia,protanopia,tritanopia,greyscale"
    && !filterOf(views[0]) && views.slice(1).every((v) => filterOf(v) === `url(#fa-cvd-side-${v.dataset.mode})`
      && matrixOf(v) === visionMatrix(v.dataset.mode)),
  "Side by side (View tab) shows the page normally and with each colour vision preview, each through its own filter",
  views.map((v) => `${v.dataset.mode} ${filterOf(v)}`).join("; "));
  check(copies.every((g) => g && g.children.length === canvas.itemsLayer.children.length && !g.getAttribute("filter")
    && !g.querySelector("[id], [data-id]")), "each shows a copy of the page's objects, without the page's own preview or any ids",
  copies.map((g) => g && `${g.children.length} ${g.getAttribute("filter")} ${!!g.querySelector("[id], [data-id]")}`).join("; "));
  check(views.find((v) => v.getAttribute("aria-pressed") === "true")?.dataset.mode === "protanopia",
    "the preview on the page now is marked", views.map((v) => v.getAttribute("aria-pressed")).join());
  views[3].click();
  await until(() => !document.querySelector("dialog.cvd-dialog[open]"));
  check(canvas.colourVision === "tritanopia" && !document.querySelector(".cvd-note").hidden && !document.querySelector("dialog.cvd-dialog[open]"),
    "clicking one keeps previewing it on the page", canvas.colourVision);
  canvas.setColourVision("normal");

  // Command search
  const search = (q) => {
    const input = document.querySelector("dialog.command-search input");
    input.value = q;
    input.dispatchEvent(new Event("input"));
    return [...document.querySelectorAll("dialog.command-search [role=option]")].map((li) => li.textContent);
  };
  key("/", { metaKey: true, ctrlKey: true });
  const ukFound = search("colour blind"), usFound = search("color blind"), grey = search("grayscale")[0] || "";
  const deuter = search("deuter")[0] || "";
  const input = document.querySelector("dialog.command-search input");
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  await until(() => canvas.colourVision === "deuteranopia");
  const visionCmds = (found) => found.filter((t) => t.startsWith("Colour vision")).length;
  check(visionCmds(ukFound) === 6 && visionCmds(usFound) === 6 && /greyscale/.test(grey) && /deuteranopia/.test(deuter)
    && canvas.colourVision === "deuteranopia", "command search finds the views by “colour blind”, “color blind” or a kind's name",
  `${visionCmds(ukFound)} ${visionCmds(usFound)} ${grey} | ${deuter} -> ${canvas.colourVision}`);
  canvas.setColourVision("normal");
  for (const d of document.querySelectorAll("dialog[open]")) d.close();
  const viewMenu = app.menuSpec().find((m) => m.title === "View").items.find((it) => it.title === "Colour-Vision Preview");
  check(viewMenu?.items.some((it) => it.action === "compareVision"), "the Mac View menu has Side by Side… under Colour-Vision Preview",
    JSON.stringify(viewMenu?.items.map((it) => it.title || it)));
}

export async function run(app, params) {
  let keepAids = false;
  const given = (params.get("files") || "").split(",").filter(Boolean);
  const isPpt = (f) => /\.(pptx|slides|gvml)$/i.test(f);
  const files = given.filter((f) => !isPpt(f)), ppt = given.filter(isPpt);   // pictures; PowerPoint's files
  const out = params.get("out");
  app.autoConfirm = true;
  app.info.windows = false;   // (in the app's window too: New and Open replace the figure, except in windowChecks)
  for (const dlg of document.querySelectorAll("dialog[open]")) dlg.close();   // e.g. a recovery offer
  try {
    // Start from the default layout aids, whatever an earlier run left switched on
    await app.savePrefs({ show_rulers: true, show_grid: false, show_guides: true, snap: true });
    store.setDoc(await rpc("new_document"));
    canvas.fit();
    await settle();
    check(store.items().length === 0, "new document is empty");
    if (params.get("only") === "objects") { await objectsListChecks(app); throw ONLY; }   // just that part, while working on it
    if (params.get("only") === "slides") { await slidesChecks(app, ppt); throw ONLY; }
    if (params.get("only") === "links") { await linkedFileChecks(app); throw ONLY; }
    if (params.get("only") === "problem") { await problemReportChecks(app); throw ONLY; }
    if (params.get("only") === "journals") { await myJournalsChecks(app); await findJournalChecks(app); throw ONLY; }
    if (params.get("only") === "dialogs") { await dialogDragChecks(app); throw ONLY; }
    if (params.get("only") === "updates") { await updateChecks(app); throw ONLY; }
    if (params.get("only") === "selection") { await selectionChecks(app); throw ONLY; }
    if (params.get("only") === "windows") { await windowChecks(app, out); throw ONLY; }
    if (params.get("only") === "sizes") { await pageSizeChecks(app); throw ONLY; }
    if (params.get("only") === "vision") { await visionChecks(app); throw ONLY; }
    if (params.get("only") === "export") { await exportNoteChecks(app, out); throw ONLY; }
    if (params.get("only") === "progress") { await exportProgressChecks(app, out); throw ONLY; }
    if (params.get("only") === "guides") { await rulerGuideChecks(app); throw ONLY; }
    if (params.get("only") === "pictures") { await pictureMenuChecks(app); throw ONLY; }
    if (params.get("only") === "zoomshapes") { await zoomShapeChecks(app); throw ONLY; }
    if (params.get("only") === "scalebars") { await scaleBarChecks(app); throw ONLY; }
    if (params.get("only") === "pasteboard") { await pasteboardChecks(app); throw ONLY; }
    if (params.get("only") === "offpage") { await offPageChecks(app); throw ONLY; }
    if (params.get("only") === "rename") { await renameChecks(app, out); throw ONLY; }
    if (params.get("only") === "keeping") { await keepingChecks(app, out); throw ONLY; }
    if (params.get("only") === "pagedrag") { await pageDragChecks(app); throw ONLY; }
    if (params.get("only") === "pageselect") { await pageSelectChecks(app); throw ONLY; }
    if (params.get("only") === "clickthrough") { await clickThroughChecks(app); throw ONLY; }
    if (params.get("only") === "textribbon") { await textRibbonChecks(app); throw ONLY; }
    if (params.get("only") === "journallabels") { await journalLabelChecks(app); throw ONLY; }
    if (params.get("only") === "journalchecks") { await journalCheckChecks(app); throw ONLY; }
    if (params.get("only") === "dangerous") { await dangerousModeChecks(app); throw ONLY; }
    if (params.get("only") === "refresh") { await refreshAllChecks(app); throw ONLY; }
    if (params.get("only") === "arrangetab") { await arrangeTabChecks(app); throw ONLY; }
    if (params.get("only") === "sizestrip") { await sizeStripChecks(app); throw ONLY; }
    if (params.get("only") === "angles") { await angleChecks(app); throw ONLY; }
    if (params.get("only") === "editanchor") { await editAnchorChecks(); throw ONLY; }
    if (params.get("only") === "duptype") { await dupTypeChecks(app); throw ONLY; }
    if (params.get("only") === "crops") { await cropChecks(app); throw ONLY; }
    if (params.get("only") === "attach") { await linkChecks(app); throw ONLY; }
    if (params.get("only") === "turnflip") { await turnFlipChecks(app); throw ONLY; }
    if (params.get("only") === "dashspacing") { await dashSpacingChecks(app); throw ONLY; }
    if (params.get("only") === "multilook") { await multiLookChecks(app); throw ONLY; }
    if (params.get("only") === "freeform") { await freeformChecks(app); throw ONLY; }
    if (params.get("only") === "areagap") { await areaGapChecks(app); throw ONLY; }
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
    check(ribbonTabs.length === 5 && tabRows.every((n) => n === 1) && toolbox.scrollHeight <= toolbox.clientHeight + 1
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
    // Snapping to placed plots: their axis and frame lines and ink edges are snapped to, and a plot
    // being moved snaps by its own
    await until(() => canvas.plotLines?.get(`${pics[0].asset}:0`), 15000);
    const plotT = canvas.plotSnaps(store.item(pics[0].id)), plotFr = store.item(pics[0].id).frame;
    const upright = plotT.find((t) => t.axis === 0 && t.v > plotFr[0] + 1 && t.v < plotFr[0] + plotFr[2] - 1);
    check(upright && plotT.filter((t) => t.axis === 1).length >= 2, "a placed plot's axis lines and ink edges are found to snap to",
      JSON.stringify(plotT.slice(0, 4)));
    // (a twentieth of a point off, nearer than anything else)
    const snapBox = [upright.v + 0.05, plotFr[1] - 40, upright.v + 0.06, plotFr[1] - 30];
    const [plotDx] = canvas.snapMove(snapBox, 0, 0, canvas.snapTargets([]), {});
    check(near(snapBox[0] + plotDx, upright.v, 1e-6), "an object's edge snaps to a plot's axis line",
      `${snapBox[0]} + ${plotDx} vs ${upright.v} (${JSON.stringify(plotT.slice(0, 3))}, frame ${plotFr})`);
    const pageMid = store.page().width / 2, moveDx = pageMid - upright.v + 0.05;
    const [ownDx] = canvas.snapMove(itemsBBox([store.item(pics[0].id)]), moveDx, 0, canvas.snapTargets([pics[0].id]), {},
      canvas.innerSnaps([store.item(pics[0].id)]));
    check(near(upright.v + ownDx, pageMid, 1e-6), "a plot being moved snaps by its own axis line (here to the page's middle)",
      `${upright.v} + ${ownDx} vs ${pageMid}`);
    canvas.snapGuides = [];
    store.select([pics[0].id]);
    inspector.render();
    const units = [...document.querySelectorAll("#inspector .unit")].map((u) => u.textContent);
    check(units.includes("cm") && !units.includes("pt"), "a picture's position and size show in centimetres", units.join(","));
    // A picture stretched unevenly (as PowerPoint can leave one) says so, and 100% puts both sides back
    const trueFr = store.item(pics[0].id).frame.slice();
    store.update("Stretch for test", (doc) => {
      const it = doc.pages[0].items.find((i) => i.id === pics[0].id);
      it.frame = [it.frame[0], it.frame[1], it.frame[2] * 0.988, it.frame[3] * 0.9];
    });
    inspector.render();
    const scaleNote = document.querySelector("#inspector p.scale");
    check(scaleNote?.classList.contains("warn") && /98\.8% across, 90% down — stretched/.test(scaleNote.textContent),
      "a picture stretched unevenly shows its scale across and down, with a warning", scaleNote?.textContent);
    document.querySelector('#inspector button[aria-label="Set to true size (100%)"]').click();
    await settle();
    const backFr = store.item(pics[0].id).frame;
    check(backFr.every((v, i) => near(v, trueFr[i], 1e-6)), "100% puts a stretched picture back to true size both ways",
      `${JSON.stringify(backFr)} vs ${JSON.stringify(trueFr)}`);
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
    // Pathway ends: an inhibition bar, drawn as a line across the end
    const headWas = JSON.parse(JSON.stringify(store.item(arrow.id).arrow_end));
    await choose("End", "bar");
    await settle();
    const barPaths = [...(canvas.els.get(arrow.id)?.g.querySelectorAll("path") || [])].map((pth) => pth.getAttribute("style") || "");
    check(store.item(arrow.id).arrow_end.type === "bar" && barPaths.length === 2 && barPaths[1].includes("fill:none"),
      "an arrow can end in an inhibition bar", barPaths.join(" | "));
    store.update("Head back", (doc) => { findItem(doc, arrow.id).arrow_end = headWas; });
    canvas.setTool("label");
    await drag([5, 5], [5, 5]);
    const label = store.items().find((i) => i.text?.paragraphs?.[0]?.runs?.[0]?.t === "a");
    check(label && label.text.paragraphs[0].runs[0].bold, "panel label 'a' added in bold");
    canvas.setTool("label");
    await drag([5, 200], [5, 200]);
    check(store.items().some((i) => i.text?.paragraphs?.[0]?.runs?.[0]?.t === "b"), "next panel label is 'b'");
    await settle();
    check(label && label.frame[3] > 5 && label.frame[3] < 15, "label box fitted to its text", JSON.stringify(label?.frame));
    // Panel labels stay with their panel: one put on a picture goes with it when it moves or
    // grows, keeps the corner it's dragged to, moves once when moved with its picture, and stays
    // put once detached
    const lpPic = pics[pics.length - 1], lpWas = JSON.parse(JSON.stringify(lpPic));
    const lpF = () => store.item(lpPic.id).frame;
    canvas.setTool("label");
    await drag([lpF()[0] + 4, lpF()[1] + 4], [lpF()[0] + 4, lpF()[1] + 4]);
    const lpId = store.selected()[0]?.id, lpL = () => store.item(lpId);
    check(lpL()?.attach?.to === lpPic.id && lpL().attach.corner === "tl", "a panel label put on a picture is attached to its nearest corner",
      JSON.stringify(lpL()?.attach));
    inspector.render();
    check(/Stays with .*top left corner/.test(document.querySelector("#inspector").textContent), "and its Arrange tab says so");
    const lpAt = lpL().frame.slice();
    store.update("Move the panel", (doc) => { const pp = findItem(doc, lpPic.id); pp.frame[0] += 25; pp.frame[1] += 10; });
    check(near(lpL().frame[0], lpAt[0] + 25, 1e-6) && near(lpL().frame[1], lpAt[1] + 10, 1e-6), "the label goes with its panel",
      `${lpAt} -> ${lpL().frame}`);
    store.update("Label to the top right", (doc) => { findItem(doc, lpId).frame[0] = lpF()[0] + lpF()[2] - 8; });
    const lpRight = lpF()[0] + lpF()[2] - lpL().frame[0];
    store.update("Wider panel", (doc) => { findItem(doc, lpPic.id).frame[2] += 30; });
    check(lpL().attach.corner === "tr" && near(lpF()[0] + lpF()[2] - lpL().frame[0], lpRight, 1e-6),
      "dragged to another corner, it keeps that one when the panel grows", JSON.stringify(lpL().attach));
    store.select([lpPic.id, lpId]);
    const lpX = lpL().frame[0];
    app.nudge(5, 0);
    check(near(lpL().frame[0], lpX + 5, 1e-6), "moved together with its panel, it moves once", `${lpX} -> ${lpL().frame[0]}`);
    store.select([lpId]);
    await app.run("detachLabel");
    const lpY = lpL().frame[1];
    store.update("Move the panel again", (doc) => { findItem(doc, lpPic.id).frame[1] += 40; });
    check(!lpL().attach && near(lpL().frame[1], lpY, 1e-6), "Detach lets go: the label stays put", JSON.stringify(lpL().attach));
    await app.run("attachLabel");
    check(lpL().attach?.to === lpPic.id || !app.labelPanel(lpL()), "Attach to the panel attaches it again when it's on one",
      JSON.stringify(lpL().attach));
    store.update("Panel back", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      items.splice(items.findIndex((i) => i.id === lpPic.id), 1, lpWas);
      items.splice(items.findIndex((i) => i.id === lpId), 1);
    }, { select: [] });
    // Equations: maths typed as in LaTeX become a picture with PDF and SVG copies of one size;
    // a bigger text size draws it again, bigger, in the same place; maths that can't be read says why
    const addingEq = app.addEquation();
    await settle();
    const eqPrompt = [...document.querySelectorAll("dialog[open]")].pop();
    eqPrompt.querySelector("input").value = "\\frac{\\Delta F}{F_0}";
    [...eqPrompt.querySelectorAll("button")].find((b) => b.textContent === "OK").click();
    await addingEq;
    const eqPic = store.selected()[0], eqAsset = eqPic && store.doc.assets[eqPic.asset];
    check(eqPic?.equation?.tex === "\\frac{\\Delta F}{F_0}" && eqAsset?.variants?.pdf && eqAsset.variants.svg
      && JSON.stringify(eqAsset.variants.pdf.size_pt) === JSON.stringify(eqAsset.variants.svg.size_pt),
      "an equation becomes a picture with PDF and SVG copies of one size", JSON.stringify(eqAsset?.size_pt));
    inspector.render();
    check(/Maths, written as in LaTeX/.test(document.querySelector("#inspector").textContent), "its own tab has its maths, size and font");
    const eqAt = eqPic.frame.slice();
    await app.updateEquation(eqPic.id, { size: 12 });
    const eqNow = store.item(eqPic.id).frame;
    check(eqNow[2] > eqAt[2] * 1.6 && near(eqNow[0], eqAt[0], 1e-6) && near(eqNow[1], eqAt[1], 1e-6) && store.item(eqPic.id).equation.size === 12,
      "a bigger text size draws it again, bigger, from the same corner", `${eqAt} -> ${eqNow}`);
    await app.updateEquation(eqPic.id, { tex: "\\frac{a}{" });
    const eqErr = [...document.querySelectorAll("dialog[open]")].pop();
    check(/expected/.test(eqErr?.textContent || "") && store.item(eqPic.id).equation.tex === "\\frac{\\Delta F}{F_0}",
      "maths that can't be read says why, and the equation stays as it was", eqErr?.textContent);
    eqErr?.close();
    store.select([eqPic.id]);
    await app.run("delete");

    // Object styles: a style made from one line and given to another; changing the style moves
    // both, except what one changed by hand; deleting it keeps the look
    const osLine = (id, y, color, width) => ({ id, type: "line", points: [[300, y], [360, y]], arrow_start: null, arrow_end: null,
      stroke: { color, width, dash: "solid", cap: "round", join: "round", opacity: 1 } });
    store.update("Lines for a style", (doc) => doc.pages[store.pageIndex].items.push(osLine("osA", 480, "#ff0000", 2),
      osLine("osB", 500, "#000000", 1)), { select: ["osA"] });
    const makingStyle = app.newObjectStyle();
    await settle();
    const osPrompt = [...document.querySelectorAll("dialog[open]")].pop();
    osPrompt.querySelector("input").value = "Red line";
    [...osPrompt.querySelectorAll("button")].find((b) => b.textContent === "OK").click();
    await makingStyle;
    const redStyle = (store.doc.object_styles || []).find((x) => x.name === "Red line");
    check(redStyle && redStyle.stroke.color === "#ff0000" && !("fill" in redStyle) && store.item("osA").object_style === redStyle.id,
      "New style from this object makes a style with its look, and links it", JSON.stringify(redStyle));
    store.select(["osB"]);
    app.useObjectStyle(redStyle.id);
    check(store.item("osB").stroke.color === "#ff0000" && store.item("osB").stroke.width === 2, "a style given to another object gives it the look");
    store.update("B wider", (doc) => { findDeep(doc.pages[store.pageIndex].items, "osB").stroke.width = 3; });
    inspector.render();
    check(/This object differs from Red line/.test(document.querySelector("#inspector").textContent), "its Style tab says when it differs");
    store.update("A blue", (doc) => { findDeep(doc.pages[store.pageIndex].items, "osA").stroke.color = "#0000ff"; });
    app.redefineObjectStyle(redStyle.id, store.item("osA"));
    check(store.item("osB").stroke.color === "#0000ff" && store.item("osB").stroke.width === 3,
      "Update the style to match: the others follow, keeping what was changed by hand", JSON.stringify(store.item("osB").stroke));
    app.deleteObjectStyle(redStyle.id);
    check(!store.item("osB").object_style && store.item("osB").stroke.color === "#0000ff" && !(store.doc.object_styles || []).length,
      "deleting a style keeps the objects' look");
    store.select(["osA", "osB"]);
    await app.run("delete");

    // Symbols: two objects made a symbol leave one copy; a copy resized to twice the size draws
    // its lines twice as wide; editing one copy in place changes every copy; Break link makes a
    // copy its own objects, scaled as it was
    store.update("Objects for a symbol", (doc) => doc.pages[store.pageIndex].items.push(
      { ...gRectFor("syA", 300, 420, 30, 20), fill: { color: "#ff0000" } }, gRectFor("syB", 336, 424, 10, 10)), { select: ["syA", "syB"] });
    await app.run("makeSymbol");
    const sy1 = store.selected()[0], symDef = () => store.doc.symbols?.find((x) => x.id === sy1?.symbol);
    check(sy1?.type === "symbol" && symDef()?.items.length === 2 && JSON.stringify(sy1.frame) === "[300,420,46,20]"
      && !store.item("syA"), "Make symbol turns the objects into a symbol and leaves one copy where they were", JSON.stringify(sy1));
    await app.run("duplicate");
    const sy2 = store.selected()[0];
    store.update("Twice the size", (doc) => { const c = findDeep(doc.pages[store.pageIndex].items, sy2.id); c.frame[2] *= 2; c.frame[3] *= 2; });
    await settle();
    const drawnOf = (id) => canvas.els.get(id)?.g.innerHTML || "";
    check(sy2.symbol === sy1.symbol && /matrix\(2 0 0 2 /.test(drawnOf(sy2.id)), "a copy at twice the size draws its lines and text twice as large",
      drawnOf(sy2.id).slice(0, 160));
    inspector.render();
    check(/2 copies in this figure, this one at 200%/.test(document.querySelector("#inspector").textContent), "its tab says how many copies there are");
    await app.editSymbol(sy1.id);
    const editG = store.doc.pages[store.pageIndex].items.find((i) => i.editing_symbol);
    check(editG && store.scope.includes(editG.id) && editG.items.length === 2, "double-clicking a copy edits its symbol in place");
    store.update("Blue", (doc) => { findDeep(doc.pages[store.pageIndex].items, editG.items[0].id).fill = { color: "#0000ff" }; });
    store.exitGroup();
    await settle();
    check(symDef().items[0].fill.color === "#0000ff" && store.item(sy1.id)?.type === "symbol" && /#0000ff/i.test(drawnOf(sy2.id))
      && store.selection[0] === sy1.id, "leaving it changes the symbol, and every copy with it", JSON.stringify(symDef().items[0].fill));
    store.select([sy2.id]);
    await app.run("breakSymbol");
    const broken = store.selected()[0];
    check(broken?.type === "group" && near(broken.items[0].stroke.width, 2, 1e-6) && near(broken.items[0].frame[2], 60, 1e-6),
      "Break link makes a copy its own objects, scaled as it was", JSON.stringify(broken?.items?.[0]?.frame));
    store.select([sy1.id, broken.id]);
    await app.run("delete");
    app.deleteSymbol(sy1.symbol);
    check(!(store.doc.symbols || []).length, "a symbol with no copies left can be deleted");

    // Grid layout: three panels as they lie (two in a row, one below) keep their sizes in cells,
    // top left; the grid reflows when one grows, moves as one, and takes a panel dragged onto
    // another cell there; Stop grid layout leaves an ordinary group
    const gRect = gRectFor;
    store.update("Panels for a grid", (doc) => doc.pages[store.pageIndex].items.push(gRect("gA", 100, 300, 60, 40),
      gRect("gB", 180, 305, 50, 30), gRect("gC", 100, 360, 40, 50)), { select: ["gA", "gB", "gC"] });
    await app.run("gridLayout");
    const gridG = store.selected()[0], gF = (id) => store.item(id).frame;
    check(gridG?.grid?.cols === 2 && near(gridG.grid.gap[0], 20, 1e-6) && near(gridG.grid.gap[1], 20, 1e-6)
      && JSON.stringify(gridG.grid.order) === '["gA","gB","gC"]' && near(gF("gB")[1], 300, 1e-6) && near(gF("gB")[0], 180, 1e-6)
      && near(gF("gC")[1], 360, 1e-6), "Grid layout puts panels in rows and columns as they lie, each at the top left of its cell",
      JSON.stringify(gridG?.grid));
    inspector.render();
    check(/Grid layout/.test(document.querySelector("#inspector").textContent) && fieldByLabel("Columns"),
      "and its Arrange tab has the columns and gaps");
    store.update("Wider A", (doc) => { findDeep(doc.pages[store.pageIndex].items, "gA").frame[2] = 80; });
    check(near(gF("gB")[0], 200, 1e-6), "the grid reflows when a panel grows", JSON.stringify(gF("gB")));
    store.select([gridG.id]);
    app.nudge(5, 0);
    check(near(gF("gA")[0], 105, 1e-6) && near(gF("gB")[0], 205, 1e-6) && near(gF("gC")[0], 105, 1e-6),
      "and moves as one", `${gF("gA")[0]} ${gF("gB")[0]} ${gF("gC")[0]}`);
    canvas.enterGroup(gridG.id);
    store.update("Drag C onto B's cell", (doc) => { findDeep(doc.pages[store.pageIndex].items, "gC").frame = [215, 300, 40, 50]; });
    check(JSON.stringify(store.item(gridG.id).grid.order) === '["gA","gC","gB"]' && near(gF("gC")[0], 205, 1e-6)
      && near(gF("gC")[1], 300, 1e-6) && near(gF("gB")[0], 105, 1e-6) && near(gF("gB")[1], 370, 1e-6),
      "a panel dragged onto another cell moves there, and the rest make room", JSON.stringify(store.item(gridG.id).grid));
    store.exitGroup();
    store.select([gridG.id]);
    await app.run("stopGrid");
    const gBAt = gF("gB").slice();
    store.update("Move B by hand", (doc) => { findDeep(doc.pages[store.pageIndex].items, "gB").frame[1] += 7; });
    check(!store.item(gridG.id).grid && near(gF("gB")[1], gBAt[1] + 7, 1e-6), "Stop grid layout leaves an ordinary group");
    store.select([gridG.id]);
    await app.run("delete");

    // The pen: two corners and a dragged smooth point, closed on the first point, make a freeform
    // shape with a curve; its points can be moved, added on the outline, made smooth and removed;
    // an open path of corners is a line; a rectangle can be made editable
    const snapWas = app.prefs.snap;
    await app.savePrefs({ snap: false });
    canvas.setTool("pen");
    await drag([400, 500], [400, 500]);
    await drag([440, 500], [460, 520]);
    await drag([440, 540], [440, 540]);
    await drag([400, 500], [400, 500]);
    const penShape = store.selected()[0], penCmds = () => store.item(penShape.id).path.subpaths[0].cmds;
    check(penShape?.geom === "custom" && penCmds().some((c) => c[0] === "C") && penCmds().at(-1)[0] === "Z" && canvas.tool === "select",
      "the pen draws a closed freeform shape with a smooth point", JSON.stringify(penCmds()));
    const pagePts = () => ringsOf(store.item(penShape.id))[0].nodes.map((nd) => toPageOf(store.item(penShape.id), nd.p));
    canvas.startPointEdit(penShape.id);
    check(canvas.pointEdit?.id === penShape.id && canvas.overlay.querySelectorAll(".pt-node").length === 3, "editing its points shows them");
    const corner = pagePts()[2];
    await drag(corner, [corner[0] + 20, corner[1]]);
    check(near(pagePts()[2][0], corner[0] + 20, 1e-6) && near(pagePts()[2][1], corner[1], 1e-6), "a point drags to a new place",
      `${corner} -> ${pagePts()[2]}`);
    const [penP0, penP2] = [pagePts()[0], pagePts()[2]], penMid = [(penP0[0] + penP2[0]) / 2, (penP0[1] + penP2[1]) / 2];
    await drag(penMid, penMid);
    check(pagePts().length === 4, "a click on the outline adds a point there", `${pagePts().length}`);
    key("Delete");
    check(pagePts().length === 3 && store.item(penShape.id), "Delete removes the point picked, not the shape");
    const penFirst = screenOf(...pagePts()[0]);
    canvas.stage.dispatchEvent(new MouseEvent("dblclick", { clientX: penFirst[0], clientY: penFirst[1], bubbles: true }));
    check(ringsOf(store.item(penShape.id))[0].nodes[0].hout, "double-clicking a corner makes it smooth");
    key("Escape");
    check(!canvas.pointEdit && store.selection[0] === penShape.id, "Escape ends editing the points");
    canvas.setTool("pen");
    await drag([300, 600], [300, 600]);
    await drag([340, 610], [340, 610]);
    key("Enter");
    const penLine = store.selected()[0];
    check(penLine?.type === "line" && penLine.points.length === 2, "an open path of corners is a line", JSON.stringify(penLine?.points));
    store.update("A rectangle", (doc) => doc.pages[store.pageIndex].items.push(gRectFor("edRect", 300, 640, 40, 20)), { select: ["edRect"] });
    await app.makeEditable();
    check(store.item("edRect")?.geom === "custom" && canvas.pointEdit?.id === "edRect" && ringsOf(store.item("edRect"))[0].nodes.length === 4,
      "Make editable shape gives a rectangle four points to move", JSON.stringify(store.item("edRect")?.path));
    key("Escape");
    store.select([penShape.id, penLine.id, "edRect"]);
    await app.run("delete");
    await app.savePrefs({ snap: snapWas });

    // Elbow connectors: a line from one box's right side to another's left runs level, upright,
    // level; it follows when a box moves; the handle on its middle stretch moves that stretch;
    // Straight makes it a straight line again
    store.update("Boxes for an elbow", (doc) => doc.pages[store.pageIndex].items.push(gRectFor("elA", 300, 700, 40, 30),
      gRectFor("elB", 420, 760, 40, 30)));
    await settle();
    const siteKey = (id, at) => canvas.sitesOf(store.item(id)).find((x) => near(x.at[0], at[0], 0.01) && near(x.at[1], at[1], 0.01))?.key;
    store.update("An elbow", (doc) => doc.pages[store.pageIndex].items.push({ id: "elL", type: "line", points: [[340, 715], [420, 775]],
      arrow_start: null, arrow_end: { type: "triangle", w: "med", len: "med" },
      stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 },
      start_link: { item: "elA", site: siteKey("elA", [340, 715]) }, end_link: { item: "elB", site: siteKey("elB", [420, 775]) } }),
    { select: ["elL"] });
    app.setRoute("elbow");
    const elPts = () => store.item("elL").points;
    check(store.item("elL").route === "elbow" && JSON.stringify(elPts()) === "[[340,715],[380,715],[380,775],[420,775]]",
      "an elbow connector runs level, upright, level between the sides it's attached to", JSON.stringify(elPts()));
    store.update("B lower", (doc) => { findDeep(doc.pages[store.pageIndex].items, "elB").frame[1] += 20; });
    check(JSON.stringify(elPts()) === "[[340,715],[380,715],[380,795],[420,795]]", "and follows when a box moves", JSON.stringify(elPts()));
    store.select(["elL"]);
    await drag([380, 755], [400, 755]);
    check(near(store.item("elL").elbow, 0.75, 1e-6) && near(elPts()[1][0], 400, 1e-6) && near(elPts()[2][0], 400, 1e-6),
      "the handle on its middle stretch moves that stretch", JSON.stringify(elPts()));
    app.setRoute("straight");
    check(!store.item("elL").route && elPts().length === 2, "Straight makes it a straight line again", JSON.stringify(elPts()));
    store.select(["elA", "elB", "elL"]);
    await app.run("delete");

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
    // Arrow keys: a round step in the panels' units that follows the zoom, shown in the status
    // bar (Shift 10 steps, Option a tenth, Option+Shift resizes by one); a click there makes it 1 pt
    store.select([rect.id]);
    const unitsWas = app.prefs.units, zoomWas = canvas.zoom, frameWas = [...store.item(rect.id).frame];
    await app.savePrefs({ units: "cm" });
    const readout = document.querySelector(".nudge-step"), boxNow = () => store.item(rect.id).frame, cm = 72 / 2.54;
    canvas.setZoom(4);
    const shown400 = readout.textContent, pressed = readout.getAttribute("aria-pressed");
    key("ArrowRight");
    const by400 = boxNow()[0] - frameWas[0];
    canvas.setZoom(0.25);
    const shown25 = readout.textContent;
    key("ArrowRight", { shiftKey: true });
    const byShift = boxNow()[0] - frameWas[0] - by400;
    key("ArrowDown", { altKey: true });
    key("ArrowRight", { altKey: true, shiftKey: true });
    check(shown400 === "Arrows 0.01 cm" && pressed === "true" && near(by400, 0.01 * cm, 1e-6) && shown25 === "Arrows 0.2 cm"
      && near(byShift, 2 * cm, 1e-6) && near(boxNow()[1] - frameWas[1], 0.02 * cm, 1e-6) && near(boxNow()[2] - frameWas[2], 0.2 * cm, 1e-6),
    "arrow keys move a round step that follows the zoom, shown in the status bar (0.01 cm at 400%, 0.2 cm at 25%; Shift 10, Option a tenth, Option+Shift resizes)",
    `${shown400} ${pressed} ${by400}; ${shown25} ${byShift}; ${boxNow()} from ${frameWas}`);
    readout.click();
    await until(() => !app.prefs.nudge_zoom);
    const fixed = [readout.textContent, readout.getAttribute("aria-pressed"), app.menuChecks().toggleNudgeZoom].join();
    const x1 = boxNow()[0];
    key("ArrowRight");
    const by1 = boxNow()[0] - x1;
    key("ArrowRight", { shiftKey: true });
    const by10 = boxNow()[0] - x1 - by1;
    readout.click();
    await until(() => app.prefs.nudge_zoom);
    check(fixed === "Arrows 1 pt,false,false" && near(by1, 1, 1e-6) && near(by10, 10, 1e-6) && readout.getAttribute("aria-pressed") === "true"
      && app.menuChecks().toggleNudgeZoom, "a click there makes them 1 pt (10 with Shift) at any zoom, and another follows the zoom again",
    `${fixed}; ${by1} ${by10}; ${readout.getAttribute("aria-pressed")}`);
    store.update("Put the box back", (doc) => { findItem(doc, rect.id).frame = frameWas; });
    await app.savePrefs({ units: unitsWas });
    canvas.setZoom(zoomWas);
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
    // mosaic's own copy pastes as objects while it's the newest thing; anything copied
    // after it in another app wins
    store.select([pastedPic?.id].filter(Boolean));
    app.run("copy");
    const own = await pasteOne(null, () => app.run("paste"));
    check(own?.type === "picture" && own.asset === pastedPic?.asset, "mosaic's own copy pastes as objects");
    const newer = await pasteOne({ text: "Newer" }, () => app.run("paste"));
    check(newer?.textbox, "text copied in another app afterwards wins over mosaic's older copy");
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

    // Scrolling moves around the page even while it all fits (Fit page centres it); zoomed in
    // too, and Centre page (⌘⇧0) brings it back to the middle
    canvas.fit();
    const viewBox = canvas.stage.getBoundingClientRect();
    const pageCentred = () => {
      const [mx, my] = canvas.toScreen(store.page().width / 2, store.page().height / 2);
      return near(mx, viewBox.width / 2, 0.5) && near(my, viewBox.height / 2, 0.5);
    };
    const scroll = () => canvas.stage.dispatchEvent(new WheelEvent("wheel", { deltaX: 40, deltaY: 60, bubbles: true,
      cancelable: true, clientX: viewBox.left + 100, clientY: viewBox.top + 100 }));
    const fitted = pageCentred();
    scroll();
    check(fitted && !pageCentred(), "Fit page centres the page, and scrolling moves around it even while it all fits");
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
    // Outline Sides and Gaps. A rectangle's line goes all the way round it, so even unfilled it
    // has Outside, Inside and Both sides (what an outline drawn underneath shows with no fill);
    // Gaps show greyed out, with the reason, until the line is dashed or dotted
    const choicesOf = (label) => { const f = fieldByLabel(label); return (f?.choices || [...(f?.options || [])].map((o) => o.value)).join(); };
    const shownAs = (label) => fieldByLabel(label)?.value;
    const greyed = (label) => fieldByLabel(label)?.getAttribute("aria-disabled") === "true";
    const drawnPaths = () => [...(canvas.els.get(rect.id)?.g.querySelectorAll("path") || [])].filter((p) => !p.closest("clipPath"));
    check(choicesOf("Sides") === "outside,inside,both" && shownAs("Sides") === "both" && greyed("Gaps")
      && /For dashed and dotted lines/.test(fieldByLabel("Gaps")?.closest(".field")?.textContent || ""),
    "an unfilled rectangle offers Outside, Inside or Both sides, and Gaps greyed out for a solid line, saying why",
    `${choicesOf("Sides")} ${shownAs("Sides")} greyed ${greyed("Gaps")}`);
    store.update("Fill for the test", (doc) => { findItem(doc, rect.id).fill = { color: "#cfe3ff", opacity: 1 }; });
    await settle();
    check(shownAs("Sides") === "outside", "with a fill the same outline shows as Outside", shownAs("Sides"));
    // (Sides keeps the gaps half of the type: Outside's gaps were filled)
    await choose("Sides", "both");
    await settle();
    const layered = drawnPaths().map((p) => p.getAttribute("style") || "");
    check(store.item(rect.id).outline.type === "both_filled" && layered.length === 3 && layered[0].includes("fill:#cfe3ff")
      && layered[1].includes("stroke:#ffffff"), "Both sides of the line draws the outline over the fill, under the line",
      layered.join(" | "));
    // Inside: clipped to the shape, over the fill and under the line
    await choose("Sides", "inside");
    await settle();
    const insideG = canvas.els.get(rect.id)?.g;
    const drawnOrder = [...(insideG?.children || [])].filter((el) => el.tagName !== "defs");
    const clipRef = /clip-path:url\(#([^)]+)\)/.exec(drawnOrder[1]?.getAttribute("style") || "");
    check(store.item(rect.id).outline.type === "inside" && drawnOrder.map((el) => el.tagName).join() === "path,g,path"
      && (drawnOrder[0].getAttribute("style") || "").includes("fill:#cfe3ff") && clipRef && insideG.querySelector(`clipPath[id="${clipRef[1]}"]`),
      "Inside keeps the outline to the shape: clipped, over the fill, under the line", insideG?.innerHTML.slice(0, 300));
    // A dashed line adds Gaps, keeping the sides chosen
    await choose("Dash", "dash");
    await settle();
    check(choicesOf("Gaps") === "filled,empty" && !greyed("Gaps") && shownAs("Sides") === "inside" && shownAs("Gaps") === "filled",
      "a dashed line makes Gaps filled or empty choosable, keeping the sides chosen", `${choicesOf("Gaps")} ${shownAs("Sides")} ${shownAs("Gaps")}`);
    await choose("Gaps", "empty");
    await settle();
    check(store.item(rect.id).outline.type === "inside_gaps" && shownAs("Sides") === "inside",
      "Gaps empty changes only the gaps", store.item(rect.id).outline.type);
    // Both sides, gaps filled outlines the line drawn whole
    await choose("Sides", "both");
    await choose("Gaps", "filled");
    await settle();
    const gapsFilled = drawnPaths();
    const subpaths = (p) => ((p?.getAttribute("d") || "").match(/M/g) || []).length;
    check(store.item(rect.id).outline.type === "both_filled" && gapsFilled.length === 3
      && (gapsFilled[1].getAttribute("style") || "").includes("stroke:#ffffff") && subpaths(gapsFilled[1]) === 1 && subpaths(gapsFilled[2]) > 1,
      "Both sides, gaps filled draws one unbroken outline between the fill and the dashes",
      gapsFilled.map((p) => `${subpaths(p)} ${p.getAttribute("style")}`).join(" | "));
    // With no fill, Outside keeps off the inside of the line: clipped to everything else
    store.update("Unfill", (doc) => { findItem(doc, rect.id).fill = null; });
    await settle();
    await choose("Sides", "outside");
    await settle();
    const outsideClip = canvas.els.get(rect.id)?.g.querySelector("clipPath path");
    check(store.item(rect.id).outline.type === "outside_only" && shownAs("Gaps") === "filled" && outsideClip?.getAttribute("clip-rule") === "evenodd",
      "with no fill, Outside keeps the outline off the shape's inside", `${store.item(rect.id).outline.type} ${outsideClip?.outerHTML.slice(0, 120)}`);
    store.update("Outline type back", (doc) => { findItem(doc, rect.id).outline.type = "outside"; });
    await choose("Dash", "solid");
    // A line has no inside: its Sides are its left and right, going from its start to its end
    const arrowWas = JSON.parse(JSON.stringify(store.item(arrow.id)));
    store.update("Dashed outlined arrow for the test", (doc) => {
      const a = findItem(doc, arrow.id);
      a.stroke = { ...a.stroke, dash: "dash" };
      a.outline = { color: "#ffffff", width: 1, opacity: 1 };
    });
    store.select([arrow.id]);
    await settle();
    check(choicesOf("Sides") === "left,right,both" && shownAs("Sides") === "both" && choicesOf("Gaps") === "filled,empty"
      && shownAs("Gaps") === "empty", "a dashed line offers Left side, Right side or Both sides, and gaps filled or empty",
    `${choicesOf("Sides")} ${shownAs("Sides")} | ${choicesOf("Gaps")} ${shownAs("Gaps")}`);
    await choose("Sides", "left");
    await settle();
    const leftType = store.item(arrow.id).outline.type, oneSide = canvas.els.get(arrow.id)?.g.querySelector("clipPath");
    await choose("Gaps", "filled");
    await settle();
    check(leftType === "left_gaps" && oneSide && store.item(arrow.id).outline.type === "left",
      "Left side keeps the outline to one side of the line, with its gaps choice", `${leftType} ${!!oneSide} ${store.item(arrow.id).outline.type}`);
    store.update("Arrow back", (doc) => {
      const a = findItem(doc, arrow.id);
      a.stroke = arrowWas.stroke;
      if ("outline" in arrowWas) a.outline = arrowWas.outline;
      else delete a.outline;
    });

    // Distances on hover: Option held with the rectangle selected, pointing off the page, shows
    // its distances to the page's edges; letting go of Option hides them
    store.select([rect.id]);
    key("Alt");
    pointer("pointermove", screenOf(-20, -20), { buttons: 0, altKey: true });
    const dLabels = [...canvas.overlay.querySelectorAll(".distance-text")].map((t) => t.textContent);
    const rBox = itemBBox(store.item(rect.id));
    check(dLabels.length === 4 && dLabels.includes(lengthText(rBox[0])), "Option shows the selection's distances to the page's edges",
      dLabels.join(", "));
    canvas.stage.dispatchEvent(new KeyboardEvent("keyup", { key: "Alt", bubbles: true }));
    check(!canvas.overlay.querySelector(".distance"), "and letting go of Option hides them");

    // Duplicate as in PowerPoint: move the copy, and the next Duplicate repeats that offset
    store.select([rect.id]);
    await app.run("duplicate");
    const dupA = store.selected()[0], rectAt = store.item(rect.id).frame;
    check(near(dupA.frame[0] - rectAt[0], 10, 1e-6) && near(dupA.frame[1] - rectAt[1], 10, 1e-6),
      "Duplicate puts the copy 10 pt down and right", JSON.stringify(dupA.frame));
    store.update("Move the copy", (doc) => { const d = findItem(doc, dupA.id); d.frame[0] += 30; d.frame[1] -= 10; });
    await app.run("duplicate");
    const dupB = store.selected()[0], dupOffset = [dupB.frame[0] - store.item(dupA.id).frame[0], dupB.frame[1] - store.item(dupA.id).frame[1]];
    check(near(dupOffset[0], 40, 1e-6) && near(dupOffset[1], 0, 1e-6), "once the copy is moved, Duplicate repeats that offset",
      JSON.stringify(dupOffset));
    // Transform again (⌘⇧D): the last nudge, typed turn and resize, each done again
    app.nudge(5, 0);
    const nudgedX = store.item(dupB.id).frame[0];
    await app.run("transformAgain");
    check(near(store.item(dupB.id).frame[0] - nudgedX, 5, 1e-6), "Transform again repeats the last move", `${store.item(dupB.id).frame[0] - nudgedX}`);
    await choose("Rotation", "15");
    await app.run("transformAgain");
    check(near(store.item(dupB.id).rot, 30, 1e-6), "and the last turn", `${store.item(dupB.id).rot}`);
    store.update("Unturn", (doc) => { findItem(doc, dupB.id).rot = 0; });
    const beforeResize = store.item(dupB.id).frame.slice();
    app.noteTransform({ kind: "resize", sx: 2, sy: 1, anchor: [0, 0] });
    await app.run("transformAgain");
    const afterResize = store.item(dupB.id).frame;
    check(near(afterResize[2], beforeResize[2] * 2, 1e-6) && near(afterResize[0], beforeResize[0], 1e-6) && near(afterResize[3], beforeResize[3], 1e-6),
      "and the last resize, keeping the same side still", `${JSON.stringify(beforeResize)} -> ${JSON.stringify(afterResize)}`);
    // Copy style / Paste style (⌘⇧C / ⌘⇧V): everything the target can take
    const jsonOf = (v) => JSON.stringify(v ?? null);
    store.update("Style the copies", (doc) => {
      for (const id of [dupA.id, dupB.id]) {
        const d = findItem(doc, id);
        d.stroke = { color: "#d62728", width: 3, dash: "dash", cap: "round", join: "round", opacity: 1 };
        d.fill = { color: "#ffd166", opacity: 1 };
        delete d.outline;
      }
    });
    store.select([rect.id]);
    await app.run("copyStyle");
    store.select([dupB.id]);
    await app.run("pasteStyle");
    const styleFrom = store.item(rect.id), styleTo = store.item(dupB.id);
    check(jsonOf(styleTo.stroke) === jsonOf(styleFrom.stroke) && jsonOf(styleTo.outline) === jsonOf(styleFrom.outline)
      && jsonOf(styleTo.fill) === jsonOf(styleFrom.fill), "Paste style gives another shape the line, fill and outline copied",
    `${jsonOf(styleTo.stroke)} ${jsonOf(styleTo.fill)}`);
    // From a line: its line and outline, and the shape keeps its fill
    store.update("Fill it again", (doc) => { findItem(doc, dupB.id).fill = { color: "#ffd166", opacity: 1 }; });
    store.select([arrow.id]);
    await app.run("copyStyle");
    store.select([dupB.id]);
    await app.run("pasteStyle");
    check(jsonOf(store.item(dupB.id).stroke) === jsonOf(store.item(arrow.id).stroke) && store.item(dupB.id).fill?.color === "#ffd166",
      "a line's style gives a shape its line and leaves its fill", jsonOf(store.item(dupB.id).stroke));
    // The Format Painter: click it, then the object to paint
    const painterBtn = document.querySelector('#rpanel-home [data-cmd="formatPainter"]');
    const centreOf = (id) => { const b = itemBBox(store.item(id)); return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]; };
    store.select([rect.id]);
    painterBtn.click();
    check(canvas.tool === "painter" && painterBtn.getAttribute("aria-pressed") === "true",
      "the Format Painter picks up the selected object's style and waits for a click", canvas.tool);
    await drag(centreOf(dupA.id), centreOf(dupA.id));
    check(jsonOf(store.item(dupA.id).stroke) === jsonOf(store.item(rect.id).stroke) && !store.item(dupA.id).fill && canvas.tool === "select",
      "a click paints it on, and the painter puts itself away", `${jsonOf(store.item(dupA.id).stroke)} ${canvas.tool}`);
    // Double-clicked, it keeps painting until Escape
    store.select([arrow.id]);
    painterBtn.click();
    painterBtn.click();
    painterBtn.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    await drag(centreOf(dupB.id), centreOf(dupB.id));
    check(canvas.tool === "painter" && jsonOf(store.item(dupB.id).stroke) === jsonOf(store.item(arrow.id).stroke),
      "double-clicked, the Format Painter keeps painting", canvas.tool);
    key("Escape");
    check(canvas.tool === "select" && painterBtn.getAttribute("aria-pressed") === "false", "and Escape puts it away", canvas.tool);
    // Match size: the others take the key object's height (or width), or with no key the tallest's
    // (widest's), keeping their proportions
    store.update("Bigger copy", (doc) => { const d = findItem(doc, dupB.id); d.frame[2] *= 2; d.frame[3] *= 3; });
    const tallWas = store.item(dupB.id).frame.slice(), smallWas = store.item(rect.id).frame.slice();
    const tallH = () => { const b = itemBBox(store.item(dupB.id)); return b[3] - b[1]; };
    const heightWas = tallH();
    store.select([rect.id, dupB.id]);
    document.querySelector('#rpanel-arrange [data-cmd="sameHeight"]').click();
    const matched = store.item(rect.id).frame, mb = itemBBox(store.item(rect.id));
    check(near(mb[3] - mb[1], heightWas, 1e-6) && near(matched[2] / matched[3], smallWas[2] / smallWas[3], 1e-6)
      && near(matched[0], smallWas[0], 1e-6) && near(matched[1], smallWas[1], 1e-6)
      && JSON.stringify(store.item(dupB.id).frame) === JSON.stringify(tallWas),
    "Same height with no key object makes the others as tall as the tallest, keeping their proportions and corner",
    `${JSON.stringify(smallWas)} -> ${JSON.stringify(matched)} (tallest ${JSON.stringify(tallWas)})`);
    // Fonts: each font the text uses, and Replace swaps one everywhere
    store.update("Arial text for the test", (doc) => doc.pages[store.pageIndex].items.push({ id: "fonttest", type: "shape", geom: "rect",
      textbox: true, frame: [50, 50, 60, 12], rot: 0, stroke: null, fill: null,
      text: { paragraphs: [{ align: "l", runs: [{ t: "Arial text", font: "Arial", size: 6, bold: false, italic: false, color: "#000000" }] }],
        insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" } }));
    await app.run("fonts");
    const fontsDlg = [...document.querySelectorAll("dialog[open]")].pop();
    const arialRow = [...fontsDlg.querySelectorAll("tbody tr")].find((tr) => tr.querySelector(".font-name")?.textContent === "Arial");
    check(arialRow && /1 text object/.test(arialRow.textContent), "the Fonts dialog lists each font and the text using it",
      fontsDlg.querySelector("tbody")?.textContent);
    arialRow.querySelector("input").value = "Helvetica";
    arialRow.querySelector("button").click();
    const fontNow = store.item("fonttest").text.paragraphs[0].runs[0].font;
    check(fontNow === "Helvetica" && ![...fontsDlg.querySelectorAll(".font-name")].some((el) => el.textContent === "Arial"),
      "Replace swaps the font everywhere, and the list follows", fontNow);
    fontsDlg.close();
    store.select([dupA.id, dupB.id, "fonttest"]);
    await app.run("delete");

    // Check: the thinnest line, flagged below 0.25 pt, and the page's size against a journal
    // chosen there
    store.update("Thin line for the test", (doc) => doc.pages[store.pageIndex].items.push({ id: "thintest", type: "line",
      points: [[40, 40], [90, 40]], arrow_start: null, arrow_end: null, stroke: { color: "#000000", width: 0.1 } }));
    const journalWas = app.prefs.check_journal || "";
    await app.run("preflight");
    const checkDlg = [...document.querySelectorAll("dialog[open]")].pop();
    const checkResults = checkDlg.querySelector(".preflight-results");
    check(/Thinnest line: 0\.1 pt/.test(checkResults.textContent) && /its line is 0\.10 pt \(below 0\.25 pt\)/.test(checkResults.textContent),
      "Check gives the thinnest line and flags a line thinner than 0.25 pt", checkResults.textContent);
    const journalPick = checkDlg.querySelector("select");
    check(groupsOf(journalPick).join() === PUBLISHER_GROUPS && optionsIn(journalPick, "Wiley").join() === "New Phytologist,The Plant Journal",
      "Check's journal list groups the journals by publisher", groupsOf(journalPick).join());
    journalPick.value = "Nature";
    journalPick.dispatchEvent(new Event("change"));
    await until(() => /Nature figures/.test(checkResults.textContent) && app.prefs.check_journal === "Nature");   // (two requests)
    check(/Nature figures/.test(checkResults.textContent) && app.prefs.check_journal === "Nature",
      "and compares the page's size with the journal chosen there", checkResults.textContent);
    checkDlg.close();
    await app.savePrefs({ check_journal: journalWas });
    store.select(["thintest"]);
    await app.run("delete");

    // Swatches: a palette adds named colours; one picked for a line stays linked to it
    store.select([rect.id]);
    app.addPalette([["Orange", "#e69f00"], ["Blue", "#0072b2"]], "Test");
    const orangeSw = (store.doc.swatches || []).find((x) => x.name === "Orange");
    check(orangeSw && store.doc.swatches.some((x) => x.name === "Blue"), "a palette adds its colours to the figure as swatches",
      JSON.stringify(store.doc.swatches));
    inspector.render();
    document.querySelector('#inspector [aria-label="Swatches for Line colour"]').click();
    [...document.querySelectorAll(".context-menu .menu-item")].find((b) => b.textContent.includes("Orange"))?.click();
    await settle();
    inspector.render();   // a hidden window draws the panel on a late frame
    check(store.item(rect.id).stroke.color === "#e69f00" && store.item(rect.id).stroke.swatch === orangeSw.id
      && document.querySelector("#inspector").textContent.includes("Swatch: Orange"),
    "picking a swatch colours the line and links it, and the panel says which", JSON.stringify(store.item(rect.id).stroke));
    // Changing the swatch in the Swatches dialog recolours what's linked to it
    await app.run("swatches");
    const swatchDlg = [...document.querySelectorAll("dialog[open]")].pop();
    const orangePicker = swatchDlg.querySelector('input[type="color"][aria-label="Orange: colour"]');
    orangePicker.value = "#ff0000";
    orangePicker.dispatchEvent(new Event("change", { bubbles: true }));
    check(store.item(rect.id).stroke.color === "#ff0000" && (store.doc.swatches.find((x) => x.id === orangeSw.id) || {}).color === "#ff0000",
      "changing a swatch recolours everything linked to it", store.item(rect.id).stroke.color);
    // The figure's swatches saved as a palette in your library
    swatchDlg.querySelector('input[aria-label="Name for a palette in your library"]').value = "Self-test palette";
    [...swatchDlg.querySelectorAll("button")].find((b) => b.textContent === "Save as a palette").click();
    await until(() => (app.prefs.swatch_library || []).some((p) => p.name === "Self-test palette"));
    check((app.prefs.swatch_library || []).some((p) => p.name === "Self-test palette" && p.colours.length === store.doc.swatches.length),
      "the figure's swatches can be saved as a palette in your library", JSON.stringify(app.prefs.swatch_library));
    swatchDlg.close();
    await app.deletePalette("Self-test palette");
    // A colour typed by hand drops the link
    inspector.render();
    const lineHex = document.querySelector('#inspector input[aria-label="Line colour hex code"]');
    lineHex.value = "#123456";
    lineHex.dispatchEvent(new Event("change", { bubbles: true }));
    check(store.item(rect.id).stroke.color === "#123456" && !store.item(rect.id).stroke.swatch, "typing a colour by hand drops the link",
      JSON.stringify(store.item(rect.id).stroke));
    store.update("Black line again", (doc) => { findItem(doc, rect.id).stroke.color = "#000000"; });

    // Text styles: one made from a text and given to another, which follows it except where changed
    const styledText = (id, x, size, bold) => ({ id, type: "shape", geom: "rect", textbox: true, frame: [x, 200, 50, 10], rot: 0,
      stroke: null, fill: null, text: { paragraphs: [{ align: "l", runs: [{ t: id, font: "Helvetica", size, bold, italic: false,
        color: "#000000" }] }], insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" } });
    store.update("Texts for styles", (doc) => doc.pages[store.pageIndex].items.push(styledText("tsA", 40, 7, false), styledText("tsB", 120, 11, true)));
    store.select(["tsA"]);
    const making = app.newTextStyle();
    await settle();
    const promptDlg = [...document.querySelectorAll("dialog[open]")].pop();
    promptDlg.querySelector("input").value = "Note";
    [...promptDlg.querySelectorAll("button")].find((b) => b.textContent === "OK").click();
    await making;
    const noteStyle = (store.doc.text_styles || []).find((x) => x.name === "Note");
    check(noteStyle && noteStyle.size === 7 && store.item("tsA").text.paragraphs[0].style === noteStyle.id,
      "New style from this text makes a style with its format, and links the text", JSON.stringify(noteStyle));
    store.select(["tsB"]);
    await choose("Text style", noteStyle.id);
    const runOfB = () => store.item("tsB").text.paragraphs[0].runs[0];
    check(runOfB().size === 7 && !runOfB().bold && store.item("tsB").text.paragraphs[0].style === noteStyle.id,
      "choosing a text style gives the text its format", JSON.stringify(runOfB()));
    store.update("Bigger B", (doc) => { findItem(doc, "tsB").text.paragraphs[0].runs[0].size = 9; });
    store.update("Bold A", (doc) => { findItem(doc, "tsA").text.paragraphs[0].runs[0].bold = true; });
    app.redefineTextStyle(noteStyle.id, store.item("tsA"));
    check(runOfB().bold === true && runOfB().size === 9 && (store.doc.text_styles.find((x) => x.id === noteStyle.id) || {}).bold === true,
      "updating the style changes the text using it, keeping what was changed by hand", JSON.stringify(runOfB()));
    store.select(["tsB"]);
    inspector.render();
    check(document.querySelector("#inspector").textContent.includes("This text differs from Note"),
      "the Text tab says when text differs from its style");
    app.clearTextChanges();
    check(runOfB().size === 7, "Clear changes puts it back to the style", JSON.stringify(runOfB()));
    // A style called Panel label is used for new labels
    app.renameTextStyle(noteStyle.id, "Panel label");
    canvas.setTool("label");
    await drag([330, 60], [330, 60]);
    const newLabel = store.selected()[0];
    check(newLabel?.text?.paragraphs[0].style === noteStyle.id && newLabel.text.paragraphs[0].runs[0].size === 7,
      "new panel labels take the style called Panel label", JSON.stringify(newLabel?.text?.paragraphs[0]));
    app.deleteTextStyle(noteStyle.id);
    check(!store.item("tsA").text.paragraphs[0].style && store.item("tsA").text.paragraphs[0].runs[0].bold === true,
      "deleting a style keeps the text's format", JSON.stringify(store.item("tsA").text.paragraphs[0]));
    // Superscript while typing (⌘⇧=), and a symbol inserted at the cursor from the Text tab
    store.update("Text for scripts", (doc) => doc.pages[store.pageIndex].items.push(styledText("scr", 40, 7, false)));
    store.select(["scr"]);
    canvas.startEdit("scr");
    await settle();
    const edRange = document.createRange();
    edRange.selectNodeContents(canvas.editor);
    getSelection().removeAllRanges();
    getSelection().addRange(edRange);
    canvas.editor.dispatchEvent(new KeyboardEvent("keydown", { key: "+", shiftKey: true, metaKey: true, ctrlKey: true, bubbles: true, cancelable: true }));
    const endRange = document.createRange();
    endRange.selectNodeContents(canvas.editor);
    endRange.collapse(false);
    getSelection().removeAllRanges();
    getSelection().addRange(endRange);
    inspector.render();
    const microBtn = document.querySelector('#inspector button[aria-label="Insert µ, micro"]');
    microBtn?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
    microBtn?.click();
    canvas.commitEdit();
    await settle();
    const scrRuns = store.item("scr").text.paragraphs[0].runs;
    check(scrRuns.some((r) => r.baseline === 0.3 && r.t.includes("scr")) && scrRuns.map((r) => r.t).join("").endsWith("µ"),
      "⌘⇧= makes the selected text superscript, and a symbol goes in at the cursor",
      scrRuns.map((r) => `${r.t}:${r.baseline ?? 0}`).join(" | "));
    store.select(["tsA", "tsB", newLabel.id, "scr"]);
    await app.run("delete");

    // Isolation mode: double-click a group to work on its parts, the rest faded; Escape leaves
    const isoBox = (id, x) => ({ id, type: "shape", geom: "rect", frame: [x, 420, 40, 30], rot: 0, flip_h: false, flip_v: false,
      stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 }, fill: { color: "#cfe3ff", opacity: 1 } });
    store.update("Boxes to group", (doc) => doc.pages[store.pageIndex].items.push(isoBox("isoA", 60), isoBox("isoB", 130)));
    store.select(["isoA", "isoB"]);
    await app.run("group");
    const isoGroup = store.selected()[0];
    const dblAt = (pt) => { const [sx, sy] = screenOf(...pt); canvas.stage.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: sx, clientY: sy })); };
    dblAt([80, 435]);
    await settle();
    const outsideFaded = canvas.els.get(rect.id)?.g.classList.contains("outside-scope");
    check(store.scope.join() === isoGroup.id && store.selection.length === 0 && !document.querySelector(".scope-note").hidden && outsideFaded,
      "double-clicking a group edits inside it, with the rest of the page faded and a note", `${store.scope} ${outsideFaded}`);
    await drag([150, 435], [150, 435]);
    check(store.selection.join() === "isoB", "a click inside picks one part", store.selection.join());
    app.nudge(10, 0);
    check(store.item("isoB").frame[0] === 140 && store.item(isoGroup.id)?.items.length === 2, "a part moves on its own, still in its group",
      JSON.stringify(store.item("isoB").frame));
    canvas.setTool("rect");
    await drag([210, 425], [240, 445], { metaKey: true, ctrlKey: true });
    check(store.item(isoGroup.id).items.length === 3, "something drawn inside the group goes into it", `${store.item(isoGroup.id).items.length}`);
    await app.run("selectAll");
    check(store.selection.length === 3 && store.selection.every((id) => store.item(isoGroup.id).items.some((c) => c.id === id)),
      "Select all picks the group's parts only", store.selection.join());
    key("Escape");
    key("Escape");
    check(!store.scope.length && store.selection.join() === isoGroup.id && !canvas.els.get(rect.id)?.g.classList.contains("outside-scope"),
      "Escape (with nothing selected) leaves the group, selecting it", `${store.scope} ${store.selection}`);
    key("Enter");
    check(store.scope.join() === isoGroup.id, "Enter on a selected group edits inside it too", store.scope.join());
    document.querySelector(".scope-note button").click();
    check(!store.scope.length && document.querySelector(".scope-note").hidden, "the note's Leave group button leaves it", store.scope.join());
    store.select([isoGroup.id]);
    await app.run("delete");

    // Crop to shape: a picture shown only inside a shape fitted to its frame
    store.select([pics[0].id]);
    await choose("Crop to shape", "ellipse");
    const clipped = () => canvas.els.get(pics[0].id)?.g.querySelector(":scope > g")?.getAttribute("clip-path");   // (round the picture's svg)
    await until(clipped, 4000);
    const picClip = clipped() || "";
    const picClipPath = document.querySelector(`[id="${picClip.slice(5, -1)}"] path`)?.getAttribute("d") || "";
    check(store.item(pics[0].id).mask?.geom === "ellipse" && picClip && picClipPath.includes("C"),
      "Crop to shape crops the picture to an ellipse, on the page too",
      `geom=${store.item(pics[0].id).mask?.geom} clip=${picClip} d=${picClipPath.slice(0, 30)} sel=${store.selection.join()}`);
    await choose("Crop to shape", "");
    check(!store.item(pics[0].id).mask && !canvas.els.get(pics[0].id)?.g.querySelector("svg")?.getAttribute("clip-path"), "and None takes the shape away");
    // Clipping masks: the top shape clips what's under it (⌘7), and isn't drawn itself
    const maskPart = (id, geom, frame) => ({ id, type: "shape", geom, frame, rot: 0, flip_h: false, flip_v: false,
      stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 }, fill: { color: "#ffd166", opacity: 1 } });
    store.update("Mask parts", (doc) => doc.pages[store.pageIndex].items.push(maskPart("mkRect", "rect", [60, 480, 120, 60]),
      maskPart("mkOval", "ellipse", [80, 485, 80, 50])));
    store.select(["mkRect", "mkOval"]);
    key("7", { metaKey: true, ctrlKey: true });
    await settle();
    const clipGroup = store.selected()[0];
    await until(() => canvas.els.get(clipGroup?.id)?.g.getAttribute("clip-path"), 4000);
    check(clipGroup?.clip && clipGroup.items.map((c) => c.id).join() === "mkRect,mkOval"
      && canvas.els.get(clipGroup.id)?.g.getAttribute("clip-path") && canvas.els.get("mkOval")?.g.style.display === "none",
    "⌘7 makes a clipping mask: the top shape clips the rest, and isn't drawn", JSON.stringify(clipGroup));
    // Inside it, a click where the rectangle shows picks the rectangle, not the clipping shape over it
    canvas.enterGroup(clipGroup.id);
    await drag([120, 510], [120, 510]);
    check(store.selection.join() === "mkRect", "inside a clipping mask, a click picks what's clipped; the shape only by its edge",
      store.selection.join());
    key("Escape");
    key("Escape");
    store.select([clipGroup.id]);
    await app.run("releaseClipMask");
    check(store.items().some((it) => it.id === "mkOval") && !store.items().some((it) => it.id === clipGroup.id)
      && canvas.els.get("mkOval")?.g.style.display !== "none", "Release separates the shape and what it clipped", store.selection.join());
    await objectsListChecks(app);
    await selectionChecks(app);
    // (on documents of their own: this one comes back as it was, with its own recovery copies, and
    // theirs go, so the recovery offer later lists only its own test copies)
    const keepDoc = JSON.parse(JSON.stringify(store.doc)), keepPage = store.pageIndex, keepKey = store.autosaveKey;
    const keepDirty = store.dirty, copiesBefore = new Set((await rpc("autosaved", keepKey)).map((s) => s.path));
    const slidesFrom = performance.now();
    await slidesChecks(app, ppt);
    info.slidesMs = Math.round(performance.now() - slidesFrom);
    await linkedFileChecks(app);
    await problemReportChecks(app);
    await myJournalsChecks(app);
    await findJournalChecks(app);
    await dialogDragChecks(app);
    await updateChecks(app);
    await windowChecks(app, out);
    await pageSizeChecks(app);
    await visionChecks(app);
    await exportNoteChecks(app, out);
    if (out) await exportProgressChecks(app, out);
    await rulerGuideChecks(app);
    await pictureMenuChecks(app);
    await zoomShapeChecks(app);
    await scaleBarChecks(app);
    await pasteboardChecks(app);
    await offPageChecks(app);
    if (out) await renameChecks(app, out);
    if (out) await keepingChecks(app, out);
    await pageDragChecks(app);
    await pageSelectChecks(app);
    await clickThroughChecks(app);
    await textRibbonChecks(app);
    await journalLabelChecks(app);
    await journalCheckChecks(app);
    await dangerousModeChecks(app);
    await refreshAllChecks(app);
    await arrangeTabChecks(app);
    await sizeStripChecks(app);
    await angleChecks(app);
    await editAnchorChecks();
    await dupTypeChecks(app);
    await cropChecks(app);
    await linkChecks(app);
    await turnFlipChecks(app);
    await dashSpacingChecks(app);
    await multiLookChecks(app);
    await freeformChecks(app);
    await areaGapChecks(app);
    store.setDoc(keepDoc);
    store.autosaveKey = keepKey;
    store.dirty = keepDirty;
    const strays = (await rpc("autosaved", keepKey)).filter((s) => !copiesBefore.has(s.path));
    if (strays.length) await rpc("delete_autosaves", strays.map((s) => s.path), keepKey);
    store.setPage(keepPage);
    canvas.fit();
    await settle();
    // Pathfinder: Unite joins overlapping shapes into one freeform shape, in the top one's place
    store.update("Shapes to combine", (doc) => doc.pages[store.pageIndex].items.push(maskPart("pfA", "rect", [60, 560, 60, 40]),
      maskPart("pfB", "ellipse", [90, 570, 60, 40])));
    store.select(["pfA", "pfB"]);
    document.querySelector('#rpanel-combine [data-cmd="unite"]').click();
    await until(() => store.selected()[0]?.geom === "custom", 4000);
    const united = store.selected()[0];
    check(united?.geom === "custom" && !store.item("pfA") && !store.item("pfB") && near(united.frame[2], 90, 0.01)
      && (united.path?.subpaths?.[0]?.cmds || []).some((c) => c[0] === "C"),
    "Unite joins the shapes into one freeform shape, its curves kept", JSON.stringify(united?.frame));
    await app.run("undo");
    check(store.item("pfA") && store.item("pfB") && !store.item(united.id), "and Undo brings back the shapes");
    store.select(["mkRect", "mkOval", "pfA", "pfB"]);
    await app.run("delete");

    // Scale bars: a picture given a scale, and a bar that follows its size, crop and place
    const sbWas = JSON.parse(JSON.stringify(store.item(pics[0].id)));
    store.select([pics[0].id]);
    inspector.render();
    const scaleLabel = [...document.querySelectorAll("#inspector label")].find((l) => /^(Size of one pixel|Length of one point of the original)$/.test(l.textContent));
    const scaleInput = scaleLabel && document.getElementById(scaleLabel.htmlFor);
    scaleInput.value = "2";
    scaleInput.dispatchEvent(new Event("change", { bubbles: true }));
    const sbPic = () => store.item(pics[0].id), sbAsset = store.doc.assets[sbPic().asset];
    check(sbPic().scale?.unit === "µm" && sbPic().scale.how === "typed", "typing a size gives the picture a scale", JSON.stringify(sbPic().scale));
    document.querySelector('#rpanel-figure [data-cmd="addScaleBar"]').click();
    const sbar = store.selected()[0], sbId = sbar?.id;
    const sbW = () => store.item(sbId).frame[2], sbWant = () => (store.item(sbId).length / sbPic().scale.per_pt) * pageScale(sbPic(), sbAsset);
    check(sbar?.type === "scalebar" && near(sbW(), sbWant(), 1e-6)
      && near(sbar.frame[0] + sbar.frame[2], sbPic().frame[0] + sbPic().frame[2] + sbar.anchor.dx, 1e-6),
    "Add scale bar puts a bar a round length long just inside the picture's corner", JSON.stringify(sbar));
    const w0 = sbW();
    store.update("Wider picture", (doc) => { const pp = findItem(doc, pics[0].id); pp.frame[2] *= 2; pp.frame[3] *= 2; });
    const sbF = () => store.item(sbId).frame;
    check(near(sbW(), w0 * 2, 1e-6) && near(sbF()[0] + sbF()[2], sbPic().frame[0] + sbPic().frame[2] + sbar.anchor.dx, 1e-6),
      "the bar's length follows the picture's size, and it keeps its corner", `${w0} -> ${sbW()}`);
    store.update("Crop it", (doc) => { findItem(doc, pics[0].id).crop = [0.25, 0, 0, 0]; });
    check(near(sbW(), (w0 * 2) / 0.75, 1e-6), "and the picture's crop", `${sbW()}`);
    store.select([sbId]);
    app.nudge(-10, 0);
    const sbX = sbF()[0];
    store.update("Move the picture", (doc) => { findItem(doc, pics[0].id).frame[0] += 20; });
    check(near(sbF()[0], sbX + 20, 1e-6), "a bar stays where it was put on its picture, and goes with it", `${sbX} -> ${sbF()[0]}`);
    store.select([pics[0].id, sbId]);
    app.nudge(5, 0);
    check(near(sbF()[0], sbX + 25, 1e-6), "moved together with its picture, a bar moves once", `${sbX + 20} -> ${sbF()[0]}`);
    // Measure: a line drawn along something of known length sets the scale
    canvas.startMeasure(pics[0].id);
    const mf = sbPic().frame;
    await drag([mf[0] + 10, mf[1] + 10], [mf[0] + 110, mf[1] + 10]);
    await until(() => [...document.querySelectorAll("dialog[open] input")].length);
    const measureDlg = [...document.querySelectorAll("dialog[open]")].pop();
    measureDlg.querySelector("input").value = "50 µm";
    [...measureDlg.querySelectorAll("button")].find((b) => b.textContent === "OK").click();
    await until(() => sbPic().scale?.how === "measured");
    check(sbPic().scale?.how === "measured" && near(sbPic().scale.per_pt, 50 / (100 / pageScale(sbPic(), sbAsset)), 1e-6),
      "Measure: a 100 pt line said to be 50 µm sets the scale", JSON.stringify(sbPic().scale));
    store.update("Picture back", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      items.splice(items.findIndex((i) => i.id === pics[0].id), 1, sbWas);
      items.splice(items.findIndex((i) => i.id === sbId), 1);
    }, { select: [] });

    // Zoom insets: a box dragged on a picture; the area enlarged beside it, joined by two lines
    store.select([pics[0].id]);
    document.querySelector('#rpanel-figure [data-cmd="zoomInset"]').click();
    const zp = store.item(pics[0].id).frame, zcrop = store.item(pics[0].id).crop || [0, 0, 0, 0];
    const zBox = [zp[0] + zp[2] * 0.2, zp[1] + zp[3] * 0.3, zp[2] * 0.25, zp[3] * 0.2];
    check(canvas.tool === "zoom", "Zoom inset waits for a box to be dragged on a picture", canvas.tool);
    await drag([zBox[0], zBox[1]], [zBox[0] + zBox[2], zBox[1] + zBox[3]]);
    const zAll = () => store.items();
    const zBoxItem = () => zAll().find((it) => it.zoom?.picture === pics[0].id);
    const zInset = () => zAll().find((it) => it.inset?.box === zBoxItem()?.id);
    const zLines = () => zAll().filter((it) => it.zoomline?.box === zBoxItem()?.id);
    const cropOf = () => zInset()?.crop || [];
    const wantCrop = (b, f) => [zcrop[0] + (b[0] - f[0]) / f[2] * (1 - zcrop[0] - zcrop[2]), zcrop[1] + (b[1] - f[1]) / f[3] * (1 - zcrop[1] - zcrop[3])];
    check(zBoxItem() && zInset() && zLines().length === 2 && near(cropOf()[0], wantCrop(zBoxItem().frame, zp)[0], 1e-6)
      && near(cropOf()[1], wantCrop(zBoxItem().frame, zp)[1], 1e-6)
      && near(zInset().frame[3] / zInset().frame[2], zBoxItem().frame[3] / zBoxItem().frame[2], 1e-6)
      && zLines().every((l) => l.points.length === 2),
    "dragging a box makes the box, the area enlarged beside the picture and two lines joining them",
    `${JSON.stringify(cropOf())} ${JSON.stringify(zBoxItem()?.frame)}`);
    // Moving the box shows another area; moving the picture takes the box along
    store.select([zBoxItem().id]);
    app.nudge(10, 0);
    check(near(cropOf()[0], wantCrop(zBoxItem().frame, zp)[0], 1e-6), "moving the box changes the area shown in the inset", JSON.stringify(cropOf()));
    const cropBefore = cropOf().slice(), boxXBefore = zBoxItem().frame[0];
    store.update("Move the picture", (doc) => { findItem(doc, pics[0].id).frame[0] += 30; });
    check(near(zBoxItem().frame[0], boxXBefore + 30, 1e-6) && near(cropOf()[0], cropBefore[0], 1e-6),
      "moving the picture takes its box along, so the inset shows the same area", `${zBoxItem().frame[0]} ${JSON.stringify(cropOf())}`);
    // Significance brackets: drag across bars for one; its label; several stacked in tidy levels
    document.querySelector('#rpanel-figure [data-cmd="toolSigBracket"]').click();
    await drag([300, 400], [360, 402], { metaKey: true, ctrlKey: true });
    const brA = store.selected()[0];
    check(brA?.type === "bracket" && brA.dir === "up" && near(brA.frame[2], 60, 0.01) && near(brA.frame[1] + 9, 400, 0.01),
      "dragging across makes a bracket over that span, its bar at the drag's height", JSON.stringify(brA));
    await choose("Label", "***");
    check(store.item(brA.id).label === "***" && near(store.item(brA.id).frame[1] + 9, 400, 0.01), "its label changes, the bar staying put",
      JSON.stringify(store.item(brA.id)));
    await until(() => canvas.els.get(brA.id)?.g.textContent.includes("***") || canvas.els.get(brA.id)?.g.querySelector("path"), 3000);
    const brB = { ...JSON.parse(JSON.stringify(store.item(brA.id))), id: "brB", frame: [290, 398, 120, 13] };
    const brC = { ...JSON.parse(JSON.stringify(store.item(brA.id))), id: "brC", frame: [420, 396, 40, 13] };
    store.update("More brackets", (doc) => doc.pages[store.pageIndex].items.push(brB, brC));
    store.select([brA.id, "brB", "brC"]);
    await app.run("stackBrackets");
    const fB = store.item("brB").frame, fA = store.item(brA.id).frame, fC = store.item("brC").frame;
    check(near(fA[1] + fA[3], fC[1] + fC[3], 0.01) && fB[1] + fB[3] <= fA[1] - 1.99,
      "Stack puts brackets that don't overlap on one level, and a wider one above", `${JSON.stringify(fA)} ${JSON.stringify(fB)} ${JSON.stringify(fC)}`);
    await app.run("delete");
    store.update("Zoom gone, picture back", (doc) => {
      const items = doc.pages[store.pageIndex].items, gone = new Set([zBoxItem().id, zInset().id, ...zLines().map((l) => l.id)]);
      items.splice(0, items.length, ...items.filter((i) => !gone.has(i.id)));
      items.splice(items.findIndex((i) => i.id === pics[0].id), 1, sbWas);
    }, { select: [] });

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

    // Area fills, on a page of their own: the space three separate lines enclose, filled with the
    // Fill area tool; it follows the lines, takes them along when dragged, and goes with them
    const fillPageAt = store.pageIndex;
    await app.run("addPage");
    await settle();
    const lineItem = (id, a, b) => ({ id, type: "line", points: [a, b], arrow_start: null, arrow_end: null,
      stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 } });
    store.update("Triangle for the test", (doc) => doc.pages[store.pageIndex].items.push(lineItem("tri1", [100, 300], [200, 120]),
      lineItem("tri2", [200, 120], [300, 300]), lineItem("tri3", [300, 300], [100, 300])), { select: [] });
    await settle();
    key("f");
    check(canvas.tool === "fill", "F chooses the Fill area tool");
    pointer("pointerdown", screenOf(200, 250));
    pointer("pointerup", screenOf(200, 250), { buttons: 0 });
    await until(() => store.items().some((i) => i.geom === "region"), 4000);
    await settle();
    const area = () => store.items().find((i) => i.geom === "region");
    const firstArea = area();
    check(firstArea && store.items()[0] === firstArea && firstArea.region.items.slice().sort().join() === "tri1,tri2,tri3" && canvas.tool === "select"
      && store.selection[0] === firstArea.id, "clicking inside three lines fills the area they enclose, behind them", JSON.stringify(firstArea && firstArea.region));
    await until(() => canvas.els.get(firstArea?.id)?.regionPath, 3000);
    check(canvas.els.get(firstArea?.id)?.g.querySelector("path") && near(area().frame[0], 100, 0.5) && near(area().frame[1], 120, 0.5),
      "the engine draws it, sized to the area", JSON.stringify(area()?.frame));
    store.update("Move a corner", (doc) => {
      const its = doc.pages[store.pageIndex].items;
      its.find((i) => i.id === "tri1").points[1] = [240, 90];
      its.find((i) => i.id === "tri2").points[0] = [240, 90];
    });
    await until(() => near(area().frame[1], 90, 0.5), 3000);
    check(near(area().frame[1], 90, 0.5), "moving a corner reshapes the fill", JSON.stringify(area().frame));
    await drag([200, 260], [230, 280], { metaKey: true, ctrlKey: true });
    await until(() => near(area().frame[0], 130, 0.5), 3000);
    const tri3 = store.items().find((i) => i.id === "tri3");
    check(near(tri3.points[0][0], 330, 0.01) && near(tri3.points[0][1], 320, 0.01) && near(area().frame[0], 130, 0.5),
      "dragging the fill moves its lines with it", `${JSON.stringify(tri3.points)} ${JSON.stringify(area().frame)}`);
    store.select([area().id]);
    app.detachArea();
    await settle();
    const plain = store.items()[0];
    check(plain.geom === "custom" && plain.path?.subpaths?.length === 1 && !plain.region, "Make an ordinary shape keeps the area as a shape",
      plain.geom);
    app.run("undo");
    await settle();
    store.select(["tri1", "tri2", "tri3"]);
    app.run("delete");
    await settle();
    check(!store.items().length, "deleting the lines deletes the fill between them", store.items().map((i) => i.geom || i.type).join());
    key("f");
    pointer("pointerdown", screenOf(400, 500));
    pointer("pointerup", screenOf(400, 500), { buttons: 0 });
    await settle();
    check(!store.items().length, "clicking where nothing encloses the spot fills nothing");
    key("Escape");
    await app.run("deletePage");
    store.setPage(fillPageAt);
    store.select([rect.id]);   // as the checks below expect
    await settle();

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
    // Kerning: new text has it, typing keeps it, and the Text tab turns it off and on (an
    // auto-fitted box narrows as the pairs close up)
    canvas.startEdit(tb.id);
    canvas.editor.innerHTML = "<div>Hello <b>bold</b> world: To AVA</div>";
    canvas.commitEdit();
    await settle();
    const kerned = store.item(tb.id).text.paragraphs[0].runs.every((r) => r.kern === true), wideOn = store.item(tb.id).frame[2];
    store.select([tb.id]);
    const kernBox = fieldByLabel("Kerning (letter pairs such as Ty and AV set closer, as the font says)");
    const ticked = kernBox?.checked;
    kernBox?.click();
    await settle();
    const off = store.item(tb.id).text.paragraphs[0].runs.every((r) => !r.kern), wideOff = store.item(tb.id).frame[2];
    fieldByLabel("Kerning (letter pairs such as Ty and AV set closer, as the font says)")?.click();
    await settle();
    check(kerned && ticked && off && wideOff > wideOn + 0.3 && store.item(tb.id).text.paragraphs[0].runs.every((r) => r.kern)
      && Math.abs(store.item(tb.id).frame[2] - wideOn) < 1e-6,
    "new text is kerned and stays kerned while typed in; the Text tab's Kerning box turns it off (the box widens) and on",
    `kerned ${kerned}; ticked ${ticked}; off ${off}; widths ${wideOn} / ${wideOff} / ${store.item(tb.id).frame[2]}`);

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
    // The page stays where it is on the screen as the rulers go and come back
    const fitCorner = screenOf(0, 0);
    key("r", { metaKey: true, ctrlKey: true });
    await until(() => !rulerTop.offsetParent);
    await settle();
    const fitCorner1 = screenOf(0, 0);
    check(!rulerTop.offsetParent && near(fitCorner[0], fitCorner1[0], 0.5) && near(fitCorner[1], fitCorner1[1], 0.5),
      "⌘R hides the rulers, the page staying where it was", `${fitCorner} -> ${fitCorner1}`);
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
    store.select([box.id]);   // (it has no fill: dragged from inside only while it's selected)
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
      stroke: { color: "#000000", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 }, fill: { color: "#dddddd", opacity: 1 } });
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
    // With no key object, Top goes to the highest of them, whichever was selected first
    store.update("Nudge for test", (doc) => { findItem(doc, "eqA").frame[1] = 520; findItem(doc, "eqB").frame[1] = 470; });
    app.run("alignTop");
    check(near(fr("eqA")[1], 470, 1e-6) && near(fr("eqB")[1], 470, 1e-6) && near(fr("eqC")[1], 470, 1e-6),
      "Align tops with no key object lines them up with the highest one", `${fr("eqA")[1]} ${fr("eqB")[1]} ${fr("eqC")[1]}`);
    store.update("Back for test", (doc) => { for (const id of ["eqA", "eqB", "eqC"]) findItem(doc, id).frame[1] = 500; });
    const cAt = screenOf(fr("eqC")[0] + 20, fr("eqC")[1] + 20), itemsBefore = store.page().items.length;
    pointer("pointerdown", cAt);
    pointer("pointerup", cAt);
    await settle();
    const plainKey = app.alignTo();
    pointer("pointerdown", cAt, { altKey: true });
    pointer("pointerup", cAt, { altKey: true });
    await settle();
    check(plainKey === "selection" && app.alignTo() === "key" && app.keyObject()?.id === "eqC" && store.selection.length === 3
      && store.page().items.length === itemsBefore && app.prefs.align_to !== "key",
      "a plain click on one of the selected objects leaves Align to alone; an Option-click makes it the key object (not saved)",
      `${plainKey} ${app.alignTo()} ${app.keyObject()?.id} ${store.selection} ${store.page().items.length}/${itemsBefore}`);
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
    // The key lasts for that selection only
    const toSel = document.querySelector('#rpanel-arrange [data-sync="align_to"]');
    store.select(["eqA", "eqB"]);
    check(app.alignTo() === "selection" && !app.keyObject() && toSel.value === "selection",
      "selecting other objects ends the key object: Align to goes back to Selection", `${app.alignTo()} ${toSel.value}`);
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
    // Its colour vision preview filters the page and its objects, not the handles or exports
    const cvdLabel = [...document.querySelectorAll("#rpanel-view label")].find((l) => l.textContent === "Colour vision");
    const cvdSelect = cvdLabel && document.getElementById(cvdLabel.htmlFor);
    cvdSelect.value = "deuteranopia";
    cvdSelect.dispatchEvent(new Event("change", { bubbles: true }));
    const cvdNote = document.querySelector(".cvd-note");
    check(canvas.itemsLayer.getAttribute("filter") === "url(#fa-cvd)" && canvas.pageRect.getAttribute("filter") === "url(#fa-cvd)"
      && !canvas.overlay.getAttribute("filter") && (canvas.cvdMatrix.getAttribute("values") || "").startsWith("0.367322 0.860646")
      && !cvdNote.hidden, "Colour vision previews the page as with deuteranopia, with a note over it",
    `${canvas.itemsLayer.getAttribute("filter")} ${canvas.cvdMatrix.getAttribute("values")?.slice(0, 30)} ${cvdNote.hidden}`);
    cvdNote.querySelector("button").click();
    check(!canvas.itemsLayer.getAttribute("filter") && cvdNote.hidden && cvdSelect.value === "normal",
      "the note's Stop button ends the preview, and the menu follows", cvdSelect.value);
    // Command search (⌘/): a few letters find a command, and Enter runs it
    key("/", { metaKey: true, ctrlKey: true });
    const csDlg = document.querySelector("dialog.command-search"), csInput = csDlg?.querySelector("input");
    csInput.value = "rulers";
    csInput.dispatchEvent(new Event("input"));
    const csFirst = csDlg.querySelector('[role="option"]')?.textContent || "";
    const rulersWere = !!app.prefs.show_rulers;
    csInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await until(() => !!app.prefs.show_rulers !== rulersWere);
    // (a closed dialog leaves the page on its close event, a moment later)
    check(/rulers/i.test(csFirst) && !document.querySelector("dialog.command-search[open]") && !!app.prefs.show_rulers !== rulersWere,
      "⌘/ finds a command by name, and Enter runs it", `${csFirst}; rulers ${rulersWere} -> ${app.prefs.show_rulers}`);
    await app.run("toggleRulers");
    await until(() => !!app.prefs.show_rulers === rulersWere);
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
      { id: "cnR", type: "shape", geom: "rect", frame: [100, 100, 80, 50], rot: 0, flip_h: false, flip_v: false, fill: { color: "#dddddd", opacity: 1 },
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
    store.select([]);   // (a ⌘-press adds to the selection, and the arrow would move too)
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
    store.select([]);
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
    // Dashed outlines: an end can attach to a dot (the one furthest from the corners and side
    // middles, which come first where they're in reach; zoomed in so it's out of their reach)
    canvas.setZoom(4, ...canvas.toScreen(150, 330));
    await settle();
    const cnSites = canvas.sitesOf(store.item("cnD")), cnMains = cnSites.filter((x) => !/^d\d+[sme]$/.test(x.key));
    const clear = (x) => Math.min(...cnMains.map((m) => Math.hypot(m.at[0] - x.at[0], m.at[1] - x.at[1])));
    const dot = cnSites.filter((x) => /^d\d+m$/.test(x.key)).reduce((a, b) => (clear(b) > clear(a) ? b : a));
    await drag(cnAt(1), [dot.at[0] + 0.5, dot.at[1] + 0.5]);
    check(store.item(cn.id).end_link?.item === "cnD" && /^d\d+m$/.test(store.item(cn.id).end_link.site)
      && near(cnAt(1)[0], dot.at[0], 1e-6), "an end attaches to a dot of a dotted outline",
    `${store.item(cn.id).end_link?.site}; the dot ${clear(dot).toFixed(1)} pt from a main point, reach ${(8 / canvas.k).toFixed(1)} pt`);
    canvas.fit();
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

    await macMenuChecks(app);

    // Export, save and reopen
    if (out) {
      const res = await rpc("export", store.doc, { base: `${out}/selftest`, formats: ["pdf", "svg", "png", "pptx"], dpi: 150,
        transparent: true, pages: [0], doc_path: null });
      check(res.files.length === 4 && res.files.some((f) => f.endsWith(".pptx")), "export wrote PDF, SVG, PNG and PowerPoint",
        res.files.join(", "));
      const saved = await rpc("save_document", store.doc, `${out}/selftest.mosaic`);
      const reopened = await rpc("open_document", saved.path);
      check(reopened.doc.pages[0].items.length === store.doc.pages[0].items.length, "saved document reopens with every object");
      // The figure report, in the formats chosen (none to start with)
      await app.run("figureReport");
      const reportDlg = [...document.querySelectorAll("dialog[open]")].pop();
      check(reportDlg && [...reportDlg.querySelectorAll(".formats input")].length === 4
        && ![...reportDlg.querySelectorAll(".formats input")].some((i) => i.checked), "Figure report offers HTML, Markdown, CSV and PDF, none ticked");
      reportDlg.close();
      const rep = await rpc("figure_report", store.doc, { formats: ["csv", "md"], base: `${out}/selftest_report`, pages: [0], units: "cm" });
      check(rep.files.length === 2 && rep.files.every((f) => /selftest_report\.(csv|md)$/.test(f)), "and writes a report for each picture",
        rep.files.join(", "));
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
    if (err !== ONLY) log(false, "self-test crashed", `${err.message} ${err.stack}`);
  }
  const failed = results.filter((r) => !r.ok).length;
  info.ms = Math.round(performance.now());   // (virtual time in headless Chrome, which has a budget)
  console.log(`SELFTEST DONE ${results.length - failed}/${results.length} passed in ${info.ms} ms (PowerPoint slides ${info.slidesMs} ms)`);
  window.__selftest = { results, failed, info };
  document.body.dataset.selftest = failed ? "fail" : "pass";
}

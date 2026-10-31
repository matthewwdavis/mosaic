// Scenes for the tutorial's and user guide's screenshots, loaded only with ?docshot=<scene>
// (tools/doc_shots.py). Each builds the tutorial figure from the sample plots in examples/ up to
// its step, in the real editor, and leaves it as the picture should show it.

import { rpc } from "./api.js";
import { canvas } from "./canvas.js";
import { inspector } from "./inspector.js";
import { store } from "./store.js";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const settle = async () => { await wait(80); await canvas.resolveNow(); await wait(80); };
function screenOf(px, py) {
  const r = canvas.stage.getBoundingClientRect();
  const [x, y] = canvas.toScreen(px, py);
  return [x + r.left, y + r.top];
}
function pointer(type, at, opts = {}) {
  canvas.stage.dispatchEvent(new PointerEvent(type, { clientX: at[0], clientY: at[1], bubbles: true, button: 0, buttons: 1,
    pointerId: 1, pointerType: "mouse", ...opts }));
}
// Set a dropdown in the properties panel by its label, as a person would
async function choose(label, value) {
  inspector.render();
  const l = [...document.querySelectorAll("#inspector label")].find((x) => x.textContent === label);
  const field = l && document.getElementById(l.htmlFor);
  field.value = value;
  field.dispatchEvent(new Event("change", { bubbles: true }));
  await wait(80);
}
// Zoom in with a page point in the middle of the view
function centreOn(px, py, zoom) {
  const r = canvas.stage.getBoundingClientRect();
  canvas.zoom = zoom;
  canvas.panX = r.width / 2 - px * canvas.k;
  canvas.panY = r.height / 2 - py * canvas.k;
  canvas.applyView();
}
const label = (id, t, x, y) => ({ id, type: "shape", geom: "rect", textbox: true, frame: [x, y, 10, 10], rot: 0, stroke: null,
  fill: null, text: { paragraphs: [{ align: "l", runs: [{ t, font: "Helvetica", size: 8, bold: true, italic: false, color: "#000000" }] }],
    insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" } });

export async function run(app, params) {
  const scene = params.get("docshot"), dir = params.get("examples"), out = params.get("out");
  app.autoConfirm = true;
  for (const d of document.querySelectorAll("dialog[open]")) d.close();
  await app.savePrefs({ theme: params.get("theme") || "light", show_rulers: true, show_grid: false, show_guides: true, snap: true });
  store.setDoc(await rpc("new_document"));
  store.update("Title", (doc) => { doc.meta.title = "Tutorial figure"; });
  document.getElementById("rtab-home").click();
  canvas.fit();
  await settle();

  // Step 1: a Nature double-column page
  store.select([]);
  await choose("Journal", "Nature");
  await choose("Figure type", "Double column");
  canvas.fit();
  await settle();
  if (scene === "page-size") return finish();

  // Step 2: the three sample plots, placed at true size (the last one stays selected)
  const placed = await rpc("add_files", ["growth_curves", "expression_bars", "dose_response"].map((n) => `${dir}/${n}.pdf`), false);
  app.placeResults(placed, [30, 30], "linked");
  await settle();
  const [a, b, c] = store.items().map((i) => i.id);
  if (scene === "placed") {
    // Dropped side by side; the last one selected, showing what FigAssemble found
    store.update("Spread", (doc) => [a, b, c].forEach((id, k) => {
      const it = doc.pages[0].items.find((i) => i.id === id);
      it.frame = [[20, 20], [250, 20], [20, 190]][k].concat(it.frame.slice(2));
    }), { select: [c] });
    await settle();
    inspector.render();
    document.getElementById("itab-picture")?.click();
    return finish();
  }

  // Step 3: arranged in two rows (b on its way, for the snapping picture)
  const fr = (id) => store.item(id).frame;
  store.update("Arrange", (doc) => {
    const it = (id) => doc.pages[0].items.find((i) => i.id === id);
    it(a).frame = [14, 14, fr(a)[2], fr(a)[3]];
    it(b).frame = [227, 14, fr(b)[2], fr(b)[3]];
    it(c).frame = [14, 163, fr(c)[2], fr(c)[3]];
  }, { select: [] });
  await settle();
  if (scene === "snapping") {
    // b dragged back into line beside a: the magenta line shows its top meeting a's
    store.update("Offset", (doc) => { doc.pages[0].items.find((i) => i.id === b).frame[1] = 40; }, { select: [b] });
    await settle();
    centreOn(215, 75, 1.4);
    const from = [fr(b)[0] + 60, fr(b)[1] + 50];
    pointer("pointerdown", screenOf(...from));
    for (const f of [0.3, 0.6, 0.9, 1]) pointer("pointermove", screenOf(from[0], from[1] - 25 * f));
    return finish();
  }
  if (scene === "arrange") {
    store.select([a, b]);
    document.getElementById("rtab-arrange").click();
    return finish();
  }
  if (scene === "group") {
    // The top two plots selected and the bar chart right-clicked, the pointer on Group
    store.select([a, b]);
    await settle();
    const at = screenOf(fr(b)[0] + fr(b)[2] * 0.3, fr(b)[1] + fr(b)[3] * 0.35);
    setTimeout(() => {
      canvas.stage.dispatchEvent(new MouseEvent("contextmenu", { clientX: at[0], clientY: at[1], bubbles: true, cancelable: true, button: 2 }));
      [...document.querySelectorAll(".context-menu .menu-item")].find((m) => m.textContent.startsWith("Group"))?.focus();
    }, 200);
    return finish();
  }

  // Step 4: panel labels a, b, c
  store.update("Labels", (doc) => doc.pages[0].items.push(label("la", "a", 4, 4), label("lb", "b", 217, 4), label("lc", "c", 4, 153)),
    { select: [] });
  await settle();
  if (scene === "labels") return finish();

  // Step 5: a note with an arrow attached to it, pointing at the curve where it crosses 50% (at
  // 1.5 µM: x 261.7, y 206.7 on the page, from the plot's scales), stopping 4 pt short
  store.update("Note", (doc) => {
    doc.pages[0].items.push({ ...label("note", "Half the cells survive at 1.5 µM", 330, 173), text: {
      paragraphs: [{ align: "l", runs: [{ t: "Half the cells survive at 1.5 µM", font: "Helvetica", size: 6, bold: false, italic: false,
        color: "#000000" }] }], insets: [0, 0, 0, 0], wrap: false, anchor: "t", autofit: "shape" } });
  });
  await settle();
  store.update("Arrow", (doc) => doc.pages[0].items.push({ id: "arrow", type: "line", points: [[328, 177], [265.3, 205.1]],
    stroke: { color: "#000000", width: 0.75, dash: "solid", cap: "round", join: "round", opacity: 1 }, arrow_start: null,
    arrow_end: { type: "triangle", w: "med", len: "med" }, start_link: { item: "note", site: "m3" } }), { select: [] });
  await settle();
  // Step 6: the page's height fitted to the figure (a journal page keeps its column width)
  await app.run("fitPage");
  await settle();
  canvas.fit();
  await settle();
  if (scene === "annotated" || scene === "style") {
    store.select(["arrow"]);
    inspector.render();   // the panel draws on the next frame otherwise, after the tab is clicked
    document.getElementById(scene === "style" ? "itab-style" : "itab-arrange")?.click();
    return finish();
  }
  if (scene === "export") { setTimeout(() => app.run("export"), 200); return finish(); }
  if (scene === "themes") {
    // Settings, scrolled to the theme gallery, on the default: Match the system, Light by day, Dark at night
    await app.savePrefs({ theme: "system", theme_day: "light", theme_night: "dark" });
    setTimeout(() => {
      app.run("preferences");
      setTimeout(() => document.querySelector(".theme-gallery")?.closest("fieldset")?.scrollIntoView({ block: "start" }), 100);
    }, 200);
    return finish();
  }
  if (scene === "check") { setTimeout(() => app.run("preflight"), 200); return finish(); }
  if (scene === "shapes") { setTimeout(() => document.getElementById("shapes-button").click(), 200); return finish(); }
  if (scene === "guides") {
    await app.savePrefs({ show_grid: true });
    store.update("Guides", (doc) => { doc.pages[0].guides = { x: [14, 227], y: [14, 163] }; });
    document.getElementById("rtab-view").click();
    return finish();
  }
  if (scene === "result" && out) {
    // The finished figure as exported, for the tutorial's last step
    await rpc("export", store.doc, { base: `${out}/tutorial-result`, formats: ["png"], dpi: 220, transparent: false, pages: [0], doc_path: null });
  }
  return finish();
}

async function finish() {
  await settle();
  document.body.dataset.docshot = "ready";
  console.log("DOCSHOT READY");
}

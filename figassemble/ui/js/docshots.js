// Scenes for the tutorial's and user guide's screenshots, loaded only with ?docshot=<scene>
// (tools/doc_shots.py). Each builds the tutorial figure from the sample plots in examples/ up to
// its step, in the real editor, and leaves it as the picture should show it.

import { rpc } from "./api.js";
import { canvas } from "./canvas.js";
import { inspector } from "./inspector.js";
import { store } from "./store.js";
import { PALETTES } from "./swatches.js";
import { formatOf as lookOf } from "./objectstyles.js";

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

  if (scene === "areafill") {
    // A Venn diagram: two circles, and the three areas they make filled with the Fill area tool;
    // the overlap selected, with its Style tab
    const ring = (id, x) => ({ id, type: "shape", geom: "ellipse", frame: [x, 90, 130, 130], rot: 0, flip_h: false, flip_v: false,
      stroke: { color: "#333333", width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 }, fill: null });
    store.update("Venn", (doc) => doc.pages[0].items.push(ring("left", 110, 90), ring("right", 200, 90)), { select: [] });
    await settle();
    // Left only, right only, then the overlap (left selected)
    for (const [x, colour] of [[150, "#56b4e9"], [290, "#e69f00"], [220, "#009e73"]]) {
      await app.fillArea([x, 155]);
      store.update("Colour", (doc) => { doc.pages[0].items.find((i) => i.id === store.selection[0]).fill.color = colour; });
      await settle();
    }
    centreOn(220, 155, 2.2);
    await settle();
    inspector.render();
    document.getElementById("itab-style")?.click();
    return finish();
  }

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
  if (scene === "plotsnap") {
    // b cropped at the top and dragged into line with a: the magenta line runs along both plots'
    // x axes, though their tops don't line up
    store.update("Crop b", (doc) => {
      const it = doc.pages[0].items.find((i) => i.id === b);
      it.crop = [0, 0.2, 0, 0];
      it.frame = [it.frame[0], 60, it.frame[2], it.frame[3] * 0.8];
    }, { select: [b] });
    for (let t = 0; t < 200 && !(canvas.plotSnaps(store.item(a)).length && canvas.plotSnaps(store.item(b)).length); t++) await wait(50);
    await settle();
    const xAxis = (id) => Math.max(...canvas.plotSnaps(store.item(id)).filter((t) => t.axis === 1 && t.v < fr(id)[1] + fr(id)[3] - 2).map((t) => t.v));
    const dy = xAxis(a) - xAxis(b);
    centreOn(215, 90, 1.6);
    const from = [fr(b)[0] + 60, fr(b)[1] + 30];
    pointer("pointerdown", screenOf(...from));
    for (const f of [0.3, 0.6, 0.9, 1]) pointer("pointermove", screenOf(from[0], from[1] + (dy + 1) * f));
    return finish();
  }
  if (scene === "equation") {
    // The dose-response model beside its curve, selected, with its Equation tab
    const spec = { tex: "V = \\frac{100}{1 + (x/\\mathrm{IC}_{50})^{h}}", size: 6, font: "figure", family: "Helvetica", color: "#000000" };
    const res = await rpc("make_equation", spec);
    const pic = { id: "eq1", type: "picture", name: "", asset: res.id, page_index: 0, frame: [290, 185, ...res.asset.size_pt],
      crop: [0, 0, 0, 0], rot: 0, flip_h: false, flip_v: false, opacity: 1, source: "auto", equation: spec };
    store.update("Equation", (doc) => { doc.assets[res.id] = res.asset; doc.pages[0].items.push(pic); }, { select: ["eq1"] });
    await settle();
    centreOn(300, 200, 2.4);
    inspector.render();
    document.getElementById("itab-picture")?.click();
    return finish();
  }
  if (scene === "symbols") {
    // A cell drawn once as a symbol, used at three sizes; the biggest selected, with its tab
    const cellPart = (id, geom, frame, fill, stroke) => ({ id, type: "shape", geom, frame, rot: 0, flip_h: false, flip_v: false, fill: { color: fill },
      stroke: stroke ? { color: stroke, width: 1, dash: "solid", cap: "round", join: "round", opacity: 1 } : null });
    store.update("Cell", (doc) => doc.pages[0].items.push(cellPart("cellBody", "ellipse", [40, 300, 44, 30], "#cfe8ff", "#2b6cb0"),
      cellPart("cellNucleus", "ellipse", [55, 309, 14, 12], "#2b6cb0", null)), { select: ["cellBody", "cellNucleus"] });
    await app.run("makeSymbol");
    const first = store.selected()[0].id;
    for (const [x, k] of [[110, 1.6], [200, 0.7]]) {
      await app.run("duplicate");
      const id = store.selected()[0].id;
      store.update("Place", (doc) => { doc.pages[0].items.find((i) => i.id === id).frame = [x, 296, 44 * k, 30 * k]; });
    }
    store.select([store.items().find((i) => i.type === "symbol" && i.id !== first && i.frame[2] > 60).id]);
    await settle();
    centreOn(150, 320, 2.2);
    inspector.render();
    document.getElementById("itab-arrange")?.click();
    return finish();
  }
  if (scene === "gridlayout") {
    // The three plots in a grid layout, with its Arrange tab: columns and gaps
    store.select([a, b, c]);
    await app.run("gridLayout");
    await settle();
    inspector.render();
    document.getElementById("itab-arrange")?.click();
    return finish();
  }
  if (scene === "arrange") {
    store.select([a, b]);
    document.getElementById("rtab-arrange").click();
    return finish();
  }
  if (scene === "distances") {
    // Plot a selected, Option held and the pointer on plot b: the gap between them
    store.select([a]);
    await settle();
    const fb = fr(b);
    canvas.hoverAt = [fb[0] + fb[2] / 2, fb[1] + fb[3] / 2];
    canvas.setMeasureKey(true);
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

  if (scene === "brackets") {
    // Brackets over the bar chart's gene1 and gene3 pairs, and gene1 to gene2, stacked in levels
    const f = fr(b), bx = (u) => f[0] + f[2] * u, top = f[1] + f[3] * 0.17;
    const bracket = (id, u0, u1, label) => ({ id, type: "bracket", label, size: 6, bold: false, line_width: 0.75, color: "#000000",
      rot: 0, dir: "up", tick: 4, frame: [bx(u0), top - 13, bx(u1) - bx(u0), 13] });
    store.update("Brackets", (doc) => doc.pages[0].items.push(bracket("k1", 0.19, 0.31, "***"), bracket("k3", 0.66, 0.78, "**"),
      bracket("k12", 0.24, 0.52, "ns")), { select: ["k1", "k3", "k12"] });
    await app.run("stackBrackets");
    centreOn(f[0] + f[2] / 2, f[1] + f[3] * 0.3, 2.2);
    store.select(["k12"]);
    inspector.render();
    document.getElementById("itab-bracket")?.click();
    return finish();
  }
  if (scene === "zoominset") {
    // The dose-response plot's steep part boxed and shown enlarged beside it
    const f = fr(c);
    store.update("Narrower", (doc) => { const it = doc.pages[0].items.find((i) => i.id === c); it.frame[2] *= 0.6; it.frame[3] *= 0.6; });
    const g = fr(c);
    app.addZoomInset(c, [g[0] + g[2] * 0.42, g[1] + g[3] * 0.25, g[2] * 0.2, g[3] * 0.45]);
    await settle();
    void f;
    return finish();
  }
  if (scene === "cropshape") {
    // The bar chart cropped to a rounded rectangle, with its Picture tab
    store.update("Crop to shape", (doc) => { doc.pages[0].items.find((i) => i.id === b).mask = { geom: "roundRect", adj: { adj: 0.3 } }; },
      { select: [b] });
    inspector.render();
    document.getElementById("itab-picture")?.click();
    await settle();
    await new Promise((r) => setTimeout(r, 400));   // the clip comes from the engine
    return finish();
  }
  if (scene === "isolation") {
    // The top two plots grouped, then edited inside: the bar chart picked on its own, the rest faded
    store.select([a, b]);
    await app.run("group");
    canvas.enterGroup(store.selection[0]);
    store.select([b]);
    return finish();
  }

  // Step 4: panel labels a, b, c, each staying with its plot as the Label tool leaves them
  store.update("Labels", (doc) => doc.pages[0].items.push({ ...label("la", "a", 4, 4), attach: { to: a } },
    { ...label("lb", "b", 217, 4), attach: { to: b } }, { ...label("lc", "c", 4, 153), attach: { to: c } }), { select: [] });
  await settle();
  if (scene === "labels") return finish();
  if (scene === "attached") {
    // Label b moved a little way off its plot and selected: the plot dashed, the line to the
    // corner it keeps, and its Arrange tab; zoomed in on the corner
    const fb = fr(b);
    store.update("Label b off its plot", (doc) => {
      const lb = doc.pages[0].items.find((i) => i.id === "lb");
      lb.frame = [fb[0] - 9, fb[1] - 4, lb.frame[2], lb.frame[3]];
    }, { select: ["lb"] });
    await settle();
    canvas.setZoom(3, ...canvas.toScreen(fb[0], fb[1]));
    inspector.render();
    document.getElementById("itab-arrange")?.click();
    return finish();
  }

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
  if (scene === "objectstyles") {
    // A style made from the arrow, then the arrow made thicker by hand: its Style tab says it
    // differs, with Clear changes and Update the style to match
    store.update("Arrow style", (doc) => {
      const arrow = doc.pages[0].items.find((i) => i.id === "arrow");
      doc.object_styles = [{ id: "os1", name: "Callout arrow", ...lookOf(arrow) }];
      arrow.object_style = "os1";
      arrow.stroke = { ...arrow.stroke, width: (arrow.stroke.width || 1) * 1.5 };
    }, { select: ["arrow"] });
    inspector.render();
    document.getElementById("itab-style")?.click();
    return finish();
  }
  if (scene === "annotated" || scene === "style") {
    store.select(["arrow"]);
    inspector.render();   // the panel draws on the next frame otherwise, after the tab is clicked
    document.getElementById(scene === "style" ? "itab-style" : "itab-arrange")?.click();
    return finish();
  }
  if (scene === "swatches") {
    // The Okabe-Ito palette added, the arrow's line linked to its vermillion, and the Swatches dialog
    app.addPalette(PALETTES[0].colours, PALETTES[0].name);
    const sw = store.doc.swatches.find((x) => x.name === "Vermillion");
    store.update("Swatch", (doc) => {
      const a = doc.pages[0].items.find((i) => i.id === "arrow");
      a.stroke = { ...a.stroke, color: sw.color, swatch: sw.id };
    }, { select: ["arrow"] });
    setTimeout(() => app.run("swatches"), 200);
    return finish();
  }
  if (scene === "search") {
    // Command search with "align" typed
    setTimeout(() => {
      app.run("commandSearch");
      const input = document.querySelector("dialog.command-search input");
      input.value = "align";
      input.dispatchEvent(new Event("input"));
    }, 200);
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

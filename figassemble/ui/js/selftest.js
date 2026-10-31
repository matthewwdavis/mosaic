// Scripted run-through of the editor, loaded only with ?selftest=1 (used by tools/ui_selftest.py).
// Drives the real UI through pointer and keyboard events and reports through console.log.

import { rpc } from "./api.js";
import { canvas } from "./canvas.js";
import { store } from "./store.js";
import { lineMidpoints } from "./util.js";

const results = [];
const log = (ok, name, detail = "") => {
  results.push({ ok, name });
  console.log(`SELFTEST ${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};
const check = (cond, name, detail) => log(!!cond, name, cond ? "" : detail);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
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
  const files = (params.get("files") || "").split(",").filter(Boolean);
  const out = params.get("out");
  app.autoConfirm = true;
  for (const dlg of document.querySelectorAll("dialog[open]")) dlg.close();   // e.g. a recovery offer
  try {
    store.setDoc(await rpc("new_document"));
    canvas.fit();
    await settle();
    check(store.items().length === 0, "new document is empty");
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
    // Keep the pictures apart so pointer tests hit the one intended
    if (pics[1]) store.update("Arrange for test", (doc) => {
      const it = doc.pages[0].items.find((i) => i.id === pics[1].id);
      it.frame = [20, 250, it.frame[2], it.frame[3]];
    });

    // Drawing tools
    canvas.setTool("rect");
    await drag([300, 300], [360, 340]);
    const rect = store.items().find((i) => i.geom === "rect");
    check(rect && Math.abs(rect.frame[2] - 60) < 0.6 && Math.abs(rect.frame[3] - 40) < 0.6, "rectangle drawn by dragging", JSON.stringify(rect?.frame));
    check(canvas.els.get(rect?.id)?.g.querySelector("path"), "rectangle drawn by the engine");
    canvas.setTool("arrow");
    await drag([300, 380], [400, 380]);
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
    await drag([420, 300], [480, 360]);
    const arcItem = store.items().find((i) => i.geom === "arc");
    store.select([arcItem.id]);
    await app.run("shapeToCurve");
    const conv = store.item(arcItem.id);
    check(conv?.type === "line" && conv.curve === "smooth" && conv.points.length === 3,
      "an arc turns into an editable curve", JSON.stringify(conv?.points));
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
    await settle();
  } catch (err) {
    log(false, "self-test crashed", `${err.message} ${err.stack}`);
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`SELFTEST DONE ${results.length - failed}/${results.length} passed`);
  window.__selftest = { results, failed };
  document.body.dataset.selftest = failed ? "fail" : "pass";
}

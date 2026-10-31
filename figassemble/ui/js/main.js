// Start-up and commands: one registry drives the keyboard, the toolbar and the shortcuts list.

// Collected for the start-up smoke test (and handy when debugging in the app window)
window.__faErrors = [];
window.addEventListener("error", (e) => window.__faErrors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => window.__faErrors.push(String(e.reason?.message || e.reason)));

import { rpc } from "./api.js";
import { canvas, findDeep, reid, shiftGuides, shiftItem } from "./canvas.js";
import { inspector } from "./inspector.js";
import { panels } from "./panels.js";
import { rulers } from "./rulers.js";
import { store } from "./store.js";
import { MOD, announce, clone, describeItem, display, isMac, itemBBox, itemsBBox, lineMidpoints, shapeCatalog, uid } from "./util.js";

const app = {
  prefs: {},
  info: {},
  fonts: [],
  mod: MOD,
  clipboard: null,
  commands: {},

  async run(name) {
    const c = this.commands[name];
    if (!c) return;
    try {
      await c.run();
    } catch (err) {
      console.error(err);
      announce(`${c.label} failed: ${err.message}`);
    }
  },

  async savePrefs(p) {
    this.prefs = await rpc("prefs_set", p);
    applyPrefs(this.prefs);
    store.emit("doc", {});
  },
  // Rulers, grid, guides and snapping are switched from the toolbar, the keyboard and Preferences
  async togglePref(key, onMessage, offMessage) {
    const on = !this.prefs[key];
    await this.savePrefs({ [key]: on });
    announce(on ? onMessage : offMessage);
  },

  // Files ---------------------------------------------------------------------------

  async confirmDiscard() {
    return !store.dirty || panels.confirm("Discard changes?", "This document has unsaved changes. Discard them?", "Discard");
  },
  async newDocument() {
    if (!(await this.confirmDiscard())) return;
    store.setDoc(await rpc("new_document"));
    canvas.fit();
    announce("New document");
  },
  async open(path = null) {
    if (!(await this.confirmDiscard())) return;
    if (!path) {
      if (this.info.native) path = (await rpc("open_dialog", "document"))?.[0];
      else path = await panels.pathDialog("Open a document or PowerPoint deck", "/path/to/figure.figasm", this.prefs.recent || []);
    }
    if (!path) return;
    announce("Opening…");
    const res = await rpc("open_document", path);
    store.setDoc(res.doc, res.path);
    if (!res.path && res.suggested) store.suggested = res.suggested;
    canvas.fit();
    if (res.report?.length) panels.reportDialog("Imported from PowerPoint", res.report);
    announce(`Opened ${res.doc.meta?.title || "document"}, ${res.doc.pages.length} pages`);
  },
  async save(as = false) {
    let path = store.path;
    if (as || !path) {
      const suggested = store.suggested || `${store.doc.meta?.title || "Untitled figure"}.figasm`;
      if (this.info.native) path = await rpc("save_dialog", suggested.split(/[\\/]/).pop(), dirOf(store.path || store.suggested));
      else path = await panels.pathDialog("Save as", suggested);
    }
    if (!path) return;
    const res = await rpc("save_document", store.doc, path);
    store.markSaved(res.path);
    rpc("discard_autosave", store.autosaveKey).catch(() => {});
    announce(`Saved ${res.path.split(/[\\/]/).pop()}` + (res.warnings.length ? `, with ${res.warnings.length} warnings` : ""));
    if (res.warnings.length) panels.reportDialog("Saved, with warnings", res.warnings);
  },
  async chooseExportBase() {
    const title = (store.doc.meta?.title || "figure").replace(/[^\w.-]+/g, "_");
    if (this.info.native) {
      const p = await rpc("save_dialog", `${title}.pdf`, dirOf(store.path));
      return p ? p.replace(/\.(pdf|svg|png|tiff?|jpe?g|eps)$/i, "") : null;
    }
    const dir = dirOf(store.path) || "~/Desktop";
    const p = await panels.pathDialog("Export to (path without extension)", `${dir}/${title}`);
    return p ? p.replace(/\.(pdf|svg|png|tiff?|jpe?g|eps)$/i, "") : null;
  },

  // Placing files ---------------------------------------------------------------------

  async insertPicture() {
    if (this.info.native) {
      const paths = await rpc("open_dialog", "figures");
      if (paths?.length) await this.placeFiles(paths, null, false);
    } else {
      const input = Object.assign(document.createElement("input"), { type: "file", multiple: true,
        accept: ".pdf,.svg,.png,.jpg,.jpeg,.tif,.tiff" });
      input.addEventListener("change", () => this.placeUploads([...input.files], null));
      input.click();
    }
  },
  async placeFiles(paths, pagePoint, embedOnly) {
    announce(`Placing ${paths.length} file${paths.length === 1 ? "" : "s"}…`);
    const results = await rpc("add_files", paths, !!embedOnly);
    this.placeResults(results, pagePoint, embedOnly ? "stored without a link" : "linked");
  },
  async placeUploads(files, pagePoint) {
    const results = [];
    for (const f of files) {
      const b64 = await new Promise((res) => {
        const r = new FileReader();
        r.onload = () => res(String(r.result).split(",")[1]);
        r.readAsDataURL(f);
      });
      try { results.push(await rpc("add_upload", f.name, b64)); } catch (err) { results.push({ error: `${f.name}: ${err.message}` }); }
    }
    this.placeResults(results, pagePoint, "stored in the document");
  },
  placeResults(results, pagePoint, how) {
    const ok = results.filter((r) => !r.error);
    const errors = results.filter((r) => r.error).map((r) => r.error);
    if (!ok.length) { if (errors.length) panels.reportDialog("Couldn't place", errors); return; }
    const page = store.page();
    let [x, y] = pagePoint || [page.width * 0.1, page.height * 0.1];
    const items = [];
    store.update(`Place ${ok.length === 1 ? ok[0].asset.name : `${ok.length} pictures`}`, (doc) => {
      for (const r of ok) {
        doc.assets[r.asset_id] = r.asset;
        const [w, h] = r.asset.page_sizes ? r.asset.page_sizes[0] : r.asset.size_pt;
        const it = { id: uid("it"), type: "picture", name: r.asset.name, asset: r.asset_id, page_index: 0,
          frame: [x, y, w, h], crop: [0, 0, 0, 0], rot: 0, flip_h: false, flip_v: false, opacity: 1, source: "auto" };
        doc.pages[store.pageIndex].items.push(it);
        items.push(it);
        x += 12; y += 12;
      }
    }, { select: items.map((i) => i.id) });
    const warnings = ok.flatMap((r) => r.warnings || []).concat(errors);
    const copies = ok.map((r) => Object.keys(r.asset.variants).map((k) => k.toUpperCase()).join("+"));
    announce(`Placed ${ok.length} at true size (${how}; ${copies.join(", ")})`);
    if (warnings.length) panels.reportDialog("Placed, with notes", warnings);
  },
  async replacePicture(paths) {
    const it = store.selected()[0];
    if (!it || it.type !== "picture") return;
    if (!paths) {
      if (this.info.native) paths = await rpc("open_dialog", "figures");
      else return announce("Drop the new file onto the picture while holding Shift to replace it");
    }
    if (!paths?.length) return;
    const [r] = await rpc("add_files", [paths[0]], false);
    if (r.error) return panels.reportDialog("Couldn't replace", [r.error]);
    const old = store.doc.assets[it.asset];
    store.update("Replace picture", (doc) => {
      doc.assets[r.asset_id] = r.asset;
      const o = findDeep(doc.pages[store.pageIndex].items, it.id);
      const scale = o.frame[2] / (old.size_pt[0] * (1 - o.crop[0] - o.crop[2]));
      o.asset = r.asset_id;
      o.name = r.asset.name;
      o.crop = [0, 0, 0, 0];
      o.frame = [o.frame[0], o.frame[1], r.asset.size_pt[0] * scale, r.asset.size_pt[1] * scale];
    });
    announce(`Replaced with ${r.asset.name}`);
  },

  // Linked files that change on disk refresh in place, keeping each picture's scale
  async refreshLinks() {
    if (!store.doc || document.hidden) return;
    const linked = {};
    for (const [id, a] of Object.entries(store.doc.assets)) if (a.auto_update) linked[id] = a;
    if (!Object.keys(linked).length) return;
    const { changed } = await rpc("refresh_assets", linked, store.path);
    const ids = Object.keys(changed);
    if (!ids.length) return;
    store.update("Update from file", (doc) => {
      for (const id of ids) {
        const old = doc.assets[id], neu = changed[id];
        const walk = (items) => items.forEach((it) => {
          if (it.type === "group") walk(it.items);
          if (it.type !== "picture" || it.asset !== id) return;
          const [ow, oh] = old.size_pt, [nw, nh] = neu.size_pt;
          it.frame = [it.frame[0], it.frame[1], it.frame[2] * nw / ow, it.frame[3] * nh / oh];
        });
        doc.pages.forEach((p) => walk(p.items));
        doc.assets[id] = neu;
      }
    });
    announce(`Updated ${ids.map((id) => changed[id].name).join(", ")} from ${ids.length === 1 ? "its file" : "their files"}`);
  },

  // Arranging -----------------------------------------------------------------------

  nudge(dx, dy, resize = false) {
    const sel = store.selected().filter((it) => !it.locked);
    if (!sel.length) return;
    store.update(resize ? "Resize" : "Move", (doc) => {
      for (const s of sel) {
        const it = findDeep(doc.pages[store.pageIndex].items, s.id);
        if (resize && it.frame) {
          it.frame[2] = Math.max(it.frame[2] + dx, 0.5);
          it.frame[3] = Math.max(it.frame[3] + dy, 0.5);
        } else if (!resize) shiftItem(it, clone(it), dx, dy);
      }
    });
    if (sel.length === 1) announce(describeItem(store.selected()[0], store.doc));
  },
  align(how) {
    const sel = store.selected().filter((it) => !it.locked);
    if (!sel.length) return;
    const page = store.page();
    const ref = sel.length === 1 ? [0, 0, page.width, page.height] : itemsBBox(sel);
    store.update("Align", (doc) => {
      for (const s of sel) {
        const it = findDeep(doc.pages[store.pageIndex].items, s.id);
        const b = itemBBox(it);
        let dx = 0, dy = 0;
        if (how === "left") dx = ref[0] - b[0];
        if (how === "center") dx = (ref[0] + ref[2]) / 2 - (b[0] + b[2]) / 2;
        if (how === "right") dx = ref[2] - b[2];
        if (how === "top") dy = ref[1] - b[1];
        if (how === "middle") dy = (ref[1] + ref[3]) / 2 - (b[1] + b[3]) / 2;
        if (how === "bottom") dy = ref[3] - b[3];
        shiftItem(it, clone(it), dx, dy);
      }
    });
    announce(sel.length === 1 ? `Aligned to the page ${how}` : `Aligned ${sel.length} objects: ${how}`);
  },
  distribute(axis) {
    const sel = store.selected().filter((it) => !it.locked);
    if (sel.length < 3) return announce("Select three or more objects to distribute");
    const i0 = axis === "h" ? 0 : 1, i1 = axis === "h" ? 2 : 3;
    const boxes = sel.map((it) => ({ id: it.id, b: itemBBox(it) })).sort((a, b) => a.b[i0] - b.b[i0]);
    const total = boxes.reduce((s, x) => s + (x.b[i1] - x.b[i0]), 0);
    const span = boxes[boxes.length - 1].b[i1] - boxes[0].b[i0];
    const gap = (span - total) / (boxes.length - 1);
    store.update("Distribute", (doc) => {
      let pos = boxes[0].b[i0];
      for (const { id, b } of boxes) {
        const it = findDeep(doc.pages[store.pageIndex].items, id);
        const d = pos - b[i0];
        shiftItem(it, clone(it), axis === "h" ? d : 0, axis === "h" ? 0 : d);
        pos += b[i1] - b[i0] + gap;
      }
    });
    announce(`Distributed ${sel.length} objects evenly`);
  },
  reorder(how) {
    const ids = new Set(store.selection);
    if (!ids.size) return;
    store.update("Arrange", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      const sel = items.filter((it) => ids.has(it.id));
      const rest = items.filter((it) => !ids.has(it.id));
      if (how === "front") items.splice(0, items.length, ...rest, ...sel);
      else if (how === "back") items.splice(0, items.length, ...sel, ...rest);
      else {
        const d = how === "forward" ? 1 : -1;
        const order = d > 0 ? [...items.keys()].reverse() : [...items.keys()];
        for (const i of order) {
          if (!ids.has(items[i].id)) continue;
          const j = i + d;
          if (j < 0 || j >= items.length || ids.has(items[j].id)) continue;
          [items[i], items[j]] = [items[j], items[i]];
        }
      }
    });
    announce({ front: "Brought to front", back: "Sent to back", forward: "Brought forward", backward: "Sent backward" }[how]);
  },
  group() {
    const ids = new Set(store.selection);
    if (ids.size < 2) return announce("Select two or more objects to group");
    const g = { id: uid("it"), type: "group", name: "", items: [] };
    store.update("Group", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      const top = Math.max(...items.map((it, i) => (ids.has(it.id) ? i : -1)));
      g.items = items.filter((it) => ids.has(it.id));
      const rest = items.filter((it) => !ids.has(it.id) || it === items[top]);
      const at = rest.indexOf(items[top]);
      rest.splice(at, 1, g);
      items.splice(0, items.length, ...rest);
    }, { select: [g.id] });
    announce(`Grouped ${g.items.length} objects`);
  },
  ungroup() {
    const groups = store.selected().filter((it) => it.type === "group");
    if (!groups.length) return;
    const childIds = [];
    store.update("Ungroup", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      for (const g of groups) {
        const i = items.findIndex((it) => it.id === g.id);
        const gg = items[i];
        items.splice(i, 1, ...gg.items);
        childIds.push(...gg.items.map((c) => c.id));
      }
    }, { select: childIds });
    announce("Ungrouped");
  },
  deleteSelection() {
    const ids = new Set(store.selection);
    if (!ids.size) return;
    store.update("Delete", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      items.splice(0, items.length, ...items.filter((it) => !ids.has(it.id)));
    }, { select: [] });
    announce(`Deleted ${ids.size} object${ids.size === 1 ? "" : "s"}`);
  },
  copy(cut = false) {
    const sel = store.selected();
    if (!sel.length) return;
    const assets = {};
    const walk = (items) => items.forEach((it) => {
      if (it.type === "group") walk(it.items);
      if (it.type === "picture") assets[it.asset] = store.doc.assets[it.asset];
    });
    walk(sel);
    this.clipboard = { items: clone(sel), assets: clone(assets), page: store.page().id };
    const text = "figassemble:" + JSON.stringify(this.clipboard);
    navigator.clipboard?.writeText(text).catch(() => {});
    if (cut) this.deleteSelection();
    announce(`${cut ? "Cut" : "Copied"} ${sel.length} object${sel.length === 1 ? "" : "s"}`);
  },
  async paste() {
    let clip = this.clipboard;
    try {
      const text = await navigator.clipboard?.readText();
      if (text?.startsWith("figassemble:")) clip = JSON.parse(text.slice(12));
    } catch { /* clipboard not readable; use the internal one */ }
    if (!clip) return;
    const items = clip.items.map((it) => reid(clone(it)));
    const offset = clip.page === store.page().id ? 10 : 0;
    store.update("Paste", (doc) => {
      Object.assign(doc.assets, clip.assets);
      for (const it of items) {
        if (offset) shiftItem(it, clone(it), offset, offset);
        doc.pages[store.pageIndex].items.push(it);
      }
    }, { select: items.map((i) => i.id) });
    clip.page = store.page().id;
    announce(`Pasted ${items.length} object${items.length === 1 ? "" : "s"}`);
  },
  duplicate() {
    const sel = store.selected();
    if (!sel.length) return;
    const items = sel.map((it) => { const c = reid(clone(it)); shiftItem(c, clone(c), 10, 10); return c; });
    store.update("Duplicate", (doc) => doc.pages[store.pageIndex].items.push(...items), { select: items.map((i) => i.id) });
    announce(`Duplicated ${items.length} object${items.length === 1 ? "" : "s"}`);
  },
  // Curves --------------------------------------------------------------------------

  addPoint() {
    const it = store.selected()[0];
    if (!it || it.type !== "line") return;
    let best = 0, bestLen = -1;
    for (let i = 0; i < it.points.length - 1; i++) {
      const l = Math.hypot(it.points[i + 1][0] - it.points[i][0], it.points[i + 1][1] - it.points[i][1]);
      if (l > bestLen) { bestLen = l; best = i; }
    }
    const at = lineMidpoints(it)[best].at;
    store.update("Add point", (doc) => {
      const x = findDeep(doc.pages[store.pageIndex].items, it.id);
      x.points.splice(best + 1, 0, [at[0], at[1]]);
      if (!x.curve) x.curve = "smooth";
    });
    announce(`Added point ${best + 1}; move it in the panel or drag it on the page`);
  },
  straighten() {
    const it = store.selected()[0];
    if (!it || it.type !== "line" || it.points.length < 3) return;
    store.update("Make straight", (doc) => {
      const x = findDeep(doc.pages[store.pageIndex].items, it.id);
      x.points = [x.points[0], x.points[x.points.length - 1]];
    });
    announce("Made straight");
  },
  async shapeToCurve() {
    const it = store.selected()[0];
    if (!it || it.type !== "shape") return;
    const assets = {};
    for (const [id, a] of Object.entries(store.doc.assets)) assets[id] = { size_pt: a.size_pt, page_sizes: a.page_sizes };
    const line = await rpc("shape_to_curve", assets, it);
    store.update("Make editable curve", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      items[items.findIndex((x) => x.id === it.id)] = line;
    }, { select: [line.id] });
    announce(`Now a curve through ${line.points.length} points: drag them to reshape it`);
  },

  cycleSelection(back) {
    const items = store.items().filter((it) => !it.hidden);
    if (!items.length) return;
    const cur = items.findIndex((it) => it.id === store.selection[store.selection.length - 1]);
    const next = items[(cur + (back ? -1 : 1) + items.length) % items.length] || items[0];
    store.select([next.id]);
    announce(describeItem(next, store.doc));
  },

  // Pages ---------------------------------------------------------------------------

  addPage(copy = false) {
    const cur = store.page();
    // A new page starts with this page's size, background and guides
    const page = copy ? reidPage(clone(cur)) : { id: uid("pg"), name: `Page ${store.doc.pages.length + 1}`,
      width: cur.width, height: cur.height, background: cur.background,
      guides: { x: [...(cur.guides?.x || [])], y: [...(cur.guides?.y || [])] }, items: [] };
    if (copy) page.name = `${cur.name} copy`;
    store.update(copy ? "Duplicate page" : "Add page", (doc) => doc.pages.splice(store.pageIndex + 1, 0, page));
    store.setPage(store.pageIndex + 1);
    announce(`${copy ? "Duplicated" : "Added"} page ${store.pageIndex + 1}`);
  },
  async deletePage() {
    if (store.doc.pages.length === 1) return announce("A document needs at least one page");
    const name = store.page().name;
    if (store.items().length && !(await panels.confirm("Delete page?", `Delete page “${name}” and everything on it? `
      + "You can undo this.", "Delete page"))) return;
    const i = store.pageIndex;
    // Move to a page that still exists before anything redraws
    store.update("Delete page", (doc) => {
      doc.pages.splice(i, 1);
      store.pageIndex = Math.min(i, doc.pages.length - 1);
      store.selection = [];
    });
    store.setPage(store.pageIndex);
    announce(`Deleted page ${name}`);
  },
  movePage(from, to) {
    if (from === to || to < 0 || to >= store.doc.pages.length) return;
    store.update("Move page", (doc) => { const [p] = doc.pages.splice(from, 1); doc.pages.splice(to, 0, p); });
    store.setPage(to);
  },
  fitPage() {
    const items = store.items().filter((it) => !it.hidden);
    if (!items.length) return;
    // Use what the engine drew (strokes, arrowheads, text) where known, else the frames
    const boxes = items.map((it) => canvas.els.get(it.id)?.bbox || itemBBox(it));
    const b = [Math.min(...boxes.map((x) => x[0])), Math.min(...boxes.map((x) => x[1])),
      Math.max(...boxes.map((x) => x[2])), Math.max(...boxes.map((x) => x[3]))];
    // A journal figure keeps its column width; only the height is cropped
    const journalPage = !!store.page().preset?.journal;
    store.update(journalPage ? "Fit page height to content" : "Fit page to content", (doc) => {
      const p = doc.pages[store.pageIndex];
      if (journalPage) {
        for (const it of p.items) shiftItem(it, clone(it), 0, -b[1]);
        shiftGuides(p, 0, -b[1]);
        p.height = b[3] - b[1];
      } else {
        for (const it of p.items) shiftItem(it, clone(it), -b[0], -b[1]);
        shiftGuides(p, -b[0], -b[1]);
        p.width = b[2] - b[0];
        p.height = b[3] - b[1];
        delete p.preset;
      }
    });
    canvas.fit();
    announce(journalPage ? "Page height fitted to the content; the column width is kept"
      : "Page fitted to its content, with no margin");
  },
};

function dirOf(p) { return p ? p.replace(/[\\/][^\\/]*$/, "") : ""; }
function reidPage(p) { p.id = uid("pg"); p.items.forEach(reid); return p; }

// Commands --------------------------------------------------------------------------------

const M = isMac ? "⌘" : "Ctrl+";
const S = isMac ? "⇧" : "Shift+";
function cmd(label, run, keys = null, match = null, short = null) { return { label, run, keys, match, short }; }
const mod = (e) => (isMac ? e.metaKey : e.ctrlKey);
const plain = (e) => !e.metaKey && !e.ctrlKey && !e.altKey;
const key = (k, { shift = false } = {}) => (e) => mod(e) && e.shiftKey === shift && !e.altKey && e.key.toLowerCase() === k;
const tool = (t, label, k, short) => cmd(label, () => canvas.setTool(t), k ? k.toUpperCase() : null,
  k ? (e) => plain(e) && !e.shiftKey && e.key.toLowerCase() === k : null, short);

app.commands = {
  new: cmd("New document", () => app.newDocument(), `${M}N`, key("n"), "New"),
  open: cmd("Open document or PowerPoint deck", () => app.open(), `${M}O`, key("o"), "Open"),
  save: cmd("Save", () => app.save(), `${M}S`, key("s"), "Save"),
  saveAs: cmd("Save as", () => app.save(true), `${M}${S}S`, key("s", { shift: true })),
  export: cmd("Export", () => panels.exportDialog(), `${M}E`, key("e"), "Export"),
  preflight: cmd("Check before export", () => panels.preflightDialog(), `${M}${S}E`, key("e", { shift: true }), "Check"),
  insertPicture: cmd("Insert picture", () => app.insertPicture(), "I", (e) => plain(e) && !e.shiftKey && e.key.toLowerCase() === "i", "Picture"),
  undo: cmd("Undo", () => { const l = store.undo(); announce(l ? `Undid ${l}` : "Nothing to undo"); }, `${M}Z`, key("z"), "Undo"),
  redo: cmd("Redo", () => { const l = store.redo(); announce(l ? `Redid ${l}` : "Nothing to redo"); }, `${M}${S}Z`,
    (e) => key("z", { shift: true })(e) || (!isMac && key("y")(e)), "Redo"),
  cut: cmd("Cut", () => app.copy(true), `${M}X`, key("x")),
  copy: cmd("Copy", () => app.copy(), `${M}C`, key("c")),
  paste: cmd("Paste", () => app.paste(), `${M}V`, key("v")),
  duplicate: cmd("Duplicate", () => app.duplicate(), `${M}D`, key("d")),
  delete: cmd("Delete", () => app.deleteSelection(), "Delete", (e) => plain(e) && (e.key === "Delete" || e.key === "Backspace")),
  selectAll: cmd("Select all", () => { store.select(store.items().filter((i) => !i.locked).map((i) => i.id)); announce(`${store.selection.length} objects selected`); }, `${M}A`, key("a")),
  group: cmd("Group", () => app.group(), `${M}G`, key("g")),
  ungroup: cmd("Ungroup", () => app.ungroup(), `${M}${S}G`, key("g", { shift: true })),
  bringToFront: cmd("Bring to front", () => app.reorder("front"), `${M}${S}]`, (e) => mod(e) && e.shiftKey && (e.key === "]" || e.key === "}")),
  bringForward: cmd("Bring forward", () => app.reorder("forward"), `${M}]`, (e) => mod(e) && !e.shiftKey && e.key === "]"),
  sendBackward: cmd("Send backward", () => app.reorder("backward"), `${M}[`, (e) => mod(e) && !e.shiftKey && e.key === "["),
  sendToBack: cmd("Send to back", () => app.reorder("back"), `${M}${S}[`, (e) => mod(e) && e.shiftKey && (e.key === "[" || e.key === "{")),
  alignLeft: cmd("Align left", () => app.align("left")),
  alignCenter: cmd("Align centres", () => app.align("center")),
  alignRight: cmd("Align right", () => app.align("right")),
  alignTop: cmd("Align top", () => app.align("top")),
  alignMiddle: cmd("Align middles", () => app.align("middle")),
  alignBottom: cmd("Align bottom", () => app.align("bottom")),
  distributeH: cmd("Distribute horizontally", () => app.distribute("h")),
  distributeV: cmd("Distribute vertically", () => app.distribute("v")),
  zoomIn: cmd("Zoom in", () => canvas.setZoom(canvas.zoom * 1.25), `${M}+`, (e) => mod(e) && (e.key === "=" || e.key === "+"), "Zoom in"),
  zoomOut: cmd("Zoom out", () => canvas.setZoom(canvas.zoom / 1.25), `${M}−`, (e) => mod(e) && (e.key === "-" || e.key === "_"), "Zoom out"),
  zoomFit: cmd("Fit page in window", () => canvas.fit(), `${M}0`, (e) => mod(e) && e.key === "0", "Fit"),
  zoom100: cmd("True size (100%)", () => canvas.setZoom(1), `${M}1`, (e) => mod(e) && e.key === "1"),
  toggleRulers: cmd("Show or hide the rulers", () => app.togglePref("show_rulers", "Rulers shown", "Rulers hidden"),
    `${M}R`, key("r"), "Rulers"),
  toggleGrid: cmd("Show or hide the grid", () => app.togglePref("show_grid", "Grid shown; things snap to it while it shows",
    "Grid hidden"), `${M}'`, (e) => mod(e) && !e.shiftKey && !e.altKey && (e.key === "'" || e.code === "Quote"), "Grid"),
  toggleGuides: cmd("Show or hide guides", () => app.togglePref("show_guides", "Guides shown",
    "Guides hidden; they don't snap until they're shown again"), `${M};`,
  (e) => mod(e) && !e.shiftKey && !e.altKey && (e.key === ";" || e.code === "Semicolon"), "Guides"),
  toggleSnap: cmd("Snap to guides, the grid, the page and other objects", () => app.togglePref("snap", "Snapping on",
    `Snapping off; things move freely. ${M}${S}; turns it back on`), `${M}${S};`,
  (e) => mod(e) && e.shiftKey && !e.altKey && (e.key === ";" || e.key === ":" || e.code === "Semicolon"), "Snap"),
  toolSelect: tool("select", "Select and move", "v", "Select"),
  toolText: tool("text", "Text", "t", "Text"),
  toolLabel: tool("label", "Panel label (a, b, c…)", "p", "Label"),
  toolLine: tool("line", "Line", "l", "Line"),
  toolArrow: tool("arrow", "Arrow", "a", "Arrow"),
  toolRect: tool("rect", "Rectangle", "r", "Rect"),
  toolRoundRect: tool("roundrect", "Rounded rectangle", "u", "Rounded"),
  toolEllipse: tool("ellipse", "Ellipse or circle", "o", "Ellipse"),
  toolTriangle: tool("triangle", "Triangle", null, "Triangle"),
  toolArc: tool("arc", "Arc", null, "Arc"),
  toolBracket: tool("bracket", "Bracket", null, "Bracket"),
  shapesMenu: cmd("Shapes", () => panels.toggleShapeMenu(), "S", (e) => plain(e) && !e.shiftKey && e.key.toLowerCase() === "s", "Shapes"),
  addPage: cmd("Add page", () => app.addPage(), `${M}${S}N`, key("n", { shift: true })),
  duplicatePage: cmd("Duplicate page", () => app.addPage(true)),
  deletePage: cmd("Delete page", () => app.deletePage()),
  pageUp: cmd("Move page up", () => app.movePage(store.pageIndex, store.pageIndex - 1)),
  pageDown: cmd("Move page down", () => app.movePage(store.pageIndex, store.pageIndex + 1)),
  fitPage: cmd("Fit page to content", () => app.fitPage()),
  addPoint: cmd("Add point to line", () => app.addPoint()),
  straighten: cmd("Make line straight", () => app.straighten()),
  shapeToCurve: cmd("Make editable curve", () => app.shapeToCurve()),
  replacePicture: cmd("Replace picture", () => app.replacePicture()),
  revealPicture: cmd("Show the picture's file", async () => {
    const it = store.selected()[0];
    const a = it && store.doc.assets[it.asset];
    const src = a?.variants[a.primary]?.src;
    if (src) await rpc("reveal", src); else announce("This picture is stored in the document only");
  }),
  unlinkPicture: cmd("Unlink picture", () => {
    const it = store.selected()[0];
    if (!it || it.type !== "picture") return;
    store.update("Unlink", (doc) => {
      const a = doc.assets[it.asset];
      a.auto_update = false;
      for (const v of Object.values(a.variants)) { delete v.src; delete v.src_rel; delete v.mtime; }
    });
    announce("Unlinked: the picture now uses the copy stored in the document");
  }),
  preferences: cmd("Preferences", () => panels.preferencesDialog(), `${M},`, (e) => mod(e) && e.key === ",", "Settings"),
  shortcuts: cmd("Keyboard shortcuts and help", () => panels.shortcutsDialog(), "?", (e) => plain(e) && e.key === "?", "Help"),
};

// Keyboard ----------------------------------------------------------------------------------

document.addEventListener("keydown", (e) => {
  if (document.querySelector("dialog[open]")) return;
  if (e.key === " " && !isField(e.target)) { canvas.spaceDown = true; canvas.stage.style.cursor = "grab"; e.preventDefault(); return; }
  const inField = isField(e.target);
  // In text fields only the document-level commands are ours; everything else stays native
  const always = ["save", "saveAs", "open", "new", "export"];
  for (const [name, c] of Object.entries(app.commands)) {
    if (!c.match || !c.match(e)) continue;
    if (inField && !always.includes(name)) return;
    e.preventDefault();
    app.run(name);
    return;
  }
  if (inField) return;
  const onCanvas = e.target === canvas.stage || e.target === document.body;
  if (e.key === "Escape") {
    if (canvas.cancelDrag()) announce("Cancelled the drag");
    else if (canvas.cropping) canvas.endCrop();
    else if (canvas.tool !== "select") canvas.setTool("select");
    else if (store.selection.length) { store.select([]); announce("Nothing selected"); }
    return;
  }
  if (e.key === "Enter" && canvas.tool !== "select" && onCanvas) {
    // With a drawing tool chosen, Enter places one in the middle of the view (no pointer needed)
    e.preventDefault();
    canvas.placeDefault();
    return;
  }
  if (e.key === "Enter" && store.selection.length === 1) {
    e.preventDefault();
    const it = store.selected()[0];
    if (canvas.cropping) canvas.endCrop();
    else if (it.type === "picture") canvas.startCrop(it.id);
    else if (it.type === "shape") canvas.startEdit(it.id);
    return;
  }
  if (e.key === "Tab" && onCanvas && store.items().length) {
    e.preventDefault();
    app.cycleSelection(e.shiftKey);
    return;
  }
  const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (arrows[e.key] && store.selection.length && (onCanvas || e.target.closest?.(".items"))) {
    e.preventDefault();
    const [dx, dy] = arrows[e.key];
    if (e.altKey && e.shiftKey) app.nudge(dx, dy, true);
    else app.nudge(dx * (e.shiftKey ? 10 : e.altKey ? 0.1 : 1), dy * (e.shiftKey ? 10 : e.altKey ? 0.1 : 1));
  }
});
document.addEventListener("keyup", (e) => {
  if (e.key === " ") { canvas.spaceDown = false; canvas.stage.style.cursor = ""; }
});
function isField(el) {
  return el && (el.matches?.("input, textarea, select") || el.isContentEditable);
}

// Drag and drop ------------------------------------------------------------------------------

function dropTarget(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY);
  const pageLi = el?.closest?.(".page-list li[data-index]");
  if (pageLi) {
    store.setPage(Number(pageLi.dataset.index));
    const p = store.page();
    return { point: [p.width * 0.1, p.height * 0.1] };
  }
  const r = canvas.stage.getBoundingClientRect();
  const pt = canvas.toPage(clientX - r.left, clientY - r.top);
  return { point: pt, over: canvas.itemAt(pt) };
}
// Native window: full file paths arrive from Python so the figures can stay linked
window.FA = {
  async onNativeDrop({ paths, x, y, embed, shift }) {
    const t = dropTarget(x, y);
    if (shift && t.over?.type === "picture" && paths.length === 1) {
      store.select([t.over.id]);
      return app.replacePicture(paths);
    }
    await app.placeFiles(paths, t.point, embed);
  },
};
// Browser: files arrive as data (stored in the document, without links)
document.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); document.body.classList.add("dropping"); } });
document.addEventListener("dragleave", (e) => { if (!e.relatedTarget) document.body.classList.remove("dropping"); });
document.addEventListener("drop", (e) => {
  document.body.classList.remove("dropping");
  if (!e.dataTransfer.files.length || app.info.native) return;
  e.preventDefault();
  const t = dropTarget(e.clientX, e.clientY);
  app.placeUploads([...e.dataTransfer.files], t.point);
});
document.addEventListener("paste", (e) => {
  if (isField(e.target)) return;
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
  if (files.length) { e.preventDefault(); app.placeUploads(files.map((f, i) => new File([f], f.name || `pasted-${i + 1}.png`, { type: f.type })), null); }
});

// Preferences -------------------------------------------------------------------------------

function applyPrefs(p) {
  display.units = p.units || "cm";
  const root = document.documentElement;
  root.style.setProperty("--ui-scale", p.ui_scale || 1);
  root.dataset.theme = p.theme || "system";
  document.body.classList.toggle("no-tool-labels", p.show_tool_labels === false);
  document.body.classList.toggle("reduce-motion", !!p.reduced_motion);
  canvas.defaults = p;
  if (canvas.stage) canvas.setRulers(p.show_rulers !== false);
  document.dispatchEvent(new CustomEvent("fa-prefs", { detail: p }));
}

// Start-up ------------------------------------------------------------------------------------

async function start() {
  app.info = await rpc("app_info");
  app.prefs = app.info.prefs;
  Object.assign(shapeCatalog, app.info.shapes || {});
  applyPrefs(app.prefs);
  canvas.init(document.getElementById("stage"));
  rulers.init(document.querySelector(".stage-wrap"));
  // Dragging a new guide out of a ruler shows the guides if they were hidden
  rulers.onNeedGuides = () => {
    app.prefs.show_guides = true;
    app.savePrefs({ show_guides: true }).then(() => announce("Guides shown")).catch(() => {});
  };
  panels.init(app);
  inspector.init(document.getElementById("inspector"), app);
  rpc("fonts").then((f) => { app.fonts = f; }).catch(() => {});
  store.on((what) => {
    if (what === "doc" || what === "saved") {
      const name = store.path ? store.path.split(/[\\/]/).pop() : store.doc?.meta?.title || "Untitled";
      const title = `${name}${store.dirty ? " — edited" : ""} — FigAssemble`;
      if (document.title !== title) {
        document.title = title;
        rpc("set_title", title).catch(() => {});
        rpc("confirm_close", store.dirty).catch(() => {});
      }
    }
  });
  const params = new URLSearchParams(location.search);
  if (params.get("open")) await app.open(params.get("open"));
  else {
    store.setDoc(await rpc("new_document"));
    const saved = await rpc("autosaved").catch(() => []);
    if (saved.length) offerRecovery(saved);
  }
  canvas.fit();
  if (params.get("select")) store.select(params.get("select").split(","));   // e.g. for screenshots
  setInterval(() => app.refreshLinks().catch(() => {}), 2000);
  setInterval(() => {
    if (store.dirty && store.doc) rpc("autosave", store.doc, store.autosaveKey).catch(() => {});
  }, 60000);
  window.addEventListener("beforeunload", (e) => { if (store.dirty && !app.info.native) { e.preventDefault(); e.returnValue = ""; } });
  window.FA.app = app;
  document.body.classList.add("ready");
  announce("FigAssemble is ready. Drop figure files onto the page, or press I to insert a picture.");
  if (params.get("selftest")) import("./selftest.js").then((m) => m.run(app, params));
}

function offerRecovery(saved) {
  const list = saved.map((s) => {
    const when = new Date(s.modified * 1000).toLocaleString();
    const li = document.createElement("li");
    const open = Object.assign(document.createElement("button"), { type: "button", className: "btn", textContent: `Recover (${when})` });
    open.addEventListener("click", async () => {
      document.querySelector("dialog[open]")?.close();
      const res = await rpc("open_document", s.path);
      store.setDoc(res.doc, null);
      store.dirty = true;
      canvas.fit();
    });
    li.append(open);
    return li;
  });
  const ul = document.createElement("ul");
  ul.className = "plain";
  ul.append(...list);
  const p = document.createElement("p");
  p.textContent = "FigAssemble found work that wasn't saved last time.";
  const body = document.createElement("div");
  body.append(p, ul);
  panels.dialog("Recover unsaved work?", body);
}

start().catch((err) => {
  console.error(err);
  document.body.prepend(Object.assign(document.createElement("p"), { className: "fatal", textContent: `FigAssemble couldn't start: ${err.message}` }));
});

export { app };

// Start-up and commands: one registry drives the keyboard, the toolbar and the shortcuts list.

// Collected for the start-up smoke test (and handy when debugging in the app window)
window.__faErrors = [];
window.addEventListener("error", (e) => window.__faErrors.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => window.__faErrors.push(String(e.reason?.message || e.reason)));

import { rpc } from "./api.js";
import {
  canvas, copyItems, detachMoved, detachRegion, findDeep, rotateItem, scaleItem, shiftGuides, shiftItem, withRegionLines,
} from "./canvas.js";
import { contextMenu } from "./contextmenu.js";
import { gridFor } from "./gridlayout.js";
import { canHold, copiesOf, editGroup, finishEdits, makeSymbol, placedItems, symbolOf } from "./symbols.js";
import { middle, panelAt } from "./labels.js";
import { button, inspector } from "./inspector.js";
import { panels } from "./panels.js";
import { rulers } from "./rulers.js";
import { splitters } from "./splitters.js";
import { store } from "./store.js";
import { applyStyle, styleOf } from "./styles.js";
import { barFrame, niceLength, pageScale, pxPerPt, scaleText } from "./scalebar.js";
import { stackLevels } from "./brackets.js";
import { colourHolders, swatchById } from "./swatches.js";
import { PARA_FORMAT, RUN_FORMAT, applyTextStyle, applyToParagraph, formatOf, restyle, setFormat } from "./textstyles.js";
import { KEYS as LOOK, applyObjectStyle, formatOf as lookOf, restyle as restyleObjects } from "./objectstyles.js";
import { canMove, containerAt, moveItems } from "./layers.js";
import {
  MOD, announce, clone, describeItem, display, h, isMac, itemBBox, itemLabel, itemsBBox, lengthText, lineMidpoints, shapeCatalog, uid,
} from "./util.js";

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
  // Interface state (the open tab, folded sections) is kept without redrawing anything
  rememberUi(p) {
    Object.assign(this.prefs, p);
    rpc("prefs_set", p).catch(() => {});
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
    // A PowerPoint deck: its slides to open first (all of them if there's just one)
    let slides = null;
    if (isDeck(path)) {
      slides = await this.chooseSlides(path, { verb: "Open" });
      if (!slides) return;
    }
    announce("Opening…");
    const res = await rpc("open_document", path, slides);
    store.setDoc(finishEdits(res.doc), res.path);
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

  async chooseReportBase() {
    const title = `${(store.doc.meta?.title || "figure").replace(/[^\w.-]+/g, "_")}_report`;
    const strip = (p) => p.replace(/\.(html?|md|csv|pdf)$/i, "");
    if (this.info.native) {
      const p = await rpc("save_dialog", `${title}.html`, dirOf(store.path));
      return p ? strip(p) : null;
    }
    const p = await panels.pathDialog("Write the report to (path without extension)", `${dirOf(store.path) || "~/Desktop"}/${title}`);
    return p ? strip(p) : null;
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
    // Made first, so the new pictures end up selected
    const items = ok.map((r) => {
      const [w, h] = r.asset.page_sizes ? r.asset.page_sizes[0] : r.asset.size_pt;
      const it = { id: uid("it"), type: "picture", name: r.asset.name, asset: r.asset_id, page_index: 0,
        frame: [x, y, w, h], crop: [0, 0, 0, 0], rot: 0, flip_h: false, flip_v: false, opacity: 1, source: "auto" };
      // A microscope image's own scale (ImageJ, OME-TIFF), for scale bars
      const cal = r.asset.variants[r.asset.primary]?.calibration, ppp = pxPerPt(r.asset);
      if (cal && ppp) it.scale = { per_pt: cal.per_px * ppp, unit: cal.unit, how: "file" };
      x += 12; y += 12;
      return it;
    });
    store.update(`Place ${ok.length === 1 ? ok[0].asset.name : `${ok.length} pictures`}`, (doc) => {
      for (const r of ok) doc.assets[r.asset_id] = r.asset;
      store.container(doc).push(...items);
    }, { select: items.map((i) => i.id) });
    const warnings = ok.flatMap((r) => r.warnings || []).concat(errors);
    const copies = ok.map((r) => Object.keys(r.asset.variants).map((k) => k.toUpperCase()).join("+"));
    announce(`Placed ${ok.length} at true size (${how}; ${copies.join(", ")})`);
    if (warnings.length) panels.reportDialog("Placed, with notes", warnings);
  },

  // PowerPoint slides and shapes -------------------------------------------------------------

  // A deck's slides to bring in: the slide picker when it has more than one (null if cancelled)
  async chooseSlides(key, how) {
    announce("Reading the slides…");
    let deck;
    try {
      deck = await rpc("deck_slides", key);
    } catch (err) {
      panels.reportDialog("Couldn't read the slides", [String(err.message || err)]);
      return null;
    }
    if (!deck.slides.length) {
      panels.reportDialog("No slides", [`“${deck.name}” has no slides.`]);
      return null;
    }
    if (deck.slides.length === 1) return [1];
    return panels.slidePicker(deck, how);
  },
  // A deck dropped on the window: its chosen slides as new pages where it was dropped in the
  // Pages list, else their objects onto the page where it was dropped
  async addDeck(path, t) {
    const where = t.list ? `as pages ${slideGap(t.pageAt)}` : "onto this page";
    const numbers = await this.chooseSlides(path, { verb: "Add", where });
    if (!numbers) return;
    const got = await rpc("deck_pages", path, numbers);
    this.addSlides(got, t.list ? { pageAt: t.pageAt } : { at: t.point }, "Add");
    if (got.report.length) panels.reportDialog(`Added from ${got.name}`, got.report);
  },
  // Slides into the figure (deck_pages; or pasted or dropped, the same shape): as new pages at a
  // place in the Pages list (to.pageAt), or their objects onto this page, at a point (to.at),
  // else where they were on the slide; several slides' objects 12 pt apart. One undo step.
  addSlides(got, to, verb) {
    const n = got.pages.length, s = n === 1 ? "" : "s", done = verb === "Paste" ? "Pasted" : "Added";
    if (!n) return announce("No slides to add");
    if (to.pageAt !== undefined) {
      const pages = got.pages.map((p) => reidPage(p));
      store.update(`${verb} ${n} slide${s} as page${s}`, (doc) => {
        Object.assign(doc.assets, got.assets);
        doc.pages.splice(to.pageAt, 0, ...pages);
      });
      store.setPage(to.pageAt);
      canvas.fit();
      return announce(`${done} ${n} slide${s} as page${s} ${to.pageAt + 1}${n > 1 ? ` to ${to.pageAt + n}` : ""}`);
    }
    const items = [];
    got.pages.forEach((p, k) => {
      // What's on the slide (PowerPoint keeps things parked beside a slide too)
      const mine = copyItems(p.items.filter((it) => {
        const b = itemBBox(it);
        return b[2] > 0 && b[3] > 0 && b[0] < p.width && b[1] < p.height;
      }));
      const b = itemsBBox(mine);
      if (!b) return;
      const [dx, dy] = to.at ? [to.at[0] - b[0] + 12 * k, to.at[1] - b[1] + 12 * k] : [12 * k, 12 * k];
      if (dx || dy) for (const it of mine) shiftItem(it, clone(it), dx, dy);
      items.push(...mine);
    });
    if (!items.length) return announce(`Nothing to ${verb.toLowerCase()}: the slide${s} ${n === 1 ? "is" : "are"} empty`);
    store.update(`${verb} ${n === 1 ? "slide" : `${n} slides`} from PowerPoint`, (doc) => {
      Object.assign(doc.assets, got.assets);
      store.container(doc).push(...items);
    }, { select: items.map((i) => i.id) });
    announce(`${done} ${items.length} object${items.length === 1 ? "" : "s"} from ${n === 1 ? "a slide" : `${n} slides`}${pictureNote(got.report)}`);
  },
  // Shapes copied (or dragged) out of PowerPoint: where they were on the slide, else at a point
  addShapes(r, at, verb) {
    const items = copyItems(r.items), b = itemsBBox(items);
    if (!items.length) return announce("Nothing to add: PowerPoint's shapes had nothing FigAssemble can draw");
    if (at && b) for (const it of items) shiftItem(it, clone(it), at[0] - b[0], at[1] - b[1]);
    store.update(`${verb} from PowerPoint`, (doc) => {
      Object.assign(doc.assets, r.assets);
      store.container(doc).push(...items);
    }, { select: items.map((i) => i.id) });
    announce(`${verb === "Paste" ? "Pasted" : "Added"} ${items.length} object${items.length === 1 ? "" : "s"} from PowerPoint${pictureNote(r.report)}`);
  },
  // Slides or shapes from PowerPoint, pasted or dropped with their contents (_office_paste)
  fromPowerPoint(r, to, verb) {
    if (r.kind === "slides") this.addSlides(r, to, verb);
    else if (r.kind === "shapes") this.addShapes(r, to.at, verb);
    else return;
    const notes = r.report.filter((l) => l.includes("note:"));
    if (notes.length) panels.reportDialog(`${verb === "Paste" ? "Pasted" : "Added"} from PowerPoint, with notes`, r.report);
  },
  // Slides dragged out of PowerPoint: found in the decks it has open, as last saved, and brought
  // in from there (asking which deck when several have them)
  async dropPowerPointSlides(refs, t) {
    const { found } = await rpc("powerpoint_slides", refs, this.testDecks ?? null);
    if (!found.length) {
      return panels.reportDialog("Those slides weren't found", [
        "FigAssemble reads slides dragged out of PowerPoint from their deck as it was last saved, and no deck PowerPoint "
        + "has open has them saved yet.",
        `Save the deck in PowerPoint and drag the slides again, or copy them (${MOD}C) and paste them here (${MOD}V).`]);
    }
    let pick = found[0];
    if (found.length > 1) {
      [pick] = (await panels.pickCards({
        title: "Which deck are the slides from?",
        hint: `${found.length} decks open in PowerPoint have slides like those. Choose the one you dragged from.`,
        label: "Decks", one: true, verb: () => "Add slides",
        cards: found.map((f) => ({ value: f, label: f.name, sub: `Slide ${f.numbers.join(", ")}`,
          thumb: () => rpc("deck_thumbnail", f.path, f.numbers[0]) })),
      })) || [];
      if (!pick) return;
    }
    const got = await rpc("deck_pages", pick.path, pick.numbers);
    this.addSlides(got, t.list ? { pageAt: t.pageAt } : { at: t.point }, "Add");
    panels.reportDialog(`Added from ${pick.name}`, [`From ${pick.name} as last saved in PowerPoint: anything changed `
      + "since then isn't included.", ...got.report]);
  },
  // A deck dropped in the browser (no path to it, only its bytes)
  async addDeckUpload(file, t) {
    const b64 = await new Promise((res) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result).split(",")[1]);
      r.readAsDataURL(file);
    });
    await this.addDeck(await rpc("deck_upload", file.name, b64), t);
  },
  // Where a dragged thing would go, shown while it's over the window (null: it's gone). kind:
  // "files" (pictures), "deck" (a deck file), "slides" or "shapes" (out of PowerPoint): over the
  // Pages list, the page they'd go on, or for slides the gap they'd go in as pages
  showDropSpot(info) {
    const list = panels.pageList;
    list.querySelector(".slide-drop-line")?.remove();
    for (const li of list.querySelectorAll(".drop-target")) li.classList.remove("drop-target");
    const t = info && dropTarget(info.x, info.y);
    document.body.classList.toggle("dropping", !!t && !t.list);
    const hint = document.querySelector(".drop-hint");
    if (hint) {
      hint.textContent = info?.kind === "deck" || info?.kind === "slides" ? "Drop to put the slides' objects on this page"
        : info?.kind === "shapes" ? "Drop to put the shapes on this page" : "Drop to place at true size";
    }
    if (!t?.list) return;
    if (info.kind === "files" || info.kind === "shapes") {
      list.querySelector(`li[data-index="${t.pageIndex ?? store.pageIndex}"]`)?.classList.add("drop-target");
      return;
    }
    const rows = list.querySelectorAll("li[data-index]"), row = rows[t.pageAt];
    const y = row ? row.offsetTop : rows.length ? rows[rows.length - 1].offsetTop + rows[rows.length - 1].offsetHeight : 0;
    list.append(h("div", { class: "slide-drop-line", style: { top: `${y}px` }, "aria-hidden": "true" }));
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
    let sel = store.selected().filter((it) => !it.locked);
    if (!sel.length) return;
    if (!resize) sel = withRegionLines(sel);   // an area fill moves with its lines and shapes
    else sel = sel.filter((it) => it.geom !== "region");
    store.update(resize ? "Resize" : "Move", (doc) => {
      if (!resize) detachMoved(sel.map((x) => findDeep(doc.pages[store.pageIndex].items, x.id)));
      for (const s of sel) {
        const it = findDeep(doc.pages[store.pageIndex].items, s.id);
        if (resize && it.frame) {
          it.frame[2] = Math.max(it.frame[2] + dx, 0.5);
          it.frame[3] = Math.max(it.frame[3] + dy, 0.5);
        } else if (!resize) shiftItem(it, clone(it), dx, dy);
      }
    });
    if (!resize) this.noteTransform({ kind: "move", dx, dy });
    if (sel.length === 1) announce(describeItem(store.selected()[0], store.doc));
  },
  // Swatches (swatches.js): the figure's named colours, and palettes kept in your library -------

  addSwatch(color, name = null) {
    const id = uid("sw");
    store.update("Add swatch", (doc) => { doc.swatches = [...(doc.swatches || []), { id, name: name || color.toUpperCase(), color }]; });
    announce(`Added the swatch ${name || color.toUpperCase()}`);
    return id;
  },
  addPalette(colours, title) {
    store.update(`Add ${title} swatches`, (doc) => {
      doc.swatches = doc.swatches || [];
      for (const [name, color] of colours) {
        if (!doc.swatches.some((s) => s.name === name && s.color === color)) doc.swatches.push({ id: uid("sw"), name, color });
      }
    });
    announce(`Added the ${title} swatches`);
  },
  // Every colour linked to the swatch changes with it, in one step
  setSwatchColour(id, color) {
    store.update("Swatch colour", (doc) => {
      const sw = swatchById(doc, id);
      if (!sw) return;
      sw.color = color;
      for (const c of colourHolders(doc)) if (c.swatch === id) c.color = color;
    });
  },
  renameSwatch(id, name) {
    store.update("Rename swatch", (doc) => { const sw = swatchById(doc, id); if (sw) sw.name = name; });
  },
  // Objects keep the colour; only the link goes
  deleteSwatch(id) {
    store.update("Delete swatch", (doc) => {
      doc.swatches = (doc.swatches || []).filter((s) => s.id !== id);
      for (const c of colourHolders(doc)) if (c.swatch === id) delete c.swatch;
    });
  },
  // The colours the figure uses, as swatches, each linked to the objects that use it
  addUsedColours() {
    let added = 0;
    store.update("Swatches from the figure", (doc) => {
      doc.swatches = doc.swatches || [];
      const free = colourHolders(doc).filter((c) => c.color && !c.swatch);
      for (const color of new Set(free.map((c) => c.color.toLowerCase()))) {
        let sw = doc.swatches.find((x) => x.color.toLowerCase() === color);
        if (!sw) { sw = { id: uid("sw"), name: color.toUpperCase(), color }; doc.swatches.push(sw); added++; }
        for (const c of free) if (c.color.toLowerCase() === color) c.swatch = sw.id;
      }
    });
    announce(`Added ${added} swatch${added === 1 ? "" : "es"} from the figure's colours`);
  },
  async savePalette(name) {
    const colours = (store.doc.swatches || []).map((s) => [s.name, s.color]);
    await this.savePrefs({ swatch_library: [...(this.prefs.swatch_library || []).filter((p) => p.name !== name), { name, colours }] });
    announce(`Saved ${name} to your library`);
  },
  async deletePalette(name) {
    await this.savePrefs({ swatch_library: (this.prefs.swatch_library || []).filter((p) => p.name !== name) });
  },
  // Object styles (objectstyles.js): named looks for lines and shapes; objects using one follow
  // it, except where changed
  async newObjectStyle() {
    const it = store.selected().find((x) => x.type === "line" || x.type === "shape");
    if (!it) return announce("Select a line or shape to make a style from");
    const name = await panels.promptDialog("New object style", "Style name", "", "For example: Thin grey line, Highlight box");
    if (!name) return;
    const style = { id: uid("os"), name, ...lookOf(it) };
    store.update("New object style", (doc) => {
      doc.object_styles = [...(doc.object_styles || []), style];
      for (const id of store.selection) {
        const t = findDeep(doc.pages[store.pageIndex].items, id);
        if (t) applyObjectStyle(t, style);
      }
    });
    announce(`Made the object style ${name}`);
  },
  useObjectStyle(id) {
    const style = (store.doc.object_styles || []).find((x) => x.id === id);
    store.update(style ? "Object style" : "No object style", (doc) => {
      for (const sid of store.selection) {
        const t = findDeep(doc.pages[store.pageIndex].items, sid);
        if (!t) continue;
        if (style) applyObjectStyle(t, style);
        else delete t.object_style;
      }
    });
  },
  // The style takes this object's look; objects using it follow, keeping their own changes
  redefineObjectStyle(id, item) {
    store.update("Update object style", (doc) => {
      const st = (doc.object_styles || []).find((x) => x.id === id);
      if (!st) return;
      const old = clone(st), f = lookOf(item);
      for (const k of LOOK) if (k in f) st[k] = f[k];
      restyleObjects(doc, old, st);
    });
    announce("Updated the style, and the objects using it");
  },
  clearObjectChanges() {
    store.update("Clear changes", (doc) => {
      for (const sid of store.selection) {
        const t = findDeep(doc.pages[store.pageIndex].items, sid);
        const st = t?.object_style && (doc.object_styles || []).find((x) => x.id === t.object_style);
        if (st) applyObjectStyle(t, st);
      }
    });
  },
  renameObjectStyle(id, name) {
    store.update("Rename object style", (doc) => { const st = (doc.object_styles || []).find((x) => x.id === id); if (st) st.name = name; });
  },
  // The objects keep their look; only the link goes
  deleteObjectStyle(id) {
    store.update("Delete object style", (doc) => {
      doc.object_styles = (doc.object_styles || []).filter((x) => x.id !== id);
      const walk = (items) => items.forEach((it) => {
        if (it.type === "group") walk(it.items);
        if (it.object_style === id) delete it.object_style;
      });
      for (const pg of [...doc.pages, ...(doc.symbols || [])]) walk(pg.items);
    });
  },
  // Text styles (textstyles.js): named formats; text using one follows it, except where changed

  async newTextStyle() {
    const it = store.selected().find((x) => x.text?.paragraphs?.length);
    if (!it) { announce("Select some text to make a style from"); return; }
    const name = await panels.promptDialog("New text style", "Style name", "", "For example: Panel label, Axis note");
    if (!name) return;
    const style = { id: uid("ts"), name, ...formatOf(it) };
    store.update("New text style", (doc) => {
      doc.text_styles = [...(doc.text_styles || []), style];
      for (const id of store.selection) {
        const t = findDeep(doc.pages[store.pageIndex].items, id);
        if (t?.text) applyTextStyle(t, style);
      }
    });
    announce(`Made the text style ${name}`);
  },
  applyTextStyle(id) {
    const style = (store.doc.text_styles || []).find((x) => x.id === id);
    store.update(style ? "Text style" : "No text style", (doc) => {
      for (const sid of store.selection) {
        const t = findDeep(doc.pages[store.pageIndex].items, sid);
        if (!t?.text) continue;
        if (style) applyTextStyle(t, style);
        else for (const p of t.text.paragraphs) delete p.style;
      }
    });
  },
  // The style takes this text's format; text using it follows, keeping its own changes
  redefineTextStyle(id, item) {
    store.update("Update text style", (doc) => {
      const st = (doc.text_styles || []).find((x) => x.id === id);
      if (!st) return;
      const old = clone(st), f = formatOf(item);
      for (const k of [...RUN_FORMAT, ...PARA_FORMAT]) setFormat(st, k, f[k]);
      restyle(doc, old, st);
    });
    announce("Updated the style, and the text using it");
  },
  // Back to the style, everywhere in the selected text
  clearTextChanges() {
    store.update("Clear text changes", (doc) => {
      for (const sid of store.selection) {
        const t = findDeep(doc.pages[store.pageIndex].items, sid);
        for (const p of t?.text?.paragraphs || []) {
          const st = p.style && (doc.text_styles || []).find((x) => x.id === p.style);
          if (st) applyToParagraph(p, st);
        }
      }
    });
  },
  renameTextStyle(id, name) {
    store.update("Rename text style", (doc) => { const st = (doc.text_styles || []).find((x) => x.id === id); if (st) st.name = name; });
  },
  // The text keeps its format; only the link goes
  deleteTextStyle(id) {
    store.update("Delete text style", (doc) => {
      doc.text_styles = (doc.text_styles || []).filter((x) => x.id !== id);
      for (const pg of [...doc.pages, ...(doc.symbols || [])]) {
        const walk = (items) => items.forEach((it) => {
          if (it.type === "group") walk(it.items);
          for (const p of it.text?.paragraphs || []) if (p.style === id) delete p.style;
        });
        walk(pg.items);
      }
    });
  },
  // Fonts: every run (and text style) in that font, on every page, in another (the Fonts dialog)
  replaceFont(from, to) {
    let n = 0;
    const walk = (items) => {
      for (const it of items) {
        if (it.type === "group") walk(it.items);
        for (const p of it.text?.paragraphs || []) for (const r of p.runs || []) if (r.font === from) { r.font = to; n++; }
      }
    };
    store.update("Replace font", (doc) => {
      doc.pages.forEach((pg) => walk(pg.items));
      for (const sym of doc.symbols || []) walk(sym.items);
      for (const st of doc.text_styles || []) if (st.font === from) st.font = to;
    });
    announce(`Replaced ${from} with ${to}${n ? "" : " (nothing used it)"}`);
  },
  // Clipping masks, as in Illustrator: the top selected shape clips the others, kept together as
  // a group whose last part is that shape (drawn only as the clip); Release separates them again
  makeClipMask() {
    const ids = new Set(store.selection);
    const sel = store.scopeItems().filter((it) => ids.has(it.id));
    if (sel.length < 2) { announce("Select the objects and, on top of them, the shape to clip them with"); return; }
    const top = sel[sel.length - 1];
    if (top.type !== "shape" || top.geom === "region") { announce("The top object has to be a shape: it's the one that clips"); return; }
    const g = { id: uid("it"), type: "group", name: "", clip: true, items: [] };
    store.update("Make clipping mask", (doc) => {
      const items = store.container(doc);
      const at = Math.max(...items.map((it, i) => (ids.has(it.id) ? i : -1)));
      g.items = items.filter((it) => ids.has(it.id));
      const rest = items.filter((it) => !ids.has(it.id) || it === items[at]);
      rest.splice(rest.indexOf(items[at]), 1, g);
      items.splice(0, items.length, ...rest);
    }, { select: [g.id] });
    announce(`${itemLabel(top, store.doc)} now clips ${sel.length - 1} object${sel.length === 2 ? "" : "s"}. Double-click it to move them within it`);
  },
  releaseClipMask() {
    const masks = store.selected().filter((it) => it.type === "group" && it.clip);
    if (!masks.length) { announce("Select a clipping mask to release"); return; }
    const kids = [];
    store.update("Release clipping mask", (doc) => {
      const items = store.container(doc);
      for (const m of masks) {
        const i = items.findIndex((it) => it.id === m.id);
        kids.push(...items[i].items.map((c) => c.id));
        items.splice(i, 1, ...items[i].items);
      }
    }, { select: kids });
    announce("Released: the shape and what it clipped are separate again");
  },
  // Scale bars (scalebar.js) ---------------------------------------------------------------

  // A picture's scale: the real length of one point of its source (a raster's pixel size, typed,
  // converts to it); scale bars on it follow
  setPictureScale(id, perPt, unit, how) {
    store.update("Picture scale", (doc) => {
      const p = findDeep(doc.pages[store.pageIndex].items, id);
      if (!p) return;
      if (perPt > 0) p.scale = { per_pt: perPt, unit, how };
      else delete p.scale;
    });
    const pic = store.item(id);
    if (pic?.scale) announce(`Scale: ${scaleText(pic, store.doc.assets[pic.asset])}`);
  },
  // A bar a round length long, just inside the picture's bottom right corner, white on a
  // photograph or micrograph and black on a plot
  addScaleBar(picId = store.selected().find((it) => it.type === "picture")?.id) {
    const pic = picId && store.item(picId), asset = pic && store.doc.assets[pic.asset];
    if (!pic) { announce("Select a picture to add a scale bar to"); return; }
    if (!pic.scale?.per_pt) { announce("Give the picture a scale first, in its Picture tab: type a pixel's size or measure a known length"); return; }
    const unit = pic.scale.unit, length = niceLength(pic, asset, unit);
    const inset = Math.min(pic.frame[2], pic.frame[3]) * 0.05;
    const bar = { id: uid("it"), type: "scalebar", picture: pic.id, length, unit, thickness: 2, size: 6, label: "above", bold: false,
      color: pxPerPt(asset) ? "#ffffff" : "#000000", anchor: { corner: "br", dx: -inset, dy: -inset }, frame: [0, 0, 1, 1] };
    bar.frame = barFrame(bar, pic, asset);
    store.update("Add scale bar", (doc) => {
      const items = store.container(doc), at = items.findIndex((it) => it.id === pic.id);
      items.splice(at < 0 ? items.length : at + 1, 0, bar);   // just above its picture
    }, { select: [bar.id] });
    announce(`Added a ${length} ${unit} scale bar to ${itemLabel(pic, store.doc)}`);
  },
  measureScale() {
    const pic = store.selected().find((it) => it.type === "picture");
    if (!pic) { announce("Select a picture to measure on"); return; }
    canvas.startMeasure(pic.id);
  },
  // A line drawn on a picture along something of known length: its real length sets the scale
  async measured(picId, lenPage) {
    const pic = store.item(picId), asset = pic && store.doc.assets[pic.asset];
    if (!pic) return;
    const answer = await panels.promptDialog("How long is the line you drew?", "Its real length", "",
      `For example 100 µm (or just a number, in ${pic.scale?.unit || "µm"})`);
    if (!answer) return;
    const m = /^\s*([0-9]*[.,]?[0-9]+(?:e[-+]?\d+)?)\s*(nm|µm|um|micron|microns|mm|cm|m)?\s*$/i.exec(answer);
    const value = m && parseFloat(m[1].replace(",", "."));
    if (!(value > 0)) { announce(`“${answer}” isn't a length: type a number and a unit, such as 100 µm`); return; }
    const said = m[2]?.toLowerCase();
    const unit = { um: "µm", micron: "µm", microns: "µm" }[said] || said || pic.scale?.unit || "µm";
    this.setPictureScale(pic.id, value / (lenPage / pageScale(pic, asset)), unit, "measured");
  },
  // Zoom insets (zoom.js): a box on a picture, the area enlarged beside it, and two lines between
  // them, all in one colour (Okabe-Ito's orange shows on dark images and white pages alike)
  addZoomInset(picId, rect) {
    const pic = store.item(picId);
    if (!pic) return;
    const [px, py, pw, ph] = pic.frame;
    const x0 = Math.max(rect[0], px), y0 = Math.max(rect[1], py);
    const box = [x0, y0, Math.min(rect[0] + rect[2], px + pw) - x0, Math.min(rect[1] + rect[3], py + ph) - y0];
    if (!(box[2] > 0.5 && box[3] > 0.5)) return;
    const page = store.page(), colour = "#e69f00";
    const iw = Math.min(box[2] * 3, Math.max(pw, box[2] * 1.5)), ih = (iw * box[3]) / box[2];
    let [ix, iy] = [px + pw + 12, py];   // to its right if the page has room, or else below it
    if (ix + iw > page.width) [ix, iy] = [px, py + ph + 12];
    const stroke = (w) => ({ color: colour, width: w, dash: "solid", cap: "round", join: "miter", opacity: 1 });
    const boxItem = { id: uid("it"), type: "shape", geom: "rect", frame: box, rot: 0, flip_h: false, flip_v: false, fill: null,
      stroke: stroke(1), zoom: { picture: pic.id } };
    const inset = { ...clone(pic), id: uid("it"), name: `${itemLabel(pic, store.doc)}, enlarged`, frame: [ix, iy, iw, ih],
      inset: { box: boxItem.id }, border: { color: colour, width: 1 } };
    delete inset.mask;
    const lines = [0, 1].map((which) => ({ id: uid("it"), type: "line", points: [[0, 0], [1, 1]], stroke: stroke(0.75),
      arrow_start: null, arrow_end: null, zoomline: { box: boxItem.id, inset: inset.id, which } }));
    store.update("Zoom inset", (doc) => {
      const items = store.container(doc), at = items.findIndex((it) => it.id === pic.id);
      items.splice(at < 0 ? items.length : at + 1, 0, boxItem);   // the box just above its picture
      items.push(...lines, inset);
    }, { select: [inset.id] });
    announce("Added a zoom inset: drag the box to show another area, or the inset to place it");
  },
  // Significance brackets (brackets.js) stacked in tidy levels
  stackBrackets() {
    const sel = store.selected().filter((it) => it.type === "bracket" && (it.dir || "up") === "up");
    if (sel.length < 2) { announce("Select two or more brackets pointing up to stack them"); return; }
    const tops = stackLevels(sel);
    store.update("Stack brackets", (doc) => {
      for (const b of sel) {
        const it = findDeep(doc.pages[store.pageIndex].items, b.id);
        it.frame = [it.frame[0], tops.get(b.id), it.frame[2], it.frame[3]];
      }
    });
    announce(`Stacked ${sel.length} brackets`);
  },
  // Pathfinder, as in Illustrator: the selected shapes combined into one freeform shape, curves
  // kept exactly (pathfinder.py); it takes the top shape's place
  async pathfinder(how) {
    const ids = new Set(store.selection);
    const sel = store.scopeItems().filter((it) => ids.has(it.id));   // bottom to top
    const names = { unite: "Unite", minus_front: "Minus front", intersect: "Intersect", exclude: "Exclude" };
    if (sel.length < 2) { announce("Select two or more shapes to combine"); return; }
    if (sel.some((it) => it.type !== "shape" || it.geom === "region")) {
      announce("Pathfinder combines shapes (an area fill can be made an ordinary shape first)");
      return;
    }
    let shape;
    try { shape = await rpc("pathfinder", sel, how); } catch (err) { announce(err.message); return; }
    shape.id = uid("it");
    store.update(names[how], (doc) => {
      const items = store.container(doc);
      const at = Math.max(...items.map((it, i) => (ids.has(it.id) ? i : -1)));
      const rest = items.filter((it) => !ids.has(it.id) || it === items[at]);
      rest.splice(rest.indexOf(items[at]), 1, shape);
      items.splice(0, items.length, ...rest);
    }, { select: [shape.id] });
    announce(`${names[how]}: ${sel.length} shapes are now one`);
  },
  // Match sizes: the other selected objects take the key object's width (or height), keeping
  // their proportions and their top-left corners. Line widths don't scale, so the box grows in a
  // straight line with the factor: one trial scale gives the exact one
  matchSize(axis) {
    const sel = store.selected().filter((it) => !it.locked && it.geom !== "region");
    const key = this.keyObject();
    if (sel.length < 2 || !key) { announce("Select two or more objects: the others match the key object, or the first selected"); return; }
    const span = (it) => { const b = itemBBox(it); return axis === "w" ? b[2] - b[0] : b[3] - b[1]; };
    const want = span(key), others = sel.filter((it) => it.id !== key.id);
    store.update(axis === "w" ? "Same width" : "Same height", (doc) => {
      for (const o of others) {
        const it = findDeep(doc.pages[store.pageIndex].items, o.id);
        const have = span(it);
        if (!(have > 0) || Math.abs(have - want) < 1e-9) continue;
        const trial = clone(it), k1 = want / have;
        scaleItem(trial, k1, k1, [0, 0]);
        const slope = (span(trial) - have) / (k1 - 1), k = Math.abs(slope) > 1e-12 ? 1 + (want - have) / slope : k1;
        if (k > 0) scaleItem(it, k, k, [0, 0]);
      }
    });
    announce(`Made ${others.length} object${others.length === 1 ? "" : "s"} as ${axis === "w" ? "wide" : "tall"} as ${itemLabel(key, store.doc)}`);
  },
  // Align and distribute, as in Illustrator: to the selection, a key object or the page. One
  // object on its own always goes to the page. In key mode the key object stays put; it's the one
  // last clicked among the selected objects, or the first selected.
  alignMode(sel) {
    return sel.length === 1 ? "page" : this.prefs.align_to || "selection";
  },
  keyObject() {
    const id = this.keyId && store.selection.includes(this.keyId) ? this.keyId : store.selection[0];
    return id ? store.item(id) : null;
  },
  setAlignTo(mode) {
    this.rememberUi({ align_to: mode });
    for (const el of document.querySelectorAll('[data-sync="align_to"]')) el.value = mode;
    canvas.drawOverlay();
    const key = this.keyObject();
    announce(mode === "key" && key ? `Aligning to the key object, ${itemLabel(key, store.doc)}; click another selected object to change it`
      : `Aligning to the ${mode}`);
  },
  // Clicking one of several selected objects (without dragging) makes it the key object, or
  // stops it being one
  toggleKeyObject(id) {
    if (this.keyId === id && this.prefs.align_to === "key") {
      this.keyId = null;
      this.setAlignTo("selection");
      return;
    }
    this.keyId = id;
    this.setAlignTo("key");
  },
  alignTarget(sel) {
    const page = store.page(), mode = this.alignMode(sel);
    if (mode === "page") return { box: [0, 0, page.width, page.height], keep: null, mode };
    const key = mode === "key" ? this.keyObject() : null;
    if (key) return { box: itemBBox(key), keep: key.id, mode };
    return { box: itemsBBox(sel), keep: null, mode: "selection" };
  },
  align(how) {
    const sel = store.selected().filter((it) => !it.locked);
    if (!sel.length) return;
    const { box: ref, keep, mode } = this.alignTarget(sel);
    store.update("Align", (doc) => {
      detachMoved(sel.filter((x) => x.id !== keep).map((x) => findDeep(doc.pages[store.pageIndex].items, x.id)));
      for (const s of sel) {
        if (s.id === keep) continue;
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
    const words = { left: "left edges", center: "centres", right: "right edges", top: "tops", middle: "middles", bottom: "bottoms" }[how];
    announce(sel.length === 1 ? `Aligned to the page: ${how}` : `Aligned ${sel.length} objects' ${words} to the ${mode === "key" ? "key object" : mode}`);
  },
  // Spread objects so their left edges (centres, right edges, tops...) are evenly spaced; the
  // outer two stay put, or move to the page's edges when aligning to the page
  distributeBy(edge) {
    const sel = store.selected().filter((it) => !it.locked);
    const toPage = this.alignMode(sel) === "page";
    if (sel.length < (toPage ? 2 : 3)) return announce(`Select ${toPage ? "two" : "three"} or more objects to distribute`);
    const axis = ["left", "center", "right"].includes(edge) ? 0 : 1;
    const at = (b) => ({ left: b[0], right: b[2], top: b[1], bottom: b[3], center: (b[0] + b[2]) / 2, middle: (b[1] + b[3]) / 2 }[edge]);
    const boxes = sel.map((it) => ({ id: it.id, b: itemBBox(it) })).sort((p, q) => at(p.b) - at(q.b));
    const fb = boxes[0].b, lb = boxes[boxes.length - 1].b;
    let first = at(fb), last = at(lb);
    if (toPage) {
      const page = store.page(), size = axis ? page.height : page.width;
      first -= fb[axis];
      last += size - lb[axis + 2];
    }
    const step = (last - first) / (boxes.length - 1);
    store.update("Distribute", (doc) => boxes.forEach(({ id, b }, i) => {
      detachMoved([findDeep(doc.pages[store.pageIndex].items, id)]);
      const it = findDeep(doc.pages[store.pageIndex].items, id), d = first + i * step - at(b);
      shiftItem(it, clone(it), axis ? 0 : d, axis ? d : 0);
    }));
    announce(`Distributed ${sel.length} objects by their ${{ left: "left edges", center: "centres", right: "right edges", top: "tops", middle: "middles", bottom: "bottoms" }[edge]}`);
  },
  // Equal gaps between neighbours across (h) or down (v). With a gap set, exactly that gap,
  // counted out from the key object (or the first object); aligning to the page, the outer
  // objects go to the page's edges.
  distribute(axisName) {
    const sel = store.selected().filter((it) => !it.locked);
    const gap = this.prefs.spacing_gap, mode = this.alignMode(sel);
    if (sel.length < (gap != null || mode === "page" ? 2 : 3)) return announce("Select three or more objects to space evenly (two with a gap set)");
    const i0 = axisName === "h" ? 0 : 1, i1 = i0 + 2;
    const boxes = sel.map((it) => ({ id: it.id, b: itemBBox(it) })).sort((a, b) => a.b[i0] - b.b[i0]);
    const size = (b) => b[i1] - b[i0];
    const starts = new Map();
    if (gap != null) {
      const k = Math.max(0, mode === "key" ? boxes.findIndex((x) => x.id === this.keyObject()?.id) : 0);
      let pos = boxes[k].b[i1];
      for (let i = k + 1; i < boxes.length; i++) { starts.set(boxes[i].id, pos + gap); pos += gap + size(boxes[i].b); }
      pos = boxes[k].b[i0];
      for (let i = k - 1; i >= 0; i--) { pos -= gap + size(boxes[i].b); starts.set(boxes[i].id, pos); }
    } else {
      const page = store.page();
      const lo = mode === "page" ? 0 : boxes[0].b[i0];
      const hi = mode === "page" ? (i0 ? page.height : page.width) : boxes[boxes.length - 1].b[i1];
      const even = (hi - lo - boxes.reduce((n, x) => n + size(x.b), 0)) / (boxes.length - 1);
      let pos = lo;
      for (const x of boxes) { starts.set(x.id, pos); pos += size(x.b) + even; }
    }
    store.update("Distribute", (doc) => {
      detachMoved(boxes.map(({ id }) => findDeep(doc.pages[store.pageIndex].items, id)));
      for (const { id, b } of boxes) {
        const it = findDeep(doc.pages[store.pageIndex].items, id), d = starts.get(id) - b[i0];
        if (starts.has(id)) shiftItem(it, clone(it), i0 ? 0 : d, i0 ? d : 0);
      }
    });
    announce(gap != null ? `Spaced ${sel.length} objects ${lengthText(gap, true)} apart` : `Spaced ${sel.length} objects evenly`);
  },
  reorder(how) {
    const ids = new Set(store.selection);
    if (!ids.size) return;
    store.update("Arrange", (doc) => {
      const items = store.container(doc);
      // Inside a clipping mask its shape stays the top part, so it goes on clipping the rest
      const group = store.scope.length && findDeep(doc.pages[store.pageIndex].items, store.scope[store.scope.length - 1]);
      const mask = group?.clip && items.length > 1 ? items.pop() : null;
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
      if (mask) items.push(mask);
    });
    announce({ front: "Brought to front", back: "Sent to back", forward: "Brought forward", backward: "Sent backward" }[how]);
  },
  // The Objects list's Option+arrows: into the group just above the selection in the list, as its
  // back part (so the page looks the same), or out of the group it's in, just behind that group
  groupAbove() {
    const list = store.scopeItems(), top = Math.max(-1, ...store.selection.map((id) => list.findIndex((it) => it.id === id)));
    const g = top >= 0 ? list[top + 1] : null;
    return g?.type === "group" ? g : null;
  },
  moveIntoGroupAbove() {
    if (!store.selection.length) return announce("Select something to move into a group");
    const g = this.groupAbove();
    if (!g) return announce("There's no group just above it in the Objects list to move it into");
    this.moveObjects(store.selection, { path: [...store.scope, g.id], back: true });
  },
  moveOutOfGroup() {
    if (!store.selection.length) return announce("Select something to move out of its group");
    if (!store.scope.length) return announce("It isn't in a group");
    this.moveObjects(store.selection, { path: store.scope.slice(0, -1), behind: store.scope[store.scope.length - 1] });
  },
  moveObjects(ids, place) {
    const items = store.items(), to = containerAt(items, place.path)?.group;
    if (!canMove(items, ids, place)) {
      return announce(to?.editing_symbol ? "A symbol can't hold pictures, scale bars or zoom insets"
        : to?.grid ? "A grid layout doesn't take panel labels; they stay with their panels" : "It can't go there");
    }
    let moved = [];
    store.update("Move in the Objects list", (doc) => {
      moved = moveItems(doc.pages[store.pageIndex].items, ids, place);
      store.scope = place.path.slice();   // worked on where they are now (a symbol being edited goes back once left)
    });
    store.select(moved.map((it) => it.id));
    announce(`Moved ${moved.length === 1 ? itemLabel(moved[0], store.doc) : `${moved.length} objects`} ${this.placeText(place, store.items())}`);
  },
  // Where a move put objects, in words
  placeText(place, items) {
    const g = containerAt(items, place.path)?.group, name = g && itemLabel(g, store.doc);
    if (place.front) return g ? `to the front of ${name}` : "to the front";
    if (place.back) return g ? `to the back of ${name}` : "to the back";
    const x = containerAt(items, place.path)?.list.find((it) => it.id === place.behind);
    return `behind ${x ? itemLabel(x, store.doc) : "the object above"}${g ? `, in ${name}` : ""}`;
  },
  group() {
    const ids = new Set(store.selection);
    if (ids.size < 2) return announce("Select two or more objects to group");
    const g = { id: uid("it"), type: "group", name: "", items: [] };
    store.update("Group", (doc) => {
      const items = store.container(doc);
      const top = Math.max(...items.map((it, i) => (ids.has(it.id) ? i : -1)));
      g.items = items.filter((it) => ids.has(it.id));
      const rest = items.filter((it) => !ids.has(it.id) || it === items[top]);
      const at = rest.indexOf(items[top]);
      rest.splice(at, 1, g);
      items.splice(0, items.length, ...rest);
    }, { select: [g.id] });
    announce(`Grouped ${g.items.length} objects`);
  },
  // Grid layout (gridlayout.js): the selected objects grouped into rows and columns that reflow;
  // attached panel labels stay outside, with their panels
  gridLayout() {
    const parts = store.selected().filter((it) => !it.attach);
    if (parts.length < 2) return announce("Select two or more panels to lay out in a grid");
    const ids = new Set(parts.map((it) => it.id));
    const g = { id: uid("it"), type: "group", name: "", items: [], grid: gridFor(parts) };
    store.update("Grid layout", (doc) => {
      const items = store.container(doc);
      const top = Math.max(...items.map((it, i) => (ids.has(it.id) ? i : -1)));
      g.items = items.filter((it) => ids.has(it.id));
      const rest = items.filter((it) => !ids.has(it.id) || it === items[top]);
      rest.splice(rest.indexOf(items[top]), 1, g);
      items.splice(0, items.length, ...rest);
    }, { select: [g.id] });
    const rows = Math.ceil(parts.length / g.grid.cols);
    announce(`Laid out ${parts.length} panels in ${rows} row${rows === 1 ? "" : "s"} of up to ${g.grid.cols}; `
      + "set the columns and gaps in its Arrange tab");
  },
  // Equations (equations.py): LaTeX maths drawn by matplotlib as a PDF and an SVG with real text,
  // placed as a picture that keeps its maths (picture.equation {tex, size, font, family, color})
  async addEquation() {
    const tex = await panels.promptDialog("New equation", "Maths, written as in LaTeX", "",
      "For example: \\frac{\\Delta F}{F_0} or \\mathrm{OD}_{600}");
    if (!tex?.trim()) return;
    const spec = { tex: tex.trim(), size: this.prefs.text?.size || 6, font: "figure", family: this.prefs.text?.font || "Helvetica",
      color: "#000000" };
    const res = await rpc("make_equation", spec);
    if (res.error) return panels.reportDialog("This maths can't be drawn", [res.error]);
    const r = canvas.stage.getBoundingClientRect(), [cx, cy] = canvas.toPage(r.width / 2, r.height / 2);
    const [w, hh] = res.asset.size_pt;
    const pic = { id: uid("it"), type: "picture", name: "", asset: res.id, page_index: 0, frame: [cx - w / 2, cy - hh / 2, w, hh],
      crop: [0, 0, 0, 0], rot: 0, flip_h: false, flip_v: false, opacity: 1, source: "auto", equation: spec };
    store.update("Add equation", (doc) => {
      doc.assets[res.id] = res.asset;
      store.container(doc).push(pic);
    }, { select: [pic.id] });
    announce("Added the equation: change its maths, size or font in its Picture tab, or double-click it");
  },
  // Its maths, size, font or colour changed: drawn again, at the same place and scale
  async updateEquation(id, patch) {
    const it = store.item(id);
    if (!it?.equation) return;
    const spec = { ...it.equation, ...patch }, res = await rpc("make_equation", spec);
    if (res.error) return panels.reportDialog("This maths can't be drawn", [res.error]);
    const old = store.doc.assets[it.asset], k = it.frame[2] / Math.max(old.size_pt[0], 1e-9), [w, hh] = res.asset.size_pt;
    store.update("Change equation", (doc) => {
      doc.assets[res.id] = res.asset;
      const p = findDeep(doc.pages[store.pageIndex].items, id);
      p.asset = res.id;
      p.equation = spec;
      p.frame = [p.frame[0], p.frame[1], w * k, hh * k];
      p.crop = [0, 0, 0, 0];
    });
  },
  async editEquation(id = store.selected()[0]?.id) {
    const it = store.item(id);
    if (!it?.equation) return announce("Select an equation");
    const tex = await panels.promptDialog("Edit equation", "Maths, written as in LaTeX", it.equation.tex);
    if (tex?.trim() && tex.trim() !== it.equation.tex) await this.updateEquation(id, { tex: tex.trim() });
  },
  // Elbow connectors: lines in level and upright stretches, their corners worked out from their
  // ends (canvas.elbowRoute), or straight again
  setRoute(route) {
    const lines = store.selected().filter((it) => it.type === "line");
    if (!lines.length) return announce("Select a line or arrow");
    store.update(route === "elbow" ? "Elbow connector" : "Straight line", (doc) => {
      for (const l of lines) {
        const it = findDeep(doc.pages[store.pageIndex].items, l.id);
        it.points = [it.points[0], it.points[it.points.length - 1]];
        delete it.curve;
        delete it.elbow;
        if (route === "elbow") it.route = "elbow";
        else delete it.route;
      }
    });
    announce(route === "elbow" ? "An elbow connector now: drag the handle on its middle stretch to move it" : "A straight line now");
  },
  // Ready-made shapes as freeform shapes of the same outline (resolve.shape_to_custom), their
  // points then editable (pen.js)
  async makeEditable() {
    const shapes = store.selected().filter((it) => it.type === "shape" && !it.textbox && it.geom !== "custom" && it.geom !== "region");
    if (!shapes.length) return announce("Select a shape to make editable");
    const made = await Promise.all(shapes.map((it) => rpc("shape_to_custom", it)));
    store.update("Make editable shape", (doc) => {
      const items = doc.pages[store.pageIndex].items;
      for (const m of made) {
        const old = findDeep(items, m.id);
        if (old) { for (const k of Object.keys(old)) delete old[k]; Object.assign(old, m); }
      }
    });
    if (made.length === 1) canvas.startPointEdit(made[0].id);
    else announce(`Made ${made.length} shapes editable: double-click one to edit its points`);
  },
  // Symbols (symbols.js): the selected objects made one symbol, used again by copying its copy
  makeSymbol() {
    const sel = store.selected();
    if (!sel.length) return announce("Select the objects to make a symbol of");
    if (!sel.every(canHold)) return announce("A symbol can hold shapes, lines, text and brackets, not pictures");
    const { sym, copy } = makeSymbol(store.doc, sel);
    const ids = new Set(sel.map((it) => it.id));
    store.update("Make symbol", (doc) => {
      doc.symbols = [...(doc.symbols || []), sym];
      const items = store.container(doc), top = Math.max(...items.map((it, i) => (ids.has(it.id) ? i : -1)));
      const rest = items.filter((it) => !ids.has(it.id) || it === items[top]);
      rest.splice(rest.indexOf(items[top]), 1, copy);
      items.splice(0, items.length, ...rest);
    }, { select: [copy.id] });
    announce(`Made ${sym.name}: copy it to use it again, and double-click any copy to change them all`);
  },
  // Editing in place: the copy becomes a group of the symbol's objects, worked on inside it;
  // leaving the group puts them back in the symbol
  editSymbol(id = store.selected()[0]?.id) {
    const copy = id && store.item(id), sym = copy?.type === "symbol" && symbolOf(store.doc, copy.symbol);
    if (!sym) return announce("Select a copy of a symbol to edit it");
    const g = editGroup(copy, sym);
    store.scope = [...store.scope, g.id];   // inside it from the start, so it isn't put back at once
    store.update("Edit symbol", (doc) => {
      const items = store.container(doc), i = items.findIndex((it) => it.id === id);
      items.splice(i, 1, g);
    }, { select: [] });
    canvas.markScope();
    const n = copiesOf(store.doc, sym.id).length + 1;
    announce(`Editing ${sym.name} at its own size; ${n === 1 ? "its copy changes" : `all ${n} copies change`} when you leave (Escape)`);
  },
  breakSymbol() {
    const copies = store.selected().filter((it) => it.type === "symbol" && symbolOf(store.doc, it.symbol));
    if (!copies.length) return announce("Select a copy of a symbol");
    const out = [];
    store.update("Break link to symbol", (doc) => {
      const items = store.container(doc);
      for (const c of copies) {
        const parts = placedItems(c, symbolOf(doc, c.symbol));
        const g = parts.length === 1 ? parts[0] : { id: uid("it"), type: "group", name: c.name || "", items: parts };
        items.splice(items.findIndex((it) => it.id === c.id), 1, g);
        out.push(g.id);
      }
    }, { select: out });
    announce(copies.length === 1 ? "It's its own objects now, no longer changing with the symbol" : `Broke ${copies.length} links`);
  },
  placeSymbol(id) {
    const sym = symbolOf(store.doc, id);
    if (!sym) return;
    const r = canvas.stage.getBoundingClientRect(), [cx, cy] = canvas.toPage(r.width / 2, r.height / 2);
    const copy = { id: uid("it"), type: "symbol", symbol: id, name: "", frame: [cx - sym.size[0] / 2, cy - sym.size[1] / 2, ...sym.size],
      rot: 0, flip_h: false, flip_v: false };
    store.update("Place symbol", (doc) => store.container(doc).push(copy), { select: [copy.id] });
    announce(`Placed a copy of ${sym.name}`);
  },
  renameSymbol(id, name) {
    store.update("Rename symbol", (doc) => { const sym = symbolOf(doc, id); if (sym) sym.name = name; });
  },
  deleteSymbol(id) {
    if (copiesOf(store.doc, id).length) return announce("Delete or break the symbol's copies first");
    store.update("Delete symbol", (doc) => { doc.symbols = (doc.symbols || []).filter((x) => x.id !== id); });
  },
  stopGrid() {
    const grids = store.selected().filter((it) => it.grid);
    if (!grids.length) return announce("Select a grid layout");
    store.update("Stop grid layout", (doc) => { for (const g of grids) delete findDeep(doc.pages[store.pageIndex].items, g.id).grid; });
    announce("It's an ordinary group now: the panels stay where they are");
  },
  ungroup() {
    const groups = store.selected().filter((it) => it.type === "group");
    if (!groups.length) return;
    const childIds = [];
    store.update("Ungroup", (doc) => {
      const items = store.container(doc);
      for (const g of groups) {
        const i = items.findIndex((it) => it.id === g.id);
        const gg = items[i];
        items.splice(i, 1, ...gg.items);
        childIds.push(...gg.items.map((c) => c.id));
      }
    }, { select: childIds });
    announce("Ungrouped");
  },
  // Lock or hide the selection (hidden objects leave the selection)
  setFlag(flag, on) {
    const ids = new Set(store.selection);
    if (!ids.size) return;
    const label = flag === "locked" ? (on ? "Lock" : "Unlock") : (on ? "Hide" : "Show");
    store.update(label, (doc) => {
      for (const id of ids) {
        const it = findDeep(doc.pages[store.pageIndex].items, id);
        if (it) it[flag] = on;
      }
    }, flag === "hidden" && on ? { select: [] } : {});
    const n = `${ids.size} object${ids.size === 1 ? "" : "s"}`;
    announce({ Lock: `Locked ${n} in place`, Unlock: `Unlocked ${n}`, Hide: `Hid ${n}; the Objects list shows them again`,
      Show: `Showing ${n}` }[label]);
  },

  // Right-click menus ------------------------------------------------------------------------

  // One menu line for a command: its label and shortcut
  menuEntry(name, opts = {}) {
    const c = this.commands[name];
    return { label: c.label, keys: c.keys, run: () => this.run(name), ...opts };
  },
  // What's on the clipboard, for the menus' Paste lines ({} if it can't be told)
  async clipboardKinds() {
    await this.copying;
    try { return await rpc("clipboard_kinds", this.clipboardCount ?? null); } catch { return {}; }
  },
  // Paste, and Paste as picture when a plain paste would take the text (or PowerPoint's slides or
  // shapes, as objects) instead of the picture
  pasteEntries(clip, at) {
    const both = (clip.text || clip.slides || clip.shapes) && clip.picture && !clip.files && !clip.objects && !clip.own;
    return [this.menuEntry("paste", { run: () => this.paste("auto", at) }),
      both && { label: "Paste as picture", run: () => this.paste("picture", at) }];
  },
  // For the selected objects
  objectMenu(clip = {}, at = null) {
    const c = (name, opts) => this.menuEntry(name, opts);
    const sel = store.selected(), one = sel.length === 1 ? sel[0] : null;
    const locked = sel.length > 0 && sel.every((it) => it.locked);
    const asset = one?.type === "picture" ? store.doc.assets[one.asset] : null;
    return [
      c("cut"), c("copy"), ...this.pasteEntries(clip, at), c("duplicate"), c("delete"),
      "-",
      c("copyStyle", { disabled: !sel.length }), c("pasteStyle", { disabled: !this.styleClipboard || locked }),
      "-",
      c("group", { disabled: sel.length < 2 }), c("ungroup", { disabled: !sel.some((it) => it.type === "group") }),
      c("gridLayout", { disabled: sel.filter((it) => !it.attach).length < 2 }),
      "-",
      c("bringToFront"), c("bringForward"), c("sendBackward"), c("sendToBack"),
      "-",
      { label: "Lock position", checked: locked, run: () => this.setFlag("locked", !locked) },
      { label: "Hide", run: () => this.setFlag("hidden", true) },
      "-",
      one?.equation && { label: "Edit equation", keys: "Enter", run: () => this.editEquation(one.id) },
      one?.type === "picture" && { label: "Crop picture", keys: one.equation ? null : "Enter", run: () => canvas.startCrop(one.id) },
      one?.type === "picture" && c("replacePicture", { label: "Replace picture…" }),
      asset?.variants[asset.primary]?.src && c("revealPicture"),
      one?.geom === "custom" && { label: "Edit points", keys: "Enter", run: () => canvas.startPointEdit(one.id) },
      one?.type === "shape" && !one.textbox && !["custom", "region", "arc"].includes(one.geom) && c("makeEditable"),
      one?.type === "shape" && one.geom !== "region" && { label: "Edit text", keys: one.geom === "custom" ? null : "Enter", run: () => canvas.startEdit(one.id) },
      one?.geom === "region" && { label: "Make an ordinary shape", run: () => this.detachArea() },
      one?.type === "line" && (one.start_link || one.end_link) && { label: "Detach the ends", run: () => this.detachEnds() },
      one?.type === "line" && c("elbowConnector", { label: "Elbow connector", checked: one.route === "elbow" }),
      one?.attach && c("detachLabel", { label: "Detach from its panel" }),
      one?.type === "symbol" && { label: "Edit symbol", keys: "Enter", run: () => this.editSymbol(one.id) },
      one?.type === "symbol" && c("breakSymbol"),
      sel.length > 0 && sel.every(canHold) && !one?.editing_symbol && c("makeSymbol"),
      one?.textbox && !one.attach && this.labelPanel(one) && c("attachLabel", { label: "Attach to the panel it's on" }),
      one?.type === "group" && { label: "Edit inside the group", keys: "Enter", run: () => canvas.enterGroup(one.id) },
    ];
  },
  // For the page itself, where nothing was under the pointer
  pageMenu(clip = {}, at = null) {
    const c = (name, opts) => this.menuEntry(name, opts);
    const show = (name, pref, label) => c(name, { label, checked: !!this.prefs[pref] });
    return [
      store.scope.length && { label: "Leave the group", keys: "Escape", run: () => { store.exitGroup(); announce("Left the group"); } },
      store.scope.length && "-",
      ...this.pasteEntries(clip, at), c("selectAll"),
      "-",
      c("insertPicture", { label: "Insert picture…" }), c("fitPage"),
      "-",
      show("toggleRulers", "show_rulers", "Rulers"), show("toggleGrid", "show_grid", "Grid"),
      show("toggleGuides", "show_guides", "Guides"), show("toggleSnap", "snap", "Snap"),
    ];
  },
  // Show a menu once the clipboard has been looked at (entries(clip) builds it); a newer menu
  // asked for in the meantime wins
  async showMenu(entries, x, y, returnFocus) {
    const ask = (this._menuAsk = (this._menuAsk || 0) + 1);
    const clip = await this.clipboardKinds();
    if (ask === this._menuAsk) contextMenu.show(entries(clip), x, y, returnFocus);
  },
  // A right-click on the page: like PowerPoint, an object outside the selection becomes the
  // selection, and empty page clears it. Paste puts things where it was clicked
  contextMenuAt(x, y) {
    const r = canvas.stage.getBoundingClientRect();
    const p = canvas.toPage(x - r.left, y - r.top);
    const hit = canvas.itemAt(p);
    if (!hit) store.select([]);
    else if (!store.selection.includes(hit.id)) store.select([hit.id]);
    return this.showMenu((clip) => (hit ? this.objectMenu(clip, p) : this.pageMenu(clip, p)), x, y, canvas.stage);
  },
  // An object's menu from the Objects list
  objectListMenu(x, y) {
    const alt = isMac ? "⌥" : "Alt+";
    return this.showMenu((clip) => [...this.objectMenu(clip), "-",
      { label: "Move into the group above", keys: `${alt}→`, disabled: !this.groupAbove(), run: () => this.moveIntoGroupAbove() },
      { label: "Move out of the group", keys: `${alt}←`, disabled: !store.scope.length, run: () => this.moveOutOfGroup() },
    ], x, y, panels.layerList);
  },
  // The menu key or Shift+F10: the menu for what has the focus, beside it
  keyboardMenu(target) {
    const below = (el) => { const r = el.getBoundingClientRect(); return [r.left + 12, r.bottom - 4]; };
    if (panels.pageList.contains(target)) {
      const li = panels.pageList.children[store.pageIndex];
      if (li) panels.pageMenu(store.pageIndex, ...below(li));
      return;
    }
    const row = store.selection.length && document.getElementById(`layer-opt-${store.selection[store.selection.length - 1]}`);
    if (panels.layerList.contains(target) && row) return this.objectListMenu(...below(row));
    const sr = canvas.stage.getBoundingClientRect(), b = itemsBBox(store.selected());
    if (b) {
      // Under the selection's bottom-left corner, kept inside the view
      const [x, y] = canvas.toScreen(b[0], b[3]);
      return this.showMenu((clip) => this.objectMenu(clip), sr.left + Math.min(Math.max(x, 8), sr.width - 8),
        sr.top + Math.min(Math.max(y + 4, 8), sr.height - 8), canvas.stage);
    }
    store.select([]);
    return this.showMenu((clip) => this.pageMenu(clip), sr.left + sr.width / 2, sr.top + sr.height / 2, canvas.stage);
  },
  detachEnds() {
    const it = store.selected()[0];
    if (!it || it.type !== "line") return;
    store.update("Detach", (doc) => {
      const l = findDeep(doc.pages[store.pageIndex].items, it.id);
      delete l.start_link;
      delete l.end_link;
    });
    announce("Detached: the line's ends no longer follow other objects");
  },
  deleteSelection() {
    const ids = new Set(store.selection);
    if (!ids.size) return;
    const asked = ids.size;
    // An area fill goes too once none of its lines and shapes are left
    const left = (id) => !ids.has(id) && findDeep(store.items(), id);
    for (const it of store.items()) {
      if (it.geom === "region" && !(it.region?.items || []).some(left)) ids.add(it.id);
    }
    store.update("Delete", (doc) => {
      const items = store.container(doc);
      items.splice(0, items.length, ...items.filter((it) => !ids.has(it.id)));
    }, { select: [] });
    announce(`Deleted ${asked} object${asked === 1 ? "" : "s"}${ids.size > asked ? ", and the area fills between them" : ""}`);
  },
  // Area fills: click inside a space lines and shapes enclose. The fill goes behind them and
  // follows them when they move or change shape
  async fillArea(p) {
    let found = null;
    try { found = await rpc("region_at", store.items(), p); } catch (err) { console.error(err); }
    if (!found) return announce("Nothing encloses that spot: lines and shapes have to close an area round it");
    const fill = { id: uid("it"), type: "shape", geom: "region", name: "", region: { items: found.items, seed: found.seed },
      frame: found.frame, rot: 0, stroke: null, fill: { color: "#d9d9d9", opacity: 1 } };
    store.update("Fill area", (doc) => {
      const items = store.container(doc);
      const holds = (it, id) => it.id === id || (it.type === "group" && it.items.some((c) => holds(c, id)));
      const at = Math.min(...found.items.map((id) => items.findIndex((it) => holds(it, id))).filter((i) => i >= 0));
      items.splice(Number.isFinite(at) ? at : items.length, 0, fill);
    }, { select: [fill.id] });
    canvas.setTool("select");
    announce("Filled the area. It follows its lines and shapes when they move; choose its colour in the Style tab");
  },
  // Panel labels (labels.js): the picture or group a text box is on or near, to attach it to
  labelPanel(it) {
    const items = store.scopeItems();
    return it?.frame && items.includes(it) ? panelAt(items, middle(it.frame), { label: it }) : null;
  },
  attachLabel() {
    const it = store.selected()[0], panel = this.labelPanel(it);
    if (!it?.textbox) return announce("Select a panel label (or another text box) to attach");
    if (!panel) return announce("Move the label onto or next to a picture or group first");
    store.update("Attach label", (doc) => { findDeep(doc.pages[store.pageIndex].items, it.id).attach = { to: panel.id }; });
    announce(`The label stays with ${itemLabel(panel, store.doc)} now`);
  },
  detachLabel() {
    const sel = store.selected().filter((it) => it.attach);
    if (!sel.length) return announce("Select a label attached to a panel");
    store.update("Detach label", (doc) => { for (const it of sel) delete findDeep(doc.pages[store.pageIndex].items, it.id).attach; });
    announce(sel.length === 1 ? "Detached: the label stays where it is when its panel moves" : `Detached ${sel.length} labels`);
  },
  // An area fill as an ordinary shape of its area as it is now, no longer following its lines
  detachArea() {
    const it = store.selected()[0];
    if (it?.geom !== "region") return;
    const path = canvas.els.get(it.id)?.regionPath;
    if (!path) return announce("This area fill encloses nothing at the moment");
    store.update("Make an ordinary shape", (doc) => { detachRegion(findDeep(doc.pages[store.pageIndex].items, it.id), path); });
    announce("It's an ordinary shape now and stays where it is when the lines move");
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
    // On the system clipboard too, for other documents; its change count afterwards tells a
    // paste whether this copy is still the newest thing there
    this.clipboardCount = null;
    this.copying = Promise.resolve(navigator.clipboard?.writeText(text)).catch(() => {})
      .then(() => rpc("clipboard_copied", text)).then((n) => { this.clipboardCount = n; }).catch(() => {});
    if (cut) this.deleteSelection();
    announce(`${cut ? "Cut" : "Copied"} ${sel.length} object${sel.length === 1 ? "" : "s"}`);
  },
  // Paste what's newest on the clipboard: objects copied here or in another document, files
  // copied in the Finder or Explorer (linked, as when dropped), a picture, or text as a text box.
  // mode "picture" takes the picture even when there's text too; at: where (top-left) on the page,
  // else the middle of the view
  async paste(mode = "auto", at = null) {
    await this.copying;   // a copy just made is on the clipboard first
    let r;
    try { r = await rpc("clipboard_paste", mode, this.clipboardCount ?? null, store.path || null); } catch { r = { kind: "unavailable" }; }
    const centred = ([w, h]) => {
      if (at) return at;
      const sr = canvas.stage.getBoundingClientRect(), [cx, cy] = canvas.toPage(sr.width / 2, sr.height / 2);
      return [cx - w / 2, cy - h / 2];
    };
    const sizeOf = (asset) => (asset.page_sizes ? asset.page_sizes[0] : asset.size_pt);
    if (r.kind === "own" && this.clipboard) return this.pasteObjects(this.clipboard);
    if (r.kind === "objects") return this.pasteObjects(r.clip);
    if (r.kind === "slides" || r.kind === "shapes") return this.fromPowerPoint(r, { at }, "Paste");
    if (r.kind === "files") {
      const first = r.results.find((x) => !x.error);
      return this.placeResults(r.results, first ? centred(sizeOf(first.asset)) : at, "linked");
    }
    if (r.kind === "picture") return this.placeResults([r], centred(sizeOf(r.asset)), "stored in the document");
    if (r.kind === "text") return this.pasteText(r.paragraphs, at);
    if (r.kind === "unavailable") {
      // No system clipboard to read here: FigAssemble's own copies only
      let clip = this.clipboard;
      try {
        const text = await navigator.clipboard?.readText();
        if (text?.startsWith("figassemble:")) clip = JSON.parse(text.slice(12));
      } catch { /* not readable: the copy made in this window */ }
      if (clip) return this.pasteObjects(clip);
    }
    announce(mode === "picture" ? "There's no picture on the clipboard" : "Nothing to paste");
  },
  pasteObjects(clip) {
    const items = copyItems(clip.items);
    const offset = clip.page === store.page().id ? 10 : 0;
    store.update("Paste", (doc) => {
      Object.assign(doc.assets, clip.assets);
      for (const it of items) {
        if (offset) shiftItem(it, clone(it), offset, offset);
        store.container(doc).push(it);
      }
    }, { select: items.map((i) => i.id) });
    clip.page = store.page().id;
    announce(`Pasted ${items.length} object${items.length === 1 ? "" : "s"}`);
  },
  // Pasted text: a text box in the default font and size, keeping bold, italic and line breaks.
  // Long paragraphs wrap in a box 60% of the page wide; short ones size the box to the text
  pasteText(paragraphs, at) {
    const d = canvas.defaults || {};
    const base = { font: d.text?.font || "Helvetica", size: d.text?.size || 6, color: "#000000" };
    const paras = paragraphs.map((runs) => ({ align: "l",
      runs: (runs.length ? runs : [{ t: "" }]).map((r) => ({ ...base, t: r.t, bold: !!r.bold, italic: !!r.italic })) }));
    const longest = Math.max(0, ...paragraphs.map((runs) => runs.reduce((n, r) => n + r.t.length, 0)));
    const wrap = longest > 80, w = wrap ? Math.round(store.page().width * 0.6) : 10;
    let [x, y] = at || [];
    if (!at) {
      const sr = canvas.stage.getBoundingClientRect();
      [x, y] = canvas.toPage(sr.width / 2, sr.height / 2);
      if (wrap) x -= w / 2;
    }
    const item = { id: uid("it"), type: "shape", geom: "rect", textbox: true, stroke: null, fill: null, rot: 0,
      frame: [x, y, w, 10], text: { paragraphs: paras, insets: [0, 0, 0, 0], wrap, anchor: "t", autofit: "shape" } };
    store.update("Paste text", (doc) => store.container(doc).push(item), { select: [item.id] });
    announce(`Pasted text: ${paras.length} paragraph${paras.length === 1 ? "" : "s"}, in ${base.font} ${base.size} pt`);
  },
  // Duplicate, as in PowerPoint: the copy goes 10 pt down and right, but once a copy has been
  // moved, duplicating it again puts the next copy at that same offset from it
  duplicate() {
    const sel = store.selected();
    if (!sel.length) return;
    let [dx, dy] = [10, 10];
    const last = this.lastDuplicate, ids = sel.map((it) => it.id);
    const from = last && last.copies.length === ids.length && last.copies.every((id) => ids.includes(id))
      ? last.originals.map((id) => store.item(id)).filter(Boolean) : [];
    if (from.length && from.length === last.originals.length) {
      const a = itemsBBox(from), b = itemsBBox(sel);
      if (a && b) [dx, dy] = [b[0] - a[0], b[1] - a[1]];
    }
    const items = copyItems(sel);
    for (const c of items) shiftItem(c, clone(c), dx, dy);
    store.update("Duplicate", (doc) => store.container(doc).push(...items), { select: items.map((i) => i.id) });
    this.lastDuplicate = { originals: ids, copies: store.selection.slice() };
    announce(`Duplicated ${items.length} object${items.length === 1 ? "" : "s"}`);
  },
  // Styles: Copy style (⌘⇧C) takes the selected object's look; Paste style (⌘⇧V) puts it on
  // what's selected; the Format Painter takes it and paints it on the next object clicked
  copyStyle() {
    const src = store.selected()[0];
    const style = src && styleOf(src);
    if (!style) { announce("Select an object to copy its style"); return false; }
    this.styleClipboard = style;
    announce(`Copied the style of ${itemLabel(src, store.doc)}`);
    return true;
  },
  pasteStyle(ids = store.selection) {
    if (!this.styleClipboard) { announce("Copy a style first"); return; }
    const targets = ids.map((id) => store.item(id)).filter((it) => it && !it.locked);
    if (!targets.length) return;
    store.update("Paste style", (doc) => {
      for (const t of targets) applyStyle(findDeep(doc.pages[store.pageIndex].items, t.id), this.styleClipboard);
    });
    announce(targets.length === 1 ? `Pasted the style onto ${itemLabel(store.item(targets[0].id), store.doc)}`
      : `Pasted the style onto ${targets.length} objects`);
  },
  // A click on the button paints once; a double-click keeps painting until Escape
  formatPainter(keep = false) {
    if (canvas.tool === "painter" && !keep) { canvas.setTool("select"); return; }
    if (!this.copyStyle()) return;
    this.painterKeeps = keep;
    canvas.setTool("painter");
    announce(keep ? "Click objects to paint the style on them; Escape stops" : "Click an object to paint the style on it");
  },
  // A click paints the object under it; Enter (from the keyboard) paints what's selected
  paintStyle(hit, keyboard = false) {
    if (keyboard) this.pasteStyle();
    else if (hit && !hit.locked) this.pasteStyle([hit.id]);
    if (!this.painterKeeps) canvas.setTool("select");
  },
  // Transform Again (⌘⇧D), as in Illustrator: the last move, resize or turn, done again to what's
  // selected now; a move made by Option-dragging a copy makes another copy
  noteTransform(t) { this.lastTransform = t; },
  transformAgain() {
    const t = this.lastTransform;
    let sel = store.selected().filter((it) => !it.locked);
    if (!t) { announce("Nothing to repeat yet: move, resize or rotate something first"); return; }
    if (!sel.length) return;
    if (t.kind === "move" && t.copy) {
      const items = copyItems(withRegionLines(sel));
      for (const c of items) shiftItem(c, clone(c), t.dx, t.dy);
      store.update("Transform again", (doc) => store.container(doc).push(...items),
        { select: items.slice(0, sel.length).map((i) => i.id) });
      announce(`Copied and moved ${lengthText(Math.hypot(t.dx, t.dy), this.prefs.units)} again`);
      return;
    }
    if (t.kind === "move") sel = withRegionLines(sel);
    else sel = sel.filter((it) => it.geom !== "region");
    const box = itemsBBox(sel);
    store.update("Transform again", (doc) => {
      const items = sel.map((x) => findDeep(doc.pages[store.pageIndex].items, x.id));
      if (t.kind === "move") {
        detachMoved(items);
        for (const it of items) shiftItem(it, clone(it), t.dx, t.dy);
      } else if (t.kind === "rotate") {
        for (const it of items) rotateItem(it, t.angle, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2);
      } else if (t.kind === "resize") {
        for (const it of items) scaleItem(it, t.sx, t.sy, t.anchor);
      }
    });
    announce(t.kind === "move" ? `Moved ${lengthText(Math.hypot(t.dx, t.dy), this.prefs.units)} again`
      : t.kind === "rotate" ? `Turned ${Math.round(t.angle * 10) / 10} degrees again` : "Resized again");
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
      const items = store.container(doc);
      items[items.findIndex((x) => x.id === it.id)] = line;
    }, { select: [line.id] });
    announce(`Now a curve through ${line.points.length} points: drag them to reshape it`);
  },

  cycleSelection(back) {
    const items = store.scopeItems().filter((it) => !it.hidden);
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
function reidPage(p) { p.id = uid("pg"); p.items = copyItems(p.items); return p; }

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
  cut: cmd("Cut", () => app.copy(true), `${M}X`, key("x"), "Cut"),
  copy: cmd("Copy", () => app.copy(), `${M}C`, key("c"), "Copy"),
  paste: cmd("Paste", () => app.paste(), `${M}V`, key("v"), "Paste"),
  duplicate: cmd("Duplicate", () => app.duplicate(), `${M}D`, key("d"), "Duplicate"),
  fonts: cmd("Fonts in this figure: see and replace them", () => panels.fontsDialog(), null, null, "Fonts"),
  swatches: cmd("Swatches: the figure's named colours, and palettes", () => panels.swatchesDialog(), null, null, "Swatches"),
  textStyles: cmd("Text styles: the figure's named text formats", () => panels.textStylesDialog(), null, null, "Text styles"),
  objectStyles: cmd("Object styles: the figure's named looks for lines and shapes", () => panels.objectStylesDialog(), null, null, "Object styles"),
  sameWidth: cmd("Same width: make the selected objects as wide as the key object (or the first selected), keeping "
    + "their proportions", () => app.matchSize("w"), null, null, "Same width"),
  sameHeight: cmd("Same height: make the selected objects as tall as the key object (or the first selected), keeping "
    + "their proportions", () => app.matchSize("h"), null, null, "Same height"),
  addScaleBar: cmd("Scale bar: add one to the selected picture (it needs a scale)", () => app.addScaleBar(), null, null, "Scale bar"),
  measureScale: cmd("Measure a known length on the selected picture, to give it a scale", () => app.measureScale(), null, null,
    "Measure"),
  zoomInset: cmd("Zoom inset: drag a box on a picture to show that area enlarged beside it", () => canvas.startZoom(), null, null,
    "Zoom inset"),
  toolSigBracket: cmd("Significance bracket: drag across the bars it compares (or upright)", () => canvas.setTool("sigbracket"),
    null, null, "Bracket"),
  stackBrackets: cmd("Stack the selected brackets in tidy levels, the narrowest lowest", () => app.stackBrackets(), null, null, "Stack"),
  unite: cmd("Unite: join the selected shapes into one", () => app.pathfinder("unite"), null, null, "Unite"),
  minusFront: cmd("Minus front: cut the shapes on top out of the bottom one", () => app.pathfinder("minus_front"), null, null,
    "Minus front"),
  intersect: cmd("Intersect: keep only where the selected shapes overlap", () => app.pathfinder("intersect"), null, null, "Intersect"),
  exclude: cmd("Exclude: keep where the shapes don't overlap", () => app.pathfinder("exclude"), null, null, "Exclude"),
  makeClipMask: cmd("Make clipping mask: the top selected shape clips the objects under it", () => app.makeClipMask(),
    `${M}7`, key("7"), "Make mask"),
  releaseClipMask: cmd("Release clipping mask: separate the shape and what it clips", () => app.releaseClipMask(), null, null, "Release"),
  figureReport: cmd("Figure report: each picture's source, copies, size, scale, crop, turns, resolution and scale bars",
    () => panels.figureReportDialog(), null, null, "Report"),
  equation: cmd("Equation: maths written as in LaTeX, drawn as real text", () => app.addEquation(), null, null, "Equation"),
  elbowConnector: cmd("Elbow connector: route the selected line in level and upright stretches, or straight again",
    () => app.setRoute(store.selected().every((it) => it.route === "elbow") ? "straight" : "elbow"), null, null, "Elbow"),
  makeEditable: cmd("Make editable shape: a freeform shape of the same outline, whose points can be moved",
    () => app.makeEditable(), null, null, "Make editable"),
  makeSymbol: cmd("Make symbol: one object to use many times, changed everywhere at once", () => app.makeSymbol(), null, null, "Make symbol"),
  editSymbol: cmd("Edit symbol: change the selected copy's symbol where it is (every copy follows)", () => app.editSymbol(), null, null, "Edit symbol"),
  breakSymbol: cmd("Break link to symbol: make the selected copy its own objects", () => app.breakSymbol(), null, null, "Break link"),
  symbols: cmd("Symbols: the figure's symbols, to place, rename or delete", () => panels.symbolsDialog(), null, null, "Symbols…"),
  gridLayout: cmd("Grid layout: put the selected panels in rows and columns that keep their gaps when a panel changes",
    () => app.gridLayout(), null, null, "Grid"),
  stopGrid: cmd("Stop grid layout: keep the panels where they are, as an ordinary group", () => app.stopGrid(), null, null, "Stop grid"),
  attachLabel: cmd("Attach label: keep the selected label with the picture or group it's on", () => app.attachLabel(), null, null, "Attach label"),
  detachLabel: cmd("Detach label: let the selected label stay put when its panel moves", () => app.detachLabel(), null, null, "Detach label"),
  copyStyle: cmd("Copy style", () => app.copyStyle(), `${M}${S}C`, key("c", { shift: true }), "Copy style"),
  pasteStyle: cmd("Paste style", () => app.pasteStyle(), `${M}${S}V`, key("v", { shift: true }), "Paste style"),
  formatPainter: cmd("Format painter: click it, then click an object to give it the selected object's style "
    + "(double-click it to keep painting)", () => app.formatPainter(), null, null, "Painter"),
  transformAgain: cmd("Transform again: repeat the last move, resize or turn", () => app.transformAgain(), `${M}${S}D`,
    key("d", { shift: true }), "Again"),
  delete: cmd("Delete", () => app.deleteSelection(), "Delete", (e) => plain(e) && (e.key === "Delete" || e.key === "Backspace"), "Delete"),
  selectAll: cmd("Select all", () => { store.select(store.scopeItems().filter((i) => !i.locked).map((i) => i.id)); announce(`${store.selection.length} objects selected`); }, `${M}A`, key("a")),
  group: cmd("Group", () => app.group(), `${M}G`, key("g"), "Group"),
  ungroup: cmd("Ungroup", () => app.ungroup(), `${M}${S}G`, key("g", { shift: true }), "Ungroup"),
  bringToFront: cmd("Bring to front", () => app.reorder("front"), `${M}${S}]`, (e) => mod(e) && e.shiftKey && (e.key === "]" || e.key === "}"), "To front"),
  bringForward: cmd("Bring forward", () => app.reorder("forward"), `${M}]`, (e) => mod(e) && !e.shiftKey && e.key === "]", "Forward"),
  sendBackward: cmd("Send backward", () => app.reorder("backward"), `${M}[`, (e) => mod(e) && !e.shiftKey && e.key === "[", "Backward"),
  sendToBack: cmd("Send to back", () => app.reorder("back"), `${M}${S}[`, (e) => mod(e) && e.shiftKey && (e.key === "[" || e.key === "{"), "To back"),
  alignLeft: cmd("Align left edges", () => app.align("left"), null, null, "Left"),
  alignCenter: cmd("Align centres", () => app.align("center"), null, null, "Centre"),
  alignRight: cmd("Align right edges", () => app.align("right"), null, null, "Right"),
  alignTop: cmd("Align top edges", () => app.align("top"), null, null, "Top"),
  alignMiddle: cmd("Align middles", () => app.align("middle"), null, null, "Middle"),
  alignBottom: cmd("Align bottom edges", () => app.align("bottom"), null, null, "Bottom"),
  distributeLeft: cmd("Distribute left edges", () => app.distributeBy("left"), null, null, "Left"),
  distributeCenter: cmd("Distribute centres", () => app.distributeBy("center"), null, null, "Centre"),
  distributeRight: cmd("Distribute right edges", () => app.distributeBy("right"), null, null, "Right"),
  distributeTop: cmd("Distribute top edges", () => app.distributeBy("top"), null, null, "Top"),
  distributeMiddle: cmd("Distribute middles", () => app.distributeBy("middle"), null, null, "Middle"),
  distributeBottom: cmd("Distribute bottom edges", () => app.distributeBy("bottom"), null, null, "Bottom"),
  distributeH: cmd("Space evenly across", () => app.distribute("h"), null, null, "Across"),
  distributeV: cmd("Space evenly down", () => app.distribute("v"), null, null, "Down"),
  zoomIn: cmd("Zoom in", () => canvas.setZoom(canvas.zoom * 1.25), `${M}+`, (e) => mod(e) && (e.key === "=" || e.key === "+"), "Zoom in"),
  zoomOut: cmd("Zoom out", () => canvas.setZoom(canvas.zoom / 1.25), `${M}−`, (e) => mod(e) && (e.key === "-" || e.key === "_"), "Zoom out"),
  zoomFit: cmd("Fit page in window", () => canvas.fit(), `${M}0`,
    (e) => mod(e) && !e.shiftKey && (e.key === "0" || e.code === "Digit0"), "Fit"),
  centrePage: cmd("Centre page", () => { canvas.centre(); announce("Page centred"); }, `${M}${S}0`,
    (e) => mod(e) && e.shiftKey && !e.altKey && (e.key === "0" || e.key === ")" || e.code === "Digit0"), "Centre"),
  zoom100: cmd("True size (100%)", () => canvas.setZoom(1), `${M}1`, (e) => mod(e) && e.key === "1", "100%"),
  gridSettings: cmd("Grid spacing and snapping settings", () => panels.preferencesDialog(), null, null, "Settings"),
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
  toolPen: tool("pen", "Pen: click for corners, drag for curves, click the first point to close", "b", "Pen"),
  toolRect: tool("rect", "Rectangle", "r", "Rect"),
  toolRoundRect: tool("roundrect", "Rounded rectangle", "u", "Rounded"),
  toolEllipse: tool("ellipse", "Ellipse or circle", "o", "Ellipse"),
  toolTriangle: tool("triangle", "Triangle", null, "Triangle"),
  toolArc: tool("arc", "Arc", null, "Arc"),
  toolBracket: tool("bracket", "Bracket", null, "Bracket"),
  toolFill: tool("fill", "Fill an area that lines and shapes enclose", "f", "Fill area"),
  shapesMenu: cmd("Shapes", () => panels.toggleShapeMenu(), "S", (e) => plain(e) && !e.shiftKey && e.key.toLowerCase() === "s", "Shapes"),
  addPage: cmd("Add page", () => app.addPage(), `${M}${S}N`, key("n", { shift: true }), "Add page"),
  duplicatePage: cmd("Duplicate page", () => app.addPage(true)),
  deletePage: cmd("Delete page", () => app.deletePage()),
  pageUp: cmd("Move page up", () => app.movePage(store.pageIndex, store.pageIndex - 1)),
  pageDown: cmd("Move page down", () => app.movePage(store.pageIndex, store.pageIndex + 1)),
  fitPage: cmd("Fit page to content", () => app.fitPage(), null, null, "Fit page"),
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
  commandSearch: cmd("Search commands: type to find and run any command", () => panels.commandSearch(), `${M}/`, key("/"), "Search"),
  shortcuts: cmd("Keyboard shortcuts and help", () => panels.shortcutsDialog(), "?", (e) => plain(e) && e.key === "?", "Help"),
};

// Keyboard ----------------------------------------------------------------------------------

document.addEventListener("keydown", (e) => {
  if (document.querySelector("dialog[open]")) return;
  if (e.key === " " && !isField(e.target)) { canvas.spaceDown = true; canvas.stage.style.cursor = "grab"; e.preventDefault(); return; }
  if (e.key === "Alt" && !isField(e.target)) canvas.setMeasureKey(true);   // distances on hover
  const inField = isField(e.target);
  if (!inField && (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey))) {
    e.preventDefault();
    app.keyboardMenu(e.target);
    return;
  }
  // Drawing with the pen or editing points: Enter, Escape and Delete are theirs (pen.js)
  if (!inField && canvas.penKey(e)) { e.preventDefault(); return; }
  // In text fields only the document-level commands are ours; everything else stays native
  const always = ["save", "saveAs", "open", "new", "export"];
  for (const [name, c] of Object.entries(app.commands)) {
    if (!c.match || !c.match(e)) continue;
    if (inField && !always.includes(name)) return;
    e.preventDefault();
    if (inField) {
      // What's being typed goes into the document first, so a save includes it
      canvas.commitEdit();
      e.target.blur();
    }
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
    else if (store.scope.length && store.exitGroup()) announce("Left the group");
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
    else if (it.equation) app.editEquation(it.id);
    else if (it.type === "picture") canvas.startCrop(it.id);
    else if (it.geom === "custom" && !it.text?.paragraphs?.some((p) => p.runs?.some((r) => r.t))) canvas.startPointEdit(it.id);
    else if (it.type === "shape") canvas.startEdit(it.id);
    else if (it.type === "group") canvas.enterGroup(it.id);
    else if (it.type === "symbol") app.editSymbol(it.id);
    return;
  }
  if (e.key === "Tab" && onCanvas && store.scopeItems().length) {
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
  if (e.key === "Alt") canvas.setMeasureKey(false);
});
window.addEventListener("blur", () => {
  canvas.setMeasureKey(false);
});
function isField(el) {
  return el && (el.matches?.("input, textarea, select") || el.isContentEditable);
}

// Drag and drop ------------------------------------------------------------------------------

const isDeck = (path) => /\.(pptx|pptm|potx)$/i.test(path || "");
// Words for a gap in the Pages list, where slides would go in as pages
function slideGap(at) {
  const n = store.doc.pages.length;
  return at >= n ? `after page ${n}` : `before page ${at + 1}`;
}
// What importing said about the pictures, for an announcement
function pictureNote(report = []) {
  const linked = report.filter((l) => l.startsWith("relinked ")).length, kept = report.filter((l) => l.startsWith("kept the deck's copy")).length;
  const parts = [linked && `${linked} picture${linked === 1 ? "" : "s"} linked to the original file${linked === 1 ? "" : "s"}`,
    kept && `${kept} picture${kept === 1 ? "" : "s"} kept as PowerPoint's cop${kept === 1 ? "y" : "ies"} (no original found)`].filter(Boolean);
  return parts.length ? `; ${parts.join(", ")}` : "";
}
// Where a drop lands: the Pages panel ({list, pageIndex: the page under the pointer, pageAt: the
// gap nearest it}) or the page ({point, over: what's there})
function dropTarget(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY);
  if (el?.closest?.("#pages")) {
    const rows = [...panels.pageList.querySelectorAll("li[data-index]")], li = el.closest("li[data-index]");
    const k = rows.findIndex((row) => { const r = row.getBoundingClientRect(); return clientY < r.top + r.height / 2; });
    return { list: true, pageIndex: li ? Number(li.dataset.index) : null, pageAt: k < 0 ? rows.length : k };
  }
  const r = canvas.stage.getBoundingClientRect();
  const pt = canvas.toPage(clientX - r.left, clientY - r.top);
  return { point: pt, over: canvas.itemAt(pt) };
}
// Pictures dropped: at the point on the page, or on the page dropped on in the Pages list
function placeAt(t) {
  if (!t.list) return t.point;
  if (t.pageIndex !== null) store.setPage(t.pageIndex);
  return [store.page().width * 0.1, store.page().height * 0.1];
}
window.FA = {
  // Native window: full file paths arrive from Python so the figures can stay linked; on a Mac,
  // slides dragged out of PowerPoint (pptSlides: references) or shapes with their contents
  // (dropped: a token for take_dropped) arrive too (macdrag.py)
  async onNativeDrop({ paths = [], x, y, embed, shift, pptSlides, dropped }) {
    app.nativeDrag = false;
    app.showDropSpot(null);
    const t = dropTarget(x, y);
    if (pptSlides) return app.dropPowerPointSlides(pptSlides, t);
    if (dropped) {
      const r = await rpc("take_dropped", dropped, store.path || null);
      return app.fromPowerPoint(r, t.list ? (r.kind === "slides" ? { pageAt: t.pageAt } : { at: placeAt(t) }) : { at: t.point }, "Add");
    }
    const decks = paths.filter(isDeck), files = paths.filter((p) => !isDeck(p));
    if (shift && t.over?.type === "picture" && files.length === 1) {
      store.select([t.over.id]);
      await app.replacePicture(files);
    } else if (files.length) await app.placeFiles(files, placeAt(t), embed);
    for (const deck of decks) await app.addDeck(deck, t);
  },
  // A drag over the native window that the page can't see into (macdrag.py): where it'd go
  onNativeDrag(info) {
    app.nativeDrag = !!info;
    app.showDropSpot(info);
  },
};
// Browser: files arrive as data (stored in the document, without links). Slides dragged out of
// PowerPoint arrive as its web data ("ppt/slides", if a Chromium web view is handed it)
document.addEventListener("dragover", (e) => {
  const types = e.dataTransfer.types;
  if (!types.includes("Files") && !types.includes("ppt/slides")) return;
  e.preventDefault();
  if (app.nativeDrag) return;   // shown from the native window's own view of the drag
  const deck = [...e.dataTransfer.items].some((i) => i.type.includes("presentationml"));
  app.showDropSpot({ kind: types.includes("ppt/slides") ? "slides" : deck ? "deck" : "files", x: e.clientX, y: e.clientY });
});
document.addEventListener("dragleave", (e) => { if (!e.relatedTarget && !app.nativeDrag) app.showDropSpot(null); });
document.addEventListener("drop", (e) => {
  app.showDropSpot(null);
  const t = dropTarget(e.clientX, e.clientY);
  if (e.dataTransfer.types.includes("ppt/slides")) {
    e.preventDefault();
    let pkg = null;
    try { pkg = JSON.parse(e.dataTransfer.getData("ppt/slides")); } catch { /* not PowerPoint's */ }
    if (pkg?.data && pkg.isDataCompressed !== "True") {
      rpc("dropped_package", "slides", pkg.data, store.path || null)
        .then((r) => app.fromPowerPoint(r, t.list ? { pageAt: t.pageAt } : { at: t.point }, "Add"));
    }
    return;
  }
  if (!e.dataTransfer.files.length || app.info.native) return;
  e.preventDefault();
  const files = [...e.dataTransfer.files], decks = files.filter((f) => isDeck(f.name));
  if (files.length > decks.length) app.placeUploads(files.filter((f) => !isDeck(f.name)), placeAt(t));
  (async () => { for (const f of decks) await app.addDeckUpload(f, t); })();
});
// Edit ▸ Copy, Cut and Paste in the menu bar (the keys are handled above) do what the editor's
// own commands do, outside text fields
document.addEventListener("paste", (e) => {
  if (isField(e.target)) return;
  e.preventDefault();
  if (app.info.clipboard) return app.paste();
  // No system clipboard to read here: pictures the web view hands over, else FigAssemble's own copy
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
  if (files.length) app.placeUploads(files.map((f, i) => new File([f], f.name || `pasted-${i + 1}.png`, { type: f.type })), null);
  else app.paste();
});
for (const [type, cut] of [["copy", false], ["cut", true]]) {
  document.addEventListener(type, (e) => {
    if (isField(e.target) || !store.selection.length) return;
    e.preventDefault();
    app.copy(cut);
  });
}

// Preferences -------------------------------------------------------------------------------

function applyPrefs(p) {
  display.units = p.units || "cm";
  const root = document.documentElement;
  root.style.setProperty("--ui-scale", p.ui_scale || 1);
  root.dataset.theme = p.theme || "system";
  applyTheme(p);
  document.body.classList.toggle("no-tool-labels", p.show_tool_labels === false);
  document.body.classList.toggle("reduce-motion", !!p.reduced_motion);
  canvas.defaults = p;
  if (canvas.stage) canvas.setRulers(p.show_rulers !== false);
  document.dispatchEvent(new CustomEvent("fa-prefs", { detail: p }));
}

// The theme's colours: written into the page by the server at load, swapped here when Settings
// changes the theme (or its day and night themes)
let themeKey = null;
function applyTheme(p) {
  const key = [p.theme || "system", p.theme_day || "light", p.theme_night || "dark"];
  if (key.join("|") === themeKey) return;
  const first = themeKey === null;
  themeKey = key.join("|");
  if (first) return;
  rpc("theme_css", ...key).then((css) => {
    if (key.join("|") !== themeKey) return;
    document.getElementById("theme-vars").textContent = css;
    document.dispatchEvent(new CustomEvent("fa-prefs", { detail: app.prefs }));   // the rulers redraw in it
  }).catch(() => {});
}
// The system switching between light and dark: the rulers (drawn, not styled) follow
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  document.dispatchEvent(new CustomEvent("fa-prefs", { detail: app.prefs }));
});

// Start-up ------------------------------------------------------------------------------------

async function start() {
  app.info = await rpc("app_info");
  app.prefs = app.info.prefs;
  Object.assign(shapeCatalog, app.info.shapes || {});
  applyPrefs(app.prefs);
  canvas.init(document.getElementById("stage"));
  canvas.onKeyClick = (id) => app.toggleKeyObject(id);
  canvas.onTransform = (t) => app.noteTransform(t);
  canvas.onPaint = (hit, keyboard) => app.paintStyle(hit, keyboard);
  canvas.onMeasure = (id, len) => app.measured(id, len);
  canvas.onZoomBox = (id, box) => app.addZoomInset(id, box);
  canvas.onContextMenu = (x, y) => app.contextMenuAt(x, y);
  canvas.onEditSymbol = (id) => app.editSymbol(id);
  canvas.onEditEquation = (id) => app.editEquation(id);
  canvas.onFillArea = (p) => app.fillArea(p);
  canvas.keyObject = () => (app.prefs.align_to === "key" && store.selection.length > 1 ? app.keyObject() : null);
  rulers.init(document.querySelector(".stage-wrap"));
  // Dragging a new guide out of a ruler shows the guides if they were hidden
  rulers.onNeedGuides = () => {
    app.prefs.show_guides = true;
    app.savePrefs({ show_guides: true }).then(() => announce("Guides shown")).catch(() => {});
  };
  panels.init(app);
  splitters.init(app);
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
    const saved = await rpc("autosaved", store.autosaveKey).catch(() => []);
    if (saved.length) offerRecovery(saved);
  }
  canvas.fit();
  if (params.get("select")) store.select(params.get("select").split(","));   // e.g. for screenshots
  setInterval(() => app.refreshLinks().catch(() => {}), 2000);
  setInterval(() => {
    if (store.dirty && store.doc) rpc("autosave", store.doc, store.autosaveKey).catch(() => {});
  }, 60000);
  window.addEventListener("beforeunload", (e) => { if (store.dirty && !app.info.native) { e.preventDefault(); e.returnValue = ""; } });
  Object.assign(window.FA, { app, store, canvas, panels, inspector });   // for the smoke test's checks
  app.offerRecovery = offerRecovery;
  document.body.classList.add("ready");
  announce("FigAssemble is ready. Drop figure files onto the page, or press I to insert a picture.");
  if (params.get("selftest")) import("./selftest.js").then((m) => m.run(app, params));
  if (params.get("docshot")) import("./docshots.js").then((m) => m.run(app, params));   // the docs' screenshots
}

// Work that wasn't saved last time: recover a document, or delete copies that aren't wanted
function offerRecovery(saved) {
  const list = h("ul", { class: "recovery-list" });
  const deleteAll = h("button", { type: "button", class: "btn" }, "Delete all");
  let items = saved, dlg = null;
  const show = (left) => {
    items = left;
    if (!items.length) { dlg?.close(); return; }
    list.replaceChildren(...items.map((s) => {
      const when = new Date(s.modified * 1000).toLocaleString();
      const what = `${s.pages} page${s.pages === 1 ? "" : "s"}, ${s.objects} object${s.objects === 1 ? "" : "s"} · ${when}`;
      return h("li", {},
        h("div", { class: "recovery-name" }, s.title), h("div", { class: "hint" }, what),
        h("div", { class: "button-row" },
          button(`Recover ${s.title}, ${when}`, async () => {
            dlg.close();
            const res = await rpc("open_document", s.path);
            store.setDoc(finishEdits(res.doc), null);
            // Keep writing to this copy, so saving the document clears it
            store.autosaveKey = s.path.split(/[\\/]/).pop().replace(/\.figasm$/i, "");
            store.dirty = true;
            canvas.fit();
            announce(`Recovered ${s.title}`);
          }, "Recover", "primary"),
          button(`Delete ${s.title}, ${when}`, async () => {
            if (!(await panels.confirmDeleteRecovery(1))) return;
            show(await rpc("delete_autosaves", [s.path], store.autosaveKey));
            announce(`Deleted the unsaved copy of ${s.title}`);
          }, "Delete")));
    }));
  };
  deleteAll.addEventListener("click", async () => {
    if (!(await panels.confirmDeleteRecovery(items.length))) return;
    show(await rpc("delete_autosaves", items.map((s) => s.path), store.autosaveKey));
    announce("Deleted all unsaved work from earlier sessions");
  });
  show(saved);
  dlg = panels.dialog("Recover unsaved work?", h("div", {},
    h("p", {}, "FigAssemble kept copies of documents that weren't saved:"), list), [deleteAll], "Not now");
}

start().catch((err) => {
  console.error(err);
  document.body.prepend(Object.assign(document.createElement("p"), { className: "fatal", textContent: `FigAssemble couldn't start: ${err.message}` }));
});

export { app };

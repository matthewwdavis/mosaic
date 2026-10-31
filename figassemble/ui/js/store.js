// The document, the selection and undo history. Everything that changes the document goes
// through update() so it can be undone.

import { clone } from "./util.js";

const MAX_HISTORY = 200;

export const store = {
  doc: null,
  path: null,
  dirty: false,
  pageIndex: 0,
  selection: [],          // ids of selected top-level items on the current page
  history: [],
  future: [],
  listeners: new Set(),
  autosaveKey: null,
  afterChange: null,      // set by the canvas: attached line ends follow their objects

  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); },
  emit(what, detail) { for (const fn of this.listeners) fn(what, detail); },

  setDoc(doc, path = null) {
    this.doc = doc;
    this.path = path;
    this.dirty = false;
    this.pageIndex = 0;
    this.selection = [];
    this.history = [];
    this.future = [];
    this.autosaveKey = `doc-${Date.now().toString(36)}`;
    this.emit("doc", { reset: true });
    this.emit("selection");
  },

  page() { return this.doc.pages[this.pageIndex]; },
  items() { return this.page().items; },
  item(id) { return this.items().find((it) => it.id === id); },
  selected() { return this.selection.map((id) => this.item(id)).filter(Boolean); },

  // Snapshot-based undo: take a snapshot, mutate, record it
  snapshot() { return JSON.stringify({ doc: this.doc, pageIndex: this.pageIndex, selection: this.selection }); },
  record(snap, label) {
    this.history.push({ snap, label });
    if (this.history.length > MAX_HISTORY) this.history.shift();
    this.future = [];
    this.dirty = true;
  },
  update(label, fn, { select } = {}) {
    const snap = this.snapshot();
    const result = fn(this.doc);
    this.afterChange?.(this.doc);
    this.record(snap, label);
    if (select) this.selection = select;
    this.emit("doc", { label });
    if (select) this.emit("selection");
    return result;
  },
  // Live changes during a drag: one undo step when finished
  beginLive() { this._live = this.snapshot(); },
  live() { this.afterChange?.(this.doc); this.emit("doc", { live: true }); },
  endLive(label) {
    if (!this._live) return;
    this.record(this._live, label);
    this._live = null;
    this.emit("doc", { label });
  },
  cancelLive() {
    if (!this._live) return;
    this.restore(this._live);
    this._live = null;
  },
  restore(snap) {
    const s = JSON.parse(snap);
    this.doc = s.doc;
    this.pageIndex = Math.min(s.pageIndex, this.doc.pages.length - 1);
    this.selection = s.selection.filter((id) => this.item(id));
    this.emit("doc", {});
    this.emit("selection");
  },
  undo() {
    const h = this.history.pop();
    if (!h) return null;
    this.future.push({ snap: this.snapshot(), label: h.label });
    this.restore(h.snap);
    this.dirty = true;
    return h.label;
  },
  redo() {
    const f = this.future.pop();
    if (!f) return null;
    this.history.push({ snap: this.snapshot(), label: f.label });
    this.restore(f.snap);
    this.dirty = true;
    return f.label;
  },
  // Changes the engine makes on its own (auto-fitted text boxes) don't get an undo step
  silent(fn) { fn(this.doc); this.afterChange?.(this.doc); },

  select(ids) {
    this.selection = [...new Set(ids)].filter((id) => this.item(id));
    this.emit("selection");
  },
  setPage(i) {
    this.pageIndex = Math.max(0, Math.min(i, this.doc.pages.length - 1));
    this.selection = [];
    this.emit("page");
    this.emit("doc", {});
    this.emit("selection");
  },
  markSaved(path) {
    this.path = path;
    this.dirty = false;
    this.emit("saved");
  },
};

export function findItem(items, id) {
  for (const it of items) {
    if (it.id === id) return it;
    if (it.type === "group") {
      const f = findItem(it.items, id);
      if (f) return f;
    }
  }
  return null;
}

export { clone };

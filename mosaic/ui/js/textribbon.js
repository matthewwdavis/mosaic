// The Home tab's Text section: two rows of small controls, as in PowerPoint's Font group. Text
// style, font, size, bigger and smaller, line spacing; bold, italic, underline, raised and lowered
// text, colour, left/centre/right and top/middle/bottom. It works on the text boxes selected (one
// or several), or while typing in one (or in any shape, or a bracket's label) on the highlighted
// words: with only the caret, on what's typed next; alignment, line spacing and styles on the
// lines the words are in. Selecting text boxes, or typing in anything, shows the Home tab, and the
// tab before comes back afterwards unless another one was picked meanwhile (Settings:
// prefs.text_home_tab; the ribbon's followSelection, in panels.js).

import { SUBSCRIPT, SUPERSCRIPT, canvas } from "./canvas.js";
import { contextMenu } from "./contextmenu.js";
import { store } from "./store.js";
import { linked } from "./swatches.js";
import { applyToParagraph } from "./textstyles.js";
import { collapsed, common, nextSize, ordered, runsIn } from "./textformat.js";
import { announce, fmt, h, keepFieldKeys, pathIcon } from "./util.js";

const ICONS = {
  bigger: "M3 20L8.5 6 14 20M5.2 15h6.6M16.5 10.5L19 8l2.5 2.5M19 8v8",
  smaller: "M3 20L8.5 6 14 20M5.2 15h6.6M16.5 13.5L19 16l2.5-2.5M19 8v8",
  spacing: "M10 6h10M10 12h10M10 18h10M5 4v16M3 6.5L5 4l2 2.5M3 17.5L5 20l2-2.5",
  left: "M4 6h16M4 10h10M4 14h16M4 18h10", centre: "M4 6h16M7 10h10M4 14h16M7 18h10",
  right: "M4 6h16M10 10h10M4 14h16M10 18h10",
  top: "M4 4h16M4 20h16M8 8h8M8 11.5h8", middle: "M4 4h16M4 20h16M8 10.25h8M8 13.75h8",
  bottom: "M4 4h16M4 20h16M8 12.5h8M8 16h8",
};
const SPACINGS = [0.8, 0.9, 1, 1.15, 1.5, 2, 2.5, 3];
const SIZE_LIST = [5, 5.5, 6, 6.5, 7, 7.5, 8, 9, 10, 12, 14, 18, 24, 36];
const MIXED = "\u0000mixed";   // the style list's blank line, for text in several styles
const NAMES = { bold: "Bold", italic: "Italic", underline: "Underline" };
const ALIGN_NAMES = { l: "left", ctr: "centred", r: "right" }, ANCHOR_NAMES = { t: "top", ctr: "middle", b: "bottom" };
const isTextBox = (it) => it?.type === "shape" && !!it.textbox;

export const textRibbon = {
  app: null,
  ribbon: null,
  els: null,
  held: null,         // what a field works on while it has the focus

  build(app, ribbon) {
    this.app = app;
    this.ribbon = ribbon;
    const els = this.els = {};
    const glyph = (text, cls = "") => h("span", { class: `glyph ${cls}`, "aria-hidden": "true" }, text);
    const icon = (name) => pathIcon(ICONS[name]);
    const mini = (cmd, content, pressable = false) => {
      const c = app.commands[cmd];
      const b = h("button", { type: "button", class: "tool mini", title: c.keys ? `${c.label} (${c.keys})` : c.label,
        "aria-label": c.label, "data-cmd": cmd, tabindex: -1, "aria-pressed": pressable ? "false" : null }, content);
      // (the text being typed keeps the focus, its words still highlighted)
      b.addEventListener("mousedown", (e) => e.preventDefault());
      b.addEventListener("click", () => app.run(cmd));
      return b;
    };
    els.style = h("select", { class: "text-style", "aria-label": "Text style", title: "Text style: one of the figure's named formats" });
    els.font = h("input", { type: "text", class: "text-font", list: "ribbon-fonts", "aria-label": "Font", title: "Font",
      spellcheck: "false", autocomplete: "off" });
    els.size = h("input", { type: "text", inputmode: "decimal", class: "text-size", list: "ribbon-sizes",
      "aria-label": "Text size in points", title: "Text size (pt)", spellcheck: "false", autocomplete: "off" });
    els.fonts = h("datalist", { id: "ribbon-fonts" });
    els.bigger = mini("textBigger", icon("bigger"));
    els.smaller = mini("textSmaller", icon("smaller"));
    els.spacing = mini("lineSpacing", [icon("spacing"), glyph("▾", "more")]);
    els.bold = mini("textBold", glyph("B", "bold"), true);
    els.italic = mini("textItalic", glyph("I", "italic"), true);
    els.underline = mini("textUnderline", glyph("U", "underline"), true);
    els.sup = mini("textSuperscript", glyph("x²"), true);
    els.sub = mini("textSubscript", glyph("x₂"), true);
    els.bar = h("span", { class: "colour-bar" });
    els.colour = mini("textColour", [h("span", { class: "colour-a", "aria-hidden": "true" }, glyph("A"), els.bar), glyph("▾", "more")]);
    for (const b of [els.spacing, els.colour]) b.setAttribute("aria-haspopup", "menu");
    els.picker = h("input", { type: "color", class: "visually-hidden", tabindex: -1, "aria-hidden": "true" });
    els.align = { l: mini("textLeft", icon("left"), true), ctr: mini("textCentre", icon("centre"), true),
      r: mini("textRight", icon("right"), true) };
    els.anchor = { t: mini("textTop", icon("top"), true), ctr: mini("textMiddle", icon("middle"), true),
      b: mini("textBottom", icon("bottom"), true) };
    const sep = () => h("span", { class: "text-sep", "aria-hidden": "true" });
    this.group = h("div", { class: "rgroup text-group", role: "group", "aria-labelledby": "rgroup-text" },
      h("div", { class: "rgroup-items text-rows" },
        h("div", { class: "text-row" }, els.style, els.font, els.size, els.bigger, els.smaller, els.spacing),
        h("div", { class: "text-row" }, els.bold, els.italic, els.underline, els.sup, els.sub, els.colour, sep(),
          els.align.l, els.align.ctr, els.align.r, sep(), els.anchor.t, els.anchor.ctr, els.anchor.b)),
      h("div", { class: "rgroup-label", id: "rgroup-text" }, "Text"),
      els.fonts, h("datalist", { id: "ribbon-sizes" }, ...SIZE_LIST.map((v) => h("option", { value: v }))), els.picker);
    this.fields();
    this.listen();
    return this.group;
  },

  // The font and size fields and the style list. While one has the focus, it works on what was
  // selected when it got it (the words highlighted in the text, which no longer shows them)
  fields() {
    const { font, size, style } = this.els;
    const back = () => { if (canvas.editing) canvas.restoreSelection(); };   // typing carries on
    for (const el of [font, size, style]) {
      el.addEventListener("focus", () => {
        this.held = this.target();
        el.dataset.was = el.value;
        if (el === font && !this.els.fonts.childElementCount) {
          this.els.fonts.replaceChildren(...(this.app.fonts || []).map((f) => h("option", { value: f })));
        }
      });
      el.addEventListener("blur", () => { this.held = null; queueMicrotask(() => this.refresh()); });
    }
    const commit = (el, fn) => {
      const v = el.value.trim();
      if (!v || v === el.dataset.was) return;
      if (fn(v) !== false) el.dataset.was = v;
    };
    const commitFont = () => commit(font, (v) => this.change("Font", { run: (r) => { r.font = v; } }));
    const commitSize = () => commit(size, (v) => {
      const pt = parseFloat(v.replace(",", "."));
      if (!(pt >= 0.5 && pt <= 4000)) {
        announce(`“${v}” isn't a text size; type points, such as 6 or 7.5`);
        size.value = size.dataset.was;
        return false;
      }
      return this.change("Text size", { run: (r) => { r.size = pt; } });
    });
    for (const [el, done] of [[font, commitFont], [size, commitSize]]) {
      el.addEventListener("change", done);
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); done(); back(); }
        else if (e.key === "Escape") { e.preventDefault(); el.value = el.dataset.was; back(); }
        keepFieldKeys(e);
      });
    }
    style.addEventListener("change", () => {
      if (style.value === MIXED) return;
      const st = (store.doc.text_styles || []).find((x) => x.id === style.value);
      this.change(st ? "Text style" : "No text style", { para: (p) => { if (st) applyToParagraph(p, st); else delete p.style; } });
      announce(st ? `Text style ${st.name}` : "No text style");
      back();
    });
  },

  listen() {
    store.on((what, detail) => {
      if (what === "doc" && detail?.live) return;   // mid-drag: nothing about the text changes
      if (["doc", "selection", "page"].includes(what)) this.refresh();
    });
    document.addEventListener("fa-editing", () => this.refresh());
    let queued = false;
    document.addEventListener("selectionchange", () => {
      if (!canvas.editing || queued) return;
      queued = true;
      queueMicrotask(() => { queued = false; this.refresh(); });
    });
  },

  // What the section works on now: the text box being typed in, with the words highlighted (or
  // the caret), or the text boxes selected; null for anything else
  target() {
    const ed = canvas.editing;
    // (typing in a text box, in any other shape, or in a bracket's label: everything the editor
    // opens on)
    if (ed) return ["shape", "bracket"].includes(store.item(ed.id)?.type) ? { typing: true, id: ed.id, range: canvas.editorRange() } : null;
    const sel = store.doc ? store.selected() : [];
    return sel.length && sel.every(isTextBox) ? { typing: false, ids: sel.map((it) => it.id) } : null;
  },
  // What it would change: the runs (for the caret, the look typing there would have), the
  // paragraphs and the texts
  look(t) {
    if (!t.typing) {
      const texts = t.ids.map((id) => store.item(id)?.text).filter(Boolean);
      const paras = texts.flatMap((x) => x.paragraphs || []);
      const all = paras.flatMap((p) => p.runs || []), filled = all.filter((r) => (r.t || "").length);
      return { runs: filled.length ? filled : all, paras, texts };
    }
    const model = canvas.editorModel(), texts = [store.item(t.id).text];
    if (!t.range) return { runs: model.flatMap((p) => p.runs), paras: model, texts };
    const r = ordered(t.range), runs = collapsed(r) ? [] : runsIn(model, r);
    return { runs: runs.length ? runs : [canvas.caretStyle()], paras: model.slice(r.start[0], r.end[0] + 1), texts };
  },

  refresh() {
    if (!this.els || !store.doc) return;
    const t = this.target();
    this.ribbon.followSelection(!!t);
    const els = this.els;
    const controls = [els.style, els.font, els.size, els.bigger, els.smaller, els.spacing, els.bold, els.italic, els.underline,
      els.sup, els.sub, els.colour, ...Object.values(els.align), ...Object.values(els.anchor)];
    for (const el of controls) el.disabled = !t;
    if (!t && controls.some((el) => el.tabIndex === 0)) {
      // (the ribbon's way in by Tab moves to a button that can still be pressed)
      for (const el of controls) el.tabIndex = -1;
      const first = this.group.closest(".ribbon-panel")?.querySelector("button.tool:not(:disabled)");
      if (first) first.tabIndex = 0;
    }
    const look = t ? this.look(t) : { runs: [], paras: [], texts: [] };
    const runs = look.runs, every = (f) => runs.length > 0 && runs.every(f);
    const press = (b, on) => b.setAttribute("aria-pressed", on ? "true" : "false");
    press(els.bold, every((r) => r.bold));
    press(els.italic, every((r) => r.italic));
    press(els.underline, every((r) => r.underline));
    press(els.sup, every((r) => (r.baseline || 0) > 0));
    press(els.sub, every((r) => (r.baseline || 0) < 0));
    const font = t ? common(runs.map((r) => r.font || "Helvetica")) : "";
    const size = t ? common(runs.map((r) => r.size ?? 6)) : null;
    if (document.activeElement !== els.font) els.font.value = font ?? "";
    if (document.activeElement !== els.size) els.size.value = size == null ? "" : fmt(size, 2);
    els.font.placeholder = t && font === undefined ? "Several" : "";
    const colour = t ? common(runs.map((r) => (r.color || "#000000").toLowerCase())) : null;
    els.bar.style.background = colour || "";
    els.bar.classList.toggle("mixed", !!t && colour === undefined);
    const align = t ? common(look.paras.map((p) => p.align || "l")) : null;
    for (const [k, b] of Object.entries(els.align)) press(b, align === k);
    const anchor = t ? common(look.texts.map((x) => x.anchor || "t")) : null;
    for (const [k, b] of Object.entries(els.anchor)) press(b, anchor === k);
    this.fillStyles(t ? common(look.paras.map((p) => p.style || "")) : undefined);
  },
  fillStyles(current) {
    const sel = this.els.style, styles = store.doc.text_styles || [];
    const key = JSON.stringify(styles.map((s) => [s.id, s.name]));
    if (sel.dataset.key !== key) {
      sel.dataset.key = key;
      sel.replaceChildren(h("option", { value: MIXED, hidden: true }, ""), h("option", { value: "" }, "No style"),
        ...styles.map((s) => h("option", { value: s.id }, s.name)));
    }
    if (document.activeElement !== sel) sel.value = current === undefined ? MIXED : current;
  },


  // Changes -----------------------------------------------------------------------------

  change(label, change, t = this.held || this.target()) {
    if (!t) {
      announce("Select a text box, or type in one, first");
      return false;
    }
    canvas.changeText(label, change, t);
    return true;
  },
  step(dir) {
    if (this.change(dir > 0 ? "Bigger text" : "Smaller text", { run: (r) => { r.size = nextSize(r.size ?? 6, dir > 0); } })) {
      const t = this.target(), size = t && common(this.look(t).runs.map((r) => r.size ?? 6));
      announce(size == null ? (dir > 0 ? "Bigger text" : "Smaller text") : `Text size ${fmt(size, 2)} pt`);
    }
  },
  // Bold, italic and underline: while typing, as their keys do (⌘B, ⌘I, ⌘U); otherwise on for
  // all the text unless all of it has it already
  toggle(key) {
    const t = this.target();
    if (t?.typing) {
      canvas.restoreSelection();
      document.execCommand(key);
      return this.refresh();
    }
    if (!t) return this.change(NAMES[key]);
    const on = !this.look(t).runs.every((r) => r[key]);
    this.change(NAMES[key], { run: (r) => { r[key] = on; } }, t);
    announce(`${NAMES[key]} ${on ? "on" : "off"}`);
  },
  // Raised (dir > 0) or lowered text
  script(dir) {
    const t = this.target(), base = dir > 0 ? SUPERSCRIPT : SUBSCRIPT, name = dir > 0 ? "Superscript" : "Subscript";
    if (t?.typing) {
      canvas.restoreSelection();
      document.execCommand(dir > 0 ? "superscript" : "subscript");
      return this.refresh();
    }
    if (!t) return this.change(name);
    const on = !this.look(t).runs.every((r) => (r.baseline || 0) === base);
    this.change(name, { run: (r) => { if (on) r.baseline = base; else delete r.baseline; } }, t);
    announce(`${name} ${on ? "on" : "off"}`);
  },
  align(v) {
    if (this.change("Align text", { para: (p) => { p.align = v; } })) announce(`Text ${ALIGN_NAMES[v]}`);
  },
  anchor(v) {
    if (this.change("Text position", { body: (x) => { x.anchor = v; } })) announce(`Text at the ${ANCHOR_NAMES[v]} of its box`);
  },
  colourMenu() {
    const t = this.target();
    if (!t) return this.change("Text colour");
    const runs = this.look(t).runs, btn = this.els.colour;
    const now = common(runs.map((r) => (r.color || "#000000").toLowerCase())), nowSwatch = common(runs.map((r) => r.swatch || null));
    const set = (color, swatch) => this.change("Text colour", { run: (r) => { linked(r, swatch).color = color; } }, t);
    const all = store.doc.swatches || [];
    const r = btn.getBoundingClientRect();
    contextMenu.show([
      ...all.map((s) => ({ label: s.name, swatch: s.color, checked: s.id === nowSwatch, run: () => set(s.color, s.id) })),
      all.length ? "-" : { label: "No swatches in this figure yet", disabled: true, run: () => {} },
      { label: "Black", swatch: "#000000", checked: !nowSwatch && now === "#000000", run: () => set("#000000", null) },
      { label: "Other colour…", run: () => this.pickColour(now || "#000000", (c) => set(c, null)) },
      now && !nowSwatch ? { label: "Add this colour as a swatch", run: () => set(now, this.app.addSwatch(now)) } : null,
      { label: "Swatches…", run: () => this.app.run("swatches") },
    ], r.left, r.bottom + 2, btn, { label: "Text colour" });
  },
  pickColour(now, done) {
    const p = this.els.picker;
    p.value = now;
    p.onchange = () => done(p.value);
    p.click();
  },
  spacingMenu() {
    const t = this.target();
    if (!t) return this.change("Line spacing");
    const now = common(this.look(t).paras.map((p) => p.line_spacing || { pct: 1 }));
    const set = (v) => this.change("Line spacing", { para: (p) => {
      if (v.pct === 1) delete p.line_spacing;
      else p.line_spacing = v;
    } }, t);
    const btn = this.els.spacing, r = btn.getBoundingClientRect();
    contextMenu.show([
      ...SPACINGS.map((v) => ({ label: v === 1 ? "1.0 (single)" : fmt(v, 2), checked: now?.pct === v && !now.pts, run: () => set({ pct: v }) })),
      "-",
      { label: now?.pts ? `Exactly ${fmt(now.pts, 2)} pt…` : "Exactly…", checked: !!now?.pts, run: () => this.exactSpacing(now, set) },
    ], r.left, r.bottom + 2, btn, { label: "Line spacing" });
  },
  // Line spacing as a fixed distance between baselines (PowerPoint's Exactly)
  exactSpacing(now, set) {
    const input = h("input", { type: "text", inputmode: "decimal", id: "exact-spacing", value: fmt(now?.pts || 7.2, 2) });
    const ok = h("button", { type: "submit", class: "btn primary", value: "ok" }, "Set");
    ok.addEventListener("click", () => {
      const v = parseFloat(input.value.replace(",", "."));
      if (v > 0) set({ pts: v });
    });
    const dlg = this.ribbon.dialog("Line spacing", h("div", { class: "field" },
      h("label", { for: "exact-spacing" }, "Baseline to baseline (pt)"), input), [ok]);
    dlg.addEventListener("close", () => { if (canvas.editing) canvas.restoreSelection(); });   // typing carries on
  },
};

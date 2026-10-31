// The properties panel: what's selected and every setting it has. All controls are real,
// labelled form fields grouped in fieldsets, so they work with the keyboard and screen readers.

import { rpc } from "./api.js";
import { canvas, findDeep, shiftItem } from "./canvas.js";
import { store } from "./store.js";
import { UNIT_LABEL, announce, fmt, fromUnit, h, isCurved, itemLabel, itemsBBox, lineSamples, shapeCatalog, shapeName, toUnit } from "./util.js";

const DASHES = [["solid", "Solid"], ["sysDot", "Round dot"], ["sysDash", "Short dash"], ["dash", "Dash"],
  ["dashDot", "Dash dot"], ["lgDash", "Long dash"], ["lgDashDot", "Long dash dot"], ["lgDashDotDot", "Long dash dot dot"],
  ["dot", "Dot"]];
const HEADS = [["none", "None"], ["triangle", "Triangle"], ["stealth", "Stealth"], ["arrow", "Open arrow"],
  ["oval", "Circle"], ["diamond", "Diamond"]];
const SIZES = [["sm", "Small"], ["med", "Medium"], ["lg", "Large"]];
const ROUNDED_HEADS = ["triangle", "stealth", "arrow", "diamond"];   // heads whose corners can be rounded
let fieldId = 0;

export const inspector = {
  init(root, app) {
    this.root = root;
    this.app = app;
    this.linkStatus = {};
    store.on((what, detail) => {
      if (what === "doc" && detail?.live) return this.refreshValues();
      if (["selection", "doc", "page", "saved"].includes(what)) this.schedule();
    });
  },
  schedule() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = null; this.render(); });
  },
  units() { return this.app.prefs.units || "cm"; },
  pageUnits() { return this.app.prefs.page_units || "mm"; },

  render() {
    if (!store.doc) return;
    // Don't rebuild under the user's fingers: a focused field keeps its edit
    const active = document.activeElement;
    if (active && this.root.contains(active) && active.matches("input[type=text], input[type=number], textarea")) {
      return this.refreshValues();
    }
    const sel = store.selected();
    const parts = [];
    if (sel.length === 0) parts.push(...this.pageSections());
    else if (sel.length === 1) parts.push(...this.itemSections(sel[0]));
    else parts.push(...this.multiSections(sel));
    this.root.replaceChildren(...parts);
  },
  // During drags only the numbers change
  refreshValues() {
    const sel = store.selected();
    if (sel.length !== 1) return;
    for (const input of this.root.querySelectorAll("[data-bind]")) {
      if (input === document.activeElement) continue;
      const v = this.bound(sel[0], input.dataset.bind);
      if (v !== undefined) input.value = v;
    }
  },
  bound(it, key) {
    const u = this.units();
    if (key === "rot") return fmt(it.rot || 0, 2);
    if (it.frame && "xywh".includes(key)) return fmt(toUnit(it.frame["xywh".indexOf(key)], u), digits(u));
    const m = it.points && /^p(\d+)([xy])$/.exec(key);
    if (m && it.points[Number(m[1])]) return fmt(toUnit(it.points[Number(m[1])][m[2] === "x" ? 0 : 1], u), digits(u));
    return undefined;
  },

  // Editing helpers --------------------------------------------------------------------

  edit(label, fn) {
    const ids = [...store.selection];
    store.update(label, (doc) => {
      for (const id of ids) {
        const it = findDeep(doc.pages[store.pageIndex].items, id);
        if (it) fn(it, doc);
      }
    });
  },
  editPage(label, fn) { store.update(label, (doc) => fn(doc.pages[store.pageIndex], doc)); },

  // Page -------------------------------------------------------------------------------

  pageSections() {
    const page = store.page();
    const pu = this.pageUnits();
    const { standard, journal, type } = pagePreset(page, this.app.info);
    const standards = this.app.info.standard_sizes || [];
    const journals = this.app.info.journals || [];
    const len = (mm) => `${fmt(toUnit(mm * MM_PT, pu), 1)} ${UNIT_LABEL[pu]}`;
    const setStandard = (name) => {
      const s = standards.find((x) => x.name === name);
      if (!s) return;
      this.editPage(`${name} page`, (p) => { p.width = s.width_mm * MM_PT; p.height = s.height_mm * MM_PT; p.preset = { standard: name }; });
      canvas.fit();
      announce(`Page is now ${name}, ${len(s.width_mm)} by ${len(s.height_mm)}`);
    };
    const setJournal = (jname, tname) => {
      const j = journals.find((x) => x.name === jname);
      if (!j) { this.editPage("No journal size", (p) => { delete p.preset; }); return; }
      // A journal on its own starts at its widest figure type (most multi-panel figures)
      const t = j.types.find((x) => x.name === tname) || j.types.reduce((a, b) => (b.width_mm > a.width_mm ? b : a));
      this.editPage(`${j.name} ${t.name.toLowerCase()} page`, (p) => {
        p.width = t.width_mm * MM_PT;
        p.height = j.depth_mm * MM_PT;
        p.preset = { journal: j.name, type: t.name };
      });
      canvas.fit();
      announce(`Page is now a ${j.name} ${t.name.toLowerCase()} figure, ${len(t.width_mm)} wide and ${len(j.depth_mm)} deep`);
    };
    return [
      section("Page", [
        textField("Name", page.name, (v) => this.editPage("Rename page", (p) => { p.name = v || p.name; })),
        selectField("Standard size", standard ? standard.name : "",
          [["", journal ? "—" : "Custom size"], ...standards.map((s) => [s.name, `${s.name} (${len(s.width_mm)} × ${len(s.height_mm)})`])],
          setStandard),
        selectField("Journal", journal ? journal.name : "", [["", "None"], ...journals.map((j) => [j.name, j.name])],
          (v) => setJournal(v)),
        selectField("Figure type", type ? type.name : "",
          journal ? journal.types.map((t) => [t.name, `${t.name} — ${len(t.width_mm)} wide`]) : [["", "Choose a journal first"]],
          (v) => setJournal(journal.name, v), { disabled: !journal }),
        journal ? h("p", { class: "hint" }, `${journal.name}: ${journal.note} Source: ${journal.source}.`) : null,
        row(numField("Width", page.width, pu, (v) => this.editPage("Page width", (p) => { p.width = Math.max(v, 1); delete p.preset; }), { min: 1 }),
          numField("Height", page.height, pu, (v) => this.editPage("Page height", (p) => {
            p.height = Math.max(v, 1);
            if (p.preset?.standard) delete p.preset;   // a journal figure may be shorter than the full depth
          }), { min: 1 })),
        h("div", { class: "button-row" },
          button("Swap width and height", () => this.editPage("Rotate page", (p) => { [p.width, p.height] = [p.height, p.width]; delete p.preset; }), "⟲"),
          button(journal ? "Fit the page height to the content (keeps the column width)" : "Fit page to content",
            () => this.app.run("fitPage"), "Fit to content")),
        radioField("Background", page.background ? "white" : "none", [["none", "Transparent"], ["white", "White"]],
          (v) => this.editPage("Background", (p) => { p.background = v === "white" ? "#ffffff" : null; })),
      ]),
      section("Document", [
        textField("Title", store.doc.meta?.title || "", (v) => store.update("Rename document", (d) => { d.meta.title = v; })),
        h("p", { class: "hint" }, `${store.doc.pages.length} page${store.doc.pages.length === 1 ? "" : "s"} · `
          + `${Object.keys(store.doc.assets).length} placed file${Object.keys(store.doc.assets).length === 1 ? "" : "s"}`),
      ]),
      h("p", { class: "hint" }, "Drop figure files (PDF, SVG, PNG, JPEG, TIFF) onto the page to place them at true size. "
        + "Hold Option (Alt) while dropping to store a copy without linking to the file."),
    ];
  },

  // One item -----------------------------------------------------------------------------

  itemSections(it) {
    const out = [this.headerSection(it), this.arrangeSection(it)];
    if (it.type === "picture") out.push(this.pictureSection(it));
    if (it.type === "shape") {
      if (!it.textbox) out.push(this.geometrySection(it));
      if (it.text) out.push(this.textSection(it));
      if (!it.textbox || it.fill || it.stroke) out.push(this.fillSection(it));
      out.push(this.strokeSection(it));
      if ((shapeCatalog.shapes[it.geom]?.open || it.geom === "custom") && it.stroke) out.push(this.endsSection(it));
      if (!it.textbox || it.fill || it.stroke) out.push(this.outlineSection(it));
      if (it.textbox && !it.text) out.push(this.textSection(it));
    }
    if (it.type === "line") {
      out.push(this.strokeSection(it));
      out.push(this.endsSection(it));
      out.push(this.outlineSection(it));
    }
    if (it.type === "group") out.push(section("Group", [
      h("p", { class: "hint" }, `${it.items.length} objects. Ungroup (${this.app.mod}Shift+G) to edit them one by one.`),
      button("Ungroup", () => this.app.run("ungroup"), "Ungroup"),
    ]));
    return out;
  },
  headerSection(it) {
    const kids = [h("p", { class: "kind" }, kindName(it)),
      textField("Name", it.name || "", (v) => this.edit("Rename", (x) => { x.name = v; }))];
    if (it.type === "picture" || it.type === "group") {
      kids.push(textArea("Description for screen readers", it.alt || "", (v) => this.edit("Description", (x) => { x.alt = v; })));
    }
    kids.push(h("div", { class: "button-row" },
      toggle("Lock position", !!it.locked, (on) => this.edit(on ? "Lock" : "Unlock", (x) => { x.locked = on; }), "🔒 Lock"),
      toggle("Hide", !!it.hidden, (on) => this.edit(on ? "Hide" : "Show", (x) => { x.hidden = on; }), "Hide")));
    return section("Selected", kids);
  },
  arrangeSection(it) {
    const u = this.units();
    if (it.type === "line") {
      const n = it.points.length;
      const samples = lineSamples(it);
      let length = 0;
      for (let i = 1; i < samples.length; i++) length += Math.hypot(samples[i][0] - samples[i - 1][0], samples[i][1] - samples[i - 1][1]);
      const rows = it.points.map((p, i) => {
        const name = i === 0 ? "Start" : i === n - 1 ? "End" : `Point ${i}`;
        const setPt = (axis) => (v) => this.edit("Move point", (x) => { x.points[i][axis] = v; });
        return h("div", { class: "point-row" },
          row(numField(`${name} X`, p[0], u, setPt(0), { bind: `p${i}x` }), numField(`${name} Y`, p[1], u, setPt(1), { bind: `p${i}y` })),
          i > 0 && i < n - 1 ? button(`Remove ${name.toLowerCase()}`, () => canvas.removePoint(it.id, i), "Remove point", "small") : null);
      });
      return section("Points", [
        radioField("Path", it.curve === "smooth" ? "smooth" : "straight",
          [["straight", "Straight segments"], ["smooth", "Smooth curve"]],
          (v) => this.edit(v === "smooth" ? "Curve line" : "Straight segments", (x) => { x.curve = v; })),
        ...rows,
        h("div", { class: "button-row" },
          button("Add a point halfway along the longest stretch", () => this.app.run("addPoint"), "Add point"),
          n > 2 ? button("Remove the middle points to make the line straight", () => this.app.run("straighten"), "Make straight") : null),
        h("p", { class: "hint" }, `Length ${fmt(toUnit(length, u), 2)} ${UNIT_LABEL[u]}. On the page, drag the hollow handle `
          + "halfway along the line to bend it; double-click a point to remove it, or the line to add one."),
      ]);
    }
    if (it.type === "group") {
      const b = itemsBBox(it.items);
      const move = (axis) => (v) => this.edit("Move", (x) => {
        const bb = itemsBBox(x.items);
        const orig = JSON.parse(JSON.stringify(x));
        shiftItem(x, orig, axis === 0 ? v - bb[0] : 0, axis === 1 ? v - bb[1] : 0);
      });
      return section("Position", [row(numField("X", b[0], u, move(0)), numField("Y", b[1], u, move(1))),
        h("p", { class: "hint" }, `${fmt(toUnit(b[2] - b[0], u), 2)} × ${fmt(toUnit(b[3] - b[1], u), 2)} ${UNIT_LABEL[u]}`)]);
    }
    const [x, y, w, hh] = it.frame;
    const lockAspect = it.type === "picture";
    const setW = (v) => this.edit("Resize", (o) => {
      const nw = Math.max(v, 0.1);
      if (lockAspect) o.frame[3] = o.frame[3] * nw / o.frame[2];
      o.frame[2] = nw;
    });
    const setH = (v) => this.edit("Resize", (o) => {
      const nh = Math.max(v, 0.1);
      if (lockAspect) o.frame[2] = o.frame[2] * nh / o.frame[3];
      o.frame[3] = nh;
    });
    const kids = [
      row(numField("X", x, u, (v) => this.edit("Move", (o) => { o.frame[0] = v; }), { bind: "x" }),
        numField("Y", y, u, (v) => this.edit("Move", (o) => { o.frame[1] = v; }), { bind: "y" })),
      row(numField("Width", w, u, setW, { bind: "w", min: 0.1 }), numField("Height", hh, u, setH, { bind: "h", min: 0.1 })),
      row(numField("Rotation", it.rot || 0, "deg", (v) => this.edit("Rotate", (o) => { o.rot = ((v % 360) + 360) % 360; }), { bind: "rot", step: 1 }),
        h("div", { class: "button-row inline" },
          toggle("Flip horizontally", !!it.flip_h, (on) => this.edit("Flip", (o) => { o.flip_h = on; }), "⇋"),
          toggle("Flip vertically", !!it.flip_v, (on) => this.edit("Flip", (o) => { o.flip_v = on; }), "⇵"))),
    ];
    if (lockAspect) kids.push(h("p", { class: "hint" }, "Width and height keep the picture's proportions."));
    if (it.type === "picture") {
      kids.push(transparencyField("Transparency", it.opacity, (op) => this.edit("Transparency", (o) => { o.opacity = op; })));
    }
    return section("Position and size", kids);
  },
  pictureSection(it) {
    const a = store.doc.assets[it.asset];
    const [sw] = a.size_pt;
    const [l, t, r, b] = it.crop || [0, 0, 0, 0];
    const scalePct = (it.frame[2] / (sw * (1 - l - r))) * 100;
    const variants = Object.keys(a.variants).map((k) => k.toUpperCase()).join(" + ");
    const status = h("p", { class: "link-status", id: `link-${it.id}` }, "Checking file…");
    this.updateLinkStatus(a, it.asset, status);
    const exportKinds = [["auto", "Automatic (best copy for each format)"], ...Object.keys(a.variants).map((k) => [k, `Always the ${k.toUpperCase()} copy`])];
    return section("Picture", [
      h("p", { class: "file-name", title: a.name }, a.name),
      status,
      h("p", { class: "hint" }, `Copies found: ${variants}. `
        + (a.variants.pdf ? "PDF export uses the PDF copy unchanged" : a.variants.svg ? "PDF export converts the SVG (no PDF copy)" : "")
        + (a.variants.svg ? "; SVG export uses the SVG copy unchanged." : a.variants.pdf ? "; SVG export converts the PDF (no SVG copy)." : ".")),
      h("p", { class: `scale ${Math.abs(scalePct - 100) > 0.05 ? "warn" : ""}` },
        `Scale ${fmt(scalePct, 1)}%` + (Math.abs(scalePct - 100) > 0.05 ? ` — text in it prints at ${fmt(scalePct, 1)}% of its size` : " (true size)")),
      h("div", { class: "button-row" },
        button("Crop picture", () => canvas.startCrop(it.id), "Crop"),
        button("Reset crop", () => this.edit("Reset crop", (o) => {
          const sc = o.frame[2] / (sw * (1 - o.crop[0] - o.crop[2]));
          o.crop = [0, 0, 0, 0];
          o.frame[2] = a.size_pt[0] * sc;
          o.frame[3] = a.size_pt[1] * sc;
        }), "Reset crop"),
        button("Set to true size (100%)", () => this.edit("True size", (o) => {
          const sc = o.frame[2] / (sw * (1 - o.crop[0] - o.crop[2]));
          o.frame[2] /= sc;
          o.frame[3] /= sc;
        }), "100%")),
      selectField("Export from", it.source || "auto", exportKinds, (v) => this.edit("Export source", (o) => { o.source = v; })),
      h("div", { class: "button-row" },
        button("Replace with another file", () => this.app.run("replacePicture"), "Replace…"),
        button("Show the linked file in the Finder", () => this.app.run("revealPicture"), "Show file"),
        button("Stop following the file; keep the stored copy", () => this.app.run("unlinkPicture"), "Unlink")),
    ]);
  },
  async updateLinkStatus(asset, assetId, el) {
    try {
      const st = await rpc("link_status", { [assetId]: asset }, store.path);
      const s = st[assetId];
      const src = asset.variants[asset.primary]?.src;
      const label = { linked: "🔗 Linked — updates when the file changes", missing: "⚠ Linked file not found — using the stored copy",
        embedded: "📦 Stored in this document only" }[s] || s;
      el.textContent = label;
      el.className = `link-status ${s}`;
      if (src) el.title = src;
    } catch { el.textContent = ""; }
  },
  // Which shape it is, its adjustments (the yellow handles' values) and corner rounding
  geometrySection(it) {
    const info = shapeCatalog.shapes[it.geom];
    const kids = [];
    if (it.geom !== "custom") {
      const groups = shapeCatalog.groups.map((g) => [g.title, g.shapes.map((geom) => [geom, shapeName(geom)])]);
      if (!shapeCatalog.groups.some((g) => g.shapes.includes(it.geom))) groups.push(["From PowerPoint", [[it.geom, shapeName(it.geom)]]]);
      kids.push(groupedSelectField("Shape", it.geom, groups, (v) => this.edit("Change shape", (o) => {
        o.geom = v;
        o.adj = {};
        if (!shapeCatalog.shapes[v]?.open) { o.arrow_start = null; o.arrow_end = null; }
      })));
    }
    const fields = (info?.adjust || []).map((a) => numField(a.label, (it.adj?.[a.name] ?? a.default) * a.factor, a.unit,
      (v) => this.setAdjust(it.id, a, v), { step: 1, min: a.unit === "deg" || a.min === null ? undefined : a.min * a.factor,
        max: a.unit === "deg" || a.max === null ? undefined : a.max * a.factor }));
    const roundable = info?.corners || it.geom === "custom";
    if (roundable) fields.push(numField("Corner rounding", (it.rounding || 0) * 100, "%", (v) => this.edit("Corner rounding", (o) => {
      o.rounding = Math.min(Math.max(v, 0), 100) / 100;
      if (!o.rounding) delete o.rounding;
    }), { min: 0, max: 100, step: 5 }));
    for (let i = 0; i < fields.length; i += 2) kids.push(fields[i + 1] ? row(fields[i], fields[i + 1]) : fields[i]);
    if (it.geom === "arc") {
      kids.push(button("Turn this arc into a curve with points you can drag", () => this.app.run("shapeToCurve"), "Make editable curve"));
      kids.push(h("p", { class: "hint" }, "The curve passes through points along the arc, so its shape may shift by a fraction of a point."));
    }
    const hints = [];
    if (info?.adjust?.length) hints.push("Drag the yellow handles on the page to adjust the shape.");
    if (/^star\d+$/.test(it.geom)) hints.push("Inner radius is a percentage of the outer radius.");
    if (roundable) hints.push("Corner rounding: 0% keeps the corners sharp; 100% is as round as the shape allows.");
    if (hints.length) kids.push(h("p", { class: "hint" }, hints.join(" ")));
    return section("Shape", kids);
  },
  // A typed adjustment, kept inside the range its handle allows on this shape
  async setAdjust(id, a, shown) {
    let v = shown / a.factor;
    if (a.unit === "deg") v = ((v % 360) + 360) % 360;
    const it = store.item(id);
    if (!it) return;
    const stored = await rpc("clamp_adjust", { geom: it.geom, frame: it.frame, adj: it.adj }, a.name, v);
    this.edit(a.label, (o) => { o.adj = { ...(o.adj || {}), [a.name]: stored }; });
    if (Math.abs(stored - v) > 1e-6) {
      announce(`${a.label} goes up to ${fmt(stored * a.factor, 1)}${a.unit === "deg" ? "°" : "%"} on this shape`);
    }
  },
  fillSection(it) {
    const f = it.fill;
    const mode = !f ? "none" : f.gradient ? "gradient" : "solid";
    const opts = [["none", "No fill"], ["solid", "Colour"]];
    if (mode === "gradient") opts.push(["gradient", "Gradient (from PowerPoint)"]);
    const kids = [selectField("Fill", mode, opts, (v) => this.edit("Fill", (o) => {
      if (v === "none") o.fill = null;
      else if (v === "solid") o.fill = { color: o.fill?.color || "#ffffff", opacity: o.fill?.opacity ?? 1 };
    }))];
    if (mode === "solid") kids.push(row(
      colorField("Fill colour", f.color, (v) => this.edit("Fill colour", (o) => { o.fill = { ...o.fill, color: v }; })),
      transparencyField("Fill transparency", f.opacity, (op) => this.edit("Fill transparency", (o) => { o.fill = { ...o.fill, opacity: op }; }))));
    return section("Fill", kids);
  },
  strokeSection(it) {
    const st = it.stroke;
    const kids = [];
    if (it.type !== "line") kids.push(selectField("Line", st ? "solid" : "none", [["none", "No line"], ["solid", "Line"]], (v) =>
      this.edit(v === "none" ? "Remove line" : "Add line", (o) => { o.stroke = v === "none" ? null : { color: "#000000", width: this.app.prefs.stroke_width || 1, dash: "solid", cap: "round", join: "round", opacity: 1 }; })));
    if (st) {
      const set = (label, key, conv = (v) => v) => (v) => this.edit(label, (o) => { o.stroke = { ...o.stroke, [key]: conv(v) }; });
      kids.push(row(colorField("Line colour", st.color || "#000000", set("Line colour", "color")),
        numField("Line width", st.width ?? 1, "pt", set("Line width", "width", (v) => Math.max(v, 0)), { min: 0, step: 0.25 })));
      kids.push(selectField("Dash", typeof st.dash === "string" ? st.dash : "solid", DASHES, set("Dash", "dash")));
      kids.push(row(selectField("Ends", st.cap || "flat", [["round", "Round"], ["flat", "Flat"], ["square", "Square"]], set("Line ends", "cap")),
        selectField("Corners", st.join || "round", [["round", "Round"], ["miter", "Sharp"], ["bevel", "Bevelled"]], set("Corners", "join"))));
      kids.push(transparencyField("Line transparency", st.opacity, (op) => this.edit("Line transparency", (o) => { o.stroke = { ...o.stroke, opacity: op }; })));
    }
    return section("Line", kids);
  },
  // A contour in a second colour around the whole arrow or shape (lines, heads and fill)
  outlineSection(it) {
    const o = it.outline;
    const kids = [checkField("Outline around it", !!o, (on) => this.edit(on ? "Add outline" : "Remove outline", (x) => {
      x.outline = on ? { color: contrastingOutline(x), width: 1, opacity: 1 } : null;
    }))];
    if (o) {
      const set = (label, key) => (v) => this.edit(label, (x) => { x.outline = { ...x.outline, [key]: v }; });
      kids.push(row(colorField("Outline colour", o.color, set("Outline colour", "color")),
        numField("Outline thickness", o.width ?? 1, "pt", (v) => set("Outline thickness", "width")(Math.max(v, 0.05)), { min: 0.05, step: 0.25 })));
      kids.push(transparencyField("Outline transparency", o.opacity, (op) => set("Outline transparency", "opacity")(op)));
    }
    kids.push(h("p", { class: "hint" }, "A band of another colour around everything it draws, e.g. a white edge that keeps a black arrow visible on a photo."));
    return section("Outline", kids);
  },
  endsSection(it) {
    const end = (key, label) => {
      const spec = it[key];
      const out = [row(selectField(label, spec?.type || "none", HEADS, (v) => this.edit("Arrowhead", (o) => {
        o[key] = v === "none" ? null : { ...(o[key] || {}), type: v, w: o[key]?.w || "med", len: o[key]?.len || "med" };
      })), selectField(`${label} size`, spec?.w || "med", SIZES, (v) => this.edit("Arrowhead size", (o) => {
        if (o[key]) o[key] = { ...o[key], w: v, len: v };
      }), { disabled: !spec }))];
      if (spec && ROUNDED_HEADS.includes(spec.type)) {
        out.push(numField(`${label} rounding`, (spec.rounding || 0) * 100, "%", (v) => this.edit("Arrowhead rounding", (o) => {
          if (!o[key]) return;
          o[key] = { ...o[key], rounding: Math.min(Math.max(v, 0), 100) / 100 };
          if (!o[key].rounding) delete o[key].rounding;
        }), { min: 0, max: 100, step: 5 }));
      }
      return out;
    };
    const rounded = [it.arrow_start, it.arrow_end].some((s) => s && ROUNDED_HEADS.includes(s.type));
    return section("Arrowheads", [...end("arrow_start", "Start"), ...end("arrow_end", "End"),
      button("Swap start and end arrowheads", () => this.edit("Swap arrowheads", (o) => { [o.arrow_start, o.arrow_end] = [o.arrow_end, o.arrow_start]; }), "Swap ends"),
      rounded ? h("p", { class: "hint" }, "Rounding: 0% is a sharp point; 100% is fully rounded. The rounded tip still ends on the line's end point.") : null]);
  },
  textSection(it) {
    const body = it.text || { paragraphs: [{ runs: [] }] };
    const first = body.paragraphs[0]?.runs?.[0] || {};
    const allRuns = (o) => o.text.paragraphs.flatMap((p) => p.runs || []);
    const setRuns = (label, fn) => this.edit(label, (o) => { if (o.text) allRuns(o).forEach(fn); });
    const fontList = h("datalist", { id: "font-list" }, ...(this.app.fonts || []).map((f) => h("option", { value: f })));
    const align = body.paragraphs[0]?.align || "l";
    return section("Text", [
      button("Edit text", () => canvas.startEdit(it.id), "Edit text…"),
      fontList,
      textField("Font", first.font || "Helvetica", (v) => setRuns("Font", (r) => { r.font = v; }), { list: "font-list" }),
      row(numField("Size", first.size || 6, "pt", (v) => setRuns("Text size", (r) => { r.size = Math.max(v, 0.5); }), { min: 0.5, step: 0.5 }),
        colorField("Text colour", first.color || "#000000", (v) => setRuns("Text colour", (r) => { r.color = v; }))),
      h("div", { class: "button-row" },
        toggle("Bold", !!first.bold, (on) => setRuns("Bold", (r) => { r.bold = on; }), "B", "bold"),
        toggle("Italic", !!first.italic, (on) => setRuns("Italic", (r) => { r.italic = on; }), "I", "italic"),
        toggle("Underline", !!first.underline, (on) => setRuns("Underline", (r) => { r.underline = on; }), "U", "underline")),
      radioField("Align", align, [["l", "Left"], ["ctr", "Centre"], ["r", "Right"]],
        (v) => this.edit("Align text", (o) => { o.text.paragraphs.forEach((p) => { p.align = v; }); })),
      radioField("Vertical position", body.anchor || "t", [["t", "Top"], ["ctr", "Middle"], ["b", "Bottom"]],
        (v) => this.edit("Text position", (o) => { o.text.anchor = v; })),
      checkField("Wrap text in the box", body.wrap !== false, (on) => this.edit("Wrap", (o) => { o.text.wrap = on; })),
      checkField("Resize the box to fit the text", body.autofit === "shape", (on) => this.edit("Autofit", (o) => { o.text.autofit = on ? "shape" : "none"; })),
    ]);
  },

  // Several items ------------------------------------------------------------------------

  multiSections(sel) {
    const a = (cmd, label, icon) => button(label, () => this.app.run(cmd), icon);
    return [section(`${sel.length} objects selected`, [
      h("p", { class: "hint" }, sel.map((it) => itemLabel(it, store.doc)).slice(0, 6).join(", ") + (sel.length > 6 ? "…" : "")),
      h("div", { class: "button-row" }, a("alignLeft", "Align left edges", "⇤"), a("alignCenter", "Align centres", "↔"),
        a("alignRight", "Align right edges", "⇥")),
      h("div", { class: "button-row" }, a("alignTop", "Align top edges", "⤒"), a("alignMiddle", "Align middles", "↕"),
        a("alignBottom", "Align bottom edges", "⤓")),
      h("div", { class: "button-row" }, a("distributeH", "Distribute horizontally", "Space across"),
        a("distributeV", "Distribute vertically", "Space down")),
      h("div", { class: "button-row" }, a("group", "Group", "Group"), a("delete", "Delete", "Delete")),
    ])];
  },
};

// Field builders ---------------------------------------------------------------------------

const MM_PT = 72 / 25.4;

// Which standard or journal size a page is, if it still has that size
export function pagePreset(page, info) {
  const near = (a, b) => Math.abs(a - b) < 0.05;
  const p = page.preset || {};
  const journal = (info.journals || []).find((j) => j.name === p.journal);
  const type = journal?.types.find((t) => t.name === p.type && near(t.width_mm * MM_PT, page.width)) || null;
  if (journal && type) return { journal, type, standard: null };
  const standard = (info.standard_sizes || []).find((s) => near(s.width_mm * MM_PT, page.width)
    && near(s.height_mm * MM_PT, page.height)) || null;
  return { journal: null, type: null, standard };
}

function digits(u) { return u === "in" || u === "cm" ? 3 : 2; }
function kindName(it) {
  if (it.type === "picture") return "Picture";
  if (it.type === "line") return `${isCurved(it) ? "Curved " : ""}${it.arrow_start || it.arrow_end ? "arrow" : "line"}`.replace(/^./, (c) => c.toUpperCase());
  if (it.type === "group") return "Group";
  if (it.textbox) return "Text box";
  return shapeName(it.geom);
}
function section(title, children) {
  const id = `sec-${++fieldId}`;
  return h("fieldset", { class: "section", "aria-labelledby": id }, h("legend", { id }, title), ...children);
}
function row(...children) { return h("div", { class: "row" }, ...children); }
function label(text, id) { return h("label", { for: id }, text); }

export function numField(text, valuePt, unit, onCommit, opts = {}) {
  const id = `f${++fieldId}`;
  const isLen = unit in { pt: 1, mm: 1, cm: 1, in: 1, px: 1 };
  const shown = isLen ? toUnit(valuePt, unit) : valuePt;
  const input = h("input", { id, type: "number", inputmode: "decimal", value: fmt(shown, isLen ? digits(unit) : 2),
    step: opts.step ?? (isLen ? { in: 0.01, pt: 0.5, cm: 0.1, mm: 0.5, px: 1 }[unit] : 1), min: opts.min, max: opts.max,
    "data-bind": opts.bind, "aria-describedby": `${id}-u` });
  input.addEventListener("change", () => {
    const v = parseFloat(input.value);
    if (Number.isNaN(v)) return;
    onCommit(isLen ? fromUnit(v, unit) : v);
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); e.stopPropagation(); });
  const unitText = { deg: "°", "%": "%" }[unit] || UNIT_LABEL[unit] || unit;
  return h("div", { class: "field" }, label(text, id),
    h("div", { class: "with-unit" }, input, h("span", { class: "unit", id: `${id}-u`, "aria-label": unitName(unit) }, unitText)));
}
function unitName(u) {
  return { pt: "points", mm: "millimetres", cm: "centimetres", in: "inches", px: "pixels", deg: "degrees", "%": "percent" }[u] || u;
}
export function textField(text, value, onCommit, opts = {}) {
  const id = `f${++fieldId}`;
  const input = h("input", { id, type: "text", value: value ?? "", list: opts.list });
  input.addEventListener("change", () => onCommit(input.value.trim()));
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); e.stopPropagation(); });
  return h("div", { class: "field" }, label(text, id), input);
}
function textArea(text, value, onCommit) {
  const id = `f${++fieldId}`;
  const ta = h("textarea", { id, rows: 2 }, value || "");
  ta.addEventListener("change", () => onCommit(ta.value.trim()));
  ta.addEventListener("keydown", (e) => e.stopPropagation());
  return h("div", { class: "field" }, label(text, id), ta);
}
// A dropdown with its options in labelled groups: [[group title, [[value, label], ...]], ...]
function groupedSelectField(text, value, groups, onChange) {
  const id = `f${++fieldId}`;
  const sel = h("select", { id }, ...groups.map(([title, options]) => h("optgroup", { label: title },
    ...options.map(([v, l]) => h("option", { value: v, selected: v === value ? "selected" : undefined }, l)))));
  sel.value = value;
  sel.addEventListener("change", () => onChange(sel.value));
  return h("div", { class: "field" }, label(text, id), sel);
}
export function selectField(text, value, options, onChange, opts = {}) {
  const id = `f${++fieldId}`;
  const sel = h("select", { id, disabled: opts.disabled },
    ...options.map(([v, l]) => h("option", { value: v, selected: v === value ? "selected" : undefined }, l)));
  sel.value = value;
  sel.addEventListener("change", () => onChange(sel.value));
  return h("div", { class: "field" }, label(text, id), sel);
}
// A colour picker with its hex code beside it; either can be edited
function colorField(text, value, onChange) {
  const id = `f${++fieldId}`;
  const hex = parseHex(value) || "#000000";
  const picker = h("input", { id, type: "color", value: hex });
  const code = h("input", { id: `${id}-hex`, type: "text", class: "hex", value: hex.toUpperCase(), maxlength: 7,
    spellcheck: "false", autocomplete: "off", "aria-label": `${text} hex code` });
  picker.addEventListener("change", () => { code.value = picker.value.toUpperCase(); onChange(picker.value); });
  const commit = () => {
    const v = parseHex(code.value);
    if (!v) {
      announce(`“${code.value}” isn't a hex colour; use 6 digits such as #1A2B3C`);
      code.value = picker.value.toUpperCase();
      return;
    }
    code.value = v.toUpperCase();
    if (v !== picker.value) { picker.value = v; onChange(v); }
  };
  code.addEventListener("change", commit);
  code.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { commit(); code.blur(); }
    e.stopPropagation();
  });
  return h("div", { class: "field color" }, label(text, id), h("div", { class: "color-row" }, picker, code));
}
// "#1a2b3c", "1A2B3C" or "#abc" -> "#1a2b3c"; anything else -> null
export function parseHex(s) {
  let c = String(s || "").trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(c)) c = [...c].map((x) => x + x).join("");
  return /^[0-9a-f]{6}$/i.test(c) ? `#${c.toLowerCase()}` : null;
}
// Transparency in percent (0 = solid), as PowerPoint shows it; items store opacity
function transparencyField(text, opacity, onCommit) {
  return numField(text, (1 - (opacity ?? 1)) * 100, "%", (v) => onCommit(Math.min(Math.max(1 - v / 100, 0), 1)),
    { min: 0, max: 100, step: 5 });
}
// White around dark things, black around light ones
function contrastingOutline(it) {
  const main = parseHex(it.type === "line" ? it.stroke?.color : (it.fill?.color || it.stroke?.color)) || "#000000";
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(main.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 ? "#000000" : "#ffffff";
}
function checkField(text, checked, onChange) {
  const id = `f${++fieldId}`;
  const input = h("input", { id, type: "checkbox", checked });
  input.addEventListener("change", () => onChange(input.checked));
  return h("div", { class: "field check" }, input, label(text, id));
}
function radioField(text, value, options, onChange) {
  const name = `r${++fieldId}`;
  return h("fieldset", { class: "radio-group" }, h("legend", {}, text),
    ...options.map(([v, l]) => {
      const id = `${name}-${v}`;
      const input = h("input", { type: "radio", name, id, value: v, checked: v === value });
      input.addEventListener("change", () => { if (input.checked) onChange(v); });
      return h("label", { for: id, class: "radio" }, input, h("span", {}, l));
    }));
}
export function button(labelText, onClick, content, cls = "") {
  return h("button", { type: "button", class: `btn ${cls}`, title: labelText, "aria-label": labelText, onclick: onClick }, content ?? labelText);
}
function toggle(labelText, pressed, onChange, content, cls = "") {
  const b = h("button", { type: "button", class: `btn toggle ${cls}`, title: labelText, "aria-label": labelText,
    "aria-pressed": pressed ? "true" : "false" }, content);
  b.addEventListener("click", () => {
    const on = b.getAttribute("aria-pressed") !== "true";
    onChange(on);
    announce(`${labelText} ${on ? "on" : "off"}`);
  });
  return b;
}

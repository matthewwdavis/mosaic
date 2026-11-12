// The properties panel: what's selected and every setting it has. All controls are real,
// labelled form fields grouped in fieldsets, so they work with the keyboard and screen readers.

import { rpc } from "./api.js";
import { SUBSCRIPT, SUPERSCRIPT, angleOf, canvas, findDeep, lineAngle, pageGuides, scaleItem, shiftItem } from "./canvas.js";
import { icon } from "./panels.js";
import { contextMenu } from "./contextmenu.js";
import { store } from "./store.js";
import { linked, swatchById } from "./swatches.js";
import { applyToParagraph, differs } from "./textstyles.js";
import { UNITS, anchorFor, convert, niceLength, pxPerPt, scaleText } from "./scalebar.js";
import { DEFAULT_GAP } from "./gridlayout.js";
import { copiesOf, scaleOf, symbolOf } from "./symbols.js";
import { differs as looksDiffer, takes } from "./objectstyles.js";
import { CORNER_NAMES, asLabel, pageLabels, restyleLabels } from "./labels.js";
import { capPicture, dashPicture, fillPicture, headPicture, joinPicture, linePicture, outlinePicture, pathPicture, reachPicture,
  routePicture, shapePicture, stylePicture, zoomShapePicture } from "./pictures.js";
import { ZOOM_SHAPES, zoomShape } from "./zoom.js";
import { hiddenOf, liftedFrom } from "./liftedtext.js";
import { cropToSize, drawnShapePicture, resetCrop } from "./crop.js";
import { BRACKET_LABELS, across, keepBar } from "./brackets.js";
import {
  UNIT_LABEL, announce, fmt, fromUnit, h, isCurved, isMac, itemLabel, itemsBBox, keepFieldKeys, lengthText, lineSamples, luminance,
  parseHex, shapeCatalog, shapeName, toUnit,
} from "./util.js";

const DASHES = [["solid", "Solid"], ["sysDot", "Round dot"], ["sysDash", "Short dash"], ["dash", "Dash"],
  ["dashDot", "Dash dot"], ["lgDash", "Long dash"], ["lgDashDot", "Long dash dot"], ["lgDashDotDot", "Long dash dot dot"],
  ["dot", "Dot"]];
const HEADS = [["none", "None"], ["triangle", "Triangle"], ["stealth", "Stealth"], ["arrow", "Open arrow"],
  ["oval", "Circle"], ["diamond", "Diamond"], ["bar", "Bar (inhibition)"], ["half", "Half arrow"], ["open_circle", "Open circle"],
  ["open_triangle", "Open triangle"]];
const SIZES = [["xs", "Extra small"], ["sm", "Small"], ["med", "Medium"], ["lg", "Large"], ["xl", "Extra large"]];
const KIND_NAMES = { photo: "a photo", combination: "a photo with text or lines", line_art: "line art" };   // picturekind.py
// Symbols for the Text tab, with names for screen readers
const SYMBOLS = [["µ", "micro"], ["°", "degree"], ["±", "plus or minus"], ["×", "times"], ["÷", "divided by"], ["−", "minus"],
  ["≤", "less than or equal to"], ["≥", "greater than or equal to"], ["≈", "approximately"], ["≠", "not equal to"], ["∞", "infinity"],
  ["→", "right arrow"], ["←", "left arrow"], ["↑", "up arrow"], ["↓", "down arrow"], ["⇌", "equilibrium"], ["‰", "per mille"],
  ["′", "prime"], ["″", "double prime"], ["Å", "ångström"], ["·", "middle dot"], ["†", "dagger"], ["‡", "double dagger"], ["§", "section"]];
const GREEK = [..."αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ"].map((ch) => [ch, `Greek ${ch.toLowerCase() === ch ? "small" : "capital"} letter`]);
const DEFAULT_RUN = { font: "Helvetica", size: 6, bold: false, italic: false, color: "#000000", kern: true };
const ROUNDED_HEADS = ["triangle", "stealth", "arrow", "diamond", "open_triangle"];   // heads whose corners can be rounded
// What decides which outline choices look different on an object: its fill, its line, and
// whether that line goes all the way round an area (presets.encloses; a freeform's closed line)
function outlineKind(it) {
  const st = it.stroke, lined = !!st && (st.width ?? 1) > 0;
  const encloses = it.type === "shape" && (it.geom === "custom"
    ? (it.path?.subpaths || []).some((s) => s.stroke !== false && (s.cmds || []).some((c) => c[0] === "Z"))
    : !!shapeCatalog.shapes[it.geom]?.closed);
  return { filled: it.type === "shape" && !!it.fill, lined, dashed: lined && !!st.dash && st.dash !== "solid", encloses };
}
// The outline's Sides choices on this object: inside and outside of what has an inside, else the
// line's left and right as it goes from its start to its end (a line, an arc, an open curve)
function outlineSides(k) {
  if (k.filled || k.encloses) return [["outside", "Outside"], ["inside", "Inside"], ["both", "Both sides"]];
  return [["left", "Left side"], ["right", "Right side"], ["both", "Both sides"]];
}
const OUTLINE_GAPS = [["filled", "Filled"], ["empty", "Empty"]];
// An outline type as the Sides and Gaps it looks like on this object (resolve.with_outline).
// The first types, drawn underneath, show on both sides of a line with no fill to hide one
function outlineLook(type, k) {
  let t = type || "outside";
  if (/^(left|right)/.test(t)) return { sides: t.startsWith("left") ? "left" : "right", gaps: t.endsWith("_gaps") ? "empty" : "filled" };
  if (!k.filled && !k.encloses && /^(inside|outside_only)/.test(t)) t = t.endsWith("_gaps") ? "both" : "both_filled";
  let sides = t.startsWith("inside") ? "inside" : t.startsWith("both") ? "both" : "outside";
  let gaps = ["outside", "outside_only", "inside", "both_filled"].includes(t) ? "filled" : "empty";
  if (!k.filled && (t === "outside" || t === "outside_gaps")) [sides, gaps] = ["both", "empty"];
  return { sides, gaps };
}
// The type that keeps to the chosen Sides and Gaps, whatever the fill becomes later
function outlineType(sides, gaps) {
  if (sides === "left" || sides === "right") return gaps === "empty" ? `${sides}_gaps` : sides;
  if (sides === "inside") return gaps === "empty" ? "inside_gaps" : "inside";
  if (sides === "both") return gaps === "empty" ? "both" : "both_filled";
  return gaps === "empty" ? "outside_only_gaps" : "outside_only";
}
// Where a radial gradient starts: its centre as fractions of the shape's box
const CENTRES = [["middle", [0.5, 0.5], "The middle"], ["tl", [0, 0], "Top left corner"], ["tr", [1, 0], "Top right corner"],
  ["bl", [0, 1], "Bottom left corner"], ["br", [1, 1], "Bottom right corner"]];

// The gradient's colours along a bar, over a checkerboard so transparency shows
function gradientBar(g) {
  const css = (st) => {
    const c = parseHex(st.color) || "#000000";
    const [r, gg, b] = [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
    return `rgba(${r}, ${gg}, ${b}, ${st.opacity ?? 1}) ${fmt(st.pos * 100, 2)}%`;
  };
  return h("div", { class: "grad-bar", "aria-hidden": "true", style: {
    backgroundImage: `linear-gradient(90deg, ${g.stops.map(css).join(", ")}), repeating-conic-gradient(#c8c8c8 0 25%, #ffffff 0 50%)`,
    backgroundSize: "auto, 8px 8px" } });
}
// A new stop halfway across the widest gap between stops, its colour and transparency between theirs
function addGradientStop(gr) {
  let at = 0;
  for (let i = 1; i < gr.stops.length; i++) if (gr.stops[i].pos - gr.stops[i - 1].pos > gr.stops[at + 1].pos - gr.stops[at].pos) at = i - 1;
  const [a, b] = [gr.stops[at], gr.stops[at + 1]];
  const mix = (x, y) => Math.round((parseInt(x, 16) + parseInt(y, 16)) / 2).toString(16).padStart(2, "0");
  const [ca, cb] = [parseHex(a.color) || "#000000", parseHex(b.color) || "#ffffff"];
  const color = `#${[1, 3, 5].map((i) => mix(ca.slice(i, i + 2), cb.slice(i, i + 2))).join("")}`;
  gr.stops.splice(at + 1, 0, { pos: (a.pos + b.pos) / 2, color, opacity: ((a.opacity ?? 1) + (b.opacity ?? 1)) / 2 });
}
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
    document.addEventListener("fa-areas", () => this.schedule());   // (an area fill's area lost or found again)
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
    let parts;
    if (sel.length === 0) parts = this.pageSections();
    else if (sel.length === 1) parts = this.tabbed(kindKey(sel[0]), kindName(sel[0]), this.itemTabs(sel[0]), this.sizeStrip(sel[0]));
    else parts = this.tabbed("multi", `${sel.length} objects`, this.multiTabs(sel), this.multiStrip(sel));
    this.root.replaceChildren(...parts.filter(Boolean));
  },
  // Tabs (Arrange, Style, Text...) over folding sections, like PowerPoint's Format pane; the tab
  // last used for each kind of object opens next time. Above the tabs (strip), kept in view as
  // the panel scrolls: the object's position and size
  tabbed(kind, title, tabs, strip = null) {
    const remembered = (this.app.prefs.inspector_tabs || {})[kind] || DEFAULT_TAB[kind];
    let active = tabs.some(([key]) => key === remembered) ? remembered : tabs[0][0];
    const list = h("div", { class: "insp-tabs", role: "tablist", "aria-label": `${title}: properties` });
    const entries = tabs.map(([key, label, sections]) => {
      const tab = h("button", { type: "button", role: "tab", class: "insp-tab", id: `itab-${key}`, "aria-controls": `ipanel-${key}` }, label);
      const panel = h("div", { class: "insp-panel", role: "tabpanel", id: `ipanel-${key}`, "aria-labelledby": `itab-${key}` },
        ...sections.filter(Boolean));
      tab.addEventListener("click", () => { show(key); this.app.rememberUi({ inspector_tabs: { ...(this.app.prefs.inspector_tabs || {}), [kind]: key } }); });
      list.append(tab);
      return { key, tab, panel };
    });
    const show = (key) => {
      active = key;
      for (const e of entries) {
        e.tab.setAttribute("aria-selected", e.key === key ? "true" : "false");
        e.tab.tabIndex = e.key === key ? 0 : -1;
        e.panel.hidden = e.key !== key;
      }
    };
    list.addEventListener("keydown", (e) => {
      const i = entries.findIndex((x) => x.key === active);
      const j = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: entries.length - 1 }[e.key];
      if (j === undefined) return;
      e.preventDefault();
      e.stopPropagation();
      entries[(j + entries.length) % entries.length].tab.click();
      entries.find((x) => x.key === active).tab.focus();
    });
    show(active);
    const head = strip || entries.length > 1 ? h("div", { class: "insp-head" }, strip, entries.length > 1 ? list : null) : null;
    return [h("p", { class: "insp-kind" }, title), head, ...entries.map((e) => e.panel)];
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
    if (key === "angle") return fmt(lineAngle(it), 2);
    if (it.frame && "xywh".includes(key)) return fmt(toUnit(it.frame["xywh".indexOf(key)], u), digits(u));
    if (it.type === "group" && "xywh".includes(key)) {
      const b = itemsBBox(it.items);
      return fmt(toUnit([b[0], b[1], b[2] - b[0], b[3] - b[1]]["xywh".indexOf(key)], u), digits(u));
    }
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

  // A page length given in millimetres, in the units page sizes are shown in ("210 mm")
  pageLength(mm) {
    const pu = this.pageUnits();
    return `${fmt(toUnit(mm * MM_PT, pu), 1)} ${UNIT_LABEL[pu]}`;
  },
  // The current page as a standard size, or as a journal's figure type (a journal on its own: its
  // widest type, which most multi-panel figures need); from the Page panel and the Size menu
  setStandardSize(name) {
    const s = (this.app.info.standard_sizes || []).find((x) => x.name === name);
    if (!s) return;
    this.editPage(`${name} page`, (p) => { p.width = s.width_mm * MM_PT; p.height = s.height_mm * MM_PT; p.preset = { standard: name }; });
    canvas.fit();
    announce(`Page is now ${name}, ${this.pageLength(s.width_mm)} by ${this.pageLength(s.height_mm)}`);
  },
  setJournalSize(jname, tname) {
    const j = (this.app.info.journals || []).find((x) => x.name === jname);
    if (!j) { this.editPage("No journal size", (p) => { delete p.preset; }); return; }
    const t = j.types.find((x) => x.name === tname) || j.types.reduce((a, b) => (b.width_mm > a.width_mm ? b : a));
    let restyled = 0;
    this.editPage(`${j.name} ${t.name.toLowerCase()} page`, (p) => {
      // The page's panel labels take the journal's look (labels.js), in the same undo step
      const was = pageLabels(p, this.app.info.journals);
      p.width = t.width_mm * MM_PT;
      p.height = j.depth_mm * MM_PT;
      p.preset = { journal: j.name, type: t.name };
      if (j.labels) restyled = restyleLabels(p.items, was, j.labels);
    });
    canvas.fit();
    announce(`Page is now a ${j.name} ${t.name.toLowerCase()} figure, ${this.pageLength(t.width_mm)} wide and ${this.pageLength(j.depth_mm)} deep`
      + (restyled ? `; ${restyled} panel label${restyled === 1 ? "" : "s"} in ${j.name}'s style` : ""));
  },
  setPageWidth(v) { this.editPage("Page width", (p) => { p.width = Math.max(v, 1); delete p.preset; }); },
  setPageHeight(v) {
    this.editPage("Page height", (p) => {
      p.height = Math.max(v, 1);
      if (p.preset?.standard) delete p.preset;   // a journal figure may be shorter than the full depth
    });
  },
  swapPage() { this.editPage("Rotate page", (p) => { [p.width, p.height] = [p.height, p.width]; delete p.preset; }); },

  pageSections() {
    const page = store.page();
    const pu = this.pageUnits();
    const { standard, journal, type } = pagePreset(page, this.app.info);
    const journals = this.app.info.journals || [];
    const len = (mm) => this.pageLength(mm);
    return [
      section("Page", [
        textField("Name", page.name, (v) => this.editPage("Rename page", (p) => { p.name = v || p.name; })),
        selectField("Standard size", standard ? standard.name : "",
          [["", journal ? "—" : "Custom size"], ...standardOptions(this.app.info.standard_sizes, len)],
          (v) => this.setStandardSize(v)),
        selectField("Journal", journal ? journal.name : "", [["", "None"], ...journals.map((j) => [j.name, j.name])],
          (v) => this.setJournalSize(v)),
        selectField("Figure type", type ? type.name : "",
          journal ? journal.types.map((t) => [t.name, `${t.name} — ${len(t.width_mm)} wide`]) : [["", "Choose a journal first"]],
          (v) => this.setJournalSize(journal.name, v), { disabled: !journal }),
        journal ? h("p", { class: "hint" }, `${journal.name}: ${journal.note} Source: ${journal.source}.`) : null,
        journal ? this.journalRules(journal) : null,
        row(numField("Width", page.width, pu, (v) => this.setPageWidth(v), { min: 1 }),
          numField("Height", page.height, pu, (v) => this.setPageHeight(v), { min: 1 })),
        h("div", { class: "button-row" },
          button("Swap width and height", () => this.swapPage(), "⟲"),
          button(journal ? "Fit the page height to the content (keeps the column width)" : "Fit page to content",
            () => this.app.run("fitPage"), "Fit to content")),
        radioField("Background", page.background ? "white" : "none", [["none", "Transparent"], ["white", "White"]],
          (v) => this.editPage("Background", (p) => { p.background = v === "white" ? "#ffffff" : null; })),
      ]),
      this.guidesSection(),
      section("Document", [
        textField("Title", store.doc.meta?.title || "", (v) => store.update("Rename document", (d) => { d.meta.title = v; })),
        h("p", { class: "hint" }, `${store.doc.pages.length} page${store.doc.pages.length === 1 ? "" : "s"} · `
          + `${Object.keys(store.doc.assets).length} placed file${Object.keys(store.doc.assets).length === 1 ? "" : "s"}`),
      ]),
      h("p", { class: "hint" }, "Drop figure files (PDF, SVG, PNG, JPEG, TIFF) onto the page to place them at true size. "
        + "Hold Option (Alt) while dropping to store a copy without linking to the file."),
    ];
  },

  // This page's guides, to add, place exactly and remove without a pointer
  guidesSection() {
    const page = store.page(), u = this.units();
    const g = { x: page.guides?.x || [], y: page.guides?.y || [] };
    // Listed in order of position; each keeps its place in the page's list for editing
    const sorted = (axis) => g[axis].map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
    const rows = (axis, name) => sorted(axis).map(({ v, i }, n) => h("div", { class: "guide-row" },
      numField(`${name} ${n + 1}`, v, u, (nv) => this.editPage("Move guide", (p) => { pageGuides(p)[axis][i] = nv; })),
      button(`Remove ${name.toLowerCase()} ${n + 1}`, () => this.editPage("Remove guide", (p) => { pageGuides(p)[axis].splice(i, 1); }),
        "Remove", "small")));
    // A new guide goes through the middle of the page, ready for its position to be typed
    const add = (axis, name) => () => {
      this.editPage("Add guide", (p) => { pageGuides(p)[axis].push(axis === "x" ? p.width / 2 : p.height / 2); });
      const list = store.page().guides[axis];
      const n = list.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v).findIndex((o) => o.i === list.length - 1) + 1;
      this.render();
      const l = [...this.root.querySelectorAll("label")].find((x) => x.textContent === `${name} ${n}`);
      const input = l && document.getElementById(l.htmlFor);
      if (input) { input.focus(); input.select(); }
      announce(`Added ${name.toLowerCase()} ${n} through the middle of the page; type its position`);
    };
    const total = g.x.length + g.y.length;
    const hidden = this.app.prefs.show_guides === false;
    return section("Guides", [
      g.x.length ? h("p", { class: "hint" }, "Vertical guides, from the left edge of the page:") : null,
      ...rows("x", "Vertical guide"),
      g.y.length ? h("p", { class: "hint" }, "Horizontal guides, from the top edge:") : null,
      ...rows("y", "Horizontal guide"),
      h("div", { class: "button-row" },
        button("Add a vertical guide down the middle of the page", add("x", "Vertical guide"), "Add vertical"),
        button("Add a horizontal guide across the middle of the page", add("y", "Horizontal guide"), "Add horizontal"),
        total ? button("Remove every guide from this page", () => canvas.removeAllGuides(), "Remove all") : null),
      h("p", { class: "hint" }, hidden
        ? `Guides are hidden (${this.app.commands.toggleGuides.keys} shows them), and hidden guides don't snap.`
        : "Or click a ruler to put a guide at that spot, or drag one out onto the page. To remove one, right-click it "
          + "(or its mark on the ruler), or drag it back onto the ruler."),
    ]);
  },

  // One item -----------------------------------------------------------------------------

  // [key, tab name, sections] for one object
  itemTabs(it) {
    const arrange = ["arrange", "Arrange", [this.objectSection(it), this.arrangeSection(it), ...this.alignSections(1)]];
    if (it.lifted && liftedFrom(it)) arrange[2].splice(1, 0, this.liftedSection(it));
    if (it.type === "picture" && it.equation) return [arrange, ["picture", "Equation", [this.equationSection(it), this.borderSection(it)]]];
    if (it.type === "picture") {
      return [arrange, ["picture", "Picture", [this.pictureSection(it), this.plotTextSection(it), this.borderSection(it),
        it.inset ? this.insetSection(it) : null, this.scaleSection(it)]]];
    }
    if (it.type === "scalebar") return [["arrange", "Arrange", [this.objectSection(it), ...this.alignSections(1)]],
      ["scalebar", "Scale bar", [this.scalebarSection(it)]]];
    if (it.type === "bracket") return [arrange, ["bracket", "Bracket", [this.bracketSection(it)]]];
    if (it.type === "symbol") {
      arrange[2].push(this.symbolSection(it));
      return [arrange];
    }
    if (it.type === "line") {
      arrange[2].splice(2, 0, this.linkSection(it));
      return [arrange, ["style", "Style", [this.objectStyleSection(it), this.strokeSection(it), this.endsSection(it), this.outlineSection(it)]]];
    }
    if (it.geom === "region") {
      // Its shape comes from its lines and shapes: no position or size of its own to type
      const n = it.region?.items?.length || 0;
      // (its lines no longer enclose an area: said on both tabs, as it opens on Style)
      const lost = () => (canvas.areaLost(it.id) ? h("p", { class: "hint warn area-lost-note" }, `Its ${n} line${n === 1 ? "" : "s"} `
        + `and shape${n === 1 ? "" : "s"} don't enclose an area any more, so there's nothing to fill: the dashed outline is where it `
        + "was. Join the gap again (an end within 3.5 pt of a line closes it) and the fill comes back; Undo also brings it back.") : null);
      const fillArrange = ["arrange", "Arrange", [this.objectSection(it), section("Area fill", [lost(),
        h("p", { class: "hint" }, `It fills the space ${n} line${n === 1 ? "" : "s"} and shape${n === 1 ? "" : "s"} enclose, and follows them `
          + "when they move or change shape. Dragging it moves them all."),
        button("Make it an ordinary shape that stays put when the lines move", () => this.app.detachArea(), "Make an ordinary shape")])]];
      return [fillArrange, ["style", "Style", [lost(), this.objectStyleSection(it), this.fillSection(it), this.outlineSection(it)]]];
    }
    if (it.type === "group" && it.clip) {
      arrange[2].push(section("Clipping mask", [
        h("p", { class: "hint" }, `Its top shape clips the ${it.items.length - 1} object${it.items.length === 2 ? "" : "s"} under it. `
          + "Double-click it (or press Enter) to move them within the shape, or to change the shape."),
        button("Release the clipping mask: separate the shape and what it clips", () => this.app.run("releaseClipMask"), "Release")]));
      return [arrange, this.lookTab([it])].filter(Boolean);
    }
    if (it.type === "group" && it.grid) {
      arrange[2].push(this.gridSection(it));
      return [arrange, this.lookTab([it])].filter(Boolean);
    }
    if (it.type === "group") {
      arrange[2].push(section("Group", [
        h("p", { class: "hint" }, `${it.items.length} objects. Double-click it to edit them inside it, or Ungroup `
          + `(${this.app.mod}Shift+G) to separate them.`),
        button("Ungroup", () => this.app.run("ungroup"), "Ungroup")]));
      return [arrange, this.lookTab([it])].filter(Boolean);
    }
    if (it.zoom) arrange[2].push(this.zoomBoxSection(it));
    if (it.textbox) arrange[2].splice(2, 0, this.labelSection(it));
    const boxed = !it.textbox || it.fill || it.stroke;
    const style = ["style", "Style", [
      this.objectStyleSection(it),
      it.textbox ? null : this.geometrySection(it),
      boxed ? this.fillSection(it) : null,
      this.strokeSection(it),
      (shapeCatalog.shapes[it.geom]?.open || it.geom === "custom") && it.stroke ? this.endsSection(it) : null,
      boxed ? this.outlineSection(it) : null]];
    const text = it.text || it.textbox ? ["text", "Text", [this.textSection(it)]] : null;
    return [arrange, style, text].filter(Boolean);
  },
  // Where a line's ends are attached, and a way to let go
  linkSection(it) {
    const row = (key, name) => {
      const link = it[key];
      return h("div", { class: "link-row" },
        h("span", {}, `${name}: ${link ? `attached to ${canvas.siteLabel(link)}` : "not attached"}`),
        link ? button(`Detach the ${name.toLowerCase()}`, () => this.edit("Detach", (x) => { delete x[key]; }), "Detach", "small") : null);
    };
    const route = pictureField("Route", it.route === "elbow" ? "elbow" : "straight",
      [["straight", it.points.length > 2 ? "Through its points" : "Straight"], ["elbow", "Elbow: level and upright stretches"]]
        .map(([value, label]) => ({ value, label, picture: () => routePicture(value) })), (v) => this.app.setRoute(v));
    return section("Connections", [row("start_link", "Start"), row("end_link", "End"), route,
      h("p", { class: "hint" }, "Drag an end onto a corner, the middle of a side, or a dash of another object to attach it; "
        + `it then follows that object. Hold ${this.app.mod.replace("+", "")} to drop an end without attaching.`
        + (it.route === "elbow" ? " An elbow leaves and reaches attached objects square to their sides; drag the handle on its "
          + "middle stretch to move that stretch." : ""))]);
  },
  // Its object style (objectstyles.js): which, whether this object differs from it, and making one
  objectStyleSection(it) {
    const styles = store.doc.object_styles || [], st = styles.find((x) => x.id === it.object_style);
    const kids = [pictureField("Object style", st ? st.id : "", [{ value: "", label: "None", picture: () => stylePicture(it, null) },
      ...styles.map((x) => ({ value: x.id, label: x.name, picture: () => stylePicture(it, x) }))], (v) => this.app.useObjectStyle(v))];
    if (st && looksDiffer(it, st)) {
      kids.push(h("p", { class: "hint" }, `This object differs from ${st.name}.`), h("div", { class: "button-row" },
        button(`Put this object back to ${st.name}`, () => this.app.clearObjectChanges(), "Clear changes"),
        button(`Change ${st.name} to look like this object, with the objects using it`,
          () => this.app.redefineObjectStyle(st.id, store.item(it.id)), "Update the style to match")));
    }
    kids.push(h("div", { class: "button-row" }, button("Make a new object style from this object's look", () => this.app.newObjectStyle(),
      "New style from this object…")));
    return section("Object style", kids);
  },
  // An equation (equations.py): its maths, size, font and colour, drawn again when one changes
  equationSection(it) {
    const eq = it.equation, set = (patch) => this.app.updateEquation(it.id, patch);
    const a = store.doc.assets[it.asset], scale = it.frame[2] / Math.max(a.size_pt[0], 1e-9);
    const family = eq.family || "Helvetica";
    return section("Equation", [
      textArea("Maths, written as in LaTeX", eq.tex, (v) => { if (v.trim()) set({ tex: v.trim() }); }),
      row(numField("Text size", eq.size || 6, "pt", (v) => set({ size: Math.max(v, 1) }), { min: 1, step: 0.5 }),
        colorField("Colour", eq.color || "#000000", (v) => set({ color: v }))),
      selectField("Font", eq.font || "figure", [["figure", `${family}, the figure's font`], ["cm", "Computer Modern, as in LaTeX"]],
        (v) => set({ font: v, family: this.app.prefs.text?.font || family })),
      h("p", { class: "hint" }, (Math.abs(scale - 1) > 0.005 ? `Scaled to ${fmt(scale * 100, 1)}%, so its text prints at `
        + `${fmt((eq.size || 6) * scale, 2)} pt. ` : "") + "Drawn by matplotlib as real text: the PDF holds its fonts; an SVG names "
        + "them, so they need to be on the computer that opens it."),
      button("Back to 100%, the text at its own size", () => this.edit("Equation at 100%", (o) => {
        o.frame = [o.frame[0], o.frame[1], a.size_pt[0], a.size_pt[1]];
      }), "100%")]);
  },
  // A symbol's copy: its symbol's name (shared by every copy), its scale, and editing it
  symbolSection(it) {
    const sym = symbolOf(store.doc, it.symbol);
    if (!sym) return section("Symbol", [h("p", {}, "Its symbol is missing.")]);
    const n = copiesOf(store.doc, sym.id).length, [sx, sy] = scaleOf(it, sym);
    const scale = Math.abs(sx - sy) < 1e-6 ? `${fmt(sx * 100, 1)}%` : `${fmt(sx * 100, 1)}% across, ${fmt(sy * 100, 1)}% down`;
    return section("Symbol", [
      textField("Symbol name", sym.name, (v) => { if (v.trim()) this.app.renameSymbol(sym.id, v.trim()); }),
      h("p", { class: "hint" }, `${n} cop${n === 1 ? "y" : "ies"} in this figure, this one at ${scale} of the symbol's size. `
        + "Resizing a copy scales its lines and text with it."),
      h("div", { class: "button-row" },
        button("Edit the symbol where this copy is; every copy changes", () => this.app.run("editSymbol"), "Edit symbol"),
        button("Break the link: make this copy its own objects", () => this.app.run("breakSymbol"), "Break link"),
        button("The figure's symbols", () => this.app.run("symbols"), "Symbols…"))]);
  },
  // A grid layout's columns and gaps (gridlayout.js)
  gridSection(it) {
    const u = this.app.prefs.units || "cm", [gx, gy] = it.grid.gap || [DEFAULT_GAP, DEFAULT_GAP];
    const set = (label, fn) => this.edit(label, (g) => { fn(g.grid); });
    const rows = Math.ceil(it.items.length / Math.max(1, it.grid.cols || 1));
    return section("Grid layout", [
      numField("Columns", it.grid.cols || 1, "", (v) => set("Grid columns", (g) => { g.cols = Math.max(1, Math.round(v)); }),
        { min: 1, step: 1 }),
      h("p", { class: "hint" }, `${it.items.length} panels in ${rows} row${rows === 1 ? "" : "s"}.`),
      row(numField("Gap across", gx, u, (v) => set("Grid gap", (g) => { g.gap = [Math.max(v, 0), gy]; }), { min: 0 }),
        numField("Gap down", gy, u, (v) => set("Grid gap", (g) => { g.gap = [gx, Math.max(v, 0)]; }), { min: 0 })),
      h("p", { class: "hint" }, "Panels keep their sizes: each column is as wide as its widest panel and each row as tall as its "
        + "tallest, with each panel at the top left of its cell. They move up when one shrinks. The last panel of a short last "
        + "row reaches across the columns left. Double-click the grid to work inside it, and drag a panel onto another cell "
        + "to move it there."),
      h("div", { class: "button-row" },
        button("Stop the grid layout: keep the panels where they are, as an ordinary group", () => this.app.run("stopGrid"), "Stop grid layout"),
        button("Ungroup", () => this.app.run("ungroup"), "Ungroup"))]);
  },
  // The panel a label stays with (labels.js), and a way to let go, or to attach one on a panel
  labelSection(it) {
    const panel = it.attach && findDeep(store.items(), it.attach.to);
    if (panel) {
      return section("Panel", [
        h("p", {}, `Stays with ${itemLabel(panel, store.doc)}, by its ${CORNER_NAMES[it.attach.corner] || "top left"} corner.`),
        h("p", { class: "hint" }, "It goes with the panel when the panel moves or changes size. Drag it to another corner, "
          + "or onto another panel, to keep it there instead."),
        h("div", { class: "button-row" }, button("Detach the label: it stays put when the panel moves", () => this.app.run("detachLabel"), "Detach"))]);
    }
    const near = this.app.labelPanel(it);
    return near ? section("Panel", [
      h("p", {}, "Not attached to a panel."),
      h("div", { class: "button-row" }, button(`Attach to ${itemLabel(near, store.doc)}: it goes with it when it moves`,
        () => this.app.run("attachLabel"), "Attach to the panel"))]) : null;
  },
  objectSection(it) {
    const kids = [textField("Name", it.name || "", (v) => this.edit("Rename", (x) => { x.name = v; }))];
    if (it.type === "picture" || it.type === "group") {
      kids.push(textArea("Description for screen readers", it.alt || "", (v) => this.edit("Description", (x) => { x.alt = v; })));
    }
    kids.push(h("div", { class: "button-row" },
      toggle("Lock position", !!it.locked, (on) => this.edit(on ? "Lock" : "Unlock", (x) => { x.locked = on; }), "🔒 Lock"),
      toggle("Hide", !!it.hidden, (on) => this.edit(on ? "Hide" : "Show", (x) => { x.hidden = on; }), "Hide")));
    return section("Object", kids);
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
          [["straight", "Straight segments", pathPicture("straight")], ["smooth", "Smooth curve", pathPicture("smooth")]],
          (v) => this.edit(v === "smooth" ? "Curve line" : "Straight segments", (x) => { x.curve = v; })),
        ...rows,
        h("div", { class: "button-row" },
          button("Add a point halfway along the longest stretch", () => this.app.run("addPoint"), "Add point"),
          n > 2 ? button("Remove the middle points to make the line straight", () => this.app.run("straighten"), "Make straight") : null),
        h("p", { class: "hint" }, `Length ${fmt(toUnit(length, u), 2)} ${UNIT_LABEL[u]}. On the page, drag the hollow handle `
          + "halfway along the line to bend it; double-click a point to remove it, or the line to add one."),
      ]);
    }
    // (position, size, rotation and flips: the strip above the tabs)
    if (it.type !== "picture") return null;
    return section("Transparency", [
      transparencyField("Transparency", it.opacity, (op) => this.edit("Transparency", (o) => { o.opacity = op; }))]);
  },
  // Turn objects together by `angle` degrees clockwise about the middle of their outline, as one
  // undo step that Transform Again (⌘⇧D) then repeats (app.turnItems)
  turnTogether(label, ids, angle) { this.app.turnItems(label, ids, angle); },
  // Rotate left or right 90° and flip, the ribbon's commands. A shape, picture or symbol shows
  // whether it's flipped (pressed); a text box never is (it keeps reading the right way), and a
  // line, group or several objects flip as a whole, with nothing to show
  turnFlipButtons(it = null) {
    const b = (cmd, ic) => iconButton(this.app, cmd, ic);
    const shows = it?.frame && it.type !== "group" && it.type !== "bracket" && !it.textbox;
    const flip = (cmd, ic, key) => {
      const el = b(cmd, ic);
      if (shows) { el.classList.add("toggle"); el.setAttribute("aria-pressed", it[key] ? "true" : "false"); }
      return el;
    };
    return h("div", { class: "button-row inline icons turn-flip" }, b("rotateLeft90", "rotateLeft"), b("rotateRight90", "rotateRight"),
      flip("flipHorizontal", "flipH", "flip_h"), flip("flipVertical", "flipV", "flip_v"));
  },
  // The Rotation row of the strip above the tabs, with turn and flip buttons: a shape, picture,
  // text box or symbol turns about its own middle; a group turns as a whole about its middle (rot
  // keeps count of how far). A significance bracket has no Rotation: it stays level or upright,
  // and a quarter turn or a flip moves its label to another side
  rotationRow(it) {
    if (it.type === "bracket") return row(this.turnFlipButtons(it));
    const setRot = (v) => this.turnTogether("Rotate", [it.id], turnFrom(store.item(it.id).rot || 0, v));
    return row(numField("Rotation", it.rot || 0, "deg", setRot, { bind: "rot", step: 1 }), this.turnFlipButtons(it));
  },
  // A line's strip: its Angle, the way from its start to its end in degrees clockwise from
  // pointing right (90 points down, as rotation turns clockwise); a typed angle turns the whole
  // line about its middle. Beside it, the turn and flip buttons. No Angle for a line whose ends
  // meet or an elbow connector (its stretches stay level and upright, though quarter turns and
  // flips keep them so); no strip for a zoom inset's line (it follows its box)
  lineStrip(it) {
    if (it.zoomline) return null;
    const angle = lineAngle(it);
    const setAngle = (v) => {
      const was = lineAngle(store.item(it.id));
      if (was !== null) this.turnTogether("Turn line", [it.id], turnFrom(was, v));
    };
    return h("div", { class: "insp-strip", role: "group", "aria-label": "Angle" },
      row(angle === null || it.route === "elbow" ? null : numField("Angle", angle, "deg", setAngle, { bind: "angle", step: 1 }),
        this.turnFlipButtons(it)));
  },
  // Several objects: one Rotation for them all, turning them together about their middle. It
  // shows the angle they share (a line's being its way from start to end); typed, they turn
  // together until they're at it. At different angles it's blank (Mixed), and a typed angle turns
  // them all by that much. Locked objects, area fills (they follow their lines) and scale bars
  // (they follow their pictures) stay put
  multiStrip(sel) {
    const ids = sel.filter((it) => !it.locked && it.geom !== "region" && it.type !== "scalebar").map((it) => it.id);
    if (!ids.length) return null;
    const shared = () => {
      const angles = ids.map((id) => angleOf(store.item(id))).filter((a) => a !== null);
      return angles.length && angles.every((a) => sameAngle(a, angles[0])) ? angles[0] : null;
    };
    const at = shared();
    const setRot = (v) => this.turnTogether("Rotate", ids, turnFrom(shared() ?? 0, v));
    return h("div", { class: "insp-strip", role: "group", "aria-label": "Rotation" },
      row(numField("Rotation", at ?? 0, "deg", setRot, { step: 1, mixed: at === null }), this.turnFlipButtons()),
      at === null ? h("p", { class: "hint" }, "They're at different angles: a typed angle turns them all by that much, "
        + "together about their middle.") : null);
  },
  // Position, size and rotation, above the tabs so they're in view whatever tab is open, and while
  // a handle is dragged (refreshValues): X, Y, width, height and Rotation, typed to change them. A
  // picture keeps its proportions; a group's are its outline's, and its width or height scales
  // everything in it from the top-left corner, keeping its proportions (text sizes and line widths
  // stay). A line has its Angle instead (lineStrip; its points are in Arrange); area fills and
  // scale bars have none
  sizeStrip(it) {
    if (it.type === "line") return this.lineStrip(it);
    const isGroup = it.type === "group";
    if ((!it.frame && !isGroup) || it.geom === "region" || it.type === "scalebar") return null;
    const u = this.units();
    const now = () => store.item(it.id);
    const note = (t) => this.app.noteTransform?.(t);
    // Typed changes count as transforms too, for Transform Again (⌘⇧D), measured from the object
    // as it is now (the numbers here can be from before a drag)
    const box = (x) => {
      if (!isGroup) return x.frame;
      const b = itemsBBox(x.items);
      return [b[0], b[1], b[2] - b[0], b[3] - b[1]];
    };
    const lockAspect = isGroup || it.type === "picture" || !!it.zoom?.circle;
    const setPos = (i) => (v) => {
      const was = box(now());
      note({ kind: "move", dx: i === 0 ? v - was[0] : 0, dy: i === 1 ? v - was[1] : 0 });
      this.edit("Move", (o) => {
        if (!isGroup) { o.frame[i] = v; return; }
        const b = box(o);
        shiftItem(o, JSON.parse(JSON.stringify(o)), i === 0 ? v - b[0] : 0, i === 1 ? v - b[1] : 0);
      });
    };
    const setSize = (i) => (v) => {
      const want = Math.max(v, 0.1), was = box(now())[i];
      if (!(was > 0)) return;
      const k = want / was;
      note({ kind: "resize", sx: lockAspect || i === 2 ? k : 1, sy: lockAspect || i === 3 ? k : 1, anchor: [0, 0] });
      this.edit("Resize", (o) => {
        if (isGroup) { scaleItem(o, k, k, [0, 0]); return; }
        if (lockAspect) o.frame[5 - i] = o.frame[5 - i] * want / o.frame[i];
        o.frame[i] = want;
      });
    };
    const [x, y, w, hh] = box(it);
    return h("div", { class: "insp-strip", role: "group", "aria-label": "Position, size and rotation" },
      row(numField("X", x, u, setPos(0), { bind: "x" }), numField("Y", y, u, setPos(1), { bind: "y" })),
      row(numField("Width", w, u, setSize(2), { bind: "w", min: 0.1 }), numField("Height", hh, u, setSize(3), { bind: "h", min: 0.1 })),
      lockAspect ? h("p", { class: "hint" }, isGroup ? "Width and height scale everything in the group together, keeping its proportions."
        : it.zoom?.circle ? "Width and height stay equal, so the circle stays round." : "Width and height keep the picture's proportions.") : null,
      this.rotationRow(it));
  },
  // What a page's journal asks for besides its size (panel labels, text, lines, pictures, files),
  // folded under one line so the size fields stay in view; once opened it stays open
  journalRules(journal) {
    const say = (r, words) => (r ? h("p", { class: "hint" }, words(r) ? `${words(r)} Source: ${r.source}.` : `${r.source}.`) : null);
    const d = h("details", { class: "journal-rules", open: !!this.rulesOpen },
      h("summary", {}, `What ${journal.name} asks for`),
      say(journal.labels, (l) => `Panel labels: ${labelLook(l)}.`), say(journal.text, textRules),
      say(journal.lines, lineRules), say(journal.pictures, pictureRules), say(journal.export, fileRules));
    d.addEventListener("toggle", () => { this.rulesOpen = d.open; });
    return d;
  },
  // Dangerous mode (liftedtext.js): the texts lifted out of a plot, and edits dropped when its file changed
  plotTextSection(it) {
    const hidden = hiddenOf(it), dropped = it.lifted_text?.dropped || [];
    if (!hidden.length && !dropped.length) return null;
    const kids = [];
    if (hidden.length) {
      kids.push(h("p", { class: "hint" }, `${hidden.length} text${hidden.length === 1 ? "" : "s"} lifted out in dangerous mode, now `
        + `text boxes: ${hidden.map((d) => `“${d.text}”`).join(", ")}. The file itself is unchanged.`),
      h("div", { class: "button-row" }, button("Restore plot text", () => this.app.run("restorePlotText"), "Restore plot text")));
    }
    if (dropped.length) {
      kids.push(h("p", { class: "hint warn" }, `Dropped when its file changed (the text wasn't there any more): `
        + dropped.map((d) => `“${d.text}”${d.box_text && d.box_text !== d.text ? ` (edited to “${d.box_text}”)` : ""}`).join(", ")),
      h("div", { class: "button-row" }, button("Clear this list", () => this.edit("Clear dropped edits", (o) => {
        if (o.lifted_text) delete o.lifted_text.dropped;
        if (o.lifted_text && !hiddenOf(o).length) delete o.lifted_text;
      }), "Clear")));
    }
    return section("Text lifted out", kids);
  },
  // A text box lifted out of a plot: where it came from, and putting it back
  liftedSection(it) {
    const pic = liftedFrom(it), asset = pic && store.doc.assets[pic.asset];
    const d = hiddenOf(pic).find((x) => x.id === it.lifted.of);
    return section("Lifted from a plot", [
      h("p", { class: "hint" }, `Lifted out of ${asset?.name || "a placed plot"} in dangerous mode`
        + (d ? ` (it said “${d.text}”)` : "") + ". It moves and scales with its picture."),
      h("div", { class: "button-row" }, button("Put back in plot", () => this.app.run("putBackText"), "Put back")),
    ]);
  },
  pictureSection(it) {
    const a = store.doc.assets[it.asset];
    const [sw, sh] = (a.page_sizes && a.page_sizes[it.page_index || 0]) || a.size_pt;
    const [l, t, r, b] = it.crop || [0, 0, 0, 0];
    // Across and down: a picture stretched unevenly (a frame from PowerPoint, say) is off in one
    const scalePct = (it.frame[2] / (sw * (1 - l - r))) * 100;
    const scaleDownPct = (it.frame[3] / (sh * (1 - t - b))) * 100;
    const uneven = Math.abs(scalePct - scaleDownPct) > 0.05;
    const scaleText = uneven
      ? `Scale ${fmt(scalePct, 1)}% across, ${fmt(scaleDownPct, 1)}% down — stretched: its text and curves are distorted`
      : `Scale ${fmt(scalePct, 1)}%` + (Math.abs(scalePct - 100) > 0.05 ? ` — text in it prints at ${fmt(scalePct, 1)}% of its size` : " (true size)");
    const variants = Object.keys(a.variants).map((k) => k.toUpperCase()).join(" + ");
    const status = h("p", { class: "link-status", id: `link-${it.id}` }, "Checking file…");
    this.updateLinkStatus(a, it.asset, status);
    const exportKinds = [["auto", "Automatic (best copy for each format)"], ...Object.keys(a.variants).map((k) => [k, `Always the ${k.toUpperCase()} copy`])];
    // A PNG, TIFF or JPEG with no PDF or SVG copy: what kind of picture it is (journals ask more
    // dpi of line art than of photos). Automatic is the Check's guess from its pixels
    const raster = !a.variants.pdf && !a.variants.svg;
    const kind = raster ? selectField("Kind", it.picture_kind || "auto", [["auto", "Automatic"], ["photo", "Photo"],
      ["combination", "Photo with text or lines"], ["line_art", "Line art (graphs, drawings)"]],
    (v) => this.edit("Picture kind", (o) => { if (v === "auto") delete o.picture_kind; else o.picture_kind = v; })) : null;
    if (kind) this.guessKind(a, it.asset, kind);
    return section("Picture", [
      h("p", { class: "file-name", title: a.name }, a.name),
      status,
      h("p", { class: "hint" }, `Copies found: ${variants}. `
        + (a.variants.pdf ? "PDF export uses the PDF copy unchanged" : a.variants.svg ? "PDF export converts the SVG (no PDF copy)" : "")
        + (a.variants.svg ? "; SVG export uses the SVG copy unchanged." : a.variants.pdf ? "; SVG export converts the PDF (no SVG copy)." : ".")),
      h("p", { class: `scale ${uneven || Math.abs(scalePct - 100) > 0.05 ? "warn" : ""}` }, scaleText),
      h("div", { class: "button-row" },
        button("Crop picture", () => canvas.startCrop(it.id), "Crop"),
        button("Reset crop", () => resetCrop(it.id), "Reset crop"),
        // Both sides from the file's own size, so a stretched picture comes back to its proportions too
        button("Set to true size (100%)", () => this.edit("True size", (o) => {
          o.frame[2] = sw * (1 - o.crop[0] - o.crop[2]);
          o.frame[3] = sh * (1 - o.crop[1] - o.crop[3]);
        }), "100%")),
      // A typed size for what shows: cropped from the middle, at the same scale (Width and Height
      // above the tabs scale it instead)
      ...(it.inset ? [] : [row(numField("Crop to width", it.frame[2], this.units(), (v) => cropToSize(it.id, 2, v), { bind: "w", min: 0.1 }),
        numField("Crop to height", it.frame[3], this.units(), (v) => cropToSize(it.id, 3, v), { bind: "h", min: 0.1 })),
      h("p", { class: "hint" }, "Crops equally from both sides, keeping the picture's scale. Width and Height at the top scale it instead.")]),
      ...(it.inset ? [] : this.cropShapeFields(it)),   // (an inset's shape is set in its Zoom inset section)
      selectField("Export from", it.source || "auto", exportKinds, (v) => this.edit("Export source", (o) => { o.source = v; })),
      kind, kind ? h("p", { class: "hint" }, "Journals ask for more dpi for line art than for photos; Check goes by this.") : null,
      h("div", { class: "button-row" },
        button("Replace with another file", () => this.app.run("replacePicture"), "Replace…"),
        button("Show the linked file in the Finder", () => this.app.run("revealPicture"), "Show file"),
        button("Stop following the file; keep the stored copy", () => this.app.run("unlinkPicture"), "Unlink")),
    ]);
  },
  // Crop to shape (PowerPoint's): the picture shows only inside a shape fitted to its frame,
  // with the shape's adjustments and corner rounding
  cropShapeFields(it) {
    const mk = it.mask, info = mk && shapeCatalog.shapes[mk.geom];
    const groups = shapeCatalog.groups.map((g) => [g.title, g.shapes.filter((geom) => shapeCatalog.shapes[geom]?.closed)])
      .filter(([, geoms]) => geoms.length);
    const options = [{ value: "", label: "None (the whole frame)", picture: () => shapePicture(null) },
      // (a shape drawn over it and cropped to: Crop to shape drawn over it, crop.js)
      ...(mk?.geom === "custom" ? [{ value: "custom", label: "The shape drawn over it", picture: () => drawnShapePicture(mk) }] : []),
      ...groups.flatMap(([heading, geoms]) => [{ heading }, ...geoms.map((geom) => ({ value: geom, label: shapeName(geom),
        picture: () => shapePicture(geom) }))])];
    const kids = [pictureField("Crop to shape", mk?.geom || "", options, (v) => this.edit(v ? "Crop to shape" : "No shape crop", (o) => {
      if (v) o.mask = { geom: v };
      else delete o.mask;
    }))];
    if (!mk) return kids;
    const fields = (info?.adjust || []).map((a) => numField(`Shape: ${a.label}`, (mk.adj?.[a.name] ?? a.default) * a.factor, a.unit,
      (v) => this.setMaskAdjust(it.id, a, v), { step: 1, min: a.unit === "deg" || a.min === null ? undefined : a.min * a.factor,
        max: a.unit === "deg" || a.max === null ? undefined : a.max * a.factor }));
    if (info?.corners) {
      fields.push(numField("Shape: corner rounding", (mk.rounding || 0) * 100, "%", (v) => this.edit("Corner rounding", (o) => {
        o.mask = { ...o.mask, rounding: Math.min(Math.max(v, 0), 100) / 100 };
        if (!o.mask.rounding) delete o.mask.rounding;
      }), { min: 0, max: 100, step: 5 }));
    }
    for (let i = 0; i < fields.length; i += 2) kids.push(fields[i + 1] ? row(fields[i], fields[i + 1]) : fields[i]);
    kids.push(h("p", { class: "hint" }, "The picture shows only inside the shape, which fits its frame. Crop moves the picture "
      + "within it; resizing the picture resizes the shape."));
    return kids;
  },
  async setMaskAdjust(id, a, shown) {
    let v = shown / a.factor;
    if (a.unit === "deg") v = ((v % 360) + 360) % 360;
    const it = store.item(id);
    if (!it?.mask) return;
    const stored = await rpc("clamp_adjust", { geom: it.mask.geom, frame: it.frame, adj: it.mask.adj }, a.name, v);
    this.edit(a.label, (o) => { o.mask = { ...o.mask, adj: { ...(o.mask.adj || {}), [a.name]: stored } }; });
  },
  // A border round a picture (round the shape it's cropped to, if it is)
  borderSection(it) {
    const b = it.border;
    const kids = [checkField("Border round it", !!b?.width, (on) => this.edit(on ? "Add border" : "Remove border", (o) => {
      if (on) o.border = { color: "#000000", width: 1 };
      else delete o.border;
    }))];
    if (b?.width) {
      kids.push(row(colorField("Border colour", b.color || "#000000", (v, sw) => this.edit("Border colour", (o) => {
        o.border = linked({ ...o.border, color: v }, sw);
      }), b.swatch), numField("Border thickness", b.width, "pt", (v) => this.edit("Border thickness", (o) => {
        o.border = { ...o.border, width: Math.max(v, 0.1) };
      }), { min: 0.1, step: 0.25 })));
    }
    return section("Border", kids);
  },
  // A zoom inset (zoom.js) shows what's in its box; the box says where its inset is
  insetSection(it) {
    const box = store.item(it.inset.box), pic = box?.zoom && store.item(box.zoom.picture);
    return section("Zoom inset", [
      ...(box?.zoom ? this.zoomShapeFields(box, it, false) : []),
      h("p", { class: "hint" }, box && pic ? `It shows the area in its box on ${itemLabel(pic, store.doc)}, enlarged, and follows `
        + "the box. Resize it to enlarge it more or less." : "Its box has gone, so it stays as it is."),
      box ? button("Select its box on the picture", () => store.select([box.id]), "Select the box") : null]);
  },
  // A zoom inset's shape, on its box's panel and its inset's: the Shape list, Corner rounding for
  // a rounded rectangle, and whether the two share their shape (zoom.js)
  zoomShapeFields(box, inset, onBox) {
    const same = !box.zoom.own_shapes, it = onBox ? box : inset, mine = same || onBox;
    const shape = zoomShape(mine ? box : inset), geom = mine ? box.geom : inset.mask?.geom;
    const options = ZOOM_SHAPES.filter(([, sh]) => sh !== "circle" || mine)   // (an inset on its own keeps the box's proportions)
      .map(([, sh, label]) => ({ value: sh, label, picture: () => zoomShapePicture(sh) }));
    if (shape === "other") options.push({ value: "other", label: shapeName(geom), picture: () => shapePicture(geom) });
    const kids = [pictureField("Zoom shape", shape, options, (v) => { if (v !== "other") this.app.setZoomShape(it.id, v); })];
    if (shape === "round") {
      kids.push(numField("Corner rounding", ((mine ? box.rounding : inset.mask?.rounding) || 0) * 100, "%",
        (v) => this.app.setZoomRounding(it.id, Math.min(Math.max(v, 0), 100) / 100), { min: 0, max: 100, step: 5 }));
    }
    kids.push(checkField(onBox ? "Same shape as the inset" : "Same shape as the box", same, (on) => this.app.matchZoomShapes(it.id, on)));
    if (!same && !onBox) kids.push(h("p", { class: "hint" }, "Its proportions follow the box's, so it's round only when the box is."));
    return kids;
  },
  zoomBoxSection(it) {
    const all = [], walk = (its) => its.forEach((x) => { all.push(x); if (x.type === "group") walk(x.items); });
    walk(store.items());
    const inset = all.find((x) => x.inset?.box === it.id);
    return section("Zoom inset", [
      ...(inset ? this.zoomShapeFields(it, inset, true) : []),
      h("p", { class: "hint" }, inset ? "Its area is shown enlarged in the inset, which follows it: drag or resize the box to show "
        + "another area. It stays over the same part of its picture when the picture moves." : "Its inset has gone."),
      inset ? button("Select the enlarged copy", () => store.select([inset.id]), "Select the inset") : null]);
  },
  // A picture's scale, for scale bars: a pixel's size typed (a point of a PDF's or SVG's), a known
  // length measured on it, or what the file says (ImageJ, OME-TIFF)
  scaleSection(it) {
    const a = store.doc.assets[it.asset], ppp = pxPerPt(a), sc = it.scale;
    const cal = a.variants?.[a.primary]?.calibration, unit = sc?.unit || cal?.unit || "µm";
    const id = `f${++fieldId}`;
    const size = h("input", { id, type: "number", inputmode: "decimal", min: 0, step: "any", placeholder: "e.g. 0.65",
      value: sc ? +(ppp ? sc.per_pt / ppp : sc.per_pt).toPrecision(6) : "" });
    size.addEventListener("change", () => {
      const v = parseFloat(size.value);
      this.app.setPictureScale(it.id, v > 0 ? (ppp ? v * ppp : v) : 0, unit, "typed");
    });
    size.addEventListener("keydown", (e) => { if (e.key === "Enter") size.blur(); keepFieldKeys(e); });
    const kids = [row(h("div", { class: "field" }, label(ppp ? "Size of one pixel" : "Length of one point of the original", id), size),
      selectField("Scale unit", unit, UNITS.map(([u]) => [u, u]), (u) => { if (sc) this.app.setPictureScale(it.id, convert(sc.per_pt, sc.unit, u), u, sc.how); }))];
    const how = { typed: "typed", measured: "measured", file: "from the file" }[sc?.how] || "";
    kids.push(h("p", { class: "hint" }, sc ? `Scale${how ? ` (${how})` : ""}: ${scaleText(it, a)}.` : "No scale yet."));
    const fileScale = cal && ppp ? cal.per_px * ppp : null;
    if (fileScale && Math.abs((sc?.per_pt || 0) - fileScale) > fileScale * 1e-9) {
      kids.push(h("p", { class: "hint" }, `The file says one pixel is ${+cal.per_px.toPrecision(6)} ${cal.unit} (${cal.from}).`),
        button("Use the scale saved in the file", () => this.app.setPictureScale(it.id, fileScale, cal.unit, "file"), "Use the file's scale"));
    }
    kids.push(h("div", { class: "button-row" },
      button("Measure a known length on the picture", () => canvas.startMeasure(it.id), "Measure…"),
      sc ? button("Add a scale bar to this picture", () => this.app.addScaleBar(it.id), "Add scale bar") : null));
    kids.push(h("p", { class: "hint" }, "Measure: drag along something of known length in the picture, then type its length. "
      + "Scale bars stay right when the picture is resized or cropped."));
    return section("Scale", kids);
  },
  // A significance bracket: its label (asterisks, ns or any text), which side it's on, its ticks
  // and look; the bar stays put when the label changes
  bracketSection(it) {
    const set = (label, fn) => this.edit(label, (o) => keepBar(o, fn));
    const preset = BRACKET_LABELS.some(([v]) => v === it.label);
    const kids = [row(selectField("Label", preset ? it.label : "custom", [...BRACKET_LABELS, ["custom", "Other text…"]], (v) => {
      set("Bracket label", (o) => { o.label = v === "custom" ? "p = 0.05" : v; });   // other text starts as a p-value to edit
    }), preset ? null : textField("Label text", it.label || "", (v) => set("Bracket label", (o) => { o.label = v; }), {}))];
    const sides = across(it) ? [["up", "Above"], ["down", "Below"]] : [["right", "Right"], ["left", "Left"]];
    kids.push(radioField("Label side", it.dir || "up", sides, (v) => this.edit("Bracket side", (o) => { o.dir = v; })));
    if (across(it)) {
      kids.push(numField("End ticks", Math.max(it.frame[3] - (it.label ? (it.size ?? 6) * 1.5 : 0), 0), "pt", (v) => this.edit("Bracket ticks", (o) => {
        const room = o.label ? (o.size ?? 6) * 1.5 : 0, t0 = Math.max(o.frame[3] - room, 0), t1 = Math.max(v, 0);
        o.frame = [o.frame[0], (o.dir || "up") === "up" ? o.frame[1] : o.frame[1] + t0 - t1, o.frame[2], room + t1];
      }), { min: 0, step: 0.5 }));
    } else {
      kids.push(numField("End ticks", it.tick ?? 4, "pt", (v) => this.edit("Bracket ticks", (o) => { o.tick = Math.max(v, 0); }), { min: 0, step: 0.5 }));
    }
    kids.push(row(colorField("Colour", it.color || "#000000", (v, sw) => this.edit("Bracket colour", (o) => { linked(o, sw).color = v; }), it.swatch),
      numField("Line thickness", it.line_width ?? 0.75, "pt", (v) => this.edit("Bracket line", (o) => { o.line_width = Math.max(v, 0.1); }),
        { min: 0.1, step: 0.25 })));
    kids.push(row(numField("Text size", it.size ?? 6, "pt", (v) => set("Bracket text size", (o) => { o.size = Math.max(v, 1); }), { min: 1, step: 0.5 }),
      h("div", { class: "button-row inline" }, toggle("Bold", !!it.bold, (on) => this.edit("Bold", (o) => { o.bold = on; }), "B", "bold"))));
    kids.push(h("p", { class: "hint" }, "Drag its side handles to span other bars, and the top or bottom handle to lengthen "
      + "the ticks. Several brackets selected can be stacked in tidy levels (Stack, Figure tab)."));
    return section("Bracket", kids);
  },
  // A scale bar: its length and look, and which corner of its picture it stays with
  scalebarSection(it) {
    const pic = store.item(it.picture), a = pic && store.doc.assets[pic.asset];
    const set = (label, fn) => this.edit(label, fn);
    const kids = [h("p", { class: "hint" }, !pic ? "Its picture has gone, so it no longer follows a scale."
      : !pic.scale ? `${itemLabel(pic, store.doc)} has no scale any more: give it one in its Picture tab.`
        : `On ${itemLabel(pic, store.doc)} (${scaleText(pic, a)}).`)];
    kids.push(row(numField("Length", it.length, "", (v) => set("Scale bar length", (o) => { o.length = Math.max(v, 1e-9); }), { min: 0, step: "any" }),
      selectField("Length unit", it.unit, UNITS.map(([u]) => [u, u]), (v) => set("Scale bar unit", (o) => { o.unit = v; }))));
    if (pic?.scale) {
      kids.push(button("A round length about a fifth of the picture's width", () => set("Scale bar length", (o) => {
        o.length = niceLength(pic, a, o.unit);
      }), "Round length"));
    }
    kids.push(radioField("Label", it.label || "above", [["above", "Above"], ["below", "Below"], ["none", "None"]],
      (v) => set("Scale bar label", (o) => { o.label = v; })));
    kids.push(row(colorField("Colour", it.color || "#ffffff", (v, sw) => set("Scale bar colour", (o) => { linked(o, sw).color = v; }), it.swatch),
      numField("Thickness", it.thickness ?? 2, "pt", (v) => set("Scale bar thickness", (o) => { o.thickness = Math.max(v, 0.1); }), { min: 0.1, step: 0.5 })));
    kids.push(row(numField("Text size", it.size ?? 6, "pt", (v) => set("Scale bar text size", (o) => { o.size = Math.max(v, 1); }), { min: 1, step: 0.5 }),
      h("div", { class: "button-row inline" }, toggle("Bold", !!it.bold, (on) => set("Bold", (o) => { o.bold = on; }), "B", "bold"))));
    if (pic) {
      kids.push(selectField("Stays with its picture's", it.anchor?.corner || "br", [["tl", "Top left corner"], ["tr", "Top right corner"],
        ["bl", "Bottom left corner"], ["br", "Bottom right corner"]], (v) => set("Scale bar corner", (o) => { o.anchor = anchorFor(o, pic, v); })));
    }
    kids.push(h("p", { class: "hint" }, "Drag it to place it; it moves with its picture, and its length follows the picture's "
      + "size and crop."));
    return section("Scale bar", kids);
  },
  // The Check's guess at a picture's kind, named in the Kind list's Automatic choice
  async guessKind(asset, assetId, field) {
    try {
      const guess = (await rpc("picture_kinds", { [assetId]: asset }))[assetId];
      const opt = field.querySelector('option[value="auto"]');
      if (guess && opt) opt.textContent = `Automatic (looks like ${KIND_NAMES[guess]})`;
    } catch { /* it stays "Automatic" */ }
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
      const groups = shapeCatalog.groups.map((g) => [g.title, g.shapes]);
      if (!shapeCatalog.groups.some((g) => g.shapes.includes(it.geom))) groups.push(["From PowerPoint", [it.geom]]);
      kids.push(pictureField("Shape", it.geom, groups.flatMap(([heading, geoms]) => [{ heading },
        ...geoms.map((geom) => ({ value: geom, label: shapeName(geom), picture: () => shapePicture(geom) }))]), (v) => this.edit("Change shape", (o) => {
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
    if (it.geom === "custom") {
      kids.push(button("Edit this shape's points and curves on the page", () => canvas.startPointEdit(it.id), "Edit points"));
    } else if (it.geom !== "arc") {
      kids.push(button("Make this a freeform shape of the same outline, whose points you can move", () => this.app.run("makeEditable"),
        "Make editable shape"));
    }
    if (it.geom === "arc") {
      kids.push(button("Turn this arc into a curve with points you can drag", () => this.app.run("shapeToCurve"), "Make editable curve"));
      kids.push(h("p", { class: "hint" }, "The curve passes through points along the arc, so its shape may shift by a fraction of a point."));
    }
    const hints = [];
    if (info?.adjust?.length) hints.push("Drag the yellow handles on the page to adjust the shape.");
    if (/^star\d+$/.test(it.geom)) hints.push("Inner radius is a percentage of the outer radius.");
    if (roundable) hints.push("Corner rounding: 0% keeps the corners sharp; 100% is as round as the shape allows.");
    if (it.geom === "custom") hints.push("Or double-click it to edit its points.");
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
    const f = it.fill, g = f?.gradient;
    const mode = !f ? "none" : g ? (g.type === "radial" ? "radial" : "linear") : "solid";
    const opts = [["none", "No fill"], ["solid", "Colour"], ["linear", "Linear gradient"], ["radial", "Radial gradient"]];
    const kids = [pictureField("Fill", mode, opts.map(([value, label]) => ({ value, label, picture: () => fillPicture(it, value) })), (v) => this.edit("Fill", (o) => {
      if (v === "solid" && o.fill && !o.fill.gradient) return;   // (with several objects: a colour fill keeps its colour)
      const old = o.fill, og = old?.gradient;
      if (v === "none") o.fill = null;
      else if (v === "solid") o.fill = og ? { color: og.stops[0].color, opacity: og.stops[0].opacity ?? 1 }
        : { color: old?.color || "#ffffff", opacity: old?.opacity ?? 1 };
      else {
        // From the fill's colour to white, or the gradient it had, top to bottom (radial: from the middle)
        const stops = og?.stops || [{ pos: 0, color: old?.color || "#ffffff", opacity: old?.opacity ?? 1 },
          { pos: 1, color: "#ffffff", opacity: old?.opacity ?? 1 }];
        const gradient = v === "radial" ? { type: "radial", center: og?.center || [0.5, 0.5], stops }
          : { type: "linear", angle: og?.angle ?? 90, scaled: og?.scaled ?? false, stops };
        o.fill = { color: stops[0].color, opacity: 1, gradient };
      }
    }), { mixed: this.mx("fill") })];
    if (mode === "solid" && !this.mx("fill")) kids.push(row(
      colorField("Fill colour", f.color, (v, sw) => this.edit("Fill colour", (o) => { o.fill = linked({ ...o.fill, color: v }, sw); }),
        this.mx("fill.swatch") ? null : f.swatch, { mixed: this.mx("fill.color") }),
      transparencyField("Fill transparency", f.opacity, (op) => this.edit("Fill transparency", (o) => { o.fill = { ...o.fill, opacity: op }; }),
        { mixed: this.mx("fill.opacity") })));
    // (several objects: their gradients' stops only when they all have the same gradient)
    if (g && !this.mx("fill") && !this.mx("fill.gradient")) kids.push(...this.gradientFields(g));
    if (f) kids.push(this.fillReachField(it));
    return section("Fill", kids);
  },
  // Where the fill stops against its lines (fillreach.py): their middle, inner edge or outer
  // edge, which shows only through dashed, dotted or see-through lines (greyed out otherwise)
  fillReachField(it) {
    const shows = (st) => !!st && ((st.dash && st.dash !== "solid") || (st.opacity ?? 1) < 1);
    const lines = it.geom === "region" ? (it.region?.items || []).map((id) => store.item(id)?.stroke) : [it.stroke];
    return pictureField("Fill reaches", it.fill_reach || "middle", [["middle", "Middle of the line"], ["inner", "Inner edge of the line"],
      ["outer", "Outer edge of the line"]].map(([value, label]) => ({ value, label, picture: () => reachPicture(it, value) })),
    (v) => this.edit("Fill reaches", (o) => {
      if (v === "middle") delete o.fill_reach;
      else o.fill_reach = v;
    }), { disabled: lines.some(shows) || this.mixedLook ? null : "For dashed, dotted or see-through lines", mixed: this.mx("fill_reach") });
  },
  // A gradient's direction (linear) or starting point (radial), and its colour stops, each with
  // a position and a transparency
  gradientFields(g) {
    const setG = (label, fn) => this.edit(label, (o) => {
      const gr = JSON.parse(JSON.stringify(o.fill.gradient));
      fn(gr);
      gr.stops.sort((a, b) => a.pos - b.pos);
      o.fill = { ...o.fill, color: gr.stops[0].color, gradient: gr };
    });
    const out = [gradientBar(g)];
    if (g.type === "radial") {
      const at = CENTRES.find(([, c]) => c[0] === g.center?.[0] && c[1] === g.center?.[1])?.[0] || "middle";
      out.push(pictureField("Gradient from", at, CENTRES.map(([value, centre, label]) => ({ value, label,
        picture: () => fillPicture({ fill: { gradient: g } }, "radial", centre) })),
        (v) => setG("Gradient centre", (gr) => { gr.center = CENTRES.find(([k]) => k === v)[1].slice(); })));
    } else {
      out.push(numField("Gradient angle", g.angle ?? 0, "deg", (v) => setG("Gradient angle", (gr) => {
        gr.angle = ((v % 360) + 360) % 360;
      }), { step: 15 }));
    }
    g.stops.forEach((st, i) => {
      const n = i + 1;
      out.push(h("div", { class: "grad-stop" },
        row(colorField(`Stop ${n} colour`, st.color, (v, sw) => setG("Gradient colour", (gr) => { linked(gr.stops[i], sw).color = v; }), st.swatch),
          numField(`Stop ${n} position`, st.pos * 100, "%", (v) => setG("Gradient stop position", (gr) => {
            gr.stops[i].pos = Math.min(Math.max(v / 100, 0), 1);
          }), { min: 0, max: 100, step: 5 })),
        row(transparencyField(`Stop ${n} transparency`, st.opacity, (op) => setG("Gradient transparency", (gr) => { gr.stops[i].opacity = op; })),
          g.stops.length > 2 ? button(`Remove colour stop ${n}`, () => setG("Remove gradient stop", (gr) => { gr.stops.splice(i, 1); }),
            "Remove stop", "small") : null)));
    });
    out.push(row(button("Add a colour stop in the widest gap", () => setG("Add gradient stop", addGradientStop), "Add stop", "small"),
      button("Reverse the gradient's colours", () => setG("Reverse gradient", (gr) => {
        gr.stops = gr.stops.map((s) => ({ ...s, pos: 1 - s.pos }));
      }), "Reverse", "small")));
    return out;
  },
  strokeSection(it) {
    const st = it.stroke;
    const kids = [];
    // (with several objects: lines keep theirs, and a line added keeps any there already)
    if (it.type !== "line") kids.push(pictureField("Line", st ? "solid" : "none", [["none", "No line"], ["solid", "Line"]]
      .map(([value, label]) => ({ value, label, picture: () => linePicture(st, value === "solid") })), (v) =>
      this.edit(v === "none" ? "Remove line" : "Add line", (o) => {
        if (v === "none" && o.type === "line") return;
        o.stroke = v === "none" ? null : o.stroke || { color: "#000000", width: this.app.prefs.stroke_width || 1, dash: "solid", cap: "round", join: "round", opacity: 1 };
      }), { mixed: this.mx("stroke") }));
    if (st) {
      const set = (label, key, conv = (v) => v) => (v) => this.edit(label, (o) => { o.stroke = { ...o.stroke, [key]: conv(v) }; });
      kids.push(row(colorField("Line colour", st.color || "#000000",
        (v, sw) => this.edit("Line colour", (o) => { o.stroke = linked({ ...o.stroke, color: v }, sw); }),
        this.mx("stroke.swatch") ? null : st.swatch, { mixed: this.mx("stroke.color") }),
        numField("Line width", st.width ?? 1, "pt", set("Line width", "width", (v) => Math.max(v, 0)),
          { min: 0, step: 0.25, mixed: this.mx("stroke.width") })));
      kids.push(pictureField("Dash", typeof st.dash === "string" ? st.dash : "solid",
        DASHES.map(([value, label]) => ({ value, label, picture: () => dashPicture(st, value) })), set("Dash", "dash"),
        { mixed: this.mx("stroke.dash") }));
      // How close the dashes or dots are: their gaps as a percentage of the style's (lower is
      // denser), the dashes keeping their length
      const dashed = (st.dash && st.dash !== "solid") || this.mx("stroke.dash");
      if (dashed) {
        kids.push(numField("Dash spacing", (st.dash_spacing ?? 1) * 100, "%", (v) => this.edit("Dash spacing", (o) => {
          const f = Math.max(v, 0) / 100;
          o.stroke = { ...o.stroke };
          if (Math.abs(f - 1) < 1e-9) delete o.stroke.dash_spacing;
          else o.stroke.dash_spacing = f;
        }), { min: 0, max: 1000, step: 10, mixed: this.mx("stroke.dash_spacing") }),
        h("p", { class: "hint" }, "The gaps between dashes or dots: 100% as the style has them, lower is denser."));
      }
      // Dashed lines get a dash (or dot) on every corner and end, evenly spaced between them;
      // unticked, the pattern runs on regardless of corners, as in PowerPoint
      if (dashed) {
        kids.push(checkField("Even dashes: one on every corner and end", st.even_dashes !== false, (on) =>
          this.edit(on ? "Even dashes" : "PowerPoint dash spacing", (o) => {
            o.stroke = { ...o.stroke };
            if (on) delete o.stroke.even_dashes;
            else o.stroke.even_dashes = false;
          }), { mixed: this.mx("stroke.even_dashes") }));
      }
      kids.push(row(pictureField("Ends", st.cap || "flat", [["round", "Round"], ["flat", "Flat"], ["square", "Square"]]
        .map(([value, label]) => ({ value, label, picture: () => capPicture(st, value) })), set("Line ends", "cap"), { mixed: this.mx("stroke.cap") }),
      pictureField("Corners", st.join || "round", [["round", "Round"], ["miter", "Sharp"], ["bevel", "Bevelled"]]
        .map(([value, label]) => ({ value, label, picture: () => joinPicture(st, value) })), set("Corners", "join"), { mixed: this.mx("stroke.join") })));
      kids.push(transparencyField("Line transparency", st.opacity, (op) => this.edit("Line transparency", (o) => { o.stroke = { ...o.stroke, opacity: op }; }),
        { mixed: this.mx("stroke.opacity") }));
    }
    return section("Line", kids);
  },
  // A contour in a second colour around the whole arrow or shape (lines, heads and fill)
  outlineSection(it) {
    const o = it.outline, k = outlineKind(it), inside = k.filled || k.encloses, sides = outlineSides(k);
    const kids = [checkField("Outline around it", !!o, (on) => this.edit(on ? "Add outline" : "Remove outline", (x) => {
      x.outline = on ? x.outline || { color: contrastingOutline(x), width: 1, opacity: 1 } : null;
    }), { mixed: this.mx("outline") })];
    if (o) {
      const set = (label, key) => (v) => this.edit(label, (x) => { x.outline = { ...x.outline, [key]: v }; });
      kids.push(row(colorField("Outline colour", o.color,
        (v, sw) => this.edit("Outline colour", (x) => { x.outline = linked({ ...x.outline, color: v }, sw); }),
        this.mx("outline.swatch") ? null : o.swatch, { mixed: this.mx("outline.color") }),
        numField("Outline thickness", o.width ?? 1, "pt", (v) => set("Outline thickness", "width")(Math.max(v, 0.05)),
          { min: 0.05, step: 0.25, mixed: this.mx("outline.width") })));
      kids.push(transparencyField("Outline transparency", o.opacity, (op) => set("Outline transparency", "opacity")(op),
        { mixed: this.mx("outline.opacity") }));
      // Sides and Gaps each change only their half of the type; every choice is offered, greyed
      // out with the reason where it would change nothing yet. (A line made from a closed one keeps
      // its left or right side, shown as it is)
      const look = outlineLook(o.type, k);
      if (!sides.some(([v]) => v === look.sides)) sides.push([look.sides, look.sides === "left" ? "Left side" : "Right side"]);
      const pick = (label, part) => (v) => set(label, "type")(outlineType(part === "sides" ? v : look.sides, part === "gaps" ? v : look.gaps));
      kids.push(row(
        pictureField("Sides", look.sides, sides.map(([value, label]) => ({ value, label,
          picture: () => outlinePicture(it, outlineType(value, look.gaps), inside) })), pick("Outline sides", "sides"),
        { disabled: k.lined || k.filled ? null : "For something with a line or a fill", mixed: this.mx("outline.type") }),
        pictureField("Gaps", look.gaps, OUTLINE_GAPS.map(([value, label]) => ({ value, label,
          picture: () => outlinePicture(it, outlineType(look.sides, value), inside) })), pick("Outline gaps", "gaps"),
        { disabled: k.dashed || this.mixedLook ? null : "For dashed and dotted lines", mixed: this.mx("outline.type") })));
    }
    kids.push(h("p", { class: "hint" }, "A band of another colour around everything it draws, e.g. a white edge that keeps a black arrow "
      + "visible on a photo."
      + (!o ? "" : inside ? ` Outside: only outside the shape. Inside: only inside it${k.filled ? ", over the fill" : ""}. Both sides: `
        + `along both sides of the ${k.lined ? "line" : "edge"}.`
        : " Left side or Right side: one side of the line, going from its start to its end. Both sides: along both sides.")
      + (o && k.dashed ? " Gaps filled: the outline runs on through the line's gaps. Gaps empty: it goes only round each dash or dot." : "")));
    return section("Outline", kids);
  },
  endsSection(it) {
    const end = (key, label) => {
      const spec = it[key];
      const out = [row(pictureField(label, spec?.type || "none", HEADS.map(([value, name]) => ({ value, label: name,
        picture: () => headPicture(it, key, value, spec?.w || "med") })), (v) => this.edit("Arrowhead", (o) => {
        o[key] = v === "none" ? null : { ...(o[key] || {}), type: v, w: o[key]?.w || "med", len: o[key]?.len || "med" };
      }), { mixed: this.mx(key) }), pictureField(`${label} size`, spec?.w || "med", SIZES.map(([value, name]) => ({ value, label: name,
        picture: () => headPicture(it, key, spec?.type || "triangle", value) })), (v) => this.edit("Arrowhead size", (o) => {
        if (o[key]) o[key] = { ...o[key], w: v, len: v };
      }), { disabled: spec ? null : "Choose an arrowhead first", mixed: this.mx(`${key}.w`) }))];
      if (spec && ROUNDED_HEADS.includes(spec.type)) {
        out.push(numField(`${label} rounding`, (spec.rounding || 0) * 100, "%", (v) => this.edit("Arrowhead rounding", (o) => {
          if (!o[key] || !ROUNDED_HEADS.includes(o[key].type)) return;
          o[key] = { ...o[key], rounding: Math.min(Math.max(v, 0), 100) / 100 };
          if (!o[key].rounding) delete o[key].rounding;
        }), { min: 0, max: 100, step: 5, mixed: this.mx(`${key}.rounding`) }));
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
    // (while typing in it, through the text being typed, so the change isn't lost when typing ends)
    const target = () => (canvas.editing?.id === it.id ? { typing: true, id: it.id, whole: true } : { ids: [...store.selection] });
    const setRuns = (label, fn) => canvas.changeText(label, { run: fn }, target());
    const fontList = h("datalist", { id: "font-list" }, ...(this.app.fonts || []).map((f) => h("option", { value: f })));
    const align = body.paragraphs[0]?.align || "l";
    // Its text style: the one its paragraphs use, whether this text has been changed from it
    const styles = store.doc.text_styles || [];
    const st = styles.find((x) => body.paragraphs.some((p) => p.style === x.id));
    const changed = st && body.paragraphs.some((p) => p.style === st.id && differs(p, st));
    const styleKids = [selectField("Text style", st ? st.id : "", [["", "None"], ...styles.map((x) => [x.id, x.name])], (v) => {
      const pick = styles.find((x) => x.id === v);
      if (canvas.editing?.id !== it.id) return this.app.applyTextStyle(v);
      canvas.changeText(pick ? "Text style" : "No text style", { para: (p) => { if (pick) applyToParagraph(p, pick); else delete p.style; } }, target());
    })];
    if (changed) {
      styleKids.push(h("p", { class: "hint" }, `This text differs from ${st.name}.`), h("div", { class: "button-row" },
        button(`Put this text back to ${st.name}`, () => this.app.clearTextChanges(), "Clear changes"),
        button(`Change ${st.name} to look like this text, with the text using it`, () => this.app.redefineTextStyle(st.id, store.item(it.id)),
          "Update the style to match")));
    }
    styleKids.push(h("div", { class: "button-row" }, button("Make a new text style from this text", () => this.app.newTextStyle(),
      "New style from this text…")));
    return section("Text", [
      ...styleKids,
      button("Edit text", () => canvas.startEdit(it.id), "Edit text…"),
      fontList,
      textField("Font", first.font || "Helvetica", (v) => setRuns("Font", (r) => { r.font = v; }), { list: "font-list" }),
      row(numField("Size", first.size || 6, "pt", (v) => setRuns("Text size", (r) => { r.size = Math.max(v, 0.5); }), { min: 0.5, step: 0.5 }),
        colorField("Text colour", first.color || "#000000", (v, sw) => setRuns("Text colour", (r) => { linked(r, sw).color = v; }), first.swatch)),
      h("div", { class: "button-row" },
        toggle("Bold", !!first.bold, (on) => setRuns("Bold", (r) => { r.bold = on; }), "B", "bold"),
        toggle("Italic", !!first.italic, (on) => setRuns("Italic", (r) => { r.italic = on; }), "I", "italic"),
        toggle("Underline", !!first.underline, (on) => setRuns("Underline", (r) => { r.underline = on; }), "U", "underline"),
        this.scriptButton("Superscript", "superscript", SUPERSCRIPT, first, setRuns, "x²"),
        this.scriptButton("Subscript", "subscript", SUBSCRIPT, first, setRuns, "x₂")),
      this.symbolsField(),
      radioField("Align", align, [["l", "Left"], ["ctr", "Centre"], ["r", "Right"]],
        (v) => canvas.changeText("Align text", { para: (p) => { p.align = v; } }, target())),
      radioField("Vertical position", body.anchor || "t", [["t", "Top"], ["ctr", "Middle"], ["b", "Bottom"]],
        (v) => canvas.changeText("Text position", { body: (x) => { x.anchor = v; } }, target())),
      checkField("Wrap text in the box", body.wrap !== false, (on) => this.edit("Wrap", (o) => { o.text.wrap = on; })),
      checkField("Resize the box to fit the text", body.autofit === "shape", (on) => this.edit("Autofit", (o) => { o.text.autofit = on ? "shape" : "none"; })),
      // Kerning: on for text made since mosaic kerned; text from before keeps its spacing until turned on
      checkField("Kerning (letter pairs such as Ty and AV set closer, as the font says)",
        body.paragraphs.some((p) => (p.runs || []).some((r) => r.kern)),
        (on) => setRuns(on ? "Kerning on" : "Kerning off", (r) => { if (on) r.kern = true; else delete r.kern; })),
    ]);
  },

  // Raised or lowered text: while typing, the selected words (the button keeps the focus in the
  // text, and ⌘⇧= / ⌘= do the same); otherwise the whole box
  scriptButton(label, command, base, first, setRuns, content) {
    const b = button(label + (command === "superscript" ? ` (${this.app.mod}Shift+=)` : ` (${this.app.mod}=)`), () => {
      if (canvas.editing) { document.execCommand(command); return; }
      const on = (first.baseline || 0) !== base;
      setRuns(label, (r) => { if (on) r.baseline = base; else delete r.baseline; });
    }, content, "script");
    b.setAttribute("aria-pressed", (first.baseline || 0) === base ? "true" : "false");
    b.addEventListener("mousedown", (e) => e.preventDefault());
    return b;
  },
  // Symbols science needs: inserted where the cursor is while typing, or else at the end
  symbolsField() {
    const insert = (ch) => {
      if (canvas.editing) { document.execCommand("insertText", false, ch); return; }
      this.edit("Insert symbol", (o) => {
        const p = o.text.paragraphs[o.text.paragraphs.length - 1];
        const r = p.runs[p.runs.length - 1];
        if (r) r.t = (r.t || "") + ch;
        else p.runs.push({ ...DEFAULT_RUN, t: ch });
      });
    };
    const grid = (list) => h("div", { class: "symbol-grid" }, ...list.map(([ch, name]) => {
      const b = button(`Insert ${ch}, ${name}`, () => insert(ch), ch, "symbol");
      b.addEventListener("mousedown", (e) => e.preventDefault());   // keeps the cursor in the text
      return b;
    }));
    return h("details", { class: "symbols" }, h("summary", {}, "Symbols"), grid(SYMBOLS),
      h("p", { class: "hint" }, "Greek"), grid(GREEK));
  },
  // Several items ------------------------------------------------------------------------

  multiTabs(sel) {
    return [["arrange", "Arrange", [...this.alignSections(sel.length), section("Objects", [
      h("p", { class: "hint" }, sel.map((it) => itemLabel(it, store.doc)).slice(0, 6).join(", ") + (sel.length > 6 ? "…" : "")),
      h("div", { class: "button-row" }, button("Group", () => this.app.run("group"), "Group"),
        button("Delete", () => this.app.run("delete"), "Delete"))]),
    sel.every((it) => it.type === "bracket") ? section("Brackets", [
      button("Stack the brackets in tidy levels, the narrowest lowest", () => this.app.run("stackBrackets"), "Stack"),
      h("p", { class: "hint" }, "Brackets that don't overlap share a level; each level sits just above the one below.")]) : null]],
    this.lookTab(sel)].filter(Boolean);
  },
  // Several objects' looks at once (several selected, or a group): the Style tab's object style,
  // shape, fill, line, arrowheads and outline, for every line and shape among them, those inside
  // groups too (lookTargets). Each field shows what they share, blank ("Mixed") where they differ
  // (mx), and a change goes to each one that can take it (editLooks), as one undo step
  lookTab(items) {
    const all = lookTargets(items);
    if (!all.length) return null;
    const plain = (o) => o.type === "shape" && !o.textbox && o.geom !== "region";
    const lined = all.filter((o) => takes(o, "stroke")), filled = all.filter((o) => takes(o, "fill"));
    const headed = all.filter((o) => takes(o, "arrow_start")), shaped = all.filter(plain);
    // What the fields show: the first one's look, each part from the first that has it
    const first = shaped[0] || all.find((o) => o.type === "shape") || all[0];
    const rep = JSON.parse(JSON.stringify(first));
    for (const [key, list] of [["stroke", lined], ["fill", filled], ["outline", all], ["arrow_start", headed], ["arrow_end", headed]]) {
      rep[key] = JSON.parse(JSON.stringify(list.find((o) => o[key])?.[key] ?? null));
    }
    rep.fill_reach = filled.find((o) => o.fill)?.fill_reach;
    const via = (want) => {
      const ctx = Object.create(this);
      ctx.edit = (label, fn) => this.editLooks(label, fn, want, all);
      return ctx;
    };
    this.mixedLook = mixedLooks(lined, filled, headed, shaped, all);
    try {
      return ["style", "Style", [
        this.multiObjectStyleSection(rep, all),
        shaped.length ? this.multiShapeSection(shaped, via) : null,
        filled.length ? this.fillSection.call(via((o, label) => takes(o, "fill")
          && (label === "Fill" || (/gradient/i.test(label) ? !!o.fill?.gradient : !!o.fill))), rep) : null,
        lined.length ? this.strokeSection.call(via((o, label) => takes(o, "stroke")
          && (label === "Add line" || label === "Remove line" || !!o.stroke)),
        { ...rep, type: lined.every((o) => o.type === "line") ? "line" : "shape" }) : null,
        headed.length ? this.endsSection.call(via((o) => takes(o, "arrow_start")), rep) : null,
        this.outlineSection.call(via((o, label) => label === "Add outline" || label === "Remove outline" || !!o.outline), rep),
      ]];
    } finally {
      this.mixedLook = null;
    }
  },
  mx(path) { return !!this.mixedLook?.has(path); },
  editLooks(label, fn, want, targets) {
    const ids = targets.map((o) => o.id);
    store.update(label, (doc) => {
      for (const id of ids) {
        const it = findDeep(doc.pages[store.pageIndex].items, id);
        if (it && want(it, label)) fn(it, doc);
      }
    });
  },
  // Several objects' object style: the one they share, or Mixed; a choice goes to them all
  multiObjectStyleSection(rep, all) {
    const styles = store.doc.object_styles || [], used = new Set(all.map((o) => o.object_style || ""));
    return section("Object style", [pictureField("Object style", used.size === 1 ? [...used][0] : "",
      [{ value: "", label: "None", picture: () => stylePicture(rep, null) },
        ...styles.map((x) => ({ value: x.id, label: x.name, picture: () => stylePicture(rep, x) }))],
      (v) => this.app.useObjectStyle(v), { mixed: used.size > 1 })]);
  },
  // Several shapes' kind and corner rounding (not freeform shapes' kind, nor text boxes)
  multiShapeSection(shaped, via) {
    const roundable = (o) => !!shapeCatalog.shapes[o.geom]?.corners || o.geom === "custom";
    const kids = [];
    const kinds = shaped.filter((o) => o.geom !== "custom"), round = shaped.filter(roundable);
    if (kinds.length) {
      const groups = shapeCatalog.groups.map((g) => [g.title, g.shapes]);
      const geom = kinds[0].geom;
      if (!this.mx("geom") && !shapeCatalog.groups.some((g) => g.shapes.includes(geom))) groups.push(["From PowerPoint", [geom]]);
      const ctx = via((o) => o.type === "shape" && !o.textbox && o.geom !== "region" && o.geom !== "custom");
      kids.push(pictureField("Shape", geom, groups.flatMap(([heading, geoms]) => [{ heading },
        ...geoms.map((g) => ({ value: g, label: shapeName(g), picture: () => shapePicture(g) }))]), (v) => ctx.edit("Change shape", (o) => {
        o.geom = v;
        o.adj = {};
        if (!shapeCatalog.shapes[v]?.open) { o.arrow_start = null; o.arrow_end = null; }
      }), { mixed: this.mx("geom") }));
    }
    if (round.length) {
      const ctx = via((o) => o.type === "shape" && roundable(o));
      kids.push(numField("Corner rounding", (round[0].rounding || 0) * 100, "%", (v) => ctx.edit("Corner rounding", (o) => {
        o.rounding = Math.min(Math.max(v, 0), 100) / 100;
        if (!o.rounding) delete o.rounding;
      }), { min: 0, max: 100, step: 5, mixed: this.mx("rounding") }),
      h("p", { class: "hint" }, "Corner rounding: 0% keeps the corners sharp; 100% is as round as the shape allows. "
        + "It goes to the shapes with corners."));
    }
    return kids.length ? section("Shape", kids) : null;
  },
  // Align, distribute and spacing, as in the ribbon's Arrange tab (one object aligns to the page)
  alignSections(n) {
    const b = (cmd, ic) => iconButton(this.app, cmd, ic);
    const align = section(n === 1 ? "Align to page" : "Align", [h("div", { class: "button-row icons" },
      b("alignLeft", "alignLeft"), b("alignCenter", "alignCenter"), b("alignRight", "alignRight"),
      b("alignTop", "alignTop"), b("alignMiddle", "alignMiddle"), b("alignBottom", "alignBottom"))]);
    if (n === 1) return [align];
    return [align,
      section("Distribute", [h("div", { class: "button-row icons" },
        b("distributeLeft", "distLeft"), b("distributeCenter", "distCenter"), b("distributeRight", "distRight"),
        b("distributeTop", "distTop"), b("distributeMiddle", "distMiddle"), b("distributeBottom", "distBottom"))]),
      section("Spacing", [h("div", { class: "row" },
        h("div", { class: "button-row icons" }, b("distributeH", "spaceH"), b("distributeV", "spaceV")), gapField(this.app)),
      h("p", { class: "hint" }, "Equal gaps between neighbours; with a gap set, exactly that gap.")]),
      section("Align to", [alignToField(this.app), h("p", { class: "hint" },
        `Key object: the one that stays put. ${isMac ? "Option" : "Alt"}-click one of the selected objects to make it the key; `
        + "it lasts until the selection changes.")])];
  },
};

// Which tab opens first for each kind of object (until another is chosen)
// The lines and shapes among objects, those inside groups too (not a clipping mask's shape, which
// isn't drawn): what several objects' Style tab works on
function lookTargets(items) {
  const out = [];
  const walk = (list) => {
    for (const it of list) {
      if (it.type === "group") walk(it.clip ? it.items.slice(0, -1) : it.items);
      else if (it.type === "line" || it.type === "shape") out.push(it);
    }
  };
  walk(items);
  return out;
}
// Where several objects' looks differ, by field ("stroke" whether they have a line, "stroke.width"
// its width among those that have one...): what inspector.mx asks
const PART_DEFAULT = { opacity: 1, dash: "solid", dash_spacing: 1, even_dashes: true, cap: "flat", join: "round", width: 1 };
function mixedLooks(lined, filled, headed, shaped, all) {
  const out = new Set();
  const differ = (path, list, get) => {
    if (new Set(list.map((o) => JSON.stringify(get(o) ?? null))).size > 1) out.add(path);
  };
  const parts = (key, list) => {
    differ(key, list, (o) => !!o[key]);
    const have = list.filter((o) => o[key]);
    for (const sub of new Set(have.flatMap((o) => Object.keys(o[key])))) differ(`${key}.${sub}`, have, (o) => o[key][sub] ?? PART_DEFAULT[sub]);
  };
  parts("stroke", lined);
  parts("outline", all);
  differ("fill", filled, (o) => (!o.fill ? "none" : o.fill.gradient ? (o.fill.gradient.type === "radial" ? "radial" : "linear") : "solid"));
  const fills = filled.filter((o) => o.fill);
  for (const sub of ["color", "opacity", "swatch", "gradient"]) differ(`fill.${sub}`, fills, (o) => o.fill[sub] ?? PART_DEFAULT[sub]);
  differ("fill_reach", fills, (o) => o.fill_reach || "middle");
  for (const key of ["arrow_start", "arrow_end"]) {
    differ(key, headed, (o) => o[key]?.type || "none");
    const have = headed.filter((o) => o[key]);
    differ(`${key}.w`, have, (o) => o[key].w || "med");
    differ(`${key}.rounding`, have.filter((o) => ROUNDED_HEADS.includes(o[key].type)), (o) => o[key].rounding || 0);
  }
  differ("object_style", all, (o) => o.object_style || "");
  differ("geom", shaped.filter((o) => o.geom !== "custom"), (o) => o.geom);
  differ("rounding", shaped.filter((o) => shapeCatalog.shapes[o.geom]?.corners || o.geom === "custom"), (o) => o.rounding || 0);
  return out;
}

const DEFAULT_TAB = { shape: "style", textbox: "text", line: "style", picture: "picture", group: "arrange", multi: "arrange",
  region: "style", scalebar: "scalebar", bracket: "bracket" };
function kindKey(it) { return it.geom === "region" ? "region" : it.type === "shape" && it.textbox ? "textbox" : it.type; }

// Field builders ---------------------------------------------------------------------------

const MM_PT = 72 / 25.4;

// Which standard or journal size a page is, if it still has that size
// A journal's panel labels and text rules in words (journals.py): "a, b, c in bold 8 pt Helvetica";
// "Text 5–7 pt; fonts: Helvetica or Arial preferred. Check flags other text."
export function labelLook(l) {
  const letters = ["a", "b", "c"].map((c) => asLabel(c, l)).join(", ");
  return `${letters} in ${l.bold ? "bold " : ""}${fmt(l.size, 1)} pt ${l.font}`;
}
function textRules(t) {
  const sizes = t.min_pt != null && t.max_pt != null ? `${t.about ? "about " : ""}${fmt(t.min_pt, 1)}–${fmt(t.max_pt, 1)} pt`
    : t.min_pt != null ? `at least ${fmt(t.min_pt, 1)} pt` : t.max_pt != null ? `at most ${fmt(t.max_pt, 1)} pt` : "";
  const names = t.fonts?.length > 1 ? `${t.fonts.slice(0, -1).join(", ")} or ${t.fonts.at(-1)}` : t.fonts?.[0];
  const fonts = names ? `${t.fonts_only ? "only " : ""}${names}${t.fonts_only ? "" : " preferred"}` : "";
  if (!sizes && !fonts) return "";
  return `Text${sizes ? ` ${sizes}` : ""}${sizes && fonts ? "; fonts: " : fonts ? " fonts: " : ""}${fonts}. Check flags other text.`;
}
// A journal's line widths, picture resolution and files in words: "Lines 0.5–1.5 pt."
function lineRules(l) {
  const w = l.min_pt != null && l.max_pt != null ? `${l.about ? "about " : ""}${fmt(l.min_pt)}–${fmt(l.max_pt)} pt`
    : l.min_pt != null ? `at least ${fmt(l.min_pt)} pt` : l.max_pt != null ? `at most ${fmt(l.max_pt)} pt` : "";
  return w ? `Lines ${w}; Check flags thinner ones.` : "";
}
function pictureRules(p) {
  const vector = p.vector || [];
  const and = (list) => `${list.slice(0, -1).join(", ")}${list.length > 1 ? " and " : ""}${list.at(-1)}`;
  const each = [["photo", "photos"], ["combination", "photos with text or lines"], ["line_art", "line art"]]
    .filter(([k]) => p[k] && !vector.includes(k)).map(([k, what]) => `${fmt(p[k], 0)} dpi for ${what}`);
  const vec = [vector.includes("line_art") ? "line art as vector files" : "",
    vector.includes("combination") ? "text and lines over photos kept editable" : ""].filter(Boolean);
  const said = [each.length ? `pictures at least ${and(each)}` : "", vec.length ? and(vec) : ""].filter(Boolean).join("; ");
  return said ? `${said[0].toUpperCase()}${said.slice(1)} (a picture's kind is on its Picture tab).` : "";
}
const FORMAT_NAMES = { pdf: "PDF", svg: "SVG", png: "PNG", tiff: "TIFF", jpeg: "JPEG", eps: "EPS", pptx: "PowerPoint" };
function fileRules(e) {
  const list = (e.formats || []).map((f) => FORMAT_NAMES[f]);
  if (!list.length) return "";
  return `Files: ${list.length > 1 ? `${list.slice(0, -1).join(", ")} or ${list.at(-1)}` : list[0]}, in `
    + `${{ rgb: "RGB", rgb_preferred: "RGB (preferred) or CMYK", either: "RGB or CMYK",
      cmyk_preferred: "CMYK (preferred for print) or RGB", cmyk: "CMYK" }[e.colour || "either"]} colour`
    + `${e.max_mb ? `, ${e.firm === false ? "under" : "at most"} ${fmt(e.max_mb, 1)} MB each${e.firm === false ? " where possible" : ""}` : ""}.`;
}
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
// The standard sizes as a list's options in their groups (Paper, Slides, Posters), each with its
// size: len(mm) writes a length in the page units
export function standardOptions(standards = [], len) {
  const groups = [];
  for (const s of standards) {
    let g = groups.find((x) => x.group === s.group);
    if (!g) groups.push((g = { group: s.group, options: [] }));
    g.options.push([s.name, `${s.name} (${len(s.width_mm)} × ${len(s.height_mm)})`]);
  }
  return groups;
}

function digits(u) { return u === "in" || u === "cm" ? 3 : 2; }
function kindName(it) {
  if (it.geom === "region") return "Area fill";
  if (it.type === "picture") return it.equation ? "Equation" : "Picture";
  if (it.type === "line") return `${isCurved(it) ? "Curved " : ""}${it.arrow_start || it.arrow_end ? "arrow" : "line"}`.replace(/^./, (c) => c.toUpperCase());
  if (it.type === "group") return it.clip ? "Clipping mask" : it.grid ? "Grid layout" : it.editing_symbol ? "Symbol (editing)" : "Group";
  if (it.type === "symbol") return "Symbol copy";
  if (it.type === "scalebar") return "Scale bar";
  if (it.type === "bracket") return "Significance bracket";
  if (it.textbox) return "Text box";
  return shapeName(it.geom);
}
// Settings under a heading that folds them away; folded sections stay folded next time
function section(title, children) {
  const folded = () => new Set(inspector.app?.prefs.inspector_closed || []);
  const d = h("details", { class: "section", open: !folded().has(title) }, h("summary", {}, title),
    h("div", { class: "section-body", role: "group", "aria-label": title }, ...children));
  d.addEventListener("toggle", () => {
    const set = folded();
    if (d.open !== set.has(title)) return;   // already as remembered
    if (d.open) set.delete(title); else set.add(title);
    inspector.app.rememberUi({ inspector_closed: [...set] });
  });
  return d;
}
function row(...children) { return h("div", { class: "row" }, ...children); }
// The turn from angle `from` to angle `to`, the short way round (-180 to 180 degrees)
function turnFrom(from, to) { return ((((to - from) % 360) + 540) % 360) - 180; }
const sameAngle = (a, b) => Math.abs(turnFrom(a, b)) < 1e-6;
function label(text, id) { return h("label", { for: id }, text); }

// opts.mixed: the objects selected differ here, so it's blank ("Mixed") until a value is typed
export function numField(text, valuePt, unit, onCommit, opts = {}) {
  const id = `f${++fieldId}`;
  const isLen = unit in { pt: 1, mm: 1, cm: 1, in: 1, px: 1 };
  const shown = isLen ? toUnit(valuePt, unit) : valuePt;
  const input = h("input", { id, type: "number", inputmode: "decimal", value: opts.mixed ? "" : fmt(shown, isLen ? digits(unit) : 2),
    placeholder: opts.mixed ? "Mixed" : null,
    step: opts.step ?? (isLen ? { in: 0.01, pt: 0.5, cm: 0.1, mm: 0.5, px: 1 }[unit] : 1), min: opts.min, max: opts.max,
    "data-bind": opts.bind, "aria-describedby": `${id}-u` });
  input.addEventListener("change", () => {
    const v = parseFloat(input.value);
    if (Number.isNaN(v)) return;
    onCommit(isLen ? fromUnit(v, unit) : v);
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); keepFieldKeys(e); });
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
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); keepFieldKeys(e); });
  return h("div", { class: "field" }, label(text, id), input);
}
function textArea(text, value, onCommit) {
  const id = `f${++fieldId}`;
  const ta = h("textarea", { id, rows: 2 }, value || "");
  ta.addEventListener("change", () => onCommit(ta.value.trim()));
  ta.addEventListener("keydown", keepFieldKeys);
  return h("div", { class: "field" }, label(text, id), ta);
}
// A choice shown as a small picture with its name: pressing it opens a menu with a picture beside
// every choice (contextmenu.js), the current one ticked. options: { value, label, picture (() =>
// an element), disabled (why it's greyed out) } or { heading } over a group. opts.disabled: why
// no choice changes anything yet (greyed out, with the reason under it). Like a select, it has a
// value, and choices (the values it offers)
export function pictureField(text, value, options, onChange, opts = {}) {
  const id = `f${++fieldId}`;
  const choices = options.filter((o) => !o.heading);
  const mixed = !!opts.mixed;   // (the objects selected differ: no picture, "Mixed", nothing ticked)
  const shown = mixed ? { label: "Mixed" } : choices.find((o) => o.value === value) || choices[0];
  const why = opts.disabled ? h("p", { class: "hint why", id: `${id}-why` }, opts.disabled) : null;
  const btn = h("button", { type: "button", id, class: "pic-select", "aria-haspopup": "menu", "aria-disabled": why ? "true" : null,
    "aria-describedby": why ? `${id}-why` : null },
  h("span", { class: "pic" }, shown?.picture?.() || null), h("span", { class: "pic-label" }, shown?.label ?? ""),
  h("span", { class: "pic-arrow", "aria-hidden": "true" }, "▾"));
  btn.value = mixed ? "" : value ?? "";
  btn.choices = choices.map((o) => o.value);
  const open = () => {
    if (why) return;
    const r = btn.getBoundingClientRect();
    contextMenu.show(options.map((o) => (o.heading ? o : { label: o.label, value: o.value, picture: o.picture?.(),
      checked: !mixed && o.value === value, disabled: !!o.disabled, note: o.disabled || null,
      run: () => { if (mixed || o.value !== value) onChange(o.value); } })), r.left, r.bottom + 2, btn, { label: text, focusChecked: true });
  };
  btn.addEventListener("click", open);
  btn.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); open(); }
  });
  return h("div", { class: "field" }, label(text, id), btn, why);
}
// options: [value, label] pairs, or {group, options: [value, label] pairs} for a group with a heading
export function selectField(text, value, options, onChange, opts = {}) {
  const id = `f${++fieldId}`;
  const option = ([v, l]) => h("option", { value: v, selected: v === value ? "selected" : undefined }, l);
  const sel = h("select", { id, disabled: opts.disabled },
    ...options.map((o) => (o.group ? h("optgroup", { label: o.group }, ...o.options.map(option)) : option(o))));
  sel.value = value;
  sel.addEventListener("change", () => onChange(sel.value));
  return h("div", { class: "field" }, label(text, id), sel);
}
// A colour picker with its hex code beside it; either can be edited
// A colour picker with its hex code beside it; either can be edited, which drops a link to a
// swatch. The swatch button picks one of the figure's swatches (and links to it), or adds one.
// onChange(colour, swatch id or null)
// opts.mixed: the objects selected differ, so the hex code is blank ("Mixed")
function colorField(text, value, onChange, swatch = null, opts = {}) {
  const id = `f${++fieldId}`;
  const hex = parseHex(value) || "#000000";
  const picker = h("input", { id, type: "color", value: hex });
  const code = h("input", { id: `${id}-hex`, type: "text", class: "hex", value: opts.mixed ? "" : hex.toUpperCase(), maxlength: 7,
    placeholder: opts.mixed ? "Mixed" : null, spellcheck: "false", autocomplete: "off", "aria-label": `${text} hex code` });
  picker.addEventListener("change", () => { code.value = picker.value.toUpperCase(); onChange(picker.value, null); });
  const commit = () => {
    if (opts.mixed && !code.value.trim()) return;   // (left blank: each keeps its own)
    const v = parseHex(code.value);
    if (!v) {
      announce(`“${code.value}” isn't a hex colour; use 6 digits such as #1A2B3C`);
      code.value = picker.value.toUpperCase();
      return;
    }
    code.value = v.toUpperCase();
    if (v !== picker.value || opts.mixed) { picker.value = v; onChange(v, null); }
  };
  code.addEventListener("change", commit);
  code.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { commit(); code.blur(); }
    keepFieldKeys(e);
  });
  const sw = swatchById(store.doc, swatch);
  const choose = h("button", { type: "button", class: "btn swatch-btn", title: `Swatches for ${text}`,
    "aria-label": `Swatches for ${text}`, "aria-haspopup": "menu" }, icon("swatches"));
  choose.addEventListener("click", () => {
    const r = choose.getBoundingClientRect(), all = store.doc.swatches || [];
    contextMenu.show([
      ...all.map((s) => ({ label: s.name, swatch: s.color, checked: s.id === swatch, run: () => onChange(s.color, s.id) })),
      all.length ? "-" : { label: "No swatches in this figure yet", disabled: true, run: () => {} },
      { label: "Add this colour as a swatch", run: () => onChange(picker.value, inspector.app.addSwatch(picker.value)) },
      { label: "Swatches…", run: () => inspector.app.run("swatches") },
    ], r.left, r.bottom + 2, choose);
  });
  return h("div", { class: "field color" }, label(text, id), h("div", { class: "color-row" }, picker, code, choose),
    sw ? h("div", { class: "swatch-link" }, `Swatch: ${sw.name}`) : null);
}
// Transparency in percent (0 = solid), as PowerPoint shows it; items store opacity
function transparencyField(text, opacity, onCommit, opts = {}) {
  return numField(text, (1 - (opacity ?? 1)) * 100, "%", (v) => onCommit(Math.min(Math.max(1 - v / 100, 0), 1)),
    { min: 0, max: 100, step: 5, ...opts });
}
// White around dark things, black around light ones
function contrastingOutline(it) {
  const main = parseHex(it.type === "line" ? it.stroke?.color : (it.fill?.color || it.stroke?.color)) || "#000000";
  return luminance(main) > 0.4 ? "#000000" : "#ffffff";
}
// opts.mixed: some of the objects selected have it and some don't (a dash in the box)
function checkField(text, checked, onChange, opts = {}) {
  const id = `f${++fieldId}`;
  const input = h("input", { id, type: "checkbox", checked: opts.mixed ? false : checked });
  if (opts.mixed) input.indeterminate = true;
  input.addEventListener("change", () => onChange(input.checked));
  return h("div", { class: "field check" }, input, label(text, id));
}
// options: [value, label] or [value, label, picture]
function radioField(text, value, options, onChange) {
  const name = `r${++fieldId}`;
  return h("fieldset", { class: "radio-group" }, h("legend", {}, text),
    ...options.map(([v, l, picture]) => {
      const id = `${name}-${v}`;
      const input = h("input", { type: "radio", name, id, value: v, checked: v === value });
      input.addEventListener("change", () => { if (input.checked) onChange(v); });
      return h("label", { for: id, class: "radio" }, input, picture ? h("span", { class: "pic" }, picture) : null, h("span", {}, l));
    }));
}
// A command as a small icon button (its name and shortcut in the tooltip)
function iconButton(app, cmd, iconName) {
  const c = app.commands[cmd];
  return button(`${c.label}${c.keys ? ` (${c.keys})` : ""}`, () => app.run(cmd), icon(iconName), "icon-btn");
}
// The gap for spacing objects evenly: blank for "as even as fits", or an exact length
export function gapField(app) {
  const u = app.prefs.units || "cm", id = `f${++fieldId}`, gap = app.prefs.spacing_gap;
  const input = h("input", { id, type: "text", inputmode: "decimal", class: "gap-input", placeholder: "auto",
    value: gap == null ? "" : fmt(toUnit(gap, u), 3), "data-sync": "spacing_gap", "aria-describedby": `${id}-u` });
  input.addEventListener("change", () => {
    const v = parseFloat(input.value);
    const pt = Number.isFinite(v) && v >= 0 ? fromUnit(v, u) : null;
    app.rememberUi({ spacing_gap: pt });
    for (const el of document.querySelectorAll('[data-sync="spacing_gap"]')) el.value = pt == null ? "" : fmt(toUnit(pt, u), 3);
    announce(pt == null ? "Spacing: as even as fits" : `Spacing: ${lengthText(pt, true)} apart`);
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); keepFieldKeys(e); });
  return h("div", { class: "field gap" }, label("Gap", id),
    h("div", { class: "with-unit" }, input, h("span", { class: "unit", id: `${id}-u`, "aria-label": unitName(u) }, UNIT_LABEL[u])));
}
// What aligning and distributing line up with
export function alignToField(app) {
  const f = selectField("Align to", app.alignTo(),
    [["selection", "Selection"], ["key", "Key object"], ["page", "Page"]], (v) => app.setAlignTo(v));
  f.querySelector("select").dataset.sync = "align_to";
  return f;
}
// The View tab's colour vision preview, kept in step with the page's Stop button
export function colourVisionField() {
  const f = selectField("Colour vision", canvas.colourVision || "normal", [["normal", "Normal"],
    ["deuteranopia", "Red-green: deuteranopia"], ["protanopia", "Red-green: protanopia"],
    ["tritanopia", "Blue-yellow: tritanopia"], ["greyscale", "Greyscale"]], (v) => canvas.setColourVision(v));
  const sel = f.querySelector("select");
  document.addEventListener("fa-colour-vision", (e) => { sel.value = e.detail; });
  return f;
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

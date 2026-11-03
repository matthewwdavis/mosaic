// Select Same, as in Illustrator: every object that shares a look with one of the selected
// objects: its fill colour, line colour or width, fill and line together, its text's font, size
// or colour, or its kind. Only the working level is looked at (the page, or the group being
// edited), since a selection stays at one level; locked and hidden objects are left out.

// [what, its name in the menus, its noun for "nothing selected has a ..."]; each is a command,
// selectSameFill and so on (main.js)
export const SAME = [
  ["fill", "Fill colour", "fill"], ["line", "Line colour", "line"], ["width", "Line width", "line"],
  ["fillLine", "Fill and line", "fill or line"], ["font", "Font", "text"], ["size", "Font size", "text"],
  ["textColour", "Text colour", "text"], ["kind", "Kind of object", null]];
export const sameCommand = (what) => `selectSame${what[0].toUpperCase()}${what.slice(1)}`;

const colour = (c) => String(c || "#000000").toLowerCase();
const fillOf = (it) => {
  const f = it.fill, g = f?.gradient;
  if (!f) return "none";
  if (g) return `gradient ${JSON.stringify([g.type, g.angle ?? null, g.center ?? null, g.stops.map((s) => [s.pos, colour(s.color), s.opacity ?? 1])])}`;
  return colour(f.color);
};
const lineOf = (it) => (it.stroke ? colour(it.stroke.color) : "none");
const widthOf = (it) => (it.stroke ? String(Math.round(it.stroke.width * 1000) / 1000) : "none");
const hasLine = (it) => it.type === "line" || (it.type === "shape" && it.geom !== "region");   // an area fill has none
// The text's runs with something in them (a shape's or a text box's)
const runsOf = (it) => (it.text?.paragraphs || []).flatMap((p) => p.runs || []).filter((r) => (r.t || "").length);

function kindOf(it) {
  if (it.type === "picture") return it.equation ? "equation" : it.inset ? "inset" : "picture";
  if (it.type === "line") return it.arrow_start || it.arrow_end ? "arrow" : "line";
  if (it.type === "shape") return it.textbox ? "textbox" : it.geom === "region" ? "region" : `shape ${it.geom}`;
  if (it.type === "group") return it.clip ? "clip" : "group";
  if (it.type === "symbol") return `symbol ${it.symbol}`;
  return it.type;   // scalebar, bracket
}

// What an object has of that look, as strings that match when the same; none if it has nothing
// of it (a picture has no fill or line, a line no fill, a shape without text no font)
export function sameKeys(it, what) {
  switch (what) {
    case "fill": return it.type === "shape" ? [fillOf(it)] : [];
    case "line": return hasLine(it) ? [lineOf(it)] : [];
    case "width": return hasLine(it) ? [widthOf(it)] : [];
    case "fillLine": {
      if (it.type !== "shape" && it.type !== "line") return [];
      const fill = it.type === "shape" ? fillOf(it) : "(a line)";
      return [[fill, hasLine(it) ? lineOf(it) : "", hasLine(it) ? widthOf(it) : "", JSON.stringify(it.stroke?.dash ?? null)].join(" | ")];
    }
    case "font": return runsOf(it).map((r) => r.font || "Helvetica");
    case "size": return runsOf(it).map((r) => String(Math.round((r.size ?? 6) * 100) / 100));
    case "textColour": return runsOf(it).map((r) => colour(r.color));
    case "kind": return [kindOf(it)];
    default: return [];
  }
}

// The ids of the objects (of `items`, in their order) sharing that look with one of `selected`,
// or null if none of `selected` has it
export function sameAs(items, selected, what) {
  const want = new Set(selected.flatMap((it) => sameKeys(it, what)));
  if (!want.size) return null;
  return items.filter((it) => !it.locked && !it.hidden && sameKeys(it, what).some((k) => want.has(k))).map((it) => it.id);
}

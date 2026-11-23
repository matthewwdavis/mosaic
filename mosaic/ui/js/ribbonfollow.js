// Which ribbon tab the selection shows: the rule prose follows too. Selecting something shows its
// tab; clicking the empty page goes back to Home; a tab picked by hand stays until something else
// is selected (or typed in). Each part has a Settings switch: text_home_tab (text: Home),
// several_arrange_tab (several objects: Arrange), object_tabs (one object's own tab, and Home
// for the empty page). panels.followSelection applies it.
//
// | Selected                                                        | Tab     |
// |-----------------------------------------------------------------|---------|
// | nothing (the empty page clicked)                                | Home    |
// | a text box or panel label, or typing in any text               | Home    |
// | a shape, an area fill, a line or arrow                          | Home    |
// | a picture (plot or photo) or an equation                        | Figure  |
// | a scale bar, a significance bracket, a symbol                   | Figure  |
// | a zoom inset's box or one of its lines                          | Figure  |
// | a group                                                         | Arrange |
// | a clipping mask                                                 | Combine |
// | two or more objects                                             | Arrange |

export const TAB_RULES = [
  ["nothing (the empty page clicked)", "home"],
  ["a text box or panel label, or typing in any text", "home"],
  ["a shape, an area fill, a line or an arrow", "home"],
  ["a picture (a plot or a photo) or an equation", "figure"],
  ["a scale bar, a significance bracket or a symbol", "figure"],
  ["a zoom inset's box or one of its lines", "figure"],
  ["a group", "arrange"],
  ["a clipping mask", "combine"],
  ["two or more objects", "arrange"],
];

// The tab one object calls for
export function objectTab(it) {
  if (!it) return "home";
  if (it.type === "group") return it.clip ? "combine" : "arrange";
  if (["picture", "scalebar", "bracket", "symbol"].includes(it.type)) return "figure";
  if ((it.type === "shape" && it.zoom) || (it.type === "line" && it.zoomline)) return "figure";
  return "home";
}

// The tab for what's selected (sel: the objects; typing: text being typed in), or null to leave
// the tab alone (that part's Settings switch is off)
export function selectionTab(sel, { typing = false, prefs = {} } = {}) {
  const on = (key) => prefs[key] !== false;
  if (typing) return on("text_home_tab") ? "home" : null;
  if (sel.length > 1) return on("several_arrange_tab") ? "arrange" : null;
  if (sel.length === 1 && sel[0].type === "shape" && sel[0].textbox) return on("text_home_tab") ? "home" : null;
  if (!on("object_tabs")) return null;
  return sel.length ? objectTab(sel[0]) : "home";
}

// What the selection is, as followSelection compares it: the tab moves only when this changes
export const selectionKey = (ids, typingId) => `${typingId ? `typing:${typingId}` : ""}|${ids.join(",")}`;

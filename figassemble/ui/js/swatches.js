// Swatches: named colours saved in the figure (doc.swatches: [{id, name, color}]). A colour picked
// from one keeps a link to it (swatch: id beside its color); editing the swatch recolours every
// colour linked to it, and typing a colour by hand drops the link. The engine draws `color` only.

// Ready-made palettes, safe for colour-blind readers (Okabe & Ito 2008; Paul Tol's schemes) and
// viridis steps for ordered values
export const PALETTES = [
  { name: "Okabe-Ito", colours: [["Black", "#000000"], ["Orange", "#e69f00"], ["Sky blue", "#56b4e9"],
    ["Bluish green", "#009e73"], ["Yellow", "#f0e442"], ["Blue", "#0072b2"], ["Vermillion", "#d55e00"],
    ["Reddish purple", "#cc79a7"]] },
  { name: "Tol bright", colours: [["Blue", "#4477aa"], ["Red", "#ee6677"], ["Green", "#228833"], ["Yellow", "#ccbb44"],
    ["Cyan", "#66ccee"], ["Purple", "#aa3377"], ["Grey", "#bbbbbb"]] },
  { name: "Tol muted", colours: [["Indigo", "#332288"], ["Cyan", "#88ccee"], ["Teal", "#44aa99"], ["Green", "#117733"],
    ["Olive", "#999933"], ["Sand", "#ddcc77"], ["Rose", "#cc6677"], ["Wine", "#882255"], ["Purple", "#aa4499"],
    ["Pale grey", "#dddddd"]] },
  { name: "Tol vibrant", colours: [["Orange", "#ee7733"], ["Blue", "#0077bb"], ["Cyan", "#33bbee"], ["Magenta", "#ee3377"],
    ["Red", "#cc3311"], ["Teal", "#009988"], ["Grey", "#bbbbbb"]] },
  { name: "Viridis (5 steps)", colours: [["Viridis 1", "#440154"], ["Viridis 2", "#3b528b"], ["Viridis 3", "#21918c"],
    ["Viridis 4", "#5ec962"], ["Viridis 5", "#fde725"]] },
];

// Every colour in the document that can be linked to a swatch: objects with a `color` (and maybe
// a `swatch`): lines, fills and their gradient stops, outlines, text and text styles
export function colourHolders(doc) {
  const out = [];
  const walk = (items) => {
    for (const it of items) {
      if (it.type === "group") walk(it.items);
      for (const k of ["stroke", "fill", "outline"]) {
        if (!it[k]) continue;
        if (!it[k].gradient) out.push(it[k]);   // a gradient's colours are its stops'
        for (const stop of it[k].gradient?.stops || []) out.push(stop);
      }
      for (const p of it.text?.paragraphs || []) for (const r of p.runs || []) out.push(r);
      if (it.type === "scalebar") out.push(it);
      if (it.border) out.push(it.border);   // a picture's border
    }
  };
  for (const pg of doc.pages || []) walk(pg.items);
  for (const st of doc.text_styles || []) out.push(st);   // text styles' colours too
  return out;
}

// A colour object with its swatch link set (or dropped)
export function linked(holder, swatch) {
  if (swatch) holder.swatch = swatch;
  else delete holder.swatch;
  return holder;
}

export function swatchById(doc, id) {
  return id ? (doc.swatches || []).find((s) => s.id === id) || null : null;
}

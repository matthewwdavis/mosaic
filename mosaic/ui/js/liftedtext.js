// Dangerous mode (View ▸ Dangerous Mode, off whenever mosaic opens): a double-click on the text
// of a placed PDF or SVG lifts that text out of the plot. It becomes an ordinary text box in the
// same font, size, colour, angle and place, editable and movable like any other, and the plot is
// drawn without it from then on (plottext.py makes the copy without it; the file placed stays in
// the document as it was).
// - The picture keeps lifted_text: {hidden: [{id, box, text, size, angle, mid, font, bold,
//   italic}], dropped: [{text, box_text}]}: each lifted text, as found in the file (to find it
//   again when R saves the file again), and edits dropped because the text wasn't there.
// - Its box keeps lifted: {picture, of, seen}: the picture and lifted text it came from, and the
//   picture's frame, crop and turn when last looked at, so it moves, scales and turns with it.
// - Deleting a box leaves its text out of the plot; Put Back in Plot puts it back, and Restore
//   Plot Text puts back every text lifted from a picture.

import { rpc } from "./api.js";
import { findItem, store } from "./store.js";
import { announce, apply, frameMatrix, invert, uid } from "./util.js";

const texts = new Map();    // [variant, page] -> Promise of the file's texts {kind, texts}
const textsDone = new Map(); // ... and the texts themselves once they've come
const copies = new Map();   // a picture's copy key -> {variants, missing}, or a Promise while it's made

export const hiddenOf = (it) => it?.lifted_text?.hidden || [];
const flat = (items, out = []) => {
  for (const it of items) {
    out.push(it);
    if (it.type === "group") flat(it.items, out);
  }
  return out;
};
const sourceSize = (pic, asset) => (asset.page_sizes && asset.page_sizes[pic.page_index || 0]) || asset.size_pt;
export const isPlot = (asset) => !!asset && ["pdf", "svg"].some((k) => asset.variants?.[k]);

// A picture's place on the page and back: its file's points <-> the page (crop, frame, turn)
function pictureMatrix(pic, asset) {
  const [sw, sh] = sourceSize(pic, asset), [l, t, r, b] = pic.crop || [0, 0, 0, 0];
  const sx = pic.frame[2] / Math.max(sw * (1 - l - r), 1e-9), sy = pic.frame[3] / Math.max(sh * (1 - t - b), 1e-9);
  const m = frameMatrix(pic.frame, pic.rot || 0, pic.flip_h, pic.flip_v);
  return { sx, sy, toPage: (x, y) => apply(m, (x - l * sw) * sx, (y - t * sh) * sy),
    toSource: (x, y) => { const [u, v] = apply(invert(m), x, y); return [u / sx + l * sw, v / sy + t * sh]; } };
}
const geomOf = (pic) => [...pic.frame, ...(pic.crop || [0, 0, 0, 0]), pic.rot || 0];

// The file's texts, from the copy on screen (R lays out a plot's PDF and SVG a little apart)
const textsKey = (asset, pageIndex, prefer) =>
  JSON.stringify([(asset.variants[prefer] || asset.variants.svg || asset.variants.pdf)?.sha256, pageIndex, prefer]);
export function plotTexts(asset, pageIndex, prefer) {
  const key = textsKey(asset, pageIndex, prefer);
  if (!texts.has(key)) {
    texts.set(key, rpc("plot_texts", asset, pageIndex, prefer).catch(() => ({ kind: null, texts: [] }))
      .then((found) => { textsDone.set(key, found); return found; }));
  }
  return texts.get(key);
}
// ... now, if they've come (for drawing)
export const plotTextsNow = (asset, pageIndex, prefer) => textsDone.get(textsKey(asset, pageIndex, prefer)) || null;
// A text's box on the page (its four corners)
export function quadOnPage(pic, asset, t) {
  const { toPage } = pictureMatrix(pic, asset);
  return t.quad.map(([x, y]) => toPage(x, y));
}
// A file's text that's been lifted already (by this picture), so not offered again: found as the
// engine finds it again (plottext.match), so a text R moved a little when it saved the file again
// still counts
const words = (text) => text.replaceAll("\u2212", "-").replaceAll("\u00a0", " ").replace(/\s+/g, " ").trim();
const sameText = (d, t) => words(d.text) === words(t.text) && Math.abs(((d.angle - t.angle + 540) % 360) - 180) <= 2
  && Math.abs(d.size - t.size) <= Math.max(0.6, 0.12 * d.size)
  && Math.hypot(d.mid[0] - t.mid[0], d.mid[1] - t.mid[1]) <= Math.max(1.5, 0.5 * d.size);
export const isLifted = (pic, t) => hiddenOf(pic).some((d) => sameText(d, t));

// The copies a picture is drawn from: its own, or (with texts lifted) the engine's copies without
// them once they're made; `ready` is called when a copy arrives
export function shownVariants(pic, asset, ready) {
  const hidden = hiddenOf(pic);
  if (!hidden.length || !isPlot(asset)) return asset.variants;
  const key = JSON.stringify([Object.values(asset.variants).map((v) => v.sha256), pic.page_index || 0,
    hidden.map((d) => [d.text, d.size, d.angle, d.mid])]);
  const got = copies.get(key);
  if (got && !(got instanceof Promise)) return { ...asset.variants, ...got.variants };
  if (!got) {
    copies.set(key, rpc("lifted_copy", asset, pic.page_index || 0, hidden).then((res) => {
      copies.set(key, res);
      ready?.();
    }, (err) => { copies.delete(key); console.error(err); }));
  }
  return asset.variants;   // (until the copy is made)
}

// The text under a page point on a picture (in dangerous mode), or null
export async function textAt(pic, p, prefer) {
  const asset = store.doc.assets[pic.asset];
  if (!isPlot(asset)) return null;
  const found = await plotTexts(asset, pic.page_index || 0, prefer);
  const { toSource } = pictureMatrix(pic, asset);
  const q = toSource(...p);
  const pad = 1;   // points of the file round each text that still hit it
  const hits = (found.texts || []).filter((t) => !isLifted(pic, t) && inQuad(q, t.quad, pad));
  hits.sort((a, b) => a.width * a.size - b.width * b.size);
  return hits[0] || null;
}
function inQuad([x, y], quad, pad) {
  // The quad's own axes: along its baseline and up from it
  const [a, b, , d] = quad;
  const ux = [b[0] - a[0], b[1] - a[1]], uy = [d[0] - a[0], d[1] - a[1]];
  const lx = Math.hypot(...ux) || 1e-9, ly = Math.hypot(...uy) || 1e-9;
  const px = ((x - a[0]) * ux[0] + (y - a[1]) * ux[1]) / lx, py = ((x - a[0]) * uy[0] + (y - a[1]) * uy[1]) / ly;
  return px >= -pad && px <= lx + pad && py >= -pad && py <= ly + pad;
}

// Lift a text out of a picture: its box goes just above the picture, selected and being edited
export async function lift(pic, t, startEdit) {
  const asset = store.doc.assets[pic.asset];
  if (pic.flip_h || pic.flip_v) {
    announce("This picture is flipped, so its text would read backwards: turn the flip off to lift its text out");
    return null;
  }
  const { sx, sy, toPage } = pictureMatrix(pic, asset);
  const { box, descriptor } = await rpc("lift_plot_text", t, sy);
  const [fx, fy, fw, fh] = box.frame;
  const [cx, cy] = toPage(fx + fw / 2, fy + fh / 2);
  const w = fw * sx, h = fh * sy;
  const id = uid("it"), of = uid("lt");
  const item = { id, type: "shape", geom: "rect", textbox: true, stroke: null, fill: null,
    frame: [cx - w / 2, cy - h / 2, w, h], rot: (((box.rot + (pic.rot || 0)) % 360) + 360) % 360,
    text: { paragraphs: [{ align: box.align, runs: [{ ...box.run, size: box.run.size * sy }] }], insets: [0, 0, 0, 0],
      wrap: false, anchor: "t", autofit: "none" },
    lifted: { picture: pic.id, of, seen: geomOf(pic) } };
  store.update("Lift text out of plot", (doc) => {
    const here = store.container(doc), at = here.findIndex((it) => it.id === pic.id);
    const o = here[at];
    o.lifted_text = { ...(o.lifted_text || {}), hidden: [...hiddenOf(o), { ...descriptor, id: of, box: id }] };
    here.splice(at + 1, 0, item);
  }, { select: [id] });
  startEdit?.(id);
  announce(`Lifted “${t.text}” out of ${asset.name}: it's a text box now. Put Back in Plot (its menu) undoes it`);
  return id;
}

// After every change: lifted boxes go with their pictures (moved, resized, cropped or turned),
// and a box whose picture is gone is an ordinary text box
export function followLifted(items, assets) {
  const all = flat(items), byId = new Map(all.map((it) => [it.id, it]));
  for (const box of all.filter((it) => it.lifted)) {
    const pic = byId.get(box.lifted.picture), asset = pic?.type === "picture" && assets[pic.asset];
    if (!asset || !hiddenOf(pic).some((d) => d.id === box.lifted.of)) { delete box.lifted; continue; }
    const geom = geomOf(pic), seen = box.lifted.seen;
    if (seen && geom.some((v, i) => Math.abs(v - seen[i]) > 1e-9)) {
      const was = pictureMatrix({ ...pic, frame: seen.slice(0, 4), crop: seen.slice(4, 8), rot: seen[8] }, asset);
      const now = pictureMatrix(pic, asset);
      const [x, y, w, h] = box.frame;
      const [cx, cy] = now.toPage(...was.toSource(x + w / 2, y + h / 2));
      const kx = now.sx / was.sx, ky = now.sy / was.sy;
      box.frame = [cx - (w * kx) / 2, cy - (h * ky) / 2, w * kx, h * ky];
      box.rot = ((((box.rot || 0) + (pic.rot || 0) - seen[8]) % 360) + 360) % 360;
      if (Math.abs(ky - 1) > 1e-9) {
        for (const para of box.text?.paragraphs || []) for (const run of para.runs || []) if (run.size) run.size *= ky;
      }
    }
    box.lifted.seen = geom;
  }
}

// Copied objects: a box copied with its picture belongs to the copy; a picture copied without
// the boxes of texts it lifted shows those texts again (its copy has no boxes for them), but
// keeps out those whose boxes were deleted
export function remapCopies(copies, ids, doc) {
  const live = new Set(flat(doc.pages.flatMap((p) => p.items)).map((it) => it.id));
  for (const it of flat(copies)) {
    if (it.lifted) {
      if (ids.has(it.lifted.picture)) it.lifted = { ...it.lifted, picture: ids.get(it.lifted.picture) };
      else delete it.lifted;
    }
    if (it.type === "picture" && hiddenOf(it).length) {
      const hidden = hiddenOf(it).filter((d) => ids.has(d.box) || !live.has(d.box)).map((d) => (ids.has(d.box) ? { ...d, box: ids.get(d.box) } : d));
      it.lifted_text = { ...it.lifted_text, hidden };
    }
  }
}

// Put lifted texts back into a picture's plot (all of them, or those listed), deleting their boxes
export function putBack(picId, which = null, label = "Put text back in plot") {
  store.update(label, (doc) => {
    const items = doc.pages[store.pageIndex].items, pic = findItem(items, picId);
    if (!pic) return;
    const going = hiddenOf(pic).filter((d) => !which || which.includes(d.id));
    const boxes = new Set(going.map((d) => d.box));
    pic.lifted_text = { ...pic.lifted_text, hidden: hiddenOf(pic).filter((d) => !going.includes(d)) };
    if (!pic.lifted_text.hidden.length && !pic.lifted_text.dropped?.length) delete pic.lifted_text;
    const prune = (list) => {
      for (let i = list.length - 1; i >= 0; i--) {
        if (boxes.has(list[i].id) && list[i].lifted) list.splice(i, 1);
        else if (list[i].type === "group") prune(list[i].items);
      }
    };
    prune(items);
  }, { select: [picId] });
}
// A lifted box's picture and its entry, if it has both
export function liftedFrom(box) {
  const pic = box?.lifted && store.item(box.lifted.picture);
  return pic && hiddenOf(pic).some((d) => d.id === box.lifted.of) ? pic : null;
}

// When R saves a picture's file again: which of the texts lifted from each picture of an asset
// are still in the new file. The picture id -> the ids of those that aren't
export async function lostAfterUpdate(doc, assetId, asset) {
  const out = {};
  for (const pic of flat(doc.pages.flatMap((p) => p.items))) {
    if (pic.type !== "picture" || pic.asset !== assetId || !hiddenOf(pic).length || !isPlot(asset)) continue;
    try {
      const res = await rpc("lifted_copy", asset, pic.page_index || 0, hiddenOf(pic));
      const kinds = Object.values(res.missing || {});
      const lost = hiddenOf(pic).filter((d) => kinds.length && kinds.every((ids) => ids.includes(d.id))).map((d) => d.id);
      if (lost.length) out[pic.id] = lost;
    } catch (err) { console.error(err); }
  }
  return out;
}
// ... and dropping those: their boxes go, and the picture notes what each said (Check lists them)
export function dropLost(doc, lost) {
  const all = flat(doc.pages.flatMap((p) => p.items)), dropped = [];
  for (const [picId, ids] of Object.entries(lost)) {
    const pic = all.find((it) => it.id === picId);
    if (!pic) continue;
    const going = hiddenOf(pic).filter((d) => ids.includes(d.id));
    const notes = going.map((d) => {
      const box = all.find((it) => it.id === d.box && it.lifted);
      return { text: d.text, box_text: box ? (box.text?.paragraphs || []).map((p) => (p.runs || []).map((r) => r.t).join("")).join("\n") : "" };
    });
    pic.lifted_text = { hidden: hiddenOf(pic).filter((d) => !ids.includes(d.id)), dropped: [...(pic.lifted_text?.dropped || []), ...notes] };
    const boxes = new Set(going.map((d) => d.box));
    for (const page of doc.pages) {
      const prune = (list) => {
        for (let i = list.length - 1; i >= 0; i--) {
          if (boxes.has(list[i].id) && list[i].lifted) list.splice(i, 1);
          else if (list[i].type === "group") prune(list[i].items);
        }
      };
      prune(page.items);
    }
    dropped.push(...notes);
  }
  return dropped;
}

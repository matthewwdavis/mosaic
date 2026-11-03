// The Objects list as a tree, and moving objects through it: the page's objects front to back,
// and under each open group its parts, one level in. Dragging rows (or Option+arrow keys) moves
// objects to another place in the stacking order, into a group or out of one, or onto another
// page (panels.js shows the list; listdrag.js does the dragging).
// - A place is {path, behind: id} (just behind that object, among the parts of the group the path
//   of group ids leads to from the page), {path, front: true} (in front of all of them) or
//   {path, back: true} (behind all of them).
// - A clipping mask's shape stays its top part: nothing goes in front of it, and it doesn't move.
// - A symbol being edited in place takes only what symbols can hold; a grid layout takes no
//   attached panel labels (they stay outside, with their panels, as when the grid was made).
// - A group a move leaves empty goes, as when leaving one; a symbol being edited stays.
// - Objects moved to another page go in front of everything there, where they were on the page.
//   Panel labels and line ends attached to objects that stay behind let go.
import { canHold } from "./symbols.js";

// A clipping mask's shape: its group's top part (when there's something for it to clip)
export const isMask = (it, group) => !!group?.clip && group.items.length > 1 && group.items[group.items.length - 1] === it;

// The rows, front to back: {it, depth, path (the ids of the groups it's in), parent, open, mask}
export function treeRows(items, isOpen) {
  const rows = [];
  const walk = (list, path, parent) => {
    for (let i = list.length - 1; i >= 0; i--) {
      const it = list[i], open = it.type === "group" && isOpen(it);
      rows.push({ it, depth: path.length, path, parent, open, mask: isMask(it, parent) });
      if (open) walk(it.items, [...path, it.id], it);
    }
  };
  walk(items, [], null);
  return rows;
}

// The parts a path leads to: the page's objects, or a group's (null if it's gone)
export function containerAt(items, path) {
  let list = items, group = null;
  for (const id of path) {
    group = list.find((it) => it.id === id && it.type === "group");
    if (!group) return null;
    list = group.items;
  }
  return { list, group };
}

// Where an object is: the list it's in, its group and the path to it
export function locate(items, id, path = [], group = null) {
  for (const it of items) {
    if (it.id === id) return { it, list: items, group, path };
    if (it.type === "group") {
      const f = locate(it.items, id, [...path, it.id], it);
      if (f) return f;
    }
  }
  return null;
}

// Whether a group (null: the page) takes these objects
export function accepts(group, moving) {
  if (!group) return true;
  if (group.editing_symbol && !moving.every(canHold)) return false;
  if (group.grid && moving.some((it) => it.attach)) return false;
  return true;
}

// The objects to move, back to front as they're stacked (a clipping mask's shape stays)
function gather(items, ids) {
  const want = new Set(ids), out = [];
  const walk = (list, group, path) => list.forEach((it) => {
    if (want.has(it.id)) { if (!isMask(it, group)) out.push({ it, list, group, path }); return; }
    if (it.type === "group") walk(it.items, it, [...path, it.id]);
  });
  walk(items, null, []);
  return out;
}

// Take them out of their lists, noting the groups that leaves empty
function takeOut(found) {
  const emptied = new Set();
  for (const f of found) {
    f.list.splice(f.list.indexOf(f.it), 1);
    if (f.group && !f.group.items.length) emptied.add(f.group);
  }
  return emptied;
}
// Groups left empty go (and any group that leaves empty, up), once the moved objects are in
function prune(items, emptied) {
  const walk = (list, group) => {
    for (let i = list.length - 1; i >= 0; i--) {
      const it = list[i];
      if (it.type !== "group") continue;
      walk(it.items, it);
      if (!it.items.length && emptied.has(it) && !it.editing_symbol) {
        list.splice(i, 1);
        if (group && !group.items.length) emptied.add(group);
      }
    }
  };
  walk(items, null);
}

// Whether objects can go to a place: it's there, it takes them, and it isn't inside them
export function canMove(items, ids, place) {
  const found = gather(items, ids), c = containerAt(items, place.path);
  if (!found.length || !c) return false;
  if (place.path.some((id) => found.some((f) => f.it.id === id))) return false;
  if (place.behind && (!c.list.some((it) => it.id === place.behind) || found.some((f) => f.it.id === place.behind))) return false;
  return accepts(c.group, found.map((f) => f.it));
}

// Move objects (by id; their stacking among themselves kept) to a place on their page. Returns
// the objects moved, or null when they can't go there
export function moveItems(items, ids, place) {
  if (!canMove(items, ids, place)) return null;
  const found = gather(items, ids), { list, group } = containerAt(items, place.path);
  const emptied = takeOut(found);
  let at = place.front ? list.length : place.back ? 0 : list.findIndex((it) => it.id === place.behind);
  if (at < 0) at = list.length;
  if (group?.clip && list.length) at = Math.min(at, list.length - 1);   // the mask's shape stays on top
  const moved = found.map((f) => f.it);
  list.splice(at, 0, ...moved);
  prune(items, emptied);
  return moved;
}

// Move objects to the front of another page, where they were on the page
export function moveToPage(doc, from, to, ids) {
  if (from === to || !doc.pages[to]) return null;
  const found = gather(doc.pages[from].items, ids);
  if (!found.length) return null;
  prune(doc.pages[from].items, takeOut(found));
  const moved = found.map((f) => f.it), kept = new Set();
  const collect = (it) => { kept.add(it.id); if (it.type === "group") it.items.forEach(collect); };
  moved.forEach(collect);
  const letGo = (it) => {
    if (it.attach && !kept.has(it.attach.to)) delete it.attach;
    for (const k of ["start_link", "end_link"]) if (it[k] && !kept.has(it[k].item)) delete it[k];
    if (it.type === "group") it.items.forEach(letGo);
  };
  moved.forEach(letGo);
  doc.pages[to].items.push(...moved);
  return moved;
}

// The places a gap between two rows of the list can stand for, one for each depth from the row
// below's to one inside the row above (when that's an open group): just behind the row above,
// or behind the group it's in at that depth, or in front of the open group's parts. `rows` are
// the rows left once the ones being moved (and their parts) are taken out.
export function slotPlaces(items, rows, k, moving) {
  const a = rows[k - 1], b = rows[k];
  if (!a) return [{ depth: 0, place: { path: [], front: true } }];
  const out = [];
  for (let d = b ? b.depth : 0; d <= a.depth + (a.open ? 1 : 0); d++) {
    let place;
    if (d > a.depth) {
      if (a.it.clip && a.it.items.length) continue;   // in front of a clipping mask's shape
      place = { path: [...a.path, a.it.id], front: true };
    } else place = { path: a.path.slice(0, d), behind: d === a.depth ? a.it.id : a.path[d] };
    const c = containerAt(items, place.path);
    if (c && accepts(c.group, moving)) out.push({ depth: d, place });
  }
  return out;
}

// Into a closed group, by dropping onto its row: in front of its parts (behind a mask's shape)
export function intoPlace(row, moving) {
  if (row.it.type !== "group" || row.open || !accepts(row.it, moving)) return null;
  return { path: [...row.path, row.it.id], front: true };
}

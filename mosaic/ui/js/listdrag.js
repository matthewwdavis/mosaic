// Dragging rows of a list to move them, as in the Finder: the row being dragged follows the
// pointer and the other rows slide apart to make room where it would go. The Pages and Objects
// lists use it (panels.js). The owner says what a press drags and where each gap between the rows
// left would put it (in a tree, one place for each depth the gap can be at, chosen by how far
// across the pointer goes), hears whenever that changes (so the page can show the new order
// meanwhile), and is told on letting go, or on cancelling: Escape, or letting go away from the
// list and from anything else that takes the rows (a page in the Pages list).
// - A row the dragged rows can go into (a closed group) takes them while held over its middle,
//   and opens after a moment, so they can go anywhere among its parts.
// - Near the top or bottom of the list, it scrolls.
// The owner: {rows: selector, scroller, start(row) -> {row, depth, count} | null, places(rows) ->
// [[{depth, place}] for each gap], into(row) -> place | null, open(row) -> bool, indent(depth) -> px,
// outside(element) -> {el, target} | null, preview(target), drop(target), cancel()}
import { isMac } from "./util.js";

const START = 4;      // px the pointer moves before a press becomes a drag
const EDGE = 28;      // px from the list's top or bottom edge where it scrolls
const SPRING = 700;   // ms over a closed group before it opens

const keyOf = (t) => (t ? JSON.stringify([t.place ?? null, t.outside ?? null]) : "");

export function listDrag(list, owner) {
  let press = null, d = null;

  list.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || (isMac && e.ctrlKey) || press || d) return;   // Control-click is a right-click on a Mac
    const row = e.target.closest(owner.rows);
    if (!row || !list.contains(row) || e.target.closest("button, input, .twisty")) return;
    const r = row.getBoundingClientRect();
    press = { row, x: e.clientX, y: e.clientY, id: e.pointerId, dy: e.clientY - r.top, h: r.height };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", up, true);
    window.addEventListener("pointercancel", cancel, true);
  });

  function move(e) {
    if (!press || e.pointerId !== press.id) return;
    if (!d) {
      if (Math.hypot(e.clientX - press.x, e.clientY - press.y) < START) return;
      if (!begin()) { stop(); return; }
    }
    e.preventDefault();
    d.last = e;
    track(e);
  }

  function begin() {
    const got = owner.start(press.row);   // may draw the list again, with the dragged rows hidden
    if (!got?.row) return false;
    const lr = list.getBoundingClientRect();
    d = { h: press.h, depth0: got.depth || 0, depth: got.depth || 0, target: null, gap: null };   // (the pressed row is hidden now)
    // The row in hand: a copy of the pressed one, over everything
    const copy = got.row.cloneNode(true);
    copy.removeAttribute("id");
    copy.classList.remove("drag-hidden");
    if (got.count > 1) copy.append(Object.assign(document.createElement("span"), { className: "drag-count", textContent: `+${got.count - 1}` }));
    d.held = document.createElement("ul");
    d.held.className = `${list.className} drag-held`;
    d.held.setAttribute("aria-hidden", "true");
    d.held.append(copy);
    d.held.style.width = `${lr.width}px`;
    d.held.style.left = `${lr.left}px`;
    document.body.append(d.held);
    document.body.classList.add("list-dragging");
    window.addEventListener("keydown", key, true);
    try { list.setPointerCapture(press.id); } catch { /* a synthetic pointer */ }
    measure();
    // The gap starts where the pressed row was
    d.gap = d.rows.filter((el) => el.compareDocumentPosition(got.row) & Node.DOCUMENT_POSITION_FOLLOWING).length;
    d.raf = requestAnimationFrame(scroll);
    return true;
  }

  // The rows left, at their places with no gap (offsetTop isn't moved by the sliding), and where
  // each gap between them would put the dragged rows
  function measure() {
    d.rows = [...list.querySelectorAll(owner.rows)].filter((el) => !el.classList.contains("drag-hidden"));
    d.tops = d.rows.map((el) => el.offsetTop);
    d.heights = d.rows.map((el) => el.offsetHeight);
    d.end = d.rows.length ? d.tops[d.rows.length - 1] + d.heights[d.rows.length - 1] : 0;
    d.places = owner.places(d.rows);
    d.into = d.rows.map((el) => owner.into?.(el) || null);
    list.style.paddingBottom = `${d.h}px`;   // room for the gap below the last row
    // Rows drawn again slide from where they are, not from the top
    list.classList.add("drag-instant");
    requestAnimationFrame(() => requestAnimationFrame(() => list.classList.remove("drag-instant")));
  }

  function track(e) {
    const lr = list.getBoundingClientRect(), sr = (owner.scroller || list).getBoundingClientRect();
    const over = e.clientX >= sr.left && e.clientX <= sr.right && e.clientY >= sr.top && e.clientY <= sr.bottom;
    let target = null, gap = null, into = null;
    if (over) {
      const yc = e.clientY - press.dy + d.h / 2 - lr.top;   // the middle of the row in hand, in the list
      // Over the middle of a closed group: into it (the gap stays where it was)
      d.into.forEach((place, j) => {
        const c = d.tops[j] + d.h / 2;
        if (place && into === null && yc > c + d.heights[j] * 0.25 && yc < c + d.heights[j] * 0.75) into = j;
      });
      if (into !== null) {
        target = { place: d.into[into] };
        gap = d.gap;
      } else {
        // Otherwise the nearest gap that takes them, at the depth nearest where the pointer has
        // taken the row across
        let best = null;
        d.places.forEach((opts, k) => {
          if (!opts.length) return;
          const dist = Math.abs(yc - ((k < d.rows.length ? d.tops[k] : d.end) + d.h / 2));
          if (!best || dist < best.dist) best = { k, dist };
        });
        if (best) {
          gap = best.k;
          const want = (owner.indent?.(d.depth0) || 0) + (e.clientX - press.x), at = (o) => Math.abs((owner.indent?.(o.depth) || 0) - want);
          const pick = d.places[gap].reduce((a, o) => (at(o) < at(a) ? o : a));
          d.depth = pick.depth;
          target = { place: pick.place };
        }
      }
    } else if (owner.outside) {
      const el = document.elementFromPoint(e.clientX, e.clientY), out = el && owner.outside(el);
      if (out) target = { outside: out.target, el: out.el };
    }
    d.gap = gap;
    d.rows.forEach((el, k) => {
      el.style.transform = gap !== null && k >= gap ? `translateY(${d.h}px)` : "";
      el.classList.toggle("drop-into", k === into);
    });
    if (d.outEl && d.outEl !== target?.el) d.outEl.classList.remove("drop-target");
    d.outEl = target?.el || null;
    d.outEl?.classList.add("drop-target");
    // The row in hand: over the list, at its place's indent; elsewhere, with the pointer
    const copy = d.held.firstChild;
    copy.style.setProperty("--depth", d.depth);
    d.held.style.left = `${over ? lr.left : e.clientX - (press.x - lr.left)}px`;
    d.held.style.top = `${e.clientY - press.dy}px`;
    d.held.classList.toggle("away", !over);
    spring(into);
    if (keyOf(target) !== keyOf(d.target)) {
      d.target = target;
      owner.preview?.(target);
    }
  }

  // A closed group held over for a moment opens
  function spring(into) {
    const el = into === null ? null : d.rows[into];
    if (el === d.springEl) return;
    clearTimeout(d.spring);
    d.springEl = el;
    if (!el) return;
    d.spring = setTimeout(() => {
      if (!d || d.springEl !== el || !owner.open?.(el)) return;
      d.springEl = null;
      measure();
      track(d.last);
    }, SPRING);
  }

  function scroll() {
    if (!d) return;
    const sc = owner.scroller || list, r = sc.getBoundingClientRect(), e = d.last;
    let v = 0;
    if (e && e.clientX >= r.left && e.clientX <= r.right) {
      if (e.clientY >= r.top && e.clientY < r.top + EDGE) v = -Math.ceil((r.top + EDGE - e.clientY) / 4);
      else if (e.clientY <= r.bottom && e.clientY > r.bottom - EDGE) v = Math.ceil((e.clientY - (r.bottom - EDGE)) / 4);
    }
    if (v) {
      const before = sc.scrollTop;
      sc.scrollTop += v;
      if (sc.scrollTop !== before) track(e);
    }
    d.raf = requestAnimationFrame(scroll);
  }

  function up(e) {
    if (!press || e.pointerId !== press.id) return;
    if (!d) { stop(); return; }   // a click: the row's own handler picks it
    track(e);
    const target = d.target;
    finish();
    // The click that comes with letting go (in the same turn, wherever it lands) isn't a click on
    // a row or a page
    const swallow = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
    window.addEventListener("click", swallow, true);
    setTimeout(() => window.removeEventListener("click", swallow, true), 0);
    if (target) owner.drop(target);
    else owner.cancel();
  }
  function cancel() {
    if (d) { finish(); owner.cancel(); }
    stop();
  }
  // Escape cancels; other keys wait until the drag is over
  function key(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.key === "Escape") cancel();
  }

  function finish() {
    clearTimeout(d.spring);
    cancelAnimationFrame(d.raf);
    for (const el of d.rows) { el.style.transform = ""; el.classList.remove("drop-into"); }
    d.outEl?.classList.remove("drop-target");
    d.held.remove();
    list.style.paddingBottom = "";
    document.body.classList.remove("list-dragging");
    window.removeEventListener("keydown", key, true);
    try { list.releasePointerCapture(press.id); } catch { /* a synthetic pointer */ }
    d = null;
    stop();
  }
  function stop() {
    window.removeEventListener("pointermove", move, true);
    window.removeEventListener("pointerup", up, true);
    window.removeEventListener("pointercancel", cancel, true);
    press = null;
  }

  return { get active() { return !!d; } };
}

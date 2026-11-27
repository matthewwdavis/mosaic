// The zoom as a percentage you can click and type into, with a ▾ beside it listing set zooms, as
// Illustrator's zoom box (Matthew asked, 27 Nov 2026: "click the small Zoom percent and type in a
// number", the list too, in both apps). Shared by prose (its status bar) and mosaic (its status bar
// and the View tab), from labapp/web, served to each app's page as labapp/zoombox.js and
// labapp/zoombox.css by server.py.
//
// A click selects the percentage, ready to type over. Enter, Tab or a click elsewhere sets the zoom
// typed ("150", "150%", "33.3", "33,3"); Escape puts back the one there was. A zoom past the app's
// limits goes to the limit (his choice); anything that isn't a number changes nothing. ↓ (or ⌥↓)
// opens the list, as the ▾ does; ↑ ↓ move in it, Enter chooses, Escape closes it.

// A typed zoom as a percentage, or null when it isn't one ("", "abc", "-5")
export function parseZoom(text) {
  const t = String(text ?? "").replace(/\s+/g, "").replace(/%$/, "").replace(",", ".");
  if (!/^(\d+\.?\d*|\.\d+)$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

// The zoom a typed percentage asks for (1 = 100%), kept within [min, max]; null when it isn't a number
export function typedZoom(text, min, max) {
  const p = parseZoom(text);
  if (p === null) return null;
  return Math.min(max, Math.max(min, p / 100));
}

// The list's line for a zoom now: the one at that zoom (to a hundredth of a percent), else none
export function currentEntry(entries, z) {
  return entries.findIndex((e) => e && typeof e === "object" && typeof e.zoom === "number" && Math.abs(e.zoom - z) < 5e-5);
}

const pct = (z) => `${Math.round(z * 100)}%`;
let boxes = 0;

// A zoom box for a window. zoom(): the zoom now; set(z): go to zoom z (1 = 100%, already within
// [min, max]); entries: the list's lines, {label, zoom} (a set zoom), {label, run, keys} (a command,
// with its shortcut shown) or "-" (a line between groups); done(): give the keys back to the page
// (after Enter, Escape or a choice from the list; not after a click elsewhere, which already took
// them); format(z): the zoom as shown ("125%"); title: the box's tooltip.
// Returns {el (to put in the page), show(z) (the zoom shown, as it changes; not while typing),
// field, arrow, open(), close(), listEl() (the list while it's open), editing()}.
export function makeZoomBox(doc = document, { zoom, set, min, max, entries = [], done = () => {}, format = pct,
  title = "Zoom: click to type a zoom; ▾ for set zooms", label = "Zoom" } = {}) {
  const win = doc.defaultView || window;
  const id = `labapp-zoombox-list-${++boxes}`;
  const el = doc.createElement("span");
  el.className = "labapp-zoombox";
  // (typed exactly as typed: no automatic capitals, corrections or spelling marks, as the apps' one-line fields)
  el.innerHTML = `<input class="labapp-zoombox-field" type="text" inputmode="decimal" spellcheck="false" autocomplete="off"`
    + ` autocapitalize="off" autocorrect="off"`
    + ` size="5" role="combobox" aria-autocomplete="none" aria-expanded="false" aria-controls="${id}">`
    + `<button type="button" class="labapp-zoombox-arrow" tabindex="-1" aria-haspopup="listbox" aria-expanded="false">`
    + `<svg viewBox="0 0 10 6" width="8" height="5" aria-hidden="true"><path d="M1 1l4 4 4-4"/></svg></button>`;
  const field = el.querySelector("input"), arrow = el.querySelector("button");
  field.setAttribute("aria-label", label);
  field.title = title;
  arrow.setAttribute("aria-label", `${label} choices`);
  arrow.dataset.tipName = `${label} choices`;
  arrow.dataset.tipDesc = "Set zooms to choose from";

  let typing = false, list = null, lit = -1, choices = [];
  const show = (z = zoom()) => { if (!typing) field.value = format(z); };

  // Typing ------------------------------------------------------------------------------
  const begin = () => {
    if (typing) return;
    typing = true;
    field.value = format(zoom());
    field.select();
  };
  // The end of typing: the zoom typed set (apply), or the old one put back
  const finish = (apply) => {
    if (!typing) return;
    typing = false;
    if (apply) {
      const z = typedZoom(field.value, min, max);
      if (z !== null && Math.abs(z - zoom()) > 1e-9) set(z);
    }
    show();
  };
  field.addEventListener("mousedown", (e) => {
    if (doc.activeElement === field || e.button !== 0) return;   // (already typing: the caret goes where clicked)
    e.preventDefault();
    field.focus({ preventScroll: true });
    begin();
  });
  field.addEventListener("focus", begin);
  field.addEventListener("blur", () => { close(); finish(true); });
  field.addEventListener("input", () => { if (list) light(-1); });
  field.addEventListener("keydown", (e) => {
    const k = e.key;
    if (list && (k === "ArrowDown" || k === "ArrowUp") && !e.altKey) {
      e.preventDefault();
      step(k === "ArrowDown" ? 1 : -1);
      return;
    }
    if (k === "ArrowDown" || (k === "ArrowUp" && e.altKey)) {
      e.preventDefault();
      if (list) close(); else open();
      return;
    }
    if (k === "Enter") {
      e.preventDefault();
      if (list && lit >= 0) { choose(lit); return; }
      close();
      finish(true);
      done();
      return;
    }
    if (k === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (list) { close(); return; }
      finish(false);
      done();
      return;
    }
    if (k === "Tab") close();   // (Tab: the field loses the keys and sets the zoom typed, as a click elsewhere)
  });

  // The list ----------------------------------------------------------------------------
  const lines = () => (list ? [...list.querySelectorAll(".labapp-zoombox-item")] : []);
  const light = (i) => {
    const ls = lines();
    lit = i;
    ls.forEach((b, j) => b.classList.toggle("lit", j === i));
    if (i >= 0 && ls[i]) {
      field.setAttribute("aria-activedescendant", ls[i].id);
      ls[i].scrollIntoView?.({ block: "nearest" });
    } else field.removeAttribute("aria-activedescendant");
  };
  const step = (d) => {
    const n = lines().length;
    if (n) light(lit < 0 ? (d > 0 ? 0 : n - 1) : (lit + d + n) % n);
  };
  const choose = (i) => {
    const e = choices[i];
    if (!e) return;
    close();
    if (typing) finish(false);
    if (typeof e.zoom === "number") set(Math.min(max, Math.max(min, e.zoom)));
    else if (e.run) e.run();
    show();
    done();
  };
  // Below the box, or above it where there's no room (a status bar's), kept inside the window
  const place = () => {
    const r = el.getBoundingClientRect(), h = list.offsetHeight, w = list.offsetWidth;
    const vw = win.innerWidth, vh = win.innerHeight;
    const below = r.bottom + 2 + h + 8 <= vh || r.top - 2 - h < 8;
    list.style.top = `${Math.max(8, below ? r.bottom + 2 : r.top - 2 - h)}px`;
    list.style.left = `${Math.max(8, Math.min(r.left, vw - w - 8))}px`;
    list.style.maxHeight = `${Math.max(80, (below ? vh - r.bottom : r.top) - 12)}px`;
  };
  const outside = (e) => { if (list && !list.contains(e.target) && !el.contains(e.target)) close(); };
  const away = () => close();
  function open() {
    if (list) return;
    list = doc.createElement("div");
    list.className = "labapp-zoombox-list";
    list.id = id;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", label);
    choices = [];
    const now = currentEntry(entries, zoom());
    entries.forEach((e, i) => {
      if (e === "-") {
        const sep = doc.createElement("div");
        sep.className = "labapp-zoombox-sep";
        sep.setAttribute("role", "separator");
        list.append(sep);
        return;
      }
      if (!e) return;
      const n = choices.length;
      choices.push(e);
      const line = doc.createElement("div");
      line.className = "labapp-zoombox-item";
      line.id = `${id}-${n}`;
      line.setAttribute("role", "option");
      line.setAttribute("aria-selected", String(i === now));
      const name = doc.createElement("span");
      name.className = "labapp-zoombox-name";
      name.textContent = e.label ?? format(e.zoom);
      line.append(name);
      if (e.keys) {
        const keys = doc.createElement("span");
        keys.className = "labapp-zoombox-keys";
        keys.textContent = e.keys;
        line.append(keys);
      }
      line.addEventListener("mousedown", (ev) => ev.preventDefault());   // (the field keeps the keys meanwhile)
      line.addEventListener("mousemove", () => { if (lit !== n) light(n); });
      line.addEventListener("click", () => choose(n));
      list.append(line);
    });
    doc.body.append(list);
    place();
    el.classList.add("open");
    field.setAttribute("aria-expanded", "true");
    arrow.setAttribute("aria-expanded", "true");
    light(-1);
    doc.addEventListener("mousedown", outside, true);
    win.addEventListener("resize", away);
    win.addEventListener("blur", away);
  }
  function close() {
    if (!list) return;
    list.remove();
    list = null;
    lit = -1;
    el.classList.remove("open");
    field.setAttribute("aria-expanded", "false");
    arrow.setAttribute("aria-expanded", "false");
    field.removeAttribute("aria-activedescendant");
    doc.removeEventListener("mousedown", outside, true);
    win.removeEventListener("resize", away);
    win.removeEventListener("blur", away);
  }
  // (the ▾ gives the field the keys, so ↑ ↓ Enter and Escape work the list; typing stays typing)
  arrow.addEventListener("mousedown", (e) => e.preventDefault());
  arrow.addEventListener("click", () => {
    if (list) { close(); return; }
    if (doc.activeElement !== field) field.focus({ preventScroll: true });
    open();
  });

  show();
  return { el, field, arrow, show, open, close, listEl: () => list, editing: () => typing };
}

// The callout a button shows when the pointer rests on it, as Word's ScreenTips: its name and its
// keyboard shortcut on top, what it does under them, after ¾ second (Matthew's choice, 26 Nov 2026:
// between Word's half second and a whole one). Shared by prose and mosaic (labapp/web, served to each
// app's page as labapp/tips.js and labapp/tips.css by server.py): every button in the window that
// says what it is, from data-tip-name, -keys and -desc (set by the app's ribbon), or a title ("Bold
// (⌘B)": the shortcut in brackets taken out of it), an aria-label or the button's own words. A button
// whose callout would only repeat what it shows has none. Moving on to the next button straight
// after shows its callout at once, as menus and Word do; a click, a key, scrolling or leaving the
// window takes it away.
//
// Each app's Settings turns it off (on by default: enabled()); off, the buttons' own system tooltips
// are as they were. While the callout is on, a button's own tooltip is held back (its title emptied,
// which hides its ancestors' too, then put back).

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

// A shortcut as the system writes it: ⌘B on a Mac, Ctrl+B on Windows and Linux (one written for the
// other already, "Ctrl+B", is left as it is)
export function keyLabel(k, mac = IS_MAC) {
  if (!k || mac) return k || "";
  if (k === "⌃=") return "Alt+=";
  const mods = [];
  let rest = String(k);
  for (const [sym, name] of [["⌃", "Ctrl"], ["⌘", "Ctrl"], ["⌥", "Alt"], ["⇧", "Shift"]]) {
    if (rest.includes(sym)) { if (!mods.includes(name)) mods.push(name); rest = rest.split(sym).join(""); }
  }
  rest = rest.replace("↩", "Enter").replace("⌫", "Backspace").replace("−", "-").replace("⎋", "Esc");
  return [...mods, rest].join("+");
}

export const TIP_DELAY = 750;
const TARGET = 'button, [role="button"], select, summary, a[href], [data-tip-name], [data-tip-desc]';
// (a shortcut in brackets in a title: "(⌘B)", "(⇧⌘E)", "(⇧F7)", "(Ctrl+B)", "(⌘L puts in the next one)" isn't)
const KEY = String.raw`(?:[⌃⌥⇧⌘]+(?:[^\s()]+)|(?:Ctrl|Alt|Shift|Cmd)\+[^\s()]+|F\d{1,2})`;
const KEYS_IN = new RegExp(String.raw`\s*\((${KEY}(?:\s*(?:,|or)\s*${KEY})*)\)`);

const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
const same = (a, b) => clean(a).toLowerCase() === clean(b).toLowerCase();

// What a button's callout says, from what it has: {title (its tooltip), name, keys, desc (set for
// it), aria (its aria-label), text (the words it shows)}: {name, keys, desc}, or null when there's
// nothing to say that it doesn't show already
export function tipFrom({ title = "", name = "", keys = "", desc = null, aria = "", text = "" } = {}, label = keyLabel) {
  let rest = clean(title);
  if (!keys) {
    const m = KEYS_IN.exec(rest);
    if (m) { keys = m[1]; rest = clean(rest.slice(0, m.index) + rest.slice(m.index + m[0].length)); }
  }
  const shown = clean(text);
  name = clean(name) || clean(aria) || (shown.length <= 40 ? shown : "");
  desc = clean(desc === null ? rest : desc);
  // (the description only where it adds to the name: not "Bold" again, nor "Track Changes" under "Track Changes: On")
  if (desc && name && (same(desc, name) || clean(name).toLowerCase().includes(clean(desc).toLowerCase()))) desc = "";
  if (!name && desc) { name = desc; desc = ""; }
  if (!name) return null;
  if (!keys && !desc && same(name, shown)) return null;
  return { name, keys: label(keys), desc };
}

// The same from a button in the page
export function tipOf(el, label = keyLabel) {
  const d = el.dataset || {};
  const text = el.querySelector && el.querySelector("svg") && !clean(el.textContent) ? "" : el.textContent;
  return tipFrom({ title: d.tipTitle ?? el.getAttribute("title") ?? "", name: d.tipName || "", keys: d.tipKeys || "",
    desc: d.tipDesc ?? null, aria: el.getAttribute("aria-label") || "", text }, label);
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// The callouts for a window. enabled(): whether they're on (the app's Settings); keys(k): a shortcut
// as the app writes it (keyLabel by default). {hide(), showing(), clicked()} for the app and its
// self-test
export function installTips(doc = document, { enabled = () => true, delay = TIP_DELAY, keys = keyLabel } = {}) {
  const win = doc.defaultView || window;
  let el = null, timer = null, box = null, visible = false, lastHidden = 0, clicked = false;
  // (the button's own tooltip held back while the pointer is on it, and given back after)
  const holdTitle = (b) => {
    if (b.dataset.tipHeld) return;
    b.dataset.tipHeld = b.hasAttribute("title") ? "1" : "0";
    b.dataset.tipTitle = b.getAttribute("title") || "";
    b.setAttribute("title", "");
  };
  const giveBack = (b) => {
    if (!b.dataset.tipHeld) return;
    if (b.getAttribute("title") === "") {   // (unless it was given a new one meanwhile)
      if (b.dataset.tipHeld === "1") b.setAttribute("title", b.dataset.tipTitle || ""); else b.removeAttribute("title");
    }
    delete b.dataset.tipHeld;
    delete b.dataset.tipTitle;
  };
  const hide = () => {
    clearTimeout(timer);
    timer = null;
    if (visible) { visible = false; lastHidden = Date.now(); box.hidden = true; }
  };
  const show = () => {
    timer = null;
    if (!el || !el.isConnected || !enabled()) return;
    const tip = tipOf(el, keys);
    if (!tip) return;
    if (!box) {
      box = doc.createElement("div");
      box.className = "labapp-tip";
      box.setAttribute("role", "tooltip");
      box.hidden = true;
      doc.body.appendChild(box);
    }
    box.innerHTML = `<div class="tip-head"><span class="tip-name">${esc(tip.name)}</span>${tip.keys ? `<span class="tip-keys">${esc(tip.keys)}</span>` : ""}</div>`
      + (tip.desc ? `<div class="tip-desc">${esc(tip.desc)}</div>` : "");
    box.hidden = false;
    // Under the button, from its left edge; above it where there isn't room (the status bar's)
    const r = el.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
    const vw = win.innerWidth, vh = win.innerHeight;
    let x = Math.min(Math.max(8, r.left), vw - w - 8), y = r.bottom + 6;
    if (y + h > vh - 8) y = Math.max(8, r.top - h - 6);
    box.style.left = `${Math.round(x)}px`;
    box.style.top = `${Math.round(y)}px`;
    visible = true;
  };
  const leave = () => { hide(); if (el) giveBack(el); el = null; clicked = false; };
  doc.addEventListener("mouseover", (e) => {
    const t = e.target && e.target.closest ? e.target.closest(TARGET) : null;
    if (t === el) return;
    if (el) leave();
    if (!t || !enabled() || !tipOf(t, keys)) return;
    el = t;
    holdTitle(el);
    // (straight after one went: at once)
    timer = setTimeout(show, Date.now() - lastHidden < 400 ? 0 : delay);
  }, true);
  doc.addEventListener("mouseout", (e) => { if (el && !(e.relatedTarget && el.contains(e.relatedTarget))) leave(); }, true);
  // A click, a key, scrolling: gone, and not back for this button until the pointer comes again
  const away = () => { if (!el) return; clicked = true; hide(); lastHidden = 0; };
  for (const ev of ["mousedown", "keydown", "wheel", "dragstart"]) doc.addEventListener(ev, away, true);
  doc.addEventListener("scroll", () => { if (visible) hide(); }, true);
  win.addEventListener("blur", leave);
  return { hide: leave, showing: () => (visible && box ? box.textContent : ""), clicked: () => clicked };
}

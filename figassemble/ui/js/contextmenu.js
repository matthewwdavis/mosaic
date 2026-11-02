// Right-click menus: the commands for what was clicked, each with its shortcut, as in PowerPoint.
// They open with a right-click (Control-click on a Mac), the menu key or Shift+F10; arrow keys
// move, a letter jumps to a command, Enter chooses, Escape closes. A line with ▸ opens more
// commands beside the menu, when pointed at or clicked, or with → or Enter; ← or Escape goes back.

import { h, s } from "./util.js";

let menu = null;
let sub = null;        // a submenu open beside the menu: {el, item: its line in the menu}
let subTimer = null;   // pointing at another line closes the submenu after a moment
let back = null;
let anchor = [0, 0];

// At the pointer, opening upwards or leftwards where it would run off the window, and kept inside it
function place() {
  menu.style.maxHeight = `${window.innerHeight - 16}px`;
  const w = menu.offsetWidth, ht = menu.offsetHeight, [x, y] = anchor;
  const left = x + w + 8 > window.innerWidth ? x - w : x, top = y + ht + 8 > window.innerHeight ? y - ht : y;
  menu.style.left = `${Math.max(8, Math.min(left, window.innerWidth - w - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(top, window.innerHeight - ht - 8))}px`;
}
// A submenu beside its line, its first command level with it: to the right, or to the left where
// there's no room
function placeSub() {
  sub.el.style.maxHeight = `${window.innerHeight - 16}px`;
  const r = sub.item.getBoundingClientRect(), m = menu.getBoundingClientRect(), box = sub.el.getBoundingClientRect();
  const first = sub.el.querySelector(".menu-item")?.getBoundingClientRect();
  const w = box.width, ht = box.height, top = r.top - (first ? first.top - box.top : 0);
  const left = m.right + w + 8 > window.innerWidth ? m.left - w + 2 : m.right - 2;
  sub.el.style.left = `${Math.max(8, Math.min(left, window.innerWidth - w - 8))}px`;
  sub.el.style.top = `${Math.max(8, Math.min(top, window.innerHeight - ht - 8))}px`;
}

// The arrow on a line that opens a submenu (the Objects list's closed-group icon)
function chevron() {
  const svg = s("svg", { viewBox: "0 0 24 24", class: "icon submenu-arrow", "aria-hidden": "true" });
  svg.append(s("path", { d: "M9 6l6 6-6 6" }));
  return svg;
}

// A menu's lines; null and false are left out, and so are lines with nothing on one side
function fill(el, entries) {
  const list = [];
  for (const e of entries.filter(Boolean)) {
    if (e !== "-" || (list.length && list[list.length - 1] !== "-")) list.push(e);
  }
  while (list[list.length - 1] === "-") list.pop();
  for (const e of list) {
    if (e === "-") {
      el.append(h("div", { class: "menu-sep", role: "separator" }));
      continue;
    }
    const checkable = e.checked !== undefined;
    const item = h("button", { type: "button", class: "menu-item", tabindex: -1,
      role: checkable ? "menuitemcheckbox" : "menuitem", "aria-checked": checkable ? String(!!e.checked) : null,
      "aria-disabled": e.disabled ? "true" : null, "aria-haspopup": e.items ? "menu" : null,
      "aria-expanded": e.items ? "false" : null },
    h("span", { class: "check", "aria-hidden": "true" }, checkable ? "✓" : ""),
    h("span", { class: "menu-label" },
      e.swatch ? h("span", { class: "chip", style: { background: e.swatch }, "aria-hidden": "true" }) : null, e.label),
    e.items ? chevron() : e.keys ? h("kbd", {}, e.keys) : h("span"));
    item.addEventListener("click", () => contextMenu.choose(e, item));
    item.addEventListener("pointermove", () => {
      if (document.activeElement !== item) item.focus({ preventScroll: true });
      contextMenu.hover(e, item);
    });
    el.append(item);
  }
  el.addEventListener("keydown", (ev) => contextMenu.key(ev));
  el.addEventListener("contextmenu", (ev) => ev.preventDefault());
}

export const contextMenu = {
  get open() { return !!menu; },
  // entries: { label, keys, run, disabled, checked, swatch (a colour chip), items (a submenu's
  // entries, instead of run) } or "-" for a line between groups
  show(entries, x, y, returnFocus = document.activeElement) {
    this.close(false);
    back = returnFocus;
    menu = h("div", { class: "popup-menu context-menu", role: "menu", "aria-label": "Commands" });
    fill(menu, entries);
    document.body.append(menu);
    anchor = [x, y];
    place();
    this.items()[0]?.focus({ preventScroll: true });
  },
  items(el = menu) { return el ? [...el.querySelectorAll(".menu-item")] : []; },
  choose(e, item) {
    if (e.disabled) return;
    if (e.items) {
      this.openSub(e, item, true);
      return;
    }
    this.close();
    e.run();
  },
  // The pointer over a line: a submenu's line opens it; another line in the menu closes it
  // after a moment, so it stays open while the pointer crosses other lines on the way to it
  hover(e, item) {
    clearTimeout(subTimer);
    if (!sub || sub.item === item || sub.el.contains(item)) {
      if (!sub && e.items && !e.disabled) this.openSub(e, item, false);
      return;
    }
    subTimer = setTimeout(() => {
      this.closeSub(false);
      if (e.items && !e.disabled && item.isConnected) this.openSub(e, item, false);
    }, 250);
  },
  openSub(e, item, focusFirst) {
    if (sub?.item !== item) {
      this.closeSub(false);
      const el = h("div", { class: "popup-menu context-menu submenu", role: "menu", "aria-label": e.label });
      fill(el, e.items);
      el.addEventListener("pointermove", () => clearTimeout(subTimer));   // (between its lines too)
      document.body.append(el);
      sub = { el, item };
      item.setAttribute("aria-expanded", "true");
      placeSub();
    }
    if (focusFirst) this.items(sub.el)[0]?.focus({ preventScroll: true });
  },
  closeSub(refocus) {
    clearTimeout(subTimer);
    if (!sub) return;
    sub.el.remove();
    sub.item.setAttribute("aria-expanded", "false");
    if (refocus) sub.item.focus({ preventScroll: true });
    sub = null;
  },
  close(refocus = true) {
    if (!menu) return;
    this.closeSub(false);
    menu.remove();
    menu = null;
    if (refocus && back?.isConnected) back.focus({ preventScroll: true });
    back = null;
  },
  key(ev) {
    ev.stopPropagation();
    const inSub = !!sub?.el.contains(ev.target);
    const items = this.items(inSub ? sub.el : menu), i = items.indexOf(document.activeElement), n = items.length;
    // (moving on in the menu closes a submenu that pointing opened)
    const go = (j) => { ev.preventDefault(); if (!inSub) this.closeSub(false); items[(j + n) % n]?.focus(); };
    if (inSub && (ev.key === "Escape" || ev.key === "ArrowLeft")) {
      ev.preventDefault();
      this.closeSub(true);
    } else if (ev.key === "Escape" || ev.key === "Tab" || ev.key === "ContextMenu" || (ev.key === "F10" && ev.shiftKey)) {
      ev.preventDefault();
      this.close();
    } else if (ev.key === "ArrowDown") go(i + 1);
    else if (ev.key === "ArrowUp") go(i < 0 ? n - 1 : i - 1);
    else if (ev.key === "Home") go(0);
    else if (ev.key === "End") go(n - 1);
    else if (ev.key === "Enter" || ev.key === " " || (ev.key === "ArrowRight" && items[i]?.getAttribute("aria-haspopup"))) {
      ev.preventDefault();
      if (i >= 0) items[i].click();
    } else if (ev.key.length === 1 && !ev.metaKey && !ev.ctrlKey && !ev.altKey) {
      // A letter jumps to the next command starting with it
      const ch = ev.key.toLowerCase();
      for (let k = 1; k <= n; k++) {
        const b = items[(i + k + n) % n];
        if (b.querySelector(".menu-label").textContent.toLowerCase().startsWith(ch)) {
          if (!inSub) this.closeSub(false);
          b.focus();
          break;
        }
      }
    }
  },
};

// A press outside the menus or leaving the window closes them; resizing the window keeps them inside it
document.addEventListener("pointerdown", (e) => {
  if (menu && !menu.contains(e.target) && !sub?.el.contains(e.target)) contextMenu.close(false);
}, true);
window.addEventListener("blur", () => contextMenu.close(false));
window.addEventListener("resize", () => {
  if (menu) place();
  if (sub) placeSub();
});

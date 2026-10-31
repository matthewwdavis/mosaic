// Right-click menus: the commands for what was clicked, each with its shortcut, as in PowerPoint.
// They open with a right-click (Control-click on a Mac), the menu key or Shift+F10; arrow keys
// move, a letter jumps to a command, Enter chooses, Escape closes.

import { h } from "./util.js";

let menu = null;
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

export const contextMenu = {
  get open() { return !!menu; },
  // entries: { label, keys, run, disabled, checked, swatch (a colour chip) } or "-" for a line between groups; null and
  // false are left out, and so are lines with nothing on one side
  show(entries, x, y, returnFocus = document.activeElement) {
    this.close(false);
    back = returnFocus;
    const list = [];
    for (const e of entries.filter(Boolean)) {
      if (e !== "-" || (list.length && list[list.length - 1] !== "-")) list.push(e);
    }
    while (list[list.length - 1] === "-") list.pop();
    menu = h("div", { class: "popup-menu context-menu", role: "menu", "aria-label": "Commands" });
    for (const e of list) {
      if (e === "-") {
        menu.append(h("div", { class: "menu-sep", role: "separator" }));
        continue;
      }
      const checkable = e.checked !== undefined;
      const item = h("button", { type: "button", class: "menu-item", tabindex: -1,
        role: checkable ? "menuitemcheckbox" : "menuitem", "aria-checked": checkable ? String(!!e.checked) : null,
        "aria-disabled": e.disabled ? "true" : null },
      h("span", { class: "check", "aria-hidden": "true" }, checkable ? "✓" : ""),
      h("span", { class: "menu-label" },
        e.swatch ? h("span", { class: "chip", style: { background: e.swatch }, "aria-hidden": "true" }) : null, e.label),
      e.keys ? h("kbd", {}, e.keys) : h("span"));
      item.addEventListener("click", () => this.choose(e));
      item.addEventListener("pointermove", () => { if (document.activeElement !== item) item.focus({ preventScroll: true }); });
      menu.append(item);
    }
    menu.addEventListener("keydown", (ev) => this.key(ev));
    menu.addEventListener("contextmenu", (ev) => ev.preventDefault());
    document.body.append(menu);
    anchor = [x, y];
    place();
    this.items()[0]?.focus({ preventScroll: true });
  },
  items() { return menu ? [...menu.querySelectorAll(".menu-item")] : []; },
  choose(e) {
    if (e.disabled) return;
    this.close();
    e.run();
  },
  close(refocus = true) {
    if (!menu) return;
    menu.remove();
    menu = null;
    if (refocus && back?.isConnected) back.focus({ preventScroll: true });
    back = null;
  },
  key(ev) {
    ev.stopPropagation();
    const items = this.items(), i = items.indexOf(document.activeElement), n = items.length;
    const go = (j) => { ev.preventDefault(); items[(j + n) % n]?.focus(); };
    if (ev.key === "Escape" || ev.key === "Tab" || ev.key === "ContextMenu" || (ev.key === "F10" && ev.shiftKey)) {
      ev.preventDefault();
      this.close();
    } else if (ev.key === "ArrowDown") go(i + 1);
    else if (ev.key === "ArrowUp") go(i < 0 ? n - 1 : i - 1);
    else if (ev.key === "Home") go(0);
    else if (ev.key === "End") go(n - 1);
    else if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      if (i >= 0) items[i].click();
    } else if (ev.key.length === 1 && !ev.metaKey && !ev.ctrlKey && !ev.altKey) {
      // A letter jumps to the next command starting with it
      const ch = ev.key.toLowerCase();
      for (let k = 1; k <= n; k++) {
        const b = items[(i + k + n) % n];
        if (b.querySelector(".menu-label").textContent.toLowerCase().startsWith(ch)) { b.focus(); break; }
      }
    }
  },
};

// A press outside the menu or leaving the window closes the menu; resizing the window keeps it inside
document.addEventListener("pointerdown", (e) => { if (menu && !menu.contains(e.target)) contextMenu.close(false); }, true);
window.addEventListener("blur", () => contextMenu.close(false));
window.addEventListener("resize", () => { if (menu) place(); });

// Any dialog can be moved: drag it by its title, to see what's under it (the document stays as
// it is while the dialog is open). Once moved, the dimming over the window goes, so what's
// behind reads clearly. Double-click the title to put it back in the middle.
//
// One listener for every dialog, whoever made it: a <dialog> with a heading (h2) at its top.

const HANDLE = "h2, .dialog-title";
const KEEP = 80;    // px of the dialog that stay inside the window's sides
const TITLE = 40;   // px of its top that stay above the window's bottom edge

function place(dlg, left, top) {
  const w = dlg.offsetWidth, vw = window.innerWidth, vh = window.innerHeight;
  const x = Math.min(Math.max(left, KEEP - w), vw - KEEP);
  const y = Math.min(Math.max(top, 0), vh - TITLE);
  dlg.style.margin = "0";
  dlg.style.left = `${x}px`;
  dlg.style.top = `${y}px`;
  dlg.style.right = "auto";
  dlg.style.bottom = "auto";
  dlg.classList.add("dialog-moved");
}

function centre(dlg) {
  for (const k of ["margin", "left", "top", "right", "bottom"]) dlg.style.removeProperty(k);
  dlg.classList.remove("dialog-moved");
}

// The dialog a press on its title would move, or null (a button or a field in the title is its own)
function dialogFor(target) {
  if (!target || !target.closest) return null;
  const dlg = target.closest("dialog[open]");
  const handle = target.closest(HANDLE);
  if (!dlg || !handle || !dlg.contains(handle) || target.closest("button, input, select, textarea, a, [contenteditable]")) return null;
  return dlg;
}

export function installDialogDrag(doc = document) {
  if (doc.dialogDragInstalled) return;
  doc.dialogDragInstalled = true;
  let drag = null;
  doc.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const dlg = dialogFor(e.target);
    if (!dlg) return;
    const r = dlg.getBoundingClientRect();
    drag = { dlg, dx: e.clientX - r.left, dy: e.clientY - r.top, x: e.clientX, y: e.clientY, moved: false, id: e.pointerId };
    e.preventDefault();   // (no text selected while it moves)
  }, true);
  doc.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (!drag.dlg.isConnected || !drag.dlg.open) { drag = null; return; }
    if (!drag.moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 3) return;   // (a click on the title isn't a move)
    drag.moved = true;
    place(drag.dlg, e.clientX - drag.dx, e.clientY - drag.dy);
  }, true);
  const end = (e) => { if (drag && e.pointerId === drag.id) drag = null; };
  doc.addEventListener("pointerup", end, true);
  doc.addEventListener("pointercancel", end, true);
  doc.addEventListener("dblclick", (e) => { const dlg = dialogFor(e.target); if (dlg && dlg.classList.contains("dialog-moved")) centre(dlg); }, true);
  // (the window made smaller: a moved dialog stays within reach)
  window.addEventListener("resize", () => {
    for (const dlg of doc.querySelectorAll("dialog[open].dialog-moved")) { const r = dlg.getBoundingClientRect(); place(dlg, r.left, r.top); }
  });
}

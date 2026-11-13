"""Closing a window with unsaved changes asks first, naming its figure: Save, Don't Save or
Cancel; a figure with AutoSave on is saved without asking. On a Mac the question is a sheet on
the window (macclose.py, which also asks about each unsaved figure in turn when mosaic quits);
on Windows a message box, Yes saving.

Save saves the figure (asking where, for one never saved), and the window closes once it's
saved; if that's cancelled or fails it stays open. Don't Save keeps a copy of the changes, made
then, that mosaic offers back the next time it starts (as it does with all unsaved work), and
closes it. Cancel leaves it open. While it asks, the window stays open (pywebview's closing
event is answered "not now"), and mosaic closes it afterwards. Should asking fail, pywebview's
own question (Close without saving or Cancel) still asks.
"""
from __future__ import annotations

import sys
import threading

KEEP_WAIT = 5.0   # seconds a window waits for its copy to be kept, before it closes anyway


def question(name: str, has_file: bool) -> dict:
    """What the question says: {"message", "detail", "save"} (Save… for a figure never saved,
    as saving it opens the Save dialog)."""
    return {"message": f"Do you want to save the changes made to “{name}”?",
            "detail": "If you don’t save, mosaic keeps a copy of your changes and offers it back the next time it starts.",
            "save": "Save" if has_file else "Save…"}


def on_closing(api, window):
    """pywebview's closing event, on the main thread: a window with unsaved changes stays open
    for now (False) and asks; one without closes."""
    if not window.confirm_close:
        return None
    ask(api, window, lambda ok: ok and close(window))
    return False


def ask(api, window, then) -> None:
    """Ask about a window's unsaved changes and do what the answer says; then then(True) once it
    may close (saved, or its copy kept), or then(False) (cancelled, or not saved after all)."""
    doc = api._doc_of(window)
    if doc.get("autosave"):   # AutoSave on (a saved figure): saved now, as it would be in a moment anyway
        answer(window, "save", then)
        return
    q = question(doc.get("name") or "Untitled figure", bool(doc.get("path")))
    _show(api, window, q, lambda choice: answer(window, choice, then))


def answer(window, choice: str, then) -> None:
    """Act on "save", "discard" (Don't Save) or "cancel"."""
    if choice == "save":
        def saved(value):
            if value is True:
                window.confirm_close = False   # (at once: a quit asking in turn moves on)
            then(value is True)
        _settle(window, "window.FA.app.saveToClose()", saved)
    elif choice == "discard":
        _settle(window, "window.FA.app.keepCopy()", lambda _kept: then(True), wait=KEEP_WAIT)
    else:
        then(False)


def close(window) -> None:
    """Close the window without asking (its changes saved or kept)."""
    window.confirm_close = False
    window.destroy()


def _settle(window, script: str, done, wait: float | None = None) -> None:
    """Run a promise of the window's editor and call done(its value) once it settles: None if
    the editor failed, or didn't answer within `wait` seconds."""
    once = threading.Lock()

    def finish(value):
        if once.acquire(blocking=False):   # (only the first answer counts)
            done(value)

    def run():
        try:
            window.evaluate_js(script, finish)
        except Exception:   # noqa: BLE001 (an editor that's gone or failing: no answer)
            finish(None)
    threading.Thread(target=run, daemon=True).start()
    if wait is not None:
        timer = threading.Timer(wait, finish, (None,))
        timer.daemon = True
        timer.start()


def _show(api, window, q: dict, reply) -> None:
    """The question as this platform asks it; reply("save" | "discard" | "cancel")."""
    if sys.platform == "darwin":
        from . import macclose
        macclose.ask(api, window, q, reply)
    else:
        reply(_ask_windows(q))


def _ask_windows(q: dict) -> str:
    """The question as a Windows message box: Yes saves, No doesn't, Cancel stays."""
    from System.Windows.Forms import DialogResult, MessageBox, MessageBoxButtons, MessageBoxIcon
    got = MessageBox.Show(f"{q['message']}\n\n{q['detail']}", "mosaic", MessageBoxButtons.YesNoCancel,
                          MessageBoxIcon.Warning)
    return "save" if got == DialogResult.Yes else "discard" if got == DialogResult.No else "cancel"

"""Closing a window with unsaved changes asks first, naming its document: Save, Don't Save or
Cancel; a document with AutoSave on is saved without asking. On a Mac the question is a sheet on
the window (mac/close.py, which also asks about each unsaved document in turn when the app
quits); on Windows a message box, Yes saving; on Linux pywebview's own question (Close without
saving or Cancel), the recovery copy the editor keeps as it goes being what's offered back.

Save saves the document (asking where, for one never saved), and the window closes once it's
saved; if that's cancelled or fails it stays open. Don't Save keeps a copy of the changes, made
then, that the app offers back the next time it starts, and closes it. Cancel leaves it open.
While it asks, the window stays open (pywebview's closing event is answered "not now"), and the
app closes it afterwards. Should asking fail, pywebview's own question still asks.

The app says who it is once (configure), and hooks the event:

    closing.configure(name="mosaic", thing="figure", save_js="window.FA.app.saveToClose()",
                      keep_js="window.FA.app.keepCopy()")
    window.events.closing += lambda: closing.on_closing(api, window)

A window asks only while window.confirm_close is true (the app sets it as the editor says there
are unsaved changes).
"""
from __future__ import annotations

import sys
import threading

KEEP_WAIT = 5.0   # seconds a window waits for its copy to be kept, before it closes anyway

# What the app says of itself (configure): its name; what it calls a document ("document"); the
# editor's promises that save the document to close it (true once saved) and keep a copy of its
# changes; and doc_of(api, window) -> {"name", "path", "autosave"} for the window's document
# detail: what the question says under its first line, for an app that keeps no copy at Don't Save
cfg: dict = {"name": "app", "thing": "document", "save_js": "", "keep_js": "", "detail": None,
             "doc_of": lambda api, window: api._doc_of(window)}


def configure(**values) -> None:
    unknown = set(values) - set(cfg)
    if unknown:
        raise TypeError(f"not a closing setting: {sorted(unknown)}")
    cfg.update(values)


def question(name: str, has_file: bool) -> dict:
    """What the question says: {"message", "detail", "save"} (Save… for a document never saved,
    as saving it opens the Save dialog)."""
    return {"message": f"Do you want to save the changes made to “{name}”?",
            "detail": cfg["detail"] or f"If you don’t save, {cfg['name']} keeps a copy of your changes and offers it back the next time it starts.",
            "save": "Save" if has_file else "Save…"}


def on_closing(api, window):
    """pywebview's closing event, on the main thread: a window with unsaved changes stays open
    for now (False) and asks; one without closes."""
    if not window.confirm_close:
        return None
    if not _has_question() and not cfg["doc_of"](api, window).get("autosave"):
        return None   # Linux has no question of the app's own: pywebview's asks (Close without saving or Cancel)
    ask(api, window, lambda ok: ok and close(window))
    return False


def _has_question() -> bool:
    """Whether this platform has a question of the app's own (a Mac's sheet, Windows' message box)."""
    return sys.platform in ("darwin", "win32")


def ask(api, window, then) -> None:
    """Ask about a window's unsaved changes and do what the answer says; then then(True) once it
    may close (saved, or its copy kept), or then(False) (cancelled, or not saved after all)."""
    doc = cfg["doc_of"](api, window)
    if doc.get("autosave"):   # AutoSave on (a saved document): saved now, as it would be in a moment anyway
        answer(window, "save", then)
        return
    q = question(doc.get("name") or f"Untitled {cfg['thing']}", bool(doc.get("path")))
    _show(api, window, q, lambda choice: answer(window, choice, then))


def answer(window, choice: str, then) -> None:
    """Act on "save", "discard" (Don't Save) or "cancel"."""
    if choice == "save":
        def saved(value):
            if value is True:
                window.confirm_close = False   # (at once: a quit asking in turn moves on)
            then(value is True)
        _settle(window, cfg["save_js"], saved)
    elif choice == "discard":
        _settle(window, cfg["keep_js"], lambda _kept: then(True), wait=KEEP_WAIT)
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
        from .mac import close as macclose
        macclose.ask(api, window, q, reply)
    else:
        reply(_ask_windows(q))


def _ask_windows(q: dict) -> str:
    """The question as a Windows message box: Yes saves, No doesn't, Cancel stays."""
    from System.Windows.Forms import DialogResult, MessageBox, MessageBoxButtons, MessageBoxIcon
    got = MessageBox.Show(f"{q['message']}\n\n{q['detail']}", cfg["name"], MessageBoxButtons.YesNoCancel,
                          MessageBoxIcon.Warning)
    return "save" if got == DialogResult.Yes else "discard" if got == DialogResult.No else "cancel"

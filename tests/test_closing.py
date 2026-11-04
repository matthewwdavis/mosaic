"""Closing a window with unsaved changes asks first (mosaic/app/closing.py): the question names
the figure; Save saves it and closes the window once saved, Don't Save keeps a copy and closes
it, Cancel leaves it open. (The Mac's sheet and quitting are checked by the smoke test.)"""
import threading

from mosaic.app import closing
from mosaic.app.api import Api


class FakeWindow:
    """What closing uses of a pywebview window: its editor answers a promise with `answer` (or
    never, None; or fails, `fails`)."""

    def __init__(self, answer=None, fails=False):
        self.confirm_close, self.destroyed, self.js = True, False, []
        self.answer, self.fails = answer, fails

    def evaluate_js(self, code, callback=None):
        self.js.append(code)
        if self.fails:
            raise RuntimeError("the editor is gone")
        if self.answer is not None and callback:
            callback(self.answer)

    def destroy(self):
        self.destroyed = True


def settled(window, choice):
    """What answering `choice` hands on: True (it may close), False (it stays)."""
    got, done = [], threading.Event()
    closing.answer(window, choice, lambda ok: (got.append(ok), done.set()))
    assert done.wait(5)
    return got[0]


def asking(monkeypatch, choice):
    """The questions asked, each answered `choice`."""
    asked = []
    monkeypatch.setattr(closing, "_show", lambda api, w, q, reply: (asked.append(q), reply(choice)))
    return asked


def one_window(path=None, name="single_nuclei"):
    api, w = Api(), FakeWindow()
    api._add_window(api._reserve_window(), w)
    api._caller.win = "1"
    try:
        api.doc_state(path, True, name)
    finally:
        api._caller.win = None
    return api, w


def test_the_question_names_the_figure_and_says_a_copy_is_kept():
    q = closing.question("single_nuclei", True)
    assert q["message"] == "Do you want to save the changes made to “single_nuclei”?"
    assert "keeps a copy" in q["detail"] and q["save"] == "Save"
    assert closing.question("Untitled figure", False)["save"] == "Save…"   # (the Save dialog asks where)


def test_a_window_with_nothing_unsaved_closes_without_asking(monkeypatch):
    asked = asking(monkeypatch, "cancel")
    api, w = one_window()
    w.confirm_close = False
    assert closing.on_closing(api, w) is None and not asked


def test_with_unsaved_changes_it_stays_open_and_asks_about_its_figure(monkeypatch, tmp_path):
    asked = asking(monkeypatch, "cancel")
    api, w = one_window(str(tmp_path / "single_nuclei.mosaic"))
    assert closing.on_closing(api, w) is False   # (not now)
    assert asked[0]["message"].endswith("“single_nuclei”?") and asked[0]["save"] == "Save"
    assert not w.destroyed and w.js == []   # Cancel: left as it was
    api2, w2 = one_window(None, None)
    closing.on_closing(api2, w2)
    assert asked[1]["save"] == "Save…" and "“Untitled figure”" in asked[1]["message"]


def test_save_closes_the_window_once_saved_and_not_when_it_isnt(monkeypatch, tmp_path):
    asking(monkeypatch, "save")
    api, w = one_window(str(tmp_path / "a.mosaic"))
    w.answer = True
    closing.on_closing(api, w)
    assert w.js == ["window.FA.app.saveToClose()"] and w.destroyed and not w.confirm_close
    api, w = one_window()
    w.answer = False   # the Save dialog cancelled, or the save failed
    closing.on_closing(api, w)
    assert not w.destroyed and w.confirm_close
    assert settled(FakeWindow(fails=True), "save") is False


def test_dont_save_keeps_a_copy_then_closes_even_if_the_editor_never_answers(monkeypatch):
    asking(monkeypatch, "discard")
    api, w = one_window()
    w.answer = True
    closing.on_closing(api, w)
    assert w.js == ["window.FA.app.keepCopy()"] and w.destroyed
    monkeypatch.setattr(closing, "KEEP_WAIT", 0.1)
    assert settled(FakeWindow(answer=None), "discard") is True   # (it waited, then closes)
    assert settled(FakeWindow(fails=True), "discard") is True


def test_cancel_leaves_the_editor_alone():
    w = FakeWindow(answer=True)
    assert settled(w, "cancel") is False and w.js == []


def test_the_editor_says_what_its_window_has_open(tmp_path):
    api, w = one_window(str(tmp_path / "b.mosaic"), "b")
    assert api._doc_of(w)["name"] == "b" and api._doc_of(w)["path"] and api._doc_of(FakeWindow()) == {}

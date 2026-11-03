"""Several windows in one app: each editor's requests reach its own window, documents open in a
window of their own (one open already comes to the front), documents the system opened
FigAssemble with wait for the first editor, recovery copies being kept aren't offered back
elsewhere, and a dropped .figasm's pages come with what they use (figassemble/app/api.py)."""
import json
import os
import urllib.request

from figassemble import docfile, model
from figassemble.app.api import Api
from figassemble.app.server import start_server


class FakeWindow:
    """What the Api uses of a pywebview window."""

    def __init__(self, uid):
        self.uid, self.confirm_close, self.title, self.shown, self.destroyed, self.js = uid, False, None, 0, False, []

    def set_title(self, title):
        self.title = title

    def show(self):
        self.shown += 1

    def destroy(self):
        self.destroyed = True

    def evaluate_js(self, code):
        self.js.append(code)


def two_windows(opened=None):
    api = Api()
    w1, w2 = FakeWindow("master"), FakeWindow("w2")
    api._add_window(api._reserve_window(), w1)
    api._add_window(api._reserve_window(), w2)
    if opened is not None:
        api._new_window = lambda doc, slides: opened.append((doc, slides))
    return api, w1, w2


def as_window(api, win, method, *args):
    api._caller.win = win
    try:
        return getattr(api, method)(*args)
    finally:
        api._caller.win = None


def test_each_request_reaches_its_own_window(tmp_path):
    api, w1, w2 = two_windows()
    as_window(api, "2", "set_title", "Two")
    as_window(api, "2", "doc_state", str(tmp_path / "b.figasm"), True)
    assert (w1.title, w2.title) == (None, "Two") and (w1.confirm_close, w2.confirm_close) == (False, True)
    assert api.window is w1   # outside a request: the first
    info = as_window(api, "2", "app_info")
    assert info["windows"] is False and info["first_window"] is False   # (no way to open windows: browser mode)
    api._new_window = lambda doc, slides: None
    assert as_window(api, "1", "app_info")["windows"] is True and as_window(api, "1", "app_info")["first_window"] is True
    # Through the server, as the editor sends them
    srv = start_server(api)
    try:
        req = urllib.request.Request(srv.url + "rpc", data=json.dumps({"method": "set_title", "args": ["By RPC"], "win": "1"}).encode(),
                                     headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req).read())["result"] is True
    finally:
        srv.shutdown()
    assert w1.title == "By RPC" and w2.title == "Two" and getattr(api._caller, "win", None) is None


def test_documents_open_in_a_window_of_their_own(tmp_path):
    opened = []
    api, w1, w2 = two_windows(opened)
    a, b = str(tmp_path / "a.figasm"), str(tmp_path / "b.figasm")
    as_window(api, "1", "doc_state", a, False)
    assert api.open_window(b) == {"opened": True} and opened == [(os.path.abspath(b), None)]
    # One open already comes to the front (however its path is written)
    assert api.open_window(os.path.join(str(tmp_path), ".", "a.figasm")) == {"shown": True} and w1.shown == 1 and len(opened) == 1
    assert api.show_document(a) and not api.show_document(b)
    # A deck always opens (its slides become a new figure), with the slides chosen; New: no document
    api.open_window(str(tmp_path / "deck.pptx"), [2, 3])
    api.open_window()
    assert opened[1:] == [(str(tmp_path / "deck.pptx"), [2, 3]), (None, None)]
    # Browser mode: no windows to open, the editor replaces its figure
    assert Api().open_window(b) == {"opened": False}
    # Closing a window forgets it, and what it had open
    api._remove_window("1")
    assert not api.show_document(a) and api.window is w2


def test_documents_the_app_opened_with_wait_for_the_first_editor(tmp_path):
    api, w1, w2 = two_windows([])
    a, b, c = (str(tmp_path / f"{n}.figasm") for n in "abc")
    api._launched.clear()   # (a Mac app, still launching)
    assert api._system_open([a, b]) == []   # no editor yet: they wait
    api._launched.set()
    assert as_window(api, "1", "launch_documents") == [a, b] and as_window(api, "2", "launch_documents") == []
    assert sorted(api._ready_uids()) == ["master", "w2"]
    # Later ones go to the editor in front, except one open already, which comes to the front
    as_window(api, "2", "doc_state", c, False)
    assert api._system_open([c, b]) == [b] and w2.shown == 1


def test_recovery_copies_being_kept_arent_offered_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGASSEMBLE_HOME", str(tmp_path))
    doc = model.new_document("Unsaved")
    one, other = Api(), Api()   # (two FigAssembles running at once)
    one._add_window(one._reserve_window(), FakeWindow("master"))
    as_window(one, "1", "autosave", doc, "doc-kept")
    other.autosave(doc, "doc-left")
    other._unlock_autosave("doc-left")   # (as when that FigAssemble quits)
    names = lambda api: [os.path.basename(c["path"]) for c in api.autosaved()]   # noqa: E731
    assert names(other) == ["doc-left.figasm"]   # the other's live copy isn't offered back
    assert sorted(names(one)) == ["doc-kept.figasm", "doc-left.figasm"]   # (a window's own: as before)
    other.delete_autosaves([str(tmp_path / "autosave" / "doc-kept.figasm")])
    assert os.path.exists(tmp_path / "autosave" / "doc-kept.figasm")   # nor deleted
    one._remove_window("1")   # its window closed: left behind, offered next time
    assert sorted(names(other)) == ["doc-kept.figasm", "doc-left.figasm"]
    # A recovered copy is claimed at once; saving discards it and lets go
    assert other.claim_autosave("doc-kept") and not one.claim_autosave("doc-kept")
    other.discard_autosave("doc-kept")
    assert not os.path.exists(tmp_path / "autosave" / "doc-kept.figasm") and one.claim_autosave("doc-kept")
    assert not one.claim_autosave("../escape")   # only FigAssemble's own names


def test_restarting_keeps_copies_of_the_other_windows_unsaved_work(tmp_path):
    api, w1, w2 = two_windows()
    as_window(api, "1", "doc_state", None, True)
    as_window(api, "2", "doc_state", None, True)
    api._keep_copies(exclude="1", wait=0.2)
    assert w1.js == [] and w2.js == ["window.FA && window.FA.app.keepCopy()"]


def test_a_dropped_figures_pages_come_with_what_they_use(tmp_path):
    doc = model.new_document("Other")
    doc["swatches"] = [{"id": "sw_1", "name": "Blue", "color": "#0000ff"}]
    doc["symbols"] = [{"id": "sym_1", "name": "Star", "items": [], "size": [10, 10]}]
    doc["text_styles"] = [{"id": "ts_1", "name": "Label", "font": "Helvetica", "size": 6}]
    doc["pages"][0]["items"].append(model.text_item("Hello", 10, 10))
    path = str(tmp_path / "Other.figasm")
    docfile.save(doc, path)
    got = Api().figure_pages(path)
    assert got["name"] == "Other" and got["pages"][0]["items"][0]["text"]["paragraphs"][0]["runs"][0]["t"] == "Hello"
    assert [s["id"] for s in got["swatches"]] == ["sw_1"] and [s["id"] for s in got["symbols"]] == ["sym_1"]
    assert got["text_styles"][0]["name"] == "Label" and got["object_styles"] == [] and got["assets"] == {}
    import base64
    with open(path, "rb") as fh:
        up = Api().figure_upload("Other.figasm", base64.b64encode(fh.read()).decode())
    assert up["pages"] == got["pages"]

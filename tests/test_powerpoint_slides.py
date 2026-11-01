"""PowerPoint slides into a figure: the slide picker's API (a deck imported once, its slides'
titles and pictures, the slides chosen), slides and shapes copied in PowerPoint (what PowerPoint
for Mac really put on the clipboard: tests/data/powerpoint), and slides dragged out of it."""
import base64
import io
import os
import shutil
import struct

import pytest
from PIL import Image

from figassemble.app import clipboard as cb
from figassemble.app import powerpoint
from figassemble.importers.gvml import import_shapes
from figassemble.importers.pptx import DeckImporter, slide_ids

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "powerpoint")
DECK = os.path.join(DATA, "example_deck.pptx")
FIGURES = os.path.join(DATA, "Figures")


def read(name: str) -> bytes:
    with open(os.path.join(DATA, name), "rb") as fh:
        return fh.read()


def descriptor(source: str) -> bytes:
    """An OLE object descriptor naming the file a copy came from (as Office writes one)."""
    name, src = "PowerPoint\x00".encode("utf-16-le"), (source + "\x00").encode("utf-16-le")
    return struct.pack("<I16sIiiiiIII", 52 + len(name) + len(src), b"\x00" * 16, 1, 0, 0, 0, 0, 0, 52, 52 + len(name)) + name + src


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("FIGASSEMBLE_FAKE_CLIPBOARD", "1")
    monkeypatch.setattr(cb, "_fake", None)
    return cb.backend()


# Decks ---------------------------------------------------------------------------------------

def test_titles_hidden_slides_and_a_report_for_some_slides(cache):
    imp = DeckImporter(DECK, None, True, cache)
    doc, report = imp.run(None)
    assert [s["title"] for s in imp.slide_info()] == ["Example figures", "", "", ""]
    assert [s["hidden"] for s in imp.slide_info()] == [False, False, False, True]
    assert slide_ids(DECK) == imp.slide_ids == [256, 257, 258, 259]
    # Slide 4 uses both pictures, already relinked for slides 2 and 3: its own report says so too
    four = imp.report_for([4])
    assert sum(line.startswith("relinked image") for line in four) == 2 and four[-1].startswith("slide 4:")
    both = imp.report_for([3, 4])
    assert sum(line.startswith("relinked image") for line in both) == 2
    assert sum(line.startswith("relinked image") for line in report) == 2   # the whole deck's: each picture once


def test_copied_slide_reads_like_a_deck(cache):
    # PowerPoint's clipboard deck keeps its parts under clipboard/, found through its relationships
    imp = DeckImporter(read("copied_slide.slides"), [FIGURES], True, cache, name="Copied slides")
    doc, report = imp.run(None)
    assert doc["meta"]["title"] == "Copied slides" and "imported_from" not in doc["meta"]
    items = doc["pages"][0]["items"]
    assert [(it["type"], it["name"]) for it in items] == [
        ("picture", "Picture 1"), ("shape", "TextBox 2"), ("shape", "Rounded Rectangle 3"), ("line", "Connector 4"),
        ("shape", "Oval 5"), ("group", "Group 6")]
    assert items[0]["frame"] == pytest.approx([60, 80, 158.4, 129.6])   # where it was on the slide
    assert report[0].startswith("relinked image1.png -> ") and report[0].endswith("example_scatter.png [pdf+png+svg]")


def test_copied_shapes_come_in_editable(cache):
    (rect,), _, report = import_shapes(read("copied_rect.gvml"), cache=cache)
    assert rect["geom"] == "roundRect" and rect["frame"] == pytest.approx([260, 90, 120, 50])
    assert rect["fill"]["color"] == "#DDE8F4" and rect["stroke"]["color"] == "#487AB6"   # the theme's line
    run = rect["text"]["paragraphs"][0]["runs"][0]
    assert run["t"] == "Treated" and run["color"] == "#FFFFFF"
    assert report == ["copied shapes: 1 shape with text"]
    (group,), _, _ = import_shapes(read("copied_group.gvml"), cache=cache)
    assert group["type"] == "group" and [it["geom"] for it in group["items"]] == ["rect", "triangle"]
    assert group["items"][1]["frame"] == pytest.approx([320, 170, 40, 30])
    assert group["items"][0]["fill"]["gradient"]["type"] == "linear"   # the theme's fill style
    (pic,), assets, report = import_shapes(read("copied_picture.gvml"), [FIGURES], cache=cache)
    assert pic["type"] == "picture" and assets[pic["asset"]]["primary"] in ("pdf", "png")
    assert report[0].endswith("example_scatter.png [pdf+png+svg]")
    (line,), _, _ = import_shapes(read("copied_line.gvml"), cache=cache)
    assert line["type"] == "line" and line["points"] == [[230, 115], [258, 115]]


def test_page_thumbnail(cache):
    from figassemble.export.run import page_thumbnail
    doc, _ = DeckImporter(DECK, None, True, cache).run([2])
    im = page_thumbnail(doc, 0, 320, cache)
    assert im.size == (320, 180) and im.getpixel((0, 0))[:3] == (255, 255, 255)
    assert len(im.getcolors(1 << 20)) > 20   # the plot, text and shapes are drawn


# The clipboard ---------------------------------------------------------------------------------

def test_source_of_copy():
    assert cb.source_of_copy(descriptor("/Users/me/Figures/deck.pptx!2")) == "/Users/me/Figures/deck.pptx"
    assert cb.source_of_copy(descriptor(r"C:\Talks\deck.pptx!12")) == r"C:\Talks\deck.pptx"
    assert cb.source_of_copy(descriptor("/a!b/deck.pptx")) == "/a!b/deck.pptx"
    assert cb.source_of_copy(b"\x00" * 20) is None and cb.source_of_copy(None) is None


def test_plan_takes_slides_and_shapes_before_their_picture(fake, fixtures):
    fake.put({"slides": os.path.join(DATA, "copied_slide.slides"), "pdf": fixtures["pdf"]})
    kind, got = cb.plan(fake)
    assert kind == "slides" and got["data"][:2] == b"PK" and got["source"] is None
    assert cb.plan(fake, "picture")[0] == "picture"
    assert cb.kinds(fake)["slides"] and cb.kinds(fake)["picture"]
    fake.put({"shapes": base64.b64encode(read("copied_rect.gvml")).decode(),
              "objdesc": base64.b64encode(descriptor(DECK + "!2")).decode(), "png": {"size": [20, 10], "dpi": 144}})
    kind, got = cb.plan(fake)
    assert kind == "shapes" and got["source"] == DECK
    # PowerPoint's copied text stays text
    fake.put({"text": "Treated", "pdf": fixtures["pdf"]})
    assert cb.plan(fake)[0] == "text"


def test_api_pastes_slides_and_shapes(fake, monkeypatch):
    from figassemble.app.api import Api
    monkeypatch.setattr(powerpoint, "open_decks", lambda: [])   # not the decks open on this computer
    api = Api()
    fake.put({"slides": os.path.join(DATA, "copied_slide.slides")})
    doc_path = os.path.join(DATA, "figure.figasm")   # (not saved: only where its pictures may be)
    r = api.clipboard_paste("auto", None, doc_path)
    assert r["kind"] == "slides" and r["key"].startswith("copied:") and len(r["pages"]) == 1
    assert len(r["pages"][0]["items"]) == 6 and list(r["assets"].values())[0]["name"].startswith("example_scatter")
    assert any(line.startswith("relinked image1.png") for line in r["report"])   # found near the figure
    fake.put({"shapes": os.path.join(DATA, "copied_picture.gvml"), "objdesc": base64.b64encode(descriptor(DECK + "!2")).decode()})
    r = api.clipboard_paste()
    assert r["kind"] == "shapes" and r["items"][0]["type"] == "picture"
    assert r["report"][0].startswith("relinked image1.png")   # found near the deck the shapes came from


# The slide picker ------------------------------------------------------------------------------

def test_picker_api(tmp_path, monkeypatch):
    from figassemble.app.api import Api
    monkeypatch.setattr(powerpoint, "open_decks", lambda: [])   # not the decks open on this computer
    api = Api()
    deck = tmp_path / "Figures" / "deck.pptx"
    shutil.copytree(FIGURES, tmp_path / "Figures")
    shutil.copy(DECK, deck)
    info = api.deck_slides(str(deck))
    assert info["name"] == "deck" and info["width"] == pytest.approx(960) and info["height"] == pytest.approx(540)
    assert [s["n"] for s in info["slides"]] == [1, 2, 3, 4] and info["slides"][0]["title"] == "Example figures"
    url = api.deck_thumbnail(str(deck), 2)
    assert url.startswith("data:image/png;base64,")
    assert Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).size == (320, 180)
    got = api.deck_pages(str(deck), [3])
    assert [p["name"] for p in got["pages"]] == ["Slide 3"] and [a["name"] for a in got["assets"].values()] == ["example_bars.png"]
    assert got["report"][0].startswith("relinked image2.png") and got["report"][-1].startswith("slide 3:")
    opened = api.open_document(str(deck), [2, 4])
    assert [p["name"] for p in opened["doc"]["pages"]] == ["Slide 2", "Slide 4"] and opened["path"] is None
    assert opened["suggested"].endswith("deck.figasm") and opened["doc"]["meta"]["imported_from"] == str(deck)
    assert len(api.open_document(str(deck))["doc"]["pages"]) == 4   # no slides chosen: all of them
    # Pages are copies: changing one doesn't change the next time they're asked for
    got["pages"][0]["items"].clear()
    assert api.deck_pages(str(deck), [3])["pages"][0]["items"]
    # A changed deck is read again
    before = api._decks[str(deck)]["importer"]
    os.utime(deck, (1, 1))
    api.deck_slides(str(deck))
    assert api._decks[str(deck)]["importer"] is not before
    # A deck dropped in the browser arrives as its bytes: a key stands for it
    key = api.deck_upload("dropped.pptx", base64.b64encode(read("example_deck.pptx")).decode())
    assert key.startswith("copied:") and api.deck_slides(key)["name"] == "dropped"
    assert [p["name"] for p in api.deck_pages(key, [4])["pages"]] == ["Slide 4"]
    assert api.deck_thumbnail(key, 1).startswith("data:image/png;base64,")
    # Web data dropped (PowerPoint's for dragged slides): as a paste of them
    r = api.dropped_package("slides", base64.b64encode(read("copied_slide.slides")).decode())
    assert r["kind"] == "slides" and len(r["pages"][0]["items"]) == 6


# Slides dragged out of PowerPoint --------------------------------------------------------------

def test_dragged_slides_are_found_in_open_decks(tmp_path):
    other = tmp_path / "other.pptx"
    shutil.copy(DECK, other)
    lsof = "\n".join(["p2793", "fcwd", f"n{tmp_path}", f"n{DECK}", f"n{tmp_path}/~$other.pptx", f"n{other}",
                      "n/Applications/Microsoft PowerPoint.app/Contents/MacOS/Microsoft PowerPoint", f"n{tmp_path}/gone.pptx"])
    assert powerpoint.parse_lsof(lsof) == [DECK, str(other)]
    refs = powerpoint.slide_refs([powerpoint.slide_ref_archive(258), powerpoint.slide_ref_archive(257)])
    assert [r["slide"] for r in refs] == [258, 257]
    assert powerpoint.find_slides(refs, [DECK]) == [{"path": DECK, "numbers": [3, 2]}]
    assert len(powerpoint.find_slides(refs, [DECK, str(other)])) == 2   # slide ids start at 256 in every deck
    assert powerpoint.find_slides(powerpoint.slide_refs([powerpoint.slide_ref_archive(300)]), [DECK]) == []
    assert powerpoint.slide_refs([b"not a keyed archive"]) == []

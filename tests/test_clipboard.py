"""Paste from other apps: reading the clipboard (figassemble/app/clipboard.py) and what a paste
puts on the page (Api.clipboard_paste)."""
import io
import os
import struct
import sys

import pytest
from PIL import Image

from figassemble.app import clipboard as cb


def show(paras):
    """Paragraphs as text: *bold*, _italic_, | between paragraphs, / for a line break."""
    out = []
    for p in paras:
        s = ""
        for r in p:
            if r["t"] == "\n":
                s += "/"
                continue
            t = r["t"]
            if r["bold"]:
                t = f"*{t}*"
            if r["italic"]:
                t = f"_{t}_"
            s += t
        out.append(s)
    return " | ".join(out)


def png(size=(20, 10), dpi=None) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, "PNG", **({"dpi": (dpi, dpi)} if dpi else {}))
    return buf.getvalue()


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("FIGASSEMBLE_FAKE_CLIPBOARD", "1")
    monkeypatch.setattr(cb, "_fake", None)
    return cb.backend()


# Text ------------------------------------------------------------------------------------------

def test_html_keeps_bold_italic_and_breaks():
    assert show(cb.paragraphs_from_html("<p>Plain and <b>bold</b> and <i>it</i></p><p>Line<br>two</p>")) == \
        "Plain and *bold* and _it_ | Line/two"
    assert show(cb.paragraphs_from_html("<strong>S</strong><em>E</em><h2>Heading</h2>")) == "*S*_E_ | *Heading*"


def test_html_inline_styles_win_over_tags():
    # Google Docs wraps everything in <b style="font-weight:normal">
    html = ('<b style="font-weight:normal;" id="docs-internal-guid-1"><span style="font-weight:700">Bold</span>'
            '<span style="font-weight:400"> plain </span><span style="font-style:italic">ital</span></b>')
    assert show(cb.paragraphs_from_html(html)) == "*Bold* plain _ital_"


def test_html_whitespace_lists_and_hidden_parts():
    html = ("<html><head><title>T</title><style>p {}</style></head><body>\n  <div>  A  <b>B</b>\n C </div>"
            "<ul><li>one</li><li>two &amp; three</li></ul><script>x()</script></body></html>")
    assert show(cb.paragraphs_from_html(html)) == "A *B* C | one | two & three"


def test_plain_text_paragraphs():
    assert show(cb.paragraphs_from_text("one\r\ntwo\n\nfour\n")) == "one | two |  | four"
    assert show(cb.split_paragraphs([{"t": "a b", "bold": True}])) == "*a*/*b*"


def test_cf_html_fragment():
    body = b"<html><body>\r\n<!--StartFragment-->x<b>y</b><!--EndFragment-->\r\n</body></html>"
    header = b"Version:0.9\r\nStartHTML:%010d\r\nEndHTML:%010d\r\nStartFragment:%010d\r\nEndFragment:%010d\r\n"
    size = len(header % (0, 0, 0, 0))
    start, end = size + body.index(b"-->x") + 3, size + body.index(b"<!--End")
    data = header % (size, size + len(body), start, end) + body
    assert cb.cf_html_fragment(data) == "x<b>y</b>"


# What a paste does -------------------------------------------------------------------------------

def test_plan_order(fake, fixtures):
    fake.put({"text": "Words", "html": "W<b>ords</b>", "png": {"size": [20, 10], "dpi": 144}})
    kind, paras = cb.plan(fake)
    assert kind == "text" and show(paras) == "W*ords*"
    kind, (data, ext) = cb.plan(fake, "picture")
    assert kind == "picture" and ext == ".png" and data[:4] == b"\x89PNG"
    assert cb.kinds(fake) == {"available": True, "own": False, "files": False, "objects": False, "slides": False,
                              "shapes": False, "text": True, "picture": True}
    # A link to a picture (as browsers copy one) pastes the picture
    fake.put({"text": "https://example.org/a.png", "png": {"size": [20, 10]}})
    assert cb.plan(fake)[0] == "picture" and not cb.kinds(fake)["text"]
    # Copied files come first (the Finder adds their names and an icon)
    fake.put({"files": [fixtures["pdf"], "/no/such/file.pdf"], "text": "plot.pdf", "tiff": {"size": [8, 8]}})
    assert cb.plan(fake) == ("files", [fixtures["pdf"]])
    # FigAssemble's own copies: objects, or "own" while the editor's copy is still the newest
    n = fake.put({"text": 'figassemble:{"items": []}'})
    assert cb.plan(fake) == ("objects", '{"items": []}') and cb.plan(fake, own_count=n) == ("own", None)
    fake.put({})
    assert cb.plan(fake) == ("none", None) and cb.plan(fake, "picture") == ("none", None)
    assert cb.plan(None) == ("unavailable", None) and cb.kinds(None) == {"available": False}


def test_picture_choice(fake, fixtures):
    with open(fixtures["pdf"], "rb") as f:
        pdf = f.read()
    fake.put({"pdf": fixtures["pdf"], "png": {"size": [20, 10], "dpi": 144}})
    assert cb.picture(fake, fake.available()) == (pdf, ".pdf")
    fake.put({"svg": fixtures["svg"], "png": {"size": [20, 10]}})
    assert cb.picture(fake, fake.available())[1] == ".svg"
    # A PNG that doesn't record its resolution gives way to a TIFF that does (a Mac screenshot)
    tiff = io.BytesIO()
    Image.new("RGB", (40, 20)).save(tiff, "TIFF", dpi=(144, 144))
    fake.data = {"png": png((40, 20)), "tiff": tiff.getvalue()}
    data, ext = cb.picture(fake, fake.available())
    im = Image.open(io.BytesIO(data))
    assert ext == ".png" and im.size == (40, 20) and round(im.info["dpi"][0]) == 144
    fake.data = {"png": png((40, 20), dpi=300), "tiff": tiff.getvalue()}
    assert round(Image.open(io.BytesIO(cb.picture(fake, fake.available())[0])).info["dpi"][0]) == 300


def test_tiff_takes_the_largest_image():
    buf = io.BytesIO()
    small, big = Image.new("RGB", (10, 5), "red"), Image.new("RGB", (20, 10), "blue")
    small.save(buf, "TIFF", save_all=True, append_images=[big], dpi=(144, 144))
    out = Image.open(io.BytesIO(cb.tiff_to_png(buf.getvalue())))
    assert out.size == (20, 10) and out.getpixel((0, 0)) == (0, 0, 255)


def test_api_paste(fake, fixtures):
    from figassemble.app.api import Api
    api = Api()
    assert api.app_info()["clipboard"] is True
    api.clipboard_fake({"text": "Plain and bold", "html": "Plain and <b>bold</b>"})
    r = api.clipboard_paste()
    assert r["kind"] == "text" and show(r["paragraphs"]) == "Plain and *bold*"
    api.clipboard_fake({"png": {"size": [288, 144], "dpi": 144}})
    r = api.clipboard_paste()
    assert r["kind"] == "picture" and r["asset"]["primary"] == "png" and r["asset"]["size_pt"] == pytest.approx([144, 72])
    api.clipboard_fake({"pdf": fixtures["pdf"], "text": "Shape text"})
    assert api.clipboard_paste()["kind"] == "text"
    r = api.clipboard_paste("picture")
    assert r["kind"] == "picture" and r["asset"]["primary"] == "pdf" and r["asset"]["size_pt"] == pytest.approx([100, 50])
    api.clipboard_fake({"files": [fixtures["svg"]]})
    r = api.clipboard_paste()
    assert r["kind"] == "files" and r["results"][0]["asset"]["variants"]["svg"]["src"] == fixtures["svg"]
    # The editor's copy: "own" until something else is copied
    n = api.clipboard_copied('figassemble:{"items": [], "assets": {}, "page": "p"}')
    assert api.clipboard_paste("auto", n) == {"kind": "own"} and api.clipboard_kinds(n) == {"available": True, "own": True}
    assert api.clipboard_paste()["kind"] == "objects"
    api.clipboard_fake({"text": "Newer"})
    assert api.clipboard_paste("auto", n)["kind"] == "text"


def test_fake_only_with_the_test_clipboard(monkeypatch):
    from figassemble.app.api import Api
    monkeypatch.delenv("FIGASSEMBLE_FAKE_CLIPBOARD", raising=False)
    with pytest.raises(PermissionError):
        Api().clipboard_fake({"text": "x"})


# The real clipboard on Windows, in CI (it would replace a person's clipboard) -----------------------

def _win_set(formats: dict) -> bool:
    """Put formats ({id or name: bytes}) on the Windows clipboard; False if it can't be opened."""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                  wintypes.HINSTANCE, wintypes.LPVOID]
    u.CreateWindowExW.restype = wintypes.HWND
    u.DestroyWindow.argtypes = [wintypes.HWND]
    u.OpenClipboard.argtypes, u.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    u.SetClipboardData.argtypes, u.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    u.RegisterClipboardFormatW.argtypes, u.RegisterClipboardFormatW.restype = [wintypes.LPCWSTR], wintypes.UINT
    k.GlobalAlloc.argtypes, k.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    k.GlobalLock.argtypes, k.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
    k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    # The clipboard needs an owner window to take data (a hidden one will do)
    hwnd = u.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)
    if not hwnd or not u.OpenClipboard(hwnd):
        return False
    try:
        u.EmptyClipboard()
        for fmt, data in formats.items():
            fmt = u.RegisterClipboardFormatW(fmt) if isinstance(fmt, str) else fmt
            h = k.GlobalAlloc(0x0002, len(data))
            p = k.GlobalLock(h)
            ctypes.memmove(p, data, len(data))
            k.GlobalUnlock(h)
            u.SetClipboardData(fmt, h)
    finally:
        u.CloseClipboard()
        u.DestroyWindow(hwnd)
    return True


def _cf_html(fragment: str) -> bytes:
    body = f"<html><body><!--StartFragment-->{fragment}<!--EndFragment--></body></html>".encode()
    header = b"Version:0.9\r\nStartHTML:%010d\r\nEndHTML:%010d\r\nStartFragment:%010d\r\nEndFragment:%010d\r\n"
    size = len(header % (0, 0, 0, 0))
    start = size + body.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
    return header % (size, size + len(body), start, size + body.index(b"<!--EndFragment-->")) + body + b"\x00"


@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("CI"), reason="the Windows clipboard, in CI only")
def test_windows_clipboard(fixtures):
    w = cb.WindowsClipboard()
    text = "Plain and bold".encode("utf-16-le") + b"\x00\x00"
    if not _win_set({13: text, "HTML Format": _cf_html("Plain and <b>bold</b>")}):
        pytest.skip("no clipboard on this machine")
    assert {"text", "html"} <= w.available()
    assert w.get("text") == "Plain and bold" and w.get("html") == "Plain and <b>bold</b>"
    kind, paras = cb.plan(w)
    assert kind == "text" and show(paras) == "Plain and *bold*"
    # Files copied in Explorer: a DROPFILES header, then the paths, each ending in a zero
    paths = [fixtures["pdf"], fixtures["svg"]]
    drop = struct.pack("<IiiII", 20, 0, 0, 0, 1) + "".join(p + "\x00" for p in paths).encode("utf-16-le") + b"\x00\x00"
    assert _win_set({15: drop})
    assert cb.plan(w) == ("files", paths)
    # A picture as PNG, and as a bitmap (what most programs copy)
    assert _win_set({"PNG": png((30, 15), dpi=144)})
    kind, (data, ext) = cb.plan(w)
    assert kind == "picture" and ext == ".png" and Image.open(io.BytesIO(data)).size == (30, 15)
    bmp = io.BytesIO()
    Image.new("RGB", (12, 6), (200, 10, 10)).save(bmp, "BMP")
    assert _win_set({8: bmp.getvalue()[14:]})   # CF_DIB: a BMP without its file header
    kind, (data, ext) = cb.plan(w)
    assert kind == "picture" and Image.open(io.BytesIO(data)).size == (12, 6)
    n = w.count()
    assert _win_set({13: "x".encode("utf-16-le") + b"\x00\x00"}) and w.count() != n


@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("CI"), reason="the Windows clipboard, in CI only")
def test_windows_clipboard_powerpoint(fixtures):
    """Slides and shapes copied in PowerPoint for Windows: its own formats, by name."""
    w = cb.WindowsClipboard()
    data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "powerpoint")
    with open(os.path.join(data, "copied_slide.slides"), "rb") as fh:
        slides = fh.read()
    with open(os.path.join(data, "copied_rect.gvml"), "rb") as fh:
        shapes = fh.read()
    if not _win_set({"PowerPoint 14.0 Slides Package": slides, "PNG": png()}):
        pytest.skip("no clipboard on this machine")
    kind, got = cb.plan(w)
    assert kind == "slides" and got["data"].startswith(slides) and got["source"] is None
    name, src = "PowerPoint\x00".encode("utf-16-le"), "C:\\Talks\\deck.pptx!2\x00".encode("utf-16-le")
    desc = struct.pack("<I16sIiiiiIII", 52 + len(name) + len(src), b"\x00" * 16, 1, 0, 0, 0, 0, 0, 52, 52 + len(name)) + name + src
    assert _win_set({"Art::GVML ClipFormat": shapes, "Object Descriptor": desc, "PNG": png()})
    kind, got = cb.plan(w)
    assert kind == "shapes" and got["data"].startswith(shapes) and got["source"] == "C:\\Talks\\deck.pptx"
    assert cb.plan(w, "picture")[0] == "picture"

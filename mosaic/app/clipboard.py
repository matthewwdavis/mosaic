"""The system clipboard, for Paste: files copied in the Finder or Explorer, slides and shapes
copied in PowerPoint (as editable objects), pictures (vector PDF or SVG where the copying app
offers one, else a bitmap), and text with its bold, italic and line breaks.

PowerPoint puts copied slides on the clipboard as a small deck ("PowerPoint 14.0 Slides
Package") and copied shapes as a DrawingML package ("Art::GVML ClipFormat"), with an OLE object
descriptor naming the deck they came from; on a Mac the same names, as com.microsoft.* types.

Read here, on mosaic's own side, rather than through the web view: a web page can't see
copied files or PDF data, and WebKit asks before handing over anything another app copied.

The editor's own copies are text starting "mosaic:". The editor writes them through the web
view and then notes the clipboard's change count, so a paste can tell whether its copy is still
the newest thing on the clipboard.

MOSAIC_FAKE_CLIPBOARD=1 swaps in a clipboard of mosaic's own (for the editor
self-test), so tests never touch the real one.
"""
from __future__ import annotations

import base64
import io
import os
import re
import sys
import time
from html.parser import HTMLParser

PREFIX = "mosaic:"
PICTURE_KINDS = ("pdf", "svg", "png", "tiff", "jpeg")
OFFICE_KINDS = ("slides", "shapes", "objdesc")   # PowerPoint's copied slides and shapes, and where they came from


# Text: paragraphs of runs ({"t", "bold", "italic"}); a line break inside a paragraph is a run
# of "\n", as the text editor stores Shift+Enter ----------------------------------------------

def split_paragraphs(runs: list[dict]) -> list[list[dict]]:
    """Runs whose text may hold paragraph and line breaks -> paragraphs of runs, merged by style."""
    paras: list[list[dict]] = [[]]
    for r in runs:
        style = {"bold": bool(r.get("bold")), "italic": bool(r.get("italic"))}
        text = r["t"].replace("\r\n", "\n").replace("\r", "\n").replace(" ", "\n")
        for i, part in enumerate(text.split("\n")):
            if i:
                paras.append([])
            for j, piece in enumerate(part.split(" ")):
                if j:
                    paras[-1].append({"t": "\n", **style})
                if piece:
                    paras[-1].append({"t": piece, **style})
    out = []
    for p in paras:
        merged: list[dict] = []
        for r in p:
            if merged and merged[-1]["t"] != "\n" and r["t"] != "\n" and \
                    (merged[-1]["bold"], merged[-1]["italic"]) == (r["bold"], r["italic"]):
                merged[-1]["t"] += r["t"]
            else:
                merged.append(dict(r))
        out.append(merged)
    while out and not out[-1]:
        out.pop()
    while out and not out[0]:
        out.pop(0)
    return out


def paragraphs_from_text(text: str) -> list[list[dict]]:
    return split_paragraphs([{"t": text}])


class _HtmlRuns(HTMLParser):
    """HTML -> runs with bold and italic: tags (b, strong, i, em, headings) and inline styles
    (font-weight, font-style), so Google Docs' <b style="font-weight:normal"> stays plain."""

    BLOCKS = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "blockquote",
              "pre", "dt", "dd", "section", "article", "header", "footer", "figcaption"}
    SKIP = {"style", "script", "head", "title", "template", "noscript"}
    VOID = {"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "wbr", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.runs: list[dict] = []
        self.stack = [(False, False, False)]   # bold, italic, preformatted
        self.skip = 0
        self.at_start = True   # of a paragraph: leading spaces are dropped, as HTML shows them

    def _break(self, kind: str) -> None:
        if self.runs and not self.at_start:
            self.runs.append({"t": kind, "bold": False, "italic": False})
        self.at_start = True

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if tag == "br":
            if self.runs:
                self.runs.append({"t": " ", "bold": False, "italic": False})
            self.at_start = True
            return
        if tag in self.VOID:
            return
        bold, italic, pre = self.stack[-1]
        if tag in ("b", "strong", "th") or re.fullmatch(r"h[1-6]", tag):
            bold = True
        if tag in ("i", "em", "cite", "var"):
            italic = True
        if tag == "pre":
            pre = True
        style = dict(attrs).get("style") or ""
        m = re.search(r"font-weight\s*:\s*([a-z0-9]+)", style, re.I)
        if m:
            w = m.group(1).lower()
            bold = w in ("bold", "bolder") or (w.isdigit() and int(w) >= 600)
        m = re.search(r"font-style\s*:\s*([a-z]+)", style, re.I)
        if m:
            italic = m.group(1).lower() in ("italic", "oblique")
        if tag in self.BLOCKS:
            self._break("\n")
        self.stack.append((bold, italic, pre))

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if tag in self.VOID:
            return
        if len(self.stack) > 1:
            self.stack.pop()
        if tag in self.BLOCKS:
            self._break("\n")

    def handle_data(self, data):
        if self.skip:
            return
        bold, italic, pre = self.stack[-1]
        if not pre:
            data = re.sub(r"[ \t\r\n\f]+", " ", data)
            if self.at_start:
                data = data.lstrip(" ")
            elif self.runs and self.runs[-1]["t"].endswith(" ") and data.startswith(" "):
                data = data[1:]
        if data:
            self.runs.append({"t": data, "bold": bold, "italic": italic})
            self.at_start = False


def paragraphs_from_html(html: str) -> list[list[dict]]:
    p = _HtmlRuns()
    p.feed(html)
    p.close()
    paras = split_paragraphs(p.runs)
    for para in paras:   # spaces left at the ends of lines by the markup
        if para and para[-1]["t"] != "\n":
            para[-1]["t"] = para[-1]["t"].rstrip(" ")
            if not para[-1]["t"]:
                para.pop()
    return [p for p in paras if p]


def cf_html_fragment(data: bytes) -> str:
    """Windows' "HTML Format": a header of byte offsets, then the HTML; the copied part only."""
    def offset(name: bytes) -> int | None:
        m = re.search(name + rb":(-?\d+)", data[:400])
        return int(m.group(1)) if m and int(m.group(1)) >= 0 else None
    start, end = offset(b"StartFragment"), offset(b"EndFragment")
    if start is None or end is None:
        start, end = offset(b"StartHTML"), offset(b"EndHTML")
    if start is None or end is None or end <= start:
        start, end = 0, len(data)
    return data[start:end].decode("utf-8", "replace")


def source_of_copy(data: bytes | None) -> str | None:
    """The file an Office copy came from, from its OLE object descriptor (the struct's
    dwSrcOfCopy: an offset to "path!slide number" in UTF-16), or None."""
    import struct
    if not data or len(data) < 52:
        return None
    off = struct.unpack_from("<I", data, 48)[0]
    if not 52 <= off < len(data):
        return None
    text = data[off:].decode("utf-16-le", "replace").split("\x00", 1)[0]
    m = re.fullmatch(r"(.+?)(![^\\/!]*)?", text)
    return m.group(1) if m and m.group(1) else None


# Backends: each says what's on the clipboard (available), hands over one kind (get), and
# counts changes (count) ------------------------------------------------------------------------

class FakeClipboard:
    """A clipboard of mosaic's own, for tests: contents set through the API."""

    def __init__(self):
        self.n = 0
        self.data: dict = {}

    def count(self) -> int:
        return self.n

    def available(self) -> set[str]:
        return {k for k, v in self.data.items() if v}

    def get(self, kind: str):
        return self.data.get(kind)

    def put(self, contents: dict) -> int:
        """{"text", "html", "files": [...]} as they are; picture and PowerPoint kinds as a file
        path, base64, or for "png" {"size": [w, h], "dpi": n} to draw one."""
        data = {}
        for kind, v in contents.items():
            if kind in PICTURE_KINDS and isinstance(v, dict):
                from PIL import Image
                buf = io.BytesIO()
                kw = {"dpi": (v["dpi"], v["dpi"])} if v.get("dpi") else {}
                Image.new("RGB", tuple(v["size"]), (40, 90, 200)).save(buf, "PNG" if kind == "png" else kind.upper(), **kw)
                v = buf.getvalue()
            elif kind in PICTURE_KINDS + OFFICE_KINDS and isinstance(v, str):
                if os.path.exists(v):
                    with open(v, "rb") as f:
                        v = f.read()
                else:
                    v = base64.b64decode(v)
            data[kind] = v
        self.data = data
        self.n += 1
        return self.n


class MacClipboard:
    TYPES = {"files": "public.file-url", "text": "public.utf8-plain-text", "html": "public.html", "rtf": "public.rtf",
             "pdf": "com.adobe.pdf", "png": "public.png", "tiff": "public.tiff", "jpeg": "public.jpeg",
             "slides": "com.microsoft.PowerPoint-14.0-Slides-Package", "shapes": "com.microsoft.Art--GVML-ClipFormat",
             "objdesc": "com.microsoft.Object-Descriptor"}

    def __init__(self):
        import AppKit
        self.AppKit = AppKit

    def _pb(self):
        return self.AppKit.NSPasteboard.generalPasteboard()

    def count(self) -> int:
        return int(self._pb().changeCount())

    def _types(self) -> list[str]:
        return [str(t) for t in (self._pb().types() or [])]

    def available(self) -> set[str]:
        types = self._types()
        have = {k for k, t in self.TYPES.items() if t in types}
        if "NSFilenamesPboardType" in types:
            have.add("files")
        if any("svg" in t.lower() for t in types):
            have.add("svg")
        return have

    def get(self, kind: str):
        pb, AppKit = self._pb(), self.AppKit
        if kind == "files":
            urls = pb.readObjectsForClasses_options_([AppKit.NSURL], {AppKit.NSPasteboardURLReadingFileURLsOnlyKey: True})
            return [str(u.path()) for u in urls or []]
        if kind == "text":
            s = pb.stringForType_(AppKit.NSPasteboardTypeString)
            return None if s is None else str(s)
        t = next((t for t in self._types() if "svg" in t.lower()), None) if kind == "svg" else self.TYPES.get(kind)
        data = pb.dataForType_(t) if t else None
        if data is None:
            return None
        data = bytes(data)
        return data.decode("utf-8", "replace") if kind == "html" else data

    def put_text(self, text: str, html: str | None = None) -> None:
        pb, AppKit = self._pb(), self.AppKit
        pb.clearContents()
        if html:
            pb.setString_forType_(html, AppKit.NSPasteboardTypeHTML)
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)


def put_text(cb, text: str, html: str | None = None) -> bool:
    """Text (and the same as HTML, for a word processor to keep its italics) onto the clipboard from
    mosaic itself; False where only the page can (Windows and Linux: navigator.clipboard)."""
    if isinstance(cb, FakeClipboard):
        cb.put({"text": text, **({"html": html} if html else {})})
        return True
    if isinstance(cb, MacClipboard):
        cb.put_text(text, html)
        return True
    return False


def paragraphs_from_rtf(data: bytes) -> list[list[dict]] | None:
    """RTF (as Word, TextEdit, Pages and Excel copy text on a Mac) -> paragraphs, through AppKit."""
    import AppKit
    import Foundation
    res = AppKit.NSAttributedString.alloc().initWithRTF_documentAttributes_(
        Foundation.NSData.dataWithBytes_length_(data, len(data)), None)
    text = res[0] if isinstance(res, tuple) else res
    if text is None:
        return None
    runs, i, n = [], 0, text.length()
    while i < n:
        attrs, rng = text.attributesAtIndex_effectiveRange_(i, None)
        if rng.length == 0:
            break
        font = attrs.get(AppKit.NSFontAttributeName) if attrs else None
        traits = int(font.fontDescriptor().symbolicTraits()) if font is not None else 0
        runs.append({"t": str(text.attributedSubstringFromRange_(rng).string()), "bold": bool(traits & 2),
                     "italic": bool(traits & 1)})
        i = rng.location + rng.length
    return split_paragraphs(runs)


class WindowsClipboard:
    CF_UNICODETEXT, CF_HDROP, CF_DIB, CF_DIBV5 = 13, 15, 8, 17
    NAMES = {"html": "HTML Format", "png": "PNG", "svg": "image/svg+xml", "slides": "PowerPoint 14.0 Slides Package",
             "shapes": "Art::GVML ClipFormat", "objdesc": "Object Descriptor"}

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        u = self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        k = self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        s = self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        u.OpenClipboard.argtypes, u.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
        u.CloseClipboard.argtypes, u.CloseClipboard.restype = [], wintypes.BOOL
        u.IsClipboardFormatAvailable.argtypes, u.IsClipboardFormatAvailable.restype = [wintypes.UINT], wintypes.BOOL
        u.GetClipboardData.argtypes, u.GetClipboardData.restype = [wintypes.UINT], wintypes.HANDLE
        u.RegisterClipboardFormatW.argtypes, u.RegisterClipboardFormatW.restype = [wintypes.LPCWSTR], wintypes.UINT
        u.GetClipboardSequenceNumber.argtypes, u.GetClipboardSequenceNumber.restype = [], wintypes.DWORD
        k.GlobalLock.argtypes, k.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
        k.GlobalUnlock.argtypes, k.GlobalUnlock.restype = [wintypes.HGLOBAL], wintypes.BOOL
        k.GlobalSize.argtypes, k.GlobalSize.restype = [wintypes.HGLOBAL], ctypes.c_size_t
        s.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        s.DragQueryFileW.restype = wintypes.UINT
        self.formats = {"text": self.CF_UNICODETEXT, "files": self.CF_HDROP}
        for kind, name in self.NAMES.items():
            self.formats[kind] = u.RegisterClipboardFormatW(name)

    def count(self) -> int:
        return int(self.user32.GetClipboardSequenceNumber())

    def _open(self) -> None:
        for _ in range(20):   # another program may have it open for a moment
            if self.user32.OpenClipboard(None):
                return
            time.sleep(0.01)
        raise OSError("the clipboard is in use by another program")

    def available(self) -> set[str]:
        have = {k for k, f in self.formats.items() if self.user32.IsClipboardFormatAvailable(f)}
        if self.user32.IsClipboardFormatAvailable(self.CF_DIB) or self.user32.IsClipboardFormatAvailable(self.CF_DIBV5):
            have.add("png")
        return have

    def _bytes(self, fmt: int) -> bytes | None:
        h = self.user32.GetClipboardData(fmt)
        if not h:
            return None
        p = self.kernel32.GlobalLock(h)
        if not p:
            return None
        try:
            return self.ctypes.string_at(p, self.kernel32.GlobalSize(h))
        finally:
            self.kernel32.GlobalUnlock(h)

    def get(self, kind: str):
        if kind == "png" and not self.user32.IsClipboardFormatAvailable(self.formats["png"]):
            # A bitmap (what most programs copy): Pillow reads it and makes a PNG
            from PIL import ImageGrab
            im = ImageGrab.grabclipboard()
            if im is None or isinstance(im, list):
                return None
            buf = io.BytesIO()
            dpi = im.info.get("dpi")
            im.save(buf, "PNG", **({"dpi": dpi} if dpi else {}))
            return buf.getvalue()
        if kind not in self.formats:
            return None
        self._open()
        try:
            if kind == "files":
                h = self.user32.GetClipboardData(self.CF_HDROP)
                if not h:
                    return []
                n = self.shell32.DragQueryFileW(h, 0xFFFFFFFF, None, 0)
                out = []
                for i in range(n):
                    size = self.shell32.DragQueryFileW(h, i, None, 0) + 1
                    buf = self.ctypes.create_unicode_buffer(size)
                    self.shell32.DragQueryFileW(h, i, buf, size)
                    out.append(buf.value)
                return out
            data = self._bytes(self.formats[kind])
        finally:
            self.user32.CloseClipboard()
        if data is None:
            return None
        if kind == "text":
            return data.decode("utf-16-le", "replace").split("\x00", 1)[0]
        if kind == "html":
            return cf_html_fragment(data.split(b"\x00", 1)[0])
        return data.rstrip(b"\x00") if kind == "svg" else data


class LinuxClipboard:
    """Linux's clipboard, read with the desktop's own tool: wl-paste on Wayland (wl-clipboard),
    xclip on X11. Neither there: no system clipboard (LookupError), and pastes are mosaic's own."""

    TYPES = {"files": ("text/uri-list",), "text": ("text/plain;charset=utf-8", "UTF8_STRING", "text/plain", "STRING"),
             "html": ("text/html",), "pdf": ("application/pdf",), "svg": ("image/svg+xml",), "png": ("image/png",),
             "tiff": ("image/tiff",), "jpeg": ("image/jpeg",)}

    def __init__(self):
        import shutil
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
            self.tool = "wl-paste"
        elif os.environ.get("DISPLAY") and shutil.which("xclip"):
            self.tool = "xclip"
        else:
            raise LookupError("no wl-paste or xclip")

    def _run(self, mime: str | None) -> bytes | None:
        """The clipboard as `mime` (None: the list of what it holds); None if it isn't there."""
        import subprocess
        if self.tool == "wl-paste":
            cmd = ["wl-paste", "--list-types"] if mime is None else ["wl-paste", "--no-newline", "--type", mime]
        else:
            cmd = ["xclip", "-selection", "clipboard", "-o", "-t", mime or "TARGETS"]
        try:
            got = subprocess.run(cmd, capture_output=True, timeout=3, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return got.stdout if got.returncode == 0 else None

    def _types(self) -> list[str]:
        return (self._run(None) or b"").decode("utf-8", "replace").split()

    def _mime(self, kind: str) -> str | None:
        types = self._types()
        return next((m for m in self.TYPES.get(kind, ()) if m in types), None)

    def count(self) -> int:
        """There's no count of changes to ask for: a number that differs when what's held does."""
        import zlib
        return zlib.crc32(" ".join(self._types()).encode() + b"\0" + (self._run(self._mime("text")) or b"")[:4096])

    def available(self) -> set[str]:
        types = set(self._types())
        return {k for k, mimes in self.TYPES.items() if types.intersection(mimes)}

    def get(self, kind: str):
        mime = self._mime(kind)
        data = self._run(mime) if mime else None
        if data is None:
            return None
        if kind == "files":
            from urllib.parse import unquote, urlsplit
            lines = [ln.strip() for ln in data.decode("utf-8", "replace").splitlines()]
            return [unquote(urlsplit(ln).path) for ln in lines if ln.startswith("file://")]
        return data.decode("utf-8", "replace") if kind in ("text", "html") else data


_fake: FakeClipboard | None = None


def backend():
    """The clipboard to read: the fake for tests, else the system's (on Linux through wl-paste or
    xclip), else None."""
    global _fake
    if os.environ.get("MOSAIC_FAKE_CLIPBOARD"):
        if _fake is None:
            _fake = FakeClipboard()
        return _fake
    try:
        if sys.platform == "darwin":
            return MacClipboard()
        if sys.platform == "win32":
            return WindowsClipboard()
        if sys.platform.startswith("linux"):
            return LinuxClipboard()
    except Exception:   # noqa: BLE001 (no AppKit, no user32, no wl-paste or xclip: no clipboard)
        return None
    return None


# What a paste puts on the page ------------------------------------------------------------

def _just_a_link(text: str) -> bool:
    return bool(re.fullmatch(r"\s*(https?|file)://\S+\s*", text))


def _has_dpi(png: bytes) -> bool:
    from PIL import Image
    try:
        dpi = Image.open(io.BytesIO(png)).info.get("dpi")
    except Exception:   # noqa: BLE001
        return False
    return bool(dpi and dpi[0] and float(dpi[0]) >= 2)


def tiff_to_png(data: bytes) -> bytes:
    """A TIFF as a PNG with the same resolution: its largest image, since a Mac puts a 1x and a
    2x version of a screenshot in one TIFF."""
    from PIL import Image, ImageSequence
    im = Image.open(io.BytesIO(data))
    frames = [(f.size[0] * f.size[1], f.copy(), dict(f.info)) for f in ImageSequence.Iterator(im)]
    _, best, info = max(frames, key=lambda x: x[0])
    if best.mode not in ("RGB", "RGBA", "L", "LA"):
        best = best.convert("RGBA" if "A" in best.mode else "RGB")
    buf = io.BytesIO()
    dpi = info.get("dpi")
    best.save(buf, "PNG", **({"dpi": tuple(float(v) for v in dpi)} if dpi else {}))
    return buf.getvalue()


def picture(cb, have: set[str]) -> tuple[bytes, str] | None:
    """The best picture on the clipboard: vector PDF or SVG, else a bitmap at its true size (a
    PNG that records its resolution, else a TIFF, which usually does, else any PNG or JPEG)."""
    for kind, ext in (("pdf", ".pdf"), ("svg", ".svg")):
        data = cb.get(kind) if kind in have else None
        if data:
            return data, ext
    png = cb.get("png") if "png" in have else None
    if png and _has_dpi(png):
        return png, ".png"
    tiff = cb.get("tiff") if "tiff" in have else None
    if tiff:
        try:
            return tiff_to_png(tiff), ".png"
        except Exception:   # noqa: BLE001 (an unreadable TIFF: try the others)
            pass
    if png:
        return png, ".png"
    jpeg = cb.get("jpeg") if "jpeg" in have else None
    return (jpeg, ".jpg") if jpeg else None


def text_paragraphs(cb, have: set[str], plain: str | None) -> list[list[dict]]:
    """Text with its bold, italic and line breaks: from RTF (Mac), else HTML (not tables, which
    read better as the plain tab-separated text), else the plain text."""
    if "rtf" in have and sys.platform == "darwin" and not isinstance(cb, FakeClipboard):
        try:
            paras = paragraphs_from_rtf(cb.get("rtf") or b"")
            if paras:
                return paras
        except Exception:   # noqa: BLE001
            pass
    html = cb.get("html") if "html" in have else None
    if html and not re.search(r"<table\b", html, re.I):
        paras = paragraphs_from_html(html)
        if paras:
            return paras
    return paragraphs_from_text(plain or "")


def plan(cb, mode: str = "auto", own_count: int | None = None) -> tuple[str, object]:
    """What a paste should do: ("own"|"objects"|"files"|"slides"|"shapes"|"picture"|"text"|"none"|
    "unavailable", data).

    The editor's own copy if it's still the newest thing; else copied files (placed linked);
    else mosaic objects copied in another document; else slides or shapes copied in
    PowerPoint ({"data", "source": the deck they came from, if known}); else text, or a picture
    where there's no text (or only a link to the picture). mode "picture" pastes the picture even
    with text, slides or shapes.
    """
    if cb is None:
        return "unavailable", None
    if own_count is not None and cb.count() == own_count:
        return "own", None
    have = cb.available()
    if "files" in have:
        files = [f for f in cb.get("files") or [] if os.path.isfile(f)]
        if files:
            return "files", files
    text = cb.get("text") if "text" in have else None
    if text and text.startswith(PREFIX):
        return "objects", text[len(PREFIX):]
    if mode != "picture":
        for kind in ("slides", "shapes"):
            data = cb.get(kind) if kind in have else None
            if data:
                return kind, {"data": data, "source": source_of_copy(cb.get("objdesc")) if "objdesc" in have else None}
    pictures = have & set(PICTURE_KINDS)
    if mode == "picture" or (pictures and (not text or not text.strip() or _just_a_link(text))):
        pic = picture(cb, have) if pictures else None
        if pic:
            return "picture", pic
        if mode == "picture":
            return "none", None
    if (text and text.strip()) or "html" in have:
        paras = text_paragraphs(cb, have, text)
        if paras:
            return "text", paras
    return "none", None


def kinds(cb, own_count: int | None = None) -> dict:
    """What's on the clipboard, for the menus (no pictures are read)."""
    if cb is None:
        return {"available": False}
    if own_count is not None and cb.count() == own_count:
        return {"available": True, "own": True}
    have = cb.available()
    text = cb.get("text") if "text" in have else None
    pictures = bool(have & set(PICTURE_KINDS))
    # "text": a plain paste makes a text box (so "Paste as picture" is worth offering)
    return {"available": True, "own": False, "files": "files" in have,
            "objects": bool(text and text.startswith(PREFIX)), "slides": "slides" in have, "shapes": "shapes" in have,
            "text": bool(text and text.strip() and not _just_a_link(text)) or ("html" in have and not pictures and not text),
            "picture": pictures}

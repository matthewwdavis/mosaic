"""The Mac app: mosaic.app runs Python from inside itself, so macOS takes the app's name
from it (packaging/macos/make_app.py), and the menu bar's pieces (mosaic/app/macmenu.py)."""
import os
import subprocess
import sys

import pytest

from mosaic.app import macmenu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mac = pytest.mark.skipif(sys.platform != "darwin", reason="a Mac's")


def test_shortcuts_as_menu_keys():
    cmd, shift, opt, ctrl = 1 << 20, 1 << 17, 1 << 19, 1 << 18
    assert macmenu.key_equivalent("⌘S") == ("s", cmd)
    assert macmenu.key_equivalent("⌘⇧S") == ("s", cmd | shift)
    assert macmenu.key_equivalent("⌘−") == ("-", cmd)   # (the editor writes a minus sign)
    assert macmenu.key_equivalent("⌘+") == ("+", cmd)
    assert macmenu.key_equivalent("⌃⌘F") == ("f", cmd | ctrl)
    assert macmenu.key_equivalent("⌥⌘H") == ("h", cmd | opt)
    for plain in ("Delete", "?", "I", None, ""):
        assert macmenu.key_equivalent(plain) is None   # plain keys stay the page's


@mac
def test_the_app_runs_python_from_inside_itself(tmp_path):
    subprocess.run([sys.executable, os.path.join(ROOT, "packaging", "macos", "make_app.py"), "--dest", str(tmp_path), "--no-register"],
                   check=True, capture_output=True)
    folder = tmp_path / "mosaic.app" / "Contents" / "MacOS"
    py = folder / "python"
    assert py.is_symlink() and os.path.realpath(py) == os.path.realpath(sys.executable)
    assert '"$(dirname "$0")/python" -m mosaic' in (folder / "mosaic").read_text()
    # (python-app, on macOS 26 and later: the same Python marked as made for this macOS, for today's
    # window buttons and title bar; the launcher runs it while it's a copy of the environment's)
    marked = folder / "python-app"
    for exe in [py] + ([marked] if marked.exists() else []):
        out = subprocess.run([str(exe), "-c", "import Foundation, sys; b = Foundation.NSBundle.mainBundle(); "
                              "print(b.infoDictionary()['CFBundleName']); print(b.bundlePath()); print(sys.prefix)"],
                             check=True, capture_output=True, text=True).stdout.splitlines()
        assert out[0] == "mosaic" and out[1].endswith("mosaic.app"), exe
        assert os.path.realpath(out[2]) == os.path.realpath(sys.prefix), exe   # its own environment, found from there
    if int(__import__("platform").mac_ver()[0].split(".")[0]) >= 26:
        assert marked.is_symlink() and '"$here/python-app" -m mosaic' in (folder / "mosaic").read_text()


@mac
def test_menus_from_the_editors_description():
    import AppKit
    macmenu._state.update(items={}, recent=None)
    target = macmenu._target()
    menu = AppKit.NSMenu.alloc().initWithTitle_("File")
    macmenu._fill(menu, [{"title": "Save", "action": "save", "keys": "⌘S"}, "-", {"title": "Open Recent", "recent": True},
                         {"title": "Rulers", "action": "toggleRulers", "keys": "⌘R", "check": True},
                         {"title": "Close", "selector": "performClose:", "keys": "⌘W"},
                         {"title": "Preview", "items": [{"title": "Greyscale", "action": "vision:greyscale", "check": False}]},
                         {"title": "Guide", "url": "https://example.org/guide"}])
    assert [str(i.title()) for i in menu.itemArray()] == ["Save", "", "Open Recent", "Rulers", "Close", "Preview", "Guide"]
    save, close = menu.itemAtIndex_(0), menu.itemAtIndex_(4)
    assert save.keyEquivalent() == "s" and save.keyEquivalentModifierMask() == 1 << 20
    assert save.representedObject() == "save" and save.target() == target
    assert str(close.action()) == "performClose:" and close.target() is None   # AppKit's own, along the responder chain
    assert menu.itemAtIndex_(6).representedObject() == "url:https://example.org/guide"
    macmenu.set_checks({"toggleRulers": False, "vision:greyscale": True})
    assert menu.itemAtIndex_(3).state() == 0 and menu.itemAtIndex_(5).submenu().itemAtIndex_(0).state() == 1
    macmenu.set_recent(["/no/such/folder/fig one.mosaic", __file__])
    recent = menu.itemAtIndex_(2).submenu()
    assert [str(i.title()) for i in recent.itemArray()] == ["fig one.mosaic", os.path.basename(__file__), "", "Clear Menu"]
    assert not recent.itemAtIndex_(0).isEnabled() and recent.itemAtIndex_(1).isEnabled()   # gone; there
    assert recent.itemAtIndex_(1).representedObject() == f"open:{__file__}"
    macmenu.set_recent([])
    assert [str(i.title()) for i in recent.itemArray()] == ["Clear Menu"] and not recent.itemAtIndex_(0).isEnabled()

"""The Mac app: mosaic.app runs Python inside its own program, so macOS takes the app's name
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
    """mosaic.app's program is labapp's launcher, running this environment's Python inside itself:
    macOS sees mosaic (its name in the menu bar and privacy prompts, its icon), not a Python."""
    subprocess.run([sys.executable, os.path.join(ROOT, "packaging", "macos", "make_app.py"), "--dest", str(tmp_path), "--no-register"],
                   check=True, capture_output=True)
    app = tmp_path / "mosaic.app"
    program = app / "Contents" / "MacOS" / "mosaic"
    assert os.listdir(program.parent) == ["mosaic"]   # (nothing linked to outside the app)
    assert "module=mosaic" in (app / "Contents" / "Resources" / "launcher.txt").read_text().splitlines()
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "sitecustomize.py").write_text(
        "import Foundation, sys\nb = Foundation.NSBundle.mainBundle()\n"
        "print(b.infoDictionary()['CFBundleName']); print(b.bundlePath()); print(sys.prefix); print(sys.executable)\n"
        "sys.stdout.flush(); import os; os._exit(0)\n")   # (before mosaic itself starts)
    out = subprocess.run([str(program)], env=dict(os.environ, PYTHONPATH=str(probe)), check=True, capture_output=True,
                         text=True, timeout=60).stdout.splitlines()
    assert out[0] == "mosaic" and out[1] == str(app)
    assert os.path.realpath(out[2]) == os.path.realpath(sys.prefix)   # its own environment, found from there
    assert out[3] == sys.executable   # (what it runs for exports and other work in the background)
    signed = subprocess.run(["/usr/bin/codesign", "-dv", str(app)], capture_output=True, text=True).stderr
    assert "Identifier=io.github.matthewwdavis.mosaic" in signed
    assert subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(app)], capture_output=True).returncode == 0


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

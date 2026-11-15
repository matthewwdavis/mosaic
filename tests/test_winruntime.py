"""Windows needs the WebView2 runtime for mosaic's window (mosaic/app/winruntime.py): mosaic
looks for it where Microsoft says, and elsewhere there's nothing to look for."""
import sys
import types

import pytest

from mosaic.app import winruntime


def fake_winreg(values):
    """A stand-in registry: {(root, key): version}."""
    class Key:
        def __init__(self, v):
            self.v = v

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def open_key(root, key):
        if (root, key) not in values:
            raise OSError("no such key")
        return Key(values[(root, key)])
    return types.SimpleNamespace(HKEY_LOCAL_MACHINE="HKLM", HKEY_CURRENT_USER="HKCU", OpenKey=open_key,
                                 QueryValueEx=lambda k, name: (k.v, 1))


def test_the_runtime_is_found_for_every_account_or_this_one(monkeypatch):
    client = winruntime._CLIENT
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({("HKCU", "Software\\" + client): "131.0.2903.86"}))
    assert winruntime.webview2_version() == "131.0.2903.86"
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({("HKLM", "SOFTWARE\\WOW6432Node\\" + client): "0.0.0.0"}))
    assert winruntime.webview2_version() is None   # (what an uninstall leaves behind)
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({}))
    assert winruntime.webview2_version() is None


@pytest.mark.skipif(sys.platform == "win32", reason="not Windows'")
def test_elsewhere_there_is_nothing_to_look_for():
    assert winruntime.ensure() is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows'")
def test_this_pc_has_it():
    assert winruntime.webview2_version()   # (GitHub's Windows machines do, as Windows 11 does)

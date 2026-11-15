"""Windows shows an app's window with Microsoft Edge WebView2. Windows 11 has it, and so do
nearly all Windows 10 PCs; one without it would fall back to Internet Explorer's engine, which
can't run the editor (a blank window). So the app looks before opening a window and, if it's
missing, says so and offers Microsoft's download page."""
from __future__ import annotations

import sys

DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/webview2/#download"
_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"   # the Evergreen runtime


def webview2_version() -> str | None:
    """The installed WebView2 runtime's version, or None (where Microsoft says to look: for
    every account, 64- and 32-bit, then this account's)."""
    import winreg
    places = [(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + _CLIENT),
              (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + _CLIENT),
              (winreg.HKEY_CURRENT_USER, "Software\\" + _CLIENT)]
    for root, key in places:
        try:
            with winreg.OpenKey(root, key) as k:
                version = str(winreg.QueryValueEx(k, "pv")[0] or "")
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return version
    return None


def ensure(app: str) -> bool:
    """Whether the app's window can open; if not, the person is told why and offered the download."""
    if sys.platform != "win32":
        return True
    try:
        if webview2_version():
            return True
    except Exception as exc:   # noqa: BLE001 (couldn't look: go on, as before)
        print(f"Couldn't look for WebView2: {exc}", file=sys.stderr, flush=True)
        return True
    import ctypes
    import webbrowser
    text = (f"{app} needs Microsoft Edge WebView2 to show its window, and this PC doesn't have it.\n\n"
            "Choose OK to open Microsoft's download page (pick the Evergreen Bootstrapper), install it, "
            f"then start {app} again.")
    if ctypes.windll.user32.MessageBoxW(None, text, app, 0x1 | 0x30) == 1:   # OK/Cancel, warning; 1 = OK
        webbrowser.open(DOWNLOAD)
    return False

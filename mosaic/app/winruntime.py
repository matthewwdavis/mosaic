"""Windows shows mosaic's window with Microsoft Edge WebView2; a PC without it is told so and
offered Microsoft's download page before a blank window opens (the shared library's:
_labapp/winruntime.py, `shared` here)."""
from __future__ import annotations

from .._labapp import winruntime as shared
from .._labapp.winruntime import _CLIENT, DOWNLOAD, webview2_version   # noqa: F401


def ensure() -> bool:
    """Whether mosaic's window can open; if not, the person is told why and offered the download."""
    return shared.ensure("mosaic")

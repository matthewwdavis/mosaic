"""The document's name in a window's title bar, on a Mac: double-click it to rename the file
(the editor's Rename dialog, app.rename in main.js), or right-click it for Rename, Show in Finder,
Copy File Path and the folders it's in. The work is the shared library's (_labapp/mac/title.py);
this says what is mosaic's: which file a window has open and how its editor runs a command."""
from __future__ import annotations

import json

from .._labapp.mac import title as _shared
from .._labapp.mac.title import act, build_menu, on_press, path_chain, run_in_editor, smoke   # noqa: F401

_state = _shared._state


def install(api) -> None:
    """Watch presses on mosaic's windows' titles (once; on the main thread)."""
    def path_of(uid: str) -> str | None:
        for w in list(api._windows.values()):
            if getattr(w, "uid", None) == uid:
                return api._doc_of(w).get("path")
        return None
    _shared.install(api, path_of, lambda command: f"window.FA && window.FA.app.menu({json.dumps(command)})",
                    sample=("Figures", "figure_3.mosaic"))

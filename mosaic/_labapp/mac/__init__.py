"""The Mac's own parts of an app (AppKit, through PyObjC): the menu bar, the title bar's name.
Nothing here is imported on another system."""
from __future__ import annotations

import threading


def on_main(fn, timeout: float = 5.0):
    """Run fn on the main (AppKit) thread and return its result."""
    from PyObjCTools import AppHelper
    done, out = threading.Event(), {}

    def call():
        try:
            out["value"] = fn()
        except Exception as err:  # noqa: BLE001 (handed back to the calling thread)
            out["error"] = err
        done.set()
    AppHelper.callAfter(call)
    if not done.wait(timeout):
        raise TimeoutError("the main thread didn't answer")
    if "error" in out:
        raise out["error"]
    return out.get("value")

"""mosaic's icon (mosaic/icon.py): light and dark, the panels the same in both; on a Mac the Dock
icon follows the system's appearance (_labapp/mac/dockicon.py)."""
import sys

import pytest

from mosaic import icon


def test_the_icon_has_a_light_and_a_dark_appearance_with_the_same_panels():
    light, dark = icon.draw_icon(256), icon.draw_icon(256, "dark")
    assert light.size == dark.size == (256, 256) and light.getpixel((0, 0))[3] == 0   # (clear corners)
    middle_of_tile = (128, 40)   # (above the panels)
    assert sum(light.getpixel(middle_of_tile)[:3]) > 700 and sum(dark.getpixel(middle_of_tile)[:3]) < 150
    for (x0, y0, x1, y1), rgb in icon.ICON_TILES:   # (each panel its own colour, in both)
        at = (round((x0 + x1) / 2 * 256), round((y0 + y1) / 2 * 256))
        assert light.getpixel(at)[:3] == rgb and dark.getpixel(at)[:3] == rgb
    assert icon.png(64, "dark")[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.skipif(sys.platform != "darwin", reason="a Mac's Dock")
def test_the_dock_icon_is_the_one_for_the_systems_appearance(monkeypatch):
    import AppKit

    from mosaic._labapp.mac import dockicon
    AppKit.NSApplication.sharedApplication()
    shown = []
    monkeypatch.setattr(dockicon, "_state", {"light": icon.png(64), "dark": icon.png(64, "dark")})
    monkeypatch.setattr(dockicon, "_image", lambda data: shown.append(data) or None)   # (no real Dock in a test)
    monkeypatch.setattr(dockicon, "is_dark", lambda: True)
    assert dockicon.apply() == "dark" and shown[-1] == dockicon._state["dark"]
    monkeypatch.setattr(dockicon, "is_dark", lambda: False)
    assert dockicon.apply() == "light" and shown[-1] == dockicon._state["light"]

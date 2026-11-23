"""Liquid Glass (View > Glass): text over the glass stays readable in every theme. Each theme's
see-through amounts (themes.py glass_amounts, written into the page with its colours) over the worst
the Mac's glass shows behind a window (_labapp/glass.py WORST: the light glass over black, the dark
glass over white) keep 4.5:1 for the text and the grey text on the ribbon, tool bar, panels and
status bar, at every level; menus and dialogs too, over the glass and over a white or black page.
And the app's side: set_glass hands the level to labapp."""
import re
from pathlib import Path

import pytest

from mosaic import themes
from mosaic._labapp import glass

GLASS_CSS = (Path(__file__).resolve().parents[1] / "mosaic" / "ui" / "css" / "glass.css").read_text()


def written(theme_id: str) -> dict:
    """The --glass-* amounts (0-1) as the page gets them for a theme."""
    css = themes.css(theme_id)
    return {k: int(v) / 100 for k, v in re.findall(r"--glass-(subtle|standard|clear|pop|shade|muted): (\d+)%", css)}


@pytest.mark.parametrize("theme", themes.THEMES, ids=lambda t: t["id"])
def test_chrome_and_menus_read_over_the_glass(theme):
    got = written(theme["id"])
    assert set(got) == {"subtle", "standard", "clear", "pop", "shade", "muted"}
    c, dark = theme["colors"], theme["dark"]
    inks = [c["text"], glass.mix(c["muted"], c["text"], got["muted"])]
    panels = [glass.mix(c[k], "#000000", got["shade"]) for k in ("panel", "panel2", "hover")]
    look = "dark" if dark else "light"
    for level in ("subtle", "standard", "clear"):
        for ink in inks:
            for p in panels:
                r = glass.worst_contrast(ink, p, got[level], dark)
                assert r >= 4.5, f"{theme['id']} at {level}: {r:.2f}"
    backs = [glass.WORST[(m, look)] for m in ("glass", "vibrancy")] + [0, 255]
    for ink in inks:
        for b in backs:
            r = glass.contrast(ink, glass.mix(c["panel"], (b,) * 3, got["pop"]))
            assert r >= 4.5, f"{theme['id']} menus over {b}: {r:.2f}"


def test_levels_and_increase_contrast():
    light, dark = written("light"), written("dark")
    for amounts in (light, dark):
        assert amounts["subtle"] > amounts["standard"] > amounts["clear"]
    assert written("contrast")["standard"] == 1.0   # (High contrast: solid)
    assert re.search(r':root\[data-glass-contrast="more"\]:not\(\[data-glass="off"\]\) \{ --glass-a: 9\d%', GLASS_CSS)
    assert ".stage-wrap { background: var(--stage); }" in GLASS_CSS   # (the canvas stays solid)


def test_system_themes_carry_both_amounts():
    css = themes.css("system", "light", "dark")
    assert css.count("--glass-standard:") == 2   # (the day theme's, and the night theme's in the dark)


def test_set_glass_hands_the_level_to_labapp(monkeypatch):
    from mosaic.app.api import Api
    got = {}

    def fake_apply(window, level, titlebar=None):
        got.update(window=window, level=level, titlebar=titlebar)
        return glass.state(level, {"reduceTransparency": True, "increaseContrast": False}, "glass")
    monkeypatch.setattr(glass, "apply", fake_apply)
    monkeypatch.setattr(glass, "watch", lambda cb: got.setdefault("watched", cb))
    api = Api.__new__(Api)
    api._windows, api._caller = {"1": "window one"}, type("C", (), {"win": "1"})()
    st = api.set_glass("subtle", [255, 255, 255, 0.85])
    assert got["window"] == "window one" and got["level"] == "subtle" and got["titlebar"] == [255, 255, 255, 0.85]
    assert st["effective"] == "off" and st["reduceTransparency"] and callable(got["watched"])

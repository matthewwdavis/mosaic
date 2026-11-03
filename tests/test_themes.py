"""Interface themes (mosaic/themes.py): readable in every theme, and applied from the first paint."""
import os
import re
import urllib.request

from mosaic import themes

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mosaic", "ui")


def test_every_theme_is_readable():
    # Text and hints 4.5:1 on every surface they sit on; selection, guides and focus 3:1 on the
    # page, the area around it and the panels (WCAG 2.1, 1.4.3 and 1.4.11)
    problems = [p for t in themes.THEMES for p in themes.check(t)]
    assert problems == []


def test_themes_are_complete():
    ids = [t["id"] for t in themes.THEMES]
    assert len(ids) == len(set(ids)) == 22
    for t in themes.THEMES:
        assert set(t["colors"]) == set(themes.VARS), t["id"]
        assert t["group"] in themes.GROUPS
        assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in t["colors"].values()), t["id"]
        # Dark themes have dark panels, light ones light panels (form controls follow color-scheme)
        assert (themes._luminance(t["colors"]["panel"]) < 0.2) == t["dark"], t["id"]


def test_css_for_a_theme_and_for_day_and_night():
    one = themes.css("dracula")
    assert "--panel: #282a36" in one and "color-scheme: dark" in one and "prefers-color-scheme" not in one
    both = themes.css("system", "pistachio", "monokai")
    day, night = both.split("@media (prefers-color-scheme: dark)")
    assert "--panel: #fbfaf2" in day and "--panel: #272822" in night
    assert "--panel: #ffffff" in themes.css("no-such-theme")   # an unknown theme falls back to Light
    assert "prefers-contrast: more" in one


def test_css_fallback_is_the_light_theme():
    # app.css's own colours (used only if the theme style were missing) stay the Light theme's
    with open(os.path.join(UI, "css", "app.css"), encoding="utf-8") as f:
        root = f.read().split(":root {", 1)[1].split("}", 1)[0]
    css = dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-f]{6})", root))
    light = themes.BY_ID["light"]["colors"]
    assert {themes.VARS[k]: v for k, v in light.items()} == {k: css[k] for k in themes.VARS.values()}


def test_server_writes_the_chosen_theme_into_the_page():
    from mosaic.app.api import Api
    from mosaic.app.server import start_server
    api = Api()
    api.prefs_set({"theme": "walnut"})
    srv = start_server(api)
    try:
        html = urllib.request.urlopen(srv.url + "ui/index.html").read().decode("utf-8")
    finally:
        srv.shutdown()
        api.prefs_set({"theme": "system"})
    assert '<style id="theme-vars">:root { --bg: #2a1d14' in html
    assert [t["id"] for t in api.app_info()["themes"]] == [t["id"] for t in themes.THEMES]

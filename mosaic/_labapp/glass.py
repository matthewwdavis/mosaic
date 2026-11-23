"""Liquid Glass (View ▸ Glass): the window's ribbon, side panes and status bar show what's behind
the window, blurred, as the Mac's own apps do; the page (mosaic: the canvas) stays solid.

Four levels: Off, Subtle, Standard and Clear. On a Mac the glass is the system's own (macOS 26 and
later: Liquid Glass; before that, the frosted material Finder's sidebar uses), put behind the
window's web view (mac/glass.py). The level is how much of the app's own colour the page paints
over it: the page's stylesheet holds those amounts, as see-through versions of its colours.
Windows and Linux have no glass behind a web view: the page imitates it, frosted, with the blur
of what's under its pop-ups and menus (material "css").

The system's Reduce Transparency setting turns glass off whatever the level (on Windows,
Settings ▸ Personalization ▸ Colors ▸ Transparency effects); Increase Contrast is passed to the
page, which then paints its chrome nearly solid.

Text over glass must stay readable over anything behind the window. WORST holds what each
material shows over the worst thing behind it (measured on a Mac: the light glass over black,
the dark glass over white, nothing of the page's over it); worst_contrast() is the contrast of
text over a page colour at an amount over that, which the apps' tests hold to 4.5:1.
"""
from __future__ import annotations

import os
import sys

LEVELS = ("off", "subtle", "standard", "clear")
DEFAULT = "standard"
NAMES = {"off": "Off", "subtle": "Subtle", "standard": "Standard", "clear": "Clear"}

# What the glass alone shows (sRGB grey) over the worst backdrop, by material and appearance
WORST = {("glass", "light"): 154, ("glass", "dark"): 141,
         ("vibrancy", "light"): 213, ("vibrancy", "dark"): 105}


def level_of(value) -> str:
    """A level, from a saved setting (anything else: the default)."""
    return value if value in LEVELS else DEFAULT


def material() -> str:
    """"glass" (macOS 26 and later), "vibrancy" (older macOS) or "css" (Windows, Linux)."""
    if sys.platform == "darwin":
        try:
            from .mac import glass as macglass
            return macglass.material()
        except Exception:   # noqa: BLE001 (no AppKit: the page's own imitation)
            return "css"
    return "css"


def _windows_transparency_off() -> bool:
    """Windows' Transparency effects switched off (Settings ▸ Personalization ▸ Colors)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "EnableTransparency")[0] == 0
    except Exception:   # noqa: BLE001 (not set: transparency is on)
        return False


def system() -> dict:
    """The system's settings that change glass: Reduce Transparency, Increase Contrast.
    (LABAPP_REDUCE_TRANSPARENCY=1 stands in for the first, for tests.)"""
    out = {"reduceTransparency": False, "increaseContrast": False}
    if sys.platform == "darwin":
        try:
            from .mac import glass as macglass
            out = macglass.system()
        except Exception:   # noqa: BLE001 (no AppKit)
            pass
    elif os.name == "nt":
        out["reduceTransparency"] = _windows_transparency_off()
    if os.environ.get("LABAPP_REDUCE_TRANSPARENCY") == "1":
        out["reduceTransparency"] = True
    return out


def state(level, settings: dict | None = None, kind: str | None = None) -> dict:
    """What a window gets for a level: {"level", "effective" (Off when the system reduces
    transparency), "material", "reduceTransparency", "increaseContrast"}."""
    level = level_of(level)
    settings = settings if settings is not None else system()
    kind = kind or material()
    effective = "off" if settings.get("reduceTransparency") else level
    return {"level": level, "effective": effective, "material": kind, **settings}


def apply(window, level, titlebar=None) -> dict:
    """Glass at a level in a pywebview window: the Mac's own glass behind it, nothing elsewhere
    (the page imitates it). titlebar: the title bar's tint on a Mac, [r, g, b (0-255), a (0-1)].
    Returns state(level), for the page to paint itself to match."""
    st = state(level)
    if sys.platform == "darwin" and st["material"] != "css":
        from .mac import glass as macglass
        macglass.apply(window, st["effective"], titlebar)
    return st


def watch(callback) -> None:
    """callback(system()) when the system's settings change (a Mac; elsewhere they're read again
    when the page next applies its level)."""
    if sys.platform == "darwin":
        try:
            from .mac import glass as macglass
            macglass.watch(callback)
        except Exception as exc:   # noqa: BLE001 (the page reads them again on its next change)
            print(f"Glass: the system's settings can't be watched: {exc}", file=sys.stderr, flush=True)


# Contrast (WCAG 2) -----------------------------------------------------------------------------

def _rgb(colour) -> tuple:
    if isinstance(colour, str):
        h = colour.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(colour[:3])


def luminance(colour) -> float:
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def mix(a, b, amount: float) -> tuple:
    """a at this amount (0-1) over b, as CSS color-mix(in srgb, a amount, b) gives."""
    a, b = _rgb(a), _rgb(b)
    return tuple(x * amount + y * (1 - amount) for x, y in zip(a, b))


def worst_contrast(text, panel, amount: float, dark: bool) -> float:
    """Text over a page colour painted at this amount (0-1) over the glass, with the worst thing
    behind the window, the lower of the two Mac materials."""
    look = "dark" if dark else "light"
    return min(contrast(text, mix(panel, (WORST[(m, look)],) * 3, amount)) for m in ("glass", "vibrancy"))

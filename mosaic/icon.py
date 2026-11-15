"""mosaic's icon: figure panels of different sizes fitted together as tiles, in the
colour-blind-safe Okabe-Ito colours, on a rounded tile. Two appearances: light (an off-white tile
with a dark edge) and dark (a charcoal tile with a grey edge), the panels the same in both.

The installers draw the app's icon from here (packaging/macos/make_app.py and the Windows and Linux
scripts: the light one). On a Mac the icon follows the system's appearance: on macOS 26 and later
the app carries packaging/macos/Assets.car (made from icon_document()), which macOS draws light or
dark by itself; otherwise the running app's Dock icon is switched (app/window.py, through
_labapp/mac/dockicon.py).

    python -m mosaic.icon        # writes packaging/macos/mosaic.icon again (after a change of design)
"""
from __future__ import annotations

import io

# (x0, y0, x1, y1) as fractions of the icon's width
ICON_TILES = [((0.2, 0.2, 0.55, 0.52), (0, 114, 178)), ((0.585, 0.2, 0.8, 0.36), (230, 159, 0)),
              ((0.585, 0.395, 0.8, 0.52), (86, 180, 233)), ((0.2, 0.555, 0.36, 0.8), (0, 158, 115)),
              ((0.395, 0.555, 0.8, 0.68), (213, 94, 0)), ((0.395, 0.715, 0.6, 0.8), (240, 228, 66)),
              ((0.635, 0.715, 0.8, 0.8), (204, 121, 167))]
LOOKS = {"light": {"tile": (250, 250, 247, 255), "edge": (40, 40, 38, 255)},
         "dark": {"tile": (38, 39, 43, 255), "edge": (112, 114, 120, 255)}}


def draw_icon(size: int, appearance: str = "light"):
    """A rounded tile holding the mosaic, drawn four times as big and scaled down, for smooth edges."""
    from PIL import Image, ImageDraw
    look = LOOKS["dark" if appearance == "dark" else "light"]
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = round(s * 0.09)
    d.rounded_rectangle((pad, pad, s - pad, s - pad), radius=round(s * 0.2), fill=look["tile"],
                        outline=look["edge"], width=max(4, round(s * 0.02)))
    for (x0, y0, x1, y1), rgb in ICON_TILES:
        d.rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), radius=round(s * 0.018), fill=rgb + (255,))
    return im.resize((size, size), Image.LANCZOS)


def panels(size: int = 1024):
    """The panels alone, on a clear ground: the layer of the Mac's Icon Composer document
    (packaging/macos/mosaic.icon), where macOS draws the tile itself, off-white or charcoal."""
    from PIL import Image, ImageDraw
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for (x0, y0, x1, y1), rgb in ICON_TILES:
        d.rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), radius=round(s * 0.018), fill=rgb + (255,))
    return im.resize((size, size), Image.LANCZOS)


def icon_document(folder: str) -> None:
    """mosaic.icon: the panels over a tile that's off-white in Light mode and charcoal in Dark.
    labapp's tools/make_mac_icon.py compiles it into packaging/macos/Assets.car."""
    import json
    import os
    os.makedirs(os.path.join(folder, "Assets"), exist_ok=True)
    panels().save(os.path.join(folder, "Assets", "panels.png"), optimize=True)
    srgb = lambda c: "srgb:" + ",".join(f"{v / 255:.5f}" for v in c[:3]) + ",1.00000"   # noqa: E731
    doc = {"fill-specializations": [{"value": {"solid": srgb(LOOKS["light"]["tile"])}},
                                    {"appearance": "dark", "value": {"solid": srgb(LOOKS["dark"]["tile"])}}],
           "groups": [{"layers": [{"image-name": "panels.png", "name": "panels", "glass": False}],
                       "shadow": {"kind": "none", "opacity": 0.5}, "translucency": {"enabled": False, "value": 0.5}}],
           "supported-platforms": {"squares": ["macOS"]}}
    with open(os.path.join(folder, "icon.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def png(size: int = 512, appearance: str = "light") -> bytes:
    out = io.BytesIO()
    draw_icon(size, appearance).save(out, "PNG")
    return out.getvalue()


if __name__ == "__main__":
    import os
    doc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packaging", "macos", "mosaic.icon")
    icon_document(doc)
    print(doc)

"""mosaic's icon: figure panels of different sizes fitted together as tiles, in the
colour-blind-safe Okabe-Ito colours, on a rounded tile. Two appearances: light (an off-white tile
with a dark edge) and dark (a charcoal tile with a grey edge), the panels the same in both.

The installers draw the app's icon from here (packaging/macos/make_app.py and the Windows and Linux
scripts: the light one), and on a Mac the running app's Dock icon follows the system's appearance
(app/window.py, through _labapp/mac/dockicon.py).
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


def png(size: int = 512, appearance: str = "light") -> bytes:
    out = io.BytesIO()
    draw_icon(size, appearance).save(out, "PNG")
    return out.getvalue()

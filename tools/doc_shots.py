"""Screenshots for the README, the tutorial and the user guide, taken in the real editor.

    python tools/doc_shots.py [scene ...]        (writes docs/images/; all scenes by default)

Each scene (figassemble/ui/js/docshots.js) builds the tutorial figure from the sample plots in
examples/ up to one step. Headless Chrome takes each picture at twice the window's size, then it's
scaled down so the text stays crisp; some are cropped to the part that matters, and the window
tour gets numbered callouts. Run it again whenever the interface changes.
"""
import os
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from ui_selftest import find_chrome  # noqa: E402

OUT = os.path.join(ROOT, "docs", "images")
W, H, SCALE = 1440, 900, 2
# scene -> crop (x0, y0, x1, y1) in window pixels, or None for the whole window
SCENES = {
    "window": None, "page-size": (1176, 98, 1440, 640), "placed": None, "snapping": None, "arrange": None,
    "group": (405, 140, 1065, 600),
    "labels": None, "annotated": None, "style": (1176, 98, 1440, 900), "check": (380, 270, 1060, 630),
    "export": (380, 60, 1060, 860), "shapes": (200, 98, 760, 900), "guides": None, "result": None, "themes": (468, 63, 972, 838), "areafill": None,
    "swatches": (420, 40, 1020, 880), "isolation": (200, 98, 1180, 640), "cropshape": (420, 98, 1440, 640), "zoominset": (200, 300, 1180, 820), "brackets": (200, 98, 1440, 700), "search": (380, 60, 1060, 640), "distances": (290, 200, 1170, 560), "attached": (560, 98, 1440, 672), "plotsnap": (296, 262, 1166, 556), "gridlayout": (410, 98, 1440, 860), "symbols": (290, 300, 1440, 730), "objectstyles": (1176, 98, 1440, 520), "equation": (560, 160, 1440, 540), "report": (466, 216, 974, 684), "pen": (490, 290, 970, 590), "elbow": (396, 226, 1150, 672), "objects": (0, 98, 211, 462),
    "slides": (345, 297, 1095, 603), "selectsame": (380, 135, 1000, 725),
}
# Numbered callouts on the window tour: (x, y) in window pixels, in the order the tutorial lists them
TOUR = [(412, 22), (905, 62), (1042, 18), (78, 120), (238, 780), (304, 450), (1262, 124), (1038, 884)]


def example_deck(tmp: str) -> str:
    """A small PowerPoint deck of the example plots, for the slide picker's picture: a title
    slide, then the plots with panel labels, the last slide hidden."""
    from pptx import Presentation
    from pptx.util import Emu, Pt
    ex = os.path.join(ROOT, "examples")
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    title = prs.slides.add_slide(prs.slide_layouts[0])
    title.shapes.title.text = "Example figures"
    title.placeholders[1].text = "The tutorial's plots"
    labels = iter("abcd")
    for plots, hidden in ((["dose_response"], False), (["expression_bars", "growth_curves"], False), (["growth_curves"], True)):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        width = 840 / len(plots)
        for i, name in enumerate(plots):
            x = 60 + (900 - width * len(plots)) / 2 + width * i
            s.shapes.add_picture(os.path.join(ex, f"{name}.png"), Pt(x + 20), Pt(70), width=Pt(width - 40))
            box = s.shapes.add_textbox(Pt(x), Pt(46), Pt(30), Pt(30))
            box.text_frame.text = next(labels)
            box.text_frame.paragraphs[0].runs[0].font.size = Pt(28)
            box.text_frame.paragraphs[0].runs[0].font.bold = True
        if hidden:
            s._element.set("show", "0")
    path = os.path.join(tmp, "Example figures.pptx")
    prs.save(path)
    return path


def shoot(chrome: str, server_url: str, scene: str, tmp: str) -> str:
    extra = {"deck": example_deck(tmp)} if scene == "slides" else {}
    query = urllib.parse.urlencode({"docshot": scene, "examples": os.path.join(ROOT, "examples"), "out": OUT, **extra})
    shot = os.path.join(tmp, f"{scene}.png")
    with tempfile.TemporaryDirectory() as profile:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               f"--user-data-dir={profile}", f"--window-size={W},{H}", f"--force-device-scale-factor={SCALE}",
               "--hide-scrollbars", "--virtual-time-budget=30000", f"--screenshot={shot}",
               server_url + "ui/index.html?" + query]
        if sys.platform.startswith("linux"):
            cmd.insert(1, "--no-sandbox")
        subprocess.run(cmd, capture_output=True, timeout=300)
    return shot


def finish(src: str, scene: str) -> None:
    im = Image.open(src).convert("RGB")
    crop = SCENES[scene]
    if crop:
        im = im.crop(tuple(v * SCALE for v in crop))
    im = im.resize((im.width // SCALE, im.height // SCALE), Image.LANCZOS)
    im.save(os.path.join(OUT, f"{scene}.png"), optimize=True)
    if scene == "window":
        tour(im).save(os.path.join(OUT, "window-tour.png"), optimize=True)


def tour(im):
    """The window with numbered callouts, matching the tutorial's list."""
    im = im.copy()
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 17, index=1)
    except OSError:
        font = ImageFont.load_default()
    for n, (x, y) in enumerate(TOUR, start=1):
        r = 14
        d.ellipse((x - r, y - r, x + r, y + r), fill=(209, 0, 122), outline="white", width=3)
        d.text((x, y + 1), str(n), fill="white", font=font, anchor="mm")
    return im


def main() -> int:
    chrome = find_chrome()
    if not chrome:
        print("Chrome not found")
        return 1
    os.environ.setdefault("FIGASSEMBLE_HOME", tempfile.mkdtemp(prefix="figassemble-docshots-"))
    from figassemble.app.api import Api
    from figassemble.app.server import start_server
    os.makedirs(OUT, exist_ok=True)
    scenes = sys.argv[1:] or list(SCENES)
    srv = start_server(Api())
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for scene in scenes:
                shot = shoot(chrome, srv.url, scene, tmp)
                if scene != "result":
                    finish(shot, scene)
                print(scene)
    finally:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

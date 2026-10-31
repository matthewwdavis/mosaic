"""Render two (or more) PDF/PNG figures at the same resolution and report how they differ.

    python tools/compare_renders.py a.pdf b.pdf [--dpi 300] [--out tools/output/cmp] [--crop x0,y0,x1,y1]

Writes <out>_side.png (side by side, white background) and <out>_diff.png (|a - b|,
contrast-stretched), and prints the share of pixels that differ.
"""
import argparse
import os
import sys

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageOps


def render(path: str, dpi: float) -> Image.Image:
    if path.lower().endswith(".pdf"):
        doc = pdfium.PdfDocument(path)
        im = doc[0].render(scale=dpi / 72.0, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
        doc.close()
        return im
    im = Image.open(path)
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    return im.convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--dpi", type=float, default=300)
    ap.add_argument("--out", default="tools/output/cmp")
    ap.add_argument("--crop", help="x0,y0,x1,y1 in points")
    args = ap.parse_args()
    ims = [render(f, args.dpi) for f in args.files]
    w = min(im.size[0] for im in ims)
    h = min(im.size[1] for im in ims)
    ims = [im.crop((0, 0, w, h)) for im in ims]
    if args.crop:
        x0, y0, x1, y1 = (float(v) * args.dpi / 72 for v in args.crop.split(","))
        ims = [im.crop((int(x0), int(y0), int(x1), int(y1))) for im in ims]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    side = Image.new("RGB", (sum(im.size[0] for im in ims) + 10 * (len(ims) - 1), ims[0].size[1]), (255, 0, 255))
    x = 0
    for im in ims:
        side.paste(im, (x, 0))
        x += im.size[0] + 10
    side.save(args.out + "_side.png")
    a, b = np.asarray(ims[0], dtype=np.int16), np.asarray(ims[1], dtype=np.int16)
    diff = np.abs(a - b).max(axis=2)
    print(f"{args.files[0]} vs {args.files[1]}: {np.mean(diff > 32) * 100:.3f}% of pixels differ by >32/255, "
          f"{np.mean(diff > 0) * 100:.3f}% differ at all, max {diff.max()}")
    d = ImageOps.autocontrast(ImageChops.difference(ims[0], ims[1]).convert("L"))
    ImageOps.invert(d).save(args.out + "_diff.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())

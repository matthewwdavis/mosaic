import sys, os
import numpy as np
from PIL import Image
from render import pdfium_page, quartz_page
before, after, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
x0, y0, x1, y1 = 330, 0, 510, 70   # panel b on page 3, points from the top left

def crop(im, s):
    return im.crop((int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s)))

def stats(a, b):
    d = np.abs(np.asarray(a).astype(int) - np.asarray(b).astype(int)).max(axis=2)
    return int(d.max()), int((d > 8).sum()), int((d > 32).sum())

for s in (1, 2, 6):
    pb, pa = pdfium_page(before, 2, s), pdfium_page(after, 2, s)
    qb, qa = quartz_page(before, 2, s), quartz_page(after, 2, s)
    cb = {k: crop(v, s) for k, v in dict(pdfium_before=pb, pdfium_after=pa, quartz_before=qb, quartz_after=qa).items()}
    for k, v in cb.items():
        v.save(f"{out}/b_{k}_{s}x.png")
    # A 2x2 sheet: rows PDFium, Quartz; columns before, after
    w, h = cb["pdfium_before"].size
    sheet = Image.new("RGB", (w * 2 + 10, h * 2 + 10), (255, 0, 255))
    sheet.paste(cb["pdfium_before"], (0, 0)); sheet.paste(cb["pdfium_after"], (w + 10, 0))
    sheet.paste(cb["quartz_before"], (0, h + 10)); sheet.paste(cb["quartz_after"], (w + 10, h + 10))
    sheet.save(f"{out}/b_sheet_{s}x.png")
    print(f"{s}x panel b  PDFium vs Quartz before (max, >8, >32): {stats(cb['pdfium_before'], cb['quartz_before'])}"
          f"  after: {stats(cb['pdfium_after'], cb['quartz_after'])}")
    print(f"{s}x whole page 3  Quartz before vs after: {stats(qb, qa)}   PDFium before vs after: {stats(pb, pa)}")

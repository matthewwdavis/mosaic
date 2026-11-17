import sys
import numpy as np
from PIL import Image
d = sys.argv[1]
for s in (1, 2, 6):
    q = np.asarray(Image.open(f"{d}/b_quartz_after_{s}x.png")).astype(int)
    for when in ("before", "after"):
        p = np.asarray(Image.open(f"{d}/b_pdfium_{when}_{s}x.png")).astype(int)
        # grey drawn where Apple's renderer shows (near) white: the fringe
        n = int(((q.min(axis=2) >= 235) & (p.max(axis=2) <= q.min(axis=2) - 40)).sum())
        print(f"{s}x {when:6s} fringe pixels (Quartz white, PDFium 40+ darker): {n}")
# zoomed leaf crops at 6x (second-column leaf with a white fade shape)
for when in ("pdfium_before", "pdfium_after", "quartz_after"):
    im = Image.open(f"{d}/b_{when}_6x.png").crop((150, 20, 300, 120)).resize((450, 300), Image.NEAREST)
    im.save(f"{d}/leaf_{when}_6x.png")
a, b, c = (Image.open(f"{d}/leaf_{k}_6x.png") for k in ("pdfium_before", "pdfium_after", "quartz_after"))
sheet = Image.new("RGB", (450 * 3 + 20, 300), (255, 0, 255))
for i, im in enumerate((a, b, c)): sheet.paste(im, (i * 460, 0))
sheet.save(f"{d}/leaf_zoom_6x.png")

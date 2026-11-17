import sys, zlib
import numpy as np, pikepdf
from pikepdf import Name, Dictionary, Array
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from mosaic import alphableed
from render import pdfium_page, quartz_page

N = 400
yy, xx = np.mgrid[0:N, 0:N]
r = np.hypot(xx - N / 2, yy - N / 2)
alpha = np.clip((150 - r) / 3.0, 0, 1)            # a soft-edged disc
alpha = (alpha * 255).round().astype(np.uint8)
white = np.full((N, N, 3), 255, np.uint8)
color = white.copy(); color[alpha == 0] = 0        # black hidden under alpha 0
af = alpha[..., None] / 255.0

def make(colour, matte=None, path="x.pdf"):
    pdf = pikepdf.new()
    img = pikepdf.Stream(pdf, zlib.compress(colour.tobytes()))
    img.Type, img.Subtype = Name.XObject, Name.Image
    img.Width = img.Height = N; img.BitsPerComponent = 8; img.ColorSpace = Name.DeviceRGB; img.Filter = Name.FlateDecode
    m = pikepdf.Stream(pdf, zlib.compress(alpha.tobytes()))
    m.Type, m.Subtype = Name.XObject, Name.Image
    m.Width = m.Height = N; m.BitsPerComponent = 8; m.ColorSpace = Name.DeviceGray; m.Filter = Name.FlateDecode
    if matte is not None:
        m.Matte = Array(matte)
    img.SMask = pdf.make_indirect(m)
    # light grey page, five copies at shrinking sizes
    ops = ["0.85 0.85 0.85 rg 0 0 300 100 re f"]
    x = 5
    for s in (80, 50, 30, 20, 12):
        ops.append(f"q {s} 0 0 {s} {x} 10 cm /Im0 Do Q"); x += s + 5
    page = pdf.add_blank_page(page_size=(300, 100))
    page.Resources = Dictionary(XObject=Dictionary(Im0=pdf.make_indirect(img)))
    page.Contents = pdf.make_stream(" ".join(ops).encode())
    pdf.save(path)

variants = {
    "black": (color, None),
    "bleed": (alphableed.fill_hidden(color, alpha), None),
    "matte_black": ((color * af).round().astype(np.uint8), [0, 0, 0]),
    "matte_white": ((255 + af * (color.astype(float) - 255)).round().astype(np.uint8), [1, 1, 1]),
}
# reference: a disc composited onto grey properly, at each scale = Quartz render of "bleed"
for name, (c, matte) in variants.items():
    make(c, matte, f"{name}.pdf")
for scale in (1, 2, 6):
    q = np.asarray(quartz_page("bleed.pdf", 0, scale)).astype(int)
    for name in variants:
        a = np.asarray(pdfium_page(f"{name}.pdf", 0, scale)).astype(int)
        b = np.asarray(quartz_page(f"{name}.pdf", 0, scale)).astype(int)
        print(f"scale {scale} {name:12s} PDFium darkest {a.min():3d} max|PDFium-Quartz(bleed)| {np.abs(a - q).max():3d}   Quartz darkest {b.min():3d} max|Quartz-Quartz(bleed)| {np.abs(b - q).max():3d}")

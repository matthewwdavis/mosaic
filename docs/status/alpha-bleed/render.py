"""Render helpers: PDFium and Quartz, page -> RGB PIL image on white."""
import pypdfium2 as pdfium
from PIL import Image


def pdfium_page(path, page=0, scale=1.0):
    doc = pdfium.PdfDocument(path)
    im = doc[page].render(scale=scale, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
    doc.close()
    return im


def quartz_page(path, page=0, scale=1.0):
    import Quartz
    from Foundation import NSURL
    doc = Quartz.CGPDFDocumentCreateWithURL(NSURL.fileURLWithPath_(path))
    pg = Quartz.CGPDFDocumentGetPage(doc, page + 1)
    box = Quartz.CGPDFPageGetBoxRect(pg, Quartz.kCGPDFMediaBox)
    w, h = int(round(box.size.width * scale)), int(round(box.size.height * scale))
    cs = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, w * 4, cs, Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w, h))
    Quartz.CGContextScaleCTM(ctx, scale, scale)
    Quartz.CGContextTranslateCTM(ctx, -box.origin.x, -box.origin.y)
    Quartz.CGContextDrawPDFPage(ctx, pg)
    img = Quartz.CGBitmapContextCreateImage(ctx)
    prov = Quartz.CGImageGetDataProvider(img)
    data = bytes(Quartz.CGDataProviderCopyData(prov))
    bpr = Quartz.CGImageGetBytesPerRow(img)
    return Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", bpr, 1).convert("RGB")

"""The colour hidden under a picture's see-through pixels is filled from the visible ones on
export (mosaic/alphableed.py), so PDFium (Chrome, prose, mosaic's PNG export and previews), which
scales a picture and its transparency apart, draws no grey edges; visible pixels stay as they were."""
import io
import urllib.request
import zlib

import numpy as np
import pikepdf
import pypdfium2 as pdfium
from pikepdf import Name
from PIL import Image

from mosaic import alphableed, assets, model
from mosaic.export.preflight import preflight
from mosaic.export.run import export_document

N = 400


def disc(hidden=(0, 0, 0)):
    """A white disc with soft edges, and `hidden` under its fully see-through pixels (black, as
    Cairo and PowerPoint leave it), with a black dot in the middle to show the visible pixels."""
    yy, xx = np.mgrid[0:N, 0:N]
    r = np.hypot(xx - N / 2, yy - N / 2)
    alpha = (np.clip((150 - r) / 3.0, 0, 1) * 255).round().astype(np.uint8)
    color = np.full((N, N, 3), 255, np.uint8)
    color[alpha == 0] = hidden
    color[190:210, 190:210] = 0
    return color, alpha


def render(path, scale=1.0, page=0):
    doc = pdfium.PdfDocument(path)
    im = np.asarray(doc[page].render(scale=scale, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB"))
    doc.close()
    return im


def placed_pdf(path, color, alpha):
    """A PDF page as R's cairo_pdf writes a picture: the colour and a separate soft mask, the
    picture drawn small (400 px in 50 pt)."""
    pdf = pikepdf.new()
    img = pikepdf.Stream(pdf, zlib.compress(color.tobytes()))
    img.Type, img.Subtype, img.Width, img.Height = Name.XObject, Name.Image, N, N
    img.BitsPerComponent, img.ColorSpace, img.Filter = 8, Name.DeviceRGB, Name.FlateDecode
    m = pikepdf.Stream(pdf, zlib.compress(alpha.tobytes()))
    m.Type, m.Subtype, m.Width, m.Height = Name.XObject, Name.Image, N, N
    m.BitsPerComponent, m.ColorSpace, m.Filter = 8, Name.DeviceGray, Name.FlateDecode
    img.SMask = pdf.make_indirect(m)
    page = pdf.add_blank_page(page_size=(60, 60))
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=pdf.make_indirect(img)))
    page.Contents = pdf.make_stream(b"q 50 0 0 50 5 5 cm /Im0 Do Q")
    pdf.save(path)
    return str(path)


def ring_darkness(im):
    """How dark the darkest pixel is outside the middle (where the black dot is): the edge."""
    h, w, _ = im.shape
    out = im.copy()
    out[h * 2 // 5:h * 3 // 5, w * 2 // 5:w * 3 // 5] = 255
    return 255 - int(out.min())


def export_one(path, cache, tmp_path, formats=("pdf",)):
    doc = model.new_document("bleed")
    aid, asset, _ = assets.new_asset(str(path), cache, use_siblings=False)
    doc["assets"][aid] = asset
    item = model.picture_item(aid, asset, 0, 0)
    item["frame"] = [5, 5, 50, 50]
    doc["pages"][0]["items"] = [item]
    doc["pages"][0]["width"] = doc["pages"][0]["height"] = 60.0
    return doc, export_document(doc, str(tmp_path / "out"), list(formats), cache=cache)


def images_of(path):
    """(colour, alpha) of every image with a soft mask in a PDF."""
    out = []
    with pikepdf.open(path) as pdf:
        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == Name.Image and "/SMask" in obj:
                w, h = int(obj.Width), int(obj.Height)
                n = len(obj.read_bytes()) // (w * h)
                out.append((np.frombuffer(obj.read_bytes(), np.uint8).reshape(h, w, n),
                            np.frombuffer(obj.SMask.read_bytes(), np.uint8).reshape(h, w)))
    return out


def test_the_fill_keeps_visible_pixels_and_takes_their_colour_under_the_see_through_ones():
    color, alpha = disc()
    color[alpha > 0] = (40, 200, 90)   # a green disc
    filled = alphableed.fill_hidden(color, alpha)
    seen = alpha > 0
    assert np.array_equal(filled[seen], color[seen])
    assert np.array_equal(filled[~seen].reshape(-1, 3).min(axis=0), [40, 200, 90])   # green everywhere
    assert np.array_equal(filled[~seen].reshape(-1, 3).max(axis=0), [40, 200, 90])
    # Nothing to do: nothing see-through, or nothing visible
    assert alphableed.fill_hidden(color, np.full_like(alpha, 255)) is color
    assert alphableed.fill_hidden(color, np.zeros_like(alpha)) is color
    # Grey pictures and odd sizes
    g = alphableed.fill_hidden(np.zeros((7, 5), np.uint8) + np.eye(7, 5, dtype=np.uint8) * 200,
                               (np.eye(7, 5) * 255).astype(np.uint8))
    assert g.shape == (7, 5) and g.min() == 200


def test_a_placed_pdf_draws_without_grey_edges_in_pdfium(cache, tmp_path):
    color, alpha = disc()
    src = placed_pdf(tmp_path / "leaf.pdf", color, alpha)
    # (the fault itself: drawn as it is, PDFium shows a dark ring around the white disc)
    assert ring_darkness(render(src, 1.0)) > 40
    _, out = export_one(src, cache, tmp_path)
    for scale in (0.5, 1.0, 2.0, 6.0):
        assert ring_darkness(render(out["files"][0], scale)) < 8, scale
    # Visible pixels and the transparency are byte for byte as they were
    (c, a), = images_of(out["files"][0])
    assert np.array_equal(a, alpha)
    assert np.array_equal(c[alpha > 0], color[alpha > 0])
    assert (c[alpha == 0] > 200).all()


def test_a_transparent_png_exports_clean_to_pdf_and_png(cache, tmp_path):
    color, alpha = disc()
    path = tmp_path / "leaf.png"
    Image.fromarray(np.dstack([color, alpha]), "RGBA").save(path, dpi=(576, 576))
    _, out = export_one(path, cache, tmp_path, ("pdf", "png"))
    pdf = next(f for f in out["files"] if f.endswith(".pdf"))
    png = next(f for f in out["files"] if f.endswith(".png"))
    for scale in (0.5, 1.0, 6.0):
        assert ring_darkness(render(pdf, scale)) < 8, scale
    (c, a), = images_of(pdf)
    assert np.array_equal(a, alpha) and np.array_equal(c[alpha > 0], color[alpha > 0])
    # The PNG export (drawn by PDFium): composited on white, the edge has no grey either
    im = Image.open(png).convert("RGBA")
    on_white = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB")
    assert ring_darkness(np.asarray(on_white)) < 8


def test_cleaning_is_made_once_and_kept(cache, tmp_path, monkeypatch):
    color, alpha = disc()
    src = placed_pdf(tmp_path / "leaf.pdf", color, alpha)
    sha = assets.sha256_file(src)
    found, path = alphableed.cleaned(cache, sha, "pdf", src)
    assert path != src and found["cleaned"] == 1 and found["edges"] == 1
    # The second time reads what the first one kept
    monkeypatch.setattr(alphableed, "clean_pdf", lambda *a: (_ for _ in ()).throw(AssertionError("made again")))
    assert alphableed.cleaned(cache, sha, "pdf", src) == (found, path)


def test_a_picture_with_nothing_to_clean_exports_from_its_own_file(cache, tmp_path):
    color, alpha = disc(hidden=(255, 255, 255))   # white under the see-through parts already
    src = placed_pdf(tmp_path / "clean.pdf", color, alpha)
    found, path = alphableed.cleaned(cache, assets.sha256_file(src), "pdf", src)
    assert path == src and found["images"] == 1 and not found["cleaned"]
    opaque = tmp_path / "opaque.png"
    Image.new("RGB", (10, 10), (200, 30, 30)).save(opaque)
    assert alphableed.cleaned(cache, assets.sha256_file(str(opaque)), "png", str(opaque))[1] == str(opaque)


def test_a_jpeg_with_a_soft_mask_is_left_as_it_is(cache, tmp_path):
    color, alpha = disc()
    src = placed_pdf(tmp_path / "leaf.pdf", color, alpha)
    with pikepdf.open(src, allow_overwriting_input=True) as pdf:
        img = next(o for o in pdf.objects if isinstance(o, pikepdf.Stream) and "/SMask" in o)
        buf = io.BytesIO()
        Image.fromarray(color).save(buf, "JPEG", quality=90)
        img.write(buf.getvalue(), filter=Name.DCTDecode)
        pdf.save(src)
    found, path = alphableed.cleaned(cache, assets.sha256_file(src), "pdf", src)
    assert path == src and found["images"] == 1 and not found["cleaned"]


def test_check_says_what_will_be_cleaned(tmp_path):
    color, alpha = disc()
    dark = placed_pdf(tmp_path / "leaf.pdf", color, alpha)
    clean = placed_pdf(tmp_path / "clean.pdf", *disc(hidden=(255, 255, 255)))
    doc = model.new_document("check")
    for i, path in enumerate((dark, clean)):
        aid, asset, _ = assets.new_asset(path, use_siblings=False)
        doc["assets"][aid] = asset
        item = model.picture_item(aid, asset, 70 * i, 0)
        item["name"] = f"Picture {i + 1}"
        doc["pages"][0]["items"].append(item)
    said = [f["message"] for f in preflight(doc, {"pages": [0]})["items"] if "see-through" in f["message"]]
    assert said == ["Picture 1: 1 picture inside it hides a contrasting colour under the see-through parts, which "
                    "Chrome and prose show as thin grey edges; export fills it in, so nothing else changes"]


def test_the_editors_preview_of_a_pdf_is_drawn_clean(tmp_path, monkeypatch):
    from mosaic.app.api import Api
    from mosaic.app.server import start_server
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    srv = start_server(Api(), 0)
    try:
        color, alpha = disc()
        with open(placed_pdf(tmp_path / "leaf.pdf", color, alpha), "rb") as fh:
            sha, _ = assets.get_cache().put_bytes(fh.read(), "pdf")
        with urllib.request.urlopen(srv.url + f"asset/{sha}.pdf?page=0&scale=1") as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGBA")
        on_white = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB")
        assert ring_darkness(np.asarray(on_white)) < 8
    finally:
        srv.shutdown()

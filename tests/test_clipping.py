"""Crop to shape and clipping masks: a shape's area clips a picture, or a group's other parts."""
import numpy as np
import pikepdf
from lxml import etree
from PIL import Image

from figassemble import assets, model
from figassemble.app.api import Api
from figassemble.export.preflight import preflight
from figassemble.export.run import export_document
from figassemble.resolve import DrawGroup, DrawPicture, Resolver, flat_prims

SVG_NS = "{http://www.w3.org/2000/svg}"


def masked_picture(fixtures, cache):
    doc = model.new_document("clip")
    page = doc["pages"][0]
    page["width"], page["height"] = 200.0, 150.0
    jid, jasset, _ = assets.new_asset(fixtures["jpg"], cache)
    doc["assets"][jid] = jasset
    pic = model.picture_item(jid, jasset, 10, 10)
    pic["mask"] = {"geom": "ellipse"}
    page["items"].append(pic)
    return doc, pic


def pdf_content(path):
    pdf = pikepdf.open(path)
    contents = pdf.pages[0].Contents
    data = b"".join(s.read_bytes() for s in contents) if isinstance(contents, pikepdf.Array) else contents.read_bytes()
    pdf.close()
    return data


def test_a_picture_cropped_to_a_shape(fixtures, cache, tmp_path):
    doc, pic = masked_picture(fixtures, cache)
    prims = Resolver(doc).resolve(pic).prims
    assert len(prims) == 1 and isinstance(prims[0], DrawGroup) and prims[0].clip
    assert [type(p) for p in flat_prims(prims)] == [DrawPicture]
    export_document(doc, str(tmp_path / "m"), ["png", "svg", "pdf"], dpi=144, transparent=True)
    im = Image.open(tmp_path / "m.png").convert("RGBA")
    x, y, w, h = pic["frame"]
    # The frame's corner is outside the ellipse; its middle shows the picture
    assert im.getpixel((int((x + 0.5) * 2), int((y + 0.5) * 2)))[3] == 0
    assert im.getpixel((int((x + w / 2) * 2), int((y + h / 2) * 2)))[3] == 255
    assert etree.parse(str(tmp_path / "m.svg")).findall(f".//{SVG_NS}clipPath")
    assert b"\nW\nn\n" in pdf_content(tmp_path / "m.pdf")
    # The pre-export check still sees the picture inside its clip
    assert any(f.get("item") == pic["id"] for f in preflight(doc, {"pages": [0]})["items"])


def test_a_clipping_mask_clips_the_parts_under_its_shape(tmp_path):
    doc = model.new_document("mask")
    page = doc["pages"][0]
    page["width"], page["height"] = 120.0, 80.0
    red = {"id": "r", "type": "shape", "geom": "rect", "frame": [0, 0, 120, 80], "rot": 0, "fill": {"color": "#ff0000"},
           "stroke": None}
    # The mask's own fill and line aren't drawn: it only clips
    mask = {"id": "m", "type": "shape", "geom": "ellipse", "frame": [20, 10, 80, 60], "rot": 0, "fill": {"color": "#00ff00"},
            "stroke": {"color": "#0000ff", "width": 4}}
    page["items"] = [{"id": "g", "type": "group", "clip": True, "items": [red, mask]}]
    prims = Resolver(doc).resolve(page["items"][0]).prims
    assert len(prims) == 1 and prims[0].clip and len(list(flat_prims(prims))) == 1
    export_document(doc, str(tmp_path / "g"), ["png"], dpi=72, transparent=True)
    im = Image.open(tmp_path / "g.png").convert("RGBA")
    assert im.getpixel((60, 40)) == (255, 0, 0, 255)   # inside the ellipse: the red under it
    assert im.getpixel((5, 5))[3] == 0                   # inside the red rectangle, outside the ellipse
    a = np.asarray(im)
    assert not ((a[..., 3] > 0) & ((a[..., 1] > 200) | (a[..., 2] > 200))).any()   # no green or blue mask drawn


def test_the_editor_gets_the_clip_in_the_frame_or_on_the_page():
    api = Api()
    local = api.area_path({"type": "picture", "frame": [10, 10, 80, 60], "mask": {"geom": "rect"}}, True)
    assert local["d"].startswith("M0 0") and not local["even_odd"]
    page = api.area_path({"type": "shape", "geom": "rect", "frame": [10, 10, 80, 60], "rot": 0}, False)
    assert page["d"].startswith("M10 10")
    assert api.area_path({"type": "line", "points": [[0, 0], [5, 5]]}) is None


def test_a_border_round_a_picture_or_the_shape_its_cropped_to(fixtures, cache):
    doc, pic = masked_picture(fixtures, cache)
    plain = {k: v for k, v in pic.items() if k != "mask"} | {"border": {"color": "#ff0000", "width": 2}}
    edge = Resolver(doc).resolve(plain).prims[-1]
    x, y, w, h = pic["frame"]
    assert edge.stroke.width == 2 and edge.fill is None and edge.path.bbox() == (x, y, x + w, y + h)
    # Cropped to an ellipse: the border follows the ellipse, outside the clip so it isn't cut
    prims = Resolver(doc).resolve(pic | {"border": {"color": "#ff0000", "width": 2}}).prims
    assert isinstance(prims[0], DrawGroup) and any(s[0] == "C" for s in prims[-1].path.segs)

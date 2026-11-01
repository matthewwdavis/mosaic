"""Make editable shape: a ready-made shape becomes a freeform shape of the same outline (its
adjustments and corner rounding built in), drawn exactly as before."""
import numpy as np
from PIL import Image

from figassemble import model
from figassemble.export.run import export_document
from figassemble.resolve import Resolver, shape_to_custom


def shape(geom, **kw):
    return {"id": "s", "type": "shape", "geom": geom, "frame": [10, 10, 80, 50], "rot": 0, "flip_h": False, "flip_v": False,
            "stroke": {"color": "#000000", "width": 1.5}, "fill": {"color": "#e69f00"}, **kw}


def test_the_same_outline_as_a_freeform_shape(tmp_path):
    for geom, extra in (("star5", {}), ("roundRect", {"adj": {"adj": 30000}}), ("rect", {"rounding": 0.4}),
                        ("rightArrow", {}), ("donut", {})):
        before = shape(geom, **extra)
        after = shape_to_custom(before)
        assert after["geom"] == "custom" and "adj" not in after and "rounding" not in after, geom
        assert all(c[0] in "MLCZ" for sp in after["path"]["subpaths"] for c in sp["cmds"]), geom
        r0, r1 = Resolver({"assets": {}}).resolve(before), Resolver({"assets": {}}).resolve(after)
        assert np.allclose(r0.bbox, r1.bbox, atol=1e-6), geom
        # Drawn the same, pixel for pixel
        pngs = []
        for i, it in enumerate((before, after)):
            doc = model.new_document("pen")
            page = doc["pages"][0]
            page["width"], page["height"], page["background"] = 100.0, 70.0, "#ffffff"
            page["items"] = [it]
            export_document(doc, str(tmp_path / f"{geom}{i}"), ["png"], dpi=144, transparent=False)
            pngs.append(np.asarray(Image.open(tmp_path / f"{geom}{i}.png").convert("RGB"), dtype=int))
        assert np.abs(pngs[0] - pngs[1]).max() <= 2, geom
    custom = shape("custom", path={"subpaths": []})
    assert shape_to_custom(custom) == custom


def test_an_elbows_repeated_corner_draws_nothing_extra():
    def arrow(points):
        return {"id": "l", "type": "line", "points": points, "arrow_start": None, "arrow_end": {"type": "triangle", "w": "med", "len": "med"},
                "stroke": {"color": "#000000", "width": 1, "cap": "flat", "join": "miter"}}
    once = Resolver({"assets": {}}).resolve(arrow([[0, 0], [40, 0], [40, 30]]))
    twice = Resolver({"assets": {}}).resolve(arrow([[0, 0], [40, 0], [40, 0], [40, 30]]))
    assert [p.path.segs for p in once.prims] == [p.path.segs for p in twice.prims]

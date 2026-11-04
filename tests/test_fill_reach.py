"""Where a fill stops against its lines (fillreach.py): their middle as before, their inner edge
or their outer edge, for a shape's own fill and for an area fill; curves stay curves."""
from mosaic import model, regions
from mosaic.export.run import export_document
from mosaic.fonts import get_font_index
from mosaic.geometry import DrawPath, flatten
from mosaic.resolve import Resolver

DASHED = {"color": "#000000", "width": 6, "dash": "dash", "cap": "flat", "join": "miter", "opacity": 1}


def body(item, page=()):
    r = Resolver({"assets": {}, "symbols": []}, get_font_index())
    r.use_page([*page, item])
    return [p for p in r.resolve(item).prims if isinstance(p, DrawPath) and p.fill is not None][0].path


def bounds(path):
    pts = [p for sub in flatten(path) for p in sub]
    return [round(f(p[i] for p in pts), 3) for f, i in ((min, 0), (min, 1), (max, 0), (max, 1))]


def box(**kw):
    return {"id": "b", "type": "shape", "geom": "rect", "frame": [100, 100, 100, 60], "rot": 0,
            "fill": {"color": "#cccccc", "opacity": 1}, "stroke": DASHED, **kw}


def test_a_shapes_fill_stops_at_its_lines_middle_inner_or_outer_edge():
    assert bounds(body(box())) == [100, 100, 200, 160]
    assert bounds(body(box(fill_reach="inner"))) == [103, 103, 197, 157]   # half the 6 pt line in
    assert bounds(body(box(fill_reach="outer"))) == [97, 97, 203, 163]
    ring = body(box(geom="ellipse", fill_reach="inner"))
    assert any(s[0] == "C" for s in ring.segs)   # still curves, not a polygon


def test_an_area_fills_reach_is_beside_its_lines_not_where_they_run_on():
    st = {**DASHED, "width": 4}
    lines = [{"id": i, "type": "line", "points": [a, b], "stroke": st, "arrow_start": None, "arrow_end": None}
             for i, a, b in (("l1", [80, 100], [220, 100]), ("l2", [80, 200], [220, 200]), ("v1", [100, 80], [100, 220]),
                             ("v2", [200, 80], [200, 220]))]
    found = regions.area_at(lines, [150, 150])
    fill = {"id": "f", "type": "shape", "geom": "region", "frame": found["frame"], "stroke": None,
            "region": {"items": found["items"], "seed": found["seed"]}, "fill": {"color": "#56b4e9", "opacity": 1}}
    assert bounds(body(fill, lines)) == [100, 100, 200, 200]
    assert bounds(body({**fill, "fill_reach": "inner"}, lines)) == [102, 102, 198, 198]
    assert bounds(body({**fill, "fill_reach": "outer"}, lines)) == [98, 98, 202, 202]   # (not out along the lines' ends)


def test_powerpoint_takes_such_a_shape_as_an_exact_picture(cache, tmp_path):
    doc = model.new_document("reach")
    doc["pages"][0]["items"] = [box(fill_reach="outer")]
    res = export_document(doc, str(tmp_path / "deck"), ["pptx"], cache=cache)
    assert any("a fill to its line's inner or outer edge" in n for n in res.get("notes", []) + res.get("warnings", []))

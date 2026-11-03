"""Area fills that follow their lines (mosaic/regions.py, Resolver._region)."""
import copy

import pikepdf

from mosaic import regions
from mosaic.export.run import export_document
from mosaic.resolve import Resolver

ST = {"color": "#000000", "width": 1.5, "cap": "round", "join": "round"}


def line(i, a, b, width=1.5):
    return {"id": i, "type": "line", "points": [a, b], "stroke": dict(ST, width=width)}


def triangle(gap=0.0):
    # Three separate lines; the last stops `gap` short of the first corner
    return [line("a", [20, 150], [110, 20]), line("b", [110, 20], [200, 150]), line("c", [200, 150], [20 + gap, 150])]


def test_three_lines_enclose_an_area():
    found = regions.area_at(triangle(), [100, 120])
    assert sorted(found["items"]) == ["a", "b", "c"]
    assert [round(v, 3) for v in found["frame"]] == [20, 20, 180, 130]
    u, v = found["seed"]
    assert 0 < u < 1 and 0 < v < 1
    assert regions.area_at(triangle(), [5, 5]) is None   # outside it


def test_a_gap_narrower_than_the_line_still_closes_it():
    assert regions.area_at(triangle(gap=0.6), [100, 120]) is not None      # hidden by the 1.5 pt line's round end
    assert regions.area_at(triangle(gap=5.0), [100, 120]) is None          # a real opening


def test_a_shape_inside_is_a_hole_and_part_of_the_boundary():
    circle = {"id": "o", "type": "shape", "geom": "ellipse", "frame": [90, 80, 40, 40], "rot": 0, "stroke": dict(ST), "fill": None}
    found = regions.area_at(triangle() + [circle], [60, 135])
    assert sorted(found["items"]) == ["a", "b", "c", "o"]
    area = regions.find({"items": found["items"], "seed": found["seed"]}, {it["id"]: it for it in triangle() + [circle]})
    rings = [s for s in area["path"].segs if s[0] == "M"]
    assert len(rings) == 2   # the triangle and the circle's hole


def test_it_follows_its_lines_and_opens_when_one_goes():
    items = triangle()
    found = regions.area_at(items, [100, 120])
    region = {"items": found["items"], "seed": found["seed"]}
    moved = copy.deepcopy(items)
    moved[0]["points"][1] = [140, 0]
    moved[1]["points"][0] = [140, 0]
    area = regions.find(region, {it["id"]: it for it in moved})
    assert [round(v, 3) for v in area["frame"]] == [20, 0, 180, 150]
    # The whole drawing moved: the seed moves with it
    shifted = copy.deepcopy(items)
    for it in shifted:
        it["points"] = [[x + 300, y + 50] for x, y in it["points"]]
    assert round(regions.find(region, {it["id"]: it for it in shifted})["frame"][0], 3) == 320
    assert regions.find(region, {it["id"]: it for it in items[:2]}) is None


def test_dashed_outlines_and_what_encloses_nothing():
    dashed = {"id": "r", "type": "shape", "geom": "rect", "frame": [0, 0, 100, 60], "rot": 0,
              "stroke": dict(ST, dash="dash"), "fill": None}
    assert regions.area_at([dashed], [50, 30])["items"] == ["r"]   # its dashes don't open it
    textbox = {"id": "t", "type": "shape", "geom": "rect", "textbox": True, "frame": [0, 0, 100, 60], "rot": 0,
               "stroke": None, "fill": None, "text": {"paragraphs": []}}
    assert regions.area_at([textbox], [50, 30]) is None


def test_drawn_and_exported_with_its_page(tmp_path):
    from mosaic.app.api import Api
    items = triangle()
    found = regions.area_at(items, [100, 120])
    fill = {"id": "f", "type": "shape", "geom": "region", "region": {"items": found["items"], "seed": found["seed"]},
            "frame": found["frame"], "rot": 0, "stroke": None, "fill": {"color": "#ffd166", "opacity": 1}}
    doc = Api().new_document()
    doc["pages"][0]["items"] = [fill] + items
    r = Resolver(doc)
    r.use_page(doc["pages"][0]["items"])
    drawn = r.resolve(fill)
    assert drawn.prims and drawn.prims[0].fill.even_odd and drawn.region["frame"] == found["frame"]
    # Without its lines it draws nothing and says why
    alone = Resolver(doc).resolve(fill)
    assert not alone.prims and alone.warnings
    export_document(doc, str(tmp_path / "f"), ["pdf"])
    pdf = pikepdf.open(str(tmp_path / "f.pdf"))
    contents = pdf.pages[0].Contents
    data = b"".join(s.read_bytes() for s in contents) if isinstance(contents, pikepdf.Array) else contents.read_bytes()
    assert b"f*" in data   # the area, filled even-odd
    # As an ordinary shape it keeps the area
    plain = dict(fill, geom="custom", path=drawn.region["path"], fill={"color": "#ffd166", "even_odd": True})
    plain.pop("region")
    box = Resolver(doc).resolve(plain).bbox
    assert [round(v, 3) for v in box] == [20, 20, 200, 150]


def test_an_area_fill_can_be_outlined_just_inside_its_edge():
    from mosaic.resolve import DrawGroup
    items = triangle()
    found = regions.area_at(items, [100, 120])
    fill = {"id": "f", "type": "shape", "geom": "region", "region": {"items": found["items"], "seed": found["seed"]},
            "frame": found["frame"], "rot": 0, "stroke": None, "fill": {"color": "#ffd166", "opacity": 1},
            "outline": {"color": "#ffffff", "width": 2, "opacity": 1, "type": "inside"}}
    r = Resolver({"assets": {}})
    r.use_page([fill] + items)
    area, band = r.resolve(fill).prims
    # Over the fill, clipped to the area (even-odd, as the area is drawn)
    assert isinstance(band, DrawGroup) and band.clip == [(area.path, True)]

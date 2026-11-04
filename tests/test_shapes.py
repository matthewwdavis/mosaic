"""Preset shapes from PowerPoint's formulas, corner rounding and rounded arrowheads."""
import math

import pytest

from mosaic import presets
from mosaic.geometry import DrawPath, Path, corner_count, flatten, head_outline, round_corners
from mosaic.resolve import Resolver, line_end_trim


def points(path, per_curve=32):
    return [p for sub in flatten(path, per_curve) for p in sub]


def menu_shapes():
    return [g for group in presets.catalog()["groups"] for g in group["shapes"]]


def test_every_menu_shape_draws_inside_its_frame():
    for geom in menu_shapes():
        for w, h in ((100.0, 60.0), (30.0, 80.0)):
            paths = presets.shape_paths(geom, w, h)
            assert any(not sp.path.is_empty for sp in paths), geom
            if geom == "mathNotEqual":   # its slash leaves a narrow frame, as in PowerPoint
                continue
            tol = 0.02 * max(w, h)
            for sp in paths:
                bb = sp.path.bbox()
                assert bb[0] > -tol and bb[1] > -tol and bb[2] < w + tol and bb[3] < h + tol, (geom, w, h, bb)


def test_menu_shapes_have_names_icons_and_labelled_adjustments():
    cat = presets.catalog()
    assert len(menu_shapes()) >= 80 and len(cat["shapes"]) == 187
    for geom in menu_shapes():
        info = cat["shapes"][geom]
        assert info["name"] and info["icon"].startswith("M"), geom
        assert all(not a["label"].startswith("Adjustment") for a in info["adjust"]), geom
    # PowerPoint's handles for a star and a block arrow
    assert [a["label"] for a in cat["shapes"]["star5"]["adjust"]] == ["Inner radius"]
    assert [a["label"] for a in cat["shapes"]["rightArrow"]["adjust"]] == ["Shaft width", "Head length"]
    assert cat["shapes"]["arc"]["open"] and not cat["shapes"]["can"]["open"]
    assert cat["shapes"]["triangle"]["corners"] and not cat["shapes"]["ellipse"]["corners"]
    assert not cat["shapes"]["arc"]["corners"]   # only its filled wedge has a corner


def test_star_inner_radius_follows_its_adjust_value():
    # The top point and the inner corner straight below the centre, which PowerPoint puts at
    # 1.10557 x half the height (its "vf" factor)
    w = h = 100.0
    cy = 50.0 * 1.10557
    for adj, ratio in ((None, 0.38196), ({"adj": 0.25}, 0.5)):
        pts = points(presets.shape_paths("star5", w, h, adj)[0].path, 1)
        top = min(p[1] for p in pts)
        inner = max(p[1] for p in pts if abs(p[0] - 50.0) < 1e-9)
        assert top == pytest.approx(0.0, abs=1e-9)
        assert (inner - cy) / (cy - top) == pytest.approx(ratio, rel=1e-4)


def test_angle_and_fraction_adjust_values_convert_like_pptx():
    assert presets.to_stored("arc", "adj1", 16200000) == 270.0
    assert presets.to_stored("roundRect", "adj", 16667) == pytest.approx(0.16667)
    assert presets.to_stored("mathNotEqual", "adj2", 6600000) == 110.0
    assert presets.defaults("star5")["adj"] == pytest.approx(0.19098)


def test_dragging_a_handle_finds_the_adjust_value_back():
    for geom, adj in (("star5", {"adj": 0.3}), ("rightArrow", {"adj1": 0.3, "adj2": 0.7}), ("roundRect", {"adj": 0.4}),
                      ("pie", {"adj1": 30.0, "adj2": 200.0}), ("blockArc", {"adj1": 160.0, "adj2": 20.0, "adj3": 0.2})):
        w, h = 120.0, 80.0
        targets = presets.handles(geom, w, h, adj)
        for i, (x, y) in enumerate(targets):
            got = presets.drag_handle(geom, w, h, {}, i, x, y)
            again = presets.handles(geom, w, h, dict(adj, **got))[i]
            assert again == pytest.approx([x, y], abs=0.05), (geom, i, got)


def test_typed_adjustments_stay_in_range():
    assert presets.clamp_adjust("roundRect", 100, 60, {}, "adj", 0.8) == 0.5
    assert presets.clamp_adjust("star5", 100, 100, {}, "adj", -0.1) == 0.0
    assert presets.clamp_adjust("triangle", 100, 60, {}, "adj", 0.3) == 0.3


def test_rounded_triangle_becomes_its_inscribed_circle():
    w, h = 60.0, 40.0
    a, b, c = (0.0, h), (w / 2, 0.0), (w, h)
    tri = Path().move_to(*a).line_to(*b).line_to(*c).close()
    la, lb, lc = math.dist(b, c), math.dist(a, c), math.dist(a, b)
    s = (la + lb + lc) / 2
    rho = w * h / 2 / s
    centre = ((la * a[0] + lb * b[0] + lc * c[0]) / (2 * s), (la * a[1] + lb * b[1] + lc * c[1]) / (2 * s))
    circle = round_corners([tri], 1.0)[0]
    assert all(math.dist(p, centre) == pytest.approx(rho, rel=1e-3) for p in points(circle))
    assert round_corners([tri], 0.0)[0] is tri


def test_rounded_rectangle_corners_are_tangent_arcs():
    rect = Path().move_to(0, 0).line_to(100, 0).line_to(100, 40).line_to(0, 40).close()
    assert corner_count([rect]) == 4
    half = round_corners([rect], 0.5)[0]   # half the largest radius (20)
    assert half.bbox() == pytest.approx((0, 0, 100, 40))
    segs = [s for s in half.segs if s[0] in "LC"]
    assert [s[0] for s in segs] == ["L", "C"] * 4
    assert (segs[0][1], segs[0][2]) == pytest.approx((90, 0))           # the top edge stops 10 short
    assert segs[1][-2:] == pytest.approx((100, 10))                     # the arc lands 10 down the side
    stadium = round_corners([rect], 1.0)[0]
    assert all(s[0] != "L" or abs(s[2] - 0) < 1e-9 or abs(s[2] - 40) < 1e-9 for s in stadium.segs)


def test_only_corners_between_straight_edges_are_rounded():
    # A rounded rectangle's corners are arcs already: nothing changes
    rr = presets.shape_paths("roundRect", 80, 50)[0].path
    assert corner_count([rr]) == 0
    assert round_corners([rr], 1.0)[0].to_svg(6) == rr.to_svg(6)


@pytest.mark.parametrize("kind", ["triangle", "stealth", "arrow"])
@pytest.mark.parametrize("amount", [0.25, 0.6, 1.0])
def test_rounded_heads_keep_their_tip_on_the_end_point(kind, amount):
    outline, shift = head_outline({"type": kind, "w": "med", "len": "med", "rounding": amount}, 1.0)
    assert outline.bbox()[2] == pytest.approx(0.0, abs=1e-9) and shift > 0


@pytest.mark.parametrize("width,size", [(1.0, "med"), (3.0, "sm"), (0.5, "lg")])
@pytest.mark.parametrize("amount", [0.3, 1.0])
def test_line_end_stays_hidden_inside_a_rounded_head(width, size, amount):
    item = {"id": "a", "type": "line", "points": [[0, 0], [100, 0]],
            "stroke": {"width": width, "color": "#000000", "cap": "round"},
            "arrow_end": {"type": "triangle", "w": size, "len": size, "rounding": amount}}
    body, head = [p for p in Resolver({"assets": {}}).resolve(item).prims if isinstance(p, DrawPath)]
    end = body.path.end_tangent()[0]
    # The line's round cap (radius width/2) lies inside the head, which ends at x = 100
    poly = points(head.path)
    inside = sum(1 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1])
                 if (y0 > end[1]) != (y1 > end[1]) and end[0] < (x1 - x0) * (end[1] - y0) / (y1 - y0) + x0) % 2
    assert inside
    nearest = min(math.dist(end, p) for p in poly)
    assert nearest >= width / 2 - 1e-6
    assert max(p[0] for p in poly) == pytest.approx(100.0, abs=1e-6)
    assert line_end_trim(item["arrow_end"], width) > 0


def test_corner_rounding_and_shades_reach_the_drawing():
    cube = {"id": "c", "type": "shape", "geom": "cube", "frame": [0, 0, 60, 60], "rounding": 0.2,
            "stroke": {"width": 1, "color": "#000000"}, "fill": {"color": "#808080"}}
    prims = Resolver({"assets": {}}).resolve(cube).prims
    fills = [p.fill.color for p in prims if p.fill]
    assert fills == ["#808080", "#666666", "#999999"]   # front, darker side, lighter top
    assert any(s[0] == "C" for p in prims for s in p.path.segs)               # rounded


def test_a_shapes_outline_for_telling_what_a_click_is_on():
    """The engine's outline of a shape, sent to the editor with its drawing: the area its fill
    covers and the path its line follows, on the page; an open shape's line stays open."""
    from mosaic.resolve import shape_outline
    ring = shape_outline({"type": "shape", "geom": "ellipse", "frame": [10, 20, 100, 50], "rot": 0})
    assert len(ring["fill"]) == 1 and len(ring["line"]) == 1 and ring["fill"][0].startswith("M10 45") and not ring["even_odd"]
    arc = shape_outline({"type": "shape", "geom": "arc", "frame": [10, 20, 100, 50], "rot": 0})
    assert not arc["line"][0].rstrip().endswith("Z")   # the arc itself, open
    turned = shape_outline({"type": "shape", "geom": "rect", "frame": [0, 0, 100, 50], "rot": 90})
    assert turned["line"][0].startswith("M75 -25")    # turned about its middle
    assert shape_outline({"type": "shape", "geom": "rect", "textbox": True, "frame": [0, 0, 10, 10]}) is None

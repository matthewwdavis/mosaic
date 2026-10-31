import math

import pytest

from figassemble.geometry import (Matrix, Path, arrowhead, dash_array, frame_matrix, preset_paths)


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_number_formatting_keeps_whole_numbers():
    from figassemble.geometry import _fmt
    assert _fmt(300, 0) == "300"
    assert _fmt(180.0, 2) == "180"
    assert _fmt(0.25, 4) == "0.25"
    assert _fmt(-0.00001, 3) == "0"


def test_matrix_compose_and_inverse():
    m = Matrix.translate(10, 5) @ Matrix.rotate(30) @ Matrix.scale(2, 3)
    x, y = m.apply(1.5, -2)
    assert close(m.inverse().apply(x, y), (1.5, -2))


def test_quarter_turns_are_exact():
    assert Matrix.rotate(90).as_tuple() == (0.0, 1.0, -1.0, 0.0, 0.0, 0.0)
    assert Matrix.rotate(270).apply(1, 0) == (0.0, -1.0)


def test_frame_matrix_flip_then_rotate_about_centre():
    # PowerPoint: a line from top-left to bottom-right, flipped horizontally, runs top-right -> bottom-left
    m = frame_matrix([10, 20, 100, 40], 0, flip_h=True)
    assert close(m.apply(0, 0), (110, 20))
    assert close(m.apply(100, 40), (10, 60))
    # Rotation keeps the centre fixed
    m = frame_matrix([0, 0, 100, 40], 90)
    assert close(m.apply(50, 20), (50, 20))


def test_quarter_ellipse_arc_matches_powerpoint_bracket():
    # Right bracket measured in PowerPoint's own PDF export (Bushy_Top figure 3)
    w, h = 2.161, 59.645
    stroke = [sp for sp in preset_paths("rightBracket", w, h, {"adj": 0.08333}) if sp.stroke][0].path
    first_curve = next(s for s in stroke.segs if s[0] == "C")
    # PowerPoint: m 327.019 319.116  c 328.212 319.116  329.18 319.197  329.18 319.296  (frame at 327.019, 319.116)
    got = [v + off for v, off in zip(first_curve[1:], (327.019, 319.116) * 3)]
    assert close(got, (328.212, 319.116, 329.18, 319.197, 329.18, 319.296), tol=2e-3)


def test_arc_bbox_and_full_circle():
    p = preset_paths("ellipse", 20, 10)[0].path
    assert close(p.bbox(), (0, 0, 20, 10), tol=1e-9)


def test_dash_arrays_match_powerpoint():
    # Round-dot (sysDot) 1.5 pt: zero-length dashes, period 3 pt; dash 1 pt: drawn 4, gap 3
    assert dash_array("sysDot", 1.5, "round") == [0.0, 3.0]
    assert dash_array("dash", 1.0, "round") == [3.0, 4.0]
    assert dash_array("dash", 1.0, "flat") == [4.0, 3.0]
    assert dash_array("solid", 1.0) is None


def test_small_triangle_arrowhead_is_4pt_on_1pt_line():
    paths, _ = arrowhead((0, 0), (1, 0), 1.0, {"type": "triangle", "w": "sm", "len": "sm"})
    x0, y0, x1, y1 = paths[0].path.bbox()
    assert x1 - x0 == pytest.approx(4.0)
    assert y1 - y0 == pytest.approx(4.0)


def test_trim_line_end():
    p = Path().move_to(0, 0).line_to(10, 0)
    assert p.trimmed(0, 3).end_tangent()[0] == pytest.approx((7, 0))
    assert p.trimmed(2, 0).start_tangent()[0] == pytest.approx((2, 0))


def test_smooth_path_passes_through_points_smoothly():
    from figassemble.geometry import smooth_path
    pts = [(0, 0), (40, -25), (90, 10), (130, -5)]
    p = smooth_path(pts)
    curves = [s for s in p.segs if s[0] == "C"]
    assert len(curves) == 3
    ends = [(s[5], s[6]) for s in curves]
    assert ends == [pts[1], pts[2], pts[3]]
    # Tangents match where segments meet (no corners at the points)
    for a, b in zip(curves, curves[1:]):
        out_dir = (a[5] - a[3], a[6] - a[4])
        in_dir = (b[1] - a[5], b[2] - a[6])
        cross = out_dir[0] * in_dir[1] - out_dir[1] * in_dir[0]
        assert abs(cross) < 1e-9 * (math.hypot(*out_dir) * math.hypot(*in_dir) + 1)
        assert out_dir[0] * in_dir[0] + out_dir[1] * in_dir[1] > 0


def test_curved_arrow_keeps_its_tip_on_the_end_point():
    from figassemble.geometry import DrawPath
    from figassemble.resolve import Resolver
    item = {"id": "c", "type": "line", "curve": "smooth", "points": [[0, 0], [50, -30], [100, 0]],
            "stroke": {"width": 1, "color": "#000000", "cap": "round"},
            "arrow_end": {"type": "triangle", "w": "sm", "len": "sm"}}
    prims = Resolver({"assets": {}}).resolve(item).prims
    body, head = prims[0], prims[1]
    assert any(s[0] == "C" for s in body.path.segs)
    assert head.meta.get("role") == "line-end"
    assert (100, 0) in [(round(s[1], 6), round(s[2], 6)) for s in head.path.segs if s[0] in "ML"]


def test_outline_sits_under_line_and_head():
    from figassemble.resolve import DrawGroup, Resolver
    item = {"id": "o", "type": "line", "points": [[0, 0], [100, 0]],
            "stroke": {"width": 1, "color": "#000000", "cap": "round"},
            "arrow_end": {"type": "triangle", "w": "sm", "len": "sm"},
            "outline": {"color": "#ffffff", "width": 1.5, "opacity": 1.0}}
    prims = Resolver({"assets": {}}).resolve(item).prims
    assert [p.meta.get("role") for p in prims] == ["outline", "outline", None, "line-end"]
    body, head = prims[0], prims[1]
    assert body.stroke.width == pytest.approx(4.0) and body.stroke.color == "#ffffff"
    assert head.fill.color == "#ffffff" and head.stroke.width == pytest.approx(3.0)
    # A transparent outline fades as one piece
    item["outline"]["opacity"] = 0.4
    prims = Resolver({"assets": {}}).resolve(item).prims
    assert isinstance(prims[0], DrawGroup) and prims[0].opacity == 0.4 and len(prims[0].prims) == 2


def test_outline_of_flat_dashed_line_wraps_dash_ends():
    from figassemble.resolve import Resolver
    item = {"id": "d", "type": "line", "points": [[0, 0], [100, 0]],
            "stroke": {"width": 1, "color": "#000000", "cap": "flat", "dash": "dash"},
            "outline": {"color": "#ffffff", "width": 1.0}}
    outline = Resolver({"assets": {}}).resolve(item).prims[0]
    assert outline.stroke.dash == [6.0, 1.0]            # dash 4 + 2, gap 3 - 2
    x0, _, x1, _ = outline.path.bbox()
    assert (x0, x1) == (pytest.approx(-1.0), pytest.approx(101.0))


def test_arc_becomes_editable_curve():
    from figassemble.geometry import DrawPath
    from figassemble.resolve import Resolver, shape_to_curve
    arc = {"id": "a1", "type": "shape", "geom": "arc", "frame": [10, 10, 60, 40], "rot": 30,
           "adj": {"adj1": 270, "adj2": 0}, "stroke": {"width": 1, "color": "#000000"},
           "arrow_end": {"type": "triangle", "w": "sm", "len": "sm"}}
    line = shape_to_curve(arc)
    assert line["type"] == "line" and line["curve"] == "smooth" and line["id"] == "a1"
    assert len(line["points"]) == 3 and line["arrow_end"]["type"] == "triangle"
    path = [p for p in Resolver({"assets": {}}).resolve(dict(arc, arrow_end=None)).prims
            if isinstance(p, DrawPath) and p.stroke][0].path
    start, end = path.start_tangent()[0], path.end_tangent()[0]
    assert line["points"][0] == pytest.approx(list(start), abs=1e-6)
    assert line["points"][-1] == pytest.approx(list(end), abs=1e-3)


def test_trim_curve_end_by_arc_length():
    r = 10.0
    p = Path().move_to(r, 0).arc_to(r, r, 0, 90)   # quarter circle, length pi*r/2
    t = p.trimmed(0, math.pi * r / 4)               # half of it
    end = t.end_tangent()[0]
    assert math.hypot(end[0], end[1]) == pytest.approx(r, abs=1e-3)
    assert math.degrees(math.atan2(end[1], end[0])) == pytest.approx(45, abs=0.1)

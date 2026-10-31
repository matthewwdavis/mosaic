import math

import pytest

from figassemble.geometry import (Matrix, Path, arrowhead, dash_array, frame_matrix, preset_paths)


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


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


def test_trim_curve_end_by_arc_length():
    r = 10.0
    p = Path().move_to(r, 0).arc_to(r, r, 0, 90)   # quarter circle, length pi*r/2
    t = p.trimmed(0, math.pi * r / 4)               # half of it
    end = t.end_tangent()[0]
    assert math.hypot(end[0], end[1]) == pytest.approx(r, abs=1e-3)
    assert math.degrees(math.atan2(end[1], end[0])) == pytest.approx(45, abs=0.1)

"""Connection points: corners and side middles of a shape's own outline, ends, dashes."""
import math

import pytest

from mosaic import connect
from mosaic.app.api import Api


def sites(geom, stroke=None, w=100, h=60, **kw):
    item = {"geom": geom, "frame": [0, 0, w, h], "stroke": stroke or {"width": 1}, **kw}
    return {k: (u, v) for k, u, v in connect.shape_sites(item)}


def test_rectangle_has_its_corners_and_side_middles():
    s = sites("rect")
    assert [x for k in range(4) for x in s[f"c{k}"]] == pytest.approx([0, 0, 1, 0, 1, 1, 0, 1])
    assert [x for k in range(4) for x in s[f"m{k}"]] == pytest.approx([0.5, 0, 1, 0.5, 0.5, 1, 0, 0.5])
    assert len(s) == 8


def test_triangle_and_star_use_their_real_corners():
    s = sites("triangle")
    flat = lambda kind: [x for k, v in sorted(s.items(), key=lambda kv: kv[1]) if k[0] == kind for x in v]
    assert flat("c") == pytest.approx([0, 1, 0.5, 0, 1, 1])
    assert flat("m") == pytest.approx([0.25, 0.5, 0.5, 1, 0.75, 0.5])
    star = sites("star5", w=100, h=100)
    assert sum(k[0] == "c" for k in star) == 10 and sum(k[0] == "m" for k in star) == 10


def test_ellipse_gets_eight_points_round_it():
    s = sites("ellipse", w=80, h=80)
    assert sorted(s) == [f"p{k}" for k in range(8)]
    for u, v in s.values():   # all on the circle
        assert math.hypot(u - 0.5, v - 0.5) == pytest.approx(0.5, abs=1e-3)
    assert s["p0"] == pytest.approx((1, 0.5)) and s["p6"] == pytest.approx((0.5, 0))


def test_rounded_corners_attach_at_their_middles():
    s = sites("roundRect")
    assert 0 < s["c0"][0] < 0.1 and 0 < s["c0"][1] < 0.1      # on the rounded corner, inside the frame's
    assert s["m0"] == pytest.approx((0.5, 0), abs=1e-6)


def test_open_shapes_attach_at_their_ends_too():
    s = sites("arc")
    assert s["e0"] == pytest.approx((0.5, 0), abs=1e-6) and s["e1"] == pytest.approx((1, 0.5), abs=1e-6)


def test_dashed_outlines_add_each_dashs_ends_and_middle():
    dotted = sites("rect", {"width": 2, "dash": "sysDot", "cap": "round"})
    dots = [v for k, v in dotted.items() if k.startswith("d")]
    assert all(k.endswith("m") for k in dotted if k.startswith("d"))      # a dot has only its middle
    for corner in [(0, 0), (1, 0), (1, 1), (0, 1)]:                          # a dot on every corner
        assert any(math.dist(d, corner) < 1e-6 for d in dots)
    dashed = sites("rect", {"width": 1, "dash": "dash", "cap": "flat"})
    starts = [k for k in dashed if k.startswith("d") and k.endswith("s")]
    assert starts and all(k[:-1] + "m" in dashed and k[:-1] + "e" in dashed for k in starts)


def test_the_engine_returns_connection_points(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path))
    api = Api()
    shape = {"id": "s", "type": "shape", "geom": "rect", "frame": [10, 10, 50, 30], "rot": 0, "fill": None,
             "stroke": {"color": "#000000", "width": 1}}
    line = {"id": "l", "type": "line", "points": [[0, 0], [100, 0]],
            "stroke": {"color": "#000000", "width": 1, "dash": "dash", "cap": "flat"}}
    res = {r["id"]: r for r in api.resolve({}, [shape, line])}
    assert ["c0", 0.0, 0.0] in [list(x) for x in res["s"]["sites"]]
    dash_sites = res["l"]["sites"]
    assert dash_sites[0][0] == "d0s" and dash_sites[0][1:] == pytest.approx([0, 0])   # the first dash starts at the end
    assert dash_sites[-1][0].endswith("e") and dash_sites[-1][1:] == pytest.approx([100, 0])

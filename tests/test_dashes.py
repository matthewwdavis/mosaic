"""Even dash spacing: a dash or dot on every corner and line end, whole repeats between them."""
import math
import re

import pytest

from figassemble import dashes, model, presets
from figassemble.geometry import Path, dash_array
from figassemble.resolve import Resolver


def pieces(path: Path):
    """Each dash as its list of points (curves by their end points)."""
    return [[(s[-2], s[-1]) for s in sub.segs if s[0] in "MLC"] for sub in path.subpaths()]


def dot_centres(path: Path):
    return [p[0] for p in pieces(path)]


def near(p, q, tol=1e-6):
    return math.dist(p, q) < tol


def rect(w, h):
    return Path().move_to(0, 0).line_to(w, 0).line_to(w, h).line_to(0, h).close()


def test_dotted_rectangle_has_a_dot_on_every_corner_and_even_sides():
    dots = dot_centres(dashes.layout(rect(100, 60), [0, 4]).path())
    for corner in [(0, 0), (100, 0), (100, 60), (0, 60)]:
        assert sum(near(d, corner) for d in dots) == 1, corner
    for side, axis in [(lambda d: abs(d[1]) < 1e-9, 0), (lambda d: abs(d[0] - 100) < 1e-9, 1)]:
        xs = sorted(d[axis] for d in dots if side(d))
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        assert max(gaps) - min(gaps) < 1e-6 and abs(gaps[0] - 4) < 0.2


def test_dashed_square_centres_a_dash_on_each_corner():
    for dash in pieces(dashes.layout(rect(60, 60), [8, 6]).path()):
        corner = [p for p in dash[1:-1]]
        if corner:   # the dash bends round a corner, with equal arms
            assert len(corner) == 1
            assert math.dist(dash[0], corner[0]) == pytest.approx(math.dist(corner[0], dash[-1]), abs=1e-6)
    bent = sum(1 for d in pieces(dashes.layout(rect(60, 60), [8, 6]).path()) if len(d) == 3)
    assert bent == 4


def test_closed_curves_have_no_seam():
    path = presets.shape_paths("ellipse", 50, 50)[0].path
    dots = dot_centres(dashes.layout(path, [0, 3]).path())
    steps = [math.dist(a, b) for a, b in zip(dots, dots[1:] + dots[:1])]
    assert max(steps) - min(steps) < 1e-3 * max(steps)


def test_lines_start_and_end_on_whole_dashes():
    d = pieces(dashes.layout(Path().move_to(0, 0).line_to(100, 0), [5, 3]).path())
    assert near(d[0][0], (0, 0)) and near(d[-1][-1], (100, 0))
    lengths = [math.dist(p[0], p[-1]) for p in d]
    gaps = [math.dist(a[-1], b[0]) for a, b in zip(d, d[1:])]
    assert max(lengths) - min(lengths) < 1e-6 and max(gaps) - min(gaps) < 1e-6


def test_a_bend_in_a_line_gets_a_dash_centred_on_it():
    path = Path().move_to(0, 0).line_to(50, 0).line_to(50, 40)
    bent = [p for p in pieces(dashes.layout(path, [4, 3]).path()) if len(p) == 3]
    assert len(bent) == 1 and near(bent[0][1], (50, 0))
    assert math.dist(bent[0][0], bent[0][1]) == pytest.approx(math.dist(bent[0][1], bent[0][2]), rel=0.1)


def test_rounded_corners_are_alike():
    path = presets.shape_paths("roundRect", 90, 60)[0].path
    dots = dot_centres(dashes.layout(path, [0, 4]).path())
    # Mirrored across both centre lines the dots land on each other
    for mirror in (lambda p: (90 - p[0], p[1]), lambda p: (p[0], 60 - p[1])):
        assert all(min(math.dist(mirror(d), e) for e in dots) < 1e-3 for d in dots)


def test_dots_on_tight_curves_keep_their_spacing():
    path = presets.shape_paths("roundRect", 60, 20, {"adj": 0.5})[0].path   # a stadium: tight ends
    dots = dot_centres(dashes.layout(path, [0, 2]).path())
    steps = [math.dist(a, b) for a, b in zip(dots, dots[1:] + dots[:1])]
    # Measured straight across, the dots round the ends are as far apart as along the sides
    # (each stretch between corners is fitted on its own, so allow a little between them)
    assert max(steps) / min(steps) < 1.06


def resolve_shape(stroke, geom="rect", outline=None):
    doc = model.new_document()
    item = {"id": "s", "type": "shape", "geom": geom, "frame": [10, 10, 80, 40], "rot": 0, "fill": None,
            "stroke": stroke}
    if outline:
        item["outline"] = outline
    return Resolver(doc).resolve(item).prims


def test_the_switch_keeps_powerpoints_spacing():
    stroke = {"color": "#000000", "width": 1, "dash": "dash", "cap": "flat"}
    even = resolve_shape(stroke)[0]
    assert even.stroke.dash is None and len(even.path.subpaths()) > 4
    plain = resolve_shape({**stroke, "even_dashes": False})[0]
    assert plain.stroke.dash == dash_array("dash", 1, "flat") and len(plain.path.subpaths()) == 1


def test_square_caps_become_flat_dashes_of_full_length():
    prim = resolve_shape({"color": "#000000", "width": 2, "dash": "sysDot", "cap": "square"})[0]
    assert prim.stroke.cap == "flat"
    lengths = {round(math.dist(p[0], p[-1]), 6) for p in pieces(prim.path) if len(p) == 2}
    assert lengths == {2.0}   # each dot a 2 pt square: the zero-length dash plus half a width each side


def test_outline_hugs_flat_dashes():
    prims = resolve_shape({"color": "#000000", "width": 1, "dash": "dash", "cap": "flat"},
                          outline={"color": "#ffffff", "width": 1, "opacity": 1})
    outline, line = prims[0], prims[1]
    assert outline.meta["role"] == "outline" and outline.stroke.dash is None
    straight = lambda path: sorted(math.dist(p[0], p[-1]) for p in pieces(path) if len(p) == 2)
    assert [round(o - m, 6) for o, m in zip(straight(outline.path), straight(line.path))] == [2.0] * len(straight(line.path))


def test_exports_draw_dashes_without_a_dash_pattern(cache, tmp_path):
    import pikepdf
    from figassemble.export.run import export_document
    doc = model.new_document()
    doc["pages"][0]["items"].append({"id": "s", "type": "shape", "geom": "roundRect", "frame": [10, 10, 80, 40],
                                     "rot": 0, "fill": None,
                                     "stroke": {"color": "#000000", "width": 1, "dash": "sysDot", "cap": "round"}})
    out = export_document(doc, str(tmp_path / "d"), ["pdf", "svg"], cache=cache)
    with pikepdf.open(out["files"][0]) as pdf:
        content = pdf.pages[0].Contents.read_bytes().decode("latin-1")
    svg = open(out["files"][1], encoding="utf-8").read()
    assert not re.search(r"\[[^\]]*\]\s+[\d.]+\s+d\b", content) and re.search(r"\b1 J\b", content)   # round caps, no dashes
    assert "stroke-dasharray" not in svg and "stroke-linecap:round" in svg

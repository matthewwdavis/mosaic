"""Pathfinder: shapes combined into one freeform shape, curves kept (pathfinder.py)."""
import pytest

from mosaic.pathfinder import _to_skia, combine
from mosaic.resolve import Resolver, item_area


def square(id_, x, y, colour, rot=0):
    return {"id": id_, "type": "shape", "geom": "rect", "frame": [x, y, 10, 10], "rot": rot, "fill": {"color": colour},
            "stroke": {"color": "#000000", "width": 1}}


def area(shape):
    return round(_to_skia(item_area(shape)).area, 3)


def test_the_four_ways_of_combining_two_squares():
    back, front = square("a", 0, 0, "#ff0000"), square("b", 5, 5, "#0000ff")
    assert area(combine([back, front], "unite")) == 175
    assert area(combine([back, front], "minus_front")) == 75
    assert area(combine([back, front], "intersect")) == 25
    assert area(combine([back, front], "exclude")) == 150
    # The top shape's style, or for Minus front the bottom one's
    assert combine([back, front], "unite")["fill"]["color"] == "#0000ff"
    assert combine([back, front], "minus_front")["fill"]["color"] == "#ff0000"


def test_curves_stay_curves_and_turns_count():
    circles = [{"id": f"c{i}", "type": "shape", "geom": "ellipse", "frame": [x, 0, 20, 20], "rot": 0, "fill": {"color": "#56b4e9"}}
               for i, x in enumerate((0, 10))]
    united = combine(circles, "unite")
    cmds = [c[0] for sp in united["path"]["subpaths"] for c in sp["cmds"]]
    assert cmds.count("C") >= 6 and "L" not in cmds
    # A square turned 45 degrees reaches further than an upright one
    assert combine([square("a", 0, 0, "#f00", rot=45), square("b", 0, 0, "#00f")], "unite")["frame"][2] > 14
    # The result draws as an ordinary freeform shape
    assert Resolver({"assets": {}}).resolve({**united, "id": "u"}).prims


def test_nothing_left_or_nothing_to_combine():
    with pytest.raises(ValueError):
        combine([square("a", 0, 0, "#f00"), square("b", 50, 50, "#00f")], "intersect")
    with pytest.raises(ValueError):
        combine([square("a", 0, 0, "#f00"), {"id": "l", "type": "line", "points": [[0, 0], [5, 5]]}], "unite")

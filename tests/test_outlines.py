"""Outline types: where an item's outline goes among what it draws (resolve.with_outline)."""
from figassemble.geometry import DrawPath
from figassemble.resolve import DrawGroup, Resolver


def drawn(outline_type, dash="solid", stroke=True, fill=True):
    item = {"id": "s", "type": "shape", "geom": "rect", "frame": [10, 10, 80, 60], "rot": 0,
            "stroke": {"color": "#1f3a93", "width": 3, "dash": dash, "cap": "round", "join": "round"} if stroke else None,
            "fill": {"color": "#cfe3ff"} if fill else None,
            "outline": {"color": "#ff9900", "width": 2, "opacity": 1, "type": outline_type}}
    return Resolver({"assets": {}}).resolve(item).prims


def kinds(prims):
    """Each primitive as outline-fill, outline-line, fill or line, in drawing order."""
    out = []
    for p in prims:
        assert isinstance(p, DrawPath)
        # (a fill's outline is the fill grown by a stroke round it, so it has both)
        role = "outline-" if p.meta.get("role") == "outline" else ""
        out.append(role + ("fill" if p.fill is not None else "line"))
    return out


def test_outside_is_underneath_everything():
    assert kinds(drawn("outside")) == ["outline-fill", "outline-line", "fill", "line"]
    assert kinds(drawn("outside")) == kinds(drawn(None))   # the default


def test_both_sides_sits_between_the_fill_and_its_line():
    # Over the fill, under the line, and no band along the fill's edge
    assert kinds(drawn("both")) == ["fill", "outline-line", "line"]
    assert kinds(drawn("both", dash="dash")) == ["fill", "outline-line", "line"]


def test_outside_gaps_empty_drops_the_band_along_a_dashed_fill():
    assert kinds(drawn("outside_gaps", dash="dash")) == ["outline-line", "fill", "line"]
    # A solid line has no gaps: the same as Outside
    assert kinds(drawn("outside_gaps")) == kinds(drawn("outside"))


def test_a_shape_with_no_line_is_outlined_outside_whatever_the_type():
    for t in ("outside", "both", "outside_gaps"):
        assert kinds(drawn(t, stroke=False)) == ["outline-fill", "fill"], t


def test_transparent_outline_is_one_group():
    item = {"id": "l", "type": "line", "points": [[0, 0], [50, 0]], "stroke": {"color": "#000", "width": 2},
            "arrow_end": {"type": "triangle", "w": "med", "len": "med"},
            "outline": {"color": "#fff", "width": 2, "opacity": 0.5, "type": "both"}}
    prims = Resolver({"assets": {}}).resolve(item).prims
    # A line has no inside: Both sides draws as Outside, the outline one see-through group under it
    assert isinstance(prims[0], DrawGroup) and not any(isinstance(p, DrawGroup) for p in prims[1:])

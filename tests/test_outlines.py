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


def pieces(prim):
    """How many separate pieces a primitive's path has (one per dash for a dashed line)."""
    return sum(1 for s in prim.path.segs if s[0] == "M")


def test_both_sides_gaps_filled_outlines_the_whole_dashed_line():
    # Between the fill and the dashes, like Both sides, but round the line drawn whole
    prims = drawn("both_filled", dash="dash")
    assert kinds(prims) == ["fill", "outline-line", "line"]
    outline, line = prims[1], prims[2]
    assert pieces(line) > 1 and pieces(outline) == 1 and not outline.stroke.dash
    # Round a solid line it's the same as Both sides
    assert kinds(drawn("both_filled")) == kinds(drawn("both"))
    assert drawn("both_filled")[1].path.segs == drawn("both")[1].path.segs
    # With no fill there's no inside to keep clear: the whole line's outline goes underneath
    prims = drawn("both_filled", dash="dash", fill=False)
    assert kinds(prims) == ["outline-line", "line"] and pieces(prims[0]) == 1


def test_a_shape_with_no_line_is_outlined_outside_whatever_the_type():
    for t in ("outside", "both", "outside_gaps", "both_filled"):
        assert kinds(drawn(t, stroke=False)) == ["outline-fill", "fill"], t


def test_an_open_arrowhead_never_has_an_outline_over_its_line():
    # An open head is a stroked line drawn after the line it ends: the outlines of both go
    # before either, so the head's outline can't cut across the line's end
    line = {"id": "l", "type": "line", "points": [[0, 0], [50, 0]], "stroke": {"color": "#000", "width": 2, "dash": "dash"},
            "arrow_end": {"type": "arrow", "w": "med", "len": "med"}}
    arc = {"id": "a", "type": "shape", "geom": "arc", "frame": [10, 10, 80, 60], "rot": 0, "fill": {"color": "#cfe3ff"},
           "stroke": {"color": "#000", "width": 3, "dash": "dash"}, "arrow_end": {"type": "arrow", "w": "med", "len": "med"}}
    for item, t in ((line, "both_filled"), (arc, "both"), (arc, "both_filled")):
        prims = Resolver({"assets": {}}).resolve(dict(item, outline={"color": "#fff", "width": 2, "type": t})).prims
        roles = [p.meta.get("role") for p in prims if p.meta.get("role") != "body"]
        assert roles == ["outline", "outline", None, "line-end"], (item["id"], t, roles)


def test_transparent_outline_is_one_group():
    for t, head in (("both", "triangle"), ("both_filled", "triangle"), ("both_filled", "arrow")):
        item = {"id": "l", "type": "line", "points": [[0, 0], [50, 0]], "stroke": {"color": "#000", "width": 2},
                "arrow_end": {"type": head, "w": "med", "len": "med"},
                "outline": {"color": "#fff", "width": 2, "opacity": 0.5, "type": t}}
        prims = Resolver({"assets": {}}).resolve(item).prims
        # A line has no inside: both sides draw as Outside, the outline one see-through group under it
        assert isinstance(prims[0], DrawGroup) and not any(isinstance(p, DrawGroup) for p in prims[1:]), (t, head)

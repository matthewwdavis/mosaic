"""Outline types: where an item's outline goes among what it draws (resolve.with_outline)."""
import pikepdf
from lxml import etree

from figassemble import presets
from figassemble.export.run import export_document
from figassemble.export.svgwriter import fragment
from figassemble.geometry import DrawPath
from figassemble.resolve import DrawGroup, Resolver


def drawn(outline_type, dash="solid", stroke=True, fill=True, geom="rect"):
    item = {"id": "s", "type": "shape", "geom": geom, "frame": [10, 10, 80, 60], "rot": 0,
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


def layers(prims):
    """Like kinds, with a clipped outline group as clipped(...its contents...): a band along the
    area's edge is twice the outline's width (4 pt in drawn), a line's outline wider."""
    out = []
    for p in prims:
        if isinstance(p, DrawGroup) and p.clip:
            out.append("clipped(" + " ".join("band" if q.fill is None and q.stroke.width == 4.0 else "outline"
                                             for q in p.prims) + ")")
        else:
            out += kinds([p])
    return out


def test_inside_is_kept_to_the_shape_over_its_fill():
    # Over the fill and under the line, clipped to the rectangle, with a band along its edge
    # that runs through the gaps of a dashed line (Inside, gaps filled)
    prims = drawn("inside", dash="dash")
    assert layers(prims) == ["fill", "clipped(band outline)", "line"]
    (clip, even_odd), = prims[1].clip
    assert clip.segs == prims[0].path.segs and not even_odd
    # Gaps empty: only round each dash; a solid line has no gaps, so the band stays
    assert layers(drawn("inside_gaps", dash="dash")) == ["fill", "clipped(outline)", "line"]
    assert layers(drawn("inside_gaps")) == layers(drawn("inside"))
    # A fill with no line: a band just inside its edge
    assert layers(drawn("inside", stroke=False)) == ["fill", "clipped(band)"]
    # No fill: kept inside the area the shape's own line goes round
    assert layers(drawn("inside", fill=False)) == ["clipped(band outline)", "line"]


def test_outside_only_keeps_off_an_unfilled_shapes_inside():
    # Everything but the rectangle: a box round it with the rectangle cut out, even-odd
    prims = drawn("outside_only", fill=False, dash="dash")
    assert layers(prims) == ["clipped(band outline)", "line"]
    assert layers(drawn("outside_only_gaps", fill=False, dash="dash")) == ["clipped(outline)", "line"]
    (clip, even_odd), = prims[0].clip
    assert even_odd and len(clip.subpaths()) == 2
    # A fill already hides the inside: the same as Outside
    assert layers(drawn("outside_only", dash="dash")) == layers(drawn("outside", dash="dash"))
    assert layers(drawn("outside_only_gaps", dash="dash")) == layers(drawn("outside_gaps", dash="dash"))


def test_a_line_with_no_inside_keeps_its_gaps_choice():
    line = {"id": "l", "type": "line", "points": [[0, 0], [50, 0], [50, 40]], "stroke": {"color": "#000", "width": 2, "dash": "dash"}}

    def with_type(item, t):
        return layers(Resolver({"assets": {}}).resolve(dict(item, outline={"color": "#fff", "width": 2, "type": t})).prims)
    brackets = {"id": "b", "type": "shape", "geom": "bracketPair", "frame": [0, 0, 80, 60], "rot": 0,
                "stroke": {"color": "#000", "width": 2, "dash": "dash"}, "fill": None}
    for item in (line, brackets):
        for t in ("inside", "outside_only"):
            assert with_type(item, t) == with_type(item, "both_filled"), (item["id"], t)
        for t in ("inside_gaps", "outside_only_gaps"):
            assert with_type(item, t) == with_type(item, "both"), (item["id"], t)


def test_which_shapes_lines_go_all_the_way_round():
    for geom in ("rect", "ellipse", "star5", "can", "cube", "foldedCorner", "curvedRightArrow"):
        assert presets.encloses(geom), geom
    for geom in ("line", "arc", "bracketPair", "leftBrace", "chartPlus", "callout1", "bentConnector3"):
        assert not presets.encloses(geom), geom
    assert presets.catalog()["shapes"]["can"]["closed"] is True


def test_an_area_of_several_paths_is_clipped_to_their_union():
    # A cube's three faces: one even-odd clip round all of them
    prims = drawn("inside", fill=False, geom="cube")
    (group,) = [p for p in prims if isinstance(p, DrawGroup)]
    (clip, even_odd), = group.clip
    assert even_odd and len(clip.subpaths()) == 1


def test_clipped_outlines_in_svg_pdf_and_the_editor(tmp_path):
    from figassemble.app.api import Api
    doc = Api().new_document()
    item = {"id": "r", "type": "shape", "geom": "rect", "frame": [20, 20, 120, 60], "rot": 0, "fill": None,
            "stroke": {"color": "#000", "width": 2, "dash": "dash"},
            "outline": {"color": "#ff9900", "width": 2, "opacity": 0.5, "type": "outside_only"}}
    doc["pages"][0]["items"] = [item]
    export_document(doc, str(tmp_path / "o"), ["svg", "pdf"])
    ns = "{http://www.w3.org/2000/svg}"
    svg = etree.parse(str(tmp_path / "o.svg"))
    (cp,) = svg.findall(f".//{ns}clipPath")
    assert cp[0].get("clip-rule") == "evenodd"
    clipped = [g for g in svg.iter(f"{ns}g") if f"url(#{cp.get('id')})" in (g.get("style") or "")]
    assert len(clipped) == 1 and clipped[0][0].get("opacity") == "0.5"
    pdf = pikepdf.open(str(tmp_path / "o.pdf"))
    content = pdf.pages[0].Contents.read_bytes().decode("latin-1")
    assert "\nW*\nn\n" in content
    # The editor's copy gives the clip its own id, so items don't share one
    frag = fragment(Resolver({"assets": {}}).resolve(item), "it7")
    assert 'id="it7-fa-clip1"' in frag and "url(#it7-fa-clip1)" in frag


def test_transparent_outline_is_one_group():
    for t, head in (("both", "triangle"), ("both_filled", "triangle"), ("both_filled", "arrow")):
        item = {"id": "l", "type": "line", "points": [[0, 0], [50, 0]], "stroke": {"color": "#000", "width": 2},
                "arrow_end": {"type": head, "w": "med", "len": "med"},
                "outline": {"color": "#fff", "width": 2, "opacity": 0.5, "type": t}}
        prims = Resolver({"assets": {}}).resolve(item).prims
        # A line has no inside: both sides draw as Outside, the outline one see-through group under it
        assert isinstance(prims[0], DrawGroup) and not any(isinstance(p, DrawGroup) for p in prims[1:]), (t, head)

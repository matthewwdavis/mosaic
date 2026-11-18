"""Significance brackets: a bar with end ticks and its label beyond it (resolve._bracket)."""
from mosaic.resolve import DrawText, Resolver


def drawn(**kw):
    item = {"id": "b", "type": "bracket", "frame": [10, 10, 60, 13], "label": "**", "size": 6, "dir": "up"} | kw
    return Resolver({"assets": {}}).resolve(item).prims


def test_a_bracket_over_two_bars():
    line, text = drawn()
    # Ticks down from the bar to the frame's bottom; the label room (6 pt text: 9 pt) above the bar
    assert line.path.to_svg(1) == "M10 23L10 19L70 19L70 23"
    assert line.stroke.cap == "round" and line.stroke.join == "miter"
    assert isinstance(text, DrawText) and text.runs[0].text == "**" and text.bbox()[3] <= 19
    assert abs((text.bbox()[0] + text.bbox()[2]) / 2 - 40) < 0.5   # centred over the bar


def test_the_other_sides_and_no_label():
    line, text = drawn(dir="down")
    assert line.path.to_svg(1) == "M10 10L10 14L70 14L70 10" and text.bbox()[1] >= 14
    line, text = drawn(dir="right", frame=[10, 10, 20, 50], tick=4)
    assert line.path.to_svg(1) == "M10 10L14 10L14 60L10 60" and text.bbox()[0] >= 14
    line, text = drawn(dir="left", frame=[10, 10, 20, 50], tick=4)
    assert line.path.to_svg(1) == "M30 10L26 10L26 60L30 60" and text.bbox()[2] <= 26
    (line,) = drawn(label="", frame=[10, 10, 60, 4])
    assert line.path.to_svg(1) == "M10 14L10 10L70 10L70 14"


def test_a_bracket_with_a_line_of_its_own_and_its_label_a_gap_from_it():
    from mosaic.resolve import DrawText, Resolver, ink_box
    resolver = Resolver({"assets": {}})
    old = {"id": "b", "type": "bracket", "frame": [10, 10, 60, 13], "label": "*", "size": 6, "dir": "up", "tick": 4,
           "color": "#d55e00", "line_width": 1.25}
    # From before brackets had a stroke: drawn with its colour and width, round ends, mitred corners
    line = Resolver({"assets": {}}).resolve(old).prims[0]
    assert (line.stroke.color, line.stroke.width, line.stroke.cap, line.stroke.join) == ("#d55e00", 1.25, "round", "miter")
    new = {**{k: v for k, v in old.items() if k not in ("color", "line_width")}, "label": "p < 0.05", "gap": 0.5, "italic": True,
           "frame": [10, 10, 60, 4 + 0.5 + 7.2],
           "stroke": {"color": "#000000", "width": 1, "dash": "dash", "cap": "flat", "join": "round", "opacity": 0.5}}
    r = resolver.resolve(new)
    text = [p for p in r.prims if isinstance(p, DrawText)][0]
    _, _, _, bottom = ink_box(text)
    bar = 10 + 0.5 + 7.2   # the bar's middle: under the label's room (the gap and a line of text)
    assert abs((bar - 0.5) - text.matrix.apply(0, bottom)[1] - 0.5) < 1e-9 and abs(r.label_gap - 0.5) < 1e-9
    assert text.runs[0].opacity == 0.5 and text.runs[0].color == "#000000"   # the line's colour and transparency
    line = r.prims[0]
    assert line.stroke.opacity == 0.5 and line.meta.get("dashes")   # see-through, its dashes laid out evenly
    # An outline round the lines, and on its own switch round the letters
    plain = len(resolver.resolve({**new, "stroke": {**new["stroke"], "opacity": 1}}).prims)
    lines_only = resolver.resolve({**new, "stroke": {**new["stroke"], "opacity": 1}, "outline": {"color": "#ffffff", "width": 0.5}})
    both = resolver.resolve({**new, "stroke": {**new["stroke"], "opacity": 1}, "outline": {"color": "#ffffff", "width": 0.5, "text": True}})
    text_only = resolver.resolve({**new, "stroke": {**new["stroke"], "opacity": 1},
                                  "outline": {"color": "#ffffff", "width": 0.5, "text": True, "lines": False}})
    assert len(lines_only.prims) > plain and len(both.prims) > len(lines_only.prims) and len(text_only.prims) == len(both.prims) - (len(lines_only.prims) - plain)


def test_a_rich_label_only_its_p_in_italics():
    from mosaic.resolve import DrawText, Resolver
    bracket = {"id": "b", "type": "bracket", "frame": [10, 10, 60, 13], "label": "P < 0.05", "size": 7, "dir": "up", "tick": 4, "bold": True,
               "stroke": {"color": "#0072b2", "width": 0.75}, "text": {"paragraphs": [{"runs": [{"t": "P", "italic": True}, {"t": " < 0.05"}]}]}}
    r = Resolver({"assets": {}}).resolve(bracket)
    runs = [run for p in r.prims if isinstance(p, DrawText) for run in p.runs]
    assert "".join(run.text for run in runs) == "P < 0.05"
    italic = [("Italic" in run.face.ps_name or "Oblique" in run.face.ps_name or run.skew > 0) for run in runs]
    assert italic[0] and not any(italic[1:])   # only the P
    assert all(run.size == 7 and run.color == "#0072b2" for run in runs)   # the whole label's size, in the line's colour
    assert all("Bold" in run.face.ps_name for run in runs)   # the whole label's bold, on every letter
    assert r.text_box is not None and len(r.text_box) == 4   # where the editor goes to type in it

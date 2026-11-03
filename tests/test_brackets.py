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

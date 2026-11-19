"""Scale bars: a picture's scale read from microscope TIFFs, and the bar the engine draws."""
from PIL import Image, TiffImagePlugin

from mosaic.assets import probe
from mosaic.resolve import DrawText, Resolver


def tiff(path, description=None, resolution=None):
    info = TiffImagePlugin.ImageFileDirectory_v2()
    if description is not None:
        info[270] = description
    if resolution is not None:
        info[282] = info[283] = resolution
    Image.new("L", (100, 50), 128).save(path, tiffinfo=info)
    return str(path)


def test_the_scale_microscopes_and_imagej_save(tmp_path):
    # ImageJ: the unit, and the resolution as pixels per unit (0.325 µm pixels)
    info = probe(tiff(tmp_path / "ij.tif", "ImageJ=1.54f\nimages=1\nunit=micron\n", 1 / 0.325))
    cal = info["calibration"]
    assert cal["unit"] == "µm" and abs(cal["per_px"] - 0.325) < 1e-6 and cal["from"] == "ImageJ"
    # Its resolution tags are pixels per micron, not a print resolution: placed at the usual 300 dpi
    assert info["dpi_assumed"] and info["size_pt"] == [100 / 300 * 72, 50 / 300 * 72]
    # ImageJ writes µ escaped
    assert probe(tiff(tmp_path / "ij2.tif", "ImageJ=1.54f\nunit=\\u00B5m\n", 2.0))["calibration"]["unit"] == "µm"
    # OME-TIFF: PhysicalSizeX
    ome = '<OME><Image><Pixels PhysicalSizeX="0.5" PhysicalSizeXUnit="nm" SizeX="100"/></Image></OME>'
    cal = probe(tiff(tmp_path / "ome.tif", ome))["calibration"]
    assert cal == {"per_px": 0.5, "unit": "nm", "from": "OME-TIFF"}
    # A plain TIFF's resolution is for printing, not a measurement
    assert "calibration" not in probe(tiff(tmp_path / "plain.tif", None, 300))
    # Imperial units: ImageJ's "inch", OME's "ft"
    cal = probe(tiff(tmp_path / "ij_in.tif", "ImageJ=1.54f\nunit=inch\n", 100.0))["calibration"]
    assert cal["unit"] == "in" and abs(cal["per_px"] - 0.01) < 1e-9
    ome_ft = '<OME><Image><Pixels PhysicalSizeX="0.25" PhysicalSizeXUnit="ft" SizeX="100"/></Image></OME>'
    assert probe(tiff(tmp_path / "ome_ft.tif", ome_ft))["calibration"] == {"per_px": 0.25, "unit": "ft", "from": "OME-TIFF"}


def test_the_bar_and_its_length_written_above_or_below_it():
    bar = {"id": "sb", "type": "scalebar", "frame": [10, 10, 40, 11.2], "length": 50, "unit": "µm", "thickness": 2,
           "size": 6, "label": "above", "color": "#ffffff"}
    prims = Resolver({"assets": {}}).resolve(bar).prims
    rect, text = prims
    assert rect.path.bbox() == (10, 19.2, 50, 21.2)   # at the bottom of its frame, as long as the frame
    assert isinstance(text, DrawText) and text.runs[0].text == "50 µm" and text.bbox()[3] < 19.2
    below = Resolver({"assets": {}}).resolve({**bar, "label": "below"}).prims
    assert below[0].path.bbox()[1] == 10 and below[1].bbox()[1] > 12
    assert len(Resolver({"assets": {}}).resolve({**bar, "label": "none", "frame": [10, 10, 40, 2]}).prims) == 1


def test_the_gap_is_to_the_letters_and_the_bar_turns_with_its_label():
    from mosaic.resolve import ink_extent
    bar = {"id": "sb", "type": "scalebar", "frame": [10, 10, 40, 2 + 0.5 + 7.2], "length": 50, "unit": "µm", "thickness": 2,
           "size": 6, "label": "above", "color": "#ffffff", "gap": 0.5}
    resolver = Resolver({"assets": {}})

    def letters(r):   # the letters' outline on the page, y down
        text = r.prims[1]
        top, bottom = ink_extent(text)
        return text.matrix.apply(0, top)[1], text.matrix.apply(0, bottom)[1]

    # Above: the µ's tail 0.5 pt over the bar's top; the engine says so, and puts the handle there
    r = resolver.resolve(bar)
    bar_top = r.prims[0].path.bbox()[1]
    assert abs(bar_top - letters(r)[1] - 0.5) < 1e-9 and abs(r.label_gap - 0.5) < 1e-9
    assert r.handles == [[20.0, bar["frame"][3] - 2 - 0.5]]
    # 0 touches; below, the tops of the letters stand off the bar's underside
    touching = resolver.resolve({**bar, "gap": 0})
    assert abs(touching.prims[0].path.bbox()[1] - letters(touching)[1]) < 1e-9
    below = resolver.resolve({**bar, "label": "below", "gap": 1})
    assert abs(letters(below)[0] - below.prims[0].path.bbox()[3] - 1) < 1e-9 and abs(below.label_gap - 1) < 1e-9
    # A bar from before gaps: drawn as it was (the line box 0.3 sizes off), its letters' gap reported
    # (how far depends on the font's line height: about 2 pt with the Mac's Helvetica, 0.8 pt with
    # what Windows has for it)
    old = resolver.resolve({k: v for k, v in bar.items() if k != "gap"} | {"frame": [10, 10, 40, 11.2]})
    assert old.prims[0].path.bbox() == (10, 19.2, 50, 21.2) and 0 < old.label_gap < 6
    assert abs(letters(old)[1] + old.label_gap - old.prims[0].path.bbox()[1]) < 1e-9
    # Italic, and a turn: a quarter turn makes it upright, its label beside it
    italic = resolver.resolve({**bar, "italic": True}).prims[1]
    assert italic.runs[0].skew or "Italic" in italic.runs[0].face.ps_name or "Oblique" in italic.runs[0].face.ps_name
    turned = resolver.resolve({**bar, "rot": 270})
    x0, y0, x1, y1 = turned.prims[0].path.bbox()
    assert abs((x1 - x0) - 2) < 1e-9 and abs((y1 - y0) - 40) < 1e-9
    tx0, ty0, tx1, ty1 = turned.prims[1].bbox()
    assert ty1 - ty0 > tx1 - tx0 and tx1 < x0   # upright text, left of the bar (its "above" turned)


def test_round_ends_stay_within_the_length():
    bar = {"id": "sb", "type": "scalebar", "frame": [10, 10, 40, 11.2], "length": 50, "unit": "µm", "thickness": 2,
           "size": 6, "label": "above", "color": "#ffffff"}
    resolver = Resolver({"assets": {}})
    square = resolver.resolve(bar).prims[0].path
    assert all(s[0] != "C" for s in square.segs)   # square ends unless asked
    rounded = resolver.resolve({**bar, "ends": "round"}).prims[0].path
    x0, y0, x1, y1 = rounded.bbox()
    # The rounded tips are the length's ends; the bar as thick as before
    assert abs(x0 - 10) < 1e-9 and abs(x1 - 50) < 1e-9 and abs(y0 - 19.2) < 1e-9 and abs(y1 - 21.2) < 1e-9
    assert sum(s[0] == "C" for s in rounded.segs) == 4
    # Turned, the tips are still the length's ends
    turned = resolver.resolve({**bar, "ends": "round", "rot": 90}).prims[0].path.bbox()
    assert abs((turned[3] - turned[1]) - 40) < 1e-9


def test_an_outline_round_the_bar_and_the_text_and_see_through_bars():
    from mosaic.resolve import DrawGroup
    bar = {"id": "sb", "type": "scalebar", "frame": [10, 10, 40, 2 + 0.5 + 7.2], "length": 50, "unit": "µm", "thickness": 2,
           "size": 6, "label": "above", "color": "#ffffff", "gap": 0.5}
    resolver = Resolver({"assets": {}})
    plain = resolver.resolve(bar).prims
    outline = {"color": "#000000", "width": 0.5, "opacity": 1}
    round_bar = resolver.resolve({**bar, "outline": outline}).prims
    both = resolver.resolve({**bar, "outline": {**outline, "text": True}}).prims
    text_only = resolver.resolve({**bar, "outline": {**outline, "text": True, "lines": False}}).prims
    halo = len(both) - len(round_bar)   # one outline per letter drawn ("50 µm": 4)
    assert len(round_bar) == len(plain) + 1 and halo == 4 and len(text_only) == len(plain) + halo
    assert both[0].meta.get("role") == "outline" and isinstance(both[-1], DrawText)   # the letters' outline under all, the text on top
    see_through = resolver.resolve({**bar, "opacity": 0.5, "outline": outline}).prims
    assert len(see_through) == 1 and isinstance(see_through[0], DrawGroup) and see_through[0].opacity == 0.5


def test_the_length_written_left_or_right_of_the_bar():
    from mosaic.resolve import ink_box
    # The frame holds the bar (bar_w), the gap and the letters (label_w, as last measured)
    bar = {"id": "sb", "type": "scalebar", "frame": [10, 10, 40 + 0.5 + 15, 7.2], "length": 50, "unit": "µm", "thickness": 2,
           "size": 6, "label": "right", "color": "#ffffff", "gap": 0.5, "bar_w": 40, "label_w": 15}
    resolver = Resolver({"assets": {}})

    def letters(r):   # the letters' outline on the page (left, top, right, bottom; y down)
        text = r.prims[1]
        left, top, right, bottom = ink_box(text)
        return (*text.matrix.apply(left, top), *text.matrix.apply(right, bottom))

    def figures_middle(r):   # halfway up the numbers, on the page
        text = r.prims[1]
        run = text.runs[0]
        top = max(run.face.ink(g)[3] for ch, g in zip(run.text, run.gids) if ch.isdigit()) * run.size
        return text.matrix.apply(0, run.y - top / 2)[1]

    # Right: the bar along the frame's left side, as long as bar_w and level with the frame's
    # middle; the letters 0.5 pt from its end, the numbers' middle level with the bar's
    right = resolver.resolve(bar)
    x0, y0, x1, y1 = right.prims[0].path.bbox()
    assert (x0, x1) == (10, 50) and abs((y0 + y1) / 2 - 13.6) < 1e-9 and y1 - y0 == 2
    assert abs(letters(right)[0] - (50 + 0.5)) < 1e-9 and abs(right.label_gap - 0.5) < 1e-9
    assert abs(figures_middle(right) - 13.6) < 1e-9 and letters(right)[3] > 13.6 + 2   # (the µ's tail below)
    assert right.handles == [[40.5, 3.6]]
    # The engine says how wide the letters are, for the editor to make room
    lw = right.label_w
    assert abs(lw - (letters(right)[2] - letters(right)[0])) < 1e-9 and 10 < lw < 25
    # Left: the bar along the right side, the letters' right edge 0.5 pt before its start
    left = resolver.resolve({**bar, "label": "left"})
    x0, _, x1, _ = left.prims[0].path.bbox()
    assert abs(x0 - (10 + 15.5)) < 1e-9 and abs(x1 - 65.5) < 1e-9
    assert abs(letters(left)[2] - (x0 - 0.5)) < 1e-9 and abs(left.label_gap - 0.5) < 1e-9
    # The bar keeps its length when the letters are measured wider than the room kept for them
    wide = resolver.resolve({**bar, "label_w": 5})
    assert wide.prims[0].path.bbox()[2] - wide.prims[0].path.bbox()[0] == 40 and wide.label_w == lw
    # No gap set: 0.3 text sizes; no bar_w: what the frame leaves after the gap and letters
    plain = resolver.resolve({k: v for k, v in bar.items() if k not in ("gap", "bar_w")} | {"frame": [10, 10, 40 + 1.8 + 15, 7.2]})
    x0, _, x1, _ = plain.prims[0].path.bbox()
    assert abs(x1 - x0 - 40) < 1e-9 and abs(plain.label_gap - 1.8) < 1e-9
    # Round ends stay within the bar; turned, the label turns with it
    rounded = resolver.resolve({**bar, "ends": "round"}).prims[0].path.bbox()
    assert abs(rounded[0] - 10) < 1e-9 and abs(rounded[2] - 50) < 1e-9
    turned = resolver.resolve({**bar, "rot": 90})
    bx0, by0, bx1, by1 = turned.prims[0].path.bbox()
    tx0, ty0, tx1, ty1 = turned.prims[1].bbox()
    assert abs(bx1 - bx0 - 2) < 1e-9 and abs(by1 - by0 - 40) < 1e-9 and ty0 > by1 - 1e-9   # upright, the label below its end

"""Scale bars: a picture's scale read from microscope TIFFs, and the bar the engine draws."""
from PIL import Image, TiffImagePlugin

from figassemble.assets import probe
from figassemble.resolve import DrawText, Resolver


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

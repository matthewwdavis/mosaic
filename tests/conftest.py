import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session", autouse=True)
def isolated_home(tmp_path_factory):
    """Keep caches out of ~/.figassemble while testing (the font index is reused across tests)."""
    home = tmp_path_factory.mktemp("figassemble-home")
    os.environ["FIGASSEMBLE_HOME"] = str(home)
    os.environ["FIGASSEMBLE_KEYSTORE"] = "file"   # never this computer's Keychain or Credential Manager
    yield home


@pytest.fixture
def cache(tmp_path):
    from figassemble.assets import AssetCache
    return AssetCache(str(tmp_path / "cache"))


@pytest.fixture
def fixtures(tmp_path):
    """A small vector PDF, a matching SVG, a PNG and a JPEG, as R would save a plot."""
    import pikepdf
    from PIL import Image

    d = tmp_path / "Figures"
    d.mkdir()
    # Vector PDF 100 x 50 pt: a filled rectangle and a stroked line
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(100, 50))
    page.obj.Contents = pdf.make_stream(b"0 0 1 rg 10 10 30 20 re f 0 0 0 RG 2 w 50 10 m 90 40 l S")
    pdf.save(d / "plot.pdf")
    # Same plot as SVG with an id and a stylesheet that must not leak
    (d / "plot.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='100pt' height='50pt' viewBox='0 0 100 50'>"
        "<defs><style>* { stroke-linecap: butt; } .bar { fill: blue; }</style>"
        "<clipPath id='cp1'><rect x='0' y='0' width='100' height='50'/></clipPath></defs>"
        "<rect width='100%' height='100%' style='fill: none'/>"
        "<g clip-path='url(#cp1)'><rect class='bar' x='10' y='20' width='30' height='20'/>"
        "<line x1='50' y1='40' x2='90' y2='10' style='stroke: black; stroke-width: 2'/></g></svg>",
        encoding="utf-8")
    Image.new("RGB", (200, 100), (200, 30, 30)).save(d / "plot.png", dpi=(144, 144))
    Image.new("RGB", (60, 40), (20, 120, 200)).save(tmp_path / "photo.jpg", quality=90, dpi=(300, 300))
    rgba = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    rgba.paste((0, 160, 0, 255), (10, 10, 30, 30))
    rgba.save(tmp_path / "icon.png", dpi=(300, 300))
    return {"dir": d, "pdf": str(d / "plot.pdf"), "svg": str(d / "plot.svg"), "png": str(d / "plot.png"),
            "jpg": str(tmp_path / "photo.jpg"), "rgba": str(tmp_path / "icon.png")}

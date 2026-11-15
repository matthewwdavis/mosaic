"""Linux's applications-menu entry (packaging/linux/make_desktop.py): mosaic started from the
environment's Python, its icon, and .mosaic documents (and FigAssemble's .figasm) as its own."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packaging", "linux"))


def test_the_entry_starts_mosaic_and_owns_its_documents(tmp_path):
    import make_desktop
    entry = make_desktop.install(str(tmp_path), python="/home/a/miniforge3/envs/mosaic/bin/python", register=False)
    text = open(entry, encoding="utf-8").read()
    assert 'Exec="/home/a/miniforge3/envs/mosaic/bin/python" -P -m mosaic %f' in text
    assert "MimeType=application/x-mosaic;" in text and "Icon=mosaic" in text
    xml = open(tmp_path / "mime" / "packages" / "mosaic.xml", encoding="utf-8").read()
    assert '<glob pattern="*.mosaic"/>' in xml and '<glob pattern="*.figasm"/>' in xml
    assert (tmp_path / "icons" / "hicolor" / "256x256" / "apps" / "mosaic.png").stat().st_size > 500

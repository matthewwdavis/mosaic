"""The editor's own self-test, run in headless Chrome when it's installed."""
import importlib.util
import os
import shutil

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ui_selftest", os.path.join(HERE, "..", "tools", "ui_selftest.py"))
ui_selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui_selftest)

CHROME = ui_selftest.find_chrome()
POWERPOINT = os.path.join(HERE, "data", "powerpoint")


@pytest.mark.skipif(CHROME is None, reason="Chrome isn't installed")
def test_editor_selftest(fixtures, tmp_path):
    # PowerPoint's: a deck and another like it, a slide and shapes copied in PowerPoint
    deck = os.path.join(POWERPOINT, "example_deck.pptx")
    other = shutil.copy(deck, tmp_path / "other_deck.pptx")
    ppt = [deck, str(other), os.path.join(POWERPOINT, "copied_slide.slides"), os.path.join(POWERPOINT, "copied_rect.gvml")]
    res = ui_selftest.run_selftest([fixtures["svg"], fixtures["pdf"], *ppt], CHROME, str(tmp_path / "shot.png"),
                                   str(tmp_path / "out"))
    report = "\n".join(res["lines"] + res["errors"])
    assert res["done"], "self-test didn't finish:\n" + report
    assert not res["failed"], report

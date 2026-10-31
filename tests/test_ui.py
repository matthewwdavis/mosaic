"""The editor's own self-test, run in headless Chrome when it's installed."""
import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ui_selftest", os.path.join(HERE, "..", "tools", "ui_selftest.py"))
ui_selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui_selftest)

CHROME = ui_selftest.find_chrome()


@pytest.mark.skipif(CHROME is None, reason="Chrome isn't installed")
def test_editor_selftest(fixtures, tmp_path):
    res = ui_selftest.run_selftest([fixtures["svg"], fixtures["pdf"]], CHROME, str(tmp_path / "shot.png"),
                                   str(tmp_path / "out"))
    report = "\n".join(res["lines"] + res["errors"])
    assert res["done"], "self-test didn't finish:\n" + report
    assert not res["failed"], report

"""Progress of long jobs (mosaic/progress.py): export, the figure report, Check and Refresh all
pictures say what they're on as they go, reach the end, and stop when asked, an export or
report removing the files it had written."""
import os

import pytest

from mosaic import model, report
from mosaic.app.api import Api
from mosaic.export.preflight import preflight
from mosaic.export.run import export_document
from mosaic.progress import Cancelled, Progress


class Watched(Progress):
    """A Progress that notes each step, and asks to stop at one."""
    def __init__(self, stop_at=None):
        super().__init__()
        self.steps, self.stop_at = [], stop_at

    def step(self, label):
        self.steps.append((label, self.state()["fraction"]))
        if label == self.stop_at:
            self.cancel()
        super().step(label)


def three_pages():
    doc = model.new_document("Fig")
    doc["pages"] += [model.new_page("Page 2"), model.new_page("Page 3")]
    for page in doc["pages"]:
        page["items"].append({"id": f"r{page['id']}", "type": "shape", "geom": "rect", "frame": [10, 10, 50, 30], "rot": 0,
                              "flip_h": False, "flip_v": False, "fill": {"color": "#56b4e9", "opacity": 1}, "stroke": None})
    return doc


def test_an_export_says_each_step_and_fills_up(tmp_path):
    p = Watched()
    res = export_document(three_pages(), str(tmp_path / "fig"), ["pdf", "svg", "png"], dpi=150, progress=p)
    labels = [s for s, _ in p.steps]
    assert len(res["files"]) == 7
    assert labels[:3] == ["Laying out page 1 of 3", "Laying out page 2 of 3", "Laying out page 3 of 3"]
    for want in ["Building the PDF, page 2 of 3", "Finishing the PDF (fonts)", "Writing the PDF", "Writing SVG, page 3 of 3",
                 "Drawing PNG at 150 dpi, page 1 of 3", "Writing PNG, page 3 of 3"]:
        assert want in labels
    fractions = [f for _, f in p.steps]
    assert fractions == sorted(fractions) and p.state()["fraction"] == pytest.approx(1.0)


def test_a_stopped_export_removes_what_it_wrote(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(Cancelled):
        export_document(three_pages(), str(out / "fig"), ["pdf", "svg", "png"], dpi=150,
                        progress=Watched(stop_at="Writing SVG, page 3 of 3"))
    assert os.listdir(out) == []   # (the PDF and two SVGs it had written: gone)


def test_a_stopped_report_removes_what_it_wrote(tmp_path):
    with pytest.raises(Cancelled):
        report.write(three_pages(), str(tmp_path / "rep"), ["html", "md", "csv"], progress=Watched(stop_at="Writing the CSV report"))
    assert os.listdir(tmp_path) == []


def test_check_goes_object_by_object():
    p = Watched()
    preflight(three_pages(), {"pages": [0, 1, 2]}, p)
    assert len(p.steps) == 3 and p.state()["fraction"] == pytest.approx(2 / 3)   # (the last one's done as it returns)


def test_the_editor_asks_how_far_a_job_has_got_and_can_stop_it(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    api, seen = Api(), []

    def job(p):
        p.plan(2)
        p.step("first")
        p.advance(1)
        seen.append(api.job_progress("j1"))
        api.cancel_job("j1")
        p.step("second")
        return {"finished": True}
    assert api._run_job("j1", job) == {"cancelled": True}
    assert seen == [{"fraction": 0.5, "label": "first", "cancelled": False}]
    assert api.job_progress("j1") is None and api.cancel_job("j1") is False   # (over)
    res = api.export(three_pages(), {"base": str(tmp_path / "fig"), "formats": ["svg"], "job": "j2"})
    assert len(res["files"]) == 3 and api.job_progress("j2") is None

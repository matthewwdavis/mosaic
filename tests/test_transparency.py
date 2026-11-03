"""A see-through line and its arrowheads fade as one (resolve.fade_together), so they don't double
up where the line runs into its head."""
import numpy as np
import pikepdf
from PIL import Image

from mosaic import connect, model
from mosaic.export.run import export_document
from mosaic.resolve import DrawGroup, Resolver


def arrow(opacity=0.5, head="triangle", **kw):
    return {"id": "a", "type": "line", "points": [[20, 30], [105, 30]], "arrow_start": None,
            "arrow_end": {"type": head, "w": "lg", "len": "lg"},
            "stroke": {"color": "#5aa9ff", "width": 5, "cap": "round", "opacity": opacity, **kw}}


def test_a_see_through_arrow_is_one_faded_group():
    for head in ("triangle", "stealth", "arrow"):
        (group,) = Resolver({"assets": {}}).resolve(arrow(head=head)).prims
        assert isinstance(group, DrawGroup) and group.opacity == 0.5, head
        assert all((p.stroke or p.fill).opacity == 1.0 for p in group.prims), head
    # Opaque: drawn as before, the line and its head side by side
    assert not any(isinstance(p, DrawGroup) for p in Resolver({"assets": {}}).resolve(arrow(opacity=1)).prims)
    # A dashed one keeps its dash points for connectors
    dashed = Resolver({"assets": {}}).resolve(arrow(dash="dash")).prims
    assert connect.line_sites(dashed)


def test_one_even_colour_where_the_line_runs_into_its_head(tmp_path):
    doc = model.new_document("arrow")
    page = doc["pages"][0]
    page["width"], page["height"], page["background"] = 130.0, 60.0, "#2b2b2b"
    page["items"] = [arrow(opacity=0.45)]
    export_document(doc, str(tmp_path / "a"), ["png", "pdf"], dpi=300, transparent=False)
    px = np.asarray(Image.open(tmp_path / "a.png").convert("RGB"), dtype=int)
    k = 300 / 72
    overlap, head, shaft = (px[int(y * k), int(x * k)] for x, y in ((84, 30), (84, 35), (40, 30)))
    assert np.abs(overlap - head).max() <= 1 and np.abs(overlap - shaft).max() <= 1
    # In the PDF: one transparency group, faded once
    pdf = pikepdf.open(tmp_path / "a.pdf")
    forms = [x for x in pdf.pages[0].Resources.XObject.values() if x.get("/Group") is not None]
    assert len(forms) == 1 and forms[0].Group.S == "/Transparency"
    pdf.close()

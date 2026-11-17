"""Add a Journal ▸ Start from a Journal's Reference Style… and Read Figure Sizes from the Author
Guidelines… (mosaic/app/api.py over _labapp's cslindex and guidelines): found by name or ISSN with
no connection, figure sizes read from a page (a local one here) or a saved file, and kept in the
journal's file with the sentence each came from."""
import http.server
import threading

import pytest

from mosaic import journals
from mosaic.app.api import Api

PAGE = """<html><body><nav class="site-nav">Journals</nav>
<h2>Preparing figures</h2>
<p>Figures are best prepared at a width of 84 mm (single column) and 174 mm (double column) with a maximum height of 234 mm.</p>
<p>The abstract should be no more than 250 words.</p></body></html>"""


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    yield Api()
    journals.load_user()


def test_a_journal_is_found_by_its_issn_or_name(api):
    got = api.csl_search("1614-2942")
    assert got[0] == {"style": "tree-genetics-and-genomes", "name": "Tree Genetics & Genomes", "issn": "1614-2942, 1614-2950",
                      "publisher": "Springer", "guidelines": got[0]["guidelines"]}
    assert api.csl_search("tree genetics")[0]["style"] == "tree-genetics-and-genomes"
    assert api.csl_search("") == []


def test_the_starter_and_the_guidelines_sizes_are_kept_in_the_journal_file(api, tmp_path):
    start = api.csl_starter("tree-genetics-and-genomes")
    assert start["name"] == "Tree Genetics & Genomes" and start["references"]["csl"] == "tree-genetics-and-genomes"
    saved = tmp_path / "guidelines.html"
    saved.write_text(PAGE, encoding="utf-8")
    read = api.guidelines_figures(str(saved))
    fields = {p["field"]: p for p in read["proposals"]}
    assert set(fields) == {"figures.types", "figures.depth_mm"}, "only the figure sizes"
    assert [t["width_mm"] for t in fields["figures.types"]["value"]] == [84.0, 174.0]
    assert fields["figures.depth_mm"]["value"] == 234.0 and "maximum height of 234 mm" in fields["figures.depth_mm"]["evidence"]
    j = api.guidelines_apply(start, read["proposals"], read["source"])
    entry = {"name": j["name"], "depth_mm": 234, "types": fields["figures.types"]["value"], "journal": j}
    mine = api.user_journals_save([entry])["mine"]
    kept = mine[0]["journal"]
    assert kept["issn"] == {"print": "1614-2942", "online": "1614-2950"} and kept["references"]["csl"] == "tree-genetics-and-genomes"
    assert kept["figures"]["depth_mm"] == 234.0 and "84 mm (single column)" in str(kept["figures"]["evidence"])
    assert journals.journal_size("Tree Genetics & Genomes", "Double column")


def test_a_page_is_read_only_from_the_address_given_and_a_refusal_says_what_to_do(api, tmp_path):
    (tmp_path / "authors.html").write_text(PAGE, encoding="utf-8")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(tmp_path), **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/blocked":
                self.send_error(403)
            else:
                super().do_GET()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        got = api.guidelines_figures(base + "/authors.html")
        assert got["source"].endswith("/authors.html") and len(got["proposals"]) == 2
        with pytest.raises(ValueError, match="save it"):
            api.guidelines_figures(base + "/blocked")
    finally:
        srv.shutdown()
    with pytest.raises(ValueError):
        api.guidelines_figures(str(tmp_path / "missing.pdf"))

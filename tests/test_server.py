"""The editor's own web server (mosaic/app/server.py) answers only on this computer, only with
its token, and only for mosaic's interface files and placed files named by their hash."""
import urllib.error
import urllib.request

import pytest

from mosaic.app.api import Api
from mosaic.app.server import start_server
from mosaic.assets import get_cache


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    s = start_server(Api(), 0)
    yield s
    s.shutdown()


def status(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status
    except urllib.error.HTTPError as err:
        return err.code


def test_it_serves_the_interface_and_nothing_beside_it(srv):
    assert status(srv.url + "ui/index.html") == 200
    assert status(srv.url + "ui/../app/server.py") == 404
    assert status(srv.url + "ui/..%2f..%2fpyproject.toml") == 404
    assert status(srv.url + "nothing") == 404


def test_without_the_token_nothing_is_served(srv):
    host = srv.url.split("/")[2]
    assert status(f"http://{host}/ui/index.html") in (403, 404)
    assert status(f"http://{host}/wrong-token/ui/index.html") in (403, 404)
    assert host.startswith("127.0.0.1:")


def test_placed_files_are_asked_for_by_hash_with_a_sound_page_and_scale(srv):
    sha, _ = get_cache().put_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "svg")
    assert status(srv.url + f"asset/{sha}.svg") == 200
    assert status(srv.url + "asset/../../secret.svg") == 400
    assert status(srv.url + f"asset/{'0' * 64}.svg") == 404
    pdf, _ = get_cache().put_bytes(b"%PDF-1.4", "pdf")
    assert status(srv.url + f"asset/{pdf}.pdf?page=abc") == 400
    assert status(srv.url + f"asset/{pdf}.pdf?page=-1") == 400
    assert status(srv.url + f"asset/{pdf}.pdf?scale=nan") == 400

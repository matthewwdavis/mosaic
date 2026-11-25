"""Where the editor's window may go (mosaic/app/macnav.py): its own address and frames inside it,
never a file or another site (a file is put on the page instead, a clicked web link opens in the
browser)."""
from mosaic.app.macnav import decide, file_path

HOME = "http://127.0.0.1:54967/3f9c2a/ui/index.html"


def test_the_editors_own_address_is_allowed():
    assert decide("http://127.0.0.1:54967/3f9c2a/ui/index.html?win=2&open=%2FUsers%2Fx.mff", HOME) == "allow"
    assert decide("http://127.0.0.1:54967/3f9c2a/ui/index.html#page", HOME) == "allow"
    assert decide("HTTP://127.0.0.1:54967/other", HOME) == "allow"
    assert decide("about:blank", HOME) == "allow"


def test_frames_inside_the_page_are_its_own_business():
    assert decide("file:///Users/x/plot.svg", HOME, main_frame=False) == "allow"
    assert decide("https://example.org/", HOME, main_frame=False) == "allow"


def test_a_file_is_put_on_the_page():
    # (what WebKit sends the window to for a file let go of before the page took the drag, 2026-11-24)
    url = "file:///Users/davismw/Projects/Pistachio/Bushy_Top/Figures/Chr02_Deletion/chr02_deletion_split_reads.svg"
    assert decide(url, HOME) == "place"
    assert decide(url, HOME, link=True) == "place"
    assert file_path("file:///Users/x/My%20plots/a%20b.svg") == "/Users/x/My plots/a b.svg"


def test_other_addresses_are_refused_and_clicked_web_links_open_in_the_browser():
    assert decide("https://example.org/paper", HOME) == "refuse"
    assert decide("https://example.org/paper", HOME, link=True) == "browser"
    assert decide("http://127.0.0.1:1234/ui/index.html", HOME) == "refuse"   # (another program's server)
    assert decide("http://localhost:54967/ui/index.html", HOME) == "refuse"
    assert decide("data:text/html,<p>hi</p>", HOME) == "refuse"
    assert decide("blob:http://127.0.0.1:54967/0b1c", HOME) == "refuse"
    assert decide("http://127.0.0.1:notaport/", HOME) == "refuse"

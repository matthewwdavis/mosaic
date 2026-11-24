"""A placed file's copy in the cache is named by the bytes it holds (AssetCache.put_file), and a linked
file that's still being written isn't taken half-way (make_variant). Found 2026-11-23: the editor's 2 s
look caught a 12 MB plot that R was still writing; put_file hashed the file and then copied it, two
reads, so the finished plot was kept under the half-written file's hash. The document then embedded
the new picture under the old name, and a fresh cache (another computer, a restored backup) dropped
it on the next save."""
import hashlib
import os
import shutil

from mosaic import assets
from mosaic.assets import make_variant, refresh_asset


def svg(w: float, label: str) -> str:
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}pt' height='50pt' viewBox='0 0 {w} 50'>"
            f"<rect x='5' y='5' width='{w - 10}' height='30' fill='#336699'/><text x='5' y='46'>{label}</text></svg>")


def sha_of(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def moved_on(path: str, before_ns: int) -> None:
    """Make sure a re-saved file's time stamp moved on (some file systems keep coarse times)."""
    if os.stat(path).st_mtime_ns <= before_ns:
        os.utime(path, ns=(before_ns + 10_000_000, before_ns + 10_000_000))


def test_a_copy_is_named_by_its_own_bytes_when_the_file_changes_after_it_is_first_read(tmp_path, cache, monkeypatch):
    """R finishes writing the plot just after mosaic's first read of it, whichever read that is (the
    hash before the copy, as it was, or the copy itself): the copy kept must still match its name."""
    path = str(tmp_path / "plot.svg")
    with open(path, "w") as fh:
        fh.write(svg(100, "half-written"))
    real_copy, real_sha = shutil.copyfile, assets.sha256_file
    rewritten = []

    def finish_writing():
        if not rewritten:
            rewritten.append(1)
            before = os.stat(path).st_mtime_ns
            with open(path, "w") as fh:
                fh.write(svg(140, "finished"))
            moved_on(path, before)

    def copy(src, dst, *a, **k):
        out = real_copy(src, dst, *a, **k)
        if os.path.abspath(src) == path:
            finish_writing()
        return out

    def sha(p):
        out = real_sha(p)
        if os.path.abspath(p) == path:
            finish_writing()
        return out

    monkeypatch.setattr(assets.shutil, "copyfile", copy)
    monkeypatch.setattr(assets, "sha256_file", sha)
    got, stored = cache.put_file(path, "svg")
    assert rewritten
    assert sha_of(stored) == got
    assert os.path.basename(stored) == f"{got}.svg"


def test_a_file_still_being_written_is_copied_again_once_it_holds_still(tmp_path, cache, monkeypatch):
    path = tmp_path / "plot.svg"
    path.write_text(svg(100, "half"))
    final = svg(140, "finished plot")
    real_copy = shutil.copyfile
    calls = []

    def copy_while_writing(src, dst, *a, **k):
        out = real_copy(src, dst, *a, **k)
        calls.append(1)
        if len(calls) == 1:   # the first copy is taken while R is still writing
            before = os.stat(src).st_mtime_ns
            with open(src, "w") as fh:
                fh.write(final)
            moved_on(str(src), before)
        return out

    monkeypatch.setattr(assets.shutil, "copyfile", copy_while_writing)
    monkeypatch.setattr(assets, "STABLE_WAIT", 0)
    var = make_variant(str(path), cache)
    assert len(calls) == 2
    assert var["sha256"] == hashlib.sha256(final.encode()).hexdigest()
    assert var["size_pt"] == [140.0, 50.0]          # read from the copy kept: the finished plot
    assert var["bytes"] == len(final.encode())
    assert var["mtime"] == os.stat(path).st_mtime   # it held still: nothing for the next look to do


def test_a_file_that_never_holds_still_is_read_again_at_the_next_look(tmp_path, cache, monkeypatch):
    path = tmp_path / "plot.svg"
    path.write_text(svg(100, "v0"))
    real_copy = shutil.copyfile
    n = [0]

    def copy_while_always_writing(src, dst, *a, **k):
        out = real_copy(src, dst, *a, **k)
        n[0] += 1
        before = os.stat(src).st_mtime_ns
        with open(src, "w") as fh:
            fh.write(svg(100 + n[0], f"v{n[0]}"))
        moved_on(str(src), before)
        return out

    monkeypatch.setattr(assets.shutil, "copyfile", copy_while_always_writing)
    monkeypatch.setattr(assets, "STABLE_WAIT", 0)
    var = make_variant(str(path), cache)
    assert n[0] == assets.STABLE_TRIES
    assert sha_of(cache.path(var["sha256"], "svg")) == var["sha256"]
    # The time kept is from before the last copy, so the next look sees the file changed and takes it
    monkeypatch.setattr(assets.shutil, "copyfile", real_copy)
    asset = {"name": "plot.svg", "primary": "svg", "size_pt": var["size_pt"], "variants": {"svg": var}, "auto_update": True}
    assert refresh_asset(asset, cache) == ["svg"]
    assert asset["variants"]["svg"]["sha256"] == sha_of(str(path))

"""Updates (mosaic/updates.py), against a stand-in for GitHub (tools/fake_github.py): finding
a release on the right channel, downloading it with or without a sign-in (and never sending the
sign-in on to the host files are redirected to), refusing anything not signed with a trusted key
or not matching its signature, signing in with a code and refreshing the sign-in, Ask me first,
skipping a version and going back to the one before, when an update installs as mosaic
quits, how the last install went, and documents saved by a newer mosaic. The installers
themselves are tried for real on Mac and Windows in CI (tools/update_e2e.py)."""
import base64
import json
import os
import sys
import time
import zipfile

import pytest

from mosaic import docfile, model, updates
from mosaic.app.api import Api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fake_github  # noqa: E402
import release  # noqa: E402

NOTES = "What's new:\n\n- Exports twice as fast"


def keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    return key.private_bytes_raw(), base64.b64encode(key.public_key().public_bytes_raw()).decode()


@pytest.fixture
def key(monkeypatch):
    private, public = keypair()
    monkeypatch.setenv("MOSAIC_UPDATE_TEST_KEY", public)
    return private


@pytest.fixture
def source(tmp_path):
    """A small stand-in for mosaic's folder: the installers, environment.yml and the package."""
    src = tmp_path / "src"
    (src / "mosaic").mkdir(parents=True)
    (src / "mosaic" / "__init__.py").write_text('__version__ = "0.0.0"\n')
    (src / "environment.yml").write_text("name: mosaic\ndependencies:\n  - python=3.12\n")
    (src / "install-mac.command").write_text("#!/bin/bash\necho installing\n")
    (src / "install-windows.bat").write_bytes(b"@echo off\r\necho installing\r\n")
    return src


def publish(folder, source, version, private_key, prerelease=False, zip_name=None, tamper=None):
    """A signed release, as tools/release.py makes one, into the fake GitHub's folder."""
    work = folder.parent / f"build-{version}"
    work.mkdir(exist_ok=True)
    zpath = work / (zip_name or f"mosaic-{version}.zip")
    release.zip_tree(str(source), version, str(zpath))
    manifest = release.manifest_for(str(zpath), version, (source / "environment.yml").read_bytes(), NOTES)
    if tamper:
        tamper(manifest, zpath)
    signed = updates.sign_manifest(manifest, private_key)
    mpath = work / updates.MANIFEST
    mpath.write_text(json.dumps(signed))
    fake_github.add_release(str(folder), f"v{version}", [str(zpath), str(mpath)], prerelease=prerelease, body=NOTES)


@pytest.fixture
def github(tmp_path, monkeypatch):
    """The fake GitHub, with mosaic pointed at it, installed (so it may update) and with a
    GitHub app to sign in with."""
    folder = tmp_path / "releases"
    folder.mkdir()
    gh = fake_github.FakeGitHub(str(folder), private=True).start()
    monkeypatch.setenv("MOSAIC_UPDATE_API", gh.api)
    monkeypatch.setenv("MOSAIC_UPDATE_WEB", gh.web)
    monkeypatch.setenv("MOSAIC_UPDATE_KIND", "installed")
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(updates, "INSTALLER", "install-mac.command")   # (Linux has no installer of its own)
    info = {**updates.settings(), "github_app_client_id": "Iv1.test"}
    monkeypatch.setattr(updates, "settings", lambda: info)
    gh.folder_path = folder
    yield gh
    gh.stop()


def make(prefs=None, version="0.1.0"):
    p = {"updates": "auto", "update_channel": "stable", **(prefs or {})}
    return updates.Updater(lambda: p, version=version)


def sign_in(gh, up):
    """Signed in already: a token the fake GitHub accepts, kept as mosaic keeps it."""
    gh.tokens.add("ghu_kept")
    up.keystore.set(json.dumps({"access_token": "ghu_kept", "login": "early-adopter"}))
    up._creds = ...


def test_versions_compare_as_numbers():
    v = updates.parse_version
    assert v("v0.2.10") > v("0.2.9") > v("0.2") and v("0.2") == v("0.2.0") and v("1") > v("0.99.99")
    assert v("") == () and v(None) == () and v("abc") == ()


def test_only_a_trusted_key_and_unchanged_bytes_pass(key):
    signed = updates.sign_manifest({"app": "mosaic", "version": "0.2.0"}, key)
    assert updates.verify_manifest(signed)["version"] == "0.2.0"
    changed = dict(signed, payload=base64.b64encode(base64.b64decode(signed["payload"]).replace(b"0.2.0", b"9.2.0")).decode())
    other, _ = keypair()
    with pytest.raises(updates.UpdateError, match="signature doesn't match"):
        updates.verify_manifest(changed)
    with pytest.raises(updates.UpdateError, match="isn't signed with a key this mosaic trusts"):
        updates.verify_manifest(updates.sign_manifest({"app": "mosaic", "version": "0.2.0"}, other))
    with pytest.raises(updates.UpdateError, match="isn't for mosaic"):
        updates.verify_manifest(updates.sign_manifest({"app": "Something else", "version": "0.2.0"}, key))
    with pytest.raises(updates.UpdateError):
        updates.verify_manifest({"format": 2})


def test_the_right_release_for_the_channel_skip_and_going_back():
    rel = lambda v, pre=False: {"version": v, "prerelease": pre}   # noqa: E731
    releases = [rel("0.3.0", True), rel("0.2.1"), rel("0.2.0"), rel("0.1.9")]
    newest, update, previous = updates.pick(releases, "stable", "0.2.0")
    assert (newest["version"], update["version"], previous["version"]) == ("0.2.1", "0.2.1", "0.1.9")
    assert updates.pick(releases, "test", "0.2.0")[1]["version"] == "0.3.0"   # test versions too
    assert updates.pick(releases, "stable", "0.2.0", skip="0.2.1")[1] is None   # skipped
    assert updates.pick(releases, "test", "0.2.0", skip="0.2.1")[1]["version"] == "0.3.0"   # a newer one isn't
    assert updates.pick(releases, "stable", "0.2.1")[1] is None and updates.pick([], "stable", "0.2.1") == (None, None, None)


def test_a_private_repository_needs_a_sign_in_and_the_files_come_without_it(github, source, key):
    publish(github.folder_path, source, "0.2.0", key)
    up = make()
    st = up.check()
    assert st["access"] == "sign_in" and st["update"] is None and st["error"] is None and st["staged"] is None
    sign_in(github, up)
    github.seen.clear()
    st = up.check()
    assert st["access"] == "signed_in" and st["update"]["version"] == "0.2.0" and st["signed_in"] == "early-adopter"
    staged = up.state["staged"]
    assert staged["version"] == "0.2.0" and staged["notes"] == NOTES and staged["env_changed"] is True
    assert os.path.isfile(os.path.join(staged["dir"], "install-mac.command"))
    assert "0.2.0" in open(os.path.join(staged["dir"], "mosaic", "__init__.py")).read()
    files = [s for s in github.seen if s[0] == "objects"]
    assert files and all(auth is None for _, _, auth in files)   # the sign-in stayed with GitHub's API
    assert all(tok == "ghu_kept" for host, path, tok in github.seen if host == "api" and "/releases" in path)


def test_a_public_repository_needs_no_sign_in(github, source, key):
    github.private = False
    publish(github.folder_path, source, "0.2.0", key)
    st = make().check()
    assert st["access"] == "public" and st["staged"]["version"] == "0.2.0" and st["signed_in"] is None
    assert any(host == "objects" for host, *_ in github.seen)


def test_anything_not_matching_its_signature_is_refused(github, source, key):
    github.private = False

    def bigger(manifest, zpath):   # the ZIP swapped after signing
        with zipfile.ZipFile(zpath, "a") as z:
            z.writestr("mosaic-0.2.0/extra.py", "print('not in the signed release')")
    publish(github.folder_path, source, "0.2.0", key, tamper=bigger)
    st = make().check()
    assert st["staged"] is None and ("doesn't match the signed release" in st["error"] or "bigger than the release says" in st["error"])
    # Signed with a key mosaic doesn't trust
    other, _ = keypair()
    publish(github.folder_path, source, "0.2.1", other)
    st = make().check()
    assert st["staged"] is None and "trusts" in st["error"]


def test_signing_in_with_a_code_and_refreshing_the_sign_in(github, source, key):
    publish(github.folder_path, source, "0.2.0", key)
    up = make()
    started = up.signin_start()
    assert started["user_code"] == "WDJB-MJHT" and "device_code" not in started
    for _ in range(100):
        if up.status()["signin"]["state"] != "waiting":
            break
        time.sleep(0.05)
    s = up.status()
    assert s["signin"]["state"] == "done" and s["signin"]["login"] == "early-adopter" and s["signed_in"] == "early-adopter"
    for _ in range(100):   # it looks for an update straight after
        if up.status()["staged"]:
            break
        time.sleep(0.05)
    assert up.status()["staged"]["version"] == "0.2.0"
    # Eight hours on, the token has run out: the refresh token gets a new one (used once)
    kept = json.loads(up.keystore.get())
    kept["expires_at"] = time.time() - 1
    up.keystore.set(json.dumps(kept))
    up._creds = ...
    token = up._token()
    assert token and token != kept["access_token"] and json.loads(up.keystore.get())["login"] == "early-adopter"
    assert kept["refresh_token"] not in github.refresh_tokens
    # Withdrawn on GitHub: mosaic forgets it and asks to sign in again
    github.tokens.clear()
    github.refresh_tokens.clear()
    st = up.check(manual=True)
    assert st["signed_in"] is None and st["access"] == "sign_in"
    # Cancelled on GitHub
    github.deny = True
    up.signin_start()
    for _ in range(100):
        if up.status()["signin"]["state"] != "waiting":
            break
        time.sleep(0.05)
    assert up.status()["signin"]["state"] == "denied"


def test_ask_first_skip_and_go_back(github, source, key):
    github.private = False
    for v in ("0.1.9", "0.2.0", "0.2.1"):
        publish(github.folder_path, source, v, key)
    up = make({"updates": "ask"}, version="0.2.0")
    st = up.check()
    assert st["update"]["version"] == "0.2.1" and st["staged"] is None and st["previous"]["version"] == "0.1.9"
    staged = up.get("update")   # Update now
    assert staged["version"] == "0.2.1" and staged["approved"]
    up.skip("0.2.1")   # Skip this version: not installed, and not offered until a newer one
    assert up.state["staged"] is None and up.check()["update"] is None
    up.skip(None)
    # Go back: the version before, skipping this one afterwards
    staged = up.get("previous")
    assert staged["version"] == "0.1.9" and staged["go_back"] and up.state["skip"] == "0.2.0"


def test_when_an_update_installs_as_mosaic_quits(github, source, key, monkeypatch):
    github.private = False
    publish(github.folder_path, source, "0.2.0", key)
    launched = []
    monkeypatch.setattr(updates.Updater, "launch", lambda self, staged, reopen=False: launched.append((staged["version"], reopen)) or True)
    up = make()
    up.check()
    up.register()
    assert up.on_quit() and launched == [("0.2.0", False)]   # automatic: by itself, without opening again
    tired = make()
    tired.state["tries"] = {"0.2.0": updates.MAX_TRIES}
    assert not tired.on_quit() and len(launched) == 1   # failed twice: it waits for a click
    # Another mosaic still open: the last one to close installs it
    other = os.path.join(updates.updates_dir(), "running", str(os.getppid()))
    open(other, "w").close()
    assert not make().on_quit() and len(launched) == 1
    os.remove(other)
    ask = make({"updates": "ask"})
    assert not ask.on_quit() and len(launched) == 1   # Ask me first: not without a click
    assert ask.restart_now() and ask.on_quit() and launched[-1] == ("0.2.0", True)   # Restart now: opened again


def test_how_the_last_install_went(github, monkeypatch):
    folder = updates.updates_dir()
    up = make(version="0.1.0")
    with open(os.path.join(folder, "state.json"), "w") as fh:
        json.dump({"installing": {"version": "0.2.0", "from": "0.1.0", "notes": NOTES, "go_back": False},
                   "staged": {"version": "0.2.0", "dir": "x", "go_back": False}}, fh)
    open(os.path.join(folder, updates.RESULT), "w").write("failed: conda wasn't found\n")
    st = make(version="0.1.0").status()
    assert st["failed"] == {**st["failed"], "version": "0.2.0", "error": "conda wasn't found"} and st["tries"] == 1
    assert not os.path.exists(os.path.join(folder, updates.RESULT))
    # And the next one went in: What's new, once
    up.state = {"installing": {"version": "0.2.0", "from": "0.1.0", "notes": NOTES, "go_back": False}}
    up._save()
    open(os.path.join(folder, updates.RESULT), "w").write("ok\n")
    st = make(version="0.2.0").status()
    assert st["updated"]["version"] == "0.2.0" and st["updated"]["notes"] == NOTES and st["failed"] is None
    assert make(version="0.2.0").seen()["updated"] is None


@pytest.mark.skipif(sys.platform not in ("darwin", "win32"), reason="the installers are a Mac's and Windows'")
def test_the_installer_starts_with_what_it_needs(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MOSAIC_UPDATE_KIND", "installed")
    top = tmp_path / "mosaic-0.2.0"
    top.mkdir()
    out = tmp_path / "seen.txt"
    if sys.platform == "darwin":
        (top / updates.INSTALLER).write_text(
            f'#!/bin/bash\nprintf "%s|%s|%s\\n" "$MOSAIC_PREFIX" "$MOSAIC_NO_OPEN" "$MOSAIC_WAIT_PID" > "{out}"\n'
            'echo ok > "$MOSAIC_RESULT"\nrm -f "$MOSAIC_LOCK"\n')
    else:   # (bytes: written as text, Windows would double the line ends' CR)
        (top / updates.INSTALLER).write_bytes(
            f'@echo off\r\n(echo %MOSAIC_PREFIX%^|%MOSAIC_NO_OPEN%^|%MOSAIC_WAIT_PID%)>"{out}"\r\n'
            '(echo ok)>"%MOSAIC_RESULT%"\r\ndel "%MOSAIC_LOCK%"\r\n'.encode())
    up = make()
    assert up.launch({"version": "0.2.0", "dir": str(top), "notes": NOTES})
    assert up.state["installing"]["version"] == "0.2.0"
    for _ in range(100):
        if out.exists() and out.read_text().strip() and os.path.exists(os.path.join(updates.updates_dir(), updates.RESULT)):
            break
        time.sleep(0.1)
    prefix, no_open, pid = out.read_text().strip().split("|")
    assert os.path.normcase(prefix) == os.path.normcase(sys.prefix) and no_open == "1" and pid == str(os.getpid())
    assert open(os.path.join(updates.updates_dir(), updates.RESULT)).read().strip() == "ok"


def test_the_sign_in_is_kept_for_this_user(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path))
    store = updates.Keystore("mosaic test")
    assert store.backend == "file" and store.get() is None
    store.set('{"access_token": "x"}')
    assert store.get() == '{"access_token": "x"}'
    if os.name != "nt":
        assert oct(os.stat(next(tmp_path.glob("*.secret"))).st_mode & 0o777) == "0o600"   # only the user can read it
    store.delete()
    assert store.get() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' Credential Manager")
def test_windows_keeps_the_sign_in_in_its_credential_manager(monkeypatch):
    monkeypatch.setenv("MOSAIC_KEYSTORE", "windows")
    store = updates.Keystore("mosaic test entry")
    store.set('{"access_token": "ghu_test"}')
    try:
        assert store.get() == '{"access_token": "ghu_test"}'
        store.set('{"access_token": "ghu_again"}')
        assert store.get() == '{"access_token": "ghu_again"}'
    finally:
        store.delete()
    assert store.get() is None


def test_a_release_zip_unpacks_only_inside_its_folder(tmp_path, monkeypatch, source):
    monkeypatch.setattr(updates, "INSTALLER", "install-mac.command")
    good = tmp_path / "good.zip"
    release.zip_tree(str(source), "0.2.0", str(good))
    top = updates.extract(str(good), str(tmp_path / "out"))
    assert os.path.basename(top) == "mosaic-0.2.0" and os.path.isfile(os.path.join(top, "install-mac.command"))
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("mosaic/install-mac.command", "")
        z.writestr("../../escaped.txt", "outside")
    with pytest.raises(updates.UpdateError, match="outside its folder"):
        updates.extract(str(bad), str(tmp_path / "out2"))


def test_a_checkout_doesnt_update_itself(monkeypatch):
    monkeypatch.delenv("MOSAIC_UPDATE_KIND", raising=False)
    assert updates.install_kind() == "source"   # (these tests run from the repository)
    assert make().check()["staged"] is None


def test_documents_say_which_version_saved_them(tmp_path):
    path = str(tmp_path / "figure.mosaic")
    docfile.save(model.new_document(), path)
    doc = docfile.load(path)
    assert doc["meta"]["saved_by"] == updates.__version__
    assert Api().open_document(path)["newer"] is None
    # Saved by a newer mosaic: opened, with a warning
    doc["meta"]["saved_by"] = "99.0.0"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(docfile.DOC_NAME, json.dumps(doc))
    assert Api().open_document(path)["newer"] == "99.0.0"
    # In a form this version can't read: it says to update
    doc["mosaic"] = model.FORMAT_VERSION + 1
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(docfile.DOC_NAME, json.dumps(doc))
    with pytest.raises(ValueError, match=r"saved by a newer mosaic \(99\.0\.0\).*Update mosaic"):
        docfile.load(path)


def test_the_release_keys_backup_catches_a_typo():
    private, _ = keypair()
    text = release.backup_text(private)
    assert release.from_backup(text) == private and release.from_backup(f"  {text}\n") == private
    head, middle, check = text.split(":")
    typo = middle[:10] + ("A" if middle[10] != "A" else "B") + middle[11:]
    for bad in (f"{head}:{typo}:{check}", f"{head}:{middle[:-8]}:{check}", middle, f"{head}:{middle}"):
        with pytest.raises(ValueError):
            release.from_backup(bad)
    assert release.next_version("0.1.0", []) == "0.1.1" and release.next_version("0.1.0", ["v0.2.3", "v0.2.10"]) == "0.2.11"


def test_opened_again_while_an_update_installs_it_waits(tmp_path, monkeypatch):
    import subprocess
    import threading
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path))
    closed = []
    monkeypatch.setattr(updates, "_waiting_notice", lambda version: (lambda: closed.append(version)))
    installer = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
    threading.Thread(target=installer.wait, daemon=True).start()   # (as the system does once mosaic has gone)
    with open(os.path.join(updates.updates_dir(), updates.LOCK), "w") as fh:
        json.dump({"pid": installer.pid, "version": "0.2.0", "started": time.time()}, fh)
    t0 = time.time()
    updates.wait_for_install(timeout=30)
    assert 1.0 < time.time() - t0 < 10 and closed == ["0.2.0"]   # waited, saying so, and closed the notice
    t0 = time.time()
    updates.wait_for_install()   # nothing installing: straight on
    assert time.time() - t0 < 0.5 and closed == ["0.2.0"]


def test_a_redirect_to_anything_but_a_secure_address_is_refused():
    """GitHub sends downloads on to another host; mosaic follows only to https (or this computer, for the tests)."""
    import http.server
    import threading

    class Away(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "file:///etc/passwd" if "file" in self.path else "http://example.invalid/x")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Away)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for path in ("/file", "/plain"):
            with pytest.raises(updates.UpdateError, match="secure"):
                updates.http(f"http://127.0.0.1:{srv.server_port}{path}")
    finally:
        srv.shutdown()

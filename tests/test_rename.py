"""What mosaic keeps from when it was called FigAssemble: its settings folder (copied once, and
left as it was), its .figasm documents (they open, and save as themselves) and its GitHub
sign-in (read once from FigAssemble's entry)."""
import json
import os
import zipfile

from mosaic import docfile, fonts, model, updates


def tree(folder):
    """Every file under a folder, with its size and time: to see that nothing changed."""
    out = {}
    for d, _, names in os.walk(folder):
        for n in names:
            p = os.path.join(d, n)
            out[os.path.relpath(p, folder).replace(os.sep, "/")] = (os.path.getsize(p), os.path.getmtime(p))
    return out


def test_the_settings_folder_is_copied_once_and_the_old_one_left_as_it_was(tmp_path, monkeypatch):
    old = tmp_path / ".figassemble"
    (old / "autosave").mkdir(parents=True)
    (old / "math-fonts").mkdir()
    (old / "cache").mkdir()
    (old / "prefs.json").write_text(json.dumps({"units": "mm"}))
    (old / "autosave" / "doc-abc123.figasm").write_bytes(b"recovery copy")
    (old / "autosave" / "doc-abc123.lock").write_text("")
    (old / "math-fonts" / "STIXTwoMath.otf").write_bytes(b"font")
    (old / "cache" / "page.png").write_bytes(b"cached")
    (old / "font-index.json").write_text("{}")
    before = tree(old)
    monkeypatch.delenv("MOSAIC_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    new = fonts.config_dir()
    assert new == str(tmp_path / ".mosaic")
    # Settings, recovery copies (as .mosaic documents) and math fonts; not locks or caches
    assert sorted(tree(new)) == ["autosave/doc-abc123.mosaic", "math-fonts/STIXTwoMath.otf", "prefs.json"]
    assert json.loads((tmp_path / ".mosaic" / "prefs.json").read_text()) == {"units": "mm"}
    assert (tmp_path / ".mosaic" / "autosave" / "doc-abc123.mosaic").read_bytes() == b"recovery copy"
    assert tree(old) == before   # nothing in the old folder moved, changed or went
    # Once: settings changed in mosaic aren't copied over again
    (tmp_path / ".mosaic" / "prefs.json").write_text(json.dumps({"units": "cm"}))
    fonts.config_dir()
    assert json.loads((tmp_path / ".mosaic" / "prefs.json").read_text()) == {"units": "cm"}
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]


def test_a_new_settings_folder_without_figassemble_s(tmp_path, monkeypatch):
    monkeypatch.delenv("MOSAIC_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert fonts.config_dir() == str(tmp_path / ".mosaic") and os.listdir(tmp_path / ".mosaic") == []


def test_figassemble_documents_open_and_save_as_themselves(tmp_path, monkeypatch):
    from mosaic.app.api import Api
    monkeypatch.setenv("MOSAIC_HOME", str(tmp_path / "home"))
    doc = model.new_document("Figure 2")
    doc["pages"][0]["items"].append(model.text_item("a", 2, 2))
    saved = tmp_path / "saved.mosaic"
    docfile.save(doc, str(saved))
    # As FigAssemble wrote it: a .figasm whose format is under "figassemble"
    old = tmp_path / "Figure 2.figasm"
    with zipfile.ZipFile(saved) as zin, zipfile.ZipFile(old, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename == docfile.DOC_NAME:
                d = json.loads(data)
                d["figassemble"] = d.pop("mosaic")
                data = json.dumps(d).encode("utf-8")
            zout.writestr(info, data)
    opened = docfile.load(str(old))
    assert opened["mosaic"] == model.FORMAT_VERSION and "figassemble" not in opened
    assert opened["pages"][0]["items"][0]["text"] == doc["pages"][0]["items"][0]["text"]
    # Saving it keeps its name; a name with no extension gets .mosaic
    assert Api().save_document(opened, str(old))["path"] == str(old)
    assert docfile.load(str(old))["mosaic"] == model.FORMAT_VERSION
    assert Api().save_document(opened, str(tmp_path / "copy"))["path"] == str(tmp_path / "copy.mosaic")


def test_the_github_sign_in_is_read_from_figassemble_s_entry():
    signed_in = json.dumps({"access_token": "ghu_old", "login": "matthewwdavis"})
    updates.Keystore(*updates.OLD_SIGNIN).set(signed_in)
    try:
        up = updates.Updater(lambda: {"updates": "off"})
        assert up._load_creds()["access_token"] == "ghu_old"
        assert updates.Keystore(updates.SIGNIN_SERVICE).get() == signed_in   # kept under mosaic's name too
        assert updates.Keystore(*updates.OLD_SIGNIN).get() == signed_in      # and FigAssemble's left
        up.signout()   # forgets both, so it isn't read back
        assert updates.Keystore(updates.SIGNIN_SERVICE).get() is None and updates.Keystore(*updates.OLD_SIGNIN).get() is None
        assert updates.Updater(lambda: {"updates": "off"})._load_creds() is None
    finally:
        for store in (updates.Keystore(updates.SIGNIN_SERVICE), updates.Keystore(*updates.OLD_SIGNIN)):
            store.delete()

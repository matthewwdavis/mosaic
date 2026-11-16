"""mosaic's documents open in it when double-clicked: the Mac app declares the .mff type (new
documents'), and the older .mosaic and .figasm (from when it was called FigAssemble), as its own and decks as an alternative (packaging/macos/make_app.py), and on Windows the installer
registers them for the account (packaging/windows/make_shortcuts.py)."""
import os
import plistlib
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packaging", "macos"))
sys.path.insert(0, os.path.join(ROOT, "packaging", "windows"))


def test_the_mac_app_owns_mosaic_documents_and_opens_decks_as_an_alternative():
    import make_app
    types = make_app.document_types()
    own, decks = types["CFBundleDocumentTypes"]
    assert own["LSItemContentTypes"] == ["io.github.matthewwdavis.mosaic.mff", "io.github.matthewwdavis.mosaic.document",
                                         "org.figassemble.figasm"]
    assert own["LSHandlerRank"] == "Owner" and own["CFBundleTypeRole"] == "Editor"
    assert own["CFBundleTypeIconSystemGenerated"] is True   # (one document icon for every extension)
    assert decks["LSHandlerRank"] == "Alternate" and "org.openxmlformats.presentationml.presentation" in decks["LSItemContentTypes"]
    new, older, oldest = types["UTExportedTypeDeclarations"]
    assert new["UTTypeIdentifier"] == "io.github.matthewwdavis.mosaic.mff"   # new documents'
    assert new["UTTypeTagSpecification"]["public.filename-extension"] == ["mff"]
    assert older["UTTypeIdentifier"] == "io.github.matthewwdavis.mosaic.document"   # .mosaic, until November 2026
    assert older["UTTypeTagSpecification"]["public.filename-extension"] == ["mosaic"]
    assert oldest["UTTypeIdentifier"] == "org.figassemble.figasm"   # FigAssemble's documents
    assert oldest["UTTypeTagSpecification"]["public.filename-extension"] == ["figasm"]
    assert all("public.data" in t["UTTypeConformsTo"] and t["UTTypeDescription"] == "mosaic figure" for t in (new, older, oldest))


def test_every_document_extension_has_its_mac_type():
    import make_app

    from mosaic import docfile
    assert [ext for _, ext in make_app.SPEC.doc_types] == [e.lstrip(".") for e in docfile.EXTENSIONS]
    assert make_app.SPEC.extension == docfile.EXTENSION == ".mff"


@pytest.mark.skipif(sys.platform != "darwin", reason="a Mac's")
def test_the_built_app_declares_them(tmp_path):
    subprocess.run([sys.executable, os.path.join(ROOT, "packaging", "macos", "make_app.py"), "--dest", str(tmp_path), "--no-register"],
                   check=True, capture_output=True)
    with open(tmp_path / "mosaic.app" / "Contents" / "Info.plist", "rb") as fh:
        info = plistlib.load(fh)
    import make_app
    assert {k: info[k] for k in ("CFBundleDocumentTypes", "UTExportedTypeDeclarations")} == make_app.document_types()
    assert [t["UTTypeTagSpecification"]["public.filename-extension"] for t in info["UTExportedTypeDeclarations"]] == \
        [["mff"], ["mosaic"], ["figasm"]]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows'")
def test_windows_registers_them_for_the_account(tmp_path):
    import winreg

    import make_shortcuts
    root = r"Software\mosaicTest\Classes"
    pythonw, icon = r"C:\Users\Some One\miniforge3\envs\mosaic\pythonw.exe", str(tmp_path / "mosaic.ico")
    make_shortcuts.register_file_types(pythonw, icon, root=root)

    def read(path, name=""):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{root}\\{path}") as key:
            return winreg.QueryValueEx(key, name)[0]
    try:
        assert read(".mff") == "mosaic.Document"
        assert read(r".mff\OpenWithProgids", "mosaic.Document") == ""
        assert read(".mosaic") == "mosaic.Document"   # documents from before .mff
        assert read(r"mosaic.Document\shell\open\command") == f'"{pythonw}" -P -m mosaic "%1"'
        assert read(r"mosaic.Document\DefaultIcon") == f'"{icon}",0'
        assert read(r"mosaic.Document\shell\open", "FriendlyAppName") == "mosaic"
        assert read(r".mosaic\OpenWithProgids", "mosaic.Document") == ""
        assert read(".figasm") == "mosaic.Document"   # FigAssemble's documents
        assert read(r".figasm\OpenWithProgids", "mosaic.Document") == ""
        for ext in (".pptx", ".pptm", ".potx"):
            assert read(f"{ext}\\OpenWithProgids", "mosaic.Deck") == ""   # Open with only: the deck's own app stays
            with pytest.raises(OSError):
                read(ext)
    finally:
        def remove(path):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        sub = winreg.EnumKey(key, 0)
                    except OSError:
                        break
                    remove(f"{path}\\{sub}")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        remove(r"Software\mosaicTest")

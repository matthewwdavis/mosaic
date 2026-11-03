"""FigAssemble's documents open in it when double-clicked: the Mac app declares the .figasm type as
its own and decks as an alternative (packaging/macos/make_app.py), and on Windows the installer
registers them for the account (packaging/windows/make_shortcuts.py)."""
import os
import plistlib
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packaging", "macos"))
sys.path.insert(0, os.path.join(ROOT, "packaging", "windows"))


def test_the_mac_app_owns_figasm_documents_and_opens_decks_as_an_alternative():
    import make_app
    types = make_app.document_types()
    own, decks = types["CFBundleDocumentTypes"]
    assert own["LSItemContentTypes"] == ["org.figassemble.figasm"] and own["LSHandlerRank"] == "Owner" and own["CFBundleTypeRole"] == "Editor"
    assert decks["LSHandlerRank"] == "Alternate" and "org.openxmlformats.presentationml.presentation" in decks["LSItemContentTypes"]
    (declared,) = types["UTExportedTypeDeclarations"]
    assert declared["UTTypeIdentifier"] == "org.figassemble.figasm"
    assert declared["UTTypeTagSpecification"]["public.filename-extension"] == ["figasm"]
    assert "public.data" in declared["UTTypeConformsTo"]


@pytest.mark.skipif(sys.platform != "darwin", reason="a Mac's")
def test_the_built_app_declares_them(tmp_path):
    subprocess.run([sys.executable, os.path.join(ROOT, "packaging", "macos", "make_app.py"), "--dest", str(tmp_path), "--no-register"],
                   check=True, capture_output=True)
    with open(tmp_path / "FigAssemble.app" / "Contents" / "Info.plist", "rb") as fh:
        info = plistlib.load(fh)
    import make_app
    assert {k: info[k] for k in ("CFBundleDocumentTypes", "UTExportedTypeDeclarations")} == make_app.document_types()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows'")
def test_windows_registers_them_for_the_account(tmp_path):
    import winreg

    import make_shortcuts
    root = r"Software\FigAssembleTest\Classes"
    pythonw, icon = r"C:\Users\Some One\miniforge3\envs\figassemble\pythonw.exe", str(tmp_path / "FigAssemble.ico")
    make_shortcuts.register_file_types(pythonw, icon, root=root)

    def read(path, name=""):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{root}\\{path}") as key:
            return winreg.QueryValueEx(key, name)[0]
    try:
        assert read(".figasm") == "FigAssemble.Document"
        assert read(r"FigAssemble.Document\shell\open\command") == f'"{pythonw}" -P -m figassemble "%1"'
        assert read(r"FigAssemble.Document\DefaultIcon") == f'"{icon}",0'
        assert read(r"FigAssemble.Document\shell\open", "FriendlyAppName") == "FigAssemble"
        assert read(r".figasm\OpenWithProgids", "FigAssemble.Document") == ""
        for ext in (".pptx", ".pptm", ".potx"):
            assert read(f"{ext}\\OpenWithProgids", "FigAssemble.Deck") == ""   # Open with only: the deck's own app stays
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
        remove(r"Software\FigAssembleTest")

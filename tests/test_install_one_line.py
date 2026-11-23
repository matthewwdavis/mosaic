"""The one-line installers (install.sh, install.ps1): they download mosaic.zip from the newest
release (the fixed name tools/release.py uploads beside mosaic-<version>.zip), run the installer
inside it and delete the download afterwards. Tried against a stand-in GitHub serving a release
whose installers are stand-ins too, so nothing is installed."""
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

from mosaic._labapp.fakegithub import FakeGitHub, add_release

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = "https://github.com/matthewwdavis/mosaic/releases/latest/download/mosaic.zip"


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_the_one_line_installers_fetch_what_a_release_uploads():
    data = json.loads(read(os.path.join("mosaic", "data", "updates.json")))
    assert LATEST == f"https://github.com/{data['owner']}/{data['repo']}/releases/latest/download/mosaic.zip"
    sh, ps1 = read("install.sh"), read("install.ps1")
    assert LATEST in sh and LATEST in ps1
    for name in re.findall(r"install-[a-z]+\.(?:command|sh|bat)", sh + ps1):
        assert os.path.isfile(os.path.join(ROOT, name)), name


STUBS = {   # stand-in installers: they say they ran, and from where
    "install-mac.command": 'printf "install-mac.command %s\\n" "$(cd "$(dirname "$0")" && pwd)" > "$STUB_MARKER"\n',
    "install-linux.sh": 'printf "install-linux.sh %s\\n" "$(cd "$(dirname "$0")" && pwd)" > "$STUB_MARKER"\n',
    "install-windows.bat": '@echo off\r\necho install-windows.bat %~dp0> "%STUB_MARKER%"\r\n',
}


@pytest.fixture
def github(tmp_path):
    """A stand-in GitHub, public, with mosaic 9.9.9 released as release.py uploads it (the two ZIPs)."""
    zpath = tmp_path / "mosaic-9.9.9.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for name, text in STUBS.items():
            z.writestr(f"mosaic-9.9.9/{name}", text)
        z.writestr("mosaic-9.9.9/environment.yml", "name: mosaic\n")
    shutil.copyfile(zpath, tmp_path / "mosaic.zip")
    add_release(str(tmp_path / "releases"), "v9.9.9", [str(zpath), str(tmp_path / "mosaic.zip")])
    with FakeGitHub(str(tmp_path / "releases"), private=False, owner="matthewwdavis", repo="mosaic") as gh:
        yield gh


def ran(marker):
    """(the installer that ran, the folder it ran from)"""
    with open(marker, encoding="utf-8") as fh:
        name, _, folder = fh.read().strip().partition(" ")
    return name, folder.rstrip("\\")


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash") or not shutil.which("curl"),
                    reason="install.sh is for Macs and Linux")
def test_install_sh_runs_the_newest_releases_installer_and_deletes_the_download(github, tmp_path):
    marker = tmp_path / "ran.txt"
    env = {**os.environ, "MOSAIC_ZIP_URL": github.web + LATEST[len("https://github.com"):], "STUB_MARKER": str(marker),
           "TMPDIR": str(tmp_path)}
    # Piped into bash, as the one line does
    out = subprocess.run(["bash"], input=read("install.sh"), env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    name, folder = ran(marker)
    assert name == ("install-mac.command" if sys.platform == "darwin" else "install-linux.sh")
    assert os.path.basename(folder) == "mosaic-9.9.9"
    assert not os.path.exists(os.path.dirname(folder))   # (the download and its folder, deleted afterwards)


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 is for Windows")
def test_install_ps1_runs_the_newest_releases_installer_and_deletes_the_download(github, tmp_path):
    marker = tmp_path / "ran.txt"
    env = {**os.environ, "MOSAIC_ZIP_URL": github.web + LATEST[len("https://github.com"):], "STUB_MARKER": str(marker)}
    script = os.path.join(ROOT, "install.ps1")
    # As `irm ... | iex` runs it: the script's text, evaluated, in Windows PowerShell
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                          f"Get-Content -Raw -LiteralPath '{script}' | Invoke-Expression"],
                         env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    name, folder = ran(marker)
    assert name == "install-windows.bat" and os.path.basename(folder) == "mosaic-9.9.9"
    assert not os.path.exists(os.path.dirname(folder))

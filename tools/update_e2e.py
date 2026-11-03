"""mosaic updating itself for real: an installed copy (made by the installer) updates from a
stand-in GitHub (tools/fake_github.py, private, with a sign-in), goes back a version, and takes a
test version, each time through the new version's own installer. Run by CI on Mac and Windows
after the installer; or by hand on a copy installed for the purpose:

    python tools/update_e2e.py --python PATH/TO/ENV/python [--keep]

The releases are this folder with other version numbers (99.0.0; 0.0.1 to go back to; 100.0.0 as
a test version), signed with a throwaway key. Settings and downloads go to a scratch folder.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

from fake_github import FakeGitHub  # noqa: E402

failures: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {what}" + (f" ({detail})" if detail and not ok else ""), flush=True)
    if not ok:
        failures.append(what)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", required=True, help="the installed environment's Python")
    ap.add_argument("--keep", action="store_true", help="keep the scratch folder")
    ap.add_argument("--minutes", type=float, default=15, help="the longest one install may take")
    args = ap.parse_args()
    scratch = tempfile.mkdtemp(prefix="mosaic-update-e2e-")
    home, folder = os.path.join(scratch, "home"), os.path.join(scratch, "releases")
    os.makedirs(home)
    key_file = os.path.join(scratch, "test.key")
    public = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "release.py"), "testkey", key_file],
                            check=True, capture_output=True, text=True).stdout.strip()

    def publish(version, test=False):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "release.py"), "local", "--src", ROOT,
                        "--version", version, "--key-file", key_file, "--out", folder] + (["--test"] if test else []),
                       check=True)
    for v, test in (("0.0.1", False), ("99.0.0", False), ("100.0.0", True)):
        publish(v, test)

    gh = FakeGitHub(folder, private=True, tokens=["ghu_e2e"]).start()
    env = dict(os.environ, MOSAIC_HOME=home, MOSAIC_KEYSTORE="file", MOSAIC_UPDATE_API=gh.api,
               MOSAIC_UPDATE_WEB=gh.web, MOSAIC_UPDATE_TEST_KEY=public)
    for k in ("MOSAIC_UPDATE_KIND", "MOSAIC_NO_OPEN"):
        env.pop(k, None)
    # Signed in already, as after GitHub's sign-in (the repository is private)
    run = lambda *a: subprocess.run([args.python, *a], env=env, cwd=scratch, capture_output=True, text=True)   # noqa: E731
    run("-I", "-c", "from mosaic.updates import Keystore, SIGNIN_SERVICE; import json; "
                    "Keystore(SIGNIN_SERVICE).set(json.dumps({'access_token': 'ghu_e2e', 'login': 'ci'}))")
    version = lambda: run("-I", "-c", "import mosaic; print(mosaic.__version__)").stdout.strip()   # noqa: E731
    result = os.path.join(home, "updates", "install.result")
    log = os.path.join(home, "updates", "install.log")

    def install(*flags):
        """`mosaic update` with these flags, then wait for its installer to finish."""
        if os.path.exists(result):
            os.remove(result)
        out = run("-m", "mosaic", "update", *flags)
        print(out.stdout.strip() + (("\n" + out.stderr.strip()) if out.stderr.strip() else ""), flush=True)
        t0 = time.time()
        while not os.path.exists(result) and time.time() - t0 < args.minutes * 60:
            time.sleep(1)
        time.sleep(1)   # (the installer's last lines)
        text = open(result).read().strip() if os.path.exists(result) else "no result"
        print(f"  installer: {text} after {time.time() - t0:.0f} s", flush=True)
        return text

    before = version()
    print(f"Installed mosaic: {before}", flush=True)
    got = install("--install")
    log_text = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    check(got == "ok" and version() == "99.0.0", "an update downloads (signed in), and its installer installs it",
          f"{got}; {version()}")
    check("The tools mosaic uses are up to date" in log_text, "the conda step is skipped when environment.yml is the same")
    check(not any(auth for host, _, auth in gh.seen if host == "objects"), "the sign-in isn't sent on with the download")
    if sys.platform == "darwin":
        app_dir = run("-I", "-c", "from mosaic.updates import mac_app_dir; print(mac_app_dir())").stdout.strip()
        plist = os.path.join(app_dir, "mosaic.app", "Contents", "Info.plist")
        import plistlib
        shown = plistlib.load(open(plist, "rb")).get("CFBundleShortVersionString") if os.path.exists(plist) else None
        check(shown == "99.0.0", "the app in Applications is the new version", f"{plist}: {shown}")
    status = run("-m", "mosaic", "update").stdout
    check("; update " not in status and "newest 99.0.0" in status, "test versions aren't taken by default", status)
    state = json.load(open(os.path.join(home, "updates", "state.json")))
    check((state.get("updated") or {}).get("version") == "99.0.0", "mosaic knows it was updated (for What's new)",
          str(state.get("updated")))
    got = install("--go-back")
    check(got == "ok" and version() == "0.0.1", "going back installs the version before", f"{got}; {version()}")
    status = run("-m", "mosaic", "update").stdout
    check("skipping 99.0.0" in status and "; update" not in status, "and the version gone back from is skipped", status)
    got = install("--install", "--test")
    check(got == "ok" and version() == "100.0.0", "with test versions on, the test version installs", f"{got}; {version()}")
    gh.stop()
    if failures:
        print(f"\n{len(failures)} failed. The last installer's log:\n" + (open(log, errors="replace").read() if os.path.exists(log) else "(none)"))
    else:
        print("\nAll passed.")
    if not args.keep:
        shutil.rmtree(scratch, ignore_errors=True)
    else:
        print(f"Kept {scratch}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

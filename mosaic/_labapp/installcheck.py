"""The app as an installer leaves it, opened: before a push (each app's git pre-push hook,
tools/install_check.py), the check GitHub's installer runs make after it, done here first.

The app's package is built as pip builds it (a wheel: only the files pyproject.toml's package data
takes in), from a clean copy of the commit being pushed (git archive: never the working folder, whose
build/ folder, left by an earlier build, would put in files the package data no longer takes),
installed into a scratch environment that borrows the app's own environment's packages
(so nothing is downloaded and it takes a minute or two), and opened from outside the source folder,
so the installed copy is the one that runs. 27 Nov 2026: mosaic's button callouts imported a file
the package didn't take in; every test passed from the source folder, and GitHub's installer check
failed on all three systems after the push.

    from ._labapp import installcheck
    installcheck.main("mosaic", ROOT, smoke={"MOSAIC_SMOKETEST": "launch"}, expect=['SMOKE launch: {"ready": true'])
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def check(package: str, root: str, smoke: dict, expect: list[str], python: str | None = None, limit: int = 300,
          log=print, ref: str = "HEAD") -> tuple[bool, str]:
    """(ok, what happened). package: the import name ("prose", "mosaic"); root: the project folder (a
    git repository); ref: the commit to check (what's being pushed); smoke: the app's environment
    variables for a smoke start (its own home and cache are made here); expect: lines the start must
    print (each a piece of a line)."""
    python = python or sys.executable
    started = time.monotonic()
    tmp = tempfile.mkdtemp(prefix=f"{package}-install-check-")
    try:
        src = os.path.join(tmp, "src")
        os.makedirs(src)
        arch = subprocess.run(["git", "-C", root, "archive", "--format=tar", ref], capture_output=True)
        if arch.returncode:
            return False, f"git archive {ref} failed: {arch.stderr.decode('utf-8', 'replace')[-500:]}"
        r = subprocess.run(["tar", "-x", "-C", src], input=arch.stdout, capture_output=True)
        if r.returncode:
            return False, "the commit's files weren't copied out: " + r.stderr.decode("utf-8", "replace")[-500:]
        wheels = os.path.join(tmp, "wheel")
        log(f"{package}: building the package as pip does ({ref[:10]})")
        r = _run([python, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "-q", "-w", wheels, src])
        if r.returncode:
            return False, "the package didn't build:\n" + (r.stderr or r.stdout)[-2000:]
        wheel = sorted(glob.glob(os.path.join(wheels, "*.whl")))
        if not wheel:
            return False, "the build made no wheel"
        venv = os.path.join(tmp, "env")
        r = _run([python, "-m", "venv", "--system-site-packages", venv])
        if r.returncode:
            return False, "the scratch environment wasn't made:\n" + r.stderr[-2000:]
        vpy = os.path.join(venv, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
        log(f"{package}: installing it into a scratch environment")
        r = _run([vpy, "-m", "pip", "install", "--no-deps", "--no-index", "--force-reinstall", "-q", wheel[-1]])
        if r.returncode:
            return False, "the package didn't install:\n" + (r.stderr or r.stdout)[-2000:]
        away = os.path.join(tmp, "elsewhere")
        os.makedirs(away)
        r = _run([vpy, "-P", "-c", f"import {package}, os; print(os.path.realpath({package}.__file__))"], cwd=away)
        where = r.stdout.strip()
        if r.returncode or not where.startswith(os.path.realpath(venv)):
            return False, f"the installed copy isn't the one that runs: {where or r.stderr[-500:]}"
        log(f"{package}: opening the installed copy")
        env = {**os.environ, **smoke, "PYTHONUNBUFFERED": "1",
               f"{package.upper()}_HOME": os.path.join(tmp, "home"), f"{package.upper()}_CACHE": os.path.join(tmp, "cache")}
        env.pop("PYTHONPATH", None)
        try:
            r = _run([vpy, "-P", "-m", package], cwd=away, env=env, timeout=limit)
            out = (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired as exc:
            out = str(exc.stdout or "") + str(exc.stderr or "")
            return False, f"the installed app didn't finish starting in {limit} s:\n{out[-2000:]}"
        missing = [e for e in expect if e not in out]
        if missing:
            return False, f"the installed app didn't start as it should (no {missing}):\n{out[-3000:]}"
        return True, f"the installed copy opens ({time.monotonic() - started:.0f} s)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pushed(lines) -> list[str]:
    """The commits a pre-push hook is given (its standard input: "<local ref> <sha> <remote ref> <sha>"
    a line), without deletions (all zeros); none: a run by hand, HEAD"""
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) == 4 and set(parts[1]) != {"0"} and parts[1] not in out:
            out.append(parts[1])
    return out or ["HEAD"]


def main(package: str, root: str, smoke: dict, expect: list[str], stdin=None) -> int:
    """For tools/install_check.py: 0 when the installed copy of each commit pushed opens, else 1
    (what happened printed). stdin: the pre-push hook's (the commits); none, HEAD."""
    if os.environ.get("LABAPP_SKIP_INSTALL_CHECK"):
        print(f"{package}: install check skipped (LABAPP_SKIP_INSTALL_CHECK)")
        return 0
    lines = [] if stdin is None or stdin.isatty() else stdin.read().splitlines()
    for ref in pushed(lines):
        ok, text = check(package, root, smoke, expect, ref=ref)
        print(f"{package}: {'OK' if ok else 'FAILED'}: {text}")
        if not ok:
            print(f"{package}: the push is stopped (git push --no-verify pushes anyway)")
            return 1
    return 0

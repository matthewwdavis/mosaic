"""Publish a mosaic release, which installed copies then update to (mosaic/updates.py).

    python tools/release.py key new          make the release key (once): kept in this Mac's Keychain,
                                             with a backup for you to keep somewhere safe
    python tools/release.py key backup       show the backup again
    python tools/release.py key restore      put the key on this computer from its backup (a new computer)
    python tools/release.py key check        is the key here, and does mosaic trust it?
    python tools/release.py publish [VERSION] [--test] [--notes FILE] [--yes]
                                             release main as VERSION (default: the next patch version);
                                             --test makes it a test version, for testers only
    python tools/release.py promote VERSION  a test version goes to everyone
    python tools/release.py list             the releases, and how often each was downloaded

Run `key new`, `key backup` and `key restore` in your own Terminal window, not through Claude:
they show the private key, and anything shown in a Claude session is kept in its transcript.

A release is the repository at its tag as a ZIP (what people install from, and what updates
install) and release.json, which says the version, the ZIP's SHA-256 and size and what changed,
signed with the release key. Installed copies accept only releases signed with a key listed in
mosaic/data/updates.json.

For the tests and CI there are also `testkey` (a throwaway key in a file) and `local` (a release
from a folder, signed with that key, into tools/fake_github.py's folder).
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mosaic import updates  # noqa: E402

KEY_SERVICE = "FigAssemble release key"
BACKUP_PREFIX = "figassemble-release-key-1"
DATA = os.path.join(ROOT, "mosaic", "data", "updates.json")
OUT = os.path.join(ROOT, "dist", "release")
SKIP = {".git", "__pycache__", "dist", "build", ".pytest_cache", "claude-commands.log", ".DS_Store"}


def die(msg: str) -> None:
    print(f"\n{msg}", file=sys.stderr)
    sys.exit(1)


def run(*cmd, check=True, capture=True, cwd=ROOT) -> str:
    res = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    if check and res.returncode != 0:
        die(f"{' '.join(cmd)} failed:\n{(res.stderr or res.stdout or '').strip()}")
    return (res.stdout or "").strip()


# The key ---------------------------------------------------------------------------------------

def backup_text(raw: bytes) -> str:
    """The key as one line to keep: base64, and a check that catches a typo or a cut-off paste."""
    return f"{BACKUP_PREFIX}:{base64.b64encode(raw).decode('ascii')}:{hashlib.sha256(raw).hexdigest()[:8]}"


def from_backup(text: str) -> bytes:
    parts = text.strip().split(":")
    if len(parts) != 3 or parts[0] != BACKUP_PREFIX:
        raise ValueError(f"a backup starts with {BACKUP_PREFIX}: and has two more parts after colons")
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except ValueError:
        raise ValueError("the middle part isn't a key (part of it may be missing)") from None
    if len(raw) != 32 or hashlib.sha256(raw).hexdigest()[:8] != parts[2]:
        raise ValueError("the check at the end doesn't match: part of the key is missing or mistyped")
    return raw


def public_of(raw: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw()


def keystore() -> updates.Keystore:
    return updates.Keystore(KEY_SERVICE, "release")


def load_key() -> bytes | None:
    text = keystore().get()
    return from_backup(text) if text else None


def trusted(data_text: str | None = None) -> dict[str, str]:
    """Trusted key ids → their notes, from data/updates.json (as it is, or the text given)."""
    data = json.loads(data_text) if data_text else json.load(open(DATA, encoding="utf-8"))
    return {updates.key_id(base64.b64decode(k["public"])): k.get("note", "") for k in data.get("release_keys", [])}


def trust(public: bytes, note: str) -> None:
    with open(DATA, encoding="utf-8") as fh:
        data = json.load(fh)
    keys = data.setdefault("release_keys", [])
    if updates.key_id(public) not in {updates.key_id(base64.b64decode(k["public"])) for k in keys}:
        keys.append({"id": updates.key_id(public), "public": base64.b64encode(public).decode("ascii"), "note": note})
    with open(DATA, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")


def key_new(args) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if keystore().get() and not args.replace:
        die("This computer already has a release key (`key check` shows it). To make another one anyway, "
            "add --replace; mosaic keeps trusting the old one until you take it out of "
            "mosaic/data/updates.json.")
    raw = Ed25519PrivateKey.generate().private_bytes_raw()
    text = backup_text(raw)
    keystore().set(text)
    trust(public_of(raw), f"made {time.strftime('%Y-%m-%d')} on {platform.node()}")
    print(f"""
A release key is made and kept in this computer's {'Keychain' if sys.platform == 'darwin' else 'key store'}.
mosaic will trust it once mosaic/data/updates.json (which now lists it) is committed and
released.

Its backup, the one way to sign releases from another computer:

    {text}

Keep it somewhere safe that isn't this computer: the Passwords app (it syncs to your other Apple
devices), another password manager, or printed and filed. Anyone who has it can sign mosaic
updates, so don't email it or put it in the repository. On a new computer:
python tools/release.py key restore
""")
    typed = input("To check it's kept, type the 8 characters after the last colon: ").strip()
    if typed != text.rsplit(":", 1)[1]:
        print("That doesn't match. The key is kept on this computer; `key backup` shows it again.")
    else:
        print("Thanks. Remember to keep the backup off this computer.")


def key_backup(_args) -> None:
    raw = load_key()
    if raw is None:
        die("There's no release key on this computer (`key new` makes one, `key restore` brings one back).")
    if input("This shows the private release key; anyone who has it can sign mosaic updates. Show it? [y/N] ")\
            .strip().lower() != "y":
        return
    print(f"\n    {backup_text(raw)}\n")


def key_restore(_args) -> None:
    text = getpass.getpass("Paste the backup (it isn't shown) and press Return: ")
    try:
        raw = from_backup(text)
    except ValueError as exc:
        die(f"That isn't a whole backup: {exc}.")
    kid = updates.key_id(public_of(raw))
    keystore().set(backup_text(raw))
    known = trusted()
    print(f"The release key ({kid}) is kept on this computer now."
          + ("" if kid in known else "\nmosaic doesn't list it as trusted, though: releases signed with it won't "
             "install until a release that trusts it (mosaic/data/updates.json) has been installed by hand."))


def key_check(_args) -> None:
    raw = load_key()
    if raw is None:
        die("There's no release key on this computer (`key new` makes one, `key restore` brings one back).")
    kid = updates.key_id(public_of(raw))
    known = trusted()
    print(f"This computer has release key {kid}: " + (f"trusted ({known[kid]})." if kid in known else
                                                       "NOT trusted by mosaic/data/updates.json."))


# Building a release ----------------------------------------------------------------------------

def manifest_for(zip_path: str, version: str, environment: bytes, notes: str, commit: str = "") -> dict:
    with open(zip_path, "rb") as fh:
        data = fh.read()
    return {"app": updates.APP, "version": version, "tag": f"v{version}", "commit": commit,
            "released": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "notes": notes.strip(),
            "zip": {"name": os.path.basename(zip_path), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
            "environment_sha256": hashlib.sha256(environment).hexdigest()}


def zip_tree(src: str, version: str, out_zip: str) -> None:
    """A release ZIP from a folder (for the tests and CI), with that version in __init__.py."""
    top = f"mosaic-{version}"
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(src):
            dirs[:] = sorted(x for x in dirs if x not in SKIP and not x.endswith(".egg-info"))
            for f in sorted(files):
                if f in SKIP or f.endswith((".pyc", ".tmp")):
                    continue
                path = os.path.join(d, f)
                rel = os.path.relpath(path, src).replace(os.sep, "/")
                if rel == "mosaic/__init__.py":
                    text = re.sub(r'__version__ = "[^"]*"', f'__version__ = "{version}"', open(path, encoding="utf-8").read())
                    z.writestr(f"{top}/{rel}", text)
                else:
                    z.write(path, f"{top}/{rel}")


def testkey(args) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    raw = Ed25519PrivateKey.generate().private_bytes_raw()
    with open(args.file, "w") as fh:
        fh.write(base64.b64encode(raw).decode("ascii"))
    print(base64.b64encode(public_of(raw)).decode("ascii"))


def local(args) -> None:
    """A release from a folder into a tools/fake_github.py folder, signed with a test key."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from fake_github import add_release
    raw = base64.b64decode(open(args.key_file).read().strip())
    with tempfile.TemporaryDirectory() as tmp:
        zpath = os.path.join(tmp, f"mosaic-{args.version}.zip")
        zip_tree(args.src, args.version, zpath)
        env = open(os.path.join(args.src, "environment.yml"), "rb").read()
        signed = updates.sign_manifest(manifest_for(zpath, args.version, env, args.notes), raw)
        mpath = os.path.join(tmp, updates.MANIFEST)
        with open(mpath, "w") as fh:
            json.dump(signed, fh)
        add_release(args.out, f"v{args.version}", [zpath, mpath], prerelease=args.test, body=args.notes)
    print(f"released {args.version}{' (test)' if args.test else ''} into {args.out}")


# Publishing ------------------------------------------------------------------------------------

def repo() -> str:
    data = json.load(open(DATA, encoding="utf-8"))
    return f"{data['owner']}/{data['repo']}"


def tags() -> list[str]:
    return [t for t in run("git", "tag", "-l", "v*").split() if updates.parse_version(t)]


def next_version(current: str, existing: list[str]) -> str:
    newest = max([updates.parse_version(current)] + [updates.parse_version(t) for t in existing])
    parts = list(newest) + [0] * (3 - len(newest))
    parts[2] += 1
    return ".".join(str(p) for p in parts[:3])


def draft_notes(since: str | None) -> str:
    log = run("git", "log", "--no-merges", "--format=%s", f"{since}..HEAD" if since else "HEAD")
    lines = [s for s in log.splitlines() if s and not s.startswith("Release ")]
    return "What's new:\n\n" + "\n".join(f"- {s}" for s in lines) + "\n"


def ci_passed(sha: str) -> bool:
    out = run("gh", "run", "list", "--commit", sha, "--workflow", "tests.yml", "--json", "status,conclusion", check=False)
    try:
        runs = json.loads(out or "[]")
    except ValueError:
        return False
    return any(r.get("status") == "completed" and r.get("conclusion") == "success" for r in runs)


def publish(args) -> None:
    if run("git", "rev-parse", "--abbrev-ref", "HEAD") != "main":
        die("Releases are made from main; switch to it first.")
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        die("There are uncommitted changes; commit or put them aside first.")
    run("git", "fetch", "origin", "main", "--tags")
    if run("git", "rev-parse", "HEAD") != run("git", "rev-parse", "origin/main"):
        die("main isn't the same as GitHub's (push or pull first), so the release would differ from what's there.")
    run("gh", "auth", "status")
    raw = load_key()
    if raw is None:
        die("There's no release key on this computer (`key restore` brings it back from its backup).")
    kid = updates.key_id(public_of(raw))
    if kid not in trusted(run("git", "show", "HEAD:mosaic/data/updates.json")):
        die(f"The release key here ({kid}) isn't in the committed mosaic/data/updates.json, so installed "
            "copies wouldn't accept the release. Commit it first.")
    sha = run("git", "rev-parse", "HEAD")
    if not args.skip_ci_check and not ci_passed(sha):
        die(f"The tests haven't passed on GitHub for {sha[:7]} (yet?). Wait for them, or add --skip-ci-check.")
    init = os.path.join(ROOT, "mosaic", "__init__.py")
    current = re.search(r'__version__ = "([^"]*)"', open(init, encoding="utf-8").read()).group(1)
    existing = tags()
    version = args.version or next_version(current, existing)
    if not updates.parse_version(version) or (existing and updates.parse_version(version) <= max(
            updates.parse_version(t) for t in existing)):
        die(f"{version} isn't newer than every release so far ({', '.join(existing[-3:])}).")
    since = max(existing, key=updates.parse_version) if existing else None
    os.makedirs(OUT, exist_ok=True)
    if args.notes:
        notes = open(args.notes, encoding="utf-8").read()
    else:
        path = os.path.join(OUT, f"notes-{version}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(draft_notes(since))
        print(f"What's new, drafted from the commits since {since or 'the start'}: {path}")
        if not args.yes:
            input("Edit it into plain words for the people using mosaic, save it, then press Return to go on. ")
        notes = open(path, encoding="utf-8").read()
    print(f"\nReleasing mosaic {version}{' as a test version' if args.test else ''} from {sha[:7]}.")
    if not args.yes and input("Go ahead? [y/N] ").strip().lower() != "y":
        return
    # The version, committed and tagged; the ZIP is the tagged commit
    text = open(init, encoding="utf-8").read()
    with open(init, "w", encoding="utf-8") as fh:
        fh.write(re.sub(r'__version__ = "[^"]*"', f'__version__ = "{version}"', text))
    message = f"Release {version}" + ("\n\n" + "\n".join(args.trailer) if args.trailer else "")
    run("git", "commit", "-q", "-m", message, "--", "mosaic/__init__.py")
    tag = f"v{version}"
    run("git", "tag", "-a", tag, "-m", f"mosaic {version}")
    try:
        zpath = os.path.join(OUT, f"mosaic-{version}.zip")
        run("git", "archive", "--format=zip", f"--prefix=mosaic-{version}/", "-o", zpath, tag)
        env = subprocess.run(["git", "show", f"{tag}:environment.yml"], cwd=ROOT, capture_output=True, check=True).stdout
        signed = updates.sign_manifest(manifest_for(zpath, version, env, notes, run("git", "rev-parse", tag)), raw)
        updates.verify_manifest(signed)   # (trusted by this checkout: the same keys)
        mpath = os.path.join(OUT, updates.MANIFEST)
        with open(mpath, "w") as fh:
            json.dump(signed, fh, indent=1)
        notes_path = os.path.join(OUT, f"notes-{version}.md")
        with open(notes_path, "w", encoding="utf-8") as fh:
            fh.write(notes)
    except BaseException:
        run("git", "tag", "-d", tag, check=False)
        run("git", "reset", "-q", "--keep", "HEAD~1", check=False)
        raise
    run("git", "push", "-q", "origin", "main")
    run("git", "push", "-q", "origin", tag)
    cmd = ["gh", "release", "create", tag, zpath, mpath, "--repo", repo(), "--title", f"mosaic {version}",
           "--notes-file", notes_path]
    if args.test:
        cmd += ["--prerelease", "--latest=false"]
    url = run(*cmd)
    print(f"\nReleased mosaic {version}{' (test version)' if args.test else ''}: {url}")
    print("Installed copies find it within a few hours (at once when mosaic next starts)."
          + (f"\nWhen it has been tried: python tools/release.py promote {version}" if args.test else ""))


def promote(args) -> None:
    tag = f"v{args.version.lstrip('vV')}"
    run("gh", "release", "edit", tag, "--repo", repo(), "--prerelease=false", "--latest")
    print(f"{tag} is a full release now: everyone's mosaic takes it.")


def list_releases(_args) -> None:
    out = run("gh", "api", f"repos/{repo()}/releases", "--paginate")
    for r in json.loads(out or "[]"):
        downloads = sum(a.get("download_count", 0) for a in r.get("assets", []) if a["name"].endswith(".zip"))
        print(f"{r['tag_name']:>10}  {(r.get('published_at') or '')[:10]}  "
              f"{'test   ' if r.get('prerelease') else 'release'}  {downloads} downloads")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("key", help="the release key")
    k.add_argument("what", choices=["new", "backup", "restore", "check"])
    k.add_argument("--replace", action="store_true")
    p = sub.add_parser("publish", help="release main")
    p.add_argument("version", nargs="?")
    p.add_argument("--test", action="store_true", help="a test version (a GitHub pre-release)")
    p.add_argument("--notes", help="What's new, from this file instead of a draft")
    p.add_argument("--yes", action="store_true", help="don't stop to ask")
    p.add_argument("--skip-ci-check", action="store_true")
    p.add_argument("--trailer", action="append", default=[], help="a line to end the version commit's message with")
    pr = sub.add_parser("promote", help="a test version goes to everyone")
    pr.add_argument("version")
    sub.add_parser("list", help="the releases and their downloads")
    t = sub.add_parser("testkey", help="(tests) a throwaway key in a file; prints its public half")
    t.add_argument("file")
    lo = sub.add_parser("local", help="(tests) a release from a folder into a fake GitHub's folder")
    lo.add_argument("--src", default=ROOT)
    lo.add_argument("--version", required=True)
    lo.add_argument("--key-file", required=True)
    lo.add_argument("--out", required=True)
    lo.add_argument("--test", action="store_true")
    lo.add_argument("--notes", default="What's new:\n\n- A test release")
    args = ap.parse_args()
    if args.cmd == "key":
        {"new": key_new, "backup": key_backup, "restore": key_restore, "check": key_check}[args.what](args)
    else:
        {"publish": publish, "promote": promote, "list": list_releases, "testkey": testkey, "local": local}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

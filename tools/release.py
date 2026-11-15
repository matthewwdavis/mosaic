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

The tool itself is the shared library's (mosaic/_labapp/release.py); this says it's for mosaic.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mosaic import updates  # noqa: E402
from mosaic._labapp import release  # noqa: E402
from mosaic._labapp.release import backup_text, from_backup, manifest_for, next_version, zip_tree  # noqa: E402,F401

# (the key's names are from when mosaic was called FigAssemble: a key made then is still found)
release.setup("mosaic", ROOT, updates, key_service="FigAssemble release key", backup_prefix="figassemble-release-key-1")

if __name__ == "__main__":
    sys.exit(release.main())

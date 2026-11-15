"""Updates: mosaic looks for a newer version on GitHub, checks that it was signed with the
release key, and installs it with the new version's own installer once mosaic has closed.

A release (tools/release.py) carries the source ZIP people also install from, and release.json:
the version, the ZIP's SHA-256 and size and what changed, signed with the release key. Only the
keys listed in data/updates.json are trusted, so nobody else who can push to the repository can
send code to everyone's computer.

While the repository is private, reading its releases takes a GitHub sign-in, once per computer,
through the mosaic updates GitHub app: it can only read this repository, and only for
people added to it. Once the repository is public, a look without a sign-in finds it, and
nobody needs to sign in.

Settings: `updates` ("auto": download in the background and install when mosaic quits;
"ask": say so and wait for a click; "off": don't look) and `update_channel` ("test" also takes
test versions, which are GitHub pre-releases).

The updater itself is the shared library's (_labapp/updates.py, `shared` here: looking, checking
the signature, downloading, starting the installer, the sign-in); this says what is mosaic's:
its name, its settings folder, data/updates.json, and the sign-in kept from FigAssemble's days.
"""
from __future__ import annotations

import os

from . import __version__
from ._labapp import updates as shared
from ._labapp.updates import (CHECK_EVERY, FIRST_LOOK, INSTALLER, LOCK, LOG, MANIFEST, MAX_TRIES, RESULT, Keystore,   # noqa: F401
                              UpdateError, Updater, api_base, cli, extract, http, install_kind, install_running,
                              key_id, mac_app_dir, parse_version, pick, pid_alive, release_view, settings,
                              sign_manifest, trusted_keys, updates_dir, verify_manifest, wait_for_install, web_base)
from .fonts import config_dir

APP = "mosaic"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "updates.json")
SIGNIN_SERVICE = "mosaic GitHub sign-in"
OLD_SIGNIN = ("FigAssemble GitHub sign-in", "figassemble")   # (service, account) from when mosaic was called FigAssemble


def _prefs() -> dict:
    from .app.api import Api
    return Api().prefs_get()


shared.configure(app=APP, env="MOSAIC", version=__version__, settings_dir=config_dir, data=DATA,
                 package_dir=os.path.dirname(os.path.abspath(__file__)), signin=SIGNIN_SERVICE, old_signin=OLD_SIGNIN,
                 prefs=_prefs)

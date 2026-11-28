"""Updates: the app looks for a newer version on GitHub, checks that it was signed with the
release key, and installs it with the new version's own installer once the app has closed.

A release (tools/release.py) carries the source ZIP people also install from, and release.json:
the version, the ZIP's SHA-256 and size and what changed, signed with the release key. Only the
keys listed in data/updates.json are trusted, so nobody else who can push to the repository can
send code to everyone's computer.

While the repository is private, reading its releases takes a GitHub sign-in, once per computer,
through the the app updates GitHub app: it can only read this repository, and only for
people added to it. Once the repository is public, a look without a sign-in finds it, and
nobody needs to sign in.

Settings: `updates` ("auto": download in the background and install when the app quits;
"ask": say so and wait for a click; "off": don't look) and `update_channel` ("test" also takes
test versions, which are GitHub pre-releases).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

# What the app says of itself (configure), once, before anything here is used:
#   app           its name, as releases and the installer's notes (etc/<app>) have it
#   env           the prefix of its environment variables ("MOSAIC": MOSAIC_UPDATE_API…), which its
#                 installers read too
#   version       the running version
#   settings_dir  its settings folder, or a function giving it (updates/ and the sign-in go there)
#   data          the JSON file saying where updates come from and the keys that sign them
#   package_dir   the folder of the app's package (a checkout beside it means "source")
#   signin        the name its GitHub sign-in is kept under; old_signin: (service, account) of an
#                 earlier name to take a sign-in over from, or None
#   prefs         a function giving the app's settings (for `<app> update` in a terminal)
cfg: dict = {"app": "app", "env": "APP", "version": "0", "settings_dir": None, "data": None, "package_dir": None,
             "signin": None, "old_signin": None, "prefs": lambda: {}}


def configure(**values) -> None:
    unknown = set(values) - set(cfg)
    if unknown:
        raise TypeError(f"not an updates setting: {sorted(unknown)}")
    cfg.update(values)


def _env(name: str) -> str:
    """The app's environment variable of that name: MOSAIC_UPDATE_API for mosaic's "UPDATE_API"."""
    return f"{cfg['env']}_{name}"


def _settings_dir() -> str:
    d = cfg["settings_dir"]
    return d() if callable(d) else d


def _signin() -> str:
    return cfg["signin"] or f"{cfg['app']} GitHub sign-in"


MANIFEST = "release.json"         # the signed description among a release's files
CHECK_EVERY = 6 * 3600            # seconds between looks while the app stays open
FIRST_LOOK = 20                   # seconds after starting, so the look doesn't slow the start
MAX_TRIES = 2                     # failed installs of one version before it waits for a click
INSTALLER = {"darwin": "install-mac.command", "win32": "install-windows.bat"}.get(sys.platform)
LOCK, RESULT, LOG = "install.lock", "install.result", "install.log"


class UpdateError(Exception):
    """Why there's no update, or why it didn't install, in words for the person using the app."""


def settings() -> dict:
    """Where updates come from and the keys that sign them (data/updates.json)."""
    with open(cfg["data"], encoding="utf-8") as fh:
        return json.load(fh)


def api_base() -> str:
    return os.environ.get(_env("UPDATE_API"), "https://api.github.com").rstrip("/")


def web_base() -> str:
    return os.environ.get(_env("UPDATE_WEB"), "https://github.com").rstrip("/")


def parse_version(text: str | None) -> tuple[int, ...]:
    """'0.2.1' or 'v0.2.1' as (0, 2, 1), for comparing; trailing zeros don't count (0.2 is 0.2.0)."""
    parts = []
    for p in (text or "").strip().lstrip("vV").split("."):
        if not p.isdigit():
            break
        parts.append(int(p))
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


# Signatures ------------------------------------------------------------------------------------

def key_id(public: bytes) -> str:
    return hashlib.sha256(public).hexdigest()[:16]


def trusted_keys() -> dict[str, bytes]:
    """The release keys the app accepts, by id; tests add one with <APP>_UPDATE_TEST_KEY."""
    keys = {}
    extra = [os.environ[_env("UPDATE_TEST_KEY")]] if os.environ.get(_env("UPDATE_TEST_KEY")) else []
    for text in [k["public"] for k in settings().get("release_keys", [])] + extra:
        raw = base64.b64decode(text)
        keys[key_id(raw)] = raw
    return keys


def sign_manifest(manifest: dict, private: bytes) -> dict:
    """release.json: the manifest's bytes and their signature with the release key (tools/release.py)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.from_private_bytes(private)
    payload = json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"format": 1, "key": key_id(key.public_key().public_bytes_raw()),
            "payload": base64.b64encode(payload).decode("ascii"),
            "signature": base64.b64encode(key.sign(payload)).decode("ascii")}


def verify_manifest(signed) -> dict:
    """The manifest, if a trusted key signed exactly these bytes; else UpdateError."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(signed, dict) or signed.get("format") != 1:
        raise UpdateError(f"the release's description is in a form this {cfg['app']} doesn't know")
    public = trusted_keys().get(signed.get("key"))
    if public is None:
        raise UpdateError(f"the release isn't signed with a key this {cfg['app']} trusts")
    try:
        payload = base64.b64decode(signed["payload"], validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(signed["signature"], validate=True), payload)
        manifest = json.loads(payload)
    except (InvalidSignature, ValueError, KeyError, TypeError):
        raise UpdateError("the release's signature doesn't match, so it may have been changed") from None
    if not isinstance(manifest, dict) or manifest.get("app") != cfg["app"] or not parse_version(manifest.get("version")):
        raise UpdateError(f"the release's description isn't for {cfg['app']}")
    return manifest


# Secrets: the GitHub sign-in (and, for tools/release.py, the release key) -----------------------

class Keystore:
    """A secret kept for this user: in the Mac's Keychain, in Windows' Credential Manager, or
    elsewhere (and with <APP>_KEYSTORE=file, as the tests use) in a file in the settings
    folder that only the user can read."""

    def __init__(self, service: str, account: str | None = None):
        self.service, self.account = service, account or cfg["app"]
        self.backend = os.environ.get(_env("KEYSTORE")) or {"darwin": "keychain", "win32": "windows"}.get(
            sys.platform, "file")

    def get(self) -> str | None:
        return getattr(self, f"_{self.backend}")("get")

    def set(self, value: str) -> None:
        getattr(self, f"_{self.backend}")("set", value)

    def delete(self) -> None:
        getattr(self, f"_{self.backend}")("delete")

    def _file(self, op: str, value: str | None = None):
        path = os.path.join(_settings_dir(), "".join(c if c.isalnum() else "-" for c in self.service.lower()) + ".secret")
        if op == "get":
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read() or None
            except OSError:
                return None
        if op == "delete":
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value)
        os.replace(path + ".tmp", path)
        return None

    def _keychain(self, op: str, value: str | None = None):
        import Foundation
        import Security
        query = {Security.kSecClass: Security.kSecClassGenericPassword, Security.kSecAttrService: self.service,
                 Security.kSecAttrAccount: self.account}
        if op == "get":
            status, data = Security.SecItemCopyMatching(
                {**query, Security.kSecReturnData: True, Security.kSecMatchLimit: Security.kSecMatchLimitOne}, None)
            return bytes(data).decode("utf-8") if status == 0 and data is not None else None
        if op == "delete":
            Security.SecItemDelete(query)
            return None
        raw = value.encode("utf-8")
        data = Foundation.NSData.dataWithBytes_length_(raw, len(raw))
        status = Security.SecItemUpdate(query, {Security.kSecValueData: data})
        if status == -25300:   # errSecItemNotFound: the first time
            status, _ = Security.SecItemAdd({**query, Security.kSecValueData: data}, None)
        if status != 0:
            raise OSError(f"the Keychain didn't keep it (error {status})")
        return None

    def _windows(self, op: str, value: str | None = None):
        import ctypes
        from ctypes import wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        adv.CredReadW.restype = wintypes.BOOL
        adv.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        adv.CredWriteW.restype = wintypes.BOOL
        adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        adv.CredDeleteW.restype = wintypes.BOOL
        adv.CredFree.argtypes = [ctypes.c_void_p]
        target, generic = self.service, 1   # (as Credential Manager lists it)
        if op == "get":
            found = ctypes.POINTER(CREDENTIAL)()
            if not adv.CredReadW(target, generic, 0, ctypes.byref(found)):
                return None
            try:
                c = found.contents
                return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-8")
            finally:
                adv.CredFree(found)
        if op == "delete":
            adv.CredDeleteW(target, generic, 0)
            return None
        raw = value.encode("utf-8")
        blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        cred = CREDENTIAL(Type=generic, TargetName=target, CredentialBlobSize=len(raw), Persist=2,   # this computer
                          CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte)), UserName=self.account)
        if not adv.CredWriteW(ctypes.byref(cred), 0):
            raise OSError(f"Windows' Credential Manager didn't keep it (error {ctypes.get_last_error()})")
        return None


# GitHub ----------------------------------------------------------------------------------------

class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None   # followed by hand (http), so a sign-in never goes along to another host


_opener = urllib.request.build_opener(_Redirects)


def http(url: str, token: str | None = None, accept: str = "application/vnd.github+json", form: dict | None = None,
         timeout: float = 30, stream: bool = False):
    """GET, or POST `form`, with GitHub's headers; the sign-in goes only to the host first asked.
    Returns (status, headers, body), the body as bytes, or with `stream` the open response for a
    200. UpdateError when there's no connection."""
    data = urllib.parse.urlencode(form).encode("ascii") if form is not None else None
    host = urllib.parse.urlsplit(url).netloc
    for _ in range(8):
        same = urllib.parse.urlsplit(url).netloc == host
        headers = {"User-Agent": f"{cfg['app']}/{cfg['version']} ({sys.platform})", "Accept": accept}
        if same:
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            if token:
                headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            resp = _opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as err:
            location = err.headers.get("Location")
            if err.code in (301, 302, 303, 307, 308) and location:
                err.close()
                url = urllib.parse.urljoin(url, location)
                to = urllib.parse.urlsplit(url)
                if to.scheme != "https" and not (to.scheme == "http" and to.hostname in ("127.0.0.1", "localhost", "::1")):
                    raise UpdateError(f"GitHub sent {cfg['app']} somewhere that isn't a secure web address") from None
                if err.code == 303:
                    data = None
                continue
            body = err.read()
            err.close()
            return err.code, err.headers, body
        except (urllib.error.URLError, OSError) as err:   # offline, no name lookup, timed out, refused
            reason = getattr(err, "reason", err)
            raise UpdateError(f"GitHub couldn't be reached ({reason}); check the internet connection") from None
        if stream:
            return resp.status, resp.headers, resp
        with resp:
            return resp.status, resp.headers, resp.read()
    raise UpdateError(f"GitHub kept sending {cfg['app']} somewhere else (too many redirects)")


def _json(body: bytes) -> dict | list:
    try:
        return json.loads(body or b"null")
    except ValueError:
        return {}


def release_view(rel: dict) -> dict | None:
    """What the app needs of a GitHub release: None for drafts and anything that isn't a signed
    the app release."""
    version = parse_version(rel.get("tag_name"))
    assets = {a["name"]: {"id": a["id"], "url": a["url"], "download": a.get("browser_download_url"),
                          "size": a.get("size")} for a in rel.get("assets", []) if a.get("name")}
    if rel.get("draft") or not version or MANIFEST not in assets:
        return None
    return {"version": rel["tag_name"].lstrip("vV"), "tag": rel["tag_name"], "prerelease": bool(rel.get("prerelease")),
            "notes": rel.get("body") or "", "published": rel.get("published_at"), "assets": assets}


def pick(releases: list[dict], channel: str, current: str, skip: str | None = None):
    """(the newest release on the channel, the one to update to: newer than `current` and than a
    version skipped, the one before `current`: for going back)."""
    on = sorted((r for r in releases if channel == "test" or not r["prerelease"]),
                key=lambda r: parse_version(r["version"]), reverse=True)
    cur = parse_version(current)
    newest = on[0] if on else None
    update = newest if newest and parse_version(newest["version"]) > cur else None
    if update and skip and parse_version(update["version"]) <= parse_version(skip):
        update = None
    previous = next((r for r in on if parse_version(r["version"]) < cur), None)
    return newest, update, previous


# This installation -----------------------------------------------------------------------------

def install_kind() -> str:
    """'installed' (by the app's installer, which can update it), 'source' (a checkout, or
    pip install -e) or 'other' (it can't update itself)."""
    if os.environ.get(_env("UPDATE_KIND")):   # for tests
        return os.environ[_env("UPDATE_KIND")]
    parent = os.path.dirname(os.path.abspath(cfg["package_dir"])) if cfg["package_dir"] else ""
    if parent and any(os.path.exists(os.path.join(parent, n)) for n in (".git", "pyproject.toml")):
        return "source"
    try:
        from importlib.metadata import distribution
        direct = distribution(cfg["app"]).read_text("direct_url.json")
        if direct and json.loads(direct).get("dir_info", {}).get("editable"):
            return "source"
    except Exception:   # noqa: BLE001 (no metadata: not installed by pip)
        pass
    if not INSTALLER or not os.path.isfile(os.path.join(sys.prefix, "etc", cfg["app"], "installer")):
        return "other"
    return "installed"


def _installed_file(name: str) -> str | None:
    """A note the installer left in the environment (etc/<app>)."""
    try:
        with open(os.path.join(sys.prefix, "etc", cfg["app"], name), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def _mac_program() -> str:
    """The running program's path, as macOS has it: the app's launcher where the app runs Python
    inside itself (packaging.mac_app, whose sys.executable is the environment's python)."""
    if sys.platform != "darwin":
        return ""
    import ctypes
    try:
        get = ctypes.CDLL(None)._NSGetExecutablePath
        size = ctypes.c_uint32(0)
        get(None, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if get(buf, ctypes.byref(size)) != 0:
            return ""
        return os.path.abspath(os.fsdecode(buf.value))
    except (AttributeError, OSError):
        return ""


def mac_app_dir() -> str | None:
    """The folder the .app is in: the running one's, or the one the installer used."""
    mark = ".app/Contents/MacOS/"
    for exe in (_mac_program(), sys.executable):   # (sys.executable: an older app's linked-in python)
        if mark in exe:
            return os.path.dirname(exe[:exe.index(mark) + 4])
    return _installed_file("app_dir")


def updates_dir() -> str:
    path = os.path.join(_settings_dir(), "updates")
    os.makedirs(path, exist_ok=True)
    return path


def pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        handle = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5   # access denied: it exists
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        k32.CloseHandle(ctypes.c_void_p(handle))
        return bool(ok) and code.value == 259   # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def install_running() -> dict | None:
    """The installer's lock while an update installs."""
    try:
        with open(os.path.join(updates_dir(), LOCK), encoding="utf-8") as fh:
            lock = json.load(fh)
    except (OSError, ValueError):
        return None
    if pid_alive(int(lock.get("pid", 0))) and time.time() - lock.get("started", 0) < 3600:
        return lock
    return None


def wait_for_install(timeout: float = 900) -> None:
    """The app opened again while an update installs (straight after quitting): wait for it,
    saying so, before starting."""
    lock = install_running()
    if not lock:
        return
    close = _waiting_notice(lock.get("version") or "a new version")
    t0 = time.time()
    while install_running() and time.time() - t0 < timeout:
        time.sleep(0.5)
    close()


def _waiting_notice(version: str):
    """A small notice that the app opens once the update is in; returns how to close it."""
    version = "".join(c for c in str(version) if c.isalnum() or c in ". -")[:40]   # (it goes into a script: plain words only)
    text = f"{cfg['app']} is finishing its update to {version}. It opens when the update is in, in a minute or so."
    try:
        if sys.platform == "darwin":
            proc = subprocess.Popen(["osascript", "-e", f'display dialog "{text}" with title "{cfg["app"]}" '
                                     'buttons {"OK"} default button 1 giving up after 900'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return proc.terminate
        if os.name == "nt":
            import ctypes
            title = f"{cfg['app']} update"
            threading.Thread(target=lambda: ctypes.windll.user32.MessageBoxW(None, text, title, 0x40 | 0x40000),
                             daemon=True).start()

            def close():
                hwnd = ctypes.windll.user32.FindWindowW(None, title)
                if hwnd:
                    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
            return close
    except Exception:   # noqa: BLE001 (it just waits without saying so)
        pass
    return lambda: None


def extract(zip_path: str, dest: str) -> str:
    """Unpack the release ZIP into `dest` (emptied first); returns the folder with the installers."""
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    root = os.path.realpath(dest)
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target = os.path.realpath(os.path.join(dest, name))
            if target != root and not target.startswith(root + os.sep):
                raise UpdateError("the release ZIP has a file outside its folder")
        z.extractall(dest)
    entries = [e for e in os.listdir(dest) if not e.startswith((".", "__MACOSX"))]
    top = os.path.join(dest, entries[0]) if len(entries) == 1 and os.path.isdir(os.path.join(dest, entries[0])) else dest
    if not INSTALLER or not os.path.isfile(os.path.join(top, INSTALLER)):
        raise UpdateError("the release has no installer for this computer")
    return top


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _remove(path: str) -> None:
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# The updater -----------------------------------------------------------------------------------

class Updater:
    """Looks for updates (at start and every few hours), downloads and checks them, installs one
    when the app quits, and keeps the GitHub sign-in. One per running the app; what it
    knows is kept in updates/state.json in the settings folder."""

    def __init__(self, prefs=None, version: str | None = None):
        self._prefs = prefs or (lambda: {})
        self.version = version or cfg["version"]
        self.lock = threading.RLock()        # the state
        self.token_lock = threading.Lock()   # a refresh uses its refresh token up: one at a time
        self.work = threading.Lock()         # one look or download at a time
        self.busy = None                     # "checking" or "downloading"
        self.progress = None                 # 0-1 while downloading
        self.error = None                    # the last look's problem
        self.access = None                   # "public", "signed_in", "sign_in" (needed) or "no_access"
        self.signin = None                   # the GitHub sign-in under way
        self.restart = False                 # Restart now, Update now or Go back: open again after installing
        self.fake = None                     # what the editor self-test has it say (selftest_update)
        self.keystore = Keystore(_signin())
        self._creds = ...                    # the sign-in, once read
        self._kind = None
        self._stop = threading.Event()
        self.state = self._load()
        self._after_install()

    # State ---------------------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            with open(os.path.join(updates_dir(), "state.json"), encoding="utf-8") as fh:
                state = json.load(fh)
                return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        path = os.path.join(updates_dir(), "state.json")
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, indent=1)
        for _ in range(25):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:   # Windows: another copy of the app reading it at that moment
                time.sleep(0.02)
        os.replace(tmp, path)

    def kind(self) -> str:
        if self._kind is None:
            self._kind = install_kind()
        return self._kind

    def mode(self) -> str:
        m = self._prefs().get("updates", "auto")
        return m if m in ("auto", "ask", "off") else "auto"

    def channel(self) -> str:
        return "test" if self._prefs().get("update_channel") == "test" else "stable"

    def _after_install(self) -> None:
        """At start: how the last install went, for What's new or the reason it failed."""
        with self.lock:
            inst = self.state.get("installing")
            staged = self.state.get("staged")
            if staged and not inst and not staged.get("go_back") and \
                    parse_version(staged["version"]) <= parse_version(self.version):
                self.state["staged"] = None   # this version or a newer one came in another way
                self._tidy()
                self._save()
            failed = self.state.get("failed")
            if failed and not inst and parse_version(failed["version"]) <= parse_version(self.version):
                self.state["failed"] = None   # (installed since, by hand)
                self._save()
            if not inst or install_running():
                return
            result = _read(os.path.join(updates_dir(), RESULT))
            version = inst["version"]
            if result.startswith("ok") and parse_version(self.version) == parse_version(version):
                self.state.update(updated={k: inst.get(k) for k in ("version", "from", "notes", "go_back")},
                                  staged=None, failed=None)
                self.state.get("tries", {}).pop(version, None)
                self._tidy()
            else:
                why = (result.partition(":")[2].strip() if result.startswith("failed") else
                       f"it installed, but this {cfg['app']} is still {self.version}" if result.startswith("ok") else
                       "the installer stopped before it finished")
                self.state["failed"] = {"version": version, "error": why or "the installer stopped", "at": time.time()}
                tries = self.state.setdefault("tries", {})
                tries[version] = tries.get(version, 0) + 1
            self.state["installing"] = None
            _remove(os.path.join(updates_dir(), RESULT))
            self._save()

    def _tidy(self) -> None:
        """Downloads and unpacked versions other than the one waiting to install aren't needed."""
        if install_running():
            return   # (an installer is running from one of them)
        staged = self.state.get("staged")
        keep = {os.path.realpath(os.path.dirname(staged["dir"]))} if staged else set()
        zips = {staged.get("zip")} if staged else set()
        versions = os.path.join(updates_dir(), "versions")
        for name in os.listdir(versions) if os.path.isdir(versions) else []:
            if os.path.realpath(os.path.join(versions, name)) not in keep:
                _remove(os.path.join(versions, name))
        downloads = os.path.join(updates_dir(), "downloads")
        for name in os.listdir(downloads) if os.path.isdir(downloads) else []:
            if os.path.join(downloads, name) not in zips:
                _remove(os.path.join(downloads, name))

    # What the editor shows -------------------------------------------------------------------

    def status(self) -> dict:
        def brief(r):
            return {k: r.get(k) for k in ("version", "prerelease", "notes", "published")} if r else None
        with self.lock:
            st = self.state
            staged = st.get("staged")
            creds = self._load_creds()
            out = {
                "kind": self.kind(), "mode": self.mode(), "channel": self.channel(), "version": self.version,
                "busy": self.busy, "progress": self.progress, "error": self.error, "access": self.access,
                "configured": bool(settings().get("github_app_client_id")), "owner": settings().get("owner"),
                "signed_in": (creds.get("login") or "GitHub") if creds else None,
                "checked": st.get("checked"), "newest": brief(st.get("newest")), "update": brief(st.get("update")),
                "previous": brief(st.get("previous")), "skip": st.get("skip"),
                "staged": {**brief(staged), "env_changed": staged.get("env_changed"), "approved": staged.get("approved"),
                           "go_back": staged.get("go_back")} if staged else None,
                "updated": st.get("updated"), "failed": st.get("failed"), "installing": bool(install_running()),
                "restarting": self.restart,
                "tries": (st.get("tries") or {}).get(staged["version"], 0) if staged else 0, "max_tries": MAX_TRIES,
                "signin": {k: v for k, v in self.signin.items() if k != "device_code"} if self.signin else None,
                "log": os.path.join(updates_dir(), LOG) if os.path.exists(os.path.join(updates_dir(), LOG)) else None,
            }
            if self.fake:
                out.update(self.fake)
            return out

    # Looking and downloading -----------------------------------------------------------------

    def start(self) -> None:
        """Look shortly after starting, then every few hours, in the background."""
        def loop():
            if self._stop.wait(FIRST_LOOK):
                return
            while True:
                try:
                    self.check()
                except Exception as exc:   # noqa: BLE001 (looks again later)
                    self.error = str(exc)
                if self._stop.wait(CHECK_EVERY):
                    return
        threading.Thread(target=loop, name=f"{cfg['app']}-updates", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def check(self, manual: bool = False) -> dict:
        """Look for a newer version; with automatic updates, download it too. `manual`: Check now,
        which looks even with updates switched off."""
        if self.kind() != "installed" or self.fake or (self.mode() == "off" and not manual):
            return self.status()
        if not self.work.acquire(blocking=False):
            return self.status()   # already looking or downloading
        try:
            self.busy, self.error = "checking", None
            info = settings()
            listed = self._get(f"/repos/{info['owner']}/{info['repo']}/releases?per_page=50")
            releases = [r for r in (release_view(x) for x in listed if isinstance(x, dict)) if r]
            newest, update, previous = pick(releases, self.channel(), self.version, self.state.get("skip"))
            with self.lock:
                self.state.update(checked=time.time(), newest=newest, update=update, previous=previous)
                staged = self.state.get("staged")
                if staged and not (staged.get("approved") or staged.get("go_back")) and \
                        (not update or update["version"] != staged["version"]):
                    self.state["staged"] = None   # no longer the one to take (skipped, or test versions switched off)
                    self._tidy()
                self._save()
            staged = self.state.get("staged")
            if update and (self.mode() == "auto" or (staged and staged.get("approved"))):
                self._download(update)
        except _NeedsSignIn:
            pass   # self.access says which
        except UpdateError as exc:
            self.error = str(exc)
        finally:
            self.busy, self.progress = None, None
            self.work.release()
        return self.status()

    def get(self, which: str = "update") -> dict:
        """Download the update (Update now) or the version before (Go back), to install at once."""
        release = self.state.get(which)
        if not release:
            raise UpdateError("there's no newer version to install" if which == "update" else
                              "there's no earlier version to go back to")
        if not self.work.acquire(timeout=120):
            raise UpdateError(f"{cfg['app']} is busy with another download; try again in a moment")
        try:
            staged = self._download(release, go_back=which == "previous", approved=True)
            if which == "previous":
                with self.lock:
                    self.state["skip"] = self.version   # so it doesn't come straight back to this one
                    self._save()
            return staged
        finally:
            self.busy, self.progress = None, None
            self.work.release()

    def _download(self, release: dict, go_back: bool = False, approved: bool = False) -> dict:
        staged = self.state.get("staged")
        if staged and staged["version"] == release["version"] and os.path.isfile(os.path.join(staged["dir"], INSTALLER)):
            with self.lock:
                staged["approved"] = staged.get("approved") or approved
                staged["go_back"] = go_back
                self._save()
            return staged
        self.busy, self.progress = "downloading", 0.0
        signed = _json(self._fetch(release, MANIFEST, limit=1 << 20))
        manifest = verify_manifest(signed)
        if parse_version(manifest["version"]) != parse_version(release["version"]):
            raise UpdateError("the release's signed version isn't the one it's named as")
        z = manifest.get("zip") or {}
        name = str(z.get("name") or "")
        if not name or name != os.path.basename(name) or name not in release["assets"]:
            raise UpdateError("the release's ZIP is missing")
        if not isinstance(z.get("size"), int) or len(str(z.get("sha256") or "")) != 64:
            raise UpdateError("the release's description doesn't say how to check its ZIP")
        folder = os.path.join(updates_dir(), "downloads")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        self._fetch(release, name, path, size=z.get("size"), sha256=z.get("sha256"))
        top = extract(path, os.path.join(updates_dir(), "versions", manifest["version"]))
        staged = {"version": manifest["version"], "tag": release["tag"], "prerelease": release["prerelease"],
                  "notes": release.get("notes") or manifest.get("notes") or "", "published": release.get("published"),
                  "dir": top, "zip": path,
                  "env_changed": (manifest.get("environment_sha256") or "").lower() != (_installed_file("environment.sha256") or "").lower(),
                  "go_back": go_back, "approved": approved}
        with self.lock:
            self.state["staged"] = staged
            self.state["failed"] = None
            self._tidy()
            self._save()
        return staged

    def _fetch(self, release: dict, name: str, dest: str | None = None, size: int | None = None,
               sha256: str | None = None, limit: int | None = None):
        """A release's file: through GitHub's API with the sign-in, or from its download link
        for a public repository. With `dest`, saved there once its size and SHA-256 match."""
        asset = release["assets"][name]
        token = self._token()
        url = asset["url"] if token or not asset.get("download") else asset["download"]
        status, headers, resp = http(url, token, accept="application/octet-stream", stream=True, timeout=60)
        if status != 200:
            raise UpdateError(f"GitHub didn't hand over {name} ({status})")
        digest, got, chunks = hashlib.sha256(), 0, []
        out = open(dest + ".part", "wb") if dest else None
        try:
            with resp:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    got += len(chunk)
                    if (size and got > size) or (limit and got > limit):
                        raise UpdateError(f"{name} is bigger than the release says")
                    digest.update(chunk)
                    if out:
                        out.write(chunk)
                    else:
                        chunks.append(chunk)
                    if size:
                        self.progress = got / size
        except OSError as exc:
            raise UpdateError(f"the download of {name} broke off ({exc})") from None
        finally:
            if out:
                out.close()
        if not dest:
            return b"".join(chunks)
        if (size is not None and got != size) or (sha256 and digest.hexdigest() != sha256):
            _remove(dest + ".part")
            raise UpdateError(f"{name} doesn't match the signed release (it may be damaged)")
        os.replace(dest + ".part", dest)
        return dest

    def _get(self, path: str):
        """JSON from GitHub's API: with the sign-in (refreshed if it ran out), or without one for a
        public repository. A private one without a sign-in is _NeedsSignIn (self.access says so)."""
        token = self._token()
        status, headers, body = http(api_base() + path, token)
        if status == 401 and token:
            token = self._token(refresh=True)
            status, headers, body = http(api_base() + path, token)
            if status == 401:   # the sign-in was withdrawn: try without (a public repository)
                self.signout()
                token = None
                status, headers, body = http(api_base() + path)
        if status == 200:
            self.access = "signed_in" if token else "public"
            return _json(body)
        if status == 404:
            self.access = "no_access" if token else "sign_in"
            raise _NeedsSignIn()
        if status in (403, 429) and (headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After")):
            raise UpdateError(f"GitHub asks {cfg['app']} to wait before looking again; it will look later")
        raise UpdateError(f"GitHub answered {status} ({(_json(body) or {}).get('message', 'no reason given')})")

    # Installing ------------------------------------------------------------------------------

    def restart_now(self) -> bool:
        """Restart now: install the downloaded update as the app closes, then open it again."""
        with self.lock:
            if self.fake:
                self.restart = True
                return True
            staged = self.state.get("staged")
            if not staged or self.kind() != "installed":
                return False
            staged["approved"] = True
            self.restart = True
            self._save()
            return True

    def skip(self, version: str | None) -> dict:
        """Skip this version (None: stop skipping): it isn't installed by itself, a newer one is."""
        with self.lock:
            self.state["skip"] = version
            staged = self.state.get("staged")
            if version and staged and parse_version(staged["version"]) <= parse_version(version) and not staged.get("go_back"):
                self.state["staged"] = None
                self._tidy()
            if self.state.get("failed") and version and self.state["failed"]["version"] == version:
                self.state["failed"] = None
            self._save()
        return self.status()

    def seen(self) -> dict:
        """What's new was read."""
        with self.lock:
            self.state["updated"] = None
            self._save()
        return self.status()

    def register(self) -> None:
        """This the app is open (the last one to close installs an update)."""
        folder = os.path.join(updates_dir(), "running")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, str(os.getpid())), "w") as fh:
            fh.write(str(time.time()))

    def _others_open(self) -> bool:
        folder = os.path.join(updates_dir(), "running")
        others = False
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            if name.isdigit() and int(name) != os.getpid() and pid_alive(int(name)):
                others = True
            elif name.isdigit() and int(name) != os.getpid():
                _remove(os.path.join(folder, name))
        return others

    def on_quit(self) -> bool:
        """The app is closing: install the downloaded update now if it should. Always after
        Restart now, Update now or Go back; by itself with automatic updates (until it has failed
        twice); never while another the app is open (the last to close installs it)."""
        _remove(os.path.join(updates_dir(), "running", str(os.getpid())))
        with self.lock:
            staged = self.state.get("staged")
            if self.fake or not staged or self.kind() != "installed":
                return False
            asked = self.restart or staged.get("approved") or staged.get("go_back")
            tries = (self.state.get("tries") or {}).get(staged["version"], 0)
            if not (asked or (self.mode() == "auto" and tries < MAX_TRIES)) or self._others_open():
                return False
            return self.launch(staged, reopen=self.restart)

    def launch(self, staged: dict, reopen: bool = False) -> bool:
        """Start the update's installer, which waits for this the app to close, installs into
        this environment, and (with `reopen`) opens the app again."""
        script = os.path.join(staged["dir"], INSTALLER or "")
        if not INSTALLER or not os.path.isfile(script):
            self.state["staged"] = None
            self._save()
            return False
        folder = updates_dir()
        _remove(os.path.join(folder, RESULT))
        env = dict(os.environ)
        env.update({_env("UPDATE"): "1", _env("PREFIX"): sys.prefix, _env("WAIT_PID"): str(os.getpid()),
                    _env("RESULT"): os.path.join(folder, RESULT), _env("LOCK"): os.path.join(folder, LOCK)})
        env.pop(_env("NO_OPEN"), None)
        if not reopen:
            env[_env("NO_OPEN")] = "1"
        log = open(os.path.join(folder, LOG), "w", encoding="utf-8")
        try:
            if sys.platform == "darwin":
                if mac_app_dir():
                    env[_env("APP_DIR")] = mac_app_dir()
                proc = subprocess.Popen(["/bin/bash", script], cwd=staged["dir"], env=env, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            else:
                # Windows PowerShell finds its own modules (a PowerShell 7 that started the app
                # would pass on its module path, and then Windows PowerShell's cmdlets don't load)
                env.pop("PSModulePath", None)
                cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", script]
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                try:   # out of any job the app runs in, so closing it doesn't end the installer
                    proc = subprocess.Popen(cmd, cwd=staged["dir"], env=env, stdin=subprocess.DEVNULL, stdout=log,
                                            stderr=subprocess.STDOUT, creationflags=flags | 0x01000000)
                except OSError:
                    proc = subprocess.Popen(cmd, cwd=staged["dir"], env=env, stdin=subprocess.DEVNULL, stdout=log,
                                            stderr=subprocess.STDOUT, creationflags=flags)
        finally:
            log.close()
        with open(os.path.join(folder, LOCK), "w", encoding="utf-8") as fh:
            json.dump({"pid": proc.pid, "version": staged["version"], "started": time.time()}, fh)
        with self.lock:
            self.state["installing"] = {"version": staged["version"], "from": self.version, "notes": staged.get("notes", ""),
                                        "go_back": bool(staged.get("go_back")), "started": time.time()}
            self._save()
        return True

    # Signing in to GitHub (while the repository is private) ----------------------------------

    def _load_creds(self) -> dict | None:
        if self._creds is ...:
            try:
                text = self.keystore.get()
                if not text and cfg["old_signin"]:   # signed in under the app's earlier name: kept under the new one too
                    text = Keystore(*cfg["old_signin"]).get()
                    if text:
                        self.keystore.set(text)
                self._creds = _json((text or "").encode("utf-8")) or None
            except Exception:   # noqa: BLE001 (no keychain to ask: not signed in)
                self._creds = None
        return self._creds

    def _keep_creds(self, data: dict, login: str | None = None) -> dict:
        now = time.time()
        creds = {"access_token": data["access_token"], "login": login}
        if data.get("expires_in"):
            creds["expires_at"] = now + int(data["expires_in"]) - 120
        if data.get("refresh_token"):
            creds["refresh_token"] = data["refresh_token"]
            creds["refresh_expires_at"] = now + int(data.get("refresh_token_expires_in") or 15897600) - 120
        if not login:
            status, _, body = http(f"{api_base()}/user", creds["access_token"])
            creds["login"] = (_json(body) or {}).get("login") if status == 200 else None
        self.keystore.set(json.dumps(creds))
        self._creds = creds
        return creds

    def _token(self, refresh: bool = False) -> str | None:
        """The sign-in's token, renewed with its refresh token once it has run out (8 hours)."""
        with self.token_lock:
            creds = self._load_creds()
            if not creds:
                return None
            if not refresh and time.time() < creds.get("expires_at", float("inf")):
                return creds["access_token"]
            if creds.get("refresh_token") and time.time() < creds.get("refresh_expires_at", 0):
                status, _, body = http(f"{web_base()}/login/oauth/access_token", accept="application/json",
                                       form={"client_id": settings().get("github_app_client_id", ""),
                                             "grant_type": "refresh_token", "refresh_token": creds["refresh_token"]})
                data = _json(body) if status == 200 else {}
                if isinstance(data, dict) and data.get("access_token"):
                    return self._keep_creds(data, creds.get("login"))["access_token"]
            if refresh or creds.get("expires_at"):
                self.signout()
                return None
            return creds["access_token"]

    def signin_start(self) -> dict:
        """Ask GitHub for a code to sign in with (its device flow): the person enters it on GitHub."""
        if self.fake is not None:   # the editor self-test: a code, without asking GitHub
            self.signin = {"user_code": "WDJB-MJHT", "uri": "https://github.com/login/device", "state": "waiting",
                           "error": None, "login": None, "expires": time.time() + 900, "interval": 5}
            return dict(self.signin)
        client = settings().get("github_app_client_id")
        if not client:
            raise UpdateError(f"signing in isn't set up yet (the {cfg['app']} updates app has no client ID)")
        status, _, body = http(f"{web_base()}/login/device/code", accept="application/json", form={"client_id": client})
        data = _json(body) if status == 200 else {}
        if not isinstance(data, dict) or not data.get("device_code"):
            raise UpdateError(f"GitHub didn't start the sign-in ({(data or {}).get('error_description') or status})")
        s = {"user_code": data["user_code"], "uri": data.get("verification_uri") or "https://github.com/login/device",
             "device_code": data["device_code"], "expires": time.time() + float(data.get("expires_in") or 900),
             "interval": float(data.get("interval") or 5), "state": "waiting", "error": None, "login": None}
        self.signin = s
        threading.Thread(target=self._signin_wait, args=(s, client), name=f"{cfg['app']}-signin", daemon=True).start()
        return {k: v for k, v in s.items() if k != "device_code"}

    def _signin_wait(self, s: dict, client: str) -> None:
        while self.signin is s and s["state"] == "waiting":
            time.sleep(s["interval"])
            if self.signin is not s:
                return
            if time.time() > s["expires"]:
                s["state"] = "expired"
                break
            try:
                status, _, body = http(f"{web_base()}/login/oauth/access_token", accept="application/json",
                                       form={"client_id": client, "device_code": s["device_code"],
                                             "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            except UpdateError:
                continue   # a moment without a connection: ask again
            data = _json(body)
            data = data if isinstance(data, dict) else {}
            err = data.get("error")
            if data.get("access_token"):
                try:
                    s["login"] = self._keep_creds(data).get("login")
                    s["state"] = "done"
                except (OSError, UpdateError) as exc:
                    s["state"], s["error"] = "error", f"the sign-in couldn't be kept ({exc})"
            elif err == "authorization_pending":
                continue
            elif err == "slow_down":
                s["interval"] = float(data.get("interval") or s["interval"] + 5)
            else:
                s["state"] = {"expired_token": "expired", "token_expired": "expired", "access_denied": "denied"}.get(err, "error")
                s["error"] = data.get("error_description") or err or f"GitHub answered {status}"
        if s["state"] == "done":
            self.check(manual=True)

    def signin_cancel(self) -> None:
        self.signin = None

    def signout(self) -> None:
        """Forget the GitHub sign-in on this computer (one kept under the app's earlier name too)."""
        for store in (self.keystore, *([Keystore(*cfg["old_signin"])] if cfg["old_signin"] else [])):
            try:
                store.delete()
            except Exception:   # noqa: BLE001 (nothing was kept)
                pass
        self._creds = None
        if self.access == "signed_in":
            self.access = None


class _NeedsSignIn(Exception):
    pass


def cli(args) -> int:
    """The app update: look for an update and say what there is; with --install (or
    --go-back) download it and start its installer, which waits for this command to finish.
    For testing the whole path, and for anyone who'd rather update from a terminal."""
    prefs = dict(cfg["prefs"]())
    if args.test:
        prefs["update_channel"] = "test"
    up = Updater(lambda: prefs)
    if up.kind() != "installed":
        print(f"This {cfg['app']} can't update itself ({up.kind()}: install it with the installer first).")
        return 1
    st = up.check(manual=True)
    print(f"{cfg['app']} {st['version']}; newest {(st['newest'] or {}).get('version', 'unknown')}"
          + (f"; update {st['update']['version']}" if st["update"] else "")
          + (f"; before it {st['previous']['version']}" if st["previous"] else "")
          + (f"; skipping {st['skip']}" if st["skip"] else ""))
    if st["error"] or st["access"] in ("sign_in", "no_access"):
        print(f"Couldn't look: {st['error'] or st['access']}", file=sys.stderr)
        return 1
    which = "previous" if args.go_back else "update" if args.install else None
    if not which:
        return 0
    if not st["update" if which == "update" else "previous"]:
        print("Nothing to install.")
        return 0
    staged = up.get(which)
    up.launch(staged, reopen=False)
    print(f"Installing {staged['version']}; the installer's log: {os.path.join(updates_dir(), LOG)}")
    print(f"It writes {os.path.join(updates_dir(), RESULT)} when it's done.")
    return 0

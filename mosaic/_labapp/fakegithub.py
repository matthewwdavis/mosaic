"""A stand-in for the parts of GitHub that the apps' releases and updates use, for the tests and CI:
the repository and its releases (private, or public), release files through the API (redirected,
like GitHub, to another host that refuses a sign-in, like Amazon S3), the download links of a
public repository (a release's, and releases/latest/download/<name>, which the README's download
button and install.sh/install.ps1 use), and signing in with a code (the device flow) and
refreshing the sign-in.

An app's tools/fake_github.py says which repository it stands in for and calls main():

    python tools/fake_github.py serve FOLDER [--private] [--token TOKEN] [--port-file FILE]

FOLDER holds releases.json (add_release writes it) and the release files. In the tests:

    with FakeGitHub(folder, private=True, owner="matthewwdavis", repo="prose") as gh:
        os.environ["PROSE_UPDATE_API"] = gh.api ...

(mosaic still has its own copy of this, from before it was shared: mosaic/tools/fake_github.py.)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def add_release(folder: str, tag: str, files: list[str], prerelease: bool = False, body: str = "",
                draft: bool = False) -> None:
    """Put a release in FOLDER: its files copied in, and listed in releases.json (newest first)."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "releases.json")
    releases = json.load(open(path)) if os.path.exists(path) else []
    next_id = 1 + max([a["id"] for r in releases for a in r["assets"]] + [0])
    assets = []
    for i, f in enumerate(files):
        name = os.path.basename(f)
        stored = os.path.join(folder, f"{next_id + i}-{name}")
        shutil.copyfile(f, stored)
        assets.append({"id": next_id + i, "name": name, "file": os.path.basename(stored), "size": os.path.getsize(stored)})
    releases.insert(0, {"tag_name": tag, "prerelease": prerelease, "draft": draft, "body": body,
                        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "assets": assets})
    with open(path, "w") as fh:
        json.dump(releases, fh, indent=1)


class _Objects(BaseHTTPRequestHandler):
    """The host release files are redirected to: like S3, it refuses a request carrying a sign-in."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        fake = self.server.fake
        fake.seen.append(("objects", self.path, self.headers.get("Authorization")))
        if self.headers.get("Authorization"):
            return self._send(400, b"Only one auth mechanism allowed")
        name = urlsplit(self.path).path.rsplit("/", 1)[-1]
        path = os.path.join(fake.folder, name)
        if not os.path.isfile(path):
            return self._send(404, b"not found")
        with open(path, "rb") as fh:
            self._send(200, fh.read(), "application/octet-stream")

    def _send(self, code, body, ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _GitHub(_Objects):
    """api.github.com and github.com in one."""

    def _json(self, code, obj, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _token(self):
        auth = self.headers.get("Authorization") or ""
        return auth[7:] if auth.startswith("Bearer ") else None

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        fake = self.server.fake
        url = urlsplit(self.path)
        token = self._token()
        fake.seen.append(("api", self.path, token))
        if token and token not in fake.tokens:
            return self._json(401, {"message": "Bad credentials"})
        allowed = not fake.private or token in fake.tokens
        owner, repo_name = fake.owner, fake.repo
        repo = f"/repos/{owner}/{repo_name}"
        if url.path == "/user":
            return self._json(200, {"login": "early-adopter"}) if token else self._json(401, {"message": "Requires authentication"})
        if url.path == repo:
            return self._json(200, {"private": fake.private}) if allowed else self._json(404, {"message": "Not Found"})
        if url.path == f"{repo}/releases":
            if not allowed:
                return self._json(404, {"message": "Not Found"})
            return self._json(200, [self._release(r) for r in fake.releases()])
        if url.path.startswith(f"{repo}/releases/assets/"):
            if not allowed:
                return self._json(404, {"message": "Not Found"})
            asset = fake.asset(int(url.path.rsplit("/", 1)[-1]))
            if not asset:
                return self._json(404, {"message": "Not Found"})
            if self.headers.get("Accept") != "application/octet-stream":
                return self._json(200, {"id": asset["id"], "name": asset["name"], "size": asset["size"]})
            return self._redirect(f"{fake.objects}/assets/{asset['file']}?signature=fake")
        if url.path.startswith(f"/{owner}/{repo_name}/releases/latest/download/"):
            # The newest full release (not a draft or a test version), as GitHub's "latest": a redirect
            # to that release's own download link, which redirects again to the file host
            if fake.private:
                return self._json(404, {"message": "Not Found"})
            name = url.path.rsplit("/", 1)[-1]
            rel = fake.latest()
            if not rel or not any(a["name"] == name for a in rel["assets"]):
                return self._json(404, {"message": "Not Found"})
            return self._redirect(f"{fake.web}/{owner}/{repo_name}/releases/download/{rel['tag_name']}/{name}")
        if url.path.startswith(f"/{owner}/{repo_name}/releases/download/"):   # a public repository's download links
            if fake.private:
                return self._json(404, {"message": "Not Found"})
            tag, name = url.path.split("/")[-2:]
            rel = next((r for r in fake.releases() if r["tag_name"] == tag), None)
            asset = next((a for a in (rel or {}).get("assets", []) if a["name"] == name), None)
            if not asset:
                return self._json(404, {"message": "Not Found"})
            return self._redirect(f"{fake.objects}/assets/{asset['file']}?signature=fake")
        return self._json(404, {"message": "Not Found"})

    def _release(self, r):
        fake = self.server.fake
        repo = f"{fake.api}/repos/{fake.owner}/{fake.repo}"
        return {**{k: r[k] for k in ("tag_name", "prerelease", "draft", "body", "published_at")},
                "assets": [{"id": a["id"], "name": a["name"], "size": a["size"], "url": f"{repo}/releases/assets/{a['id']}",
                            "browser_download_url": f"{fake.web}/{fake.owner}/{fake.repo}/releases/download/{r['tag_name']}/{a['name']}"}
                           for a in r["assets"]]}

    def do_POST(self):
        fake = self.server.fake
        length = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
        fake.seen.append(("web", self.path, form))
        path = urlsplit(self.path).path
        if path == "/login/device/code":
            if form.get("client_id") != fake.client_id:
                return self._json(200, {"error": "incorrect_client_credentials"})
            fake.polls = 0
            return self._json(200, {"device_code": "device-1", "user_code": "WDJB-MJHT",
                                    "verification_uri": f"{fake.web}/login/device", "expires_in": 900,
                                    "interval": fake.interval})
        if path == "/login/oauth/access_token":
            if form.get("grant_type") == "refresh_token":
                if form.get("refresh_token") not in fake.refresh_tokens:
                    return self._json(200, {"error": "bad_refresh_token"})
                fake.refresh_tokens.discard(form["refresh_token"])   # each is used once, as GitHub's are
                return self._json(200, fake.issue())
            fake.polls += 1
            if fake.deny:
                return self._json(200, {"error": "access_denied", "error_description": "The user cancelled"})
            if fake.polls <= fake.pending:
                return self._json(200, {"error": "authorization_pending"})
            return self._json(200, fake.issue())
        return self._json(404, {"message": "Not Found"})


class FakeGitHub:
    def __init__(self, folder: str, private: bool = True, tokens=(), client_id: str = "Iv1.test",
                 interval: float = 0.05, pending: int = 2, expires: int | None = 28800,
                 owner: str = "matthewwdavis", repo: str = "app"):
        self.folder, self.private, self.client_id = folder, private, client_id
        self.owner, self.repo = owner, repo
        self.tokens, self.refresh_tokens = set(tokens), set()
        self.interval, self.pending, self.expires = interval, pending, expires
        self.polls, self.deny, self.issued, self.seen = 0, False, 0, []

    def releases(self) -> list[dict]:
        path = os.path.join(self.folder, "releases.json")
        return json.load(open(path)) if os.path.exists(path) else []

    def latest(self) -> dict | None:
        """GitHub's latest release: the newest that is neither a draft nor a test version (pre-release)."""
        return next((r for r in self.releases() if not r.get("draft") and not r.get("prerelease")), None)

    def asset(self, aid: int) -> dict | None:
        return next((a for r in self.releases() for a in r["assets"] if a["id"] == aid), None)

    def issue(self) -> dict:
        self.issued += 1
        token, refresh = f"ghu_fake{self.issued}", f"ghr_fake{self.issued}"
        self.tokens.add(token)
        out = {"access_token": token, "token_type": "bearer", "scope": ""}
        if self.expires:
            self.refresh_tokens.add(refresh)
            out.update(expires_in=self.expires, refresh_token=refresh, refresh_token_expires_in=15897600)
        return out

    def start(self) -> "FakeGitHub":
        self._web = ThreadingHTTPServer(("127.0.0.1", 0), _GitHub)
        self._obj = ThreadingHTTPServer(("127.0.0.1", 0), _Objects)
        for srv in (self._web, self._obj):
            srv.fake = self
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.api = self.web = f"http://127.0.0.1:{self._web.server_address[1]}"
        self.objects = f"http://localhost:{self._obj.server_address[1]}"   # another host name, as S3 is
        return self

    def stop(self) -> None:
        for srv in (self._web, self._obj):
            srv.shutdown()
            srv.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def main(owner: str, repo: str, argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"A stand-in for GitHub's {owner}/{repo}, for tests")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("folder")
    s.add_argument("--private", action="store_true")
    s.add_argument("--token", action="append", default=[])
    s.add_argument("--port-file", help="write the API's address here once it's listening")
    args = ap.parse_args(argv)
    fake = FakeGitHub(os.path.abspath(args.folder), private=args.private, tokens=args.token, owner=owner, repo=repo).start()
    print(f"fake GitHub at {fake.api} (files from {fake.objects})", flush=True)
    if args.port_file:
        with open(args.port_file + ".tmp", "w") as fh:
            fh.write(fake.api)
        os.replace(args.port_file + ".tmp", args.port_file)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0

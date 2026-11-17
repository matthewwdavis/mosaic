"""A stand-in for GitHub's tool gh, for tests: answers `gh api` from a table and records every call,
so nothing reaches the network or GitHub.

    path = fakegh.make(folder, {"GET user": {"login": "alice"},
                                "POST repos/o/r/pulls": {"html_url": "https://github.com/o/r/pull/7"},
                                "GET repos/o/r/contents/journals/x.json": 404})
    os.environ["LABAPP_GH"] = path        # journallibrary.gh_path() uses it
    ...
    fakegh.calls(folder)  ->  [{"method": "GET", "path": "user", "body": None}, ...]

A key is "METHOD path" (the path as gh api is given it, query and all); a value is the JSON to
answer, or a number for an HTTP error (404, 403...). A call with no answer is a 404.
"""
from __future__ import annotations

import json
import os
import sys

_SCRIPT = r'''#!{python}
import json, sys
folder = {folder!r}
args = sys.argv[1:]
method, path, body = "GET", None, None
if not args or args[0] != "api":
    print("fake gh: only `gh api` is answered", file=sys.stderr); sys.exit(2)
rest = args[1:]
i = 0
while i < len(rest):
    a = rest[i]
    if a in ("--method", "-X"):
        method = rest[i + 1]; i += 2; continue
    if a == "--input":
        body = sys.stdin.read(); i += 2; continue
    if a.startswith("-"):
        i += 2 if a in ("-H", "--header", "-f", "-F", "--jq", "-q") else 1; continue
    path = a; i += 1
with open(folder + "/answers.json", encoding="utf-8") as fh:
    answers = json.load(fh)
try:
    parsed = json.loads(body) if body else None
except ValueError:
    parsed = body
with open(folder + "/calls.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({{"method": method, "path": path, "body": parsed}}) + "\n")
got = answers.get(method + " " + path, 404)
if isinstance(got, int):
    print("gh: HTTP %d: %s (https://api.github.com/%s)" % (got, {{404: "Not Found", 403: "Forbidden", 401: "Bad credentials"}}.get(got, "Error"), path), file=sys.stderr)
    sys.exit(1)
print(json.dumps(got))
'''


def make(folder: str, answers: dict) -> str:
    """Write the fake gh into folder with its answers; its path."""
    os.makedirs(folder, exist_ok=True)
    answer(folder, answers)
    script = os.path.join(folder, "gh")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(_SCRIPT.format(python=sys.executable, folder=os.path.abspath(folder)))
    os.chmod(script, 0o755)
    open(os.path.join(folder, "calls.jsonl"), "w").close()
    return script


def answer(folder: str, answers: dict) -> None:
    """Change the fake gh's answers."""
    with open(os.path.join(folder, "answers.json"), "w", encoding="utf-8") as fh:
        json.dump(answers, fh)


def calls(folder: str) -> list[dict]:
    """Every call made so far: [{"method", "path", "body"}]."""
    try:
        with open(os.path.join(folder, "calls.jsonl"), encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except OSError:
        return []

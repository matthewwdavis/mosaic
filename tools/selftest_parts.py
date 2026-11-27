#!/usr/bin/env python3
"""Each part of the editor's self-test (selftest.js: ?only=<part>) run on its own, in a mosaic of its
own (a fresh MOSAIC_HOME each time) in its real window, to find the parts that pass only after others
have run: a part that needs a document, a setting or a file another part left has to make it itself
(prose's checks, 27 Nov 2026: 31 passed only after others, and looked like breakages that weren't).

    python tools/selftest_parts.py                   # every part (about 45 launches)
    python tools/selftest_parts.py --only tips crops # these parts
    python tools/selftest_parts.py --out parts.json  # where the results go (and are taken up again from)

Results go to a JSON file as each part finishes ({part: {ok, failed: [names], detail, seconds}}), so a run
stopped part-way goes on from where it was (--again runs them all again); a summary is printed and
written beside it (.md). On a Mac (the parts' real window is WebKit's); run from the project folder."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELFTEST = os.path.join(ROOT, "mosaic", "ui", "js", "selftest.js")


def part_names(path: str = SELFTEST) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return list(dict.fromkeys(re.findall(r'params\.get\("only"\) === "([a-z]+)"', fh.read())))


def files(tmp: str) -> list[str]:
    """The figure files and PowerPoint's the self-test places (as tests/test_ui.py gives them)"""
    ppt = os.path.join(ROOT, "tests", "data", "powerpoint")
    deck = os.path.join(ppt, "example_deck.pptx")
    other = shutil.copy(deck, os.path.join(tmp, "other_deck.pptx"))
    return [os.path.join(ROOT, "examples", "dose_response.svg"), os.path.join(ROOT, "examples", "dose_response.pdf"), deck, other,
            os.path.join(ppt, "copied_slide.slides"), os.path.join(ppt, "copied_rect.gvml")]


def run_one(part: str, limit: int = 600) -> dict:
    started = time.monotonic()
    tmp = tempfile.mkdtemp(prefix="mosaic-part-")
    try:
        env = {**os.environ, "PYTHONPATH": ROOT, "MOSAIC_HOME": os.path.join(tmp, "home"), "MOSAIC_NO_UPDATES": "1", "MOSAIC_SMOKETEST": "1",
               "MOSAIC_SMOKE_QUERY": f"selftest=1&only={part}&files={','.join(files(tmp))}&out={os.path.join(tmp, 'out')}"}
        try:
            out = subprocess.run([sys.executable, "-m", "mosaic"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=limit).stdout
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        line = next((ln for ln in out.splitlines() if ln.startswith("SELFTEST {")), None)
        if not line:
            return {"ok": False, "failed": [], "detail": "didn't finish: " + " | ".join(out.splitlines()[-4:])[-400:], "seconds": round(time.monotonic() - started)}
        res = json.loads(line[len("SELFTEST "):])
        failed = [r for r in res.get("results") or [] if not r.get("ok")]
        n = len(res.get("results") or [])
        return {"ok": not failed and n > 1, "checks": n, "failed": [r.get("name", "?") for r in failed],
                "detail": "; ".join(f"{r.get('name', '?')}: {str(r.get('detail') or r.get('error') or '')[:200]}" for r in failed[:4]) or ("" if n > 1 else "no checks ran"),
                "seconds": round(time.monotonic() - started)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    if sys.platform != "darwin":
        print("a Mac only: the parts run in WebKit's real window")
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", default=os.path.join(ROOT, "selftest-parts.json"))
    ap.add_argument("--again", action="store_true")
    ap.add_argument("--limit", type=int, default=600, help="seconds a part may take")
    args = ap.parse_args()
    parts = [p for p in part_names() if not args.only or p in args.only]
    results = {}
    if os.path.exists(args.out) and not args.again:
        with open(args.out, encoding="utf-8") as fh:
            results = json.load(fh)
    todo = [p for p in parts if p not in results]
    print(f"{len(parts)} parts, {len(todo)} to run", flush=True)
    for k, part in enumerate(todo, 1):
        r = run_one(part, args.limit)
        results[part] = r
        with open(args.out + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=1, ensure_ascii=False)
        os.replace(args.out + ".tmp", args.out)
        print(f"[{k}/{len(todo)}] {'ok  ' if r['ok'] else 'FAIL'} {r['seconds']:4d} s  {part} ({r.get('checks', 0)} checks)", flush=True)
    bad = [p for p in parts if p in results and not results[p]["ok"]]
    text = "\n".join([f"# mosaic self-test parts run alone", "", f"{len(parts)} parts; {len(parts) - len(bad)} passed alone, {len(bad)} failed alone.", ""]
                     + [f"- **{p}**: {results[p]['detail']}" for p in bad]) + "\n"
    with open(os.path.splitext(args.out)[0] + ".md", "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())

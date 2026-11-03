"""Run the editor's scripted self-test in headless Chrome and report the results.

    python tools/ui_selftest.py FILE.svg [FILE2.pdf ...] [DECK.pptx ...] [--chrome PATH] [--shot out.png] [--only objects]

Starts the server, opens the editor with ?selftest=1 (placing the given figure files; PowerPoint's
files, from tests/data/powerpoint, are for the PowerPoint checks), and
prints every SELFTEST line from the browser console. Exit status 1 if anything failed.
On Windows, Chrome runs the same engine as the app window (Edge WebView2).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def find_chrome() -> str | None:
    cands = [os.environ.get("CHROME_PATH"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             shutil.which("google-chrome"), shutil.which("google-chrome-stable"), shutil.which("chromium"),
             shutil.which("chromium-browser"), shutil.which("chrome"),
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    return next((c for c in cands if c and os.path.exists(c)), None)


def run_selftest(files: list[str], chrome: str, shot: str, out: str, budget: int = 120000, only: str | None = None) -> dict:
    """Returns {"lines": SELFTEST lines, "errors": other console errors, "done": bool, "failed": bool}.

    Runs with its own settings folder, so it never touches ~/.figassemble (autosaves, recent
    files, preferences), and its own clipboard, so it never touches the system's. `budget`: the
    virtual time Chrome gives the page, which skips ahead whenever nothing is happening. The whole
    run took 54 s of it on 2026-11-02 on a Mac (37 s at the start of the month), more on CI, so keep
    it well above as checks are added (a run that runs out stops without its DONE line).
    """
    if not os.environ.get("FIGASSEMBLE_HOME"):
        os.environ["FIGASSEMBLE_HOME"] = tempfile.mkdtemp(prefix="figassemble-selftest-")
    from figassemble.app.api import Api
    from figassemble.app.server import start_server
    os.makedirs(out, exist_ok=True)
    fake_before = os.environ.get("FIGASSEMBLE_FAKE_CLIPBOARD")
    os.environ["FIGASSEMBLE_FAKE_CLIPBOARD"] = "1"
    srv = start_server(Api())
    query = urllib.parse.urlencode({"selftest": 1, "files": ",".join(os.path.abspath(f) for f in files),
                                    "out": os.path.abspath(out), "finalSelect": "curve", **({"only": only} if only else {})})
    url = srv.url + "ui/index.html?" + query
    with tempfile.TemporaryDirectory() as profile:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               f"--user-data-dir={profile}", "--window-size=1440,900", f"--virtual-time-budget={budget}",
               "--enable-logging=stderr", "--v=0", f"--screenshot={os.path.abspath(shot)}", url]
        if sys.platform.startswith("linux"):
            cmd.insert(1, "--no-sandbox")
        # (Chrome writes its log in UTF-8; Windows would read it in its own code page, which can't
        # take some characters in the checks' names, such as ←)
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=400)
    srv.shutdown()
    if fake_before is None:
        os.environ.pop("FIGASSEMBLE_FAKE_CLIPBOARD", None)
    else:
        os.environ["FIGASSEMBLE_FAKE_CLIPBOARD"] = fake_before
    lines = [m.group(1) for m in re.finditer(r'CONSOLE[^\n]*?"(SELFTEST[^"]*)"', proc.stderr)]
    errors = [m.group(0) for m in re.finditer(r'CONSOLE[^\n]*?"(?!SELFTEST)[^"\n]*(Error|error)[^\n]*', proc.stderr)]
    done = any(line.startswith("SELFTEST DONE") for line in lines)
    return {"lines": lines, "errors": errors, "done": done,
            "failed": (not done) or any(" FAIL " in f" {line} " for line in lines) or bool(errors)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--chrome", default=find_chrome())
    ap.add_argument("--shot", default="tools/output/ui_selftest.png")
    ap.add_argument("--out", default="tools/output/selftest")
    ap.add_argument("--budget", type=int, default=120000, help="virtual time budget, ms (the whole run took 54 s on 2026-11-02)")
    ap.add_argument("--only", help="run one part on its own, while working on it (objects: the Objects and Pages lists; slides: "
                    "PowerPoint slides; links: linked files updating; updates: updating FigAssemble; selection: selecting "
                    "several objects and Select Same; windows: New and Open in windows of their own, a .figasm "
                    "dropped on the page; sizes: page sizes, the Size menu and new documents' size; vision: colour "
                    "vision side by side and in command search; export: the window closing after an export, and its note; guides: clicking the rulers for guides, and a guide's right-click menu; pictures: the Style tab's picture menus)")
    args = ap.parse_args()
    if not args.chrome:
        print("Chrome not found; pass --chrome PATH")
        return 1
    res = run_selftest(args.files, args.chrome, args.shot, args.out, args.budget, args.only)
    for line in res["lines"]:
        print(line)
    for e in res["errors"]:
        print("console:", e[:300])
    if not res["done"]:
        print("self-test did not finish (no SELFTEST DONE line)")
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

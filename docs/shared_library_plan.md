# A shared library under mosaic and prose: plan

**Done, 14 November 2026.** The library is `~/Projects/labapp` (a working name; its README says
what's in it), and each app carries a copy in `<app>/_labapp/`. All eight parts below moved, with
three differences from the plan:

- It isn't a separate installed package pinned by version: with no GitHub repository until the
  names are final, each app carries a copy (`labapp/tools/vendor.py`), and a test in each app
  fails if the copy was edited or is behind.
- Recovery copies and versions keep each app's own form (mosaic: slim `.mosaic` files by path;
  prose: saved parts by document id). Moving either onto the other's would have changed what's on
  people's disks. The shared part is what both are built from (`labapp/kept.py`).
- prose has no updater wired in yet (it needs its own repository, key and GitHub app).

The rest of this page is the plan as written before the work.

## Why

The two apps are the same kind of program: a Python backend, a web page as the interface in a
pywebview window, a local server between them, documents as ZIP files, and the same care about
recovery, versions and updates. Prose was built by copying mosaic's parts and adapting them. The
copies have already drifted, and every platform fix now has to be made twice. During the audit:

- mosaic's tool lookup handles Windows (`bin`, `Library\bin`, `Scripts`); prose's four lookups don't.
- mosaic opens files and folders on all three systems; prose's `reveal` and `open_url` are Mac-only.
- mosaic's settings folder follows the system; prose's is `~/Library` everywhere.
- The Mac menu and title-bar code are 80% and 91% the same text in both apps.

## What is duplicated now

| Part | mosaic | prose | Same text |
|---|---|---|---|
| Mac menu bar | `app/macmenu.py` (384 lines) | `app/macmenu.py` (289) | 80% |
| Rename from the title bar | `app/mactitle.py` (283) | `app/mactitle.py` (303) | 91% |
| Documents from the Finder, windows | `app/macopen.py` (217) | `app/macopen.py` (95) | 53% |
| Local server and RPC | `app/server.py` (160) | `app/server.py` (123) | similar design |
| Recovery copies, history, versions | `app/kept.py` (348) | `recovery.py` + `versions.py` (332) | same ideas, different code |
| Updates and releases | `updates.py` (1,042), `tools/release.py` | none yet (planned) | to be copied |
| Installers and app makers | `install-*.{command,bat,sh}`, `packaging/` | `tools/make_app.py` only | to be copied |
| Problem report and log | `diagnostics.py` (212) | planned, same layout | to be copied |
| Tool lookup, open/reveal, settings folder | `assets.tool_path`, `Api.reveal`, `fonts.config_dir` | separate, Mac-only | different |
| Journal table | `journals.py` | copied by `tools/sync_journals.py` | generated copy |
| Windows WebView2 check, close question | `app/winruntime.py`, `app/closing.py` | none yet | to be copied |

About 3,000 lines in mosaic have a twin in prose or will need one.

## What the library would hold

A small package (working name `labapp`; one name, chosen when prose's is) that knows nothing
about figures or manuscripts. Each app passes in its name, document extension, bundle id and
settings folder once.

1. **platform**: settings and cache folders per system, tool lookup, open a file, reveal a file,
   open a URL, the system clipboard. Smallest, no interface changes, and it fixes five prose
   findings at once. *First.*
2. **diagnostics**: the log and the problem report, as in `mosaic/diagnostics.py`.
3. **server**: the token-guarded local server and RPC dispatch, with an explicit list of
   callable methods (prose's audit finding) and a content security policy.
4. **kept**: recovery copies, history and versions with one store of placed files
   (`kept-assets`), the size cap and the sweep. Prose's recovery and versions move onto it; the
   file lock gets a Windows branch once, here.
5. **mac**: menu bar, title-bar rename, Finder documents, the quit sheet. The app supplies its
   menu spec and callbacks.
6. **windowing**: the WebView2 check, the close question per system, and a File menu for
   Windows and Linux built from the same menu spec the Mac uses (prose has none off the Mac).
7. **updates and packaging**: `updates.py`, `tools/release.py`, the three installers and the
   app makers, taking the app's name and repository. Each app keeps its own signing key and
   GitHub app.
8. **journals**: one table of journals (sizes, label styles, limits) both apps import, replacing
   the generated copy.

## How to do it without breaking either app

- One part at a time, in the order above. Each move is: copy mosaic's version into the library
  with its tests, switch mosaic to import it (its 316 tests and the editor self-test must still
  pass), then switch prose and delete its copy.
- The library lives in its own repository and each app pins a version of it, so an app only
  takes a change when its own tests have run against it.
- Nothing changes for people using the apps: no file formats, settings or menus move.
- The interface code (JavaScript) stays separate. The two editors share almost nothing there.

## Before starting

- prose has a name, a repository and CI on the three systems.
- prose's Windows and Linux fixes are in, so its copies show what the shared version has to cover.
- Both apps are at a quiet point, with no feature half-built in the parts being moved.

Rough size: parts 1 and 2 are a day each; 3 to 6 about a week together; 7 and 8 another week,
most of it testing installers and updates on the three systems.

# Developing mosaic

How mosaic is built, run from source and tested. Design decisions are in
[design.md](design.md); progress in [roadmap.md](roadmap.md).

## Running from source

You need [conda](https://github.com/conda-forge/miniforge) (Miniforge, Miniconda or Anaconda).

```sh
git clone git@github.com:matthewwdavis/mosaic.git
cd mosaic
conda env create -f environment.yml
conda activate mosaic         # (made before the rename to mosaic: figassemble)
pip install -e .              # editable: code changes take effect on the next start
python -m mosaic              # or: mosaic
```

`python packaging/macos/make_app.py` builds a double-clickable `dist/mosaic.app` that starts
mosaic from the active environment. The environment's Python is linked into the app and
runs from there, so macOS takes the app's name, icon and version from the bundle; started any
other way, mosaic tells macOS its name itself (`macmenu.name_app`), or the menu bar would
say "python". The bundle declares the .mosaic type, so double-clicking a document opens it in
the app. Built anywhere but `dist/` (`--dest /Applications`, as the installer does), the script
registers it with LaunchServices (`lsregister -f`) as it makes it. A copy in `dist/` isn't
registered, since macOS would then choose between two apps of the same name for the documents
(starting it registers it, though; `lsregister -u dist/mosaic.app` takes it back off). A
mosaic started from a terminal isn't the bundle, so a double-clicked document starts the
app beside it. `mosaic --browser` serves the editor to a web browser instead of opening the
app window.

On a Mac the menu bar (mosaic, File, Edit, View, Window, Help) is made by
`mosaic/app/macmenu.py` from the editor's description of it (`app.menuSpec` in `main.js`),
so it always has the editor's commands and their shortcuts.

## Layout

```
mosaic/
  model.py, docfile.py      the document (JSON) and the .mosaic file (zip)
  assets.py                 placed files: copies, links, sizes, change detection
  geometry.py, presets.py   paths, corner rounding, arrowheads; PowerPoint's 187 shapes
  dashes.py, connect.py     even dash spacing; connection points
  fonts.py, textlayout.py   fonts and PowerPoint-compatible text layout
  resolve.py                items -> drawing primitives, shared by every writer and the editor
  export/                   PDF, SVG, PNG/TIFF/JPEG writers, conversions, pre-export check
  importers/                PowerPoint slides -> pages
  app/                      local server, JSON-RPC API, the app's windows
  updates.py                updates: finding, checking, downloading and installing new versions
  ui/                       the editor: HTML, CSS and JavaScript (no build step)
examples/                   sample plots for the tutorial (made by make_examples.R)
packaging/                  the Mac app; the Windows shortcuts and file types
tools/                      self-test runner, screenshots, render comparisons, releases
```

The engine (Python) is the single source of geometry and text layout. The editor sends items to
it and draws the SVG it returns, so what's on screen and what's exported come from the same code.

## Tests

```sh
python -m pytest -q                            # engine tests + the editor self-test (needs Chrome)
python tools/ui_selftest.py plot.svg plot.pdf  # the editor self-test on your own files
```

The **editor self-test** (`mosaic/ui/js/selftest.js`) drives the real editor with pointer
and keyboard events: drawing, snapping, guides, align, connectors, dashes, right-click menus,
export, PowerPoint slides, updates, windows, page sizes, colour vision, the Home tab's Text section, journal
checks and more, about 550 checks. `tests/test_ui.py` runs it in headless
Chrome. Besides a plot's SVG and PDF it takes PowerPoint's files from `tests/data/powerpoint`: a
deck and a copy of it, and what PowerPoint put on the clipboard for a copied slide (`.slides`) and
shapes (`.gvml`). `tools/ui_selftest.py ... --only slides` runs just the PowerPoint part, and
`--only links` just linked files updating (a test figure re-saved while placed), `--only
updates` the update screens (with the updater saying what each case needs), `--only
selection` selecting several objects and Select Same, `--only windows` New and Open with
several windows (opening a window stood in for) and a .mosaic dropped on the page, `--only
sizes` page sizes (the Size menu, new documents' size), `--only vision` colour vision side by
side and in command search, `--only export` the Export and Figure report windows closing with a
note, `--only guides` guides from clicking the rulers and a guide's right-click menu, `--only
pictures` the Style tab's picture menus, `--only textribbon` the Home tab's Text section
(several boxes at once, the highlighted words while typing, switching to Home and back), and
`--only journallabels` panel labels following a page's journal, and `--only journalchecks` the
journal's line widths, resolution by picture kind and Export window flags. To run it in
the app's own window (WebKit on a Mac):

```sh
D=tests/data/powerpoint
MOSAIC_HOME=$(mktemp -d) MOSAIC_SMOKETEST=1 \
  MOSAIC_SMOKE_QUERY="selftest=1&files=/path/plot.svg,/path/plot.pdf,$D/example_deck.pptx,/path/copy_of_the_deck.pptx,$D/copied_slide.slides,$D/copied_rect.gvml" \
  python -m mosaic
```

It prints `SELFTEST {...}` with every result, then `SMOKE ready errors=[]`. The figures it saves
and its exports go in a temporary folder, unless the query gives one (`&out=/path`). A hidden window's
timers run slowly, so this takes about seven minutes (it waits up to 15). Without
`MOSAIC_SMOKE_QUERY` (keep `MOSAIC_HOME`, so it can't meet your own recovery copies
and preferences) it checks that
the editor starts and that an edit switches on the close confirmation. On a Mac it then presses
every keyboard shortcut with real key events, through AppKit and pywebview as a key press goes
(`mosaic/app/keycheck.py`), since the self-test's own key presses never leave the page;
⌘-clicks with real mouse events; and pastes text, a PDF, a copied file and a screenshot from the
real clipboard (put back afterwards): `SMOKE keys: 94 of 94 passed`. A dialog open at the start
(such as the offer to recover unsaved work) is closed first, as Not now closes it. Then it hands the web view drags from PowerPoint (made up, since a
hidden window can't be dragged onto) through the drag methods `mosaic/app/macdrag.py` wraps,
and plays a slide drag to the `SlideWatch` that follows PowerPoint's real ones, with a scripted
drag pasteboard, mouse button and pointer: `SMOKE PowerPoint drags: 9 of 9 passed`. Then the
menu bar: its menus, the app's name, the shortcuts, and items run as AppKit would run them:
`SMOKE menus: 11 of 11 passed`. Last, documents and windows (`mosaic/app/macopen.py`):
documents sent as the Finder sends them, as real "open documents" Apple events to the app
itself, opening in the blank window, then in windows of their own, or bringing one open already
to the front; File > New; a menu command going to the window in front; closing a window; a deck;
and a .mosaic dropped on the page: `SMOKE windows: 12 of 12 passed`. Then closing and quitting
with unsaved changes (`mosaic/app/macclose.py`), with its buttons pressed as AppKit presses them:
- the sheet, its wording and keys;
- Cancel, Save, and Don't Save keeping a copy;
- a real quit (`terminate:`) asking about each figure in turn, which a Cancel stops, and a
  second quit meanwhile changing nothing.

`SMOKE closing: 10 of 10 passed`. A sheet shows its window, so these windows appear on screen
briefly.

To check a double-click end to end (LaunchServices choosing the app, macOS launching it with the
document), open a test figure with `open`, which can hand the app its own settings folder and a
light check that reports which windows have which documents, then quits:

```sh
H=$(mktemp -d)
python -c "from mosaic import docfile, model; docfile.save(model.new_document('Test'), '$H/test.mosaic')"
open -g --env MOSAIC_HOME=$H --env MOSAIC_SMOKETEST=launch --stdout $H/out.txt "$H/test.mosaic"
cat $H/out.txt   # SMOKE launch: {"ready": true, "windows": 1, "documents": [".../test.mosaic"]}
```

Only do this while no mosaic.app is running: macOS hands the document to a running one.

Slides and shapes copied in PowerPoint come from its own clipboard formats, and a slide dragged
out of it is only a reference to the slide (see the PowerPoint decision in [design.md](design.md)).
To see what an app puts on the Mac clipboard, read `NSPasteboard.generalPasteboard()`'s types
with PyObjC; PowerPoint's AppleScript can copy a slide (`copy object slide 2 of presentation
"deck.pptx"`) or a shape (`copy shape`), so this needs no clicking. The last drag's contents stay
on the drag pasteboard (`NSPasteboard.pasteboardWithName_(NSPasteboardNameDrag)`), and its change
count goes up with each drag. PowerPoint refuses slide-thumbnail drags to other apps, so macOS
sends the window no drag calls for them; only a person dragging can show what a real drag does.

Paste reads the system clipboard on the Python side (`mosaic/app/clipboard.py`): AppKit on
a Mac, the Windows clipboard API on Windows. The editor self-test sets
`MOSAIC_FAKE_CLIPBOARD=1`, which swaps in a clipboard of mosaic's own, so tests never
touch the real one.

GitHub Actions runs the tests on Windows and Linux for every push (`.github/workflows/tests.yml`).
`installers.yml` runs both installers on fresh Mac and Windows machines when they, what they
install or the updates change, or when started by hand from the Actions tab; then the installed
copy updates itself for real (see [Releases and updates](#releases-and-updates)).

## Documentation pictures

```sh
Rscript examples/make_examples.R   # the sample plots (PDF, PNG and SVG each), with R and ggplot2
python tools/doc_shots.py          # every screenshot in docs/images/, taken in the real editor
python tools/doc_shots.py export   # just one scene
```

The scenes are in `mosaic/ui/js/docshots.js`; each builds the tutorial figure up to one
step. Re-run `doc_shots.py` after changing the interface.

## Installers

`install-mac.command` and `install-windows.bat` install Miniforge if there's no conda, make or
update the `mosaic` environment from `environment.yml`, install mosaic into it (not
editable, so the downloaded folder can be deleted), and add the app (Mac) or shortcuts (Windows).
For testing without touching a real installation: `MOSAIC_ENV` (environment name),
`MOSAIC_APP_DIR` (Mac app folder) and `MOSAIC_NO_OPEN=1` (don't start mosaic or
wait for a key at the end). On a development machine, always set `MOSAIC_ENV`: the default
environment name is the same as the development environment's, and the installer would replace
the editable install with a copy.

The installers also leave notes in the environment's `etc/mosaic` folder: `installer` (this
copy may update itself), `environment.sha256` (what the environment was made from) and, on a Mac,
`app_dir`. Updates run the new version's installer with `MOSAIC_UPDATE=1` (no questions),
`MOSAIC_PREFIX` (the environment; conda runs only if `environment.yml` changed),
`MOSAIC_WAIT_PID` (wait for mosaic to close), `MOSAIC_RESULT` (where to write `ok`
or `failed: why`) and `MOSAIC_LOCK` (removed at the end).

## Licenses

The code is under the MIT License (`LICENSE`), the documentation and pictures (README, `docs/`,
the example plots) under CC BY 4.0 (`LICENSE-docs`). Anything that comes from others goes in
`THIRD_PARTY_NOTICES.md` with its notice, as PowerPoint's shape formulas (Ecma's notice), the
icons after Feather and Lucide, the theme colours, the palettes and the test decks' python-pptx
template do. Libraries the installers install aren't part of mosaic, but are listed there
too.

## Releases and updates

Installed copies update themselves from GitHub releases (`mosaic/updates.py`; how it looks
to people is in the [guide](guide.md#updates)). A release is the repository at its tag as a ZIP,
which is also what people install from, and `release.json`: the version, the ZIP's SHA-256 and
size, the SHA-256 of `environment.yml` and what's new, signed with the release key (Ed25519).
Installed copies accept only releases signed with a key listed in
`mosaic/data/updates.json`. Collaborators on a personal repository can push and make
releases, so the key, not GitHub, decides what installs on everyone's computer.

### Setting up, once

1. **The GitHub app, for signing in while the repository is private.** Open
   [this pre-filled form](https://github.com/settings/apps/new?name=mosaic%20Updates&description=Lets%20mosaic%20download%20its%20updates%20from%20its%20private%20repository&url=https://github.com/matthewwdavis/mosaic&public=true&webhook_active=false&contents=read)
   (name, homepage, no webhook, Contents: read-only, installable by any account so collaborators
   can authorize it; it reads only repositories it's installed on). Tick **Enable Device Flow**,
   then **Create GitHub App**. Put its **Client ID** in `mosaic/data/updates.json`
   (`github_app_client_id`). Then **Install App** → your account → **Only select repositories** →
   mosaic. Keep user tokens expiring (the default); mosaic renews them itself.
2. **The release key.** In your own Terminal window (not through Claude: it shows the private
   key, and a Claude session keeps everything shown in its transcript):

   ```sh
   conda activate mosaic
   python tools/release.py key new
   ```

   It keeps the key in the Mac's Keychain, adds its public half to `mosaic/data/updates.json`
   and shows a backup line to keep off the computer (the Passwords app, a password manager, or on
   paper). Commit `data/updates.json`; installed copies trust the key once a release with it is
   installed.

### Publishing

```sh
python tools/release.py publish                # main as the next version (0.2.1 after 0.2.0)
python tools/release.py publish 0.3.0 --test   # a test version, for those who take them
python tools/release.py promote 0.3.0          # the test version, tried, goes to everyone
python tools/release.py list                   # the releases, and how often each was downloaded
```

`publish` needs a clean `main` that matches GitHub's and passed the tests on GitHub (or
`--skip-ci-check`). It drafts What's new from the commit messages since the last release for you
to rewrite in plain words, then sets the version in `mosaic/__init__.py` (the one place it's
written; `pyproject.toml` reads it from there), commits and tags it, builds and signs the ZIP,
pushes, and makes the GitHub release. A test version is a GitHub pre-release; `promote` makes it
a full one.

### The key on another computer, and if it's lost or leaks

- **A new computer:** `python tools/release.py key restore` and paste the backup;
  `key check` says whether installed copies trust it.
- **Lost, with no backup:** `key new --replace`, commit `data/updates.json` and publish. Installed
  copies don't trust the new key, so everyone installs that release by hand once (download it,
  run the installer); after that they update as before. Then take the old key out of
  `data/updates.json`.
- **Leaked:** make a new key (`key new --replace`, which lists it beside the old one), commit, put
  the old key back for one release (`key restore` with its backup) and publish: installed copies
  accept it and from then on trust the new key too. Then `key restore` the new key, take the old
  one out of `data/updates.json`, commit and publish again.

### When the repository goes public

Nothing needs changing: an installed copy that isn't signed in looks without a sign-in first,
finds the releases and stops asking. The GitHub app can stay or be deleted (copies signed in with
it then carry on without). Take the GitHub-account step out of the README's install section.

### How an update installs

The updater looks shortly after mosaic starts and every 6 hours, and downloads what it
finds to `~/.mosaic/updates` (`release.json` checked against the trusted keys, then the ZIP
against its SHA-256 and size), and unpacks it. When mosaic quits (or after Restart now),
it starts the new version's installer in update mode and writes a lock with its process; a
mosaic opened meanwhile waits for it (`wait_for_install`). The installer writes `ok` or
`failed: why`, which the next start reads: What's new, or the reason, retried at the next quit
(twice). The last mosaic to close installs an update (`updates/running`). A copy run from a
checkout or an editable install never updates itself (`install_kind`).

### Testing updates

- `tests/test_updates.py` runs the updater against a stand-in for GitHub
  (`tools/fake_github.py`): private and public repositories, sign-in and refresh, redirects to a
  file host that refuses a sign-in, tampered or wrongly signed releases, channels, skip and going
  back, installing at quit, and what the last install left.
- `tools/update_e2e.py` (in `installers.yml`) has a copy made by the installer update itself
  through the real installers, go back, and take a test version.
- By hand: `python tools/release.py testkey key.txt` (prints the public key) and
  `python tools/release.py local --version 9.9.9 --key-file key.txt --out releases/` make a
  release; `python tools/fake_github.py serve releases/ --token T` serves it. Point a copy
  installed for testing (never the development environment) at it with `MOSAIC_UPDATE_API`
  and `MOSAIC_UPDATE_WEB` (the address it prints) and `MOSAIC_UPDATE_TEST_KEY`.

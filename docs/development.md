# Developing FigAssemble

How FigAssemble is built, run from source and tested. Design decisions are in
[design.md](design.md); progress in [roadmap.md](roadmap.md).

## Running from source

You need [conda](https://github.com/conda-forge/miniforge) (Miniforge, Miniconda or Anaconda).

```sh
git clone git@github.com:matthewwdavis/FigAssemble.git
cd FigAssemble
conda env create -f environment.yml
conda activate figassemble
pip install -e .              # editable: code changes take effect on the next start
python -m figassemble         # or: figassemble
```

`python packaging/macos/make_app.py` builds a double-clickable `dist/FigAssemble.app` that starts
FigAssemble from the active environment. The environment's Python is linked into the app and
runs from there, so macOS takes the app's name, icon and version from the bundle; started any
other way, FigAssemble tells macOS its name itself (`macmenu.name_app`), or the menu bar would
say "python". `figassemble --browser` serves the editor to a web browser instead of opening the
app window.

On a Mac the menu bar (FigAssemble, File, Edit, View, Window, Help) is made by
`figassemble/app/macmenu.py` from the editor's description of it (`app.menuSpec` in `main.js`),
so it always has the editor's commands and their shortcuts.

## Layout

```
figassemble/
  model.py, docfile.py      the document (JSON) and the .figasm file (zip)
  assets.py                 placed files: copies, links, sizes, change detection
  geometry.py, presets.py   paths, corner rounding, arrowheads; PowerPoint's 187 shapes
  dashes.py, connect.py     even dash spacing; connection points
  fonts.py, textlayout.py   fonts and PowerPoint-compatible text layout
  resolve.py                items -> drawing primitives, shared by every writer and the editor
  export/                   PDF, SVG, PNG/TIFF/JPEG writers, conversions, pre-export check
  importers/                PowerPoint slides -> pages
  app/                      local server, JSON-RPC API, the app window
  ui/                       the editor: HTML, CSS and JavaScript (no build step)
examples/                   sample plots for the tutorial (made by make_examples.R)
packaging/                  the Mac app and the Windows shortcuts
tools/                      self-test runner, screenshots, render comparisons
```

The engine (Python) is the single source of geometry and text layout. The editor sends items to
it and draws the SVG it returns, so what's on screen and what's exported come from the same code.

## Tests

```sh
python -m pytest -q                            # engine tests + the editor self-test (needs Chrome)
python tools/ui_selftest.py plot.svg plot.pdf  # the editor self-test on your own files
```

The **editor self-test** (`figassemble/ui/js/selftest.js`) drives the real editor with pointer
and keyboard events: drawing, snapping, guides, align, connectors, dashes, right-click menus,
export, PowerPoint slides and more, about 350 checks. `tests/test_ui.py` runs it in headless
Chrome. Besides a plot's SVG and PDF it takes PowerPoint's files from `tests/data/powerpoint`: a
deck and a copy of it, and what PowerPoint put on the clipboard for a copied slide (`.slides`) and
shapes (`.gvml`). `tools/ui_selftest.py ... --only slides` runs just the PowerPoint part. To run
it in the app's own window (WebKit on a Mac):

```sh
D=tests/data/powerpoint
FIGASSEMBLE_HOME=$(mktemp -d) FIGASSEMBLE_SMOKETEST=1 \
  FIGASSEMBLE_SMOKE_QUERY="selftest=1&files=/path/plot.svg,/path/plot.pdf,$D/example_deck.pptx,/path/copy_of_the_deck.pptx,$D/copied_slide.slides,$D/copied_rect.gvml" \
  python -m figassemble
```

It prints `SELFTEST {...}` with every result, then `SMOKE ready errors=[]`. A hidden window's
timers run slowly, so this takes about seven minutes (it waits up to 15). Without
`FIGASSEMBLE_SMOKE_QUERY` it checks that
the editor starts and that an edit switches on the close confirmation. On a Mac it then presses
every keyboard shortcut with real key events, through AppKit and pywebview as a key press goes
(`figassemble/app/keycheck.py`), since the self-test's own key presses never leave the page, and
pastes text, a PDF, a copied file and a screenshot from the real clipboard (put back afterwards):
`SMOKE keys: 81 of 81 passed`. Then it hands the web view drags from PowerPoint (made up, since a
hidden window can't be dragged onto) through the drag methods `figassemble/app/macdrag.py` wraps,
and plays a slide drag to the `SlideWatch` that follows PowerPoint's real ones, with a scripted
drag pasteboard, mouse button and pointer: `SMOKE PowerPoint drags: 9 of 9 passed`. Last, the
menu bar: its menus, the app's name, the shortcuts, and items run as AppKit would run them:
`SMOKE menus: 9 of 9 passed`.

Slides and shapes copied in PowerPoint come from its own clipboard formats, and a slide dragged
out of it is only a reference to the slide (see the PowerPoint decision in [design.md](design.md)).
To see what an app puts on the Mac clipboard, read `NSPasteboard.generalPasteboard()`'s types
with PyObjC; PowerPoint's AppleScript can copy a slide (`copy object slide 2 of presentation
"deck.pptx"`) or a shape (`copy shape`), so this needs no clicking. The last drag's contents stay
on the drag pasteboard (`NSPasteboard.pasteboardWithName_(NSPasteboardNameDrag)`), and its change
count goes up with each drag. PowerPoint refuses slide-thumbnail drags to other apps, so macOS
sends the window no drag calls for them; only a person dragging can show what a real drag does.

Paste reads the system clipboard on the Python side (`figassemble/app/clipboard.py`): AppKit on
a Mac, the Windows clipboard API on Windows. The editor self-test sets
`FIGASSEMBLE_FAKE_CLIPBOARD=1`, which swaps in a clipboard of FigAssemble's own, so tests never
touch the real one.

GitHub Actions runs the tests on Windows and Linux for every push (`.github/workflows/tests.yml`).
`installers.yml` runs both installers on fresh Mac and Windows machines when they or what they
install change, or when started by hand from the Actions tab.

## Documentation pictures

```sh
Rscript examples/make_examples.R   # the sample plots (PDF, PNG and SVG each), with R and ggplot2
python tools/doc_shots.py          # every screenshot in docs/images/, taken in the real editor
python tools/doc_shots.py export   # just one scene
```

The scenes are in `figassemble/ui/js/docshots.js`; each builds the tutorial figure up to one
step. Re-run `doc_shots.py` after changing the interface.

## Installers

`install-mac.command` and `install-windows.bat` install Miniforge if there's no conda, make or
update the `figassemble` environment from `environment.yml`, install FigAssemble into it (not
editable, so the downloaded folder can be deleted), and add the app (Mac) or shortcuts (Windows).
For testing without touching a real installation: `FIGASSEMBLE_ENV` (environment name),
`FIGASSEMBLE_APP_DIR` (Mac app folder) and `FIGASSEMBLE_NO_OPEN=1` (don't start FigAssemble or
wait for a key at the end).

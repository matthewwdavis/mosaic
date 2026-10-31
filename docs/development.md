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
FigAssemble from the active environment. `figassemble --browser` serves the editor to a web
browser instead of opening the app window.

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
export and more, about 160 checks. `tests/test_ui.py` runs it in headless Chrome. To run it in the
app's own window (WebKit on a Mac):

```sh
FIGASSEMBLE_HOME=$(mktemp -d) FIGASSEMBLE_SMOKETEST=1 \
  FIGASSEMBLE_SMOKE_QUERY="selftest=1&files=/path/plot.svg,/path/plot.pdf" python -m figassemble
```

It prints `SELFTEST {...}` with every result, then `SMOKE ready errors=[]`. A hidden window's
timers run slowly, so this takes a few minutes. Without `FIGASSEMBLE_SMOKE_QUERY` it checks that
the editor starts and that an edit switches on the close confirmation. On a Mac it then presses
every keyboard shortcut with real key events, through AppKit and pywebview as a key press goes
(`figassemble/app/keycheck.py`), since the self-test's own key presses never leave the page, and
pastes text, a PDF, a copied file and a screenshot from the real clipboard (put back afterwards):
`SMOKE keys: 72 of 72 passed`.

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

# FigAssemble

A small, fast app for assembling multi-panel scientific figures: set a page size, drop in
plots and images, add text, panel labels, lines, arrows and shapes, and export PDF, SVG,
PNG or TIFF at any resolution.

Unlike PowerPoint, FigAssemble never converts a placed file through an intermediate
format. A placed PDF goes into the exported PDF unchanged, a placed SVG goes into the
exported SVG unchanged, and PNG/TIFF exports are rendered once, straight from the vectors.
When a plot was saved as PDF + SVG + PNG under one name (as R's ggsave workflow does),
FigAssemble finds the copies and uses the matching one for each export. Fonts that R's
`pdf()` leaves out (Helvetica) are embedded on export.

> Status: first version. Decisions and architecture: [docs/design.md](docs/design.md);
> progress: [docs/roadmap.md](docs/roadmap.md).

## Install

You need [conda](https://docs.conda.io) (Anaconda, Miniconda or Miniforge).

```sh
git clone git@github.com:matthewwdavis/FigAssemble.git
cd FigAssemble
conda env create -f environment.yml
conda activate figassemble
pip install -e .
```

**Mac:** build a double-clickable app, then drag `dist/FigAssemble.app` into Applications:

```sh
python packaging/macos/make_app.py
```

**Windows:** start it with `figassemble` from the Anaconda Prompt (with the environment
activated). A no-command-line installer is planned.

## Using it

- **Place figures** by dragging files (PDF, SVG, PNG, JPEG, TIFF) onto the page, or with
  Picture (I). They land at true size, so 6 pt text stays 6 pt.
  - Placed files stay **linked**: re-run your R code and the panel updates by itself.
    A copy is also stored in the document, so it opens complete on a labmate's computer.
  - Hold **Option (Alt)** while dropping to store a copy without the link.
  - Hold **Shift** while dropping a file onto a picture to replace it (position and scale kept).
- **Draw** with Text (T), Panel label (P: adds a, b, c… in order), Line (L), Arrow (A),
  Rectangle (R), Rounded rectangle (U), Ellipse (O), Triangle, Arc and Bracket.
  Shift keeps straight lines, squares and proportions.
- **Curve an arrow (or line):** select it and drag the hollow handle halfway along it; the
  arrow bends into a smooth curve through that point and the head follows. Drag other hollow
  handles to add more points (S-curves), drag points to reshape, double-click a point to
  remove it. The properties panel lists every point's position and switches between smooth
  curves and straight segments. Arcs imported from PowerPoint have a "Make editable curve" button.
- **Edit** in the properties panel on the right: exact positions, sizes, rotation, line width
  and dashes, arrowheads, fills, fonts. Every colour has a picker and an editable hex code;
  transparency is a percentage (0% = solid), as in PowerPoint. Double-click text to type;
  double-click a picture to crop it.
- **Outline** an arrow or shape with a contour in a second colour (e.g. a white edge that keeps a
  black arrow visible on a photo): tick "Outline around it" and set its colour, thickness and
  transparency. It wraps the line, the arrowhead and any fill.
- **Arrange:** drag to move (objects snap to edges, centres and the page; hold ⌘/Ctrl to
  stop snapping), align and distribute several objects, group (⌘G), bring forward (⌘]).
- **Pages:** one document can hold many pages, e.g. versions of a figure. New pages are A4.
  In the Page panel, pick a **Journal** (Cell, G3, Genetics, Genome Biology, Genome Research,
  Heredity, Molecular Biology and Evolution, Molecular Plant, Nature, New Phytologist, Plant Cell,
  PLOS Genetics, PNAS, Science) and a **Figure type** (e.g. Nature single column, 90 mm) to set
  the page to that width and the journal's maximum depth, or pick a
  **Standard size** (A4, US Letter, 16:9 slide). "Fit to content" crops the page to the figure
  (on journal pages it keeps the column width). Positions and sizes are in centimetres; font
  sizes and line widths in points (change units in Settings).
- **Check** lists the smallest text after scaling, low-resolution images, conversions that
  will be needed and files that can't be found.
- **Export** (⌘E): PDF, SVG, PNG, TIFF at 300/600/1200 dpi or any other, transparent or
  white. More options: JPEG, EPS, CMYK (only when a journal asks).
- **PowerPoint:** Open a `.pptx` to turn its slides into pages, with pictures relinked to the
  original figure files where they can be found.

Documents are saved as `.figasm` files. Unsaved work is autosaved every minute and offered
back after a crash.

### Accessibility

- Every tool and setting is a labelled control reachable with the keyboard; press **?** for
  all shortcuts. On the page: Tab moves between objects, arrow keys move them (Shift: 10 pt,
  Option/Alt: 0.1 pt), Enter edits text or crops, Escape finishes.
- Screen readers hear what's selected, where it is and what each action did; pictures can
  carry a description.
- Settings: interface text size, light/dark/high-contrast appearance, toolbar labels,
  reduced motion. The system's high-contrast and reduced-motion settings are followed too.

## Command line

```sh
figassemble                                   # open the app
figassemble figure.figasm                     # open a document
figassemble export figure.figasm -f pdf,svg,png --dpi 600
figassemble import-pptx deck.pptx --slides 13 # PowerPoint slides -> figure.figasm
figassemble --browser                         # use a web browser instead of the app window
```

## Development

```sh
python -m pytest -q                           # engine tests + editor self-test (needs Chrome)
python tools/ui_selftest.py plot.svg plot.pdf # the editor self-test on your own files
python tools/serve.py                         # serve the editor for any browser
python tools/compare_renders.py a.pdf b.pdf   # pixel comparison of two exports
```

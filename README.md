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

- **The window:** commands sit in tabs across the top, like PowerPoint's ribbon: **Home**
  (file, undo, clipboard, pages), **Arrange** (align, distribute, group, order) and **View** (zoom,
  rulers, grid, guides). Snap, Check, Export, Settings and Help stay in view on the right. The
  drawing tools run down the side of the page. The properties panel on the right has tabs
  (Arrange, Style, Text, Picture) whose sections fold away and stay folded; zoom is also in the
  status bar.
- **Place figures** by dragging files (PDF, SVG, PNG, JPEG, TIFF) onto the page, or with
  Picture (I). They land at true size, so 6 pt text stays 6 pt.
  - Placed files stay **linked**: re-run your R code and the panel updates by itself.
    A copy is also stored in the document, so it opens complete on a labmate's computer.
  - Hold **Option (Alt)** while dropping to store a copy without the link.
  - Hold **Shift** while dropping a file onto a picture to replace it (position and scale kept).
- **Draw** with Text (T), Panel label (P: adds a, b, c… in order), Line (L), Arrow (A),
  Rectangle (R), Rounded rectangle (U), Ellipse (O), Triangle, Arc and Bracket.
  Shift keeps straight lines, squares and proportions. Click instead of dragging for a 2 cm
  shape; with the keyboard, choose a tool and press Enter to place one in the middle.
- **Shapes (S)** opens a menu of PowerPoint's shapes: rectangles, basic shapes (polygons,
  pie, frame, ring, cylinder, heart…), block arrows, stars, brackets and braces, and
  equation symbols. Arrow keys move through it, typing a name jumps to it, Enter chooses.
  Drag a shape's yellow handles to adjust it (a star's inner radius, an arrow's head length),
  or type the values in the properties panel.
- **Round corners:** Corner rounding (0–100%) rounds the corners of triangles, polygons,
  stars, block arrows and any other straight-edged shape; 100% is as round as the shape
  allows. Each arrowhead has its own rounding too; the rounded tip still ends on the line's
  end point.
- **Even dashes:** dashed and dotted lines put a dash (or dot) on every corner, bend and line
  end, rounded corners included, and space the stretches between them evenly, so corners don't
  crowd the way they do in PowerPoint and curved outlines have no squeezed spot where they close.
  Shapes from PowerPoint decks get it too; untick "Even dashes" on an object for PowerPoint's spacing.
- **Connect:** drop a line or arrow end on an object's connection point to attach it; it then
  follows the object when it moves, resizes or turns. Points are the object's own corners and the
  middles of its sides (triangle tips, star points, rounded corners), 8 points round an ellipse,
  a picture's or text box's corners and side middles, a line's ends and middle, and on dashed or
  dotted outlines both ends and the middle of every dash. They show while you draw a line or drag
  its end; attached ends are green. Hold ⌘ (Ctrl) to drop an end without attaching; moving a line
  on its own lets go. The properties panel says where each end is attached, with Detach.
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
- **Arrange:** drag to move; group (⌘G); bring forward (⌘]). **Align and distribute** as in
  Illustrator, from the Arrange tab or the properties panel: six aligns; distribute by left edges,
  centres, right edges, tops, middles or bottoms; space evenly across or down, or exactly a set
  **Gap** apart (e.g. 0.2 cm). **Align to** the selection, the page, or a **key object** that stays
  put: click one of the selected objects to make it the key (it gets a thick outline). One object
  on its own aligns to the page.
- **Line things up:** rulers run along the top and left of the page (⌘R), in your position units
  with 0 at the page's top-left corner. Drag a **guide** out of a ruler and drop it on the page;
  drag it (or its mark on the ruler) to move it, or back onto the ruler to remove it. With nothing
  selected, the Page panel lists the page's guides to add, type exact positions and remove. Each
  page has its own guides; a new page starts with the current page's. The **grid** (⌘') is graph
  paper over the page: 1 cm squares whose 1 mm lines appear as you zoom in (spacing in Settings).
  Guides and the grid are never exported. The **View** menu shows and hides all three.
- **Snapping:** dragged objects snap to the page's edges and centre, other objects' edges and
  centres, equal gaps between objects (the gaps show with their size), and guides and the grid
  while they're shown; hidden guides and a hidden grid never pull. Grid lines give way to
  everything else. To place something freely, hold ⌘ (Ctrl on Windows) while dragging, or turn
  the **Snap** button off (⌘⇧;); Escape cancels a drag.
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
  original figure files where they can be found. Every PowerPoint shape comes in as itself,
  drawn from PowerPoint's own shape formulas.

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

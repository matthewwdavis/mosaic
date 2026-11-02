# FigAssemble design

FigAssemble is a small desktop app for assembling multi-panel scientific figures:
place plots and images on a page of any size, add text, lines, arrows and shapes,
and export PDF, SVG, PNG or TIFF without the format conversions that degrade
PowerPoint figures.

## Core rule: never convert a file unless the output format forces it

PowerPoint rewrites inserted SVGs, wraps inserted PDFs in EMF frames, and its PDF
export draws every picture as a ~300 dpi bitmap (some JPEG). FigAssemble keeps each
placed file in its original form and writes it once, straight into the output:

| Placed file | PDF export | SVG export | PNG / TIFF export |
|---|---|---|---|
| PDF | page embedded unchanged as a Form XObject (qpdf/pikepdf) | PDF -> SVG conversion, only if no SVG copy exists | rendered once from the vectors (PDFium) |
| SVG | SVG -> PDF conversion, only if no PDF copy exists | markup copied in unchanged (IDs prefixed) | rendered from the PDF copy or converted SVG |
| PNG / JPEG / TIFF | image data embedded losslessly (JPEG bytes passed through) | embedded as a data URI, byte-identical | resampled once to the export DPI |

R notebooks save every plot as PDF + SVG + PNG under one name. FigAssemble links all
copies of a plot ("variants") and uses the matching original for each export, so the
normal case involves no conversion at all. When a conversion is unavoidable, the
pre-export check says so.

## Decisions (2026-10-30)

- **Users and platforms:** Matthew and labmates. macOS is the primary build; everything
  stays cross-platform (Python + web UI, no Mac-only APIs) so Windows works too.
  Helvetica falls back to Arial (identical letter widths) where it isn't installed.
- **Linked and embedded, both by default:** a dropped file is linked (refreshes when R
  re-saves it) and a copy is stored inside the document, so a file sent to a labmate
  still opens complete. Option/Alt-drop embeds without a link. Pictures can be relinked,
  unlinked or replaced later. Drag and drop is a primary way of working.
- **Multi-page documents**, so a figure's versions can live side by side.
- **First-version features:** pictures (PDF, SVG, PNG, JPEG, TIFF) with non-destructive
  cropping; text boxes (Helvetica mostly 5-8 pt; bold, italic and mixed runs; rotation);
  lines with widths, round caps, dash/dot styles and arrowheads; rectangles, rounded
  rectangles, ellipses, arcs, brackets, triangles and freeform paths (drawing/editing
  freeform points comes later); groups, flips, rotation, transparency.
- **Exports:** PDF, SVG, PNG, TIFF with a DPI setting and transparent or white
  background. CMYK, EPS and file-size limits are available but never the default.
- **Fonts in placed PDFs:** R's `pdf()` leaves Helvetica unembedded. PowerPoint hid this
  by rasterising every panel. PDF export embeds missing fonts without touching the
  drawing instructions (on by default); the pre-export check reports it.
- **PowerPoint import:** open slides from existing figure decks as editable pages
  (positions, crops, text, lines, shapes), pulling pictures out of the deck and relinking
  them to the R output files where they match. Grown from the test slide outwards.
- **Accessibility, all three meanings:** easy to learn and use (labeled tools, tooltips
  with shortcuts, PowerPoint-like behaviour, undo for everything); disability access
  (full keyboard control, screen-reader labels and announcements, high contrast,
  colour-blind-safe interface, adjustable interface text size, reduced motion); easy
  to install for labmates on Mac and Windows without the command line.
- **Units:** positions and sizes of objects in centimetres (changed from points on
  2026-10-31); font sizes and line widths always in points; page sizes in millimetres.
  Anyone can switch. Settings files store only real choices, so changed defaults reach everyone.
- **Page sizes:** new pages are A4. The Page panel has a Standard size dropdown (A4, US Letter,
  16:9 slide), a Journal dropdown and a Figure type dropdown; a journal type sets the column
  width and the journal's maximum figure depth (e.g. Nature 90/180 mm x 170 mm; Science
  5.7/12.1/18.4 cm x 19.9 cm, leaving room for the legend). 14 journals (2026-10-31): Cell, G3,
  Genetics, Genome Biology, Genome Research, Heredity, MBE, Molecular Plant, Nature, New
  Phytologist, Plant Cell, PLOS Genetics, PNAS, Science. Where a journal publishes no sizes
  (Genetics, G3, Genome Research, Heredity, MBE), they were measured from a published 2025
  open-access article, as Matthew chose; the app's note says so. On journal pages "Fit to
  content" keeps the column width. Data and sources: `journals.py`.
- **Shapes (2026-10-31):** a Shapes menu (S, now in the drawing tools beside the page) with PowerPoint's rectangles,
  basic shapes, block arrows, stars, brackets and braces, and equation symbols (88 in all),
  as a grid of icons in groups, usable from the keyboard (arrows, type-ahead, Enter). A click
  or Enter with any drawing tool places a 2 cm shape, so no pointer is needed. Shapes keep
  PowerPoint's yellow adjust handles; the properties panel names each adjustment (Inner
  radius, Shaft width, Head length...). The existing toolbar buttons stay.
- **Corner rounding:** every shape with corners between straight edges (triangles,
  polygons, stars, block arrows, freeforms) has Corner rounding 0-100%: one radius for all
  corners, 100% being the largest that fits (a triangle becomes its inscribed circle, a
  rectangle a stadium). Corners next to curves are left alone.
- **Rounded arrowheads:** each triangle, stealth, open or diamond head has its own rounding
  0-100% on the same scale. A pointed head slides forward so its rounded tip still ends on
  the line's end point, and the line's end moves with it, kept hidden inside the head.
- **Rulers, grid and guides (2026-10-31):** rulers along the top and left (⌘R), in the units
  positions are shown in, 0 at the page's top-left corner like the X and Y fields. Guides are
  dragged out of the rulers and belong to each page (pages can differ in size); new and duplicated
  pages start with the current page's guides, and "Fit to content" moves them with the objects.
  Objects take precedence over guides under the pointer; a guide covered by objects can be dragged
  by its mark on a ruler or typed in the Page panel. The grid is graph paper (1 cm squares, 1 mm
  lines that appear when zoomed in far enough to see them apart). Neither is ever exported. The
  View tab holds the three switches; Snap has its own button, always in view.
- **Snapping must be easy to override (Matthew's requirement):** the Snap button (⌘⇧;) turns it
  all off and always shows its state; holding ⌘/Ctrl frees a single drag; Escape cancels a drag.
  Nothing snaps to lines that can't be seen: the grid only while it shows (Matthew's choice), and
  hidden guides don't snap either. Targets: page edges and centre, other objects' edges and
  centres, equal gaps between objects (PowerPoint-style smart guides, with the gap's size shown),
  guides, then the grid, which only counts when nothing chosen on purpose is near. Resizing doesn't
  snap (not chosen). Keyboard nudges and typed values never snap.
- **Even dash spacing (2026-10-31):** PowerPoint runs a dash pattern continuously along a path,
  so dashes straddling a corner sit closer than anywhere else (up to ~30% for dots) and closed
  outlines have a squeezed seam; Matthew asked for this to be fixed. Like Illustrator's "align
  dashes to corners", a dash is centred on every corner (a dot sits on it), including bends in
  lines and the middles of rounded corners (curves between straight stretches turning 45 degrees or
  more); lines start and end on a whole dash; each stretch holds a whole number of repeats, dashes
  and gaps scaled together (his choice); closed curves fit whole repeats, so no seam; gaps are
  measured straight across, so dots on tight curves don't bunch. On for every dashed stroke,
  imported ones too, with a per-object "Even dashes" tick box (`stroke.even_dashes: false`) for
  PowerPoint's spacing. Exports carry each dash as its own subpath with a solid stroke (dots are
  0.001 pt round-capped strokes; square caps become flat ones on lengthened dashes, which PDF and
  SVG draw alike); outlines re-cut the same dashes.
- **Window layout (2026-10-31, as the app grew crowded):** PowerPoint-style ribbon tabs (Home,
  Arrange, View) with labelled groups, and Snap, Check, Export, Settings and Help always in view at
  the right of the tab row; the drawing tools in a vertical bar beside the page (between the
  Pages/Objects panel and the page, as in Illustrator and Photoshop); the properties panel in tabs
  (Arrange, Style, Text, Picture) over sections that fold away, like PowerPoint's Format pane. The
  last tab for each kind of object and the folded sections are remembered (prefs). Zoom is also in
  the status bar, since a different tab is usually open. The earlier View menu is now the View tab.
- **Align and distribute (2026-10-31), Illustrator's full set (Matthew's choice):** align ×6;
  distribute by edges or centres ×6 (outer objects stay, or go to the page's edges when aligning
  to the page); equal spacing across/down, or an exact gap counted out from the key object (or the
  first object); align to selection / key object / page. Clicking (without dragging) one of several
  selected objects makes it the key object and switches to key mode, as in Illustrator; clicking it
  again stops. Controls in the ribbon's Arrange tab and the properties panel stay in step.
- **Connectors (2026-10-31):** line and arrow ends attach to connection points and follow them
  (`start_link` / `end_link`: {item, site}). Points come from each shape's own outline (Matthew's
  choice): corners (sharp ones and rounded corners' middles) and side middles; 8 points round
  smooth outlines; ends of open ones; frame corners and side middles for pictures, text boxes and
  groups; a line's ends and middle; and on dashed outlines each dash's start, middle and end (his
  reading of "connect to either end of the dash, or the middle"). The engine gives shapes' points
  as fractions of the frame (connect.py), so the editor follows resizes and turns at once and
  takes the exact points when the engine answers. Links are kept up inside every change's undo
  step; a link to a deleted object is dropped, one whose dash has gone takes the nearest dash.
  Holding ⌘/Ctrl drops an end unattached (the same override as snapping); moving a line on its own
  (drag, arrows, align) lets go; copies keep links only among themselves.
- **Recovery copies (2026-10-31):** kept per unsaved document in the settings folder's
  `autosave/`; the recovery offer and Settings can delete them (each delete warns first). A
  recovered document keeps its copy's name, so saving it clears the copy.
- **Collaborators (2026-10-31):** installers that set up conda too (Matthew's choice):
  `install-mac.command` / `install-windows.bat` install Miniforge if there's no conda, then the
  environment, a non-editable FigAssemble and the app or shortcuts; re-running updates. Docs:
  README (install, quick start, feedback) + tutorial + user guide, with screenshots of neutral
  sample plots (his unpublished figures stay out); feedback through GitHub issue forms.
- **Objects list (2026-11-01):** a tree of the page's objects, front to back, groups opening to
  show their parts (Matthew's choice, over a list of one level). The selection stays at one
  working level, as before, so picking a part of a group in the list works inside that group
  (isolation mode), as double-clicking it on the page does. Rows drag like the Finder's: the row
  follows the pointer and the others slide apart (his choice, over a line marking the place);
  the depth a row goes to follows how far across it's dragged; the page draws the new order while
  dragging (a copy of the page put back for each new place, one undo step on letting go). Rows go
  into and out of groups and onto pages in the Pages list; a clipping mask's shape stays its top
  part. The Pages list drags the same way (layers.js, listdrag.js).
- **PowerPoint slides in (2026-11-01):** Open goes through a slide picker (a picture of each
  slide, drawn by the PDF export at 320 px; one or several chosen), and a deck imported once is
  kept for the picker and the slides then chosen. Where slides dropped on the window go depends
  on where they land (Matthew's choice): on the page, their objects at the drop point; in the
  Pages list, new pages in the gap, a line showing where meanwhile. Copied slides and shapes come
  from PowerPoint's own clipboard formats, checked by having PowerPoint for Mac 16.114 copy from
  a test deck: copied slides are a small deck with its parts under clipboard/ ("PowerPoint 14.0
  Slides Package"), copied shapes a DrawingML locked canvas ("Art::GVML ClipFormat") whose shapes
  are rewrapped as PresentationML's and read by the slide importer, plus an OLE object descriptor
  naming the deck they came from. A slide dragged out of PowerPoint carries only a reference
  (com.microsoft.PowerPoint.internal.Slide: session id, slide id, in-memory creation id), so the
  slide is found by its id in the decks PowerPoint's process has open (lsof) and read as last
  saved, asking which deck when several match (slide ids start at 256 in every deck); his choice,
  over not taking slide drags. The web view, which doesn't take drags of types it doesn't know, is
  registered for PowerPoint's and its drag methods are wrapped (macdrag.py, powerpoint.py,
  importers/gvml.py). PowerPoint also offers its copied slides as web data ("ppt/slides"), which a
  Chromium web view (Windows) may be handed for a drag; that's taken too, untested.
- **Slide drags followed by hand; blank pages take the slide's size (2026-11-01):** a real slide
  drag out of PowerPoint for Mac 16.114 never reached the web view: a logging copy of the window
  got no drag calls at all, though the drag pasteboard held the slide's reference. PowerPoint lets
  only its own windows take slide thumbnails, so macOS offers other apps nothing. Matthew chose to
  take them anyway, over a note suggesting copy and paste. So macdrag.SlideWatch follows the drag
  itself, needing no permission: a global monitor sees the mouse go down in another app, and until
  it comes up the drag pasteboard is watched (its change count). Once it holds PowerPoint's slide
  reference, the pointer is followed (CGEventGetLocation, and CGWindowListCopyWindowInfo for the
  frontmost window there, looking through layers 100 and up such as the drag image), the editor
  shows where the slides would go while it's over the window, and letting go there is a drop.
  PowerPoint still animates the slide flying back. Pressing Escape over the window and then
  letting go still counts as a drop (nothing shows that the drag ended). A drag AppKit does hand
  the web view is left to the wrapped methods, so it isn't dropped twice. Slides added to a page
  with no objects (guides don't count) make it the first slide, at the slide's size with its
  objects where they were, keeping the page's name and guides; more slides become pages after it
  (Matthew's choices, over all of them on one page, and over only pages at the default size).
  Copied shapes don't change the page. While dragged slides are read (5.5 s the first time for
  a large deck of figures), the drop area stays on the page saying so.
- **Mac menu bar (2026-11-01):** macOS names an app from its main bundle, and conda's Python has
  none, so the menu bar said "python". FigAssemble.app now links the environment's Python into
  itself and runs it from there, which makes the app the main bundle (its name, icon and
  version), as for any Mac app; started from a terminal, it sets LaunchServices' display name
  (the call Java's -Xdock:name makes). Changing the bundle's CFBundleName at run time doesn't
  rename it. pywebview's menus have no shortcuts, so the menu bar is made with AppKit
  (macmenu.py) from the editor's description of it: FigAssemble, File, Edit, View, Window, Help
  (Matthew's choice of menus; not Insert or Arrange, and Mac only, since on Windows the ribbon
  does this job, as in Office). Menu items run the editor's commands as their keys do, and wait
  while a dialog is open. Cut, Copy, Paste, Undo, Redo, Select All and Delete ask the editor
  first: in a text field they're the web view's own. macOS's Dictation and Emoji & Symbols items
  in Edit have hidden copies for their other shortcuts, so they look doubled when the menu is
  read, though each shows once.
- **Arrow keys follow the zoom (2026-11-01):** a press moves the smallest round amount (1, 2 or 5
  times a power of ten) in the units the panels show that is at least 1 pt at 100% zoom, so it's
  about the same distance on screen (1⅓ to 3⅓ px) at any zoom and positions stay on round numbers:
  in centimetres 0.05 cm at 100%, 0.01 cm at 400%, 0.2 cm at 25% (Matthew's choices, over round
  steps in points and over an exact screen distance with uneven numbers). Shift is 10 steps,
  Option a tenth, Option+Shift resizes by one. Per his rule for automatic behaviour, the status
  bar shows the step and a click there switches to the old fixed 1 pt (the nudge_zoom setting;
  also View ▸ Arrow Keys Follow the Zoom and the command search).
- **Undoing an update from a linked file (2026-11-01):** the editor looks at linked files every
  2 s, and an update is an undo step. Undoing it used to last only until the next look, which
  found the file newer than the picture and updated it again as a new step, so ⌘Z could never get
  past it. Now the version undone is remembered (by its copies' content hashes) and not taken
  again; the next save of the file, or Redo, brings an update. It's remembered only while the
  document is open, so a document opened later catches up with its files. Looks also wait while
  a drag is in progress. Found by the linked-files tests (tests/test_links.py, linkedFileChecks).
- **Updates (2026-11-01):** installed copies update themselves from GitHub releases, for rolling
  out to early adopters while changes come often. Matthew's choices: the repository stays private
  for now, with a one-time GitHub sign-in in FigAssemble, made so that going public needs no
  change; new versions install automatically by default, with Ask me first and Off in Settings
  (his rule for automatic behaviour: the setting always shows its state, and Check for updates
  works whichever is chosen); releases come from a command on his Mac, with a backup of the key
  for a new computer; going back a version, test versions first, and a warning on opening a
  document saved by a newer version. How:
  - *Not Sparkle or WinSparkle:* they replace a self-contained app, and FigAssemble lives in a
    conda environment made by its installers. An update runs the new version's own installer
    (already tested in CI on fresh machines) in an update mode, after FigAssemble closes: Windows
    can't replace files a running Python has open. conda runs only when `environment.yml`
    changed (its SHA-256 is kept in the environment), so most updates take seconds.
  - *Signed with a key on Matthew's Mac, not just downloaded from GitHub:* collaborators on a
    personal repository can push and make releases, so GitHub's word isn't enough for code that
    installs on everyone's computer. Ed25519 (`cryptography`), the public keys in
    `data/updates.json`; a key in GitHub's secrets would be readable by the same collaborators.
  - *Signing in:* a GitHub App with Contents: read-only, signed in to with a code (the device
    flow, which needs no client secret, so nothing secret ships in the app). Its tokens can read
    only repositories the app is installed on and the person can see, and expire after 8 hours
    (renewed with a refresh token). An OAuth app would need the `repo` scope: every private
    repository the person has, writable. A token built into the app would leak with it and
    couldn't be replaced once it expired. Without a sign-in FigAssemble looks anyway, so a
    public repository needs none. A sign-in is never sent on to the host GitHub redirects
    downloads to (redirects are followed by hand).
  - *Install at quit:* a downloaded update installs when the last FigAssemble window closes, or
    straight away with Restart now (unsaved work saved first, or kept as a recovery copy). It
    stops trying by itself after two failures. A FigAssemble opened while one installs waits.
  - *Test versions* are GitHub pre-releases; `release.py promote` makes one a full release,
    without rebuilding it (the signature covers the files, not the channel). *Going back*
    installs the newest release before the running version and skips the one gone back from
    until a newer one comes.
  - *Newer documents:* every save records the version that saved it (`meta.saved_by`); an older
    version says so on opening, and a document in a newer format version explains itself
    instead of "unsupported document version".
- **Repository:** `~/Projects/FigAssemble`, private GitHub repo `matthewwdavis/FigAssemble`;
  tests run on Windows and Linux via GitHub Actions (macOS is tested locally).
  "FigAssemble" is a working name; a fun name comes later.
- **Acceptance test for the first version:** rebuild the last slide of
  `Bushy_Top/Figures/Paper_Figures/genomic_instabilities_figure.pptx` (identical to slide 7
  of `nature_submission_figures.pptx`, "figure3" in `~/Desktop/test_figure_print`) and match
  or beat `compose_vector_figures.py`'s output (`figure3_pdf.pdf`, `figure3_svg.pdf`), using
  PowerPoint's own export (`figure3_powerpoint.pdf`) as the layout reference.

## Architecture

```
figassemble/
  model.py        document JSON: defaults, validation, ids
  docfile.py      .figasm container (zip: document.json + embedded assets)
  assets.py       linked/embedded files, sibling variants, intrinsic sizes, change detection
  geometry.py     matrices, paths, corner rounding, arrowheads, dashes
  presets.py      PowerPoint's 187 preset shapes from their formulas; handles; the Shapes menu
  dashes.py       even dash spacing: dashes fitted to corners, ends and closed curves
  connect.py      connection points for attaching line ends (corners, side middles, dashes)
  data/           presets.json (from the standard's presetShapeDefinitions.xml)
  fonts.py        font discovery and fallback; metrics
  textlayout.py   paragraphs/runs -> positioned glyph runs (PowerPoint-compatible)
  resolve.py      items -> drawing primitives in page space (shared by every writer and the UI)
  export/         pdfwriter (+ font embedding), svgwriter, raster, conversions, preflight
  importers/      PowerPoint (.pptx) slides -> pages; relinking media to originals
  app/            local HTTP server + JSON-RPC, pywebview window, native drag and drop
  ui/             HTML/CSS/JS editor (no build step, no framework); canvas.js draws the page,
                  grid and guides and does the snapping, rulers.js the rulers
  updates.py      updates: GitHub releases, signatures, the GitHub sign-in, installing at quit
  cli.py          `figassemble` (GUI), `figassemble export|import-pptx|update`
```

- **Python is the single source of geometry and text layout.** The UI sends items to the
  engine and draws the SVG fragments it returns, so what is on screen and what is exported
  come from the same code. During drags the UI previews with transforms and refreshes from
  the engine afterwards.
- **The UI holds the document state** (JSON) and undo history; the engine is stateless
  apart from an asset cache. Save, export and preflight send the whole document.
- **Coordinates:** points (1/72 in), page space, origin top-left, y down. Rotation is
  clockwise about the frame centre; flips apply before rotation (same as PowerPoint).
- **Document file:** `.figasm`, a zip holding `document.json` (stored uncompressed, readable
  with `unzip -p`) and `assets/<sha256>.<ext>` copies of every placed file and its variants.
- **Shapes follow DrawingML** (PowerPoint's model): preset names, adjust values, line
  ends, dash presets and text-box insets, so imported slides render the same and the
  behaviour is familiar.
- **Preset shapes come from PowerPoint's own definitions.** The Office Open XML standard
  (ECMA-376 Part 1) publishes the formulas of all 187 presets; `tools/build_presets.py`
  turns them into `data/presets.json`, and `presets.py` evaluates them in points for each
  frame: paths, the text area, darker/lighter faces (cubes, cylinders) and handle positions.
  Every preset in a .pptx imports as itself (Matthew's decks use braces, block arrows,
  equals signs...). Items store adjust values as fractions or, for angles, degrees.
- **Adjust handles** are solved numerically: the engine searches each handle's range for
  the adjust value that puts it nearest the pointer (and polishes two-value handles with
  Newton steps), so every preset's handles work without per-shape code.

# mosaic design

mosaic is a small desktop app for assembling multi-panel scientific figures:
place plots and images on a page of any size, add text, lines, arrows and shapes,
and export PDF, SVG, PNG or TIFF without the format conversions that degrade
PowerPoint figures.

## Core rule: never convert a file unless the output format forces it

PowerPoint rewrites inserted SVGs, wraps inserted PDFs in EMF frames, and its PDF
export draws every picture as a ~300 dpi bitmap (some JPEG). mosaic keeps each
placed file in its original form and writes it once, straight into the output:

| Placed file | PDF export | SVG export | PNG / TIFF export |
|---|---|---|---|
| PDF | page embedded unchanged as a Form XObject (qpdf/pikepdf) | PDF -> SVG conversion, only if no SVG copy exists | rendered once from the vectors (PDFium) |
| SVG | SVG -> PDF conversion, only if no PDF copy exists | markup copied in unchanged (IDs prefixed) | rendered from the PDF copy or converted SVG |
| PNG / JPEG / TIFF | image data embedded losslessly (JPEG bytes passed through) | embedded as a data URI, byte-identical | resampled once to the export DPI |

R notebooks save every plot as PDF + SVG + PNG under one name. mosaic links all
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
- **Page sizes:** new pages are A4. The Page panel has a Standard size dropdown (paper, slides
  and posters since 2026-11-02, below), a Journal dropdown and a Figure type dropdown; a journal type sets the column
  width and the journal's maximum figure depth (e.g. Nature 90/180 mm x 170 mm; Science
  5.7/12.1/18.4 cm x 19.9 cm, leaving room for the legend). 14 journals (2026-10-31): Cell, G3,
  Genetics, Genome Biology, Genome Research, Heredity, MBE, Molecular Plant, Nature, New
  Phytologist, Plant Cell, PLOS Genetics, PNAS, Science; Horticulture Research added 2026-11-05
  and The Plant Journal 2026-11-06 (below). Where a journal publishes no sizes (Genetics, G3,
  Genome Research, Heredity, MBE, Horticulture Research; The Plant Journal's depth), they were
  measured from a published 2025-26 open-access article, as Matthew chose; the app's note says so. On journal pages "Fit to
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
  again stops (an Option-click since 11-10, below). Controls in the ribbon's Arrange tab and the properties panel stay in step.
  - *Arrange tab follows the selection (2026-11-10, Matthew's choices):* two or more objects show
    it (text boxes too, ahead of the Text section's switch to Home); one or none brings the tab
    before back unless another was picked meanwhile; a Settings switch, on by default
    (`several_arrange_tab`). The one group Group makes keeps it showing, so the tab doesn't flip
    away under the button just pressed; a group selected by itself doesn't show it.
    `panels.followSelection` holds both rules and one tab to go back to. The tabs' panels now
    share one grid cell (hidden ones invisible but still taking room), since Arrange was 1.4 px
    taller than Home and the page jumped by that whenever the tab changed by itself.
  - *Position and size strip (2026-11-10, Matthew's choices):* X, Y, Width and Height moved from
    the Arrange tab to a strip above the properties panel's tabs, sticky with them, so they're in
    view on the Picture and Style tabs too (where pictures, shapes and lines open) and follow a
    handle drag (`inspector.sizeStrip`, refreshValues). Groups got editable fields: their
    outline's, a width or height scaling everything from the top-left (`scaleItem`, as Match size
    and Transform Again do; groups have no resize handles). Lines keep their points in Arrange;
    area fills and scale bars have none. Several objects selected show no size.
  - *Dash spacing and dash pictures (2026-11-10, Matthew's choices):* `stroke.dash_spacing`
    scales a dash style's gaps (dash_pattern in geometry.py; the dashes keep their length), shown
    as a percentage in the Line section; PowerPoint gets a custDash. The Dash menu's pictures are
    drawn at 2 pt: at the line's 1 pt, Dot and Round dot all but vanished in WebKit (checked in a
    WKWebView snapshot).
  - *Key objects (2026-11-10, Matthew's choices):* he found Top aligning to the first selected
    object, not the highest. A plain click on one of several selected objects had switched Align
    to into Key mode, which was saved in his settings, and with no key clicked it took the first
    selected. Now an Option-click makes the key (a plain click can't), and it lasts for that
    selection only (`app.keySel`), never saved: once the selection changes, Align to goes back to
    the saved Selection or Page. Same width / Same height with no key match the widest / tallest.
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
- **Journal styles for panel labels and text (2026-11-04):** each journal in `journals.py` has its
  labels' look (font, size, bold, case, and form: "a" or "(a)") and its rules for figure text
  (smallest and largest size, accepted fonts). Matthew chose: all of a page's labels follow its
  journal; the Label tool's labels and lone-letter text boxes count; journals that don't say how
  labels look get them measured from published figures; and Check follows each journal's text
  sizes and fonts.
  - *Sources:* the journals' own guidelines, read by three research agents on 2026-11-04 (quotes
    and URLs). Some publisher pages refuse scripted reads, so archived copies of the same official
    URLs were read instead.
    Measured labels come from the publisher PDFs of 2025–26 open-access articles in PubMed
    Central's open data (vector labels read exactly; pictured ones from letter height and weight).
    Where stated and printed differ, the stated rule wins: Genome Research asks for 12 pt and
    prints about 9 pt. The Plant Cell's current page gives 12 pt bold but no case; its figures now
    use lowercase, though its 2020 guide says capitals. Molecular Plant had no figure PDF to
    measure, so its labels follow Cell's measured ones (same publisher and figure rules).
  - *Restyling:* choosing a journal restyles the page's labels in the same undo step. With no
    journal before, labels take its whole look; switching journals changes only what still matches
    the old journal's look, so hand changes stay (like text styles' overrides; `labels.js`).
  - *Check:* per page, the journal's smallest and largest sizes (labels left out of the largest),
    its fonts (from mosaic's text and placed PDFs' fonts; "only" lists warn, preferred ones note),
    and labels not in its style. Sizes a journal gives roughly ("about 6–8 pt") are notes. Pages
    without a journal keep the 5 pt smallest size.
- **Journal checks: lines, resolution and files (2026-11-04):** each journal in `journals.py` also has
  its line widths (`lines`), the resolution it asks of each kind of placed picture (`pictures`:
  photo, photo with text or lines, line art, or kinds it wants as vector artwork) and the files it
  takes (`export`: formats, colour, largest file, highest resolution, embedded fonts, alpha
  channels). Matthew chose all three, a guessed picture kind with an override on the Picture tab,
  the publisher's rules where a journal states none (mosaic's 0.25 pt and 300 dpi where nothing is
  stated), and an Export window that flags what the journal doesn't take without changing the
  settings.
  - *Sources:* three research agents on 2026-11-04 (quotes and URLs; archived copies of the same
    official URLs where a site refuses scripted reads). Cell and Molecular Plant take Cell Press's
    rules (Molecular Plant's own 0.35–1.5 pt lines are from a 2023 page, gone since); New
    Phytologist's resolution and files are Wiley's; Heredity's are Nature Portfolio's artwork
    guide's; Genetics, G3, MBE and The Plant Cell take OUP's where they say nothing (OUP calls its
    guide tips). Judgement calls: Heredity's house style says "rules" no thinner than 1 pt without
    saying whether that means figures, so mosaic's 0.25 pt applies; Science's 0.5 pt (its
    instructions page, 2025) over its 2022 guide's 0.28 pt, and that guide's CMYK only as a note;
    Nature's main figures as vector files (its figure guides refuse JPEG, TIFF and PNG, though its
    final-submission page takes TIFF for photos) and 300 dpi photos (one checklist line says
    450); The Plant Cell's current page (TIFF, JPEG, EPS) over its 2020 guide's PDF.
  - *Picture kind:* `picturekind.py` guesses from 16 px blocks of the pixels (flat colour with sharp
    edges is line art; grain everywhere is a photo; one exact colour meeting the grain with a jump
    is something drawn on it). Tuned on scikit-image's and macOS's photos, the example plots and
    photos with letters, scale bars and axes added: all 44 right, JPEG plots included; a labelled
    photo saved as JPEG passes for plain. `picture_kind` on the item overrides it.
  - *Check:* per page, the journal's thinnest line replaces 0.25 pt (thicker than its thickest is a
    note) and each picture is held to the journal's dpi for its kind, or flagged if the journal
    wants that kind as vector artwork. *Export:* `export_check` runs on every change in the window;
    file sizes are checked once written (`size_limits`; a limit asked "where possible" is a note).
- **Horticulture Research (2026-11-05):** the 15th journal (OUP, Nanjing Agricultural University).
  Its instructions (academic.oup.com/hr/pages/general-instructions, read 2026-11-05) give capital
  A, B, C labels at each panel's upper left, 350 dpi pictures and 600 dpi line art (1200 for
  complex), TIFF/EPS/AI/PDF and no Word or JPEG, but no sizes, text or lines; for those they
  link OUP's artwork guide (2022 PDF: text no less than 7 pt in Arial, Times New Roman, Courier
  or Symbol; lines 0.25–1 pt; combination half-tones 600–900 dpi; RGB recommended; fonts
  embedded; "tips rather than strict rules").
  - *Sizes:* measured from three 2026 articles' publisher PDFs (PMC13091401, PMC13102514,
    PMC13255517), identical in all three: 85.7 mm columns, 177.8 mm (7 in) text width, 241.5 mm
    text depth, so 85.5 / 178 x 241 mm by the usual rounding.
  - *Labels:* the journal doesn't restyle authors' figures, so labels vary. In 13 articles (2026),
    12 used capitals, 7 of 12 measured were bold, sizes ran 8.5–16 pt with 10 pt the middle;
    the only label kept as text was 8.95 pt Arial Bold. Matthew chose 10 pt Arial Bold capitals.
  - *Text:* Matthew chose OUP's 7 pt as a note (it's a tip), with its four fonts preferred.
    Genetics, G3 and MBE also fall back on OUP's guide but keep no text rule (his choice: leave
    them). On the way, a journal's rough smallest size ("about") no longer lifts mosaic's 5 pt for
    all pages, so Cell and Molecular Plant pages now warn below 5 pt too (before: only a note).
- **The Plant Journal (2026-11-06):** the 16th journal (Wiley, Society for Experimental Biology),
  listed by its full name as Matthew chose. Wiley's site refuses scripted reads, so its author
  guidelines come from the Wayback Machine's latest copy (2022-10-25): figures 8 cm wide, or up
  to 16.8 cm for full-page composite photographs; lettering "in 8pt Helvetica if possible"; panels
  in lowercase letters. They link Wiley's figure guidelines (2016 PDF; the current
  authorservices.wiley.com page agrees): images 300 dpi, line art 600 dpi and figures with both
  as line art; PDF/EPS for line art, TIFF/PNG for images, any standard type after acceptance;
  under 10 MB each preferred; no line widths or colour mode.
  - *Sizes:* in 17 publisher PDFs (2026) the columns are 79.9 mm and the full width 168.6 mm,
    matching the guidelines, and figures of every kind use the full width, so 80 / 168 mm; the
    text block is 226.5 mm deep (PMC13725933, PMC13732550, PMC13720327 and others), so 226 mm,
    as New Phytologist (also Wiley) states.
  - *Labels:* Wiley re-letters every panel label: in 81 figures from 15 articles, all were
    bracketed, regular weight, about 9 pt (brackets 8.4–8.6 pt tall, capital A 6.5 pt, a 5.0 pt);
    case follows the authors (7 articles (A), 8 (a)). Matthew chose the guidelines' 8 pt Helvetica
    and lowercase, with the published brackets and weight: (a) in regular 8 pt Helvetica.
  - *Text:* Matthew chose 8 pt as a note ("if possible"), with Helvetica preferred.
- **Dangerous mode (2026-11-09):** editing the text of placed PDFs and SVGs, the 2026-11-04 idea
  ("Later" on the roadmap) as Matthew asked for it: a mode switched on in the View menu (and the
  ribbon's View tab, command search), off whenever mosaic opens, with a red status-bar badge;
  everything about a text editable, and movable; each placed copy with its own edits; edits
  re-applied when R saves the file again, those whose text is gone dropped and listed by Check.
  - *Lifting rather than editing in place:* "everything about it" (any font) rules out rewriting
    the file's own strings, so a double-clicked text becomes an ordinary mosaic text box and only
    that text leaves the plot. Only touched texts become objects, so the 11-04 timing worries
    (130-160 labels a figure) don't arise, and untouched text keeps R's kerning and minus signs.
  - *The never-convert rule:* the placed file stays in the document unchanged; the picture keeps
    `lifted_text.hidden` (each text as found: words, size, angle, the middle of its baseline,
    font) and `plottext.derived` makes copies without those texts, cached by content, which the
    editor shows and `with_lifts` gives every export and Check (a synthetic asset per picture,
    never saved). A PDF text-showing operator is swapped for a TJ moving as far, so text after
    it on the line stays put; an SVG `<text>` is removed, part of one hidden.
  - *Matching:* by the same words (a minus sign counts as a hyphen), angle, size within 0.6 pt
    (R's pdf() writes 4.8 pt text at 5 pt) and middle within 1.5 pt or half the size, as R's
    PDF and SVG of one plot sit up to ~1.4 pt apart (it measures text differently for each). The
    box is placed from the copy the editor shows (the SVG under 8 MB, else the PDF).
  - *Boxes:* `lift_box` sets the frame so mosaic's first baseline lands on the plot's, lined up
    as the SVG's text-anchor says (PDFs don't say: left), not auto-fitted (it would grow from the
    left); `followLifted` keeps them on their picture through moves, crops, scaling (sizes too)
    and turns. A copy of the picture alone shows the texts whose boxes still exist elsewhere.
- **Kerning (2026-11-09):** letter pairs set as the font says. Matthew chose: new text kerned at
  every size (with a Kerning box on the Text tab), text from PowerPoint as each run's own setting
  (`kern`, hundredths of a point: kerned from that size up, so PowerPoint's default 12 pt leaves
  figure text unkerned), and saved figures left as they are (a run kerns only with `kern: true`).
  - *Source:* `Face.kern` reads the font's GPOS kern feature (pair positioning, glyph pairs and
    classes, extension lookups), else its kern table; no shaping library. Pairs stop at the
    characters a line can break after, so no kerning crosses a line break.
  - *Exports:* the layout's advances carry the kerning; PDF writes a TJ with the gaps (unkerned
    runs are the same Tj as before); SVG keeps textLength, so a viewer's own kerning is held to
    mosaic's width; PowerPoint gets `kern="100"` (from 1 pt up) or `kern="0"`.
  - *R:* R's pdf() kerns with Adobe's Helvetica AFM (about 250 pairs, "Ty" -120/1000); macOS's
    Helvetica has 105 pairs ("Ty" -55), so lifted text gets closer to R's spacing, not identical.
- **Refresh All Pictures (2026-11-09):** Matthew's choices: re-read everything (every linked file
  whatever its date, an undone update included, and copies saved beside a file since it was
  placed), every page, a Refresh button in the Home tab's File group plus File menu, the page's
  right-click menu and command search, and ⌘⇧R. `refresh_asset(force=True)` re-reads each
  variant and `_new_copies` adds siblings as `new_asset` would (same name, same size within
  0.05 pt; PDF and SVG, PNG only for a picture without vector copies). It's one "Update from file"
  step, so its undo asks first as an automatic update's does, and texts lifted out in dangerous
  mode are matched again in the new files.
- **Text section in the Home tab (2026-11-04):** font, size and the rest in the ribbon, beside the
  properties panel's Text tab (`ui/js/textribbon.js`). Matthew chose all the extra controls
  (superscript and subscript, bigger and smaller, top/middle/bottom, the text style list, line
  spacing), changes to just the highlighted words while typing, a switch to Home and back, and
  text boxes only (one or several; not shapes with text, nor scale bar and bracket labels).
  - *Layout:* two rows of small controls, as in PowerPoint's Font group, no taller than the
    ribbon's other buttons, between Edit and Clipboard (moved there from after Clipboard at
    Matthew's request). The Home tab still fits one row at 1440 px.
  - *While typing:* a change to highlighted words puts what's been typed into the document as
    one undo step and the change as another, then fills the editor again with the same words
    highlighted (`canvas.retype`). Text and its positions ([paragraph, character]) are read
    from the editor the way typing is read back, so they always agree (`readEditor`). ⌘Z
    before any more typing undoes the change and typing carries on (`canvas.undoTyping`); after
    more typing, ⌘Z is the text's own again. Bold, italic, underline, superscript and subscript
    use the editor's own commands, as their keys do.
  - *Only the caret:* a change applies to what's typed next, through a marker at the caret (a
    zero-width space in a span of the new look, `canvas.pendingStyle`), taken out when the text
    is read back.
  - *The tab:* selecting text shows Home, remembering the tab before. When no text is selected
    any more, that tab comes back, unless one was picked by hand meanwhile. It isn't saved as
    the tab to open with. Settings: `text_home_tab`.
  - *The properties panel's Text tab* now goes through the same changes, so what it changes
    while typing stays when typing ends (before, the editor's copy of the text overwrote it).
- **Closing with unsaved changes (2026-11-03):** asks Save, Don't Save or Cancel, naming the
  figure (`app/closing.py`). Matthew chose the Mac's standard wording, each figure in turn
  when quitting, Don't Save keeping an up-to-date recovery copy, and Windows too.
  - *The question:* on a Mac, a sheet on the window (`app/macclose.py`); on Windows, a message
    box where Yes saves.
  - *Closing a window:* the window stays open while it asks (pywebview's closing event is
    answered "not now"). mosaic then closes it once the editor has saved it
    (`app.saveToClose`) or kept its copy (`app.keepCopy`, waited for up to 5 s).
  - *Quitting:* goes through pywebview's application delegate, with mosaic's own
    `applicationShouldTerminate_` in its place. With unsaved figures that answers "not now" and
    asks about each in turn (front window first). Once each is saved or answered Don't Save,
    mosaic quits itself. A Cancel, or a save that doesn't happen, leaves every window as it was.
    A second quit while it asks is ignored.
  - *Not NSTerminateLater:* while a reply is pending, a second quit (⌘Q again, the Dock) ends
    the app at once without asking the delegate (seen in a test on 2026-11-03: the changes were
    lost). The cost
    of answering "not now" instead: a logout or shutdown is called off, and has to be started
    again once the figures are answered.
  - *Fallback:* pywebview's own two-button question still asks if any of this fails.
- **Collaborators (2026-10-31):** installers that set up conda too (Matthew's choice):
  `install-mac.command` / `install-windows.bat` install Miniforge if there's no conda, then the
  environment, a non-editable mosaic and the app or shortcuts; re-running updates. Docs:
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
- **Selecting several (2026-11-02):** ⌘-click (Ctrl-click on Windows, where Control-click isn't a
  right-click) adds an object at once, so ⌘ held from the press of a drag moves the whole
  selection unsnapped, as in Keynote, PowerPoint and the Finder (Matthew's choice, over a ⌘-drag
  that moves the pressed object alone); on a selected object it takes it away only on letting go
  without a drag. Shift-click still adds or takes away at once. A ⌘- or Shift-press on empty page
  keeps the selection (a missed ⌘-click loses nothing) and its box adds. With Option held as the
  box is let go, it takes what it touches where a click would pick it: a line within half its
  width, an area fill's area, anything else its frame. **Select Same** (selectsame.js, his
  choice of extras) matches any selected object's fill colour, line colour or width, fill and line
  (with dash), the fonts, sizes or colours of its text runs, or its kind (a preset's name, text
  box, line or arrow, picture, equation, zoom inset, one symbol's copies); "none" matches "none".
  It keeps to the working level like every selection, so a group's parts count only inside it.
- **Documents and windows (2026-11-02):** a .mosaic double-clicked opens in mosaic, and each
  document has a window of its own (Matthew's choice, over replacing the open figure). The Mac
  app owns the types (`io.github.matthewwdavis.mosaic.document` for .mosaic, and
  `org.figassemble.figasm` for .figasm, from when it was called FigAssemble; declared in its
  Info.plist, registered with LaunchServices as the app is made) and takes decks as an
  alternative, for Open With. macOS
  sends documents as an "open documents" Apple event, at launch and while running; mosaic
  installs its own handler for it (macopen.py) in applicationWillFinishLaunching, as Apple
  documents, rather than going through pywebview's delegate. The windows share one process and
  one engine: each editor sends its window's number with every request, so dialogs, the title
  and the close confirmation go to the right window. New, Open and Open Recent use the window in
  front if it's blank (nothing on any page, nothing unsaved, no dialog open; his rule), else open
  a new one. A document open already comes to the front, and closing the last window quits (his
  choice, over staying open with no windows). Documents arriving before the first editor has
  started wait until the launch has finished (applicationDidFinishLaunching), so a double-click
  that starts mosaic opens the document in the first window. The Mac menu bar works in the
  window in front, which sends its own ticks when it comes to the front. On Windows the installer
  registers the type in HKEY_CURRENT_USER (no administrator needed), and each double-click starts a
  mosaic of its own, as Notepad does (his choice, over sending it to the open window).
  Rulers, grid, guides, snap and the interface's state are each window's own (his choice), while
  Settings are shared: a window takes changes from another when it comes to the front. A .mosaic
  dropped on the window adds its pages (his choice, over opening it), with the swatches,
  symbols, styles and pictures they use. One that's the same here is shared, and one whose id
  means something else here gets a new id. Recovery copies a window is writing are locked
  (flock, or msvcrt on Windows), so another mosaic running at the same time doesn't offer
  them back as lost work. The lock goes when the window closes or the process ends, however it
  ends.
- **Slides, posters and the Size menu (2026-11-02, Matthew's choices):** the standard sizes come
  in groups: paper (A4, US Letter), slides as PowerPoint makes them (16:9 its default, exactly
  960 x 540 pt; 4:3 its old Standard; 16:10) and posters (48 x 36 in, A0). He didn't take the
  smaller 16:9 (Google Slides' 10 x 5.625 in). Size, in the Home tab, offers these and every
  journal's figure sizes (one Journal submenu, as menus here go one level deep) whatever is
  selected, with Swap width and height and Custom size…; the Page panel shows only with nothing
  selected, which hid the sizes (his choice, recommended). Settings → New documents gives the
  size new documents start at, any of the same sizes (his choice); a size this version doesn't
  have falls back to A4.
- **Colour vision side by side (2026-11-02, Matthew's choices):** Side by side (View tab, beside
  the preview's list) shows the page normally and with each preview at once, from copies of what
  the page shows: each copy has its own colour matrix filter, loses its ids (so its references
  to clips and gradients reach the page's own definitions) and isolation mode's fading. Clicking
  one previews it on the page. Command search finds each preview by "colour blind", "color
  blind" or a kind's name. He didn't take a shortcut to step through the views.
- **Deleting the only page (2026-11-02, Matthew's choices):** a document always has a page, so
  deleting the only one puts an empty page like it in its place (its size, standard or journal
  size, background and guides, named Page 1) rather than refusing; one with objects asks first, as
  any page does. + Add page makes the same empty page, now keeping the page's standard or journal
  size too.
- **Export and report windows close when done (2026-11-02, Matthew's choices):** once the files
  are written the window closes, even with warnings (his choice), and a note at the top of the
  page names them, with Show in Finder (Explorer) and the warnings. It goes after 10 seconds but
  not while pointed at or focused, and one with warnings stays until closed so they're read (a
  failed export keeps its window, with the error). The figure report's window does the same. The
  notes along the top of the page now stack in one column (the colour vision note, then this
  one), and presses on any note stay off the page: before, a click on a note's button also reached
  the canvas underneath, which could select or deselect what lay under the note. Fonts embedded for
  placed PDFs are reported as a note, not a warning (export results have `notes` beside
  `warnings`), so they show as a plain line and don't keep the note open (his choice).
- **Picture menus; every outline choice on every object (2026-11-02, Matthew's choices):** each
  list in the Style tab is a picture menu (inspector.pictureField): a button showing the choice's
  picture and name, opening a menu (contextmenu.js, with pictures, group headings and greyed lines)
  with a picture of every choice in the object's own colours and width (his choice over picture
  buttons or a picture beside the list). Dashes, arrowheads and outlines are drawn by the engine
  (one resolve request for a menu's pictures, kept by what they draw), so they look as on the page;
  ends, corners, fills and routes are simple SVG drawings (pictures.js). This replaces the 10-31
  rule of offering only outline choices that look different (his request): lines and open shapes
  now have Left side and Right side (left or right going from start to end; resolve.with_outline
  clips Both sides to a one-sided buffer of the line drawn whole, carried past its ends for the
  arrowheads), his choice over "as if the ends were joined"; a fill with no line has Both sides (a
  band along the edge, half over the fill). Choices that change nothing yet are greyed out with the
  reason (his choice over hiding them or allowing them): Gaps on a solid line, Sides on something
  with neither line nor fill, an arrowhead's size before there's an arrowhead.
- **Guides from a click on a ruler; a guide's menu (2026-11-02, Matthew's choices):** clicking a
  ruler puts a guide at that spot, across it (the top ruler a vertical guide), while a drag out of
  a ruler still brings one out along it (his choice, as in Illustrator). He chose rounding to the
  ruler's ticks over snapping to objects. The visible ticks are 5 mm apart at 100% (finer ones would
  crowd), so a click rounds to the finest step that divides them and is at least 2.5 px on screen:
  1 mm at 100%, and a click on a tick lands on it. ⌘ (Ctrl) or Snap off gives exactly where
  clicked, per his rule that automatic behaviour has an override. Pointing at a ruler previews
  the guide with its position (his extra). A press that moves less than 4 px is a click. A guide's
  right-click menu (on the page where no object covers it, or its mark on a ruler) has Remove
  guide, Remove all guides and Hide guides (his choices; not under objects).
- **Where a fill stops (2026-11-03, Matthew's choices):** a fill stops at its lines' middle (as
  drawn, the default: his choice, so nothing changes), their inner edge or their outer edge
  (fill_reach), for a shape's own fill and for an area fill (his choice). It shows only in the gaps
  of dashed or dotted lines or through see-through ones, so the list is greyed out otherwise.
  skia-pathops traces each line's whole outline, dashes left out (fillreach.reach): inner is the
  fill less what the lines cover, outer the fill with what they cover, kept to the area grown by
  the widest half line so lines running on past an area's corner add no stubs. Curves stay curves.
  Area fills keep finding their area from the lines' centres; only the drawn fill changes.
  PowerPoint export takes such a shape as an exact picture; an area fill's freeform takes the
  drawn area. Pathfinder's skia conversions moved into fillreach.py.
- **Clicking through empty shapes (2026-11-03, Matthew's choices):** a shape with no fill, or a
  fully clear one, is picked only by its line (and its text: his choice), so a click inside it
  reaches what's underneath; a fill you can see catches clicks (his choice over faint fills too).
  Shapes are picked by what's drawn: the engine sends each shape's own fill and line paths with its
  drawing (resolve.shape_outline), and the canvas tests them with a 2D canvas's isPointInPath and
  isPointInStroke (canvas.hits), shifted for a move since (a move doesn't redraw); a shape not yet
  drawn as it is goes by its frame. An empty box's text counts by its drawn text's box. A selected
  empty shape drags from inside, and a click there without a drag picks what's under it (⌘: adds
  it) (his choice). Text boxes, pictures, lines and the rest keep their hit tests.
- **Pages dragged between windows (2026-11-03, Matthew's choices):** a page dragged out of one
  window's Pages list into another mosaic window is copied there (his choice over moving it): into
  its Pages list where a line shows, or onto its page, after the page showing (a blank page takes
  its place), as for a dropped .mosaic file (his choice), arriving as a one-page figure through
  addFigurePages with its pictures, swatches, symbols and styles. The windows share one process, so
  the source's drag (listDrag's `away`: the pointer outside the window, still captured) asks
  api.page_drag_over / page_drop, which find the other window under the real pointer with nothing
  covering it (macdrag.page_target, Sense.where) and call its editor (FA.pageDragOver / pageDrop)
  with the point in it. Mac only for now: Windows would need its own pointer and window lookup.
- **Around the page (2026-11-03, Matthew's choices):** the grey area works like the page. Scrolling
  goes past the page's edges (it's no longer held centred while it fits: this replaces the 10-31
  rule), stopping while the last 64 px of the page and its objects are in view (canvas.keepInReach),
  so nothing gets lost; Fit (⌘0) and Centre page (⌘⇧0) still centre it. Selecting, moving,
  resizing, drawing, dropping and pasting work there; Enter with a drawing tool places the shape in
  the middle of the view even off the page. Objects can be parked wholly off the page and save with
  the document; exports leave them out (PowerPoint export now too) and cut what sticks out at the
  page's edge (his choice, as before), and they're drawn as normal (his choice over faded). Fit page
  to content ignores parked objects. A click picks an object by all that shows of it, its line's
  or border's outer half and its outline included, not only its frame and 4 px. He reported that
  clicks on an object's part outside the page did nothing; it didn't reproduce (clicks select there
  in Chrome and in the app's WebKit window, with real clicks too, now a smoke check), and his
  figure's panel labels stick out only 2-3 pt. Fixed on the way: Fit page to content used where
  objects were last drawn, so it went wrong after moving them (a move only shifts the drawing).
- **Zoom inset shapes (2026-11-03, Matthew's choices):** a zoom inset can be a rectangle, a rounded
  rectangle, an ellipse or a circle (Circle stays round when resized, as well as a free Ellipse: his
  choice over Ellipse with Shift). Chosen when adding (▾ beside Zoom inset; a plain click is still a
  rectangle) and later (Zoom shape in the box's and the inset's Zoom inset sections). The box is a
  shape (geom rect + rounding, or ellipse; zoom.circle keeps its frame square); the inset is cropped
  to the box's shape (mask), the same unless zoom.own_shapes (his choice: the same, with a way to
  make one different later; an inset on its own keeps the box's proportions). Rounding starts at 20%,
  the same share on both, so it scales up (his choice). The lines are the two edges of the convex
  hull of both outlines that bridge them (outlines sampled finely enough to stay within 0.01 pt);
  two rectangles keep the corner rule, so existing figures don't change. Found on the way: the
  canvas clipped a picture cropped to a shape in its file's units (a clip-path on the nested svg),
  so a scaled or cropped one showed the wrong area; it's now clipped by a group in the frame's
  units. The zoom tool takes the picture under the pointer even when another box is on top.
- **Renamed mosaic (2026-11-03, Matthew's choices):** FigAssemble became mosaic, always lower
  case, wherever people see it and inside too: the Python package and command `mosaic`, MOSAIC_*
  settings, the Mac app's id io.github.matthewwdavis.mosaic, Windows' mosaic.Document and
  mosaic.Deck, the GitHub repo matthewwdavis/mosaic and the folder ~/Projects/mosaic. Documents
  save as .mosaic; a .figasm opens, and saves as itself (its "figassemble" format key reads as
  "mosaic"). The settings folder is ~/.mosaic, made the first time from ~/.figassemble (settings,
  recovery copies renamed .mosaic, math fonts; not the caches), which stays as it was. The GitHub
  sign-in moves to "mosaic GitHub sign-in", read once from FigAssemble's entry. The release key's
  Keychain entry and its backup's prefix keep FigAssemble's names, since renaming them means key
  steps only Matthew runs. The icon is figure panels fitted together as a mosaic of tiles, in the
  Okabe-Ito colours (his choice over a tiled "m" and stone-like tesserae).
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
  none, so the menu bar said "python". mosaic.app now links the environment's Python into
  itself and runs it from there, which makes the app the main bundle (its name, icon and
  version), as for any Mac app; started from a terminal, it sets LaunchServices' display name
  (the call Java's -Xdock:name makes). Changing the bundle's CFBundleName at run time doesn't
  rename it. pywebview's menus have no shortcuts, so the menu bar is made with AppKit
  (macmenu.py) from the editor's description of it: mosaic, File, Edit, View, Window, Help
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
  for now, with a one-time GitHub sign-in in mosaic, made so that going public needs no
  change; new versions install automatically by default, with Ask me first and Off in Settings
  (his rule for automatic behaviour: the setting always shows its state, and Check for updates
  works whichever is chosen); releases come from a command on his Mac, with a backup of the key
  for a new computer; going back a version, test versions first, and a warning on opening a
  document saved by a newer version. How:
  - *Not Sparkle or WinSparkle:* they replace a self-contained app, and mosaic lives in a
    conda environment made by its installers. An update runs the new version's own installer
    (already tested in CI on fresh machines) in an update mode, after mosaic closes: Windows
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
    couldn't be replaced once it expired. Without a sign-in mosaic looks anyway, so a
    public repository needs none. A sign-in is never sent on to the host GitHub redirects
    downloads to (redirects are followed by hand).
  - *Install at quit:* a downloaded update installs when the last mosaic window closes, or
    straight away with Restart now (unsaved work saved first, or kept as a recovery copy). It
    stops trying by itself after two failures. A mosaic opened while one installs waits.
  - *Test versions* are GitHub pre-releases; `release.py promote` makes one a full release,
    without rebuilding it (the signature covers the files, not the channel). *Going back*
    installs the newest release before the running version and skips the one gone back from
    until a newer one comes.
  - *Newer documents:* every save records the version that saved it (`meta.saved_by`); an older
    version says so on opening, and a document in a newer format version explains itself
    instead of "unsupported document version".
- **Licenses, for a public release (2026-11-01):** MIT for the code and CC BY 4.0 for the
  documentation and pictures (Matthew's choice; Creative Commons advises against its licenses
  for software). Checked for others' material first: no code from other projects; the icons
  were drawn for mosaic, but compared with Feather, Lucide and Tabler (6,705 icons) four
  simple ones are identical to Feather's and six follow Feather's or Lucide's designs, which he
  chose to keep with credit (both are MIT/ISC); the twelve RStudio-favourite themes keep their
  names, with their authors credited; PowerPoint's shape formulas carry Ecma's notice, whose
  terms allow implementing the standard in products. All in THIRD_PARTY_NOTICES.md. Mentions of
  his unpublished manuscript decks and scripts were reworded out of the current files (they
  remain in the git history). Open: whether UC Davis, as his employer, should be the copyright
  holder.
- **Repository:** `~/Projects/mosaic`, private GitHub repo `matthewwdavis/mosaic`;
  tests run on Windows and Linux via GitHub Actions (macOS is tested locally).
  Called FigAssemble, a working name, until 2026-11-03, when Matthew named it mosaic.
- **Acceptance test for the first version:** rebuild a slide of one of Matthew's manuscript
  figure decks and match or beat the figure his own script makes from the same R files (from
  their PDFs, and from their SVGs), using PowerPoint's own export of the slide as the layout
  reference.

## Architecture

```
mosaic/
  model.py        document JSON: defaults, validation, ids
  docfile.py      .mosaic container (zip: document.json + embedded assets)
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
  cli.py          `mosaic` (GUI), `mosaic export|import-pptx|update`
```

- **Python is the single source of geometry and text layout.** The UI sends items to the
  engine and draws the SVG fragments it returns, so what is on screen and what is exported
  come from the same code. During drags the UI previews with transforms and refreshes from
  the engine afterwards.
- **The UI holds the document state** (JSON) and undo history; the engine is stateless
  apart from an asset cache. Save, export and preflight send the whole document.
- **Coordinates:** points (1/72 in), page space, origin top-left, y down. Rotation is
  clockwise about the frame centre; flips apply before rotation (same as PowerPoint).
- **Document file:** `.mosaic`, a zip holding `document.json` (stored uncompressed, readable
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

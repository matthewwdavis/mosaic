# Roadmap

## First version

- [x] Repository, environment, design decisions
- [x] Engine: geometry (DrawingML presets, arrowheads, dashes), fonts, PowerPoint-compatible text layout
- [x] Assets: probing, sibling variants (PDF/SVG/PNG under one name), cache, linked + embedded
- [x] Export: PDF (placed PDFs unchanged, lossless images, embedded font subsets), SVG (inline, scoped),
      PNG/TIFF/JPEG via PDFium; CMYK and EPS via Ghostscript (opt-in)
- [x] .mosaic document file; command-line export
- [x] PowerPoint importer (test slide: a manuscript figure slide), relinking to R originals
- [x] Linear gradient fills (PDF shading + soft mask, SVG linearGradient)
- [x] Embed fonts missing from placed PDFs (R's pdf() Helvetica) without touching drawing instructions
- [x] App window: canvas, selection, move/resize/rotate, snapping, crop, text editing, drawing tools,
      panel labels, inspector, pages, objects list, undo/redo, drag and drop (link + embed, Shift-drop
      to replace), clipboard, linked-file refresh, autosave and recovery, export dialog
- [x] Pre-export check (smallest text after scaling, image resolution, conversions, missing links)
- [x] Accessibility, first pass: labelled controls, keyboard operation of the page and lists,
      screen-reader announcements, interface text size, light/dark/high-contrast, reduced motion
- [x] Mac launcher app (`packaging/macos/make_app.py`)
- [x] Editor self-test in headless Chrome and in the app's WebKit window (now 137 checks)
- [x] Curved arrows and lines: smooth curve through draggable points (centripetal Catmull-Rom),
      add/remove points on the page or in the panel, straight-segment mode, PowerPoint arcs
      convertible on demand ("Make editable curve")
- [x] Outlines in a second colour around arrows and shapes; hex codes beside every colour
- [x] Shapes menu: 88 PowerPoint shapes (rectangles, basic shapes, block arrows, stars,
      brackets and braces, equation symbols) drawn from PowerPoint's published formulas, with
      yellow adjust handles; all 187 presets import from .pptx as themselves
- [x] Corner rounding for every straight-edged shape; rounded arrowheads (tip stays on the end point)
- [x] Rulers, a grid and per-page guides; snapping to guides, the grid, objects and equal gaps,
      with a Snap button, ⌘/Ctrl-drag and Escape to override it
- [x] Even dashes: a dash or dot on every corner, bend and line end, whole repeats between them,
      no seams on curves (PowerPoint's corner crowding fixed); per-object switch back
- [x] Faster yellow-handle drags (one request per step, no 30 ms wait)
- [x] Recovery copies can be deleted (recovery offer and Settings, with warnings)
- [x] Ribbon tabs (Home, Arrange, View), drawing tools beside the page, tabbed properties panel
      with folding sections
- [x] Align and distribute as in Illustrator (key object, exact gaps, align to page)
- [x] Connectors: line ends attach to corners, side middles and dashes, and follow their objects
- [x] Docs for collaborators: README (install, quick start, feedback), step-by-step tutorial and
      user guide with screenshots from the real editor (`tools/doc_shots.py`), sample plots in
      `examples/`; one-step installers for Mac and Windows (Miniforge if needed) tested on fresh
      machines in CI; GitHub issue forms for problems and ideas
- [ ] Matthew's first real use: feedback round (in progress)
- [ ] Windows: try the app window and the installer on a real machine (the installer runs in CI)

## Illustrator-style and figure tools (asked for 2026-10-31)

Matthew's choices are in brackets.

- [x] Outlines under see-through lines and arrowheads kept off them (like see-through fills)
- [x] Colour-blind preview of the page (deuteranopia, protanopia, tritanopia, greyscale), never exported
- [x] Smart duplicate on ⌘D (a moved copy sets the offset for the next) and Transform Again on ⌘⇧D [both]
- [x] Copy style / Paste style (⌘⇧C / ⌘⇧V) and a Format Painter button [everything that applies]
- [x] Match sizes: same width / height / size, keeping proportions
- [x] Find and replace fonts
- [x] Document swatches, linked (editing one recolours its objects), saved in the figure plus a
      personal library; colour-blind-safe palettes (Okabe-Ito, Paul Tol) [linked; figure + library]
- [x] Text styles, linked, with changes to one text kept as overrides [linked]
- [x] Isolation mode: double-click a group to edit inside it, nested too [Illustrator's way]
- [x] Crop pictures to a shape, and clipping masks for any objects [both]
- [x] Pathfinder: unite, minus front, intersect, exclude, with exact curves (skia-pathops) [exact]
- [x] Scale bars that stay right when the picture is resized or cropped; scale typed as a pixel
      size, measured from a known length, or read from TIFF / ImageJ / OME metadata [all three]
- [x] Zoom insets: a box on a picture, an enlarged copy of that area, lines between, kept in step
- [x] Significance brackets: a bracket with asterisks or a p-value, tidy heights and gaps

## Ideas from other figure tools (asked for 2026-10-31, second round)

Matthew's choices are in brackets.

- [x] Pathway arrowheads: bar (inhibition), half arrow, open circle, open triangle [all four]
- [x] Superscript and subscript (⌘⇧= / ⌘= while typing, and buttons) and a symbol picker [PowerPoint's keys]
- [x] Command search: type to find and run any command [⌘/]
- [x] Distances on hover: hold Option with something selected to see its distance to what's under the pointer
- [x] More in Check: the thinnest line, placed plots' lines included, and the figure's size against the
      journal's limits [placed plots too]
- [x] Panel labels that stay with their panel (a picture or group) [attached automatically]
- [x] Snapping to placed plots' axis and frame lines and their visible edges [no tick marks]
- [x] Grid layout: rows and columns with set gaps, kept when a panel changes [keep sizes, align top left]
- [x] Symbols: one object used many times, edited once [copies scale lines and text; edited in place]
- [x] Object styles: named, linked line and shape styles, like text styles
- [x] Equations: LaTeX maths drawn as real text [matplotlib mathtext]
- [x] Figure report: each panel's source, copies, size, scale, crop, turns, resolution and scale
      [HTML, Markdown, CSV and PDF offered, none ticked by default]
- [x] Pen tool and point editing; elbow connectors
- [x] Export to editable PowerPoint [what PowerPoint can't draw goes in as exact SVG pictures]

## Feedback (asked for 2026-11-01)

Matthew's choices are in brackets.

- [x] Drag objects in the Objects list to change what's in front [groups open in the list, and rows
      drag into and out of them; the rows slide apart; the page shows the new order while dragging;
      the Pages list drags the same way; rows dropped on a page in the Pages list move there]
- [x] Open a chosen slide of a deck, and bring slides into an open figure [a slide picker with a
      picture of each slide, one or several chosen; a deck dropped on the page puts the slides'
      objects there, dropped in the Pages list makes them pages there; slides and shapes copied
      in PowerPoint paste as objects; slides dragged out of PowerPoint (Mac) come from their deck
      as last saved, since PowerPoint hands over only which slides they are]
- [x] The Mac menu bar says mosaic, not python, and has the menus a Mac app has [File,
      Edit, View, Window and Help, with the shortcuts; not Insert or Arrange; Mac only, as the
      ribbon does this job on Windows]
- [x] Slide drags out of PowerPoint actually come in: PowerPoint refuses them to other apps, so
      mosaic follows the drag itself [take them anyway, though the slide flies back]
- [x] A blank page takes the size of the slides put on it, pasted, dragged or from a dropped deck
      [any page with no objects; it becomes the first slide, and more slides become pages after it]
- [x] Arrow keys move less when zoomed in and more when zoomed out [round steps in the panels'
      units; Shift, Option and Option+Shift scale with it; the status bar shows the step and a
      click there switches to a fixed 1 pt]
- [x] Tests for linked files updating, for rolling out to early adopters; they found that undo
      couldn't get past an update from a file (the next look put it back), so an undone update now
      stays undone until the file is saved again
- [x] Updates for early adopters: mosaic looks for new versions on GitHub, installs them when
      it quits (or asks first, or not at all), and checks each one's signature [private repo with
      a one-time GitHub sign-in, ready to go public; a release command with a key backup; going
      back a version, test versions first, a warning for documents from newer versions]
- [x] Ready for a public license: MIT code, CC BY 4.0 docs, THIRD_PARTY_NOTICES.md for what
      comes from others [icons after Feather and Lucide credited, theme authors credited,
      Ecma's notice for the shape formulas; mentions of unpublished work reworded]
- [x] ⌘-click (Ctrl-click) adds objects to the selection on the page [as in Keynote, PowerPoint
      and the Finder: a ⌘-drag still moves without snapping, now the whole selection; a ⌘-click
      on a selected object takes it away only if let go without a drag]; also a box with Option
      held takes what it touches, and Select Same (fill colour, line colour, line width, fill and
      line, font, font size, text colour, kind of object) [chosen over Shift-click runs and
      Shift+arrows in the Objects list]
- [x] Double-clicking a .mosaic in Finder or Explorer opens it (the Mac app owns the type; the
      Windows installer registers it for the account), and each document has a window of its own:
      New, Open and Open Recent open a new window unless the front one is blank, a document open
      already comes to the front, closing the last window quits [Matthew's choices, over replacing
      the figure and over staying open with no windows]; decks have mosaic under Open With; a
      .mosaic dropped on the window adds its pages; rulers, grid, guides and snap are each
      window's own
- [x] Slide and poster sizes beside paper: 16:9, 4:3 and 16:10 slides, 48 × 36 in and A0
      posters; a Size menu in the Home tab, whatever is selected (journals' sizes too, Swap, Custom
      size…); the size new documents start at, in Settings [Matthew's choices]
- [x] Colour vision side by side: the page normally and with each preview at once (View tab),
      and the previews in command search ("colour blind", "color blind", "deuter") [Matthew's
      choices, over a shortcut stepping through them]
- [x] Deleting the only page leaves an empty page like it (size, background, guides) instead of
      refusing; one with objects asks first, as any page does [Matthew's choices]
- [x] Export and Figure report close by themselves once the files are written; a note over the
      page names them, with Show in Finder and any warnings [Matthew's choices: the note, closing
      even with warnings, the report too]; fonts embedded for placed PDFs are a plain line that
      doesn't keep the note open
- [x] Pictures for every Style-tab list (shape, fill, line, dash, ends, corners, arrowheads and
      sizes, outline sides and gaps, route): picture menus, drawn by the engine where exactness
      matters; outline sides on everything (Left side and Right side on lines and open shapes,
      Both sides on fills with no line); lists that change nothing yet greyed out with the reason
      [Matthew's choices]
- [x] Click a ruler for a guide at that spot (top: vertical, left: horizontal), rounded to a fine
      step of its ticks, with a preview while pointing; drags out of a ruler stay as they were;
      right-click a guide or its ruler mark: Remove guide, Remove all guides, Hide guides
      [Matthew's choices]
- [x] Corner pictures on a thick line's outline (square, rounded, cut across); in the pictures,
      colours too faint against the menu drawn grey (black in dark themes, white or pale yellow
      in light ones) [Matthew's choices]
- [x] Journal styles: a page's journal gives its panel labels the journal's look (case, brackets,
      font, size, bold; measured from published figures where the guidelines don't say) and Check
      its text sizes and fonts; switching journals keeps hand changes [Matthew's choices]
- [x] Journal checks: Check holds each page to its journal's line widths and to its resolution for
      each kind of picture (photo, photo with text or lines, line art; guessed from the pixels, set
      on the Picture tab), and the Export window flags formats, resolution, colour, fonts and
      transparency the journal doesn't take, and files too big [line widths, resolution and export;
      guessed kind with an override; the publisher's rules, else mosaic's; flag, don't change]
- [x] Text section in the Home tab: style, font, size, bigger and smaller (⌘⇧> and ⌘⇧<), line
      spacing, bold, italic, underline, superscript, subscript, colour, alignment, top/middle/bottom;
      on the text boxes selected (several at once) or the highlighted words while typing (each an
      undo step); selecting text shows Home and the tab before comes back (switch in Settings);
      ⌘B, ⌘I and ⌘U on selected boxes [Matthew's choices]
- [x] Closing with unsaved changes asks Save, Don't Save or Cancel, naming the figure, in a sheet on
      its window (on Windows, a message box); quitting asks about each unsaved figure in turn;
      Don't Save keeps an up-to-date recovery copy [Matthew's choices]
- [x] Fill reaches the middle, inner edge or outer edge of its lines, for shapes and area fills
      (shows through dashed, dotted or see-through lines) [Matthew's choices]
- [x] Clicks go through shapes with no fill (or a clear one), which are picked by their line or
      text; shapes are picked by their real outline; a selected empty shape drags from inside
      [Matthew's choices]
- [x] Drag a page from one window's Pages list into another window: a copy goes in, where a
      line shows in its Pages list or after the page showing (Mac) [Matthew's choices]
- [x] The area around the page works like the page: scroll past its edges, select, move, resize,
      draw, drop and paste there, park objects wholly off it (left out of every export); a click
      picks an object anywhere it shows [Matthew's choices]
- [x] Zoom insets as rounded rectangles, ellipses and circles: ▾ beside Zoom inset and a Zoom shape
      list later; box and inset share the shape unless told not to; the lines touch both outlines
      [Matthew's choices]
- [x] Renamed mosaic, always lower case, inside and out (package, command, settings, app id,
      GitHub repo, folder); documents save as .mosaic and .figasm ones still open; settings and
      recovery copies copied over from ~/.figassemble once; a new icon, figure panels fitted
      together as a mosaic [Matthew's choices]
- [x] Dangerous mode (asked 2026-11-09; the 11-04 idea of editable text from placed figures): in the
      View menu, off at launch, a red status-bar badge; a double-click lifts a plot's text out as a
      text box (anything about it editable, and movable); each placed copy its own; edits re-applied
      when R saves the file again, the rest dropped and listed by Check; the file itself untouched
      [Matthew's choices]
- [x] Kerning (asked 2026-11-09): the font's own pairs; new text kerned at every size, a Kerning
      box on the Text tab, PowerPoint text as each run says, saved figures unchanged [Matthew's choices]
- [x] Refresh All Pictures (asked 2026-11-09): every linked picture on every page read again now,
      undone updates and newly saved copies included; Home tab, File menu, page menu, ⌘⇧R [Matthew's choices]
- [x] Arrange tab for several objects (asked 2026-11-10): two or more selected show it, text boxes
      included; one or none brings the tab before back; a Settings switch, on [Matthew's choices]
- [x] Aligning to the highest (leftmost…) object (asked 2026-11-10): key objects by Option-click only,
      for that selection only and never saved; Same width / height with no key match the largest [Matthew's choices]
- [x] Position and size always in view (asked 2026-11-10): X, Y, Width, Height above the properties
      panel's tabs, following drags, typed to change; groups scale from their top-left [Matthew's choices]
- [x] Dash spacing (asked 2026-11-10): the gaps between dashes and dots as a percentage of the
      style's, in the Line section; Dash menu pictures at 2 pt so dots show [Matthew's choices]
- [x] Several objects' styles at once (asked 2026-11-10): a Style tab for several selected or a
      group, blank (Mixed) where they differ, each change to those that can take it, groups'
      objects included, shape kind and rounding too [Matthew's choices]

## Acceptance test (test slide)

- Imported all 52 objects; 8 of 9 SVGs relinked to the R originals with their PDF copies (the 9th is
  parked off the slide and has no original on disk; Matthew's own figure script couldn't match it either)
- Text baselines within 0.15 pt of PowerPoint's own export (PowerPoint snaps to a 0.24 pt grid)
- Arrowheads within 0.02 pt of PowerPoint's; dashes/dots identical
- All fonts embedded; 0.2% of pixels differ from the figure Matthew's own script makes
  (text now uses real Helvetica instead of the viewer's stand-in); file 2.07 MB vs 2.23 MB

## Later

- Importer coverage for every figure deck (vertical text, bullets)
- Exports that meet a journal's file-size limit by themselves (Export only flags them for now)

# Roadmap

## First version

- [x] Repository, environment, design decisions
- [x] Engine: geometry (DrawingML presets, arrowheads, dashes), fonts, PowerPoint-compatible text layout
- [x] Assets: probing, sibling variants (PDF/SVG/PNG under one name), cache, linked + embedded
- [x] Export: PDF (placed PDFs unchanged, lossless images, embedded font subsets), SVG (inline, scoped),
      PNG/TIFF/JPEG via PDFium; CMYK and EPS via Ghostscript (opt-in)
- [x] .figasm document file; command-line export
- [x] PowerPoint importer (test slide: genomic_instabilities_figure slide 13), relinking to R originals
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
- [ ] Matthew's first real use: feedback round (in progress)
- [ ] Windows: test the app window on a real machine; no-command-line installer (PyInstaller via CI)

## Acceptance test (test slide)

- Imported all 52 objects; 8 of 9 SVGs relinked to the R originals with their PDF copies (the 9th is
  parked off the slide and has no original on disk; compose_vector_figures.py couldn't match it either)
- Text baselines within 0.15 pt of PowerPoint's own export (PowerPoint snaps to a 0.24 pt grid)
- Arrowheads within 0.02 pt of PowerPoint's; dashes/dots identical
- All fonts embedded; 0.2% of pixels differ from compose_vector_figures.py's figure3_pdf.pdf
  (text now uses real Helvetica instead of the viewer's stand-in); file 2.07 MB vs 2.23 MB

## Later

- Freeform drawing and point editing; elbow connectors
- Importer coverage for every figure deck (vertical text, bullets)
- Optional raster DPI cap / file-size targets for journal limits
- Opening .figasm files by double-clicking them in Finder/Explorer
- Fun name

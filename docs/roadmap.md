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
- [ ] App window — **in progress (paused 2026-10-30)**, see below
- [ ] Accessibility pass: keyboard control, screen-reader labels and announcements, high contrast,
      interface text size, reduced motion (built into the UI as it's written; needs a full check)
- [ ] Pre-export check UI (engine side written: `export/preflight.py`)
- [ ] Easy install for labmates (Mac app launcher, Windows)

### App window: where it stands

Written:
- `app/api.py` (JSON-RPC methods), `app/server.py` (local server: UI, asset previews, RPC),
  `app/window.py` (pywebview window, native drag and drop with full paths, close confirmation)
- `export/svgwriter.fragment()` (editor draws shapes/text with the SVG export code)
- `ui/js/util.js`, `ui/js/api.js`, `ui/js/store.js` (document, selection, undo),
  `ui/js/canvas.js` (rendering, selection, move/resize/rotate, line ends, snapping, drawing tools,
  panel-label tool, cropping, in-place text editing, zoom/pan)

Still to write:
- `ui/js/inspector.js` (properties: arrange, picture/link status/crop/source, stroke/fill/arrowheads,
  text, shape parameters, page size in mm)
- `ui/js/panels.js` (toolbar, pages list, layers list, status bar with live region, dialogs: export,
  preferences, shortcuts, pre-export check, import report, autosave recovery)
- `ui/js/main.js` (startup, commands + shortcuts, native/browser drop, clipboard, linked-file refresh
  polling, autosave, window title)
- `ui/index.html`, `ui/css/app.css` (themes: light/dark/high contrast; interface scale; focus rings)

Then: run in browser mode (`figassemble --browser`) and the native window, fix issues, commit.

## Acceptance test so far (test slide)

- Imported all 52 objects; 8 of 9 SVGs relinked to the R originals with their PDF copies (the 9th is
  parked off the slide and has no original on disk; compose_vector_figures.py couldn't match it either)
- Text baselines within 0.15 pt of PowerPoint's own export (PowerPoint snaps to a 0.24 pt grid)
- Arrowheads within 0.02 pt of PowerPoint's; dashes/dots identical
- All fonts embedded; 0.2% of pixels differ from compose_vector_figures.py's figure3_pdf.pdf
  (text now uses real Helvetica instead of the viewer's stand-in); file 2.07 MB vs 2.23 MB

## Later

- Freeform drawing and point editing
- Importer coverage for every figure deck (vertical text, bullets, more presets)
- Optional raster DPI cap / file-size targets
- Fun name

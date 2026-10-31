# Roadmap

## First version

- [x] Repository, environment, design decisions
- [x] Engine: geometry (DrawingML presets, arrowheads, dashes), fonts, PowerPoint-compatible text layout
- [x] Assets: probing, sibling variants (PDF/SVG/PNG under one name), cache, linked + embedded
- [x] Export: PDF (placed PDFs unchanged, lossless images, embedded font subsets), SVG (inline, scoped),
      PNG/TIFF/JPEG via PDFium; CMYK and EPS via Ghostscript (opt-in)
- [x] .figasm document file; command-line export
- [ ] PowerPoint importer (test slide: genomic_instabilities_figure slide 13), relinking to R originals
- [ ] Embed fonts missing from placed PDFs (R's pdf() Helvetica) without touching drawing instructions
- [ ] App window: canvas, selection, move/resize/rotate, crop, text editing, shape tools, inspector,
      pages, layers, undo/redo, drag and drop (link + embed), export dialog
- [ ] Accessibility: keyboard control, screen-reader labels and announcements, high contrast,
      interface text size, reduced motion
- [ ] Pre-export check (fonts, image resolution, smallest text, conversions)
- [ ] Easy install for labmates (Mac app, Windows)

## Later

- Freeform drawing and point editing
- Importer coverage for every figure deck
- Optional raster DPI cap / file-size targets

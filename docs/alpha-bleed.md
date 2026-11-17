# Grey edges around see-through pictures (alpha bleeding), 2026-11-16

## What was wrong

A picture with transparency still has a colour in every pixel, also where it is fully
see-through. Cairo (R's `cairo_pdf`, svglite, rsvg-convert) and often PowerPoint leave black
there. In a PDF the colour and the transparency are two separate images (the picture and its soft
mask). Apple's renderer (Preview) combines them before scaling, so nothing shows. PDFium (Google
Chrome, prose, and mosaic's own PNG/TIFF/JPEG export and PDF previews) scales them separately,
so the hidden black leaks into the soft edges and draws thin grey outlines around light shapes.

Matthew's `main_figures_v2`, page 3 panel b (39 leaf and fade pictures) showed it in Chrome and
prose. So did his PNG export of that page, which PDFium draws. Page 2 has a grey box edge too.

## What mosaic does now

On export, every fully see-through pixel takes the colour of the visible pixels around it
(`mosaic/alphableed.py`, a push-pull fill over the whole see-through area, so heavy downscaling
stays clean too). Visible pixels, including half see-through ones, and the transparency stay byte
for byte as they were.

- **Where:** `SourceResolver.for_pdf`, so PDF export, PNG/TIFF/JPEG export (drawn from that
  PDF), PowerPoint's picture copies and the editor's PDF previews (`app/server.py`) all use the
  cleaned copy. It applies to pictures placed on their own (PNG, TIFF with transparency), to the
  images inside placed PDFs, and to SVGs converted to PDF. It skips images it can't rewrite without
  loss: JPEG/JPEG 2000 inside PDFs, 16-bit, Indexed colour, and any with `/Matte` already.
- **SVG export is unchanged.** It embeds transparent pictures as RGBA PNGs, where colour and
  transparency are one picture, and every viewer combines them before scaling.
- **Once per picture:** the result is kept in the cache (`derived/<sha>.bleed1.json`, plus
  `.pdf`/`.png` when anything changed). A picture with nothing to clean exports from its own file
  as before. Changing `VERSION` makes new copies.
- **Check** gives an information note for each picture whose see-through parts hide a contrasting
  colour next to their edges, for example: "Graphic 4: 39 pictures inside it hide a contrasting
  colour under the see-through parts, which Chrome and prose show as thin grey edges; export fills
  it in, so nothing else changes". Check also makes the cleaned copies, so the next export finds
  them done.

## `/Matte` tried and rejected

Another fix stores the soft mask with `/Matte`, meaning the colour pre-multiplied by a matte
colour. `docs/status/alpha-bleed/matte.py` tests it on a white disc with black hidden behind it.
PDFium draws `/Matte` clean. Apple's renderer ignores it and draws the pre-multiplied colour as it
is, so the edges go dark in Preview instead (darkest pixel 170 against 217). Bleeding is clean in
both renderers, so mosaic uses bleeding.

## Evidence (on a scratch copy of main_figures_v2.mosaic)

In `docs/status/alpha-bleed/`:

- `b_sheet_{1,2,6}x.png` show panel b, with PDFium on the top row and Quartz below, before on
  the left and after on the right. The grey outlines at the leaf stems are gone in PDFium.
- `leaf_zoom_6x.png` shows one leaf: PDFium before, PDFium after, then Quartz.
- `png_export_600dpi_before_after.png` shows mosaic's own PNG export of page 3, before on top
  and after below.
- `page2_zoom.png` shows a grey box edge on page 2 that was fixed too (PDFium before, PDFium
  after, then Quartz).
- `canvas_webkit_vs_pdfium_6x.png` shows the editor's canvas. Panel b shows its SVG in WebKit,
  which is clean. The PDF-preview path (PDFium) had the fringe before (middle) and is clean
  after (right).
- Quartz before vs after, all 5 pages at 2×, and page 3 at 1×, 2× and 6×: **0 pixels differ**.
- Every PDFium pixel that changed on pages 1 and 5 moved closer to Quartz. On pages 2–4 most
  changed pixels moved closer. The rest are places where the two renderers place edges up to a
  pixel apart anyway.
- Scripts: `proof.py` (renders), `fringe.py`, `render.py` (PDFium and Quartz),
  `wksnap.py` (a WebKit snapshot), `matte.py`.

## Cost on main_figures_v2 (5 pages, 13 placed files cleaned, 173 images in all)

| | main | this branch |
|---|---|---|
| PDF export, first time (empty cache) | 11.3 s | 21.9 s (the cleaning, once) |
| PDF export, again | 10.0 s | 10.1–10.8 s |
| Check, cache warm | 12.3 s | 12.5 s |
| PDF size | 59.3 MB | 60.7 MB (+1.4 MB, +2.4%) |

The first-time cost comes mostly from one placed PDF with 87 images (3.5 s) and two 4000-pixel
PNGs (2.4 s each).

## Tests

`tests/test_alpha_bleed.py` (8 tests): the fill, a placed PDF and a PNG exported and drawn by
PDFium at 0.5–6× with no dark edge, visible pixels and transparency unchanged, the cache made once,
pictures with nothing to clean left alone, JPEG soft-masked images left alone, Check's note, and
the editor's PDF preview drawn clean. With the cleaning switched off, the export and preview tests
fail.

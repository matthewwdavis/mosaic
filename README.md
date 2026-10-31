# FigAssemble

A small, fast app for assembling multi-panel scientific figures: set a page size, drop in
plots and images, add text, lines, arrows and shapes, and export PDF, SVG, PNG or TIFF at
any resolution.

Unlike PowerPoint, FigAssemble never converts a placed file through an intermediate
format. A placed PDF goes into the exported PDF unchanged, a placed SVG goes into the
exported SVG unchanged, and PNG/TIFF exports are rendered once, straight from the
vectors. When a plot was saved as PDF + SVG + PNG under one name (as R's ggsave workflow
does), FigAssemble finds the copies and uses the matching one for each export.

> Status: early development (first version in progress). See [docs/design.md](docs/design.md)
> for decisions and architecture, and [docs/roadmap.md](docs/roadmap.md) for progress.

## Install (development)

```sh
conda env create -f environment.yml
conda activate figassemble
pip install -e .
```

## Use

```sh
figassemble                                   # open the app
figassemble export figure.figasm -f pdf,svg,png --dpi 600
figassemble import-pptx deck.pptx --slides 13 # open PowerPoint slides as pages
```

## Test

```sh
python -m pytest -q
```

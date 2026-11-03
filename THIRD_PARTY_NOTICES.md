# Third-party notices

mosaic's code is under the MIT License ([LICENSE](LICENSE)) and its documentation and
pictures under CC BY 4.0 ([LICENSE-docs](LICENSE-docs)). These parts come from others, and are
used under their notices below.

- [PowerPoint's preset shapes](#powerpoints-preset-shapes-ecma-international) (Ecma International)
- [Icons after Feather and Lucide](#icons-after-feather-and-lucide)
- [Interface themes after code-editor themes](#interface-themes-after-code-editor-themes)
- [Colour palettes and the colour-vision preview](#colour-palettes-and-the-colour-vision-preview)
- [Test files made with python-pptx](#test-files-made-with-python-pptx)
- [Software mosaic uses](#software-mosaic-uses) (installed separately)

## PowerPoint's preset shapes (Ecma International)

`mosaic/data/presets.json` holds the formulas, adjust handles and paths of DrawingML's 187
preset shapes, converted by `tools/build_presets.py` from `presetShapeDefinitions.xml`, which is
published with ECMA-376, *Office Open XML File Formats*, Part 1. mosaic uses it to draw
PowerPoint's shapes as PowerPoint does, and to read and write them in PowerPoint files.

> COPYRIGHT NOTICE
>
> © Ecma International
>
> By obtaining and/or copying this work, you (the licensee) agree that you have read,
> understood, and will comply with the following terms and conditions.
>
> This document may be copied, published and distributed to others, and certain derivative
> works of it may be prepared, copied, published, and distributed, in whole or in part, provided
> that the above copyright notice and this Copyright License and Disclaimer are included on all
> such copies and derivative works. The only derivative works that are permissible under this
> Copyright License and Disclaimer are:
>
> (i) works which incorporate all or portion of this document for the purpose of providing
> commentary or explanation (such as an annotated version of the document),
>
> (ii) works which incorporate all or portion of this document for the purpose of incorporating
> features that provide accessibility,
>
> (iii) translations of this document into languages other than English and into different
> formats and
>
> (iv) works by making use of this specification in standard conformant products by
> implementing (e.g. by copy and paste wholly or partly) the functionality therein.
>
> However, the content of this document itself may not be modified in any way, including by
> removing the copyright notice or references to Ecma International, except as required to
> translate it into languages other than English or into a different format.
>
> The official version of an Ecma International document is the English language version on the
> Ecma International website. In the event of discrepancies between a translated version and the
> official version, the official version shall govern.
>
> The limited permissions granted above are perpetual and will not be revoked by Ecma
> International or its successors or assigns.
>
> This document and the information contained herein is provided on an "AS IS" basis and ECMA
> INTERNATIONAL DISCLAIMS ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY
> WARRANTY THAT THE USE OF THE INFORMATION HEREIN WILL NOT INFRINGE ANY OWNERSHIP RIGHTS OR ANY
> IMPLIED WARRANTIES OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.

## Icons after Feather and Lucide

mosaic's interface icons (`ICONS` in `mosaic/ui/js/panels.js`) were drawn for it, in
the style of [Feather](https://feathericons.com) and [Lucide](https://lucide.dev). Some follow
their designs closely: Transform again (their "repeat"), Text (Feather's "type"), Fill area
(Lucide's "paint-bucket"), the two eye icons for showing and hiding (their "eye" and
"eye-off") and Help (Feather's "help-circle"). The plus, the tick and the two arrows that fold
and unfold sections are drawn as in Feather.

### Feather

```
The MIT License (MIT)

Copyright (c) 2013-2023 Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Lucide

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

## Interface themes after code-editor themes

Twelve of the interface themes (`mosaic/themes.py`, "RStudio favourites") take their
colours, and their names, from code-editor themes of the same names, as RStudio ships them.
Only colour values were taken, applied to mosaic's own interface; no theme files are
included. Thanks to their authors:

- **Textmate** and **Dawn:** themes of the TextMate editor
- **Tomorrow** and **Tomorrow Night:** Chris Kempson
- **Solarized Light** and **Solarized Dark:** Ethan Schoonover
- **Xcode:** Apple's Xcode editor
- **Monokai:** Wimer Hazenberg
- **Dracula:** Zeno Rocha and the Dracula Theme contributors
- **Cobalt:** Jacob Rus
- **Material:** Mattia Astorino
- **Twilight:** Michael Sheets

## Colour palettes and the colour-vision preview

The ready-made palettes (`mosaic/ui/js/swatches.js`) and the colour-vision preview
(`mosaic/ui/js/canvas.js`) use published colour values:

- **Okabe-Ito:** Masataka Okabe and Kei Ito, *Color Universal Design (CUD): how to make figures
  and presentations that are friendly to colorblind people* (2008).
- **Tol bright, Tol muted and Tol vibrant:** Paul Tol, *Colour Schemes*, SRON technical note
  SRON/EPS/TN/09-002.
- **Viridis:** Stéfan van der Walt and Nathaniel Smith, matplotlib's viridis colour map
  (CC0).
- **Colour-vision preview:** the simulation matrices of Gustavo M. Machado, Manuel M. Oliveira
  and Leandro A. F. Fernandes, "A physiologically-based model for simulation of color vision
  deficiency", *IEEE Transactions on Visualization and Computer Graphics* 15(6):1291–1298
  (2009).

## Test files made with python-pptx

`tests/data/powerpoint/example_deck.pptx`, and the clipboard files copied from it in PowerPoint
(`copied_slide.slides`, `copied_*.gvml`), were made with [python-pptx](https://github.com/scanny/python-pptx)
from its blank template, so they carry parts of that template (its theme and layouts).

```
The MIT License (MIT)
Copyright (c) 2013 Steve Canny, https://github.com/scanny

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

## Software mosaic uses

None of these is part of mosaic or included in its repository: the installers install them
from conda-forge and PyPI (`environment.yml`), each under its own license.

| Software | License |
|---|---|
| Python | PSF License |
| pikepdf | MPL-2.0 |
| pypdfium2 and PDFium | BSD-3-Clause or Apache-2.0 |
| Pillow | MIT-CMU |
| lxml | BSD-3-Clause |
| fontTools | MIT |
| NumPy | BSD-3-Clause |
| Shapely | BSD-3-Clause |
| skia-pathops | BSD-3-Clause |
| Matplotlib | Matplotlib License (PSF-based) |
| python-pptx | MIT |
| pywebview | BSD-3-Clause |
| cryptography | Apache-2.0 or BSD-3-Clause |
| pytest (tests only) | MIT |
| Ghostscript (optional; EPS export, CMYK) | AGPL-3.0 |
| Poppler (optional; its pdftocairo) | GPL-2.0 or GPL-3.0 |
| librsvg (optional; its rsvg-convert) | LGPL-2.1 or later |

mosaic runs Ghostscript, Poppler and librsvg as separate programs, when they're installed.

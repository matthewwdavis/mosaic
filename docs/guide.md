# FigAssemble user guide

Everything FigAssemble does, by topic. New to it? Start with the [tutorial](tutorial.md).
Shortcuts are written for a Mac; on Windows use **Ctrl** for **⌘** and **Shift** for **⇧**.

- [The window](#the-window)
- [Pages and page sizes](#pages-and-page-sizes)
- [Pictures](#pictures)
- [Text and panel labels](#text-and-panel-labels)
- [Lines and arrows](#lines-and-arrows)
- [Shapes](#shapes)
- [Area fills](#area-fills)
- [Dashes](#dashes)
- [Connecting lines to objects](#connecting-lines-to-objects)
- [Moving, sizing and arranging](#moving-sizing-and-arranging)
- [Right-click menus](#right-click-menus)
- [Align and distribute](#align-and-distribute)
- [Rulers, guides, grid and snapping](#rulers-guides-grid-and-snapping)
- [Checking and exporting](#checking-and-exporting)
- [Saving, linked files and recovery](#saving-linked-files-and-recovery)
- [Opening PowerPoint slides](#opening-powerpoint-slides)
- [Settings](#settings)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Accessibility](#accessibility)
- [Command line](#command-line)
- [Troubleshooting](#troubleshooting)
- [Removing FigAssemble](#removing-figassemble)

## The window

![The FigAssemble window, numbered](images/window-tour.png)

1. **Tabs** across the top, like PowerPoint's ribbon:
   - **Home**: New, Open, Save; Undo, Redo; Cut, Copy, Paste; Duplicate, Delete; Add page,
     Fit page.
   - **Arrange**: Align, Distribute, Spacing, Align to, Group, Order (see
     [Align and distribute](#align-and-distribute)).
   - **View**: Zoom, Fit and Centre page; show or hide the Rulers, Grid and Guides; grid Settings.
2. Each tab's commands, in labelled groups.
3. **Always in view:** **Snap** (on when highlighted), **Check**, **Export**, **Settings**, **Help**.
4. **Pages** of the document, and **Objects** on the current page, front to back. Each object has
   buttons to hide or lock it; click one to select it.
5. **Drawing tools**, beside the page.
6. **The page**, with rulers along the top and left.
7. **Properties** of the selection, in tabs: **Arrange** (position, size, alignment, connections),
   **Style** (shape, fill, line, arrowheads, outline), **Text**, **Picture**. With nothing
   selected, it shows the page, its guides and the document. Click a section heading to fold it;
   folded sections stay folded, and each kind of object opens on the tab you used last.
8. **Status bar:** messages, zoom, the pointer's position, and whether the document is saved.

**Panel widths:** drag the inner edge of either side panel to make it wider or narrower (or
focus the edge and use the arrow keys). Double-click the edge to put the panel back. FigAssemble
remembers the widths.

**Selection:** the box around a selected object, and its handles, stand a few pixels outside the
object, so you can see the object's own edges while you move and resize it.

The Objects list and properties panel are real form controls, usable from the keyboard and with
screen readers (see [Accessibility](#accessibility)).

## Pages and page sizes

With nothing selected (click the grey area or press Escape), the right panel shows the **Page**.

- **Standard size**: A4, US Letter or a 16:9 slide. New pages are A4.
- **Journal** and **Figure type**: sets the page to that journal's column width and its greatest
  figure depth, e.g. Nature double column, 180 × 170 mm. Built in: Cell, G3, Genetics, Genome
  Biology, Genome Research, Heredity, Molecular Biology and Evolution, Molecular Plant, Nature,
  New Phytologist, Plant Cell, PLOS Genetics, PNAS and Science. The note below says where each
  size comes from. Some journals don't publish sizes; for those the sizes were measured from a
  recent published article, and the note says so.
- **Width** and **Height**: any size. The button beside them swaps width and height.
- **Fit to content** (also **Fit page** in the Home tab): crops the page to what's on it, with
  no margin. On a journal page it keeps the column width and fits only the height.
- **Background**: transparent (the default, which journals prefer) or white.

**Pages:** the + button above the Pages list adds a page with the same size, background and
guides. The other buttons duplicate or delete the current page. Drag pages to reorder them, and
double-click a page's name to rename it. One document can hold versions of a figure side by side.

## Pictures

**Placing:** drag PDF, SVG, PNG, JPEG or TIFF files onto the page, or click **Picture** (I), or
copy the files in Finder or Explorer and paste them (⌘V). They land at **true size**, exactly as
the file says. Several files at once arrive in a cascade.

**Pasting** (⌘V, the Paste button, or right-click → Paste to paste where you clicked) takes
whatever was copied last:

- **Objects** copied in FigAssemble, in this document or another.
- **Files** copied in Finder or Explorer: placed linked, as if you'd dropped them.
- **A picture** copied in another app, such as a screenshot or an image copied from a browser,
  at true size (its recorded resolution, or 300 dpi if it has none), stored in the document. On
  a Mac, shapes and drawings copied from Illustrator, PowerPoint, Keynote or Preview arrive as a
  vector PDF, so they stay sharp. On Windows these arrive as a bitmap.
- **Text** as a text box in your default font and size (Settings → New objects), keeping bold,
  italic and line breaks.

Some apps copy text and a picture together (Word, Excel, PowerPoint). ⌘V then pastes the text;
right-click and choose **Paste as picture** for the picture instead.

- **Linked and stored:** a placed file stays **linked**, so when the file changes (you re-run your
  R code), the picture updates within a couple of seconds and keeps its place and size. A copy is
  also stored in the document, so it opens complete anywhere. Hold **Option (Alt)** while
  dropping to store a copy without the link.
- **Copies:** if a plot was saved as PDF, SVG and PNG under one name, FigAssemble finds them all.
  Each export uses the matching copy unchanged:

  | Placed as | PDF export | SVG export | PNG / TIFF export |
  |---|---|---|---|
  | PDF | the PDF page, unchanged | converted to SVG, only if there's no SVG copy | drawn once from the vectors |
  | SVG | converted to PDF, only if there's no PDF copy | the SVG, unchanged | drawn once from the vectors |
  | PNG, JPEG, TIFF | the image data, unchanged | embedded, unchanged | resampled once to the export resolution |

The **Picture** tab of a selected picture shows its file, whether the link works, the copies found,
and its **scale**. A picture that isn't at 100% says so, with a warning that its text has shrunk
or grown. Its buttons:

- **Crop**, or double-click the picture, or press Enter: drag the edges to crop, or drag the
  picture to move it inside its frame. Press Enter or Escape when done. **Reset crop** undoes it.
- **100%** puts it back to true size.
- **Export from** forces one copy (always the PDF, say) instead of the best copy for each format.
- **Replace…** swaps in another file, keeping the position and scale. Shift-drop a file onto a
  picture does the same.
- **Show file** reveals the linked file in Finder or Explorer.
- **Unlink** stops following the file and keeps the stored copy.

The Arrange tab has its position, size (proportions kept), rotation, flips and **Transparency**.
For screen readers, give each picture a **Description** in the Object section.

## Text and panel labels

- **Text (T):** click to type, or drag to make a box the text wraps in. Press **Escape** when
  done. Double-click any text, or select it and press Enter, to edit it again. In the editor, ⌘B,
  ⌘I and ⌘U make the selected words bold, italic or underlined; Shift+Return starts a new line.
- The **Text** tab sets the font, size (in points), colour, bold, italic and underline for the
  whole box, and alignment, vertical position, wrapping and **Resize the box to fit the text**.
- **Panel label (P):** click to add the next free letter (a, b, c…) in bold 8 pt Helvetica.
  Settings changes the size and case.
- Any shape can hold text: double-click it to type.

Helvetica is used if you have it, Arial otherwise (it has the same letter widths). Text stays
real text in PDF and SVG exports, with the fonts embedded.

## Lines and arrows

- **Line (L)** and **Arrow (A):** drag from start to end, or click for a 2 cm line. Hold **Shift**
  to keep to multiples of 45°.
- **Curves:** select a line and drag the hollow handle halfway along it: it bends into a smooth
  curve through that point, and an arrowhead follows the curve. Drag other hollow handles to add
  more points (S-curves). Drag points to reshape it; double-click a point to remove it, or the
  line to add one. The **Points** section lists every point's position and switches between
  **Smooth curve** and **Straight segments**.
- **Style** tab: colour, width (in points), [dash](#dashes), line ends (round, flat or square),
  corners, transparency.
- **Arrowheads:** each end can be none, triangle, stealth, open arrow, circle or diamond, small
  to large. **Rounding** (0-100%) rounds a pointed head's tip, which still ends exactly on the
  line's end. **Swap ends** swaps them.
- **Outline** ([see Shapes](#shapes)) draws a band of another colour around the line and its head.

## Shapes

- **Tools beside the page:** Rectangle (R), Rounded rectangle (U), Ellipse (O), Triangle, Arc,
  Bracket. Drag to draw (Shift for squares and circles), or click for a 2 cm shape. With the
  keyboard: choose a tool and press Enter to place one in the middle of the view.
- **Shapes menu (S):** PowerPoint's shapes in groups: rectangles, basic shapes, block arrows,
  stars, brackets and braces, equation symbols. Arrow keys move through it, typing a name jumps
  to it, Enter chooses.

  <img src="images/shapes.png" alt="The Shapes menu" width="560">

- **Yellow handles** adjust a shape the way PowerPoint's do (a rounded rectangle's corners, a
  star's inner radius, a block arrow's head). The **Shape** section of the Style tab names each
  adjustment so you can type it, and can change one shape into another.
- **Corner rounding** (0-100%) rounds every straight-edged shape's corners (triangles, polygons,
  stars, arrows). 100% is as round as the shape allows; a triangle becomes a circle.
- **Fill**: none, a colour with transparency, or a gradient. Every colour has a picker and a hex
  code (`#1A2B3C`) you can type or paste.
  - **Linear gradient**: a blend at any angle (90° runs top to bottom).
  - **Radial gradient**: circles from the middle or a corner, out to the far corner.

  A gradient has two or more **colour stops**, each with a position along it and its own
  transparency. **Add stop** puts one in the widest gap; **Reverse** swaps the ends. Gradients
  from PowerPoint slides come in as they were.
- **Outline around it**: a band in a second colour around everything the object draws, e.g. a white
  edge that keeps a black arrow visible on a photo. You set its thickness and transparency, and
  its type where types would look different. The list shows only the types that differ on the
  selected object:
  - **Outside** or **Both sides of the line** (filled shapes with a line): underneath the shape,
    so the band shows only outside it, or along both sides of the line, over the fill too;
  - **Gaps filled** or **Gaps empty** (dashed or dotted lines): the band runs on through the gaps
    between dashes, or goes only round each dash or dot.

  A filled shape with a dashed or dotted line has all four: **Outside, gaps filled**, **Outside,
  gaps empty**, **Both sides, gaps empty** and **Both sides, gaps filled**. A solid line, or a
  shape with no line, has nothing to choose: every type looks the same there.
- **Make editable curve** (arcs): turns an arc into a curve with points you can drag.

## Area fills

Fill the space that separate lines and shapes enclose, the way Illustrator's Live Paint does:
the parts of a Venn diagram, a region between curves, a wedge outlined by lines.

![A Venn diagram whose three areas are filled](images/areafill.png)

Choose **Fill area** (F) in the tools on the left and click inside an enclosed space. FigAssemble
adds a fill that exactly covers it, behind the lines and shapes round it, and selects it so you
can choose its colour, or a gradient, in the Style tab.

- **It follows its lines.** Move a line, drag a corner or reshape a curve, and the fill reshapes
  with it. Dragging the fill, or nudging it with the arrow keys, moves its lines and shapes with
  it.
- Lines that look joined close an area, even with a hairline gap, as long as the gap is narrower
  than about the line's width.
- A shape inside the area leaves a hole.
- If the lines no longer enclose the space (one is moved away or deleted), the fill disappears
  until they do again. Deleting all of its lines and shapes deletes it too.
- **Make an ordinary shape** (Arrange tab or right-click) turns it into a plain shape of the area
  as it is, which stays put when the lines move. Copied on its own, without its lines, a fill
  becomes one of these.

## Dashes

Choose a dash in the **Line** section (round dot, short dash, dash, dash-dot, long dash…).

FigAssemble puts a dash (or a dot) **on every corner**, bend and line end, rounded corners
included, and spaces the dashes evenly between them. PowerPoint runs the pattern on regardless,
so dots crowd at corners and closed outlines get a squeezed spot. Untick **Even dashes** for
PowerPoint's spacing, e.g. to match an existing figure. Dashed lines from PowerPoint decks get
even dashes too.

## Connecting lines to objects

Drop either end of a line or arrow on a **connection point** to attach it. The end then follows
the object when it moves, resizes or rotates.

- **Connection points** show as small circles while you draw a line or drag its end near an
  object:
  - the object's own corners and the middles of its sides (triangle tips, star points, the
    middle of a rounded corner);
  - 8 points round an ellipse;
  - a picture's or text box's corners and side middles;
  - a line's ends and middle;
  - on dashed or dotted outlines, both ends and the middle of every dash.
- An attached end is a **green** dot. The arrow's Arrange tab lists what each end is attached to,
  with **Detach** buttons.
- Hold **⌘** while dropping an end to leave it unattached. Moving the line on its own (dragging
  it, arrow keys, align) lets go of both ends; moving it together with its objects keeps them.
- Copying a line and its objects together keeps the copies attached to each other.

![An attached arrow, with its Connections](images/annotated.png)

## Moving, sizing and arranging

- **Select:** click; Shift-click adds or removes; drag on empty space to select everything
  inside a box. Tab and Shift+Tab step through objects.
- **Move:** drag, or arrow keys: 1 pt per press, 10 pt with Shift, 0.1 pt with Option (Alt).
  Option-drag (Alt-drag) makes a copy.
- **Resize:** drag a handle. Corners keep a picture's proportions (Shift does the opposite).
  Option (Alt) resizes from the centre. Option+Shift+arrows change the size by 1 pt.
- **Rotate:** drag the round handle above the object; Shift keeps to 15° steps.
- **Exact values:** the Arrange tab's X, Y, Width, Height and Rotation, in centimetres (change
  the unit in Settings), plus flips.
- **Group (⌘G), Ungroup (⌘⇧G)**; **Order**: bring to front (⌘⇧]), forward (⌘]), backward
  (⌘[), to back (⌘⇧[).
- **Lock** stops an object being selected or moved on the page; **Hide** hides it (it isn't
  exported). Both are in the Object section, the Objects list and the right-click menu.

## Right-click menus

Right-click (or Control-click on a Mac) for a menu of what you can do, with each command's
shortcut beside it:

- **An object:** Cut, Copy, Paste, Duplicate, Delete; Group, Ungroup; the four Order commands;
  Lock position, Hide. A picture adds Crop, Replace and Show the picture's file; a text box or
  shape adds Edit text; a line attached to objects adds Detach the ends.
  - Right-clicking an object that isn't selected selects it.
  - Right-clicking one of several selected objects keeps them all selected, so **Group** groups
    the lot.
- **Empty page:** Paste, Select all, Insert picture, Fit page to content, and the Rulers, Grid,
  Guides and Snap switches.
- **Paste** from a right-click puts things where you clicked. When the clipboard holds both text
  and a picture, **Paste as picture** appears beside it (see [Pictures](#pictures)).
- **A page in the Pages list:** Add, Duplicate, Delete, Move up or down, Rename.
- **An object in the Objects list:** the object's menu. This is the way to unlock an object,
  since a locked one can't be clicked on the page.

From the keyboard, **Shift+F10** (or the menu key on a Windows keyboard) opens the menu for
whatever has the focus: the selection, the page, or the current page or object in a list. Arrow
keys move through it, a letter jumps to a command, Enter chooses, and Escape closes it.

## Align and distribute

Select objects and use the **Arrange** tab, or the panel on the right:

- **Align**: left edges, centres, right edges, tops, middles, bottoms. One object on its own
  aligns to the page.
- **Distribute**: spreads three or more objects so their left edges (centres, right edges, tops,
  middles or bottoms) are evenly spaced. The outer two stay put.
- **Spacing**: equal gaps between neighbours, **Across** or **Down**. Type a **Gap** (in your
  position unit) for exactly that gap, counted out from the key object. Clear it for "as even as
  fits".
- **Align to**:
  - **Selection** (the default): lines up with the selection's edges.
  - **Page**: lines up with the page's edges; distributing moves the outer objects to the edges.
  - **Key object**: lines up with one object that doesn't move. Click one of the selected
    objects (without dragging) to make it the key. It gets a thick outline; click it again to stop.

## Rulers, guides, grid and snapping

![Rulers, guides and the grid](images/guides.png)

- **Rulers** (⌘R) run along the top and left, in your position unit, with 0 at the page's
  top-left corner. They mark the selection and the pointer.
- **Guides:** drag one out of a ruler onto the page. Drag a guide to move it, or drag its mark on
  the ruler if objects cover it. Drag it back onto a ruler to remove it. With nothing selected,
  the **Guides** section of the right panel lists them, to add one, type exact positions, or
  remove them. Each page has its own guides. Show or hide them with ⌘;.
- **Grid** (⌘'): graph paper over the page, 1 cm squares whose 1 mm lines appear as you zoom in.
  The spacing is in Settings (View tab → Settings).
- **Snapping:** a dragged object snaps to the page's edges and centre, to other objects' edges
  and centres, to **equal gaps** between objects (the gaps show with their size), and to guides
  and the grid while they're shown. Hidden guides and a hidden grid never pull. Grid lines give
  way to everything else. Magenta lines show what it snapped to.
- **Getting around snapping:** hold **⌘** while dragging, just that once; turn the **Snap**
  button off (⌘⇧;); or press **Escape** mid-drag to cancel the drag. Typed values and arrow keys
  never snap.

Guides and the grid are never exported.

## Checking and exporting

**Check** (⌘⇧E) looks at the current page and lists:

- the smallest text after scaling (journals often ask for at least 5 pt);
- images whose resolution is too low at their printed size;
- conversions an export would need (an SVG with no PDF copy, say);
- placed files that can't be found.

Each item can select the object it's about. Fonts missing from placed PDFs (R's `pdf()` leaves
Helvetica out) are embedded automatically on export.

**Export** (⌘E):

- **Formats:** PDF, SVG, PNG, TIFF (LZW-compressed). **More options:** JPEG, EPS (transparency is
  flattened), CMYK colour (TIFF, JPEG, PDF; only if a journal asks), and embedding missing fonts
  (on).
- **Resolution** for PNG, TIFF and JPEG: 300, 600 or 1200 dpi, or any other.
- **Pages:** this page or all pages. **Background:** transparent or white.

Click **Export…** and choose a name and folder; one file is written per format (and per page).
Your choices are remembered for next time.

## Saving, linked files and recovery

- **Save** (⌘S) writes a `.figasm` document. It holds your pages, the links to placed files, and
  a copy of each file, so it opens complete on another computer. **Save as** (⌘⇧S) saves a copy.
- **Open** (⌘O) opens a `.figasm` document, or a PowerPoint deck (see below).
- **Linked files** are checked every couple of seconds while the document is open. A changed file
  updates its picture; a missing one falls back to the stored copy.
- **Recovery:** unsaved work is copied every minute. If FigAssemble closes unexpectedly, it offers
  the work back next time. That window can also **Delete** copies you don't need, one at a time or
  all together. **Settings → Unsaved work** shows how many copies are kept and can delete them.
  Deleting always asks first, since these are the only copies of work that was never saved.

## Opening PowerPoint slides

**Open** a `.pptx` file to turn its slides into pages. Pictures, text, lines, arrows and shapes come
in where they were, and every PowerPoint shape comes in as itself. Pictures are relinked to the
original figure files where they can be found, so the PDF or SVG your R code saved is used
instead of PowerPoint's copy. FigAssemble looks in the nearest folder called **Figures** above the
deck (where R notebooks usually save plots), or else in the deck's own folder. A report lists
anything that couldn't be brought across.

## Settings

The gear button (⌘,):

- **Theme:** how the interface looks. Click a picture to switch at once:
  - FigAssemble's own Light, Dark and High contrast;
  - a dozen RStudio favourites: Textmate, Tomorrow, Solarized Light, Dawn, Xcode, Tomorrow Night,
    Solarized Dark, Monokai, Dracula, Cobalt, Material and Twilight;
  - some originals: Pistachio, Walnut, Alfalfa, Lab notebook, Blueprint, Chalkboard and Terminal.

  **Match the system** (the default) follows your computer's light and dark mode, using the
  themes you pick for **By day** and **At night**. Themes colour the interface only: the page
  stays white, so a figure looks the way it will print. Every theme keeps text readable (WCAG AA
  contrast).
- **Measurements:** the unit for positions and sizes (cm by default; mm, points or inches) and for
  page sizes (mm). Font sizes and line widths are always in points.
- **Interface:** text size, labels under toolbar buttons, reduced motion.
- **Rulers, grid and guides:** what's shown, snapping, the grid's spacing and how many finer lines
  each square has.
- **Unsaved work:** recovery copies kept from earlier sessions, with Delete all.
- **New objects:** default text size, line width, and panel label size and case.

<img src="images/themes.png" alt="The theme gallery in Settings" width="420">

The version number is at the bottom. Settings are kept in a `.figassemble` folder in your home
folder, along with recovery copies and a cache of rendered previews.

## Keyboard shortcuts

Press **?** in FigAssemble for this list.

| Action | Mac | Windows |
|---|---|---|
| New, Open, Save, Save as | ⌘N, ⌘O, ⌘S, ⌘⇧S | Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+S |
| Export, Check before export | ⌘E, ⌘⇧E | Ctrl+E, Ctrl+Shift+E |
| Undo, Redo | ⌘Z, ⌘⇧Z | Ctrl+Z, Ctrl+Y or Ctrl+Shift+Z |
| Cut, Copy, Paste, Duplicate | ⌘X, ⌘C, ⌘V, ⌘D | Ctrl+X, Ctrl+C, Ctrl+V, Ctrl+D |
| Delete | Delete | Delete or Backspace |
| Select all | ⌘A | Ctrl+A |
| Group, Ungroup | ⌘G, ⌘⇧G | Ctrl+G, Ctrl+Shift+G |
| Bring to front, Bring forward | ⌘⇧], ⌘] | Ctrl+Shift+], Ctrl+] |
| Send backward, Send to back | ⌘[, ⌘⇧[ | Ctrl+[, Ctrl+Shift+[ |
| Menu for the selection | Right-click, Control-click or Shift+F10 | Right-click, Shift+F10 or the menu key |
| Zoom in, Zoom out, Fit page in window, True size | ⌘+, ⌘−, ⌘0, ⌘1 | Ctrl+Plus, Ctrl+Minus, Ctrl+0, Ctrl+1 |
| Centre page (keeping the zoom) | ⌘⇧0 | Ctrl+Shift+0 |
| Rulers, Grid, Guides | ⌘R, ⌘', ⌘; | Ctrl+R, Ctrl+', Ctrl+; |
| Snap on or off | ⌘⇧; | Ctrl+Shift+; |
| Select, Text, Panel label | V, T, P | V, T, P |
| Line, Arrow | L, A | L, A |
| Rectangle, Rounded rectangle, Ellipse | R, U, O | R, U, O |
| Shapes menu | S | S |
| Fill an enclosed area | F | F |
| Insert picture | I | I |
| Add page | ⌘⇧N | Ctrl+Shift+N |
| Settings, Help | ⌘, (comma), ? | Ctrl+, (comma), ? |

In a text field, the editing keys (⌘A, ⌘C, ⌘V, ⌘Z…) work on the text, and Save, Open, New and
Export still work, saving what you've typed.

**On the page:**

- Tab / Shift+Tab: select the next or previous object.
- Arrow keys: move by 1 pt; Shift: 10 pt; Option (Alt): 0.1 pt. Option+Shift+arrows: resize by 1 pt.
- Enter: edit text, or crop a picture. Escape: finish, deselect, or cancel a drag.
- With a drawing tool chosen, Enter places a 2 cm shape in the middle of the view.
- While dragging: Shift keeps lines straight and shapes square; Option (Alt) duplicates;
  ⌘ ignores snapping (and leaves line ends unattached).
- Space + drag, or scroll: move around. ⌘ + scroll, or pinch: zoom. While the whole page fits in
  the view, it stays centred; zoomed in further, ⌘⇧0 brings it back to the middle.

## Accessibility

- Every tool and setting is a labelled control you can reach with the keyboard. The toolbar, tabs,
  menus and lists move with the arrow keys; Tab moves between groups. Shift+F10 opens the
  right-click menu for whatever has the focus.
- Screen readers hear what's selected, where it is, and what each action did. Pictures can carry
  a description.
- **Settings:** interface text size, a High contrast theme (and every other theme meets WCAG AA
  contrast), labels under toolbar buttons, reduced motion. The system's dark mode, contrast and
  reduced-motion settings are followed too.

## Command line

FigAssemble can also run from a terminal, with its conda environment active
(`conda activate figassemble`):

```sh
figassemble                                    # open the app
figassemble figure.figasm                      # open a document
figassemble export figure.figasm -f pdf,svg,png --dpi 600
figassemble import-pptx deck.pptx --slides 13  # PowerPoint slides -> figure.figasm
figassemble --browser                          # use a web browser instead of the app window
```

## Troubleshooting

**The Mac installer won't open.** macOS blocks scripts downloaded from the internet until you
allow them. After the warning, open **System Settings → Privacy & Security** and click **Open
Anyway**. Or run it in Terminal: type `bash `, drag `install-mac.command` into the window, and
press Return.

**Windows says it protected your PC.** Click **More info**, then **Run anyway**. Make sure you
extracted the ZIP first and are running the installer from the extracted folder.

**The installer stopped with a message.** It says which step failed. Most often it's the internet
connection or disk space. Fix that and run the installer again; it carries on from where it got
to. If it keeps failing, [report a problem](https://github.com/matthewwdavis/FigAssemble/issues/new?template=problem.yml)
and paste the last lines of the installer's window.

**A picture says "Linked file not found".** The file has moved or been renamed. The picture uses
the copy stored in the document, so nothing is lost. Use **Replace…** to link it to the file's new
location.

**Text looks different from my R plot.** FigAssemble shows placed files exactly as they are.
If R saved Helvetica without embedding it, FigAssemble embeds it on export, using Arial (same
widths) if Helvetica isn't on your computer.

**Something else.** Please [report a problem](https://github.com/matthewwdavis/FigAssemble/issues/new?template=problem.yml),
with a screenshot if you can.

## Removing FigAssemble

**Mac:** drag **FigAssemble** from Applications to the Trash. To remove what it installed too, open
Terminal and run `~/miniforge3/bin/conda env remove -n figassemble` (use your own conda if you
had one before). If the installer installed Miniforge and you don't use conda for anything else,
delete the `miniforge3` folder in your home folder. Settings and recovery copies are in
`~/.figassemble`.

**Windows:** delete the FigAssemble shortcuts from the desktop and Start menu. Run
`%USERPROFILE%\miniforge3\Scripts\conda.exe env remove -n figassemble` in a Command Prompt. If the
installer installed Miniforge, you can uninstall it under **Settings → Apps**. Settings and
recovery copies are in `%USERPROFILE%\.figassemble`.

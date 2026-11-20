# mosaic

**Put together multi-panel scientific figures without losing quality.** Set the page to your
journal's column width, drop in the plots you saved from R (or anywhere else), line them up, add
panel labels, text and arrows, and export a PDF, SVG, PNG or TIFF that a journal will accept.

![mosaic with a three-panel figure](docs/images/window.png)

- **Nothing gets converted on the way.** A PDF you place goes into the exported PDF unchanged; an
  SVG goes into the exported SVG unchanged.
- **Plots stay at true size**, so 6 pt text stays 6 pt, and the pre-export check warns you about
  anything smaller than a journal allows.
- **Placed files stay linked.** Re-run your R code and the panel updates by itself. A copy is also
  stored in the document, so it opens complete on a labmate's computer.
- **Journal page sizes** are built in (Nature, Science, Cell, PNAS, PLOS Genetics and more), along
  with slides and posters, and fonts that R leaves out of its PDFs are embedded when you export.
  For bioRxiv preprints a figure can be any size that fits a US Letter page's text area (7 × 9.5 in),
  or up to 180 mm wide. Each journal is one **journal file** shared with prose (its figure sizes,
  panel-label look and figure rules, with their sources); a journal of your own is one too and can
  hold the same rules. prose's `docs/journal-format.md` explains the format and how to check a file
  (`python -m mosaic._labapp.journalfile validate FILE`).
- **A journal mosaic doesn't list takes a minute to add.** In **Size ▸ My Journals ▸ Add a
  Journal**, click **Start from a Journal's Reference Style…** and type the journal's name or ISSN:
  mosaic knows about 10,900 journals from the reference-style list behind Zotero (no connection
  needed), and fills in its name, keeping its ISSN, publisher and guidelines link with it. Then
  **Read Figure Sizes from the Author Guidelines…** reads the journal's instructions for authors
  (the page is read only when you press **Read the Page**, or choose a copy you saved from your
  browser with **File ▸ Save As**) and shows each width and depth it found beside the sentence it
  came from. Untick anything wrong, **Use These**, and check the numbers before you save: the sizes
  are often on a separate "preparing figures" page, and some sites turn programs away, in which
  case save the page from your browser and choose it. Nothing is sent to any AI service.
- **Find a Journal…** (Size ▸ Find a Journal…). Type a journal's name, its ISSN or its usual
  abbreviation: mosaic looks through its own journals, yours, and the library of journals others
  have shared (the one prose uses). Each shows a badge: **Verified** (a maintainer checked it
  against the journal's own pages) or **Community** (shared and checked by machine, not yet by a
  maintainer). Choose one, then its figure size, and the page takes that size. One from the
  library is brought onto this computer the first time (checked to be exactly the file the library
  lists), listed under **From the library** in Size ▸ Journal, and works offline from then on;
  prose has it too. **Size ▸ My Journals… ▸ Share…** offers one of your own journals to the
  library: for the public library it goes for review (a "pull request" on GitHub, made for you
  with GitHub's tool `gh`), and mosaic shows the link.
- **Your PowerPoint figures come along.** Open a `.pptx` and choose its slides, drop a deck on the
  page or the Pages list, or copy slides and shapes in PowerPoint and paste them. Pictures, text,
  lines and shapes come in where they were, as objects you can edit. Pictures are relinked to the
  PDFs and SVGs your R code saved, where they can be found, instead of PowerPoint's copies.
- **Drawing tools:** ready-made shapes (stars, block arrows, braces and more), arrows whose ends
  attach to objects and follow them, gradient fills, outlines, and fills for areas that lines
  enclose.
- **Figure tools:** scale bars that stay right when a picture is resized (the scale typed,
  measured, or read from ImageJ and OME-TIFF files), zoom insets, significance brackets, crop to
  shape, clipping masks and Pathfinder.
- **Consistent colours and styles:** linked swatches and text styles (change one and everything
  using it follows), colour-blind-safe palettes, colour vision previews (side by side too), and
  copying a style from one object to others.

> **Status: early version, for collaborators' feedback.** mosaic was called FigAssemble until
> November 2026; its `.figasm` documents open as they are. Figures are saved as `.mff` files
> ("mosaic figure file") from November 2026; ones saved before, as `.mosaic`, open and save as
> they are until you use Save As. Developed and tested on a Mac. On Windows and Linux the
> tests, the installers and the app's window are checked automatically on every change, but it
> hasn't been used day to day there yet, so please [report anything odd](#feedback).

## Install

You'll need about 2 GB of free disk space and an internet connection. The installer sets up
everything mosaic needs, including conda (Miniforge) if you don't have it. The first install
takes 5-15 minutes; nothing else on your computer is changed.

### The quick way: one line

Copy the line for your computer, paste it, and press Return. It downloads the newest version and
runs the same installer as the steps below, without the security warnings a downloaded file gets.
Run the same line again any time to reinstall or update.

- **Mac or Linux:** open **Terminal** (on a Mac it's in Applications ▸ Utilities) and paste

  ```bash
  curl -fsSL https://raw.githubusercontent.com/matthewwdavis/mosaic/main/install.sh | bash
  ```

- **Windows:** open **PowerShell** (type *PowerShell* in the Start menu) and paste

  ```powershell
  irm https://raw.githubusercontent.com/matthewwdavis/mosaic/main/install.ps1 | iex
  ```

### Or download it and double-click

**[⬇ Download mosaic (ZIP)](https://github.com/matthewwdavis/mosaic/releases/latest/download/mosaic.zip)**:
always the newest version, the same file for Mac, Windows and Linux. (Every version is on the
[releases page](https://github.com/matthewwdavis/mosaic/releases).) Then follow the steps for
your computer:

### Mac

1. Open the downloaded ZIP (double-click it in Downloads). You get a folder named after the
   version, such as `mosaic-0.2.0`.
2. In that folder, double-click **`install-mac.command`**.
   - If macOS says it can't open it (*"Apple could not verify…"*), click **Done**, open
     **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to
     `install-mac.command`. (On macOS 14 and older: Control-click the file, choose **Open**,
     then **Open** again.)
   - Or open **Terminal**, type `bash ` (with a space after it), drag `install-mac.command` into
     the Terminal window and press Return.
3. A Terminal window shows the progress. When it finishes, mosaic opens. From now on it's in
   your **Applications** folder like any other app.

### Windows

1. Right-click the downloaded ZIP and choose **Extract All**, then open the extracted folder (named
   after the version, such as `mosaic-0.2.0`). Run the installer from the extracted folder,
   not from inside the ZIP.
2. Double-click **`install-windows.bat`**. If Windows says it *protected your PC*, click
   **More info**, then **Run anyway**.
3. A window shows the progress. When it finishes, mosaic starts. From now on, start it from
   the **Start menu** or the **desktop** shortcut.

### Linux

1. Extract the downloaded ZIP and open a terminal in the extracted folder (named after the
   version, such as `mosaic-0.2.0`).
2. Run **`bash install-linux.sh`**. Nothing is installed system-wide and no password is asked for.
3. When it finishes, mosaic starts. From now on it's in your applications menu, and `mosaic`
   starts it from a terminal.

To paste pictures copied in other programs, mosaic uses your desktop's clipboard tool:
`wl-clipboard` on Wayland or `xclip` on X11 (install one with your package manager if neither is
there). On Linux mosaic doesn't update itself yet: download the newest release and run its
installer again. On a computer without a desktop (a cluster login node, say), `mosaic gui --browser`
runs it in your web browser instead (see the [guide](docs/guide.md#in-a-web-browser)).

**Updating:** on a Mac and Windows mosaic updates itself. When a new version is out, it downloads it and installs it
when you quit mosaic, then says what's new. **Settings → Updates** switches this to asking
first, or off, and can go back to the version before. No GitHub account is needed. You can delete the downloaded folder after installing.

Installed mosaic before it updated itself (version 0.1.0)? Run the one line above (or download
the newest release and run its installer) once; it keeps your settings, and from then on mosaic updates itself.

**Removing it:** see [the user guide](docs/guide.md#removing-mosaic).
**If something goes wrong:** see [Troubleshooting](docs/guide.md#troubleshooting).

## Quick start

The first time mosaic opens it shows a **sample figure**, four small plots as panels a to d, to
try things on; **Help ▸ Open the Sample Figure** brings it back any time (on Windows and Linux:
press **?**, then **Open the Sample Figure**).

1. **Choose a page size.** Click **Size** in the Home tab: a journal's figure size (say *Nature*,
   *Double column*), paper, a slide or a poster. With nothing selected, the panel on the right
   shows the page's size too.
2. **Drop in your plots.** Drag PDF, SVG, PNG, JPEG or TIFF files from Finder or Explorer onto the
   page, copy them there and paste (⌘V), or use **Picture** (I) in the tools on the left. They land
   at true size and stay linked to their files.
3. **Arrange them.** Drag them into place. Magenta lines show when edges and centres line up;
   hold ⌘ (Ctrl on Windows) to drag freely. The **Arrange** tab aligns and spaces several at once.
4. **Label and annotate.** Press **P** and click to add panel labels (a, b, c…). Add text (T) and
   arrows (A). Drop an arrow's end on an object's corner or edge to attach it. prose reads the
   labels, so a figure placed there from a mosaic document starts its legend with a line for each.
5. **Export.** Click **Check** to look for problems, then **Export** (⌘E) for PDF, SVG, PNG or TIFF,
   or an editable PowerPoint file for collaborators.
   Save your work with ⌘S as a `.mff` document, and double-click it to open it again (each
   figure in a window of its own).

**New to it? Follow the [tutorial](docs/tutorial.md)**: it builds the figure above in about
15 minutes, using the sample plots in [`examples/`](examples). Everything else is in the
**[user guide](docs/guide.md)**, including [all keyboard shortcuts](docs/guide.md#keyboard-shortcuts).

## Keyboard shortcuts

The ones you'll use most. Right-click an object, the page or a page in the Pages list for a menu
of what you can do with it, with the shortcuts alongside.

| Action | Mac | Windows |
|---|---|---|
| Undo, Redo | ⌘Z, ⌘⇧Z | Ctrl+Z, Ctrl+Y |
| Cut, Copy, Paste | ⌘X, ⌘C, ⌘V | Ctrl+X, Ctrl+C, Ctrl+V |
| Duplicate, Delete | ⌘D, Delete | Ctrl+D, Delete |
| Transform again (repeat the last move, resize or turn) | ⌘⇧D | Ctrl+Shift+D |
| Copy style, Paste style | ⌘⇧C, ⌘⇧V | Ctrl+Shift+C, Ctrl+Shift+V |
| Search commands (type to find any command) | ⌘/ | Ctrl+/ |
| Select all | ⌘A | Ctrl+A |
| Bold, Italic, Underline; Bigger, Smaller text | ⌘B, ⌘I, ⌘U; ⌘⇧>, ⌘⇧< | Ctrl+B, Ctrl+I, Ctrl+U; Ctrl+Shift+>, Ctrl+Shift+< |
| Add an object to the selection, or take it away | ⌘-click or ⇧-click | Ctrl-click or Shift-click |
| Group, Ungroup | ⌘G, ⌘⇧G | Ctrl+G, Ctrl+Shift+G |
| Bring forward, Send backward (or drag the object's row in the Objects list) | ⌘], ⌘[ | Ctrl+], Ctrl+[ |
| Move the selection one step (10 steps); the step follows the zoom, as the status bar shows | Arrow keys (with ⇧) | Arrow keys (with Shift) |
| Zoom in, Zoom out, Fit page, True size | ⌘+, ⌘−, ⌘0, ⌘1 | Ctrl+Plus, Ctrl+Minus, Ctrl+0, Ctrl+1 |
| Centre the page | ⌘⇧0 | Ctrl+Shift+0 |
| Save, Open, Export | ⌘S, ⌘O, ⌘E | Ctrl+S, Ctrl+O, Ctrl+E |
| Select, Text, Panel label, Line, Arrow, Rectangle | V, T, P, L, A, R | V, T, P, L, A, R |
| Insert picture | I | I |
| Fill an area that lines enclose | F | F |
| Menu for the selection | Right-click or Control-click | Right-click or Shift+F10 |
| Every shortcut | ? | ? |

All of them are in the [user guide](docs/guide.md#keyboard-shortcuts), and **?** shows them in
mosaic.

## Feedback

Feedback is the point of this early version: what's confusing, what's missing, what breaks.

- **[Report a problem](https://github.com/matthewwdavis/mosaic/issues/new?template=problem.yml)**: something didn't work, looked
  wrong in the export, or was confusing.
- **[Suggest an idea](https://github.com/matthewwdavis/mosaic/issues/new?template=idea.yml)**: something mosaic should do, or
  do differently.

**In mosaic, choose Help ▸ Report a Problem** (on Windows and Linux: press **?**, then **Report a
Problem…**). It saves a small report file on your Desktop to attach to the form or an email:
mosaic's version, your operating system, your settings and the last messages mosaic logged. It
holds none of your figures and no names of your files, and it's a ZIP you can open to check.

Each form asks for the details that help, such as what you did, what you expected and Mac or Windows.
Screenshots help a lot: paste or drag them into the form. The version number is at the bottom of
**Settings**. You can see existing reports under [Issues](https://github.com/matthewwdavis/mosaic/issues).

## License

mosaic's code is under the [MIT License](LICENSE). Its documentation and pictures (this
README, everything in `docs/` and the example plots) are under [CC BY 4.0](LICENSE-docs). A few
parts come from others and are used under their own notices, listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): PowerPoint's shape formulas (from the Office
Open XML standard), icons after Feather and Lucide, theme colours after code-editor themes, and
published colour palettes.

## For developers

Running from source, tests, the editor self-test, screenshots and installers:
[docs/development.md](docs/development.md). Design decisions: [docs/design.md](docs/design.md);
progress: [docs/roadmap.md](docs/roadmap.md).

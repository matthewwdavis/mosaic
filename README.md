# FigAssemble

**Put together multi-panel scientific figures without losing quality.** Set the page to your
journal's column width, drop in the plots you saved from R (or anywhere else), line them up, add
panel labels, text and arrows, and export a PDF, SVG, PNG or TIFF that a journal will accept.

![FigAssemble with a three-panel figure](docs/images/window.png)

FigAssemble does the job people usually do in PowerPoint, without PowerPoint's damage:

- **Nothing gets converted on the way.** A PDF you place goes into the exported PDF unchanged; an
  SVG goes into the exported SVG unchanged. PowerPoint's PDF export turns every placed plot into a
  300 dpi bitmap.
- **Plots stay at true size**, so 6 pt text stays 6 pt, and the pre-export check warns you about
  anything smaller than a journal allows.
- **Placed files stay linked.** Re-run your R code and the panel updates by itself. A copy is also
  stored in the document, so it opens complete on a labmate's computer.
- **Journal page sizes** are built in (Nature, Science, Cell, PNAS, PLOS Genetics and more), and
  fonts that R leaves out of its PDFs are embedded when you export.

> **Status: early version, for collaborators' feedback.** "FigAssemble" is a working name.
> It's used daily on a Mac; Windows should work but hasn't been tried on a real Windows computer
> yet, so please [report anything odd](#feedback).

## Install

You'll need about 2 GB of free disk space and an internet connection. The installer sets up
everything FigAssemble needs, including conda (Miniforge) if you don't have it. The first install
takes 5-15 minutes; nothing else on your computer is changed.

**First, download FigAssemble.** This repository is private, so you need a GitHub account that
Matthew has added to it. On this page, click the green **Code** button, then **Download ZIP**.

### Mac

1. Open the downloaded ZIP (double-click it in Downloads). You get a folder called
   `FigAssemble-main`.
2. In that folder, double-click **`install-mac.command`**.
   - If macOS says it can't open it (*"Apple could not verify…"*), click **Done**, open
     **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to
     `install-mac.command`. (On macOS 14 and older: Control-click the file, choose **Open**,
     then **Open** again.)
   - Or open **Terminal**, type `bash ` (with a space after it), drag `install-mac.command` into
     the Terminal window and press Return.
3. A Terminal window shows the progress. When it finishes, FigAssemble opens. From now on it's in
   your **Applications** folder like any other app.

### Windows

1. Right-click the downloaded ZIP and choose **Extract All**, then open the extracted
   `FigAssemble-main` folder. (Run the installer from the extracted folder, not from inside the ZIP.)
2. Double-click **`install-windows.bat`**. If Windows says it *protected your PC*, click
   **More info**, then **Run anyway**.
3. A window shows the progress. When it finishes, FigAssemble starts. From now on, start it from
   the **Start menu** or the **desktop** shortcut.

**Updating:** download the newest ZIP and run the installer again. It updates FigAssemble and
everything it uses, and keeps your settings. You can delete the downloaded folder after installing.

**Removing it:** see [the user guide](docs/guide.md#removing-figassemble).
**If something goes wrong:** see [Troubleshooting](docs/guide.md#troubleshooting).

## Quick start

1. **Choose a page size.** With nothing selected, the panel on the right shows the page: pick a
   **Journal** and **Figure type** (say *Nature*, *Double column*), or a standard size.
2. **Drop in your plots.** Drag PDF, SVG, PNG, JPEG or TIFF files from Finder or Explorer onto the
   page, or use **Picture** (I) in the tools on the left. They land at true size.
3. **Arrange them.** Drag them into place. Magenta lines show when edges and centres line up;
   hold ⌘ (Ctrl on Windows) to drag freely. The **Arrange** tab aligns and spaces several at once.
4. **Label and annotate.** Press **P** and click to add panel labels (a, b, c…). Add text (T) and
   arrows (A). Drop an arrow's end on an object's corner or edge to attach it.
5. **Export.** Click **Check** to look for problems, then **Export** (⌘E) for PDF, SVG, PNG or TIFF.
   Save your work with ⌘S as a `.figasm` document.

**New to it? Follow the [tutorial](docs/tutorial.md)**: it builds the figure above in about
15 minutes, using the sample plots in [`examples/`](examples). Everything else is in the
**[user guide](docs/guide.md)**, including [all keyboard shortcuts](docs/guide.md#keyboard-shortcuts).

## Feedback

Feedback is the point of this early version: what's confusing, what's missing, what breaks.

- **[Report a problem](https://github.com/matthewwdavis/FigAssemble/issues/new?template=problem.yml)**: something didn't work, looked
  wrong in the export, or was confusing.
- **[Suggest an idea](https://github.com/matthewwdavis/FigAssemble/issues/new?template=idea.yml)**: something FigAssemble should do, or
  do differently.

Each form asks for the details that help, such as what you did, what you expected and Mac or Windows.
Screenshots help a lot: paste or drag them into the form. The version number is at the bottom of
**Settings**. You can see existing reports under [Issues](https://github.com/matthewwdavis/FigAssemble/issues).

## For developers

Running from source, tests, the editor self-test, screenshots and installers:
[docs/development.md](docs/development.md). Design decisions: [docs/design.md](docs/design.md);
progress: [docs/roadmap.md](docs/roadmap.md).

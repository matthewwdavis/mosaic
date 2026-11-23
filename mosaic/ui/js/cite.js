// Help ▸ Cite mosaic: the reference (APA) copied straight away and shown, with BibTeX and RIS to
// copy for a reference manager. The app writes them from CITATION.cff (labapp's citation.py), so
// the version and date are this copy's; once Zenodo gives a release a DOI, it's in them too.
import { rpc } from "./api.js";
import { announce, h } from "./util.js";

// Text onto the clipboard: by mosaic itself where it can (a menu bar command isn't a click in the
// page, which the page's own way needs), else the page's own way (Windows, Linux)
export async function copyText(text, html = null) {
  try {
    if (await rpc("copy_text", text, html)) return true;
  } catch { /* the page's own way, below */ }
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export async function citeDialog(panels) {
  const c = await rpc("citation");
  const copied = await copyText(c.apa, c.apa_html);
  const ref = h("p", { class: "cite-ref" });
  ref.innerHTML = c.apa_html;   // (escaped by citation.py: the title in italics)
  const status = h("p", { class: "hint", role: "status" },
    copied ? "Copied. Paste it into your reference list." : "Select the reference and copy it (⌘C or Ctrl+C).");
  const copyButton = (label, text, what, html = null) => {
    const b = h("button", { type: "button", class: "btn" }, label);
    b.addEventListener("click", async () => {
      status.textContent = (await copyText(text, html)) ? `${what} copied.` : `Couldn't copy the ${what.toLowerCase()}.`;
      announce(status.textContent);
    });
    return b;
  };
  const code = (label, text) => h("details", { class: "cite-code" }, h("summary", {}, label),
    h("pre", { tabindex: 0, style: { whiteSpace: "pre-wrap", userSelect: "text" } }, text));
  const dlg = panels.dialog(`Cite ${c.title}`, h("div", {},
    h("p", {}, `If ${c.title} helped make your figures, please cite it (version ${c.version}):`),
    ref, status,
    code("BibTeX", c.bibtex), code("RIS", c.ris),
    h("p", { class: "hint" }, "Reference managers take BibTeX or RIS: copy one, then in Zotero choose File ▸ Import from Clipboard.")),
  [copyButton("Copy Reference", c.apa, "The reference", c.apa_html), copyButton("Copy BibTeX", c.bibtex, "BibTeX"),
    copyButton("Copy RIS", c.ris, "RIS")], "Done");
  announce(copied ? `Copied the reference to cite ${c.title}` : `How to cite ${c.title}`);
  return dlg;
}

"""The reference styles' list: every journal in the Citation Style Language repository, by name and ISSN.

The Citation Style Language (CSL) repository (github.com/citation-style-language/styles, the styles
behind zotero.org/styles) has a reference style for about ten thousand journals, each with the
journal's name, ISSNs, often a link to its author guidelines, and whether its citations are numbered
or author and year. Both apps ship a compact copy of that list (csl_index.json.gz beside this file)
so a journal can be found by name or ISSN without a connection, and a new journal file started from
it (journalfile.from_csl / starter).

The copy is built from one pinned snapshot of the repository, checked by its SHA-256, never at run
time:

    python -m labapp.cslindex build STYLES.tar.gz --commit SHA --sha256 HEX [--out FILE]
        STYLES.tar.gz: https://codeload.github.com/citation-style-language/styles/tar.gz/<SHA>
    python -m labapp.cslindex search "tree genetics"

Each entry (a list, to keep the file small): [name, title, short title, ISSN, eISSN, citation format,
parent style, documentation links, publisher]. entry() turns one into a dict.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sys
import tarfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(HERE, "csl_index.json.gz")
NS = "{http://purl.org/net/xbiblio/csl}"
FIELDS = ("name", "title", "short", "issn", "eissn", "citations", "parent", "links", "publisher")
REPOSITORY = "https://github.com/citation-style-language/styles"

# Publishers named by the folder the CSL project's generator read a dependent style from ("Generated
# with .../generate_dependent_styles/data/<folder>"), else by the parent style's name.
PUBLISHERS = {
    "springer": "Springer", "springer-nature": "Springer Nature", "nature": "Springer Nature", "bmc": "BioMed Central",
    "biomed-central": "BioMed Central", "elsevier": "Elsevier", "cell": "Cell Press", "taylor-and-francis": "Taylor & Francis",
    "sage": "SAGE", "wiley": "Wiley", "frontiers": "Frontiers", "mdpi": "MDPI", "multidisciplinary-digital-publishing-institute": "MDPI",
    "american-chemical-society": "American Chemical Society", "acs": "American Chemical Society", "ieee": "IEEE",
    "institute-of-physics": "IOP Publishing", "iop": "IOP Publishing", "royal-society-of-chemistry": "Royal Society of Chemistry",
    "rsc": "Royal Society of Chemistry", "cambridge-university-press": "Cambridge University Press", "oxford-university-press": "Oxford University Press",
    "oup": "Oxford University Press", "plos": "PLOS", "copernicus-publications": "Copernicus", "copernicus": "Copernicus", "karger": "Karger",
    "thieme": "Thieme", "pensoft": "Pensoft", "hindawi": "Hindawi", "aims": "AIMS Press", "american-physical-society": "American Physical Society",
    "aps": "American Physical Society", "american-meteorological-society": "American Meteorological Society", "inter-research": "Inter-Research",
    "mary-ann-liebert": "Mary Ann Liebert", "spandidos": "Spandidos", "dove-medical-press": "Dove Medical Press", "bmj": "BMJ",
    "american-medical-association": "American Medical Association", "ama": "American Medical Association", "edp-sciences": "EDP Sciences",
    "wolters-kluwer": "Wolters Kluwer", "lippincott": "Wolters Kluwer", "de-gruyter": "De Gruyter", "brill": "Brill", "emerald": "Emerald",
    "american-society-for-microbiology": "American Society for Microbiology", "asm": "American Society for Microbiology",
    "the-company-of-biologists": "The Company of Biologists", "american-physiological-society": "American Physiological Society",
    "american-society-of-agronomy": "American Society of Agronomy", "american-phytopathological-society": "American Phytopathological Society",
    "iucr": "International Union of Crystallography", "international-union-of-crystallography": "International Union of Crystallography",
    "scielo": "SciELO", "trends": "Cell Press", "the-lancet": "Elsevier", "annual-reviews": "Annual Reviews", "emboj": "EMBO Press",
}
_PARENT_PUBLISHER = (("springer", "Springer"), ("elsevier", "Elsevier"), ("taylor-and-francis", "Taylor & Francis"),
                     ("bmc-", "BioMed Central"), ("biomed-central", "BioMed Central"), ("sage-", "SAGE"), ("frontiers", "Frontiers"),
                     ("multidisciplinary-digital-publishing-institute", "MDPI"), ("american-chemical-society", "American Chemical Society"),
                     ("ieee", "IEEE"), ("institute-of-physics", "IOP Publishing"), ("royal-society-of-chemistry", "Royal Society of Chemistry"),
                     ("cambridge-university-press", "Cambridge University Press"), ("oxford-university-press", "Oxford University Press"),
                     ("copernicus", "Copernicus"), ("karger", "Karger"), ("thieme", "Thieme"), ("plos", "PLOS"), ("pensoft", "Pensoft"),
                     ("american-medical-association", "American Medical Association"), ("cell", "Cell Press"), ("nature", "Springer Nature"),
                     ("wiley", "Wiley"), ("american-society-for-microbiology", "American Society for Microbiology"),
                     ("american-physiological-society", "American Physiological Society"), ("annual-reviews", "Annual Reviews"),
                     ("mary-ann-liebert", "Mary Ann Liebert"), ("american-society-of-plant-biologists", "American Society of Plant Biologists"))


def _name_of(url: str | None) -> str:
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def info(csl_text: str, name: str | None = None) -> dict:
    """What a style's <info> says about its journal: {"name", "title", "short", "issn", "eissn",
    "citations" ("numeric", "author-date", "note", "label", "author" or ""), "parent" (the style a
    dependent style takes its rules from), "links" (its documentation links), "publisher" (when the
    style names it), "dependent"}. ValueError when it isn't a style."""
    try:
        root = ET.fromstring(csl_text.encode("utf-8") if isinstance(csl_text, str) else csl_text)
    except ET.ParseError as exc:
        raise ValueError(f"That isn't a reference style (a .csl file): {exc}") from None
    if root.tag != NS + "style":
        raise ValueError("That isn't a reference style (a .csl file).")
    inf = root.find(NS + "info")
    if inf is None:
        raise ValueError("That reference style has no <info> about its journal.")
    text = lambda tag: " ".join((inf.findtext(NS + tag) or "").split())   # noqa: E731
    links = [(ln.get("rel"), ln.get("href")) for ln in inf.findall(NS + "link")]
    self_url = next((h for r, h in links if r == "self"), None) or text("id")
    parent = _name_of(next((h for r, h in links if r == "independent-parent"), None))
    cat = next((c.get("citation-format") for c in inf.findall(NS + "category") if c.get("citation-format")), "")
    issns = [" ".join((e.text or "").split()) for e in inf.findall(NS + "issn")]
    eissn = text("eissn")
    gen = re.search(r"generate_dependent_styles/data/([A-Za-z0-9_-]+)", csl_text if isinstance(csl_text, str) else csl_text.decode("utf-8", "replace"))
    publisher = PUBLISHERS.get(gen.group(1).lower(), "") if gen else ""
    if not publisher and parent:
        publisher = next((p for pre, p in _PARENT_PUBLISHER if parent.startswith(pre)), "")
    return {"name": name or _name_of(self_url), "title": text("title"), "short": text("title-short"),
            "issn": issns[0] if issns else "", "eissn": eissn, "citations": cat, "parent": parent,
            "links": [h for r, h in links if r == "documentation" and h], "publisher": publisher,
            "dependent": bool(parent)}


# The shipped list ------------------------------------------------------------------------------------

_INDEX: dict | None = None


def load(path: str | None = None) -> dict:
    """The list as shipped: {"format", "source": {"repository", "commit", "sha256", "date", "styles"},
    "styles": [entry lists]}. An empty list when the file is missing (a build without it)."""
    global _INDEX
    if path:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    if _INDEX is None:
        try:
            with gzip.open(INDEX_PATH, "rt", encoding="utf-8") as fh:
                _INDEX = json.load(fh)
        except OSError:
            _INDEX = {"format": 1, "source": {}, "styles": []}
    return _INDEX


def entry(row: list) -> dict:
    out = dict(zip(FIELDS, row))
    out["links"] = list(out.get("links") or [])
    return out


def _fold(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(w for w in s.split() if w not in ("the", "of", "and", "journal"))


def _issn(q: str) -> str | None:
    m = re.fullmatch(r"\s*(\d{4})-?(\d{3}[\dxX])\s*", q)
    return f"{m.group(1)}-{m.group(2).upper()}" if m else None


def _initials(title: str) -> str:
    return "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", title) if w.lower() not in ("the", "of", "and", "for", "in", "on", "de"))\
        .lower()


def find(name: str, index: dict | None = None) -> dict | None:
    """One style by its name ("tree-genetics-and-genomes"), or None."""
    for row in (index or load())["styles"]:
        if row[0] == name:
            return entry(row)
    return None


def search(query: str, limit: int = 20, index: dict | None = None) -> list[dict]:
    """Styles for a journal's name or ISSN (with or without the hyphen): an exact ISSN first, then
    an exact name, names that start with the words, then names holding every word in any order, then initials
    ("MBE").
    Within each, journals' own styles (dependent ones: a journal's) before general ones, then shorter
    names first."""
    rows = (index or load())["styles"]
    q = (query or "").strip()
    if not q:
        return []
    issn = _issn(q)
    if issn:
        return [entry(r) for r in rows if issn in (r[3], r[4])][:limit]
    fq = _fold(q)
    words = fq.split()
    if not words:
        return []
    ranked = []
    for r in rows:
        title, short = _fold(r[1]), _fold(r[2] or "")
        slugs = r[0].replace("-", " ")
        if fq == title:
            rank = 0
        elif fq == short:
            rank = 1
        elif title.startswith(fq) or (short and short.startswith(fq)):
            rank = 2
        elif all(any(w in n.split() or (len(w) > 3 and any(x.startswith(w) for x in n.split())) for n in (title, short, slugs)) for w in words):
            rank = 3
        elif len(words) == 1 and len(fq) >= 2 and fq == _initials(r[1]):
            rank = 4   # (MBE: Molecular Biology and Evolution)
        else:
            continue
        ranked.append((rank, 0 if r[6] else 1, len(r[1]), r[1].lower(), r))
    ranked.sort(key=lambda t: t[:4])
    return [entry(t[4]) for t in ranked[:limit]]


# Building the list -----------------------------------------------------------------------------------

def build(tar_path: str, commit: str, sha256: str, out: str = INDEX_PATH, date: str | None = None) -> dict:
    """The list from a snapshot of the repository (a .tar.gz of one commit), checked against its
    SHA-256 first. Writes out (gzipped JSON) and returns {"styles": count, "bytes": size}."""
    h = hashlib.sha256()
    with open(tar_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != sha256.lower():
        raise ValueError(f"{tar_path}: its SHA-256 is {h.hexdigest()}, not the {sha256} given: not the snapshot asked for")
    rows = []
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in tar:
            parts = m.name.split("/")
            if not m.isfile() or not m.name.endswith(".csl") or not (len(parts) == 2 or (len(parts) == 3 and parts[1] == "dependent")):
                continue
            data = tar.extractfile(m).read().decode("utf-8", "replace")
            try:
                i = info(data, parts[-1][:-4])
            except ValueError:
                continue
            rows.append([i["name"], i["title"], i["short"] if i["short"] != i["title"] else "", i["issn"], i["eissn"],
                         i["citations"], i["parent"], i["links"][:2], i["publisher"]])
    rows.sort(key=lambda r: r[0])
    data = {"format": 1, "source": {"repository": REPOSITORY, "commit": commit, "sha256": sha256.lower(),
                                    "tarball": f"https://codeload.github.com/citation-style-language/styles/tar.gz/{commit}",
                                    "date": date or "", "styles": len(rows),
                                    "licence": "CC BY-SA 3.0 (the CSL styles' licence)"},
            "fields": list(FIELDS), "styles": rows}
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(out + ".tmp", "wb") as fh, gzip.GzipFile(filename="", fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(raw)   # (no name or time in the header: the same snapshot gives the same file)
    os.replace(out + ".tmp", out)
    return {"styles": len(rows), "bytes": os.path.getsize(out)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m labapp.cslindex", description="The reference styles' list (CSL): build or search it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("tarball")
    b.add_argument("--commit", required=True)
    b.add_argument("--sha256", required=True)
    b.add_argument("--date", default="")
    b.add_argument("--out", default=INDEX_PATH)
    s = sub.add_parser("search")
    s.add_argument("query")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        got = build(args.tarball, args.commit, args.sha256, args.out, args.date)
        print(f"{args.out}: {got['styles']} styles, {got['bytes']} bytes")
        return 0
    for e in search(args.query):
        print(f"{e['name']}\t{e['title']}\t{e['issn']} {e['eissn']}\t{e['citations']}\t{e['publisher']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

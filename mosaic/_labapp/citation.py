"""How to cite an app: its CITATION.cff read, and the reference written out for Help > Cite.

Each app keeps CITATION.cff at its repository's root (GitHub's "Cite this repository" and Zenodo
read it) and the same file in <package>/data/CITATION.cff, which an installed copy has; a release
sets both files' version and date (release.cite_version). This reads the small part of the
Citation File Format the apps use: top-level `key: value` lines and an `authors` list of
`family-names`, `given-names` and `orcid`, and writes the reference as APA 7 (plain text and
HTML, the title in italics), BibTeX and RIS.
"""
from __future__ import annotations

import re


def _value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def read_cff(text: str) -> dict:
    """{"title", "version", "date-released", "doi", "url", "repository-code", ..., "authors": [...]}"""
    out: dict = {"authors": []}
    key = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        top = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if top:
            key, value = top.group(1), top.group(2)
            if value and key != "authors":
                out[key] = _value(value)
            continue
        if key != "authors":
            continue
        item = re.match(r"^\s*-\s+([\w-]+):\s*(.*)$", line)
        if item:
            out["authors"].append({item.group(1): _value(item.group(2))})
            continue
        more = re.match(r"^\s+([\w-]+):\s*(.*)$", line)
        if more and out["authors"]:
            out["authors"][-1][more.group(1)] = _value(more.group(2))
    return out


def _initials(given: str) -> str:
    return " ".join(f"{part[0]}." for part in re.split(r"[\s]+", given.strip()) if part)


def _apa_authors(authors: list[dict]) -> str:
    names = [f"{a.get('family-names', '')}, {_initials(a.get('given-names', ''))}".strip(", ") for a in authors]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + ", & " + names[-1]


def _link(cff: dict) -> str:
    return f"https://doi.org/{cff['doi']}" if cff.get("doi") else cff.get("repository-code") or cff.get("url", "")


def formats(cff: dict) -> dict:
    """The reference as {"apa", "apa_html", "bibtex", "ris"} (and "title", "version")."""
    title, version = cff.get("title", ""), cff.get("version", "")
    date = cff.get("date-released", "")
    year = date[:4]
    authors = cff.get("authors", [])
    zenodo = " Zenodo." if cff.get("doi") else ""
    who = _apa_authors(authors)
    what = f" (Version {version})" if version else ""
    apa = f"{who} ({year or 'n.d.'}). {title}{what} [Computer software].{zenodo} {_link(cff)}".strip()
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    apa_html = (f"{esc(who)} ({year or 'n.d.'}). <i>{esc(title)}</i>{esc(what)} [Computer software].{zenodo} "
                f"{esc(_link(cff))}").strip()
    first = re.sub(r"\W", "", authors[0].get("family-names", "")) if authors else "anon"
    fields = [("author", " and ".join(f"{a.get('family-names', '')}, {a.get('given-names', '')}".strip(", ") for a in authors)),
              ("title", title), ("version", version), ("year", year),
              ("month", str(int(date[5:7])) if len(date) >= 7 else ""),
              ("doi", cff.get("doi", "")), ("url", cff.get("repository-code") or cff.get("url", ""))]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
    key = "_".join(x for x in (first, re.sub(r"[^A-Za-z0-9]", "", title), year) if x)
    bibtex = f"@software{{{key},\n{body}\n}}\n"
    ris = ["TY  - COMP"] + [f"AU  - {a.get('family-names', '')}, {a.get('given-names', '')}" for a in authors]
    ris += [f"TI  - {title}"]
    ris += [f"PY  - {year}"] if year else []
    ris += [f"DA  - {date.replace('-', '/')}"] if date else []
    ris += [f"ET  - {version}"] if version else []
    ris += ["PB  - Zenodo", f"DO  - {cff['doi']}"] if cff.get("doi") else []
    ris += [f"UR  - {cff.get('repository-code') or cff.get('url', '')}", "ER  - ", ""]
    return {"title": title, "version": version, "apa": apa, "apa_html": apa_html, "bibtex": bibtex, "ris": "\n".join(ris)}


def load(path: str) -> dict:
    """formats() of the CITATION.cff at path."""
    with open(path, encoding="utf-8") as fh:
        return formats(read_cff(fh.read()))

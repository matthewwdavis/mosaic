"""Reading a journal's author guidelines into its journal file, by rules: no AI service, nothing sent anywhere.

The person gives the guidelines' address (or a page or PDF they saved). text_of_html / text_of_pdf
turn it into plain text; extract() finds, sentence by sentence, what a journal file can hold: word
limits (abstract, main text, title, legends), how many figures, tables, references and keywords,
the sections and their order, the statements asked for, figure sizes, resolution, file formats and
fonts, and hints about the reference style. Each finding ("proposal") carries the sentence it came
from, quoted, so the person can judge it; apply() writes the ones they accept into a journal file,
each sentence kept as that section's "evidence".

    python -m labapp.guidelines PAGE.html|PAGE.pdf|PAGE.txt     # what it finds, with the sentences

Reading a page from the web (fetch) happens only when the person asks for it (a button), with
Python's own urllib: https only, a size limit, no cookies kept.

The rules were written against the 16 built-in journals' guideline pages (labapp's
tests/data/guidelines) and are measured against their checked journal files (tests/test_guidelines.py
reports how many fields come out right).
"""
from __future__ import annotations

import copy
import html as _html
import re
import sys
from html.parser import HTMLParser

MAX_BYTES = 8_000_000

# Plain text --------------------------------------------------------------------------------------------

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6",
          "dt", "dd", "blockquote", "pre", "header", "footer", "td", "th", "hr", "figure", "figcaption", "main", "aside", "dl"}
_SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "head", "button", "select", "form", "nav"}
_CHROME = re.compile(r"(^|[\s_-])(nav|navbar|menu|footer|header|breadcrumb|cookie|banner|sidebar|skip|social|share|"
                     r"site-?header|site-?footer|global-?header|ad-?slot|advert|modal|popup|signin|login)($|[\s_-])", re.I)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip: list[str] = []      # (open tags whose text is left out)
        self.stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        chrome = bool(_CHROME.search(" ".join(filter(None, (a.get("class"), a.get("id"), a.get("role"))))))
        if tag in _SKIP or (chrome and tag in ("div", "section", "aside", "header", "footer", "ul")) or tag in ("header", "footer"):
            if tag not in ("br", "hr", "img", "meta", "link", "input"):
                self.skip.append(tag)
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n## ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if self.skip and self.skip[-1] == tag:
            self.skip.pop()
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n")
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_startendtag(self, tag, attrs):
        if not self.skip and tag in ("br", "hr"):
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def text_of_html(page: str) -> str:
    """A web page's readable text: headings as "## Heading", list items as "- item", one paragraph a
    line, the site's menus, scripts and footers left out."""
    p = _Text()
    try:
        p.feed(page)
        p.close()
    except Exception:   # noqa: BLE001 (a broken page: what was read so far)
        pass
    return _tidy("".join(p.out))


def text_of_pdf(path_or_bytes) -> str:
    """A PDF's text, page by page (pypdfium2, which both apps have)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path_or_bytes)
    try:
        pages = []
        for i in range(len(doc)):
            tp = doc[i].get_textpage()
            pages.append(tp.get_text_range())
            tp.close()
    finally:
        doc.close()
    text = "\n\n".join(pages).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"-\n(?=[a-z])", "", text)   # (words hyphenated across lines)
    return _tidy(text)


def _tidy(text: str) -> str:
    text = _html.unescape(text).replace(" ", " ").replace(" ", " ").replace(" ", " ").replace("­", "")
    lines = [" ".join(ln.split()) for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln in ("", "-", "|", "## ") or re.fullmatch(r"[|\s-]+", ln):
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def text_of(data: bytes, name: str = "") -> str:
    """Text from a saved page or PDF (bytes), whichever it is."""
    if data[:5] == b"%PDF-" or name.lower().endswith(".pdf"):
        return text_of_pdf(data)
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            s = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if re.search(r"<(html|body|div|p)\b", s[:20000], re.I) or name.lower().endswith((".html", ".htm", ".xhtml")):
        return text_of_html(s)
    return _tidy(s)


def fetch(url: str, user_agent: str = "Mozilla/5.0 (Macintosh) labapp-guidelines") -> tuple[bytes, str]:
    """A guidelines page from the web, when the person asks: (its bytes, the address it ended at).
    https (or http) only; at most 8 MB. OSError/ValueError say why not, in words."""
    import urllib.request
    url = (url or "").strip()
    if not re.match(r"^https?://[^\s/]+", url):
        raise ValueError("Give the page's web address, starting https://")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5",
                                               "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:   # noqa: S310 (http(s) only, above)
            data = resp.read(MAX_BYTES + 1)
            where = resp.geturl()
    except Exception as exc:   # noqa: BLE001 (HTTPError, URLError, timeouts: said in words)
        code = getattr(exc, "code", None)
        if code in (401, 403, 429):
            raise OSError(f"The journal's site turned the app away (HTTP {code}); many publishers do for anything that "
                          "isn't a browser. Open the page in your browser, save it (File ▸ Save As, Web Page or PDF) "
                          "and choose the saved file instead.") from None
        raise OSError(f"The page couldn't be read ({exc}). Check the address, or save the page from your browser "
                      "and choose the saved file.") from None
    if len(data) > MAX_BYTES:
        raise OSError("That page is larger than 8 MB; save the part with the author guidelines and choose it instead.")
    return data, where


# Sentences ---------------------------------------------------------------------------------------------

_ABBREV = r"(?:e\.g|i\.e|etc|vs|Fig|Figs|approx|ca|No|Nos|Dr|St|al|cf|Suppl|Vol|pp|incl|max|min|resp)"


def sentences(text: str) -> list[tuple[str, str]]:
    """The text as (topic, sentence) pairs, each sentence once: each line split at sentence ends; a
    list item or table row is one sentence. The topic is the heading it's under (a "## " heading, a
    short line without a full stop such as "Abstract", or a short list item heading the items after
    it), then " | " and the first sentences of this paragraph and the one before: what tells a
    research article's limits from a review's."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    head = sub = ""
    prev_first = ""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            head, sub, prev_first = line[3:].strip(), "", ""
            out.append((head, head))
            continue
        item = line.startswith("- ")
        line = line[2:] if item else line
        short = len(line) <= 60 and len(line.split()) <= 7 and line[:1].isupper() and not re.search(r"[.:;,!?)]$", line)
        if short and not item:
            head, sub, prev_first = line, "", ""   # (a line that reads as a heading)
            out.append((head, head))
            continue
        if short and item and len(line.split()) <= 5:
            sub = line   # (a list item that heads the items after it: "- Abstract", "- Include no more than 250 words")
            out.append((head + " > " + sub, line))
            continue
        parts: list[str] = []
        for piece in re.split(r"(?<=[.!?;])\s+(?=[A-Z(“\"‘'•])", line):
            if parts and re.search(rf"\b{_ABBREV}\.$", parts[-1]):
                parts[-1] += " " + piece   # ("e.g. Figure", "Fig. 1": not a sentence's end)
            else:
                parts.append(piece)
        first = parts[0].strip() if parts else ""
        topic = head + (" > " + sub if sub and item else "")
        context = " | ".join(x[:200] for x in (prev_first, first) if x)
        for i, s in enumerate(parts):
            s = s.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append((topic + (" | " + context if context and (i or prev_first) else ""), s))
        if not item:
            prev_first, sub = first, ""
    return out


def _norm(s: str) -> str:
    """A sentence for matching: abbreviations' full stops taken out (max. 250 words), dashes as hyphens."""
    s = re.sub(r"\b(max|min|approx|ca|e\.g|i\.e|incl|no|nos|vs|resp)\.", lambda m: m.group(1).replace(".", ""), s, flags=re.I)
    return s.replace("–", "-").replace("—", " - ").replace("‑", "-")


_OTHER_TYPES = re.compile(r"\b(short (?:article|report|communication)s?|brief (?:report|communication|investigation|definitive report)s?|"
                          r"reviews?|mini-?reviews?|previews?|perspectives?|commentar(?:y|ies)|letters?(?! of)|correspondence|editorials?|"
                          r"essays?|opinions?|insights?|news|policy forums?|expert voices|book|methods? papers?|resources?|tools?|"
                          r"technical (?:note|advance)s?|technical reports?|research (?:note|highlight)s?|computer notes?|short communications?|"
                          r"replies|responses?|comments?|matters arising|hypothes[ie]s|viewpoints?|primers?|spotlights?)\b", re.I)
_RESEARCH = re.compile(r"\b(research (?:article|paper|report)s?|original (?:research|article|paper)s?|full[- ]length (?:article|paper)s?|"
                       r"regular (?:article|paper)s?|(?:main )?articles?(?! types?)|investigations?|papers?)\b", re.I)


_STRICT = re.compile(r"\b(research (?:article|paper|report)s?|original (?:research|article|paper)s?|full[- ]length|regular (?:article|paper)s?)\b", re.I)


def weight(topic: str, sentence: str) -> float:
    """How much a sentence speaks for a research article's rules: low in a paragraph about reviews,
    letters, brief reports and the like; high where it names research articles."""
    here = sentence[:160]
    other = _OTHER_TYPES.search(here) or (_OTHER_TYPES.search(topic) and not _STRICT.search(here))
    research = re.search(r"\b(research (?:article|paper)s?|original (?:research|article)s?|full[- ]length)", here + " " + topic, re.I)
    if other and not (research and not _OTHER_TYPES.search(here)):
        return 0.15
    return 2.0 if research else 1.0


# Numbers in words --------------------------------------------------------------------------------------

_SMALL = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
NUM = r"(\d{1,3}(?:[,\s]\d{3})+|\d+(?:\.\d+)?|" + "|".join(_SMALL) + r")"


def _num(s: str) -> float | None:
    s = s.strip().lower()
    if s in _SMALL:
        return _SMALL[s]
    s = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _int(s: str) -> int | None:
    v = _num(s)
    return int(v) if v is not None and v == int(v) else None


# What a journal file can take, and the words that find it -----------------------------------------------

LABELS = {
    "limits.abstract_words": "Abstract (or summary): most words",
    "limits.main_text_words": "Main text: most words",
    "limits.title_chars": "Title: most characters, with spaces",
    "limits.title_words": "Title: most words",
    "limits.legend_words": "Each figure legend: most words",
    "limits.references": "Most references",
    "limits.figures": "Most figures",
    "limits.tables": "Most tables",
    "limits.display_items": "Most figures and tables together (display items)",
    "limits.keywords": "Most keywords",
    "structure.keywords.min": "Fewest keywords",
    "structure.running_title.chars": "Running title: most characters",
    "structure.abstract.name": "What the abstract is called",
    "structure.sections": "The sections, in order",
    "structure.statements": "Statements asked for",
    "figures.types": "Figure widths",
    "figures.depth_mm": "Deepest a figure may be (mm)",
    "figures.pictures.photo": "Photographs: resolution (dpi)",
    "figures.pictures.line_art": "Line art: resolution (dpi)",
    "figures.pictures.combination": "Combination figures: resolution (dpi)",
    "figures.export.formats": "Figure file formats",
    "figures.text.fonts": "Fonts in figures",
    "figures.text.min_pt": "Smallest text in figures (pt)",
    "figures.text.max_pt": "Largest text in figures (pt)",
    "figures.labels.case": "Panel letters: capital or small",
    "figures.labels.bold": "Panel letters: bold",
    "captions.label": "What figures are called in the text",
    "references.citations": "How references are cited in the text",
    "references.max_authors": "Authors listed before et al.",
}

_WORDS = r"(?:words?|wds)"
_UPTO = r"(?:up to|no more than|not (?:to )?exceed(?:ing)?|maximum(?: of)?|max\.?|at most|limited to|less than|fewer than|under|within|≤|<|should be|must be|of|is|around|about|approximately|~|ca\.)"


def _near(sentence: str, words: str, span: int = 80) -> bool:
    return bool(re.search(words, sentence, re.I))


def _find_limit(s: str, subject: str, unit: str, max_gap: int = 90) -> tuple[int, str] | None:
    """A number of unit tied to subject in s: "abstract ... 250 words" or "250-word abstract"."""
    for m in re.finditer(subject, s, re.I):
        after = s[m.end(): m.end() + max_gap]
        a = re.match(rf"[^.;]*?{NUM}\s*(?:-|–|to)?\s*(?:{NUM})?\s*{unit}", after, re.I)
        if a:
            hi = _int(a.group(2)) if a.group(2) else _int(a.group(1))
            if hi:
                return hi, a.group(0)
        before = s[max(0, m.start() - max_gap): m.start()]
        b = re.search(rf"{NUM}\s*(?:-|–)?\s*{unit}[^.;]{{0,40}}$", before, re.I)
        if b:
            v = _int(b.group(1))
            if v:
                return v, b.group(0)
    return None


_ABSTRACT = r"\b(abstracts?|summary|summaries|summary paragraph)\b"
_MAIN = r"\b(main text|manuscript|article|paper|text|body|research articles?|articles?)\b"


_QUAL = r"(?:up to|no more than|not (?:to )?exceed(?:ing)?|a maximum of|maximum of|maximum|max|at most|limited to|limit of|fewer than|" \
        r"less than|under|about|approximately|~|≤|<|as many as)"
COUNTS = [
    ("limits.display_items", r"display items?|graphical elements?|figures? (?:and|or|and/or|/|plus)\s*tables?|tables? (?:and|or|and/or|/)\s*figures?|"
                             r"figures?\s*\+\s*tables?|figures? or tables", 1, 20),
    ("limits.references", r"(?:main[- ]text )?references|citations", 10, 300),
    ("limits.figures", r"figures?|illustrations?", 1, 20),
    ("limits.tables", r"tables?", 1, 20),
]


def _count_matches(s: str, word: str):
    """Where s gives a most-allowed number of word: "up to 50 references", "3 to 5 display items"
    (the larger), "references ... limited to 50", "50 references maximum"."""
    rng = rf"(?:{NUM}\s*(?:-|to|or)\s*)?(?P<n>{NUM})"
    yield from re.finditer(rf"\b{_QUAL}\s+{rng}\s+(?:[\w-]+\s+){{0,2}}?(?:{word})\b", s, re.I)
    yield from re.finditer(rf"\b(?:{word})\b[^.;:]{{0,30}}?(?:limited to|up to|no more than|maximum(?: of)?|max|not exceed|≤)\s*(?P<n>{NUM})\b"
                           r"(?!\s*(?:mm|cm|words|dpi|pt|%|MB|pages))", s, re.I)
    yield from re.finditer(rf"\b{rng}\s+(?:[\w-]+\s+)?(?:{word})\b\s*\(?(?:maximum|max|at most|or fewer|or less)\b", s, re.I)
    yield from re.finditer(rf"\b(?:\d|one|two|three|four|five)\s*(?:-|to)\s*(?P<n>{NUM})\s+(?:[\w-]+\s+)?(?:{word})\b", s, re.I)


def _limits(sents: list[tuple[str, str]]) -> list[dict]:
    found: list[dict] = []

    for head, s0 in sents:
        w = weight(head, s0)

        def add(field, value, sent, score=1.0, w=w):
            found.append({"field": field, "value": value, "evidence": sent, "score": score * w})

        s = _norm(s0)
        low = s.lower()
        if len(s) > 900:
            continue
        under = head.split(" | ")[0].lower()
        not_abstract = r"significance|lay summary|plain language|author summary|one-sentence|teaser|graphical|editor'?s? summary|" \
                       r"article summary|non-specialist|non-technical|in brief|etoc|highlights?|enhanced abstract|one-page summary|visual abstract|video"
        # Abstract or summary words ("an abstract of no more than 250 words", "150-word summary", or
        # "Include no more than 250 words" under a heading "Abstract")
        if re.search(_WORDS, low) and not re.search(not_abstract, low):
            got = _find_limit(s, _ABSTRACT, _WORDS) if re.search(_ABSTRACT, low) else None
            if not got and re.search(r"(^|> )(abstract|summary)s?$", under.split(" > ")[-1] if " > " in under else under) and \
                    not re.search(not_abstract, under):
                m = re.search(rf"{NUM}\s*{_WORDS}", s, re.I)
                got = (_int(m.group(1)), m.group(0)) if m and _int(m.group(1)) else None
            if got and 50 <= got[0] <= 600:
                named = 1.0 if re.search(r"abstract", low) else 0.6 if re.search(r"abstract", under) else 0.3   # (a "summary" may be another part)
                add("limits.abstract_words", got[0], s0, named * (1.0 + (0.5 if re.search(r"abstract|summary", under) else 0)))
        # Main text words ("should not exceed 5,000 words", "word count ... under 7,000")
        if re.search(_WORDS + r"|word count|word limit", low):
            hits = [(m, _int(m.group(1))) for m in re.finditer(rf"{NUM}\*?\s*{_WORDS}", s, re.I)]
            hits += [(m, _int(m.group(1))) for m in re.finditer(rf"word (?:count|limit)[^.;]{{0,90}}?(?:under|below|of|is|exceed|maximum|max|up to)\s*{NUM}", s, re.I)]
            for m, v in hits:
                if v and 1500 <= v <= 20000:
                    ctx = s[max(0, m.start() - 160): m.end() + 80].lower()
                    near = s[max(0, m.start() - 45): m.start()].lower()
                    if re.search(_ABSTRACT, near) and not re.search(r"excluding|not including|plus|and|including", near):
                        continue
                    close = s[max(0, m.start() - 45): m.end() + 15].lower()
                    if re.search(r"main text|manuscript|article|text|research paper|word count|length|words in total|total|main body", ctx) and \
                            not re.search(r"legend|caption", close) and \
                            not re.search(r"cover letter|response|review(er)?s?\b|methods? section|perspective|commentar|letter to|"
                                          r"reply|correspondence|brief communication|short report|editorial|news|insight|page of text|"
                                          r"uninterrupted page", ctx):
                        add("limits.main_text_words", v, s0, 1.0 + (0.5 if re.search(r"research (article|paper)|original|main text", ctx) else 0))
        # Title characters / words
        if re.search(r"\btitles?\b", low) and not re.search(r"running|short title|running head|table titles?|figure titles?|legend|reference", low):
            got = _find_limit(s, r"\btitles?\b", r"characters?")
            if got and 40 <= got[0] <= 400:
                add("limits.title_chars", got[0], s)
            got = _find_limit(s, r"\btitles?\b", _WORDS, 60)
            if got and 5 <= got[0] <= 40:
                add("limits.title_words", got[0], s)
        # Running title characters
        if re.search(r"running (title|head)|short title", low):
            got = _find_limit(s, r"running (?:title|head)|short title", r"characters?")
            if got and 20 <= got[0] <= 120:
                add("structure.running_title.chars", got[0], s)
        # Legend words
        if re.search(r"legends?|captions?", low) and re.search(_WORDS, low) and not re.search(r"table", low[:40]) and \
                not re.search(r"summary figure|graphical|lay-language|cover|image credit", low):
            got = _find_limit(s, r"(?:figure )?(?:legends?|captions?)", _WORDS)
            if got and 50 <= got[0] <= 600:
                add("limits.legend_words", got[0], s)
        # How many references, display items, figures, tables ("up to 50 references", "3 to 5 display
        # items", "no more than seven figures and/or tables", "Max 8 tables or figures")
        taken: list[tuple[int, int]] = []
        for field, word, lo, hi in COUNTS:
            for m in _count_matches(s, word):
                if any(m.start() < e and m.end() > b for b, e in taken):
                    continue   # (the words already read as display items)
                v = _int(m.group("n"))
                if v and lo <= v <= hi and not re.search(r"supplement|extended data|per figure|panels?|additional|online|"
                                                          r"\bin (?:the )?supporting", s[max(0, m.start() - 40): m.end() + 30], re.I):
                    add(field, v, s0)
                    taken.append((m.start(), m.end()))
                    break
        # Keywords
        if re.search(r"key ?words?", low):
            m = re.search(rf"{NUM}\s*(?:-|–|to)\s*{NUM}\s+(?:\w+\s+)?key ?words?", s, re.I) or \
                re.search(rf"key ?words?[^.;]{{0,60}}?(?:between\s+)?{NUM}\s*(?:-|–|to|and)\s*{NUM}\b", s, re.I)
            if m and _int(m.group(1)) and _int(m.group(2)) and _int(m.group(1)) < _int(m.group(2)) <= 15:
                add("structure.keywords.min", _int(m.group(1)), s)
                add("limits.keywords", _int(m.group(2)), s)
            else:
                m = re.search(rf"(?:{_UPTO})\s+{NUM}\s+(?:\w+\s+)?key ?words?", s, re.I) or \
                    re.search(rf"key ?words?[^.;]{{0,40}}?(?:up to|no more than|maximum(?: of)?|max\.?|at most|limited to)\s*{NUM}", s, re.I) or \
                    re.search(rf"\b{NUM}\s+key ?words?", s, re.I)
                if m and _int(m.group(1)) and 2 <= _int(m.group(1)) <= 15:
                    add("limits.keywords", _int(m.group(1)), s)
    return found


# Sections and their order -------------------------------------------------------------------------------

SECTION_KINDS = [
    ("introduction", r"introduction|background"),
    ("results", r"results(?! and discussion)"),
    ("results_discussion", r"results and discussion"),
    ("discussion", r"discussion"),
    ("conclusions", r"conclusions?"),
    ("methods", r"(?:materials and |star )?methods(?: and materials)?|experimental procedures|online methods"),
    ("acknowledgements", r"acknowledge?ments?"),
    ("author_contributions", r"author(?:s'?|'s)? contributions?"),
    ("competing_interests", r"(?:competing|conflicts?) of interests?|competing interests|declaration of interests|conflict of interest(?: statement)?|disclosures?"),
    ("funding", r"funding(?: information| statement)?"),
    ("data_availability", r"data (?:and (?:code|materials?) )?availability(?: statement)?|data accessibility|data archiving|availability of data(?: and materials)?|data statement"),
    ("code_availability", r"code availability"),
    ("references", r"references|literature cited|bibliography"),
    ("figure_legends", r"figure legends|figure captions"),
    ("tables", r"tables"),
    ("supplementary", r"supplementary (?:information|material|data)|supporting information"),
    ("ethics", r"ethics(?: approval)?(?: statement)?|research ethics statement"),
]
_KIND_RE = [(k, re.compile(rf"^(?:\d+\.?\s*)?({p})\b", re.I)) for k, p in SECTION_KINDS]
_LIST_SPLIT = re.compile(r"\s*(?:,|;|→|>|•|\band\b(?= [A-Z])|\bthen\b)\s*|\s+-\s+|\n")


def _kind_of(name: str) -> str | None:
    n = name.strip(" .:*()\"'“”").strip()
    for k, rx in _KIND_RE:
        m = rx.match(n)
        if m and len(n) <= len(m.group(0)) + 14:
            return k
    return None


def _sections(sents: list[tuple[str, str]], text: str) -> list[dict]:
    """The order of sections: a sentence that names several in a row ("Introduction, Results,
    Discussion, Methods") or a list under a heading about the manuscript's parts."""
    found: list[dict] = []
    for _, s in sents:
        if len(s) > 700:
            continue
        low = s.lower()
        if not re.search(r"order|sections?|organi[sz]ed|structured?|headings?|should (?:include|contain|consist)|following|divided|"
                         r"arranged|comprise|format", low):
            continue
        tail = s.split(":", 1)[1] if ":" in s else s
        parts = [p for p in _LIST_SPLIT.split(tail) if p and p.strip()]
        kinds: list[tuple[str, str]] = []
        for p in parts:
            p = re.sub(r"\(.*?\)", "", p).strip(" .")
            p = re.sub(r"^(?:and|or|then|the|a|an|followed by)\s+", "", p, flags=re.I)
            k = _kind_of(p)
            if k and k not in [x[0] for x in kinds]:
                kinds.append((k, p.strip(" .:")))
        core = {"introduction", "results", "discussion", "methods", "results_discussion", "references"}
        if len(kinds) >= 3 and len([k for k, _ in kinds if k in core]) >= 2:
            found.append({"field": "structure.sections", "value": [{"kind": k, "name": _title_case(n)} for k, n in kinds],
                          "evidence": s, "score": len(kinds)})
    # A list of headings under one heading ("Manuscript format": - Title page - Abstract - Introduction ...)
    lines = text.split("\n")
    run: list[tuple[str, str]] = []
    run_lines: list[str] = []

    def close():
        core = {"introduction", "results", "discussion", "methods", "results_discussion", "references"}
        if len(run) >= 4 and len([k for k, _ in run if k in core]) >= 3:
            found.append({"field": "structure.sections", "value": [{"kind": k, "name": _title_case(n)} for k, n in run],
                          "evidence": "; ".join(run_lines)[:400], "score": len(run) - 0.5})

    for ln in lines:
        item = ln[2:].strip() if ln.startswith("- ") else (ln.strip() if len(ln) < 50 else "")
        item = re.sub(r"^\d+[.)]\s*", "", item)
        name = re.split(r"[:–—(]| - ", item, 1)[0].strip(" .*")
        k = _kind_of(name) if name and len(name) < 70 else None
        if k:
            if k not in [x[0] for x in run]:
                run.append((k, name))
                run_lines.append(item[:120])
        elif ln.startswith("- ") or not ln.strip():
            if not ln.strip():
                continue
            if re.match(r"(title|abstract|summary|key ?words|significance|highlights|graphical|eTOC|in brief|running|author)", item, re.I):
                continue   # (front matter between the sections: the run goes on)
            close()
            run, run_lines = [], []
        else:
            close()
            run, run_lines = [], []
    close()
    return found


def _title_case(name: str) -> str:
    name = " ".join(name.split())
    if name.isupper() and len(name) > 4:
        name = name.capitalize()
    return name[:1].upper() + name[1:]


# Statements ---------------------------------------------------------------------------------------------

STATEMENTS = [
    ("data_availability", "Data availability", r"data (?:availability|accessibility|archiving)|availability of data|data statement|data,? code,? and materials availability"),
    ("competing_interests", "Competing interests", r"competing (?:financial )?interests?|conflicts? of interest|declaration of interests"),
    ("author_contributions", "Author contributions", r"author(?:s'?|'s)? contributions?|credit (?:taxonomy|roles?)|contributor roles"),
    ("funding", "Funding", r"\bfunding (?:statement|information|sources?|section)|sources? of funding|financial support"),
    ("ethics", "Ethics", r"(?:research )?ethics statements?|ethics declarations?|ethics approval and consent"),
    ("code_availability", "Code availability", r"code availability"),
    ("ai_declaration", "Use of AI", r"\b(?:generative )?(?:ai|artificial intelligence|large language models?|llms?)\b[^.]{0,150}(?:declar|disclos|statement|describ|document|acknowledg)"),
]


def _statements(sents: list[tuple[str, str]]) -> list[dict]:
    got: dict[str, dict] = {}
    for head, s in sents:
        if len(s) > 600:
            continue
        low = s.lower()
        for kind, name, rx in STATEMENTS:
            if kind in got:
                continue
            if re.search(rx, low) and re.search(r"\b(must|should|required?|requires|include|mandatory|all (?:papers|manuscripts|articles)|"
                                                r"needs? to|please provide|are asked|state|declare|disclose|provide)\b", low):
                got[kind] = {"kind": kind, "name": name, "evidence": s}
    if not got:
        return []
    return [{"field": "structure.statements", "value": [{"kind": v["kind"], "name": v["name"]} for v in got.values()],
             "evidence": " / ".join(v["evidence"] for v in got.values())[:1200], "score": len(got),
             "each": {k: v["evidence"] for k, v in got.items()}}]


# Figures --------------------------------------------------------------------------------------------------

_LEN = (r"(\d+(?:\.\d+)?)\s*(mm\b|millimet(?:er|re)s?\b|cm\b|centimet(?:er|re)s?\b|inch(?:es)?\b|in\.(?=\s)|in\b(?=\s*(?:wide|width|high|\)|,|\(|x\b|×))|"
        r"\"|”|″|pt\b|points?\b|picas?\b|pixels?\b|px\b)")


def _mm(value: float, unit: str) -> float | None:
    u = unit.lower()
    if u.startswith("mm") or u.startswith("millim"):
        return value
    if u.startswith("cm") or u.startswith("centim"):
        return value * 10
    if u.startswith("in") or u in ('"', "”", "″"):
        return value * 25.4
    if u.startswith("pica"):
        return value * 25.4 / 6
    return None   # (points and pixels: not a figure's width)


def _width_name(ctx: str) -> str | None:
    if re.search(r"\b(?:3|three)[- ]columns?\b", ctx):
        return "Three columns"
    return next((n for rx, n in _WIDTH_NAMES if re.search(rx, ctx)), None)


_WIDTH_NAMES = [(r"1\.5[- ]columns?|one[- ]and[- ]a[- ]half|intermediate|medium", "One and a half columns"),
                (r"single[- ]column|\bone[- ]column|\b1[- ]column|half[- ]page|column width|narrow|\bsmall\b", "Single column"),
                (r"double[- ]column|two[- ]columns?|\b2[- ]columns?|full[- ]page|full[- ]width|page width|whole page|\blarge\b", "Double column")]


def _figures(sents: list[tuple[str, str]]) -> list[dict]:
    found: list[dict] = []
    widths: dict[str, tuple[float, str]] = {}
    depth: tuple[float, str] | None = None
    formats: dict[str, str] = {}
    sized: list[tuple[list[tuple[float, str | None]], str]] = []
    for head, s in sents:
        if len(s) > 700:
            continue
        low = s.lower()
        parts = head.split(" | ")
        if re.search(r"graphical abstract|visual abstract|toc (?:image|graphic|icon)|cover (?:image|art)|cover art|thumbnail|"
                     r"table of contents|journal cover|social media|teaser|video", " ".join([low, parts[0], parts[-1] if len(parts) > 1 else ""]).lower()):
            continue   # (another picture's rules, not the figures')
        figure_ctx = re.search(r"figure|artwork|illustration|image|graphic|panel|column|page width|width", low + " " + head.lower())
        if figure_ctx and re.search(_LEN, s, re.I) and not re.search(r"margins?\b|paper size|letter paper|\ba4\b|page size|sequences?\b|"
                                                                     r"\btables?\b", low):
            lens = [(m, _mm(float(m.group(1)), m.group(2))) for m in re.finditer(_LEN, s, re.I)]
            lens = [(m, v) for m, v in lens if v and 20 <= v <= 300 and
                    not re.search(r"font|letter(?:ing)? size|line (?:width|weight|thickness)|stroke|scale bar|symbols?", s[max(0, m.start() - 25): m.start()].lower())]
            # (the same length in inches and then in centimetres: the metric one)
            lens = [(m, v) for i, (m, v) in enumerate(lens)
                    if not (m.group(2).lower().startswith(("in", '"', "”", "″")) and i + 1 < len(lens) and lens[i + 1][0].start() - m.end() < 25
                            and abs(lens[i + 1][1] - v) <= 0.05 * v)]
            here: list[tuple[float, str | None]] = []
            for i, (m, v) in enumerate(lens):
                near_before = s[max(0, m.start() - 35): m.start()].lower()
                near_after = s[m.end(): m.end() + 30].lower()
                if re.search(r"[x×]\s*$", near_before) or (re.search(r"deep|depth|height|high\b|tall|length|vertical", near_before + " " + near_after)
                                                            and not re.search(r"\b(?:wide|width)\b", near_after[:12])):
                    if 100 <= v <= 260 and (depth is None or v > depth[0]):
                        depth = (round(v, 1), s)
                    continue
                if not re.search(r"wide|width|column|page|figure|size", s[max(0, m.start() - 80): m.end() + 60].lower()):
                    continue
                if here and abs(here[-1][0] - v) <= 1.5:
                    continue   # (the same width in other units: 3.25" (8.25 cm))
                nxt = lens[i + 1][0].start() if i + 1 < len(lens) else len(s)
                after = s[m.end(): min(nxt, m.end() + 60)].lower()
                before = s[max(0, m.start() - 50): m.start()].lower()
                if 30 <= v <= 230:
                    here.append((round(v, 1), _width_name(after) or _width_name(before.rsplit(",", 1)[-1])))
            if here:
                sized.append((here, s))
        # File formats
        if re.search(r"\b(?:tiff?|eps|pdf|jpe?g|png|svg)\b", low) and re.search(r"figure|artwork|image|graphic|illustration|photograph", low) and \
                re.search(r"accept|format|submit|prefer|should be|must be|supplied|provided|save", low) and \
                not re.search(r"supplement|supporting information|\bdocx?\b|latex|\bword\b|manuscript file|text file|reviewer", low):
            for f, rx in (("tiff", r"\btiff?\b"), ("eps", r"\beps\b"), ("pdf", r"\bpdf\b"), ("jpeg", r"\bjpe?g\b"), ("png", r"\bpng\b"),
                          ("svg", r"\bsvg\b"), ("pptx", r"\bpptx?\b|powerpoint")):
                if re.search(rx, low) and f not in formats:
                    formats[f] = s
        # Resolution
        for m in re.finditer(r"(?<![\d,])(\d,\d{3}|\d{3,4})\s*(?:dpi|ppi|pixels per inch|dots per inch)", s, re.I):
            v = int(m.group(1).replace(",", ""))
            ctx = s[max(0, m.start() - 120): m.end() + 60].lower()
            kind = "line_art" if re.search(r"line[- ]?art|line drawings?|monochrome|black and white|bitmap|1-bit", ctx) else \
                "combination" if re.search(r"combination|halftone[- ]and[- ]line|line/tone|mixed|combined", ctx) else \
                "photo" if re.search(r"photo|halftone|colou?r|grayscale|greyscale|images?|tone|raster", ctx) else None
            if kind and 150 <= v <= 2400:
                found.append({"field": f"figures.pictures.{kind}", "value": v, "evidence": s, "score": 1.0})
        # Fonts and sizes in figures
        if re.search(r"font|typeface|lettering|text|label", low) and figure_ctx:
            fonts = [f for f in ("Arial", "Helvetica", "Times New Roman", "Times", "Symbol", "Myriad", "Calibri", "Verdana") if re.search(rf"\b{f}\b", s)]
            if fonts and re.search(r"font|typeface|lettering", low):
                found.append({"field": "figures.text.fonts", "value": fonts, "evidence": s, "score": 1.0})
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:pt|points?|point)\b", s, re.I)
            if m and 4 <= float(m.group(1)) < float(m.group(2)) <= 14:
                found.append({"field": "figures.text.min_pt", "value": float(m.group(1)), "evidence": s, "score": 1.0})
                found.append({"field": "figures.text.max_pt", "value": float(m.group(2)), "evidence": s, "score": 1.0})
            else:
                m = re.search(r"(?:minimum|at least|no smaller than|not smaller than|not less than|min\.?|≥)\s*(?:of\s*)?(?:size\s*)?(\d+(?:\.\d+)?)\s*(?:-?\s*)(?:pt|points?|point)\b", s, re.I) or \
                    re.search(r"(\d+(?:\.\d+)?)\s*(?:pt|points?|point)\b[^.]{0,30}(?:minimum|or larger|or more|or bigger)", s, re.I)
                if m and 4 <= float(m.group(1)) <= 12:
                    found.append({"field": "figures.text.min_pt", "value": float(m.group(1)), "evidence": s, "score": 1.0})
        # Panel letters
        if re.search(r"panels?|parts? labels?|multi-?part", low) and re.search(r"letter|label", low):
            if re.search(r"lower[- ]?case|small letters|\(a\)|\ba\b, \bb\b|\(a, b, c\)", low) or re.search(r"\b(a|a\)|\(a\))\s*,\s*(b|b\)|\(b\))", s):
                found.append({"field": "figures.labels.case", "value": "lower", "evidence": s, "score": 1.0})
            elif re.search(r"upper[- ]?case|capital|\(A\)|\bA\b, \bB\b", s if "upper" not in low and "capital" not in low else low):
                found.append({"field": "figures.labels.case", "value": "upper", "evidence": s, "score": 1.0})
            if re.search(r"\bbold\b", low):
                found.append({"field": "figures.labels.bold", "value": True, "evidence": s, "score": 0.8})
        # What figures are called in the text
        m = re.search(r"(?:cited|referred to|abbreviated?|referenced)\s+(?:in the text\s+)?as\s+[\"“']?(Fig\.|Figure|Fig)\s*[\"”']?", s)
        if m:
            found.append({"field": "captions.label", "value": m.group(1), "evidence": s, "score": 1.0})
    if sized:
        here, sent = max(sized, key=lambda t: len(t[0]))   # (the sentence giving the most widths)
        names = [n for _, n in here]
        if any(n is None for n in names) or len(set(names)) < len(names):
            names = {1: ["Single column"], 2: ["Single column", "Double column"],
                     3: ["Single column", "One and a half columns", "Double column"]}.get(len(here)) or [f"Width {i + 1}" for i in range(len(here))]
        types = sorted(({"name": n, "width_mm": v} for (v, _), n in zip(here, names)), key=lambda t: t["width_mm"])
        found.append({"field": "figures.types", "value": types[:4], "evidence": sent, "score": len(types)})
    if depth:
        found.append({"field": "figures.depth_mm", "value": depth[0], "evidence": depth[1], "score": 1.0})
    if formats:
        found.append({"field": "figures.export.formats", "value": list(formats), "evidence": " / ".join(dict.fromkeys(formats.values()))[:900],
                      "score": len(formats)})
    return found


# Reference style hints ------------------------------------------------------------------------------------

def _references(sents: list[tuple[str, str]]) -> list[dict]:
    found: list[dict] = []
    for head, s in sents:
        if len(s) > 600:
            continue
        low = s.lower()
        if not re.search(r"referenc|citation|cite|bibliograph", low + " " + head.lower()):
            continue
        if re.search(r"numbered (?:consecutively|sequentially|in (?:the )?order)|cited (?:in the text )?by (?:superscript )?numbers?|"
                     r"(?:superscript|square[- ]bracket|bracketed)(?:ed)? numbers?|vancouver|in numerical order|numbered in (?:the )?order|"
                     r"numbered according to|consecutive numbers", low):
            found.append({"field": "references.citations", "value": "numeric", "evidence": s, "score": 1.0})
        elif re.search(r"author[- ](?:date|year)|name[- ](?:and[- ])?year|harvard|\(smith,? \d{4}\)|\(\w+ et al\.?,? \d{4}\)|"
                       r"alphabetical(?:ly)? (?:order|by)|by (?:the )?(?:first )?author'?s? (?:sur)?name|cited by author", low):
            found.append({"field": "references.citations", "value": "author-date", "evidence": s, "score": 1.0})
        m = re.search(r"(?:list|include|name|show)\s+(?:all|the first|up to|only the first)?\s*(\w+)\s+authors?\b[^.]{0,60}et al", s, re.I) or \
            re.search(r"(?:more than|over|exceeding)\s+(\w+)\s+authors?[^.]{0,60}et al", s, re.I)
        if m and _int(m.group(1)) and 1 <= _int(m.group(1)) <= 30:
            found.append({"field": "references.max_authors", "value": _int(m.group(1)), "evidence": s, "score": 0.8})
    return found


# Putting it together --------------------------------------------------------------------------------------

def extract(text: str) -> list[dict]:
    """Proposals for a journal file from the guidelines' text: [{"field", "label", "value",
    "evidence" (the sentence, quoted as it is), "others": other values found, each with its
    sentence}], one per field. Where the guidelines give several values for a field (article types),
    the one most often given for a research article wins; the others are listed for the person."""
    sents = sentences(text)
    found = _limits(sents) + _sections(sents, text) + _statements(sents) + _figures(sents) + _references(sents)
    by: dict[str, list[dict]] = {}
    for f in found:
        by.setdefault(f["field"], []).append(f)
    out = []
    for field in LABELS:
        got = by.get(field)
        if not got:
            continue
        tally: dict[str, list] = {}
        for f in got:
            key = repr(f["value"])
            t = tally.setdefault(key, [0.0, f])
            t[0] += f.get("score", 1.0)
        ranked = sorted(tally.values(), key=lambda t: -t[0])
        best = ranked[0][1]
        prop = {"field": field, "label": LABELS[field], "value": best["value"], "evidence": _quote(best["evidence"]),
                "others": [{"value": t[1]["value"], "evidence": _quote(t[1]["evidence"])} for t in ranked[1:4]]}
        if best.get("each"):
            prop["each"] = {k: _quote(v) for k, v in best["each"].items()}
        out.append(prop)
    return out


def _quote(s: str, most: int = 400) -> str:
    s = " ".join(s.split())
    return s if len(s) <= most else s[:most - 1].rsplit(" ", 1)[0] + "…"


# Into a journal file --------------------------------------------------------------------------------------

def apply(journal: dict, accepted: list[dict], source: str | None = None, today: str | None = None) -> dict:
    """The journal file with the accepted proposals written in (a copy): each value in its place,
    its sentence as that section's evidence, the guidelines' address as a source. accepted: the
    proposals the person kept, with their values as edited. Not checked here: figure widths without
    a depth (or the other way round) need the person's answer first; journalfile.validate says so."""
    import datetime
    j = copy.deepcopy(journal)
    day = today or datetime.date.today().isoformat()
    ev = lambda sec, p: _evidence(sec, p["evidence"])   # noqa: E731
    for p in accepted:
        field, value = p["field"], p.get("value")
        if value in (None, "", []):
            continue
        if field.startswith("limits."):
            lim = j.setdefault("limits", {})
            lim.setdefault("article_type", "Research article")
            if source:
                lim.setdefault("source", source)
            lim["checked"] = day
            lim.setdefault("limits", {})[field[7:]] = int(value)
            ev(lim, p)
            if field == "limits.abstract_words":
                j.setdefault("structure", {}).setdefault("abstract", {"name": "Abstract"})["words"] = int(value)
            if field == "limits.keywords":
                j.setdefault("structure", {}).setdefault("keywords", {})["max"] = int(value)
        elif field == "structure.keywords.min":
            j.setdefault("structure", {}).setdefault("keywords", {})["min"] = int(value)
        elif field == "structure.running_title.chars":
            j.setdefault("structure", {})["running_title"] = {"chars": int(value)}
        elif field == "structure.abstract.name":
            j.setdefault("structure", {}).setdefault("abstract", {})["name"] = str(value)
        elif field == "structure.sections":
            st = j.setdefault("structure", {})
            parts = [{"kind": x["kind"], "name": x["name"]} for x in value if x.get("kind") and x.get("name")]
            cut = next((i for i, x in enumerate(parts) if x["kind"] in ("references", "acknowledgements", "author_contributions",
                                                                         "competing_interests", "funding", "data_availability")), len(parts))
            st["body"] = parts[:cut]
            back = [x for x in parts[cut:]]
            have = {x["kind"] for x in back}
            st["back"] = back + [x for x in st.get("back", []) if x["kind"] not in have]
            ev(st, p)
        elif field == "structure.statements":
            st = j.setdefault("structure", {})
            have = {x["kind"] for part in ("body", "back", "front") for x in st.get(part, [])}
            back = st.setdefault("back", [])
            ref_at = next((i for i, x in enumerate(back) if x["kind"] == "references"), len(back))
            for x in value:
                said = ((p.get("each") or {}).get(x["kind"]) or "").lower()
                if x["kind"] == "ai_declaration" and re.search(r"method|acknowledg", said):
                    # (most journals want AI use described in a part that's there anyway, not a section of its own)
                    j.setdefault("statements", {})["ai"] = "methods" if "method" in said else "acknowledgements"
                    continue
                if x["kind"] not in have:
                    back.insert(ref_at, {"kind": x["kind"], "name": x["name"], "required": True})
                    ref_at += 1
                    have.add(x["kind"])
            ev(st, p)
        elif field == "figures.types":
            fig = j.setdefault("figures", {})
            fig["types"] = [{"name": t["name"], "width_mm": float(t["width_mm"])} for t in value if t.get("width_mm")]
            fig["source"] = source or fig.get("source") or "the journal's author guidelines"
            ev(fig, p)
        elif field == "figures.depth_mm":
            fig = j.setdefault("figures", {})
            fig["depth_mm"] = float(value)
            ev(fig, p)
        elif field.startswith("figures.pictures."):
            pic = j.setdefault("figures", {}).setdefault("pictures", {})
            pic[field.rsplit(".", 1)[1]] = int(value)
            pic["source"] = source or "the journal's author guidelines"
        elif field == "figures.export.formats":
            ex = j.setdefault("figures", {}).setdefault("export", {})
            ex["formats"] = list(value)
            ex["source"] = source or "the journal's author guidelines"
        elif field.startswith("figures.text."):
            tx = j.setdefault("figures", {}).setdefault("text", {})
            tx[field.rsplit(".", 1)[1]] = value if field.endswith("fonts") else float(value)
            tx["source"] = source or "the journal's author guidelines"
        elif field.startswith("figures.labels."):
            lb = j.setdefault("figures", {}).setdefault("labels", {})
            lb[field.rsplit(".", 1)[1]] = value
            lb["source"] = source or "the journal's author guidelines"
        elif field == "captions.label":
            j.setdefault("captions", {})["label"] = value
        elif field == "references.citations":
            ref = j.setdefault("references", {})
            ref.setdefault("citations", value)
            ev(ref, p)
        elif field == "references.max_authors":
            ref = j.setdefault("references", {})
            ev(ref, p)
    if accepted and source:
        src = j.setdefault("sources", [])
        if not any(x.get("url") == source for x in src):
            src.append({"url": source, "what": f"Author guidelines, read by the app's rules on {day}; each value the person accepted "
                                               "is quoted in its section's evidence."})
        if re.match(r"^https?://", source) and not j.get("guidelines"):
            j["guidelines"] = source
    readings = j.setdefault("evidence", {}) if isinstance(j.get("evidence"), (dict, type(None))) else None
    if readings is not None and accepted:
        readings["guidelines_read"] = {"date": day, "source": source or "",
                                       "fields": [{"field": p["field"], "value": p.get("value"), "sentence": p["evidence"]} for p in accepted]}
    return j


def _evidence(section: dict, sentence: str) -> None:
    have = section.get("evidence")
    items = [] if have is None else ([have] if isinstance(have, str) else list(have))
    if sentence not in items:
        items.append(sentence)
    section["evidence"] = items if len(items) > 1 else items[0]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    with open(argv[0], "rb") as fh:
        text = text_of(fh.read(), argv[0])
    for p in extract(text):
        print(f"{p['label']}: {p['value']}\n    “{p['evidence']}”")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Split 10-K filings (EDGAR inline-XBRL HTML) into their Items.

    python src/sections.py   parse every cached filing, write data/sections/*.json
                             and print the characters per section for checking
"""
import json
import re
import warnings
from collections import Counter

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from config import DATA_DIR
from fetch_filings import cache_path, load_filings

SECTIONS_DIR = DATA_DIR / "sections"

# Items in 10-K order. All of them mark section boundaries; only KEEP is stored.
ITEM_ORDER = ["1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8",
              "9", "9A", "9B", "9C", "10", "11", "12", "13", "14", "15", "16"]
KEEP       = ["1", "1A", "3", "7", "7A", "8"]

# "Item 7A. Quantitative..." / "ITEM 7. MANAGEMENT'S..." / "Item 7.Management's...".
# A comma after the number ("Item 8, Note 2. ...") is a cross-reference, not a heading.
HEADING = re.compile(r"^item\s*(\d{1,2}[a-c]?)\s*[.:]\s*(.*)$", re.IGNORECASE)

# A table-of-contents entry is followed by the next entry almost immediately;
# a real Item 1 heading is followed by the body of the Business section.
MIN_BODY_CHARS = 500

BLOCK_TAGS = ["p", "div", "tr", "li", "br", "table",
              "h1", "h2", "h3", "h4", "h5", "h6"]
CELL_TAGS  = ["td", "th"]
NOISE_LINE = re.compile(r"^(\d{1,3}|table of contents)$", re.IGNORECASE)

# Running page footers such as "Apple Inc. | 2025 Form 10-K | 20": a label,
# a pipe and a page number, with the same label on many pages. Lines without
# the pipe are left alone, since table labels ("2025 2024 2023") also repeat.
FOOTER_LINE        = re.compile(r"^(?P<label>.+?)\s*\|\s*\d{1,3}$")
FOOTER_MIN_REPEATS = 5


def html_to_lines(html):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")

    # Inline XBRL keeps its machine-readable facts in a hidden header.
    for header in soup.find_all("ix:header"):
        header.decompose()
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    for tag in soup.find_all(CELL_TAGS):
        tag.insert_after(" ")

    text  = soup.get_text().replace("\xa0", " ")
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.split("\n"))
    lines = [line for line in lines if line and not NOISE_LINE.match(line)]
    return strip_page_footers(lines)


def strip_page_footers(lines):
    def footer_label(line):
        match = FOOTER_LINE.match(line)
        return match.group("label") if match else None

    counts  = Counter(label for label in map(footer_label, lines) if label)
    footers = {label for label, n in counts.items() if n >= FOOTER_MIN_REPEATS}
    return [line for line in lines if footer_label(line) not in footers]


def find_headings(lines):
    """Return [(line_index, item, title)] for the body's Item headings, in order."""
    candidates = []
    for i, line in enumerate(lines):
        match = HEADING.match(line)
        if match and match.group(1).upper() in ITEM_ORDER:
            candidates.append((i, match.group(1).upper(), match.group(2).strip()))

    def body_chars(n):
        end = candidates[n + 1][0] if n + 1 < len(candidates) else len(lines)
        return sum(len(line) for line in lines[candidates[n][0] + 1:end])

    start = next((n for n, (_, item, _) in enumerate(candidates)
                  if item == "1" and body_chars(n) >= MIN_BODY_CHARS), None)
    if start is None:
        return []

    # Keep headings in strictly increasing Item order; anything else is a
    # cross-reference that happens to start a line.
    headings, last_rank = [], -1
    for i, item, title in candidates[start:]:
        rank = ITEM_ORDER.index(item)
        if rank > last_rank:
            headings.append((i, item, title))
            last_rank = rank
    return headings


def split_sections(html):
    """Return [{section, title, text}] for the Items in KEEP that were found."""
    lines    = html_to_lines(html)
    headings = find_headings(lines)
    sections = []
    for n, (i, item, title) in enumerate(headings):
        if item not in KEEP:
            continue
        end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
        sections.append({
            "section": item,
            "title":   title.rstrip(".") or lines[i + 1],
            "text":    "\n".join(lines[i + 1:end]),
        })
    return sections


def main():
    SECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    for filing in load_filings():
        sections = split_sections(cache_path(filing).read_bytes())
        out = SECTIONS_DIR / f"{filing['ticker']}_FY{filing['fiscal_year']}.json"
        out.write_text(json.dumps(sections, indent=1, ensure_ascii=False), encoding="utf-8")

        found   = [s["section"] for s in sections]
        missing = [item for item in KEEP if item not in found]
        print(f"\n{filing['ticker']}  {filing['company']}  10-K FY{filing['fiscal_year']}"
              + (f"  MISSING: {', '.join(missing)}" if missing else ""))
        for s in sections:
            preview = s["text"][:150].replace("\n", " ")
            print(f"  {s['section']:3} {len(s['text']):>9,} chars  {s['title'][:45]:45}  {preview}")


if __name__ == "__main__":
    main()

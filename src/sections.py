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

# Bold text is wrapped in markers carrying its font size, so a line that is
# entirely bold can be recognised as a heading of that size after get_text().
BOLD_START, BOLD_END = "\x02", "\x03"
BOLD_STYLE   = re.compile(r"font-weight:\s*(bold|[6-9]00)", re.IGNORECASE)
FONT_SIZE    = re.compile(r"font-size:\s*([\d.]+)pt", re.IGNORECASE)
BOLD_SEGMENT = re.compile(f"{BOLD_START}([\\d.]*){BOLD_START}(.*?){BOLD_END}")
MARKERS      = re.compile(f"{BOLD_START}[\\d.]*{BOLD_START}|{BOLD_END}")

# An Item 7A that only points elsewhere, e.g. PM: "The information called for
# by this Item is included in Item 7, Market Risk."
POINTER_MAX_CHARS = 500
POINTER = re.compile(r"included in Item\s*7\s*,\s*[\"“]?(?P<name>[^\"”.]+?)[\"”]?\s*\.?$",
                     re.IGNORECASE)

# Financial tables are written one row per line, each value labelled with its
# column headers: "Foreign currency rates | At December 31, 2025: $97 | Average: $152".
# Otherwise block tags inside cells split a label from its values, and the
# headers end up lines away from the numbers they belong to.
NUMBER   = re.compile(r"^\$?\(?\$?-?\d[\d,]*(\.\d+)?\)?%?\)?$|^[—–-]$")
YEAR     = re.compile(r"^(19|20)\d\d$")
PREFIXES = {"$", "(", "$("}
SUFFIXES = {")", "%", ")%", "%)"}

# How each section's text was obtained (stored as chunk metadata).
OWN, POINTER_RESOLVED, SHORT_UNRESOLVED = "own", "pointer_resolved", "short_unresolved"

# Item 8's primary financial statements, recognised by their headings on a
# line of their own ("Consolidated Statements of Earnings", "CONSOLIDATED
# BALANCE SHEETS"). Index entries carry a page number and do not match. A
# statement runs to the next statement heading or the notes.
INCOME, BALANCE_SHEET, CASH_FLOW = "income", "balance_sheet", "cash_flow"
STATEMENT_HEADING = re.compile(r"^consolidated (?P<name>statements? of [^|.:]+|balance sheets?)$",
                               re.IGNORECASE)
NOTES_HEADING     = re.compile(r"^notes to (the )?consolidated financial statements$", re.IGNORECASE)
STATEMENT_KINDS   = [
    (INCOME,        re.compile(r"statements? of (operations|income|earnings)", re.IGNORECASE)),
    (BALANCE_SHEET, re.compile(r"balance sheets?|statements? of financial position", re.IGNORECASE)),
    (CASH_FLOW,     re.compile(r"statements? of cash flows?", re.IGNORECASE)),
]


def is_bold(tag):
    return tag.name in ("b", "strong") or bool(BOLD_STYLE.search(tag.get("style", "")))


def font_size(tag):
    for el in [tag, *tag.parents]:
        match = FONT_SIZE.search(el.get("style", "") if el.name else "")
        if match:
            return match.group(1)
    return "0"


def colspan(cell):
    try:
        return max(1, int(cell.get("colspan", 1)))
    except ValueError:
        return 1


def table_rows(table):
    """Return each row's non-empty cells as [start_column, end_column, text]."""
    rows = []
    for tr in table.find_all("tr"):
        cells, column = [], 0
        for cell in tr.find_all(CELL_TAGS):
            span = colspan(cell)
            text = re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()
            text = re.sub(r"(?<=[$(])\s+|\s+(?=[)%])", "", text)  # "( 338 )" -> "(338)"
            if text:
                cells.append([column, column + span, text])
            column += span
        if cells:
            rows.append(merge_affixes(cells))
    return rows


def merge_affixes(cells):
    """Join "$", "(" and ")", "%" cells to the number they belong to. In a
    header row ("$  %") they stay separate cells."""
    merged = []
    for cell in cells:
        if merged and cell[2] in SUFFIXES and re.search(r"[\d)]$", merged[-1][2]):
            merged[-1][1:] = [cell[1], merged[-1][2] + cell[2]]
        elif merged and merged[-1][2] in PREFIXES and re.match(r"[\d(-]", cell[2]):
            merged[-1] = [cell[0], cell[1], merged[-1][2] + cell[2]]
        else:
            merged.append(cell)
    return merged


def render_table(rows):
    """Return the table as lines, or None if it holds no row of figures."""
    if any(HEADING.match(text) for row in rows for _, _, text in row):
        return None  # Item headings laid out in a table are left to find_headings
    lines, header, header_done, has_data = [], [], False, False
    for row in rows:
        label  = row[0][2] if row[0][0] == 0 and not NUMBER.match(row[0][2]) else ""
        values = row[1:] if label else row
        numbers = [text for _, _, text in values if NUMBER.match(text)]
        # A row whose only numbers are years ("2025 2024 2023") is a header.
        if numbers and not all(YEAR.match(n) for n in numbers):
            has_data, header_done = True, True
            lines.append(" | ".join([label] * bool(label) + [
                f"{heading}: {text}" if heading else text
                for heading, text in labelled(values, header)]))
        elif values:
            if header_done:
                header, header_done = [], False
            header.append(row)
            lines.append(" | ".join(text for _, _, text in row))
        else:
            lines.append(label)
    return lines if has_data else None


def labelled(values, header):
    """Pair each value with the header cells above it. Headers spanning every
    value in the row ("Year Ended December 31,") are left out."""
    starts = [start for start, _, _ in values]
    for start, _, text in values:
        headings = [h for row in header for a, b, h in row
                    if a <= start < b and not (len(starts) > 1 and all(a <= s < b for s in starts))]
        yield " ".join(headings), text


def parse_lines(html):
    """Return [(text, heading_size)]; heading_size is set for all-bold lines."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")

    # Inline XBRL keeps its machine-readable facts in a hidden header.
    for header in soup.find_all("ix:header"):
        header.decompose()
    for table in soup.find_all("table"):
        if table.find("table"):
            continue
        lines = render_table(table_rows(table))
        if lines is not None:
            table.replace_with("\n" + "\n".join(lines) + "\n")
    for tag in soup.find_all(is_bold):
        if not any(is_bold(parent) for parent in tag.parents if parent.name):
            tag.insert(0, f"{BOLD_START}{font_size(tag)}{BOLD_START}")
            tag.append(BOLD_END)
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    for tag in soup.find_all(CELL_TAGS):
        tag.insert_after(" ")

    parsed = []
    for raw in soup.get_text().replace("\xa0", " ").split("\n"):
        raw  = re.sub(r"\s+", " ", raw).strip()
        text = re.sub(r"\s+", " ", MARKERS.sub("", raw)).strip()
        if not text or NOISE_LINE.match(text):
            continue
        segments = BOLD_SEGMENT.findall(raw)
        all_bold = segments and not MARKERS.sub("", BOLD_SEGMENT.sub("", raw)).strip()
        size     = max(float(s or 0) for s, _ in segments) if all_bold else None
        parsed.append((text, size))

    footers = page_footer_labels([text for text, _ in parsed])
    return [(text, size) for text, size in parsed if footer_label(text) not in footers]


def html_to_lines(html):
    return [text for text, _ in parse_lines(html)]


def footer_label(line):
    match = FOOTER_LINE.match(line)
    return match.group("label") if match else None


def page_footer_labels(lines):
    counts = Counter(label for label in map(footer_label, lines) if label)
    return {label for label, n in counts.items() if n >= FOOTER_MIN_REPEATS}


def strip_page_footers(lines):
    footers = page_footer_labels(lines)
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


def resolve_pointer(text, item7_range, lines, sizes):
    """Return (subsection_name, text) of the Item 7 subsection a 7A points to, or None."""
    match = POINTER.search(" ".join(text.split()))
    if not match:
        return None
    name  = match.group("name").strip()
    start = next((i for i in item7_range
                  if lines[i].casefold() == name.casefold() and sizes[i] is not None), None)
    if start is None:
        return None
    # The subsection runs to the next heading at least as large as its own.
    end = next((i for i in item7_range
                if i > start and sizes[i] is not None and sizes[i] >= sizes[start]),
               item7_range.stop)
    body = "\n".join(lines[start + 1:end])
    return (name, body) if body else None


def split_sections(html):
    """Return [{section, title, text, content_source, resolved_from}] for Items in KEEP."""
    parsed   = parse_lines(html)
    lines    = [text for text, _ in parsed]
    sizes    = [size for _, size in parsed]
    headings = find_headings(lines)

    ranges = {}
    for n, (i, item, _) in enumerate(headings):
        end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
        ranges[item] = range(i + 1, end)

    sections = []
    for i, item, title in headings:
        if item not in KEEP:
            continue
        section = {
            "section":        item,
            "title":          title.rstrip(".") or lines[i + 1],
            "text":           "\n".join(lines[j] for j in ranges[item]),
            "content_source": OWN,
            "resolved_from":  "",
        }
        if item == "7A" and len(section["text"]) < POINTER_MAX_CHARS:
            resolved = resolve_pointer(section["text"], ranges.get("7", range(0)), lines, sizes)
            if resolved:
                name, section["text"]     = resolved
                section["content_source"] = POINTER_RESOLVED
                section["resolved_from"]  = f"Item 7, {name}"
            else:
                section["content_source"] = SHORT_UNRESOLVED
        sections.append(section)
    return sections


def statement_kind(line):
    """INCOME, BALANCE_SHEET or CASH_FLOW for a primary statement heading, "" for
    any other statement or the notes heading, None for every other line."""
    match = STATEMENT_HEADING.match(line)
    if match:
        return next((kind for kind, name in STATEMENT_KINDS
                     if name.fullmatch(match.group("name"))), "")
    return "" if NOTES_HEADING.match(line) else None


def statement_parts(section):
    """Return the section's text as [(statement, text)]. In Item 8 each primary
    statement is its own part; all other text has statement ""."""
    if section["section"] != "8":
        return [("", section["text"])]
    parts = [["", []]]
    for line in section["text"].split("\n"):
        kind = statement_kind(line)
        if kind is not None and (kind or parts[-1][0]):
            parts.append([kind, []])
        parts[-1][1].append(line)
    return [(kind, "\n".join(lines)) for kind, lines in parts if lines]


def describe_7a(section):
    if section["content_source"] == POINTER_RESOLVED:
        return f"pointer resolved to {section['resolved_from']}"
    if section["content_source"] == SHORT_UNRESOLVED:
        return "short, pointer not resolved: risk scoring also reads Item 7"
    return "own content"


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
        item_7a = next((s for s in sections if s["section"] == "7A"), None)
        if item_7a:
            print(f"  7A path: {describe_7a(item_7a)}")
        item_8 = next((s for s in sections if s["section"] == "8"), None)
        if item_8:
            statements = [f"{kind} {len(text):,} chars"
                          for kind, text in statement_parts(item_8) if kind]
            print(f"  8 statements: {', '.join(statements) or 'none found'}")


if __name__ == "__main__":
    main()

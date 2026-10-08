"""Build the labeling pack for the risk-score evaluation.

    python scripts/build_factsheets.py

Reads labels/factsheets.toml and writes one fact sheet per company to
labels/factsheets/, covering scale, FX risk and interest rate risk. Every fact
is a verbatim quote that must appear on exactly one distinct line of the parsed
filing (in its Item, and in its primary statement when one is named); its value
is read from the quote. Ratios are computed from those values and printed with
their formula.

Also creates labels/risk_labels.csv for the owner's own scores. An existing CSV
is never overwritten.
"""
import csv
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import ROOT_DIR
from fetch_filings import cache_path, filing_url, load_filings
from sections import split_sections, statement_parts

LABELS_DIR  = ROOT_DIR / "labels"
FACTS_FILE  = LABELS_DIR / "factsheets.toml"
SHEETS_DIR  = LABELS_DIR / "factsheets"
LABELS_CSV  = LABELS_DIR / "risk_labels.csv"
CSV_FIELDS  = ["company", "category", "my_score", "my_reason"]
# FX and interest rate first: those rows are required, the others optional.
CATEGORIES  = ["FX Risk", "Interest Rate Risk", "Liquidity Risk", "Revenue Risk",
               "Legal Risk", "Operational Risk"]
TOPICS      = {"scale": "Scale (income statement)", "fx": "FX risk",
               "interest_rate": "Interest rate risk"}
UNITS       = {"millions": 1, "billions": 1000}   # dollar amounts, in $ millions
STATEMENTS  = {"income": "Income statement", "balance_sheet": "Balance sheet",
               "cash_flow": "Cash flow statement"}


class FactError(ValueError):
    pass


def scope_lines(sections, fact):
    """Lines of the fact's Item, or of one primary statement within it."""
    section = next((s for s in sections if s["section"] == fact["section"]), None)
    if section is None:
        raise FactError(f"{fact['id']}: Item {fact['section']} not found")
    if fact.get("statement"):
        text = "\n".join(t for kind, t in statement_parts(section) if kind == fact["statement"])
    else:
        text = section["text"]
    return text.split("\n")


def check_quote(sections, fact):
    """The quote must appear on exactly one distinct line of its scope."""
    lines = {line for line in scope_lines(sections, fact) if fact["quote"] in line}
    if len(lines) != 1:
        where = f"Item {fact['section']}" + (f" {fact['statement']}" if fact.get("statement") else "")
        raise FactError(f"{fact['id']}: quote found on {len(lines)} distinct lines of {where}")


def fact_value(fact):
    """The fact's value in $ millions (None for facts without a dollar value)."""
    if "value" not in fact:
        return None
    if fact["value"] not in fact["quote"]:
        raise FactError(f"{fact['id']}: value {fact['value']} is not in the quote")
    if fact["unit"] not in UNITS:
        return None
    return float(fact["value"].replace(",", "")) * UNITS[fact["unit"]]


def number(value):
    return f"{value:,.0f}" if value == round(value) else f"{value:,.2f}"


def ratio_text(value):
    """0.12%, 63.5%, or 10.0× once the ratio reaches 100%."""
    if value >= 1:
        return f"{value:.1f}×"
    return f"{100 * value:.2f}%" if value < 0.01 else f"{100 * value:.1f}%"


def ratio(spec, values):
    """Return (formula, ratio) for a ratio spec; terms starting with "-" are subtracted."""
    def side(terms):
        total, parts = 0.0, []
        for term in terms:
            sign, name = (-1, term[1:]) if term.startswith("-") else (1, term)
            if values.get(name) is None:
                raise FactError(f"ratio {spec['label']!r}: no dollar value for {name}")
            total += sign * values[name]
            parts.append(("- " if sign < 0 else "+ " if parts else "") + number(values[name]))
        text = " ".join(parts)
        return total, f"({text})" if len(parts) > 1 else text
    num, num_text = side(spec["numerator"])
    den, den_text = side(spec["denominator"])
    return f"{num_text} / {den_text}", num / den


def source(fact, section_meta):
    item = f"Item {fact['section']}"
    resolved = section_meta.get(fact["section"], "")
    if resolved:
        item += f" ({resolved})"
    if fact.get("statement"):
        item += f" · {STATEMENTS[fact['statement']]}"
    return item


def render(filing, spec, sections):
    meta   = {s["section"]: s["resolved_from"] for s in sections}
    values = {}
    for fact in spec["facts"]:
        check_quote(sections, fact)
        values[fact["id"]] = fact_value(fact)

    url   = filing_url(filing)
    lines = [f"# {filing['company']} ({filing['ticker']}) · {filing['form']} FY{filing['fiscal_year']}",
             "",
             f"Labeling fact sheet. Filing: [{filing['accession']}]({url}), period ended {filing['period_end']}.",
             "Every fact is quoted verbatim from the parsed filing (checked by scripts/build_factsheets.py);",
             "ratios are computed by that script from the quoted values, in $ millions. No model scores.",
             ""]
    for topic, title in TOPICS.items():
        lines += [f"## {title}", ""]
        for fact in (f for f in spec["facts"] if f["topic"] == topic):
            lines.append(f"- **{fact['label']}**: “{fact['quote']}” ({source(fact, meta)})")
        ratios = [r for r in spec.get("ratios", []) if r["topic"] == topic]
        if ratios:
            lines += ["", "| Computed ratio | Formula ($ millions) | Value |", "|---|---|---|"]
            for r in ratios:
                formula, value = ratio(r, values)
                lines.append(f"| {r['label']} | {formula} | {ratio_text(value)} |")
        lines.append("")
    if spec.get("notes"):
        lines += ["## Notes", ""] + [f"- {note}" for note in spec["notes"]] + [""]
    return "\n".join(lines)


def write_labels_csv(path, tickers):
    """Create the owner's label file; never overwrite one that exists."""
    if path.exists():
        return False
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_FIELDS)
        for ticker in tickers:
            for category in CATEGORIES:
                writer.writerow([ticker, category, "", ""])
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    specs = tomllib.loads(FACTS_FILE.read_text(encoding="utf-8"))
    SHEETS_DIR.mkdir(parents=True, exist_ok=True)
    filings = [f for f in load_filings() if f["ticker"] in specs]
    for filing in filings:
        sections = split_sections(cache_path(filing).read_bytes())
        sheet    = render(filing, specs[filing["ticker"]], sections)
        out      = SHEETS_DIR / f"{filing['ticker']}.md"
        out.write_text(sheet, encoding="utf-8", newline="\n")
        print(f"  {out.relative_to(ROOT_DIR)}  {len(specs[filing['ticker']]['facts'])} facts")
    created = write_labels_csv(LABELS_CSV, [f["ticker"] for f in filings])
    print(f"  {LABELS_CSV.relative_to(ROOT_DIR)}  {'created' if created else 'exists, left unchanged'}")


if __name__ == "__main__":
    main()

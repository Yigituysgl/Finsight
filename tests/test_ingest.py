from ingest import chunk_filing, make_splitter
from sections import INCOME

FILING = {
    "ticker": "PM", "company": "Philip Morris International Inc.", "cik": 1413329,
    "form": "10-K", "fiscal_year": 2025, "period_end": "2025-12-31",
    "accession": "0001628280-26-005939", "primary_document": "pm-20251231.htm",
}
SECTIONS = [
    {"section": "1A", "title": "Risk Factors", "text": "Risk. " * 200,
     "content_source": "own", "resolved_from": ""},
    {"section": "7A", "title": "Market Risk", "text": "Value at risk.",
     "content_source": "pointer_resolved", "resolved_from": "Item 7, Market Risk"},
]


def test_every_chunk_carries_filing_and_section_metadata():
    texts, metadatas, ids = chunk_filing(FILING, SECTIONS, make_splitter())
    assert len(texts) == len(metadatas) == len(ids) > 2
    last = metadatas[-1]
    assert last == {
        "ticker": "PM", "company": "Philip Morris International Inc.", "cik": 1413329,
        "form": "10-K", "fiscal_year": 2025, "period_end": "2025-12-31",
        "accession": "0001628280-26-005939",
        "source_url": "https://www.sec.gov/Archives/edgar/data/1413329/"
                      "000162828026005939/pm-20251231.htm",
        "section": "7A", "section_title": "Market Risk",
        "content_source": "pointer_resolved", "resolved_from": "Item 7, Market Risk",
        "statement": "", "chunk_index": 0,
    }


def test_chunk_ids_are_stable_and_unique():
    first  = chunk_filing(FILING, SECTIONS, make_splitter())[2]
    second = chunk_filing(FILING, SECTIONS, make_splitter())[2]
    assert first == second
    assert len(set(first)) == len(first)
    assert first[0] == "0001628280-26-005939:1A:0"


def test_income_statement_chunks_are_tagged_and_kept_apart_from_other_text():
    item_8 = {"section": "8", "title": "Financial Statements", "content_source": "own",
              "resolved_from": "",
              "text": "Index to Consolidated Financial Statements\n"
                      "Consolidated Statements of Earnings\n"
                      "Net revenues | 2025: $40,648\n"
                      "Notes to Consolidated Financial Statements\n" + "Note text. " * 200}
    texts, metadatas, ids = chunk_filing(FILING, [item_8], make_splitter())
    income = [t for t, m in zip(texts, metadatas) if m["statement"] == INCOME]
    assert income == ["Consolidated Statements of Earnings\nNet revenues | 2025: $40,648"]
    assert [m["chunk_index"] for m in metadatas] == list(range(len(texts)))
    assert len(set(ids)) == len(ids)

from types import SimpleNamespace

from rag import source_label, unique_sources


def doc(section, chunk_index, resolved_from=""):
    return SimpleNamespace(page_content="text", metadata={
        "ticker": "PM", "company": "Philip Morris International Inc.", "form": "10-K",
        "fiscal_year": 2025, "section": section, "section_title": "Title",
        "resolved_from": resolved_from, "accession": "0001628280-26-005939",
        "source_url": "https://www.sec.gov/x.htm", "chunk_index": chunk_index,
    })


def test_label_names_company_filing_and_section():
    assert source_label(doc("7", 0).metadata) == \
        "Philip Morris International Inc. · 10-K FY2025 · Item 7"


def test_label_shows_where_a_resolved_pointer_led():
    assert source_label(doc("7A", 0, "Item 7, Market Risk").metadata) == \
        "Philip Morris International Inc. · 10-K FY2025 · Item 7A (Item 7, Market Risk)"


def test_sources_are_one_per_section_in_retrieval_order():
    sources = unique_sources([doc("8", 4), doc("7", 1), doc("8", 9)])
    assert [s["section"] for s in sources] == ["8", "7"]
    assert "chunk_index" not in sources[0]

from types import SimpleNamespace

from rag import retrieve_for_question, source_label, unique_sources


def doc(section, chunk_index, resolved_from=""):
    return SimpleNamespace(page_content="text", metadata={
        "ticker": "PM", "company": "Philip Morris International Inc.", "form": "10-K",
        "fiscal_year": 2025, "section": section, "section_title": "Title",
        "resolved_from": resolved_from, "accession": "0001628280-26-005939",
        "source_url": "https://www.sec.gov/x.htm", "chunk_index": chunk_index,
    })


class StubStore:
    def __init__(self, pooled, item_8):
        self.pooled, self.item_8, self.filters = pooled, item_8, []

    def similarity_search(self, query, k, filter):
        self.filters.append(filter)
        return list(self.item_8[:k] if "$and" in filter else self.pooled[:k])


def test_question_retrieval_adds_an_item_8_chunk():
    store = StubStore(pooled=[doc("7", 1), doc("7", 2), doc("1A", 3)], item_8=[doc("8", 40)])
    docs  = retrieve_for_question("net revenues?", store, "PM")
    assert [(d.metadata["section"], d.metadata["chunk_index"]) for d in docs] == \
        [("7", 1), ("7", 2), ("1A", 3), ("8", 40)]
    assert store.filters == [{"ticker": "PM"},
                             {"$and": [{"ticker": "PM"}, {"section": "8"}]}]


def test_item_8_chunk_already_retrieved_is_not_duplicated():
    store = StubStore(pooled=[doc("8", 40), doc("7", 2), doc("7", 3)], item_8=[doc("8", 40)])
    docs  = retrieve_for_question("net revenues?", store, "PM")
    assert len(docs) == 3


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

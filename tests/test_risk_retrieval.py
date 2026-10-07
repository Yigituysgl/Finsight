from types import SimpleNamespace

import rag

from risk_scorer import (RISK_CATEGORIES, describe_read_from, retrieve,
                         score_category, section_quotas)


class StubStore:
    """Returns k chunks for whatever section a search is filtered to."""
    def __init__(self, available):
        self.available = available  # {section: number of chunks in the store}
        self.calls     = []

    def similarity_search(self, query, k, filter):
        section = filter["$and"][1]["section"]
        self.calls.append((section, k))
        n = min(k, self.available.get(section, 0))
        return [SimpleNamespace(page_content=f"{section} text",
                                metadata={"accession": "A", "section": section, "chunk_index": i})
                for i in range(n)]

    def get(self, ids):
        """Chroma's get by id; a chunk exists when its index is below the section's count."""
        found = {"documents": [], "metadatas": []}
        for chunk_id in ids:
            accession, section, index = chunk_id.split(":")
            if int(index) < self.available.get(section, 0):
                found["documents"].append(f"{section} text {index}")
                found["metadatas"].append({"accession": accession, "section": section,
                                           "chunk_index": int(index)})
        return found


def test_six_categories_without_guidance_or_combined_market_risk():
    assert list(RISK_CATEGORIES) == ["Liquidity Risk", "Revenue Risk", "Legal Risk",
                                     "FX Risk", "Interest Rate Risk", "Operational Risk"]


def test_every_category_has_a_primary_and_a_supporting_quota():
    for spec in RISK_CATEGORIES.values():
        quotas = list(spec["sections"].values())
        assert len(quotas) >= 2 and quotas[0] >= 2


def test_each_section_is_searched_with_its_own_quota():
    store = StubStore({"7A": 10, "8": 500})
    docs  = retrieve(store, "KO", "fx", {"7A": 2, "8": 1})
    assert store.calls == [("7A", 2), ("8", 1)]
    assert describe_read_from(docs) == "Item 7A ×2, Item 8 ×1"


def test_resolved_or_own_7a_reads_no_item_7_for_fx():
    assert section_quotas("FX Risk", "own") == {"7A": 3, "8": 1}
    assert section_quotas("FX Risk", "pointer_resolved") == {"7A": 3, "8": 1}


def test_interest_rate_reads_item_7_as_support():
    assert section_quotas("Interest Rate Risk", "own") == {"7A": 2, "8": 1, "7": 1}


def test_unresolved_7a_pointer_falls_back_to_item_7():
    assert section_quotas("FX Risk", "short_unresolved") == {"7A": 3, "8": 1, "7": 2}
    assert section_quotas("Interest Rate Risk", "short_unresolved") == {"7A": 2, "8": 1, "7": 2}


def test_fallback_only_applies_to_categories_reading_7a():
    assert section_quotas("Revenue Risk", "short_unresolved") == {"7": 2, "1A": 1}


def test_short_section_returns_what_exists():
    store = StubStore({"3": 1, "8": 5, "1A": 5})   # Item 3 is a one-chunk pointer
    docs  = retrieve(store, "PM", "legal", section_quotas("Legal Risk", "own"))
    assert describe_read_from(docs) == "Item 3 ×1, Item 8 ×1, Item 1A ×1"


def test_category_with_no_text_is_not_scored():
    assert score_category("FX Risk", []) == (None, "No text found in the Items this category reads")


def test_neighbour_expansion_adds_adjacent_chunks_of_the_same_item(monkeypatch):
    monkeypatch.setattr(rag, "NEIGHBOURS", 1)
    store = StubStore({"7A": 3, "8": 5})
    docs  = retrieve(store, "PM", "fx", {"7A": 1, "8": 1})
    assert [(d.metadata["section"], d.metadata["chunk_index"]) for d in docs] ==         [("7A", 0), ("7A", 1), ("8", 0), ("8", 1)]

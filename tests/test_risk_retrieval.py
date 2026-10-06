from types import SimpleNamespace

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
                                metadata={"section": section}) for _ in range(n)]


def test_six_categories_without_guidance_or_combined_market_risk():
    assert list(RISK_CATEGORIES) == ["Liquidity Risk", "Revenue Risk", "Legal Risk",
                                     "FX Risk", "Interest Rate Risk", "Operational Risk"]


def test_every_category_has_a_primary_and_a_supporting_quota():
    for spec in RISK_CATEGORIES.values():
        quotas = list(spec["sections"].values())
        assert len(quotas) >= 2 and quotas[0] == 2


def test_each_section_is_searched_with_its_own_quota():
    store = StubStore({"7A": 10, "8": 500})
    docs  = retrieve(store, "KO", "fx", {"7A": 2, "8": 1})
    assert store.calls == [("7A", 2), ("8", 1)]
    assert describe_read_from(docs) == "Item 7A ×2, Item 8 ×1"


def test_resolved_or_own_7a_reads_no_item_7():
    assert section_quotas("FX Risk", "own") == {"7A": 2, "8": 1}
    assert section_quotas("FX Risk", "pointer_resolved") == {"7A": 2, "8": 1}


def test_unresolved_7a_pointer_falls_back_to_item_7():
    assert section_quotas("Interest Rate Risk", "short_unresolved") == {"7A": 2, "8": 1, "7": 2}


def test_fallback_only_applies_to_categories_reading_7a():
    assert section_quotas("Revenue Risk", "short_unresolved") == {"7": 2, "1A": 1}


def test_short_section_returns_what_exists():
    store = StubStore({"3": 1, "8": 5, "1A": 5})   # Item 3 is a one-chunk pointer
    docs  = retrieve(store, "PM", "legal", section_quotas("Legal Risk", "own"))
    assert describe_read_from(docs) == "Item 3 ×1, Item 8 ×1, Item 1A ×1"


def test_category_with_no_text_is_not_scored():
    assert score_category("FX Risk", []) == (None, "No text found in the Items this category reads")

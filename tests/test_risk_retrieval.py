from types import SimpleNamespace

import pytest

import fetch_filings
from risk_scorer import (RISK_CATEGORIES, describe_read_from, retrieve, scale_passage,
                         score_category, section_quotas)
from sections import ScaleLineError


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


class IncomeStore:
    """Returns the given chunks for the income-statement lookup."""
    def __init__(self, chunks):
        self.chunks = chunks

    def get(self, where):
        assert where == {"$and": [{"ticker": "KO"}, {"statement": "income"}]}
        return {"documents": [text for text, _ in self.chunks],
                "metadatas": [{"ticker": "KO", "section": "8", "statement": "income",
                               "chunk_index": i} for _, i in self.chunks]}


KO_FILING = {"ticker": "KO", "revenue_line": "Net Operating Revenues",
             "operating_income_line": "Operating Income",
             "net_income_line": "Net Income Attributable to Shareowners of The Coca-Cola Company"}


def test_scale_passage_joins_the_pinned_rows_across_income_statement_chunks():
    store = IncomeStore([
        ("Operating Income | 2025: 13,762 | 2024: 9,992\n"
         "Net Income Attributable to Shareowners of The Coca-Cola Company | 2025: $13,107", 3),
        ("CONSOLIDATED STATEMENTS OF INCOME\n(In millions except per share data)\n"
         "Net Operating Revenues | 2025: $47,941 | 2024: $47,061\n"
         "Operating Income | 2025: 13,762 | 2024: 9,992", 2),
    ])
    passage = scale_passage(store, KO_FILING)
    assert passage.page_content == "\n".join([
        "(In millions except per share data)",
        "Net Operating Revenues | 2025: $47,941 | 2024: $47,061",
        "Operating Income | 2025: 13,762 | 2024: 9,992",
        "Net Income Attributable to Shareowners of The Coca-Cola Company | 2025: $13,107"])
    assert passage.metadata["statement"] == "income" and passage.metadata["chunk_index"] == -1


def test_scale_passage_fails_without_income_statement_chunks():
    with pytest.raises(ScaleLineError, match="no income-statement chunks"):
        scale_passage(IncomeStore([]), KO_FILING)


def test_load_filings_requires_the_scale_line_pins(tmp_path, monkeypatch):
    config = tmp_path / "filings.toml"
    config.write_text('[[filing]]\nticker = "KO"\nform = "10-K"\nrevenue_line = "Net Operating Revenues"\n',
                      encoding="utf-8")
    monkeypatch.setattr(fetch_filings, "FILINGS_CONFIG", config)
    with pytest.raises(SystemExit, match="KO: operating_income_line, net_income_line not pinned"):
        fetch_filings.load_filings()

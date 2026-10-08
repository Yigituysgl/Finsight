"""The context each risk category reads: extra searches, the balance-sheet
passage, and the prompt rules that go with them."""
from types import SimpleNamespace

import risk_scorer
from risk_scorer import (BALANCE_SHEET_CATEGORIES, EXTRA_SEARCHES, GEOGRAPHY_QUERY,
                         balance_sheet_passage, category_docs, score_category, score_prompt)
from sections import cash_debt_lines


def chunk(section, index, text="text", statement=""):
    return SimpleNamespace(page_content=text, metadata={
        "ticker": "PM", "company": "Philip Morris International Inc.", "form": "10-K",
        "fiscal_year": 2025, "accession": "a", "section": section, "statement": statement,
        "resolved_from": "", "source_url": "https://www.sec.gov/pm.htm", "chunk_index": index})


class SearchStore:
    """Returns the chunks registered for (query, section), recording each search."""
    def __init__(self, results):
        self.results, self.searches = results, []

    def similarity_search(self, query, k, filter):
        section = filter["$and"][1]["section"]
        self.searches.append((query, section, k))
        return self.results.get((query, section), [])[:k]


def test_fx_adds_the_revenue_geography_search_in_items_7_and_8():
    assert EXTRA_SEARCHES["FX Risk"] == [(GEOGRAPHY_QUERY, {"7": 1, "8": 2})]
    fx_query = risk_scorer.RISK_CATEGORIES["FX Risk"]["query"]
    store = SearchStore({(fx_query, "7A"): [chunk("7A", 3)],
                         (fx_query, "8"): [chunk("8", 40)],
                         (GEOGRAPHY_QUERY, "7"): [chunk("7", 59)],
                         (GEOGRAPHY_QUERY, "8"): [chunk("8", 40), chunk("8", 169)]})
    docs = category_docs(store, "PM", "FX Risk", "pointer_resolved")
    assert [(d.metadata["section"], d.metadata["chunk_index"]) for d in docs] == \
        [("7A", 3), ("8", 40), ("7", 59), ("8", 169)]          # Item 8 chunk 40 once
    assert (GEOGRAPHY_QUERY, "8", 2) in store.searches


def test_other_categories_have_no_extra_search():
    store = SearchStore({})
    category_docs(store, "PM", "Legal Risk", "own")
    assert {query for query, _, _ in store.searches} == {risk_scorer.RISK_CATEGORIES["Legal Risk"]["query"]}


BALANCE_SHEET = "\n".join([
    "CONSOLIDATED BALANCE SHEETS",
    "(In millions, except number of shares)",
    "Current assets:",
    "Cash and cash equivalents | September 27, 2025: $35,934",
    "Marketable securities | September 27, 2025: 18,763",
    "Accounts receivable, net | September 27, 2025: 39,777",
    "Total current assets | September 27, 2025: 147,957",
    "Non-current assets:",
    "Marketable securities | September 27, 2025: 77,723",
    "Marketable securities | September 27, 2025: 77,723",   # chunk overlap
    "Current liabilities:",
    "Accounts payable | September 27, 2025: 69,860",
    "Commercial paper | September 27, 2025: 7,979",
    "Term debt | September 27, 2025: 12,350",
    "Non-current liabilities:",
    "Term debt | September 27, 2025: 78,328",
    "Other non-current liabilities | September 27, 2025: 41,549",
])


def test_cash_debt_lines_keep_units_headings_and_cash_and_debt_rows_once():
    assert cash_debt_lines(BALANCE_SHEET) == [
        "(In millions, except number of shares)",
        "Current assets:",
        "Cash and cash equivalents | September 27, 2025: $35,934",
        "Marketable securities | September 27, 2025: 18,763",
        "Total current assets | September 27, 2025: 147,957",
        "Non-current assets:",
        "Marketable securities | September 27, 2025: 77,723",
        "Current liabilities:",
        "Commercial paper | September 27, 2025: 7,979",
        "Term debt | September 27, 2025: 12,350",
        "Non-current liabilities:",
        "Term debt | September 27, 2025: 78,328",
    ]


def test_cash_debt_lines_read_the_other_filings_wording():
    text = "\n".join(["Short-term borrowings (Note 6) | 2025: $168",
                      "Current portion of long-term debt (Note 6) | 2025: 3,533",
                      "Long-term debt (Note 6) | 2025: 45,134",
                      "Loans and notes payable | 2025: 1,551",
                      "Debt and finance leases, net of current portion | December 31, 2025: 6,736",
                      "Long-term debt was refinanced in 2025."])          # prose, not a row
    assert len(cash_debt_lines(text)) == 5


class StatementStore:
    def __init__(self, chunks):
        self.chunks = chunks

    def get(self, where):
        assert where == {"$and": [{"ticker": "PM"}, {"statement": "balance_sheet"}]}
        return {"documents": [c.page_content for c in self.chunks],
                "metadatas": [c.metadata for c in self.chunks]}


def test_balance_sheet_passage_joins_chunks_in_order():
    store = StatementStore([chunk("8", 6, "Long-term debt (Note 6) | 2025: 45,134", "balance_sheet"),
                            chunk("8", 5, "Cash and cash equivalents | 2025: $4,872", "balance_sheet")])
    passage = balance_sheet_passage(store, "PM")
    assert passage.page_content == ("Cash and cash equivalents | 2025: $4,872\n"
                                    "Long-term debt (Note 6) | 2025: 45,134")
    assert passage.metadata["statement"] == "balance_sheet" and passage.metadata["chunk_index"] == -2


def test_balance_sheet_passage_is_none_without_cash_or_debt_rows():
    assert balance_sheet_passage(StatementStore([]), "PM") is None


def test_interest_rate_and_liquidity_read_the_balance_sheet():
    assert BALANCE_SHEET_CATEGORIES == {"Interest Rate Risk", "Liquidity Risk"}


def test_prompt_requires_exact_figures_and_names_the_balance_sheet_passage():
    prompt = " ".join(score_prompt("Interest Rate Risk", "X", with_balance_sheet=True).split())
    assert "Quote figures exactly as they appear in the passage, with the same digits and units" in prompt
    assert "no rounding and no unit conversion" in prompt
    assert "is written $47,941 million, not $47.9 billion" in prompt
    assert "passage [2] its cash, investments and debt from the balance sheet" in prompt
    assert "passage [2]" not in " ".join(score_prompt("FX Risk", "X").split())


class FakeGroq:
    prompts = []

    def __init__(self, api_key):
        self.chat = SimpleNamespace(completions=self)

    def create(self, model, messages, temperature, max_tokens):
        FakeGroq.prompts.append(messages[0]["content"])
        reply = "SCORE: 6\nREASON: Debt 45,134 [2] against cash $4,872 [2]."
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


def test_balance_sheet_passage_is_numbered_second(monkeypatch):
    monkeypatch.setattr(risk_scorer, "Groq", FakeGroq)
    scale   = chunk("8", -1, "Net revenues | 2025: $40,648", "income")
    balance = chunk("8", -2, "Cash and cash equivalents | 2025: $4,872\nLong-term debt | 2025: 45,134",
                    "balance_sheet")
    score, _, evidence = score_category("Interest Rate Risk", [chunk("7A", 2)], scale, balance)
    prompt = FakeGroq.prompts[-1]
    assert prompt.index("[1] Philip Morris") < prompt.index("[2] Philip Morris International Inc. · "
                                                            "10-K FY2025 · Item 8 · Balance sheet")
    assert score == 6 and evidence["check"]["unverified_figures"] == []
    assert [p["cited"] for p in evidence["passages"]] == [False, True, False]

import re
from types import SimpleNamespace

from rag import (check_answer, cited_numbers, numbered_context, passages, qa_prompt,
                 retrieve_for_question, source_label)


def doc(section, chunk_index, resolved_from=""):
    return SimpleNamespace(page_content="text", metadata={
        "ticker": "PM", "company": "Philip Morris International Inc.", "form": "10-K",
        "fiscal_year": 2025, "section": section, "section_title": "Title",
        "resolved_from": resolved_from, "accession": "0001628280-26-005939",
        "source_url": "https://www.sec.gov/x.htm", "chunk_index": chunk_index,
    })


class StubStore:
    def __init__(self, pooled, item_8, income=()):
        self.pooled, self.item_8, self.income, self.filters = pooled, item_8, list(income), []

    def similarity_search(self, query, k, filter):
        self.filters.append(filter)
        return list(self.item_8[:k] if "$and" in filter else self.pooled[:k])

    def get(self, where):
        assert where == {"$and": [{"ticker": "PM"}, {"statement": "income"}]}
        return {"documents": [d.page_content for d in self.income],
                "metadatas": [d.metadata for d in self.income]}


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


def test_cited_numbers_read_single_list_and_adjacent_citations():
    answer = "Revenue was $40,648 [2]. Net earnings were $11,348 [1, 3][2] and rose [4]."
    assert cited_numbers(answer) == [2, 1, 3, 4]


def test_cited_numbers_ignore_other_brackets():
    assert cited_numbers("See [Item 8] and [link](https://x) and [1a].") == []


def test_passages_mark_which_ones_the_answer_cites():
    retrieved = passages([doc("7", 1), doc("8", 0), doc("8", 1)], "Figure [2].")
    assert [(p["n"], p["cited"]) for p in retrieved] == [(1, False), (2, True), (3, False)]
    assert retrieved[1]["label"] == "Philip Morris International Inc. · 10-K FY2025 · Item 8"
    assert retrieved[1]["source_url"] == "https://www.sec.gov/x.htm"
    assert retrieved[1]["text"] == "text"


def test_check_flags_citations_to_missing_passages():
    retrieved = passages([doc("7", 1), doc("8", 0)], "")
    check     = check_answer("A [1], B [3], C [0].", retrieved)
    assert check["cited"] == [1, 3, 0]
    assert check["invalid_citations"] == [3, 0]


def test_income_statement_is_always_included_in_document_order():
    store = StubStore(pooled=[doc("7", 1)], item_8=[doc("8", 40)],
                      income=[doc("8", 1), doc("8", 0)])
    docs  = retrieve_for_question("net revenues?", store, "PM")
    assert [(d.metadata["section"], d.metadata["chunk_index"]) for d in docs] == \
        [("7", 1), ("8", 40), ("8", 0), ("8", 1)]


def test_income_statement_chunk_already_retrieved_is_not_duplicated():
    store = StubStore(pooled=[doc("8", 0)], item_8=[doc("8", 0)],
                      income=[doc("8", 0), doc("8", 1)])
    docs  = retrieve_for_question("net revenues?", store, "PM")
    assert [(d.metadata["section"], d.metadata["chunk_index"]) for d in docs] == \
        [("8", 0), ("8", 1)]


def test_context_numbers_passages_and_names_the_statement():
    income = doc("8", 0)
    income.metadata["statement"] = "income"
    income.page_content = "Net revenues | 2025: $40,648"
    context = numbered_context([doc("7", 1), income])
    assert context == (
        "[1] Philip Morris International Inc. · 10-K FY2025 · Item 7\ntext\n\n"
        "[2] Philip Morris International Inc. · 10-K FY2025 · Item 8 · Income statement\n"
        "Net revenues | 2025: $40,648")


def test_prompt_asks_for_passage_citations():
    prompt = prompt_text()
    assert "cite the passage it comes from in square brackets, e.g. [2] or [1, 3]" in prompt
    assert "Cite only passage numbers that appear in the context" in prompt


def prompt_text():
    return re.sub(r"\s+", " ", qa_prompt("CONTEXT TEXT", "How did net income change?"))


def test_prompt_asks_for_net_income_attributable_to_the_company():
    prompt = prompt_text()
    assert 'containing "attributable to" the company or its common stockholders or shareowners' in prompt
    for line in ['"Net income attributable to common stockholders"',
                 '"Net Income Attributable to Shareowners of The Coca-Cola Company"',
                 '"Net earnings attributable to PMI"']:
        assert line in prompt
    assert "includes noncontrolling interests and may only be mentioned as a clearly labelled secondary figure" in prompt


def test_prompt_keeps_figure_rules_and_fills_in_context_and_question():
    prompt = prompt_text()
    assert "Never derive a figure" in prompt
    assert "label each figure with its fiscal year" in prompt
    assert "CONTEXT: CONTEXT TEXT QUESTION: How did net income change?" in prompt

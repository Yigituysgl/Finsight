"""Helpers behind the risk view: levels, card lines, citation display,
rate-limit messages, cache."""
import httpx
from groq import RateLimitError

from rag import display_citations, rate_limit_message
from risk_cache import cache_path, load_results, save_results
from risk_scorer import short_reason
from rubric import risk_level


def test_risk_level_uses_the_rubric_bands_for_scores_and_overall():
    assert [risk_level(s) for s in (1, 3, 4, 6, 7, 10)] == \
        ["Low", "Low", "Medium", "Medium", "High", "High"]
    assert [risk_level(o / 10) for o in (39, 40, 69, 70)] == ["Low", "Medium", "Medium", "High"]
    assert risk_level(None) is None


def test_short_reason_is_the_first_sentence_without_citations():
    reason = ("Gross exposure: 60.1% of revenue is earned outside the U.S. [2][1]. "
              "Hedging: notional $21,128 million [3].")
    assert short_reason(reason) == "Gross exposure: 60.1% of revenue is earned outside the U.S."


def test_short_reason_drops_emptied_parentheses_and_stops_at_a_semicolon():
    reason = ("Cash of $4,872 million covers ≈19% of current liabilities (passages [2] and [3]); "
              "the company relies on refinancing [4].")
    assert short_reason(reason) == "Cash of $4,872 million covers ≈19% of current liabilities"


def test_short_reason_keeps_decimals_and_cuts_long_sentences():
    reason = "Debt of $4.37 billion " + " ".join(["word"] * 30) + " end."
    line = short_reason(reason, max_words=8)
    assert line == "Debt of $4.37 billion word word word word…"


def test_short_reason_skips_a_first_sentence_that_only_restates_the_scale():
    reason = ("The company reports $40,648 million in net revenues, $14,892 million operating "
              "income and $11,348 million net earnings (2025) [1]; it discloses a range of "
              "investigations [3].")
    assert short_reason(reason) == "It discloses a range of investigations"


def test_short_reason_keeps_a_scale_sentence_that_says_something():
    reason = ("Tesla’s total revenue fell from $97,690 million in 2024 to $94,827 million in "
              "2025 (≈ ‑3%) [1]. Automotive sales declined 9% [2].")
    assert short_reason(reason, max_words=6) == "Tesla’s total revenue fell from $97,690…"


def test_short_reason_falls_back_to_the_first_sentence_if_all_restate_the_scale():
    assert short_reason("Net income was $11,348 million [1].") == "Net income was $11,348 million"


def test_display_citations_shows_full_width_citations_as_brackets():
    text = "Revenue $40,648 million 【4】, net income 【1†L1-L3】 and [2][3], 【1, 5】."
    assert display_citations(text) == "Revenue $40,648 million [4], net income [1] and [2][3], [1, 5]."


def rate_limit(message):
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))
    return RateLimitError(message, response=response, body=None)


def test_rate_limit_message_explains_the_daily_limit_and_when_to_retry():
    message = rate_limit_message(rate_limit(
        "Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 199833. "
        "Please try again in 15m9.791999999s. Need more tokens?"))
    assert message == ("The daily token limit of the free Groq tier has been reached, so no new "
                       "model calls can be made for now. Try again in about 15m9s.")


def test_rate_limit_message_for_the_per_minute_limit():
    message = rate_limit_message(rate_limit("Rate limit reached ... tokens per minute (TPM)"))
    assert message == "The Groq API is busy: its per-minute rate limit was reached."


FILING = {"ticker": "PM", "accession": "0001628280-26-005939"}


def test_cache_round_trip_keeps_scores_as_tuples(tmp_path):
    results = {"overall": 48, "summary": None,
               "scores_dict": {"FX Risk": (6, "Gross exposure: ..."), "Legal Risk": (None, "n/a")},
               "read_from": {"FX Risk": "Item 7A ×3"},
               "evidence": {"FX Risk": {"passages": [], "check": None}}}
    path = save_results(FILING, results, source="Evaluation run 2", created="2026-10-08 14:03",
                        cache_dir=tmp_path)
    assert path == cache_path(FILING, tmp_path) == tmp_path / "risk_PM_0001628280-26-005939.json"
    loaded = load_results(FILING, cache_dir=tmp_path)
    assert loaded["scores_dict"] == results["scores_dict"]
    assert (loaded["source"], loaded["created"], loaded["overall"]) == \
        ("Evaluation run 2", "2026-10-08 14:03", 48)


def test_no_cache_means_no_results(tmp_path):
    assert load_results(FILING, cache_dir=tmp_path) is None

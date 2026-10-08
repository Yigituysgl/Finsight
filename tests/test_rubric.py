import rubric
from risk_scorer import RISK_CATEGORIES


def test_every_category_has_bands_covering_1_to_10():
    assert set(rubric.BANDS) == set(RISK_CATEGORIES)
    for bands in rubric.BANDS.values():
        assert [(low, high) for low, high, _ in bands] == [(1, 3), (4, 6), (7, 10)]


def test_agreed_settings():
    assert rubric.MIN_SCORED_CATEGORIES == 4
    assert rubric.BOILERPLATE_MAX_SCORE == 5
    assert rubric.FX_HEDGING_MAX_REDUCTION == 2


def test_fx_rubric_text_carries_its_thresholds_and_hedging_rule():
    text = rubric.rubric_text("FX Risk")
    assert "1-3: under ~20% of revenue from outside the home market, or FX impact under ~1% of revenue" in text
    assert "4-6: ~20-50% of revenue" in text and "FX impact ~1-3% of revenue" in text
    assert "7-10: majority of revenue" in text and "over ~3% of revenue or operating income" in text
    assert "hedging lowers that score by at most 2 points" in text
    assert "states the gross exposure and the hedging separately" in text


def test_interest_rate_rubric_text_carries_its_thresholds():
    text = rubric.rubric_text("Interest Rate Risk")
    assert "under ~1% of net income" in text
    assert "~1-5% of net income" in text
    assert "over ~5% of net income, or large near-term maturities" in text
    assert "investment portfolios weigh less than effects on interest expense" in text


def test_thresholds_live_in_one_place():
    # The text is built from the constants at import time; the constants are
    # the only place the numbers appear.
    source = open(rubric.__file__, encoding="utf-8").read()
    for number in ["~20%", "~50%", "~30%", "~5%"]:
        assert number not in source


def test_general_rule_limits_boilerplate_and_insufficient():
    assert "next 1-2 years, relative to the company's scale" in rubric.GENERAL
    assert "INSUFFICIENT only if the passages contain no relevant discussion" in rubric.GENERAL
    assert "supports a score of at most 5" in rubric.GENERAL

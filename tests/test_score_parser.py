import pytest

from risk_scorer import parse_score_response


@pytest.mark.parametrize("raw, expected", [
    ("SCORE: 2  \nREASON: Strong cash flow.", 2),   # observed gpt-oss-120b output
    ("**SCORE:** 7\n**REASON:** High litigation.", 7),
    ("SCORE: [4]\nREASON: x", 4),
    ("SCORE: 7/10\nREASON: x", 7),
    ("SCORE: 6.\nREASON: x", 6),
    ("score: 3\nreason: x", 3),
    ("SCORE: 1\nREASON: x", 1),
    ("SCORE: 10\nREASON: x", 10),
])
def test_parses_valid_scores(raw, expected):
    assert parse_score_response(raw)[0] == expected


@pytest.mark.parametrize("raw", [
    "SCORE: 7.5\nREASON: x",           # decimals are rejected, not truncated
    "SCORE: 0\nREASON: x",             # the scale is 1-10
    "SCORE: 11\nREASON: x",            # out of range
    "SCORE: high\nREASON: x",
    "",                                # empty model response
    "Overall the SCORE: 5 seems fair",  # not at the start of a line
])
def test_unparsable_scores_are_none(raw):
    score, reason = parse_score_response(raw)
    assert score is None
    assert reason == "Could not parse model response"


@pytest.mark.parametrize("raw", [
    "SCORE: INSUFFICIENT\nREASON: The text covers only foreign currency risk.",
    "**SCORE:** INSUFFICIENT\n**REASON:** The text covers only foreign currency risk.",
    "score: [insufficient]\nreason: The text covers only foreign currency risk.",
])
def test_insufficient_is_none_with_its_reason(raw):
    assert parse_score_response(raw) == \
        (None, "Insufficient information: The text covers only foreign currency risk.")


def test_insufficient_without_reason():
    assert parse_score_response("SCORE: INSUFFICIENT") == \
        (None, "Insufficient information: No reason given")


def test_reason_is_extracted():
    assert parse_score_response("SCORE: 2\nREASON: Ample liquidity.") == (2, "Ample liquidity.")


def test_missing_reason_keeps_score():
    assert parse_score_response("SCORE: 3") == (3, "No reason given")

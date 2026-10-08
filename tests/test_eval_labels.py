import sys
from pathlib import Path

import httpx
import pytest
from groq import RateLimitError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import eval_retrieval
from eval_retrieval import (DailyQuotaExhausted, compare_with_labels, load_labels,
                            with_rate_limit_retries)


def test_labels_skip_blank_rows_and_keep_file_order(tmp_path):
    path = tmp_path / "risk_labels.csv"
    path.write_text("company,category,my_score,my_reason\n"
                    "KO,FX Risk,7,gross 8 minus 1\n"
                    "KO,Liquidity Risk,,\n"
                    "PM,FX Risk,8,\"gross 9, hedging -1\"\n", encoding="utf-8")
    assert load_labels(path) == {("KO", "FX Risk"): {"score": 7, "reason": "gross 8 minus 1"},
                                 ("PM", "FX Risk"): {"score": 8, "reason": "gross 9, hedging -1"}}


def test_comparison_reports_gap_agreement_and_unscored_rows():
    labels = {("KO", "FX Risk"): {"score": 7}, ("KO", "Interest Rate Risk"): {"score": 4},
              ("PM", "FX Risk"): {"score": 8}, ("PM", "Interest Rate Risk"): {"score": 6}}
    scores = {"KO": {"FX Risk": {"score": 5}, "Interest Rate Risk": {"score": 5}},
              "PM": {"FX Risk": {"score": None}}}
    rows = compare_with_labels(scores, labels)
    assert [(r["model"], r["gap"], r["within_1"], r["status"]) for r in rows] == [
        (5, -2, False, "scored"), (5, 1, True, "scored"),
        (None, None, False, "n/a"), (None, None, False, "not run")]


def rate_limit(message, retry_after=None):
    headers  = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(429, headers=headers,
                              request=httpx.Request("POST", "https://api.groq.com"))
    return RateLimitError(message, response=response, body=None)


def test_per_minute_limit_is_waited_out(monkeypatch):
    waits = []
    monkeypatch.setattr(eval_retrieval.time, "sleep", waits.append)
    calls = iter([rate_limit("Rate limit reached ... tokens per minute (TPM)", "7"), "scored"])

    def call():
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    assert with_rate_limit_retries(call) == "scored"
    assert waits == [7.0]


def test_daily_limit_stops_the_run(monkeypatch):
    monkeypatch.setattr(eval_retrieval.time, "sleep", lambda s: pytest.fail("should not wait"))

    def call():
        raise rate_limit("Rate limit reached ... tokens per day (TPD): Limit 200000")
    with pytest.raises(DailyQuotaExhausted, match="tokens per day"):
        with_rate_limit_retries(call)

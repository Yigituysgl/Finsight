import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_factsheets import (FactError, check_quote, fact_value, ratio, ratio_text,
                              write_labels_csv)

SECTIONS = [
    {"section": "7A", "resolved_from": "", "text": "VaR was $590 million.\nOther text."},
    {"section": "8", "resolved_from": "", "text": "\n".join([
        "Consolidated Statements of Operations",
        "Total net sales | 2025: 416,161",
        "Consolidated Balance Sheets",
        "Long-term debt | 2025: 42,119",
        "Notes to Consolidated Financial Statements",
        "Long-term debt | 2025: 850",
        "Long-term debt | 2025: 850",
    ])},
]


def fact(**fields):
    return {"id": "x", "section": "8", **fields}


def test_quote_on_one_line_of_its_statement_passes():
    check_quote(SECTIONS, fact(statement="balance_sheet", quote="Long-term debt | 2025: 42,119"))


def test_quote_outside_its_statement_fails():
    with pytest.raises(FactError, match="0 distinct lines"):
        check_quote(SECTIONS, fact(statement="income", quote="Long-term debt | 2025: 42,119"))


def test_quote_on_several_different_lines_fails():
    with pytest.raises(FactError, match="2 distinct lines"):
        check_quote(SECTIONS, fact(quote="Long-term debt | 2025:"))


def test_repeated_identical_line_counts_once():
    check_quote(SECTIONS, fact(quote="Long-term debt | 2025: 850"))


def test_values_are_read_from_the_quote_in_millions():
    assert fact_value(fact(quote="was $91.3 billion", value="91.3", unit="billions")) == 91_300
    assert fact_value(fact(quote="Total | 2025: 4,354", value="4,354", unit="millions")) == 4_354
    assert fact_value(fact(quote="by 2%", value="2", unit="percent")) is None
    with pytest.raises(FactError, match="not in the quote"):
        fact_value(fact(quote="was $91.3 billion", value="91.4", unit="billions"))


def test_ratio_shows_its_formula_and_subtracts_minus_terms():
    values = {"revenue": 40_648.0, "americas": 4_854.0}
    formula, value = ratio({"label": "r", "numerator": ["revenue", "-americas"],
                            "denominator": ["revenue"]}, values)
    assert formula == "(40,648 - 4,854) / 40,648"
    assert ratio_text(value) == "88.1%"


def test_ratio_needs_dollar_values():
    with pytest.raises(FactError, match="no dollar value for share"):
        ratio({"label": "r", "numerator": ["share"], "denominator": ["revenue"]},
              {"share": None, "revenue": 1.0})


def test_ratio_text_formats():
    assert ratio_text(129 / 112_010) == "0.12%"
    assert ratio_text(0.635) == "63.5%"
    assert ratio_text(10.016) == "10.0×"


def test_labels_csv_is_created_once_and_never_overwritten(tmp_path):
    path = tmp_path / "risk_labels.csv"
    assert write_labels_csv(path, ["KO"])
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [r["category"] for r in rows][:2] == ["FX Risk", "Interest Rate Risk"]
    assert len(rows) == 6 and rows[0] == {"company": "KO", "category": "FX Risk",
                                          "my_score": "", "my_reason": ""}
    path.write_text("company,category,my_score,my_reason\nKO,FX Risk,6,mine\n", encoding="utf-8")
    assert not write_labels_csv(path, ["KO"])
    assert "KO,FX Risk,6,mine" in path.read_text(encoding="utf-8")

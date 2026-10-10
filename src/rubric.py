"""Scoring rubric for the six risk categories: the single place for its thresholds.

The scoring prompt is built from these texts, so a threshold changed here is
what the model is told. Scores run 1-10: 1-3 low, 4-6 medium, 7-10 high.
Percentages are approximate ("~"), as in the rubric agreed for Phase 5.
"""

# The overall score is shown only when at least this many of the six
# categories could be scored.
MIN_SCORED_CATEGORIES = 4

# Generic risk-factor language, without company-specific facts or figures,
# supports at most this score in any category.
BOILERPLATE_MAX_SCORE = 5

# FX: gross exposure is scored first; hedging lowers it by at most this much.
FX_HEDGING_MAX_REDUCTION = 2

# Thresholds, in percent.
FX_FOREIGN_REVENUE = (20, 50)     # share of revenue from outside the home market
FX_IMPACT          = (1, 3)       # FX impact, % of revenue (or operating income at the top)
RATE_IMPACT        = (1, 5)       # +100bp impact, % of net income
REVENUE_CONCENTRATION = (30, 50)  # largest product / customer / region, % of revenue
REVENUE_DECLINE    = 5            # latest-year revenue decline, %
LEGAL_LOSS         = 5            # accruals / reasonably possible losses, % of net income
OPERATIONAL_IMPACT = 3            # quantified disruption, % of operating income

GENERAL = (
    "Score the risk to earnings and cash flow over the next 1-2 years, relative to the "
    "company's scale (its revenue, operating income and net income are given). Answer "
    "INSUFFICIENT only if the passages contain no relevant discussion of this risk at all. "
    "Generic risk-factor language without company-specific facts or figures supports a "
    f"score of at most {BOILERPLATE_MAX_SCORE}.")

lo, hi = FX_FOREIGN_REVENUE
fx_lo, fx_hi = FX_IMPACT
rate_lo, rate_hi = RATE_IMPACT
conc_lo, conc_hi = REVENUE_CONCENTRATION

# category -> [(low score, high score, description)], plus an optional note.
BANDS = {
    "FX Risk": [
        (1, 3,  f"under ~{lo}% of revenue from outside the home market, or FX impact under "
                f"~{fx_lo}% of revenue"),
        (4, 6,  f"~{lo}-{hi}% of revenue from outside the home market with hedging, FX impact "
                f"~{fx_lo}-{fx_hi}% of revenue"),
        (7, 10, f"majority of revenue from outside the home market, FX impact over ~{fx_hi}% of "
                "revenue or operating income, emerging-market exposure, or translation largely "
                "unhedged"),
    ],
    "Interest Rate Risk": [
        (1, 3,  f"low net debt or mostly fixed-rate debt; a +100bp rate rise affects under "
                f"~{rate_lo}% of net income"),
        (4, 6,  f"moderate leverage with some floating-rate debt; +100bp affects ~{rate_lo}-"
                f"{rate_hi}% of net income"),
        (7, 10, f"high leverage or mostly floating-rate debt, +100bp affects over ~{rate_hi}% of "
                "net income, or large near-term maturities"),
    ],
    "Liquidity Risk": [
        (1, 3,  "cash plus operating cash flow comfortably cover near-term obligations"),
        (4, 6,  "cash plus operating cash flow cover near-term obligations adequately"),
        (7, 10, "coverage is tight, or the company relies on refinancing"),
    ],
    "Revenue Risk": [
        (1, 3,  f"diversified (no product, customer or region above ~{conc_lo}% of revenue), "
                "revenue stable or growing over the years shown, only generic demand risks "
                "disclosed"),
        (4, 6,  f"meaningful concentration (one product, segment or region ~{conc_lo}-{conc_hi}% "
                f"of revenue), cyclical demand, or a latest-year decline of up to ~{REVENUE_DECLINE}%"),
        (7, 10, "majority of revenue from one product, customer or market, a latest-year decline "
                f"over ~{REVENUE_DECLINE}%, or a specific disclosed threat material to revenue "
                "(loss of a key customer, a regulatory ban, a price war)"),
    ],
    "Legal Risk": [
        (1, 3,  "routine litigation only, no material accruals or reasonably possible loss "
                "estimates"),
        (4, 6,  "specific pending matters or regulatory investigations, with accruals or "
                f"reasonably possible losses under ~{LEGAL_LOSS}% of net income"),
        (7, 10, f"accruals or reasonably possible losses over ~{LEGAL_LOSS}% of net income, "
                "matters threatening a core product or the business model (bans, antitrust "
                "remedies), or a pattern of large settlements"),
    ],
    "Operational Risk": [
        (1, 3,  "diversified suppliers and production, no disruptions disclosed for the period"),
        (4, 6,  "notable concentration (single-source suppliers, few manufacturing locations) "
                "or disclosed cost pressure without a quantified material impact"),
        (7, 10, f"disclosed disruptions with a quantified impact over ~{OPERATIONAL_IMPACT}% of "
                "operating income, critical single-source or geopolitically exposed supply, or a "
                "major restructuring"),
    ],
}

NOTES = {
    "FX Risk": ("Score the gross exposure first; hedging lowers that score by at most "
                f"{FX_HEDGING_MAX_REDUCTION} points. The reason states the gross exposure and "
                "the hedging separately."),
    "Interest Rate Risk": ("Changes in the valuation of investment portfolios weigh less than "
                           "effects on interest expense."),
}


def risk_level(score):
    """"Low", "Medium" or "High" for a 1-10 score (1-3, 4-6, 7-10), or for an
    overall 0-100 score divided by 10 (under 40, 40-69, 70 and above); None
    for an unscored category."""
    if score is None:
        return None
    return "Low" if score < 4 else "Medium" if score < 7 else "High"


def rubric_text(category):
    """The category's bands, one per line, followed by its note if it has one."""
    lines = [f"{low}-{high}: {text}" for low, high, text in BANDS[category]]
    if category in NOTES:
        lines.append(NOTES[category])
    return "\n".join(lines)

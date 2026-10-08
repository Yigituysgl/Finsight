# Apple Inc. (AAPL) · 10-K FY2025

Labeling fact sheet. Filing: [0000320193-25-000079](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm), period ended 2025-09-27.
Every fact is quoted verbatim from the parsed filing (checked by scripts/build_factsheets.py);
ratios are computed by that script from the quoted values, in $ millions. No model scores.

## Scale (income statement)

- **Total net sales**: “Total net sales | September 27, 2025: 416,161 | September 28, 2024: 391,035 | September 30, 2023: 383,285” (Item 8 · Income statement)
- **Operating income**: “Operating income | September 27, 2025: 133,050 | September 28, 2024: 123,216 | September 30, 2023: 114,301” (Item 8 · Income statement)
- **Net income**: “Net income | September 27, 2025: $112,010 | September 28, 2024: $93,736 | September 30, 2023: $96,995” (Item 8 · Income statement)

## FX risk

- **Net sales, U.S.**: “U.S. | 2025: $151,790 | 2024: $142,196 | 2023: $138,573” (Item 8)
- **Net sales, China**: “China (1) | 2025: 64,377 | 2024: 66,952 | 2023: 72,559” (Item 8)
- **Net sales, other countries**: “Other countries | 2025: 199,994 | 2024: 181,887 | 2023: 172,153” (Item 8)
- **VaR of foreign currency derivative positions (95%, one day)**: “the Company estimates, with 95% confidence, a maximum one-day loss in fair value of $590 million and $538 million as of September 27, 2025 and September 28, 2024, respectively” (Item 7A)
- **VaR scope**: “Changes in the Company’s underlying foreign currency exposures, which were excluded from the assessment, generally offset changes in the fair values of the Company’s foreign currency derivatives.” (Item 7A)
- **Hedging policy**: “However, the Company may choose to not hedge certain foreign currency exposures for a variety of reasons, including accounting considerations or prohibitive cost.” (Item 7A)
- **FX impact on 2025 net sales**: “The weakness in foreign currencies relative to the U.S. dollar had an unfavorable year-over-year impact on Americas net sales during 2025.” (Item 7)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| Net sales outside the U.S. / total net sales | (64,377 + 199,994) / 416,161 | 63.5% |

## Interest rate risk

- **+100bp: investment portfolio**: “Investment portfolio | Hypothetical Interest Rate Increase: 100 basis points, all tenors | Potential Impact: Decline in fair value | 2025: $2,416 | 2024: $2,755” (Item 7A)
- **+100bp: term debt**: “Term debt | Hypothetical Interest Rate Increase: 100 basis points, all tenors | Potential Impact: Increase in annual interest expense | 2025: $129 | 2024: $139” (Item 7A)
- **Fixed-rate notes outstanding**: “the Company had outstanding fixed-rate notes with varying maturities for an aggregate principal amount of $91.3 billion (collectively the “Notes”), with $12.4 billion payable within 12 months” (Item 7)
- **Notes payable within 12 months**: “with $12.4 billion payable within 12 months. Future interest payments” (Item 7)
- **Commercial paper outstanding**: “As of September 27, 2025, the Company had $8.0 billion of commercial paper outstanding, which was payable within 12 months.” (Item 7)
- **Term debt in fair value hedges**: “the carrying amount of the Company’s current and non-current term debt subject to fair value hedges was $12.6 billion and $13.5 billion, respectively” (Item 8)
- **Cash, cash equivalents and marketable securities**: “which totaled $132.4 billion as of September 27, 2025” (Item 7)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| +100bp interest expense on term debt / net income | 129 / 112,010 | 0.12% |
| +100bp portfolio fair value decline / net income | 2,416 / 112,010 | 2.2% |
| Term debt in fair value hedges (carrying) / notes principal | 12,600 / 91,300 | 13.8% |
| (Notes + commercial paper) / cash and marketable securities | (91,300 + 8,000) / 132,400 | 75.0% |
| (Notes due within 12 months + commercial paper) / cash and marketable securities | (12,400 + 8,000) / 132,400 | 15.4% |

## Notes

- The Item 8 term-debt table is misaligned by the parser (e.g. "2025 Effective Interest Rate: $86,781"), so debt figures are quoted from Item 7 instead.

# Tesla, Inc. (TSLA) · 10-K FY2025

Labeling fact sheet. Filing: [0001628280-26-003952](https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/tsla-20251231.htm), period ended 2025-12-31.
Every fact is quoted verbatim from the parsed filing (checked by scripts/build_factsheets.py);
ratios are computed by that script from the quoted values, in $ millions. No model scores.

## Scale (income statement)

- **Total revenues**: “Total revenues | 2025: 94,827 | 2024: 97,690 | 2023: 96,773” (Item 8 · Income statement)
- **Income from operations**: “Income from operations | 2025: 4,355 | 2024: 7,076 | 2023: 8,891” (Item 8 · Income statement)
- **Net income attributable to common stockholders**: “Net income attributable to common stockholders | 2025: $3,794 | 2024: $7,091 | 2023: $14,997” (Item 8 · Income statement)

## FX risk

- **Revenues, United States**: “United States | 2025: $47,627 | 2024: $47,725 | 2023: $45,235” (Item 8)
- **Revenues, China**: “China | 2025: 20,962 | 2024: 20,944 | 2023: 21,745” (Item 8)
- **Revenues, other international**: “Other international | 2025: 26,238 | 2024: 29,021 | 2023: 29,793” (Item 8)
- **Hedging policy**: “Accordingly, changes in exchange rates affect our operating results as expressed in U.S. dollars as we do not typically hedge foreign currency risk.” (Item 7A)
- **10% adverse FX move on non-local-currency monetary items (pre-tax, unhedged)**: “These changes would have resulted in a gain or loss of $1.70 billion at December 31, 2025 and $1.15 billion at December 31, 2024, assuming no foreign currency hedging.” (Item 7A)
- **Cash held in foreign currencies**: “Balances held in foreign currencies had a U.S. dollar equivalent of $4.37 billion and consisted primarily of Chinese yuan and euro.” (Item 7)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| Revenues outside the U.S. / total revenues | (20,962 + 26,238) / 94,827 | 49.8% |
| 10% FX sensitivity / total revenues | 1,700 / 94,827 | 1.8% |
| 10% FX sensitivity / income from operations | 1,700 / 4,355 | 39.0% |

## Interest rate risk

- **Total debt (unpaid principal)**: “Total debt | Net Carrying Value Current: 1,569 | Net Carrying Value Long-Term: 6,584 | Unpaid Principal Balance: $8,177 | Unused Committed Amount (1): $6,429” (Item 8)
- **Debt principal maturing in 2026**: “2026 | Recourse debt: $1 | Non-recourse debt: $1,575 | Total: $1,576” (Item 8)
- **China Working Capital Facility**: “China Working Capital Facility | Net Carrying Value Current: — | Net Carrying Value Long-Term: 4,288 | Unpaid Principal Balance: 4,288 | Unused Committed Amount (1): 1,429 | Contractual Interest Rates: 2.01 - 2.11% | Contractual Maturity Date: March 2026 - December 2026 (2)” (Item 8)
- **Cash and cash equivalents**: “As of December 31, 2025, we had $16.51 billion and $27.55 billion of cash and cash equivalents and short-term investments, respectively.” (Item 7)
- **Short-term investments**: “$27.55 billion of cash and cash equivalents and short-term investments, respectively” (Item 7)
- **Interest expense**: “Interest expense | 2025: (338) | 2024: (350) | 2023: (156)” (Item 8 · Income statement)
- **Interest income**: “Interest income | 2025: 1,680 | 2024: 1,569 | 2023: 1,066” (Item 8 · Income statement)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| Total debt / (cash + short-term investments) | 8,177 / (16,510 + 27,550) | 18.6% |
| Interest expense / income from operations | 338 / 4,355 | 7.8% |
| 2026 maturities / (cash + short-term investments) | 1,576 / (16,510 + 27,550) | 3.6% |

## Notes

- Item 7A of this filing discusses foreign currency risk only; it gives no interest rate sensitivity.

# The Coca-Cola Company (KO) · 10-K FY2025

Labeling fact sheet. Filing: [0001628280-26-010047](https://www.sec.gov/Archives/edgar/data/21344/000162828026010047/ko-20251231.htm), period ended 2025-12-31.
Every fact is quoted verbatim from the parsed filing (checked by scripts/build_factsheets.py);
ratios are computed by that script from the quoted values, in $ millions. No model scores.

## Scale (income statement)

- **Net Operating Revenues**: “Net Operating Revenues | 2025: $47,941 | 2024: $47,061 | 2023: $45,754” (Item 8 · Income statement)
- **Operating Income**: “Operating Income | 2025: 13,762 | 2024: 9,992 | 2023: 11,311” (Item 8 · Income statement)
- **Net Income Attributable to Shareowners of The Coca-Cola Company**: “Net Income Attributable to Shareowners of The Coca-Cola Company | 2025: $13,107 | 2024: $10,631 | 2023: $10,714” (Item 8 · Income statement)

## FX risk

- **Net operating revenues outside the U.S.**: “In 2025, we generated $28.8 billion of our net operating revenues from operations outside the United States.” (Item 7A)
- **FX impact on 2025 net operating revenues (after hedging)**: “Fluctuations in foreign currency exchange rates, including the effects of our hedging activities, unfavorably impacted our consolidated net operating revenues by 2%.” (Item 7)
- **FX impact on 2025 operating income (after hedging)**: “In 2025, fluctuations in foreign currency exchange rates, including the effects of our hedging activities, unfavorably impacted consolidated operating income by 12% due to a stronger U.S. dollar compared to certain foreign currencies, including the Mexican peso, Argentine peso, Brazilian real and Turkish lira” (Item 7)
- **2026 outlook**: “Based on current spot rates and our hedging coverage in place, we expect foreign currency exchange rate fluctuations will have a favorable impact on our full year 2026 net operating revenues.” (Item 7)
- **Notional of foreign currency derivatives**: “The total notional values of our foreign currency derivatives were $21,128 million and $18,442 million as of December 31, 2025 and 2024, respectively.” (Item 7A)
- **10% USD weakening: derivatives in hedge accounting**: “we estimate that a 10% weakening of the U.S. dollar would have resulted in a $609 million decrease in fair value” (Item 7A)
- **10% USD weakening: economic hedges**: “we estimate that a 10% weakening of the U.S. dollar would have resulted in a $123 million decrease in fair value” (Item 7A)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| Revenues outside the U.S. / net operating revenues | 28,800 / 47,941 | 60.1% |
| FX derivative notional / revenues outside the U.S. (not a hedge ratio) | 21,128 / 28,800 | 73.4% |

## Interest rate risk

- **+1pp: interest expense**: “we estimate that a 1 percentage point increase in interest rates would have increased interest expense by $120 million in 2025” (Item 7A)
- **+1pp: debt securities portfolio**: “We estimate that a 1 percentage point increase in interest rates would have resulted in a $39 million decrease in the fair value of our portfolio of highly liquid debt securities.” (Item 7A)
- **Loans and notes payable**: “Loans and notes payable | 2025: 1,551 | 2024: 1,499” (Item 8 · Balance sheet)
- **Current maturities of long-term debt**: “Current maturities of long-term debt | 2025: 1,822 | 2024: 648” (Item 8 · Balance sheet)
- **Long-term debt**: “Long-term debt | 2025: 42,119 | 2024: 42,375” (Item 8 · Balance sheet)
- **Long-term debt in fair value hedges (carrying value)**: “Long-term debt | Carrying Values of Hedged Items December 31, 2025: 11,648” (Item 8)
- **Cash, short-term investments and marketable securities**: “The Company’s cash, cash equivalents, short-term investments and marketable securities totaled $15.8 billion as of December 31, 2025.” (Item 7)
- **Interest expense**: “Interest expense | 2025: 1,654 | 2024: 1,656 | 2023: 1,527” (Item 8 · Income statement)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| +1pp interest expense / net income | 120 / 13,107 | 0.92% |
| Debt (loans and notes + current and long-term debt) / cash and investments | (1,551 + 1,822 + 42,119) / 15,800 | 2.9× |
| Long-term debt in fair value hedges / long-term debt | 11,648 / 42,119 | 27.7% |
| Interest expense / operating income | 1,654 / 13,762 | 12.0% |
| (Loans and notes payable + current maturities) / cash and investments | (1,551 + 1,822) / 15,800 | 21.3% |

## Notes

- Item 8 also contains other tables with lines named like the balance-sheet debt lines (e.g. "Long-term debt | 2025: 850"); the figures here are from the balance sheet.

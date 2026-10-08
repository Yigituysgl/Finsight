# Philip Morris International Inc. (PM) · 10-K FY2025

Labeling fact sheet. Filing: [0001628280-26-005939](https://www.sec.gov/Archives/edgar/data/1413329/000162828026005939/pm-20251231.htm), period ended 2025-12-31.
Every fact is quoted verbatim from the parsed filing (checked by scripts/build_factsheets.py);
ratios are computed by that script from the quoted values, in $ millions. No model scores.

## Scale (income statement)

- **Net revenues**: “Net revenues 1 & 2 (Notes 5 & 11) | 2025: $40,648 | 2024: $37,878 | 2023: $35,174” (Item 8 · Income statement)
- **Operating income**: “Operating income | 2025: 14,892 | 2024: 13,402 | 2023: 11,556” (Item 8 · Income statement)
- **Net earnings attributable to PMI**: “Net earnings attributable to PMI | 2025: $11,348 | 2024: $7,057 | 2023: $7,813” (Item 8 · Income statement)

## FX risk

- **Net revenues by segment (2025)**: “Net revenues | Europe: $17,111 | SSEA, CIS & MEA: $12,051 | EA, AU & PMI GTR: $6,632 | Americas: $4,854 | Total: $40,648” (Item 8)
- **Net revenues, Japan (largest market)**: “Total net revenues attributable to customers located in Japan, PMI's largest market in terms of net revenues, were $4.2 billion, $4.1 billion and $3.9 billion in 2025, 2024 and 2023, respectively.” (Item 8)
- **Russia and Ukraine**: “In 2025, Russia accounted for around 9% of our total cigarette and heated tobacco unit shipment volume, and around 6% of our total net revenues.” (Item 1A)
- **2025 net revenue growth, reported vs excluding currency and acquisitions/divestitures**: “Net revenues increased by 7.3%. Net revenues, excluding currency and acquisitions/divestitures, increased by 6.5%” (Item 7)
- **2025 operating income growth, reported vs excluding currency and acquisitions/divestitures**: “Operating income increased by 11.1%. Operating income, excluding currency and acquisitions/divestitures, increased by 9.3%” (Item 7)
- **VaR, instruments sensitive to foreign currency rates (95%, one day)**: “Foreign currency rates | At December 31, 2025: $97 | Average: $152 | High: $197 | Low: $97” (Item 7A (Item 7, Market Risk))
- **Foreign currency debt and derivatives**: “Foreign currency denominated debt and the majority of our $50 billion gross notional amount of derivative financial instruments are subject to foreign currency exchange rates fluctuation, primarily between the Euro and U.S. Dollar” (Item 7)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| Net revenues outside the Americas segment / net revenues | (40,648 - 4,854) / 40,648 | 88.1% |

## Interest rate risk

- **Total debt**: “Our total debt was $48.8 billion at December 31, 2025, and $45.7 billion at December 31, 2024. Our total debt is primarily fixed rate in nature. The weighted-average time to maturity of our long-term debt was approximately 7 years at the end of 2025 and 2024.” (Item 7)
- **Long-term debt maturing in 2026 (aggregate maturities)**: “2026 | $3,540” (Item 8)
- **Commercial paper**: “At December 31, 2025 and 2024, we had no commercial paper outstanding. The average commercial paper balance outstanding during 2025 and 2024 was $3.0 billion and $1.3 billion, respectively.” (Item 7)
- **VaR, instruments sensitive to interest rates (95%, one day)**: “Interest rates | At December 31, 2025: $135 | Average: $191 | High: $239 | Low: $135” (Item 7A (Item 7, Market Risk))
- **2025 net interest expense and variable-rate debt**: “Interest expense, net, of $966 million decreased by $177 million or 15.5%, primarily due to the impact of lower market interest rates on our variable-rate debt, as well as the favorable impact of derivative financial instruments.” (Item 7)
- **Interest expense, net**: “Interest expense, net (Note 13) | 2025: 966 | 2024: 1,143 | 2023: 1,061” (Item 8 · Income statement)
- **Interest expense (gross, Note 13)**: “Interest expense | 2025: $1,587 | 2024: $1,763 | 2023: $1,526” (Item 8)
- **Cash and cash equivalents**: “Cash and cash equivalents | 2025: $4,872 | 2024: $4,216” (Item 8 · Balance sheet)

| Computed ratio | Formula ($ millions) | Value |
|---|---|---|
| Total debt / cash and cash equivalents | 48,800 / 4,872 | 10.0× |
| 2026 maturities / cash and cash equivalents | 3,540 / 4,872 | 72.7% |
| Interest expense, net / operating income | 966 / 14,892 | 6.5% |

## Notes

- The Item 7 variance tables are misaligned by the parser: in the consolidated net revenues row, "Excl. Curr. & Acquis. / Divest.: 7.3%" is the reported change, "Change: 6.5%" is the change excluding currency and acquisitions/divestitures, and "Currency: $2,770" is the total variance (40,648 - 37,878). Read in order, the components are currency $461, acquisitions/divestitures $(170), price $1,536, volume/mix $920, cost/other $23 (sum 2,770). The prose quotes below are not affected.
- Net revenues by country are disclosed only for Japan. The Americas segment includes the U.S., so revenue outside the Americas segment is a lower bound for revenue outside the U.S.

# FinSight

Question answering and risk scoring over SEC 10-K filings, with every answer
and every risk reason citing the filing passages it rests on.

Built by a former treasury and FX risk analyst: the risk rubric reflects how a
treasury team reads market-risk disclosures (gross exposure before hedging,
everything relative to company size).

![Python](https://img.shields.io/badge/Python-3.11-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

<!-- docs/qa.png: a Q&A answer with its cited passage expanded -->
<!-- docs/risk.png: the risk dashboard with one category's "Sources" expanded -->
<!-- docs/demo.gif: selecting a filing, asking a question, running the risk analysis -->

## What it does

FinSight works on four pinned FY2025 10-K filings fetched from SEC EDGAR:
Apple (AAPL), Tesla (TSLA), Coca-Cola (KO) and Philip Morris International (PM).
In a Streamlit app you pick a filing and can

- **ask questions** about it: the answer cites numbered passages, and each cited
  passage can be opened in the app with a link to the filing on sec.gov;
- **run a risk analysis**: six categories (liquidity, revenue, legal, FX,
  interest rate, operational) are scored 1-10 against a written rubric, each
  with a reason that cites its passages.

## How it works

1. **Fetch** (`src/fetch_filings.py`): downloads the filings pinned in
   `filings.toml` (accession numbers) from EDGAR, with the contact
   User-Agent EDGAR requires. `--list TICKER` and `--verify` help pin and
   check filings.
2. **Parse** (`src/sections.py`): splits each filing into its Items (1, 1A, 3,
   7, 7A, 8), skipping the table of contents and page footers. An Item 7A that
   only points to Item 7 (PM) is replaced by the Item 7 section it names.
   Tables become one line per row with each value labelled by its column
   headers (`Total revenues | 2025: 94,827 | 2024: 97,690`); cells spanning
   several rows or columns are placed as a browser lays them out. In Item 8 the
   income statement, balance sheet and cash flow statement are tagged.
3. **Index** (`src/ingest.py`): 1,000-character chunks with 150 overlap, each
   primary statement chunked on its own; embeddings from all-MiniLM-L6-v2,
   stored in Chroma with the filing, Item and statement as metadata.
4. **Retrieve**: searches are filtered to the selected filing and split by
   Item with fixed quotas, so a long Item 8 cannot crowd out a short Item 7A.
   Q&A reads the 3 best chunks, the best Item 8 chunk and the whole income
   statement. Each risk category reads its own Item quotas; FX also searches
   for revenue by region or segment, and interest rate and liquidity also get
   the balance sheet's cash, investment and debt rows.
5. **Answer and cite**: the model sees the passages numbered `[1]`, `[2]`, ...
   and must cite them. The app lists the cited passages and, collapsed, the
   others retrieved. A **warn-only figure check** flags figures in an answer
   that appear in none of its cited passages, and citations to passages that
   do not exist; it does not block an answer.
6. **Model**: `openai/gpt-oss-120b` on Groq, one temperature for all calls
   (`LLM_TEMPERATURE`, default 0.1). The Q&A prompt forbids derived figures and
   asks for net income attributable to the company, not the line including
   noncontrolling interests.

## Risk methodology

The rubric lives in `src/rubric.py`; the scoring prompt is built from it.

- **Scale**: 1-10 (1-3 low, 4-6 medium, 7-10 high) for the risk to earnings and
  cash flow over the next 1-2 years, **relative to the company's size**: every
  prompt starts with the company's revenue, operating income and net income
  (three years) from its income statement as passage `[1]`.
- **Boilerplate**: generic risk-factor language without company-specific facts
  or figures supports a score of at most 5, in every category.
- **n/a**: the model answers INSUFFICIENT only if its passages contain no
  relevant discussion at all. The overall 0-100 score is shown only when at
  least 4 of the 6 categories are scored.

| Score | FX | Interest rate |
|---|---|---|
| 1-3 | under ~20% of revenue from outside the home market, or FX impact under ~1% of revenue | low net debt or mostly fixed-rate debt; +100bp affects under ~1% of net income |
| 4-6 | ~20-50% from outside the home market with hedging, FX impact ~1-3% of revenue | moderate leverage, some floating-rate debt; +100bp affects ~1-5% of net income |
| 7-10 | majority from outside the home market, FX impact over ~3% of revenue or operating income, emerging-market exposure, or translation largely unhedged | high leverage or mostly floating-rate debt, over ~5% of net income, or large near-term maturities |

- **FX**: the gross exposure is scored first; hedging lowers that score by at
  most 2 points, and the reason states gross exposure and hedging separately.
- **Interest rate**: valuation changes of investment portfolios weigh less than
  effects on interest expense.

Liquidity, revenue, legal and operational have bands of the same form in
`src/rubric.py`.

## Evaluation

All results below are **single runs at temperature 0.1** (2026-10-08), produced
by `scripts/eval_retrieval.py`; result files are written to `data/eval/results`.

**Retrieval hit checks** (no LLM): does retrieval return the chunk holding a
known passage? 10 checks: the income-statement revenue and net-income lines of
all four companies for the app's two suggested questions, Tesla's revenue line,
and PM's FX value-at-risk table. **10 of 10 pass.**

**Q&A vs the filings**: the app's questions "What was the total revenue?" and
"How did net income change year over year?" for each company (8 answers),
compared by hand with the income statements. **All figures in all 8 answers
match**, each labelled with its fiscal year; net income is the line
attributable to the company in all four cases. All 8 cite valid passages and
have no unverified figures. Example (PM, abridged; citation brackets
normalized):

> | Fiscal year | Net income attributable to PMI |
> |---|---|
> | 2025 | **$11,348** million [6] |
> | 2024 | **$7,057** million [6] |
> | 2023 | **$7,813** million [6] |

**Risk scores vs reference scores.** Goal: check whether the model's risk
scores match a treasury practitioner's judgment. For FX and interest rate
(8 scores, `labels/risk_labels.csv`), reference scores were drafted from the
fact sheets by applying the rubric, then reviewed by the author, who changed
3 of 8. Because the drafts used the same rubric, agreement may be optimistic.

The first run had two large misses: the model scored PM's FX risk 2 instead of
8 because it never saw where PM's revenue comes from, and it scored Tesla's
interest-rate risk 5 instead of 2 because it saw Tesla's debt but not its cash.
After adding revenue-by-region passages for FX and balance-sheet cash and debt
for interest rate, the scoring was run again.

"Gap" is the model's score minus the reference score (0 = exact match).

| Company | Category | Reference | Before fix | Gap | After fix | Gap |
|---|---|---|---|---|---|---|
| AAPL | FX | 6 | 5 | -1 | 7 | +1 |
| AAPL | Interest rate | 2 | 2 | 0 | 2 | 0 |
| TSLA | FX | 7 | 8 | +1 | 5 | -2 |
| TSLA | Interest rate | 2 | 5 | +3 | 2 | 0 |
| KO | FX | 7 | 7 | 0 | 8 | +1 |
| KO | Interest rate | 4 | 5 | +1 | 5 | +1 |
| PM | FX | 8 | 2 | -6 | 6 | -2 |
| PM | Interest rate | 6 | 5 | -1 | 5 | -1 |

**Result:** 6 of 8 scores within ±1 of the reference in both runs, but the
largest miss shrank from 6 points to 2, and the total gap from 13 to 8. No
category was left unscored (0 of 24 n/a).

Tesla FX moved the other way (from +1 to -2): the model placed Tesla's ~50%
foreign revenue in the 'with hedging' band although Tesla does not typically
hedge.

Reproduce with:

```bash
python scripts/eval_retrieval.py --retrieval-only
python scripts/eval_retrieval.py --qa-only
python scripts/eval_retrieval.py --risk-only
```

## Limitations

- **Only SEC 10-K filers** (US-listed companies): no PDFs, no annual reports
  of non-US companies, no 10-Q filings.
- **Four companies**, pinned to one fiscal year each.
- **Model arithmetic in risk reasons is not verified.** Ratios the model
  computes itself are marked "≈" and shown as approximate, not checked; sums
  it computes are flagged only as figures not found in the passages.
- **Tables can be misread**: e.g. PM's Americas segment includes the US, but
  the model has read PM's segment table as revenue earned entirely outside the
  home market.
- **Small reference set**: 8 scores for two of the six categories, drafted
  with the same rubric the model uses; the other four categories have no
  reference scores.
- **Single runs** at temperature 0.1; scores can vary between runs.
- The figure check only warns; an answer with an unverified figure is still
  shown.
- The free Groq tier has a daily token limit, so heavy use may need a paid
  tier.

## Setup

Requires Python 3.11 and a free Groq API key (https://console.groq.com).

```bash
git clone https://github.com/Yigituysgl/Finsight.git
cd Finsight
python -m venv .venv
```

Activate the environment (`.venv\Scripts\activate` on Windows,
`source .venv/bin/activate` on macOS/Linux), then:

```bash
pip install -r requirements-dev.txt
```

On Windows, clone into a short path (or enable long path support): a
dependency of Chroma, onnxruntime, installs deeply nested files that exceed
the 260-character path limit under long folder names.

Copy `.env.example` to `.env` and fill in:

- `GROQ_API_KEY`: your Groq API key
- `GROQ_MODEL`: `openai/gpt-oss-120b`
- `SEC_USER_AGENT`: a name and contact email, e.g. `FinSight you@example.com`
  (EDGAR requires it)
- `LLM_TEMPERATURE` (optional, default 0.1)

Fetch the filings, build the vector store, run the app:

```bash
python src/fetch_filings.py
python src/ingest.py
streamlit run src/app.py
```

Run the tests (no API key or network needed):

```bash
pytest
```

## Project structure

```
filings.toml               pinned 10-K filings and their income-statement rows
src/
  app.py                   Streamlit app
  config.py                paths and settings from .env
  fetch_filings.py         EDGAR download
  sections.py              Item splitting, tables, statement tagging
  ingest.py                chunking and the Chroma store
  rag.py                   Q&A retrieval, citations, figure check
  risk_scorer.py           risk retrieval and scoring
  rubric.py                risk rubric and thresholds
scripts/
  eval_retrieval.py        hit checks, Q&A and risk evaluation
  build_factsheets.py      fact sheets for the reference scores
labels/                    fact sheets and reference scores
tests/                     unit tests
```

Fetched filings (`data/`) and the vector store (`vectorstore/`) are generated
locally and not committed.

## Author

**Yigit Uysaloglu**
- LinkedIn: [linkedin.com/in/yigit-uysaloglu](https://www.linkedin.com/in/yigit-uysaloglu/)
- GitHub: [github.com/Yigituysgl](https://github.com/Yigituysgl)

## License

MIT, see [LICENSE](LICENSE).

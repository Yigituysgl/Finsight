"""Measure retrieval quality for one chunking setting.

    python scripts/eval_retrieval.py                          current CHUNK_SIZE / CHUNK_OVERLAP
    python scripts/eval_retrieval.py --chunk-size 1000 --chunk-overlap 150
    python scripts/eval_retrieval.py --retrieval-only         hit checks only, no LLM calls
    python scripts/eval_retrieval.py --repeats 3              repeat the LLM metrics
    python scripts/eval_retrieval.py --risk-only              hit checks + risk scores vs the owner's labels

Builds (or reuses) a separate vector store per setting under data/eval/stores,
so the app's own store is never touched, then runs the app's retrieval code:

  * hit checks: does retrieval return the chunk holding a known passage?
      - Tesla Q&A: the income-statement line with total revenues
      - PM FX risk: the value-at-risk table in Item 7A
      - the app's revenue and net-income questions, for each company: the
        income-statement lines with total revenue and with net income
        attributable to the company itself
  * LLM metrics (sampled at the app's LLM_TEMPERATURE):
      - the Tesla revenue answer, and whether it states both reported figures
      - the answers to the app's revenue and net-income questions
      - for each answer: the cited passages, citations to missing passages,
        and figures not found in any cited passage
      - the PM FX risk score
      - how many of the 24 risk categories (4 filings x 6) come back n/a

  * risk scores vs labels (--risk-only): all 24 categories scored once, one
    call at a time, compared with the owner's labels in labels/risk_labels.csv
    (blank rows are unlabeled): gap and agreement within ±1, n/a count, and
    whether an overall score is shown per company. A per-minute rate limit is
    waited out; when the daily quota runs out the run stops and saves what
    finished.

Each run is written to data/eval/results as JSON.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

from groq import RateLimitError

from config import COLLECTION_NAME, DATA_DIR, EMBED_MODEL, LLM_TEMPERATURE, ROOT_DIR
from fetch_filings import cache_path, load_filings
from ingest import CHUNK_OVERLAP, CHUNK_SIZE, chunk_filing, make_splitter
from rag import ask, check_answer, retrieve_for_question
from risk_scorer import (RISK_CATEGORIES, describe_read_from, item_7a_source, overall_score,
                         retrieve, scale_passage, score_categories, score_category,
                         section_quotas)
from sections import split_sections

EVAL_DIR   = DATA_DIR / "eval"
LABELS_CSV = ROOT_DIR / "labels" / "risk_labels.csv"

# Groq's free tier limits tokens per minute and per day. A per-minute limit is
# waited out (at most this many times per call); a daily one ends the run.
RATE_LIMIT_RETRIES = 6
DEFAULT_WAIT       = 30   # seconds, when the response gives no retry-after

TESLA_QUESTION = "What were Tesla's total revenues in fiscal 2025 and fiscal 2024?"
TESLA_FIGURES  = ["94,827", "97,690"]  # $M, FY2025 and FY2024, Item 8

# Passages a correct retrieval must return, matched with whitespace collapsed
# so they are found whatever the chunk boundaries are. Each passage is given
# in the plain table text and in the row-per-line format with column headers.
TESLA_PASSAGES = ["Total revenues 94,827 97,690",
                  "Total revenues | 2025: 94,827 | 2024: 97,690"]
PM_PASSAGES    = ["Foreign currency rates $97 $152 $197 $97",
                  "Foreign currency rates | At December 31, 2025: $97 | Average: $152 | High: $197 | Low: $97"]

# The app's suggested revenue and net-income questions, and for each company
# the income-statement lines the answers must rest on: total revenue, and net
# income attributable to the company itself, not to equity-method investees
# or noncontrolling interests.
QA_QUESTIONS = {"revenue":    "What was the total revenue?",
                "net_income": "How did net income change year over year?"}
INCOME_STATEMENT_PASSAGES = {
    "AAPL": {"revenue":    "Total net sales | September 27, 2025: 416,161 | September 28, 2024: 391,035",
             "net_income": "Net income | September 27, 2025: $112,010 | September 28, 2024: $93,736"},
    "TSLA": {"revenue":    "Total revenues | 2025: 94,827 | 2024: 97,690",
             "net_income": "Net income attributable to common stockholders | 2025: $3,794 | 2024: $7,091"},
    "KO":   {"revenue":    "Net Operating Revenues | 2025: $47,941 | 2024: $47,061",
             "net_income": "Net Income Attributable to Shareowners of The Coca-Cola Company"
                           " | 2025: $13,107 | 2024: $10,631"},
    "PM":   {"revenue":    "Net revenues 1 & 2 (Notes 5 & 11) | 2025: $40,648 | 2024: $37,878",
             "net_income": "Net earnings attributable to PMI | 2025: $11,348 | 2024: $7,057"},
}


def normalise(text):
    return re.sub(r"\s+", " ", text)


def hits(docs, passages):
    """(section, chunk_index) of each retrieved chunk that contains a passage."""
    return [(d.metadata["section"], d.metadata["chunk_index"]) for d in docs
            if any(p in normalise(d.page_content) for p in passages)]


def describe(docs):
    return [(d.metadata["section"], d.metadata["chunk_index"]) for d in docs]


def load_or_build_store(chunk_size, chunk_overlap):
    splitter = make_splitter(chunk_size, chunk_overlap)
    texts, metadatas, ids = [], [], []
    for filing in load_filings():
        sections = split_sections(cache_path(filing).read_bytes())
        t, m, i  = chunk_filing(filing, sections, splitter)
        texts, metadatas, ids = texts + t, metadatas + m, ids + i

    # Keyed by the chunks themselves, so a parser change never reuses a stale store.
    keyed      = ids + texts + [json.dumps(m, sort_keys=True) for m in metadatas]
    digest     = hashlib.sha256("\x00".join(keyed).encode("utf-8")).hexdigest()[:10]
    store_dir  = EVAL_DIR / "stores" / f"{chunk_size}_{chunk_overlap}_{digest}"
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    store      = Chroma(collection_name=COLLECTION_NAME, embedding_function=embeddings,
                        persist_directory=str(store_dir))
    if store.get(limit=1)["ids"]:
        print(f"Reusing store {store_dir}")
        return store

    print(f"Building store {store_dir} ...")
    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    print(f"  {len(texts):,} chunks")
    return store


def check_retrieval(store):
    tesla_docs = retrieve_for_question(TESLA_QUESTION, store, "TSLA")
    pm_docs    = retrieve(store, "PM", RISK_CATEGORIES["FX Risk"]["query"],
                          section_quotas("FX Risk", item_7a_source(store, "PM")))
    checks = {
        "tesla_revenue": {"hit": hits(tesla_docs, TESLA_PASSAGES), "retrieved": describe(tesla_docs)},
        "pm_fx":         {"hit": hits(pm_docs, PM_PASSAGES),       "retrieved": describe(pm_docs)},
    }
    for ticker, passages in INCOME_STATEMENT_PASSAGES.items():
        for name, question in QA_QUESTIONS.items():
            docs = retrieve_for_question(question, store, ticker)
            checks[f"{ticker}_{name}"] = {"hit": hits(docs, [passages[name]]),
                                          "retrieved": describe(docs)}
    return checks


def cited_answer(question, store, ticker):
    """The answer, the number of context passages, and check_answer's result."""
    answer, retrieved = ask(question, store, ticker)
    return {"answer": answer, "passages": len(retrieved), **check_answer(answer, retrieved)}


def describe_citations(record):
    return (f"cited {record['cited'] or 'nothing'} of {record['passages']} passages"
            f" | invalid: {record['invalid_citations'] or 'none'}"
            f" | unverified figures: {record['unverified_figures'] or 'none'}")


def run_llm_metrics(store, tickers):
    tesla     = cited_answer(TESLA_QUESTION, store, "TSLA")
    answer    = tesla["answer"]
    qa        = {ticker: {name: cited_answer(question, store, ticker)
                          for name, question in QA_QUESTIONS.items()}
                 for ticker in tickers}
    scores    = {}
    for ticker in tickers:
        scored, read_from, evidence = score_categories(store, ticker)
        scores[ticker] = {cat: {"score": s, "reason": r, "read_from": read_from[cat],
                                "check": evidence[cat]["check"]}
                          for cat, (s, r) in scored.items()}
    n_a = [f"{t} {cat}" for t, cats in scores.items()
           for cat, v in cats.items() if v["score"] is None]
    return {
        "tesla":              tesla,
        "tesla_figures_found": {f: f in answer for f in TESLA_FIGURES},
        "qa":                 qa,
        "pm_fx":              scores["PM"]["FX Risk"],
        "n_a":                n_a,
        "scores":             scores,
    }


class DailyQuotaExhausted(Exception):
    pass


def is_daily_limit(error):
    text = str(error).lower()
    return "per day" in text or "(tpd)" in text or "(rpd)" in text


def retry_after(error):
    try:
        return min(120.0, float(error.response.headers.get("retry-after")))
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_WAIT


def with_rate_limit_retries(call):
    for _ in range(RATE_LIMIT_RETRIES):
        try:
            return call()
        except RateLimitError as error:
            if is_daily_limit(error):
                raise DailyQuotaExhausted(str(error)) from error
            wait = retry_after(error)
            print(f"    rate limit, waiting {wait:.0f}s")
            time.sleep(wait)
    return call()


def score_risk(store, filings):
    """Score all categories of all filings, one call at a time. Returns
    ({ticker: {category: result}}, None) or, when the daily quota runs out,
    (what finished, the reason it stopped)."""
    scores = {}
    for filing in filings:
        ticker  = filing["ticker"]
        scale   = scale_passage(store, filing)
        item_7a = item_7a_source(store, ticker)
        scores[ticker] = {}
        for category, spec in RISK_CATEGORIES.items():
            docs = retrieve(store, ticker, spec["query"], section_quotas(category, item_7a))
            try:
                score, reason, evidence = with_rate_limit_retries(
                    lambda: score_category(category, docs, scale))
            except DailyQuotaExhausted as error:
                return scores, f"daily quota exhausted before {ticker} {category}: {error}"
            scores[ticker][category] = {
                "score": score, "reason": reason, "read_from": describe_read_from(docs),
                "check": evidence["check"],
                "cited": [p["label"] for p in evidence["passages"] if p["cited"]]}
            print(f"  {ticker:5} {category:19} {'n/a' if score is None else score}")
    return scores, None


def load_labels(path=LABELS_CSV):
    """{(ticker, category): {"score", "reason"}} for the labelled rows, in file order."""
    with open(path, encoding="utf-8", newline="") as f:
        return {(row["company"], row["category"]): {"score": int(row["my_score"]),
                                                    "reason": row["my_reason"]}
                for row in csv.DictReader(f) if row["my_score"].strip()}


def compare_with_labels(scores, labels):
    """One row per label: model score (None if n/a or not run), gap, within ±1."""
    rows = []
    for (ticker, category), label in labels.items():
        result = scores.get(ticker, {}).get(category)
        model  = result["score"] if result else None
        gap    = None if model is None else model - label["score"]
        rows.append({"company": ticker, "category": category, "label": label["score"],
                     "model": model,
                     "status": "not run" if result is None else "n/a" if model is None else "scored",
                     "gap": gap, "within_1": gap is not None and abs(gap) <= 1})
    return rows


def run_risk_vs_labels(store, filings):
    scores, stopped = score_risk(store, filings)
    overall = {ticker: overall_score({c: (v["score"], v["reason"]) for c, v in cats.items()})
                       if len(cats) == len(RISK_CATEGORIES) else "incomplete"
               for ticker, cats in scores.items()}
    rows = compare_with_labels(scores, load_labels())
    return {"complete": stopped is None, "stopped": stopped, "scores": scores,
            "overall": overall,
            "n_a": [f"{t} {c}" for t, cats in scores.items() for c, v in cats.items()
                    if v["score"] is None],
            "scored_categories": sum(len(cats) for cats in scores.values()),
            "comparison": rows,
            "within_1": sum(r["within_1"] for r in rows), "labels": len(rows)}


def print_risk_report(risk):
    print(f"\n=== Risk scores vs labels ({'complete' if risk['complete'] else 'INCOMPLETE'}) ===")
    if risk["stopped"]:
        print(f"Stopped: {risk['stopped']}")
    print(f"{'company':8}{'category':20}{'model':>7}{'label':>6}{'gap':>5}  within ±1")
    for r in risk["comparison"]:
        model = r["model"] if r["status"] == "scored" else r["status"]
        gap   = "" if r["gap"] is None else f"{r['gap']:+d}"
        print(f"{r['company']:8}{r['category']:20}{model!s:>7}{r['label']:>6}{gap:>5}  "
              f"{'yes' if r['within_1'] else 'no'}")
    print(f"\nAgreement: {risk['within_1']} of {risk['labels']} within ±1")
    print(f"n/a: {len(risk['n_a'])} of {risk['scored_categories']} categories run  {risk['n_a']}")
    for ticker, overall in risk["overall"].items():
        shown = overall if overall is not None else "not shown (fewer than 4 scored)"
        print(f"Overall {ticker}: {shown}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunk-size",    type=int, default=CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=CHUNK_OVERLAP)
    parser.add_argument("--repeats",       type=int, default=1)
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--risk-only", action="store_true",
                        help="risk scores vs labels/risk_labels.csv, no Q&A")
    args = parser.parse_args()
    # Model output can contain characters the Windows console codepage lacks.
    sys.stdout.reconfigure(encoding="utf-8")

    label   = f"{args.chunk_size}_{args.chunk_overlap}"
    store   = load_or_build_store(args.chunk_size, args.chunk_overlap)
    tickers = [f["ticker"] for f in load_filings()]
    result  = {"setting": label, "temperature": LLM_TEMPERATURE,
               "retrieval": check_retrieval(store), "runs": []}

    if args.risk_only:
        print("\nRisk scoring, one call at a time")
        result["risk"] = run_risk_vs_labels(store, load_filings())
    elif not args.retrieval_only:
        for n in range(args.repeats):
            print(f"\nLLM run {n + 1}/{args.repeats}")
            result["runs"].append(run_llm_metrics(store, tickers))

    prefix = "risk_" if args.risk_only else ""
    out = EVAL_DIR / "results" / f"{prefix}{label}_{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== {label} (temperature {LLM_TEMPERATURE}) ===")
    for name, check in result["retrieval"].items():
        print(f"{name:16} hit: {check['hit'] or 'MISS'}   retrieved: {check['retrieved']}")
    for n, run in enumerate(result["runs"], 1):
        figures = ", ".join(f"{f} {'yes' if ok else 'no'}" for f, ok in run["tesla_figures_found"].items())
        print(f"\nRun {n}: Tesla figures stated: {figures}")
        print(f"  Tesla answer: {run['tesla']['answer']}")
        print(f"  Tesla citations: {describe_citations(run['tesla'])}")
        print(f"  PM FX score:  {run['pm_fx']['score'] or 'n/a'}  ({run['pm_fx']['reason']})")
        print(f"  n/a: {len(run['n_a'])}/{len(tickers) * len(RISK_CATEGORIES)}  {run['n_a']}")
        for ticker, answers in run["qa"].items():
            for name, record in answers.items():
                print(f"\n  {ticker} {QA_QUESTIONS[name]}\n{record['answer']}")
                print(f"  Citations: {describe_citations(record)}")
        print("\n  Citation summary:")
        for ticker, answers in run["qa"].items():
            for name, record in answers.items():
                print(f"    {ticker:5} {name:11} {describe_citations(record)}")
    if "risk" in result:
        print_risk_report(result["risk"])
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()

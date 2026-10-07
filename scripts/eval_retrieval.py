"""Measure retrieval quality for one chunking setting.

    python scripts/eval_retrieval.py                          current CHUNK_SIZE / CHUNK_OVERLAP
    python scripts/eval_retrieval.py --chunk-size 1000 --chunk-overlap 150
    python scripts/eval_retrieval.py --retrieval-only         hit checks only, no LLM calls
    python scripts/eval_retrieval.py --repeats 3              repeat the LLM metrics

Builds (or reuses) a separate vector store per setting under data/eval/stores,
so the app's own store is never touched, then runs the app's retrieval code:

  * hit checks: does retrieval return the chunk holding a known passage?
      - Tesla Q&A: the income-statement line with total revenues
      - PM FX risk: the value-at-risk table in Item 7A
  * LLM metrics (sampled at the app's LLM_TEMPERATURE):
      - the Tesla revenue answer, and whether it states both reported figures
      - the PM FX risk score
      - how many of the 24 risk categories (4 filings x 6) come back n/a

Each run is written to data/eval/results as JSON.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

from config import COLLECTION_NAME, DATA_DIR, EMBED_MODEL, LLM_TEMPERATURE
from fetch_filings import cache_path, load_filings
from ingest import CHUNK_OVERLAP, CHUNK_SIZE, chunk_filing, make_splitter
from rag import ask, retrieve_for_question
from risk_scorer import (RISK_CATEGORIES, item_7a_source, retrieve,
                         score_categories, section_quotas)
from sections import split_sections

EVAL_DIR = DATA_DIR / "eval"

TESLA_QUESTION = "What were Tesla's total revenues in fiscal 2025 and fiscal 2024?"
TESLA_FIGURES  = ["94,827", "97,690"]  # $M, FY2025 and FY2024, Item 8

# Passages a correct retrieval must return, matched with whitespace collapsed
# so they are found whatever the chunk boundaries are. Each passage is given
# in the plain table text and in the row-per-line format with column headers.
TESLA_PASSAGES = ["Total revenues 94,827 97,690",
                  "Total revenues | 2025: 94,827 | 2024: 97,690"]
PM_PASSAGES    = ["Foreign currency rates $97 $152 $197 $97",
                  "Foreign currency rates | At December 31, 2025: $97 | Average: $152 | High: $197 | Low: $97"]


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
    digest     = hashlib.sha256("\x00".join(ids + texts).encode("utf-8")).hexdigest()[:10]
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
    return {
        "tesla_revenue": {"hit": hits(tesla_docs, TESLA_PASSAGES), "retrieved": describe(tesla_docs)},
        "pm_fx":         {"hit": hits(pm_docs, PM_PASSAGES),       "retrieved": describe(pm_docs)},
    }


def run_llm_metrics(store, tickers):
    answer, _ = ask(TESLA_QUESTION, store, "TSLA")
    scores    = {}
    for ticker in tickers:
        scored, read_from = score_categories(store, ticker)
        scores[ticker] = {cat: {"score": s, "reason": r, "read_from": read_from[cat]}
                          for cat, (s, r) in scored.items()}
    n_a = [f"{t} {cat}" for t, cats in scores.items()
           for cat, v in cats.items() if v["score"] is None]
    return {
        "tesla_answer":       answer,
        "tesla_figures_found": {f: f in answer for f in TESLA_FIGURES},
        "pm_fx":              scores["PM"]["FX Risk"],
        "n_a":                n_a,
        "scores":             scores,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunk-size",    type=int, default=CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=CHUNK_OVERLAP)
    parser.add_argument("--repeats",       type=int, default=1)
    parser.add_argument("--retrieval-only", action="store_true")
    args = parser.parse_args()
    # Model output can contain characters the Windows console codepage lacks.
    sys.stdout.reconfigure(encoding="utf-8")

    label   = f"{args.chunk_size}_{args.chunk_overlap}"
    store   = load_or_build_store(args.chunk_size, args.chunk_overlap)
    tickers = [f["ticker"] for f in load_filings()]
    result  = {"setting": label, "temperature": LLM_TEMPERATURE,
               "retrieval": check_retrieval(store), "runs": []}

    if not args.retrieval_only:
        for n in range(args.repeats):
            print(f"\nLLM run {n + 1}/{args.repeats}")
            result["runs"].append(run_llm_metrics(store, tickers))

    out = EVAL_DIR / "results" / f"{label}_{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== {label} (temperature {LLM_TEMPERATURE}) ===")
    for name, check in result["retrieval"].items():
        print(f"{name:14} hit: {check['hit'] or 'MISS'}   retrieved: {check['retrieved']}")
    for n, run in enumerate(result["runs"], 1):
        figures = ", ".join(f"{f} {'yes' if ok else 'no'}" for f, ok in run["tesla_figures_found"].items())
        print(f"\nRun {n}: Tesla figures stated: {figures}")
        print(f"  Tesla answer: {run['tesla_answer']}")
        print(f"  PM FX score:  {run['pm_fx']['score'] or 'n/a'}  ({run['pm_fx']['reason']})")
        print(f"  n/a: {len(run['n_a'])}/{len(tickers) * len(RISK_CATEGORIES)}  {run['n_a']}")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()

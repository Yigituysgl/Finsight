"""Build the vector store from the pinned EDGAR filings.

    python src/ingest.py   split each cached filing into Items, chunk them and
                           rebuild the "filings" collection from scratch
"""
import sys
from collections import Counter

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from config import COLLECTION_NAME, EMBED_MODEL, VECTORSTORE_DIR
from fetch_filings import cache_path, filing_url, load_filings
from sections import KEEP, describe_7a, split_sections

# Large enough to keep most financial-statement tables in one chunk, small
# enough to fit the embedding model: all-MiniLM-L6-v2 reads only the first
# 256 tokens, and at 1500 characters ~40% of chunks are cut off, which hid
# Tesla's revenue line from retrieval (scripts/eval_retrieval.py).
CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150


def make_splitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )


def chunk_filing(filing, sections, splitter):
    """Return (texts, metadatas, ids); every chunk carries its filing and section."""
    texts, metadatas, ids = [], [], []
    for section in sections:
        for i, chunk in enumerate(splitter.split_text(section["text"])):
            texts.append(chunk)
            metadatas.append({
                "ticker":         filing["ticker"],
                "company":        filing["company"],
                "cik":            filing["cik"],
                "form":           filing["form"],
                "fiscal_year":    filing["fiscal_year"],
                "period_end":     filing["period_end"],
                "accession":      filing["accession"],
                "source_url":     filing_url(filing),
                "section":        section["section"],
                "section_title":  section["title"],
                "content_source": section["content_source"],
                "resolved_from":  section["resolved_from"],
                "chunk_index":    i,
            })
            # Stable IDs: re-ingesting the same pins yields the same store.
            ids.append(f"{filing['accession']}:{section['section']}:{i}")
    return texts, metadatas, ids


def main():
    filings = load_filings()
    missing = [f["ticker"] for f in filings if not cache_path(f).exists()]
    if missing:
        sys.exit(f"Not fetched yet: {', '.join(missing)}. Run python src/fetch_filings.py first.")

    splitter = make_splitter()
    texts, metadatas, ids = [], [], []
    print("[1/2] Splitting filings into Items and chunks...")
    for filing in filings:
        sections = split_sections(cache_path(filing).read_bytes())
        t, m, i  = chunk_filing(filing, sections, splitter)
        texts, metadatas, ids = texts + t, metadatas + m, ids + i
        item_7a = next((s for s in sections if s["section"] == "7A"), None)
        print(f"  {filing['ticker']:5} {len(t):5,} chunks"
              + (f"   7A: {describe_7a(item_7a)}" if item_7a else "   7A: missing"))

    print(f"\n[2/2] Embedding {len(texts):,} chunks and rebuilding '{COLLECTION_NAME}'...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    # Rebuild from scratch so the store always matches filings.toml.
    Chroma(collection_name=COLLECTION_NAME, embedding_function=embeddings,
           persist_directory=str(VECTORSTORE_DIR)).delete_collection()
    Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        ids=ids,
        collection_name=COLLECTION_NAME,
        persist_directory=str(VECTORSTORE_DIR)
    )

    counts = Counter((m["ticker"], m["section"]) for m in metadatas)
    print(f"\n  {'':6}" + "".join(f"{item:>8}" for item in KEEP) + f"{'total':>8}")
    for filing in filings:
        row = [counts[(filing["ticker"], item)] for item in KEEP]
        print(f"  {filing['ticker']:6}" + "".join(f"{n:>8,}" for n in row) + f"{sum(row):>8,}")
    print(f"\n  Saved to '{VECTORSTORE_DIR}'")


if __name__ == "__main__":
    main()

import re
from collections import Counter
from groq import Groq

from langchain_core.documents import Document

from config import GROQ_API_KEY, GROQ_MODEL, LLM_TEMPERATURE
from fetch_filings import load_filings
from rag import (CITATION, check_answer, chunk_key, income_statement, load_vectorstore,
                 numbered_context, passages)
from rubric import GENERAL, MIN_SCORED_CATEGORIES, risk_level, rubric_text
from sections import (BALANCE_SHEET, SHORT_UNRESOLVED, ScaleLineError, cash_debt_lines,
                      scale_lines)

# gpt-oss is a reasoning model: its reasoning tokens count against
# max_tokens, so the limits must leave room for reasoning plus the answer.
SCORE_MAX_TOKENS   = 1024
SUMMARY_MAX_TOKENS = 1024

# "SCORE: 7", "SCORE: [7]", "SCORE: 7/10". Decimals such as "7.5" are
# rejected rather than truncated.
SCORE_LINE  = re.compile(r"^\s*SCORE\s*:\s*\[?\s*(\d+)(?!\d|\.\d)", re.IGNORECASE | re.MULTILINE)
# The model answers INSUFFICIENT when the text does not let it judge the risk.
INSUFFICIENT_LINE = re.compile(r"^\s*SCORE\s*:\s*\[?\s*INSUFFICIENT\b", re.IGNORECASE | re.MULTILINE)
MIN_SCORE, MAX_SCORE = 1, 10
REASON_LINE = re.compile(r"^\s*REASON\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

# Each category reads a fixed number of chunks from each 10-K Item that should
# discuss it, primary Item first. Searching each Item separately keeps a large
# Item 8 from crowding out a short Item 7A.
RISK_CATEGORIES = {
    "Liquidity Risk":     {"query":    "liquidity capital resources cash flow debt borrowing",
                           "sections": {"7": 2, "8": 1}},
    "Revenue Risk":       {"query":    "revenue decline net sales decrease demand weakness",
                           "sections": {"7": 2, "1A": 1}},
    "Legal Risk":         {"query":    "litigation lawsuit regulatory investigation contingencies",
                           "sections": {"3": 2, "8": 1, "1A": 1}},
    "FX Risk":            {"query":    "foreign currency exchange rate risk hedging",
                           "sections": {"7A": 3, "8": 1}},
    "Interest Rate Risk": {"query":    "interest rate risk sensitivity debt investments",
                           "sections": {"7A": 2, "8": 1, "7": 1}},
    "Operational Risk":   {"query":    "supply chain operational disruption workforce costs",
                           "sections": {"1A": 2, "7": 1}},
}

# Further searches per category, merged with the main one. FX gross exposure
# depends on where revenue comes from, which Item 7A rarely states: this query
# finds the revenue-by-region or by-segment table (Item 7 or the Item 8 segment
# note) in all four filings, for the current year.
GEOGRAPHY_QUERY = "revenue by geographic area United States international countries segment"
EXTRA_SEARCHES  = {"FX Risk": [(GEOGRAPHY_QUERY, {"7": 1, "8": 2})]}

# These categories also read the balance sheet's cash, investment and debt rows
# (balance_sheet_passage), so the net position is in front of the model.
BALANCE_SHEET_CATEGORIES = {"Liquidity Risk", "Interest Rate Risk"}

# When a filing's Item 7A is a pointer that could not be resolved, categories
# that read 7A also read Item 7, where the market risk discussion usually is.
FALLBACK_ITEM_7_CHUNKS = 2

def scale_passage(vectorstore, filing):
    """The company's scale for the scoring prompt: its revenue, operating
    income and net income rows (all years) from the stored income statement,
    with the statement's units line. Raises ScaleLineError if a pinned row is
    missing."""
    docs = income_statement(vectorstore, filing["ticker"])
    if not docs:
        raise ScaleLineError(f"{filing['ticker']}: no income-statement chunks in the store")
    # Chunks split at line breaks, and overlapping chunks repeat lines.
    rows, units = scale_lines("\n".join(doc.page_content for doc in docs), filing)
    text = "\n".join([units] * bool(units) + list(rows.values()))
    # Not a stored chunk: chunk_index -1 keeps it apart from real chunks.
    return Document(page_content=text, metadata={**docs[0].metadata, "chunk_index": -1})

def balance_sheet_passage(vectorstore, ticker):
    """The balance sheet's cash, investment and debt rows (sections.cash_debt_lines)
    from the stored balance-sheet chunks, or None if none are found."""
    found = vectorstore.get(where={"$and": [{"ticker": ticker}, {"statement": BALANCE_SHEET}]})
    docs  = sorted(zip(found["documents"], found["metadatas"]), key=lambda d: d[1]["chunk_index"])
    lines = cash_debt_lines("\n".join(text for text, _ in docs))
    if not any("|" in line for line in lines):
        return None
    # Not a stored chunk: chunk_index -2 keeps it apart from real chunks.
    return Document(page_content="\n".join(lines), metadata={**docs[0][1], "chunk_index": -2})

def item_7a_source(vectorstore, ticker):
    """How the filing's Item 7A text was obtained (own / pointer_resolved / short_unresolved)."""
    found = vectorstore.get(where={"$and": [{"ticker": ticker}, {"section": "7A"}]},
                            limit=1, include=["metadatas"])
    return found["metadatas"][0]["content_source"] if found["ids"] else None

def section_quotas(category, item_7a):
    quotas = dict(RISK_CATEGORIES[category]["sections"])
    if "7A" in quotas and item_7a in (SHORT_UNRESOLVED, None):
        quotas["7"] = max(quotas.get("7", 0), FALLBACK_ITEM_7_CHUNKS)
    return quotas

def retrieve(vectorstore, ticker, query, quotas):
    docs = []
    for section, k in quotas.items():
        docs += vectorstore.similarity_search(
            query, k=k, filter={"$and": [{"ticker": ticker}, {"section": section}]})
    return docs

def category_docs(vectorstore, ticker, category, item_7a):
    """The category's main search plus its EXTRA_SEARCHES, without duplicates."""
    docs = retrieve(vectorstore, ticker, RISK_CATEGORIES[category]["query"],
                    section_quotas(category, item_7a))
    for query, quotas in EXTRA_SEARCHES.get(category, []):
        docs += retrieve(vectorstore, ticker, query, quotas)
    unique = {}
    for doc in docs:
        unique.setdefault(chunk_key(doc), doc)
    return list(unique.values())

def describe_read_from(docs):
    """E.g. "Item 7A ×2, Item 8 ×1", in retrieval order."""
    counts = Counter(doc.metadata["section"] for doc in docs)
    return ", ".join(f"Item {section} ×{n}" for section, n in counts.items())

# FX reasons keep gross exposure and hedging apart (rubric.NOTES["FX Risk"]).
REASON_FORMATS = {
    "FX Risk": "Gross exposure: [facts, each cited as [n]]. Hedging: [facts, each cited as [n]].",
}
DEFAULT_REASON_FORMAT = "[one or two sentences; each fact cited as [n]]"

def score_prompt(category, context, with_balance_sheet=False):
    reason_format = REASON_FORMATS.get(category, DEFAULT_REASON_FORMAT)
    fixed = "passage [1] is the company's scale from its income statement"
    if with_balance_sheet:
        fixed += ", passage [2] its cash, investments and debt from the balance sheet"
    return f"""You are a financial risk analyst scoring the {category} of a company from its 10-K.

{GENERAL}

RUBRIC for {category} (1-3 low, 4-6 medium, 7-10 high):
{rubric_text(category)}

PASSAGES (numbered; {fixed}):
{context}

Rules:
- Use only the passages and cite the passage after each fact as [n].
- Quote figures exactly as they appear in the passage, with the same digits and
  units: no rounding and no unit conversion. A passage figure of 47,941 in a table
  "in millions" is written $47,941 million, not $47.9 billion.
- A ratio you compute yourself must be marked with "≈", e.g. "≈ 2% of revenue".
- Write the reason on a single line.

Respond in exactly this format:
SCORE: [number 1-10, or INSUFFICIENT]
REASON: {reason_format}"""

def score_category(category_name, docs, scale, balance_sheet=None):
    """Score one category from its retrieved docs, with the scale passage as [1]
    and, if given, the balance-sheet passage as [2]. Returns (score, reason,
    evidence); evidence holds the numbered passages (marked cited or not) and
    check_answer's result for the reason."""
    if not docs:
        return None, "No text found in the Items this category reads", {"passages": [], "check": None}
    docs   = [scale] + [balance_sheet] * bool(balance_sheet) + docs
    prompt = score_prompt(category_name, numbered_context(docs), bool(balance_sheet))

    client   = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=LLM_TEMPERATURE,
        max_tokens=SCORE_MAX_TOKENS
    )

    score, reason = parse_score_response(response.choices[0].message.content or "")
    retrieved     = passages(docs, reason)
    check         = check_answer(reason, retrieved, allow_approximate=True)
    return score, reason, {"passages": retrieved, "check": check}

def parse_score_response(raw):
    """Return (score, reason). score is None (shown as n/a) when the model answers
    INSUFFICIENT or no valid 1-10 integer is found."""
    text         = raw.replace("*", "")  # tolerate markdown bold: **SCORE:** 7
    reason_match = REASON_LINE.search(text)
    reason       = reason_match.group(1).strip() if reason_match else "No reason given"

    if INSUFFICIENT_LINE.search(text):
        return None, f"Insufficient information: {reason}"

    score_match = SCORE_LINE.search(text)
    score       = int(score_match.group(1)) if score_match else None
    if score is None or not MIN_SCORE <= score <= MAX_SCORE:
        return None, "Could not parse model response"
    return score, reason

def overall_score(scores_dict):
    """0-100 average of the scored categories, or None when fewer than
    MIN_SCORED_CATEGORIES could be scored. Unscored categories (None) are left
    out instead of being counted as a default value."""
    scored = [score for score, _ in scores_dict.values() if score is not None]
    if len(scored) < MIN_SCORED_CATEGORIES:
        return None
    return round(sum(scored) / (10 * len(scored)) * 100)

# The card line under each score: the reason's first sentence, without
# citations. A period or semicolon ends a sentence only after a lowercase
# letter, digit, "%" or bracket, so "U.S." and "$4.37" do not; "U.S.." (an
# abbreviation, then the period that followed its removed citation) does.
SENTENCE_END    = re.compile(r"(?<=[a-z0-9%)\]])[.;](?=\s|$)|(?<=\.)\.(?=\s|$)")
SHORT_REASON_WORDS = 20
# What is left of "(passages [3] and [4])" once the citations are removed.
EMPTY_PARENS    = re.compile(r"\s*\((?:\s|,|and|see|passages?)*\)", re.IGNORECASE)

# A sentence that only restates the company's scale ("The company reports
# $40,648 million in net revenues, $14,892 million operating income and
# $11,348 million net earnings (2025)") says nothing about the risk. Without
# its figures, scale line names, names (capitalised words) and these filler
# words, nothing is left of it.
SCALE_TERMS     = re.compile(r"\b(?:revenues?|sales|operating income|income from operations|"
                             r"net income|net earnings|earnings)\b", re.IGNORECASE)
FIGURE          = re.compile(r"[$≈~]?\s*\d[\d,.]*\s*%?")
SCALE_FILLER    = {"the", "company", "company's", "company’s", "reports", "reported", "has", "had",
                   "of", "in", "and", "with", "for", "its", "a", "an", "was", "were", "is", "are",
                   "total", "net", "million", "billion", "m", "bn", "fiscal", "year", "respectively",
                   "generated", "earned", "posted", "recorded"}

def restates_scale(sentence):
    """True when the sentence names scale figures and says nothing else."""
    if not SCALE_TERMS.search(sentence):
        return False
    rest = FIGURE.sub(" ", SCALE_TERMS.sub(" ", sentence))
    words = re.findall(r"[^\W\d_][\w'’‑-]*", rest)
    return all(word.lower() in SCALE_FILLER or word[0].isupper() for word in words)

def sentences(text):
    """The text split at SENTENCE_END, without the end marks."""
    start = 0
    for end in SENTENCE_END.finditer(text):
        yield text[start:end.start()].strip()
        start = end.end()
    if text[start:].strip():
        yield text[start:].strip().rstrip(".")

def short_reason(reason, max_words=SHORT_REASON_WORDS):
    """The first sentence of a reason without [n] citations, cut to max_words;
    the next one if the first only restates the scale figures."""
    text  = EMPTY_PARENS.sub("", CITATION.sub("", reason))
    text  = re.sub(r"\s+([.,;:)])", r"\1", " ".join(text.split()))
    parts = [part for part in sentences(text) if part] or [""]
    line  = next((part for part in parts if not restates_scale(part)), parts[0])
    words = (line[:1].upper() + line[1:]).split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")

def generate_summary(scores_dict, overall, vectorstore, ticker):
    if overall is None:
        return (f"Fewer than {MIN_SCORED_CATEGORIES} of {len(scores_dict)} risk categories could be "
                "scored, so no summary was generated.")

    docs    = retrieve(vectorstore, ticker, "financial performance risk outlook", {"7": 3})
    context = "\n\n".join([doc.page_content for doc in docs])
    scores_text = "\n".join([
        f"- {cat}: {score}/10 ({risk_level(score).upper()})" if score is not None
        else f"- {cat}: n/a (could not be scored)"
        for cat, (score, _) in scores_dict.items()
    ])

    prompt = f"""You are a senior financial analyst.
Individual risk scores:
{scores_text}
Overall risk score: {overall}/100

Document context:
{context}

Write a 3-sentence executive summary of the risk profile.
Be specific, use actual numbers from the context."""

    client   = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=LLM_TEMPERATURE,
        max_tokens=SUMMARY_MAX_TOKENS
    )
    return (response.choices[0].message.content or "").strip()

def score_categories(vectorstore, ticker):
    """Return ({category: (score, reason)}, {category: "Item 7A ×2, ..."},
    {category: evidence}); see score_category for evidence."""
    scores_dict, read_from, evidence = {}, {}, {}
    filing  = next(f for f in load_filings() if f["ticker"] == ticker)
    scale   = scale_passage(vectorstore, filing)
    balance = balance_sheet_passage(vectorstore, ticker)
    item_7a = item_7a_source(vectorstore, ticker)
    print(f"  Item 7A text: {item_7a}")

    for category in RISK_CATEGORIES:
        print(f"  Scoring {category}...")
        docs = category_docs(vectorstore, ticker, category, item_7a)
        score, reason, evidence[category] = score_category(
            category, docs, scale, balance if category in BALANCE_SHEET_CATEGORIES else None)
        scores_dict[category] = (score, reason)
        read_from[category]   = describe_read_from(docs)
    return scores_dict, read_from, evidence

def run_risk_analysis(vectorstore, ticker, company_name):
    """Score all categories and write the summary. Prints only progress lines
    (ASCII): the app runs this under whatever stdout encoding Streamlit has,
    and on Windows a redirected stdout is cp1252, which cannot encode the
    report's bars or many characters in model reasons."""
    print(f"\n=== FinSight Risk Analysis: {company_name} ===\n")
    scores_dict, read_from, evidence = score_categories(vectorstore, ticker)
    overall = overall_score(scores_dict)
    print("  Generating executive summary...")
    summary = generate_summary(scores_dict, overall, vectorstore, ticker)
    return overall, scores_dict, summary, read_from, evidence

def print_risk_report(company_name, overall, scores_dict, summary, read_from):
    """Console report for the command line (stdout must accept UTF-8)."""
    parsed = [score for score, _ in scores_dict.values() if score is not None]
    print("\n" + "="*50)
    print(f"RISK RESULTS: {company_name}")
    print("="*50)

    for category, (score, reason) in scores_dict.items():
        if score is None:
            print(f"\n{category:20} n/a")
        else:
            level = risk_level(score).upper()
            bar   = "█" * score + "░" * (10 - score)
            print(f"\n{category:20} {score}/10  [{level}]")
            print(f"  {bar}")
        print(f"  {reason}")
        print(f"  Read from: {read_from[category] or 'nothing'}")

    print("\n" + "="*50)
    print(f"Categories scored: {len(parsed)}/{len(scores_dict)}")
    if overall is None:
        print(f"OVERALL RISK SCORE: n/a (at least {MIN_SCORED_CATEGORIES} scored categories needed)")
    else:
        print(f"OVERALL RISK SCORE: {overall}/100  —  {risk_level(overall / 10).upper()} RISK")
    print("="*50)
    print(f"\nEXECUTIVE SUMMARY:\n{summary}")
    print("\n" + "="*50)

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")  # reasons quote dashes from the filings
    vectorstore = load_vectorstore()
    overall, scores_dict, summary, read_from, _ = run_risk_analysis(
        vectorstore, ticker="AAPL", company_name="Apple Inc.")
    print_risk_report("Apple Inc.", overall, scores_dict, summary, read_from)
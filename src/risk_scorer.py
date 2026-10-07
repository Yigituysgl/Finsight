import re
from collections import Counter
from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL, LLM_TEMPERATURE
from rag import load_vectorstore
from sections import SHORT_UNRESOLVED

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

# When a filing's Item 7A is a pointer that could not be resolved, categories
# that read 7A also read Item 7, where the market risk discussion usually is.
FALLBACK_ITEM_7_CHUNKS = 2

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

def describe_read_from(docs):
    """E.g. "Item 7A ×2, Item 8 ×1", in retrieval order."""
    counts = Counter(doc.metadata["section"] for doc in docs)
    return ", ".join(f"Item {section} ×{n}" for section, n in counts.items())

def score_category(category_name, docs):
    if not docs:
        return None, "No text found in the Items this category reads"
    context = "\n\n".join(f"[Item {doc.metadata['section']}]\n{doc.page_content}" for doc in docs)

    prompt = f"""You are a financial risk analyst.
Analyze the following text and score the {category_name} on a scale of 1-10.
1-3 = LOW risk, 4-6 = MEDIUM risk, 7-10 = HIGH risk
If the text does not contain enough information to assess this risk, answer
SCORE: INSUFFICIENT and use REASON to say what is missing.

TEXT:
{context}

Respond in exactly this format:
SCORE: [number 1-10, or INSUFFICIENT]
REASON: [one sentence explanation]"""

    client   = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=LLM_TEMPERATURE,
        max_tokens=SCORE_MAX_TOKENS
    )

    return parse_score_response(response.choices[0].message.content or "")

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

def get_risk_level(score):
    if score <= 3:   return "LOW"
    elif score <= 6: return "MEDIUM"
    else:            return "HIGH"

def generate_summary(scores_dict, overall_score, vectorstore, ticker):
    if overall_score is None:
        return "No risk category could be scored, so no summary was generated."

    docs    = retrieve(vectorstore, ticker, "financial performance risk outlook", {"7": 3})
    context = "\n\n".join([doc.page_content for doc in docs])
    scores_text = "\n".join([
        f"- {cat}: {score}/10 ({get_risk_level(score)})" if score is not None
        else f"- {cat}: n/a (could not be scored)"
        for cat, (score, _) in scores_dict.items()
    ])

    prompt = f"""You are a senior financial analyst.
Individual risk scores:
{scores_text}
Overall risk score: {overall_score}/100

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
    """Return ({category: (score, reason)}, {category: "Item 7A ×2, ..."})."""
    scores_dict, read_from = {}, {}
    item_7a = item_7a_source(vectorstore, ticker)
    print(f"  Item 7A text: {item_7a}")

    for category, spec in RISK_CATEGORIES.items():
        print(f"  Scoring {category}...")
        docs                  = retrieve(vectorstore, ticker, spec["query"],
                                         section_quotas(category, item_7a))
        scores_dict[category] = score_category(category, docs)
        read_from[category]   = describe_read_from(docs)
    return scores_dict, read_from

def run_risk_analysis(vectorstore, ticker, company_name):
    print(f"\n=== FinSight Risk Analysis: {company_name} ===\n")
    scores_dict, read_from = score_categories(vectorstore, ticker)

    # Unparsed categories (score None) are left out of the overall score
    # instead of being counted as a default value.
    parsed  = [score for score, _ in scores_dict.values() if score is not None]
    overall = round(sum(parsed) / (10 * len(parsed)) * 100) if parsed else None

    print("\n" + "="*50)
    print(f"RISK RESULTS: {company_name}")
    print("="*50)

    for category, (score, reason) in scores_dict.items():
        if score is None:
            print(f"\n{category:20} n/a")
        else:
            level = get_risk_level(score)
            bar   = "█" * score + "░" * (10 - score)
            print(f"\n{category:20} {score}/10  [{level}]")
            print(f"  {bar}")
        print(f"  {reason}")
        print(f"  Read from: {read_from[category] or 'nothing'}")

    print("\n" + "="*50)
    print(f"Categories scored: {len(parsed)}/{len(scores_dict)}")
    if overall is None:
        print("OVERALL RISK SCORE: n/a")
    else:
        print(f"OVERALL RISK SCORE: {overall}/100  —  {get_risk_level(overall//10)} RISK")
    print("="*50)

    print("\nGenerating executive summary...")
    summary = generate_summary(scores_dict, overall, vectorstore, ticker)
    print(f"\nEXECUTIVE SUMMARY:\n{summary}")
    print("\n" + "="*50)

    return overall, scores_dict, summary, read_from

if __name__ == "__main__":
    vectorstore = load_vectorstore()
    run_risk_analysis(vectorstore, ticker="AAPL", company_name="Apple Inc.")
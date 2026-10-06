import re
from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL, LLM_TEMPERATURE
from rag import load_vectorstore

# gpt-oss is a reasoning model: its reasoning tokens count against
# max_tokens, so the limits must leave room for reasoning plus the answer.
SCORE_MAX_TOKENS   = 1024
SUMMARY_MAX_TOKENS = 1024

# "SCORE: 7", "SCORE: [7]", "SCORE: 7/10". Decimals such as "7.5" are
# rejected rather than truncated.
SCORE_LINE  = re.compile(r"^\s*SCORE\s*:\s*\[?\s*(\d+)(?!\d|\.\d)", re.IGNORECASE | re.MULTILINE)
REASON_LINE = re.compile(r"^\s*REASON\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

RISK_CATEGORIES = {
    "Liquidity Risk":    ["cash flow", "debt", "liquidity", "borrowing"],
    "Revenue Risk":      ["revenue decline", "net sales decrease", "demand weakness"],
    "Legal Risk":        ["litigation", "lawsuit", "regulatory", "investigation"],
    "Market Risk":       ["competition", "market share", "interest rate", "foreign exchange"],
    "Operational Risk":  ["supply chain", "operating costs", "workforce", "disruption"],
    "Guidance Risk":     ["outlook", "forward looking", "uncertainty", "risk factors"]
}

def score_category(category_name, search_terms, vectorstore, ticker):
    query   = " ".join(search_terms[:3])
    docs    = vectorstore.similarity_search(query, k=3, filter={"ticker": ticker})
    context = "\n\n".join([doc.page_content for doc in docs])

    prompt = f"""You are a financial risk analyst.
Analyze the following text and score the {category_name} on a scale of 0-10.
0-3 = LOW risk, 4-6 = MEDIUM risk, 7-10 = HIGH risk

TEXT:
{context}

Respond in exactly this format:
SCORE: [number 0-10]
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
    """Return (score, reason). score is None when no valid 0-10 integer is found."""
    text         = raw.replace("*", "")  # tolerate markdown bold: **SCORE:** 7
    score_match  = SCORE_LINE.search(text)
    reason_match = REASON_LINE.search(text)

    score = int(score_match.group(1)) if score_match else None
    if score is None or not 0 <= score <= 10:
        return None, "Could not parse model response"

    reason = reason_match.group(1).strip() if reason_match else "No reason given"
    return score, reason

def get_risk_level(score):
    if score <= 3:   return "LOW"
    elif score <= 6: return "MEDIUM"
    else:            return "HIGH"

def generate_summary(scores_dict, overall_score, vectorstore, ticker):
    if overall_score is None:
        return "No risk category could be scored, so no summary was generated."

    docs    = vectorstore.similarity_search("financial performance risk outlook", k=3,
                                            filter={"ticker": ticker})
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

def run_risk_analysis(vectorstore, ticker, company_name):
    print(f"\n=== FinSight Risk Analysis: {company_name} ===\n")
    scores_dict = {}

    for category, terms in RISK_CATEGORIES.items():
        print(f"  Scoring {category}...")
        score, reason         = score_category(category, terms, vectorstore, ticker)
        scores_dict[category] = (score, reason)

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
            print(f"  {reason}")
            continue
        level = get_risk_level(score)
        bar   = "█" * score + "░" * (10 - score)
        print(f"\n{category:20} {score}/10  [{level}]")
        print(f"  {bar}")
        print(f"  {reason}")

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

    return overall, scores_dict, summary

if __name__ == "__main__":
    vectorstore = load_vectorstore()
    run_risk_analysis(vectorstore, ticker="AAPL", company_name="Apple Inc.")
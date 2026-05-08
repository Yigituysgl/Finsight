import os
from dotenv import load_dotenv
from groq import Groq
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

load_dotenv("../.env")
<<<<<<< HEAD
=======
import streamlit as st
if "GROQ_API_KEY" in st.secrets:
    os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
>>>>>>> fresh

VECTORSTORE_DIR = "../vectorstore"
EMBED_MODEL     = "all-MiniLM-L6-v2"
GROQ_MODEL      = "llama-3.3-70b-versatile"

RISK_CATEGORIES = {
    "Liquidity Risk":    ["cash flow", "debt", "liquidity", "borrowing"],
    "Revenue Risk":      ["revenue decline", "net sales decrease", "demand weakness"],
    "Legal Risk":        ["litigation", "lawsuit", "regulatory", "investigation"],
    "Market Risk":       ["competition", "market share", "interest rate", "foreign exchange"],
    "Operational Risk":  ["supply chain", "operating costs", "workforce", "disruption"],
    "Guidance Risk":     ["outlook", "forward looking", "uncertainty", "risk factors"]
}

def load_vectorstore():
    embeddings  = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectorstore = Chroma(
        persist_directory=VECTORSTORE_DIR,
        embedding_function=embeddings
    )
    return vectorstore

def score_category(category_name, search_terms, vectorstore):
    query   = " ".join(search_terms[:3])
    docs    = vectorstore.similarity_search(query, k=3)
    context = "\n\n".join([doc.page_content for doc in docs])

    prompt = f"""You are a financial risk analyst.
Analyze the following text and score the {category_name} on a scale of 0-10.
0-3 = LOW risk, 4-6 = MEDIUM risk, 7-10 = HIGH risk

TEXT:
{context}

Respond in exactly this format:
SCORE: [number 0-10]
REASON: [one sentence explanation]"""

    client   = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=150
    )

    raw    = response.choices[0].message.content.strip()
    score  = 5
    reason = "Could not parse response"

    for line in raw.split("\n"):
        if line.startswith("SCORE:"):
            try:
                score = int(line.replace("SCORE:", "").strip())
            except:
                score = 5
        if line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()

    return score, reason

def get_risk_level(score):
    if score <= 3:   return "LOW"
    elif score <= 6: return "MEDIUM"
    else:            return "HIGH"

def generate_summary(scores_dict, overall_score, vectorstore):
    docs    = vectorstore.similarity_search("financial performance risk outlook", k=3)
    context = "\n\n".join([doc.page_content for doc in docs])
    scores_text = "\n".join([
        f"- {cat}: {score}/10 ({get_risk_level(score)})"
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

    client   = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=300
    )
    return response.choices[0].message.content.strip()

def run_risk_analysis(vectorstore, company_name="Company"):
    print(f"\n=== FinSight Risk Analysis: {company_name} ===\n")
    scores_dict = {}
    total_score = 0

    for category, terms in RISK_CATEGORIES.items():
        print(f"  Scoring {category}...")
        score, reason         = score_category(category, terms, vectorstore)
        scores_dict[category] = (score, reason)
        total_score          += score

    overall = round((total_score / 60) * 100)

    print("\n" + "="*50)
    print(f"RISK RESULTS: {company_name}")
    print("="*50)

    for category, (score, reason) in scores_dict.items():
        level = get_risk_level(score)
        bar   = "█" * score + "░" * (10 - score)
        print(f"\n{category:20} {score}/10  [{level}]")
        print(f"  {bar}")
        print(f"  {reason}")

    print("\n" + "="*50)
    print(f"OVERALL RISK SCORE: {overall}/100  —  {get_risk_level(overall//10)} RISK")
    print("="*50)

    print("\nGenerating executive summary...")
    summary = generate_summary(scores_dict, overall, vectorstore)
    print(f"\nEXECUTIVE SUMMARY:\n{summary}")
    print("\n" + "="*50)

    return overall, scores_dict, summary

if __name__ == "__main__":
    vectorstore = load_vectorstore()
    run_risk_analysis(vectorstore, company_name="Apple Q4 2024")
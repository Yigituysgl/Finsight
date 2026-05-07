import os
import sys
from dotenv import load_dotenv
from groq import Groq

load_dotenv("../.env")
import streamlit as st
if "GROQ_API_KEY" in st.secrets:
    os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]


from ingest import extract_text_from_pdfs, chunk_documents, build_vectorstore
from rag import load_vectorstore, ask
from risk_scorer import run_risk_analysis

GROQ_MODEL = "llama-3.3-70b-versatile"

def classify_intent(user_input):
    """
    Uses LLaMA to classify what the user wants to do.
    Returns one of: 'qa', 'risk', 'ingest', 'unknown'
    
    Why use LLM for this instead of keywords?
    Because users don't type exact keywords. They say things like
    'can you check how risky this company is?' or 'tell me about revenue'
    and the LLM understands both perfectly.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    prompt = f"""Classify the following user request into exactly one category.

Categories:
- qa: user wants to ask a question about the financial document
- risk: user wants a risk analysis or risk score
- ingest: user wants to load or process a new PDF document
- unknown: request is unclear or unrelated

User request: "{user_input}"

Respond with ONLY the category word, nothing else."""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=10
    )
    
    intent = response.choices[0].message.content.strip().lower()
    
    
    for valid in ["qa", "risk", "ingest", "unknown"]:
        if valid in intent:
            return valid
    return "unknown"

def run_agent(user_input, vectorstore=None, company_name="Company"):
    """
    Main agent function. Takes user input, classifies intent,
    routes to the correct tool, returns the result.
    
    This is the core of what makes this an 'agent' rather than
    just a script — it makes a decision before acting.
    """
    print(f"\n[Agent] Received: '{user_input}'")
    
    
    intent = classify_intent(user_input)
    print(f"[Agent] Intent classified as: '{intent}'")
    
    
    if intent == "qa":
        if vectorstore is None:
            return "No document loaded. Please ingest a PDF first."
        print("[Agent] Routing to: Q&A tool")
        answer, sources = ask(user_input, vectorstore)
        return f"{answer}\n\nSource: {sources}"
    
    elif intent == "risk":
        if vectorstore is None:
            return "No document loaded. Please ingest a PDF first."
        print("[Agent] Routing to: Risk Scorer")
        overall, scores_dict, summary = run_risk_analysis(
            vectorstore, 
            company_name=company_name
        )
        return f"Risk Score: {overall}/100\n\n{summary}"
    
    elif intent == "ingest":
        print("[Agent] Routing to: Ingestion Pipeline")
        pdf_dir = "../data"
        documents = extract_text_from_pdfs(pdf_dir)
        chunks    = chunk_documents(documents)
        vs        = build_vectorstore(chunks)
        return f"Ingested {len(chunks)} chunks. Knowledge base ready.", vs
    
    else:
        return ("I can help you with:\n"
                "- Answering questions about the financial document\n"
                "- Running a risk analysis\n"
                "- Loading a new PDF document\n"
                "What would you like to do?")

def interactive_session():
    """
    Runs an interactive chat session with the agent.
    This is the prototype of the Streamlit chat we build on Day 5.
    """
    print("\n" + "="*55)
    print("  FinSight AI Financial Analyst Agent")
    print("="*55)
    print("Commands: ask questions, 'risk analysis', 'quit'")
    print("="*55)
    
    
    print("\n[Agent] Loading knowledge base...")
    try:
        vectorstore  = load_vectorstore()
        company_name = "Apple Q4 2024"
        print(f"[Agent] Knowledge base loaded — {company_name}")
    except Exception as e:
        print(f"[Agent] No knowledge base found: {e}")
        vectorstore  = None
        company_name = "Company"
    
    print("\nReady! Type your question below.\n")
    
    while True:
        user_input = input("You: ").strip()
        
        if not user_input:
            continue
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        
        result = run_agent(
            user_input, 
            vectorstore=vectorstore,
            company_name=company_name
        )
        
        # run_agent returns tuple when ingesting new docs
        if isinstance(result, tuple):
            message, vectorstore = result
            print(f"\nAgent: {message}\n")
        else:
            print(f"\nAgent: {result}\n")
        
        print("-" * 55)

if __name__ == "__main__":
    interactive_session()
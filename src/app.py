import os
import sys
import streamlit as st
import plotly.graph_objects as go

sys.path.append(os.path.dirname(__file__))

from config import GROQ_MODEL, VECTORSTORE_DIR
from fetch_filings import load_filings
from rag import load_vectorstore, has_documents, ask, source_label
from risk_scorer import run_risk_analysis


st.set_page_config(
    page_title="FinSight AI",
    page_icon="📊",
    layout="wide"
)


st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f77b4;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .risk-box {
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .low-risk    { background-color: #d4edda; color: #155724; }
    .medium-risk { background-color: #fff3cd; color: #856404; }
    .high-risk   { background-color: #f8d7da; color: #721c24; }
    .na-risk     { background-color: #e2e3e5; color: #383d41; }
    .chat-message {
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .user-message  { background-color: #e3f2fd; }
    .agent-message { background-color: #f5f5f5; }
    .source-text   { font-size: 0.8rem; color: #888; font-style: italic; }
</style>
""", unsafe_allow_html=True)


if "vectorstore"   not in st.session_state:
    st.session_state.vectorstore   = None
if "filing"        not in st.session_state:
    st.session_state.filing        = None
if "chat_history"  not in st.session_state:
    st.session_state.chat_history  = []
if "risk_results"  not in st.session_state:
    st.session_state.risk_results  = None
if "doc_processed" not in st.session_state:
    st.session_state.doc_processed = False


def create_gauge(score):
    color = "#28a745" if score < 40 else "#ffc107" if score < 70 else "#dc3545"
    fig = go.Figure(go.Indicator(
        mode  = "gauge+number",
        value = score,
        title = {"text": "Overall Risk Score", "font": {"size": 16}},
        gauge = {
            "axis": {"range": [0, 100]},
            "bar":  {"color": color},
            "steps": [
                {"range": [0,  40], "color": "#d4edda"},
                {"range": [40, 70], "color": "#fff3cd"},
                {"range": [70, 100],"color": "#f8d7da"},
            ]
        }
    ))
    fig.update_layout(height=250, margin=dict(t=40, b=10, l=20, r=20))
    return fig

def get_risk_color(score):
    if score is None: return "na-risk",    "⚪"
    if score <= 3:   return "low-risk",    "🟢 LOW"
    elif score <= 6: return "medium-risk", "🟡 MEDIUM"
    else:            return "high-risk",   "🔴 HIGH"

def filing_label(filing):
    return f"{filing['company']} ({filing['ticker']}) · {filing['form']} FY{filing['fiscal_year']}"


st.markdown('<p class="main-header">📊 FinSight AI</p>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-header">Financial Document Intelligence — {GROQ_MODEL} via Groq</p>',
            unsafe_allow_html=True)
st.divider()


col_left, col_main, col_right = st.columns([1, 2, 1])


with col_left:
    st.subheader("🏢 Company")

    if not st.session_state.doc_processed:
        # Loading a missing store would create an empty one on disk,
        # so only load when the directory exists and holds documents.
        vectorstore = load_vectorstore() if VECTORSTORE_DIR.exists() else None
        if vectorstore is not None and has_documents(vectorstore):
            st.session_state.vectorstore   = vectorstore
            st.session_state.doc_processed = True

    if st.session_state.doc_processed:
        # Offer only pinned filings that were actually ingested.
        filings = [f for f in load_filings()
                   if has_documents(st.session_state.vectorstore, f["ticker"])]
        filing = st.selectbox("Filing", filings, format_func=filing_label)
        if filing != st.session_state.filing:
            # Answers and scores belong to one company; start fresh on a switch.
            st.session_state.filing       = filing
            st.session_state.chat_history = []
            st.session_state.risk_results = None
    else:
        st.warning("Knowledge base is empty. Build it with "
                   "`python src/fetch_filings.py` and `python src/ingest.py`.")

    st.divider()

    
    if st.session_state.doc_processed:
        if st.button("🔍 Run Risk Analysis", type="secondary"):
            with st.spinner("Analyzing risk across 6 categories..."):
                overall, scores_dict, summary, read_from = run_risk_analysis(
                    st.session_state.vectorstore,
                    ticker=st.session_state.filing["ticker"],
                    company_name=st.session_state.filing["company"]
                )
                st.session_state.risk_results = {
                    "overall":     overall,
                    "scores_dict": scores_dict,
                    "summary":     summary,
                    "read_from":   read_from
                }
            st.success("Risk analysis complete!")

    st.divider()
    st.caption("Built with LangChain · ChromaDB · Groq · Streamlit")


with col_main:
    st.subheader("💬 Ask the AI Analyst")

    
    if st.session_state.doc_processed:
        user_input = st.chat_input(f"Ask about {st.session_state.filing['company']}'s 10-K...")
        if user_input:
            st.session_state.chat_history.append(
                {"role": "user", "content": user_input}
            )
            with st.spinner("Thinking..."):
                answer, sources = ask(user_input, st.session_state.vectorstore,
                                      st.session_state.filing["ticker"])
            st.session_state.chat_history.append({
                "role":    "assistant",
                "content": answer,
                "sources": sources
            })
            st.rerun()
    else:
        st.info("Build the knowledge base to start chatting.")

    
    if st.session_state.doc_processed and not st.session_state.chat_history:
        st.markdown("**Suggested questions:**")
        suggestions = [
            "What was the total revenue?",
            "How did net income change year over year?",
            "What are the main risk factors?",
            "What does management say about future outlook?"
        ]
        cols = st.columns(2)
        for i, suggestion in enumerate(suggestions):
            if cols[i % 2].button(suggestion, key=f"sug_{i}"):
                st.session_state.chat_history.append(
                    {"role": "user", "content": suggestion}
                )
                with st.spinner("Thinking..."):
                    answer, sources = ask(suggestion, st.session_state.vectorstore,
                                          st.session_state.filing["ticker"])
                st.session_state.chat_history.append({
                    "role":    "assistant",
                    "content": answer,
                    "sources": sources
                })
                st.rerun()

    
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["content"])
                for source in msg.get("sources", []):
                    st.caption(f"Source: [{source_label(source)}]({source['source_url']})")

with col_right:
    st.subheader("📈 Risk Dashboard")

    if st.session_state.risk_results:
        results      = st.session_state.risk_results
        overall      = results["overall"]
        scores_dict  = results["scores_dict"]
        summary      = results["summary"]

        
        failed = sum(1 for score, _ in scores_dict.values() if score is None)
        if overall is not None:
            st.plotly_chart(create_gauge(overall), use_container_width=True)
        else:
            st.error("No category could be scored, so there is no overall score.")
        if failed:
            st.warning(f"{failed} of {len(scores_dict)} categories could not be scored "
                       f"and are left out of the overall score.")


        st.markdown("**Category Breakdown:**")
        for category, (score, reason) in scores_dict.items():
            css_class, label = get_risk_color(score)
            short_name       = category.replace(" Risk", "")
            score_text       = "n/a" if score is None else f"{score}/10"
            st.markdown(
                f'<div class="risk-box {css_class}">'
                f'<b>{short_name}</b>: {score_text} {label}<br>'
                f'<small>{reason}</small></div>',
                unsafe_allow_html=True
            )
            st.caption(f"Read from: {results['read_from'][category] or 'nothing'}")

        
        st.divider()
        st.markdown("**Executive Summary:**")
        st.markdown(f"_{summary}_")

    else:
        st.info("Click 'Run Risk Analysis' to see the risk dashboard.")
        st.markdown("""
        **What you'll see:**
        - 📊 Overall risk gauge (0-100)
        - 6 category scores with explanations
        - Executive summary
        """)
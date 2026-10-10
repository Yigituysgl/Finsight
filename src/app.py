import html
import os
import sys
import streamlit as st
import plotly.graph_objects as go
from groq import RateLimitError

sys.path.append(os.path.dirname(__file__))

from config import GROQ_MODEL, VECTORSTORE_DIR
from fetch_filings import load_filings
from rag import (load_vectorstore, has_documents, ask, check_answer, display_citations,
                 rate_limit_message)
from risk_cache import load_results, save_results
from risk_scorer import run_risk_analysis, short_reason
from rubric import MIN_SCORED_CATEGORIES, risk_level


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
    .low-risk    { background-color: #d4edda; color: #155724; border-color: #28a745; }
    .medium-risk { background-color: #fff3cd; color: #856404; border-color: #ffc107; }
    .high-risk   { background-color: #f8d7da; color: #721c24; border-color: #dc3545; }
    .na-risk     { background-color: #e2e3e5; color: #383d41; border-color: #6c757d; }
    .risk-card {
        padding: 0.55rem 0.75rem;
        border-radius: 6px;
        border-left: 6px solid;
        margin: 0.6rem 0 0.25rem 0;
        line-height: 1.35;
    }
    .risk-card .card-head  { display: flex; justify-content: space-between; font-weight: 600; }
    .risk-card .card-score { font-size: 1.15rem; }
    .risk-card .card-line  { font-size: 0.82rem; margin-top: 0.2rem; }
    .overall-label { text-align: center; font-size: 1.05rem; font-weight: 600; margin-top: -0.5rem; }
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
if "llm_error"     not in st.session_state:
    st.session_state.llm_error     = None


LEVEL_COLORS = {"Low": "#28a745", "Medium": "#ffc107", "High": "#dc3545"}
LEVEL_CLASSES = {"Low": "low-risk", "Medium": "medium-risk", "High": "high-risk", None: "na-risk"}

def create_gauge(score):
    color = LEVEL_COLORS[risk_level(score / 10)]
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
    # Side margins leave room for the "0" and "100" axis labels in a narrow column.
    fig.update_layout(height=250, margin=dict(t=40, b=10, l=40, r=40))
    return fig

def escaped(text):
    """Model text for HTML: escaped, with "$" so amounts are not read as LaTeX."""
    return html.escape(text).replace("$", "&#36;")

def risk_card(category, score, reason):
    level = risk_level(score)
    score_text = "n/a" if score is None else f"{score}/10 · {level}"
    return (f'<div class="risk-card {LEVEL_CLASSES[level]}">'
            f'<div class="card-head"><span>{category.replace(" Risk", "")}</span>'
            f'<span class="card-score">{score_text}</span></div>'
            f'<div class="card-line">{escaped(short_reason(reason))}</div></div>')

def run_and_cache_risk(filing):
    """Run the analysis, cache it for the filing, and keep it in the session.
    A Groq rate limit leaves the previous result in place and explains why."""
    try:
        with st.spinner("Analyzing risk across 6 categories..."):
            overall, scores_dict, summary, read_from, evidence = run_risk_analysis(
                st.session_state.vectorstore, ticker=filing["ticker"],
                company_name=filing["company"])
    except RateLimitError as error:
        st.session_state.llm_error = rate_limit_message(error)
        return
    results = {"overall": overall, "scores_dict": scores_dict, "summary": summary,
               "read_from": read_from, "evidence": evidence}
    save_results(filing, results, source="App run")
    st.session_state.risk_results = load_results(filing)

def filing_label(filing):
    return f"{filing['company']} ({filing['ticker']}) · {filing['form']} FY{filing['fiscal_year']}"

def ask_and_record(question):
    st.session_state.chat_history.append({"role": "user", "content": question})
    try:
        with st.spinner("Thinking..."):
            answer, passages = ask(question, st.session_state.vectorstore,
                                   st.session_state.filing["ticker"])
    except RateLimitError as error:
        st.session_state.chat_history.pop()
        st.session_state.llm_error = rate_limit_message(error)
        return
    st.session_state.chat_history.append({
        "role":     "assistant",
        "content":  answer,
        "passages": passages,
        "check":    check_answer(answer, passages),
    })

def show_check(check):
    """Warnings from check_answer; "≈" ratios from risk scoring are shown as
    the model's own approximations, not as unverified figures."""
    if check["invalid_citations"]:
        st.warning("Cited passages that do not exist: "
                   + ", ".join(f"[{n}]" for n in check["invalid_citations"]))
    if check["unverified_figures"]:
        st.warning("Not found in the cited passages, check against the filing: "
                   + ", ".join(check["unverified_figures"]).replace("$", r"\$"))
    if check.get("approximate_ratios"):
        st.caption("Approximate ratio (computed by the model): "
                   + ", ".join(check["approximate_ratios"]))

def show_answer(msg):
    # Markdown reads "$...$" as LaTeX; answers are full of dollar amounts.
    st.markdown(display_citations(msg["content"]).replace("$", r"\$"))
    show_check(msg["check"])
    for passage in msg["passages"]:
        if passage["cited"]:
            with st.expander(f"[{passage['n']}] {passage['label']}"):
                st.markdown(f"[Open the filing on sec.gov]({passage['source_url']})")
                st.code(passage["text"], language=None, wrap_lines=True)
    uncited = [p for p in msg["passages"] if not p["cited"]]
    if uncited:
        with st.expander(f"Also retrieved ({len(uncited)})"):
            for passage in uncited:
                st.markdown(f"[{passage['n']}] [{passage['label']}]({passage['source_url']})")


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
            # A filing's last risk analysis is shown again without new model calls.
            st.session_state.risk_results = load_results(filing)
    else:
        st.warning("Knowledge base is empty. Build it with "
                   "`python src/fetch_filings.py` and `python src/ingest.py`.")

    st.divider()

    
    if st.session_state.doc_processed:
        label = "🔄 Re-run analysis" if st.session_state.risk_results else "🔍 Run Risk Analysis"
        if st.button(label, type="secondary"):
            run_and_cache_risk(st.session_state.filing)

    st.divider()
    st.caption("Built with LangChain · ChromaDB · Groq · Streamlit")


with col_main:
    st.subheader("💬 Ask the AI Analyst")
    if st.session_state.llm_error:
        st.warning(st.session_state.llm_error)
        st.session_state.llm_error = None

    
    if st.session_state.doc_processed:
        user_input = st.chat_input(f"Ask about {st.session_state.filing['company']}'s 10-K...")
        if user_input:
            ask_and_record(user_input)
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
                ask_and_record(suggestion)
                st.rerun()

    
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                show_answer(msg)

with col_right:
    st.subheader("📈 Risk Dashboard")

    if st.session_state.risk_results:
        results     = st.session_state.risk_results
        overall     = results["overall"]
        scores_dict = results["scores_dict"]
        scored      = sum(1 for score, _ in scores_dict.values() if score is not None)

        if overall is not None:
            st.plotly_chart(create_gauge(overall), use_container_width=True)
            level = risk_level(overall / 10)
            st.markdown(f'<div class="overall-label" style="color:{LEVEL_COLORS[level]}">'
                        f'{level} risk</div>', unsafe_allow_html=True)
        else:
            st.error(f"No overall score: only {scored} of {len(scores_dict)} categories "
                     f"could be scored (at least {MIN_SCORED_CATEGORIES} needed).")
        if overall is not None and scored < len(scores_dict):
            st.caption(f"{len(scores_dict) - scored} of {len(scores_dict)} categories could not "
                       f"be scored and are left out of the overall score.")
        st.caption(f"{results['source']}, {results['created']}")

        for category, (score, reason) in scores_dict.items():
            st.markdown(risk_card(category, score, reason), unsafe_allow_html=True)
            evidence = results["evidence"][category]
            with st.expander("Details"):
                st.markdown(escaped(display_citations(reason)), unsafe_allow_html=True)
                st.caption(f"Read from: {results['read_from'][category] or 'nothing'}")
                if evidence["check"]:
                    show_check(evidence["check"])
                for passage in (p for p in evidence["passages"] if p["cited"]):
                    st.markdown(f"**[{passage['n']}] {passage['label']}** · "
                                f"[filing on sec.gov]({passage['source_url']})")
                    st.code(passage["text"], language=None, wrap_lines=True)

        if results.get("summary"):
            st.divider()
            st.markdown("**Executive Summary:**")
            summary = display_citations(results["summary"])
            st.markdown(f"_{summary.replace('$', chr(92) + '$')}_")

    else:
        st.info("Click 'Run Risk Analysis' to see the risk dashboard.")
        st.markdown("""
        **What you'll see:**
        - 📊 Overall risk gauge (0-100)
        - 6 category scores with explanations
        - Executive summary
        """)

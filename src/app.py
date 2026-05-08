import os
import sys
import streamlit as st
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv("../.env")
sys.path.append(os.path.dirname(__file__))

from ingest import extract_text_from_pdfs, chunk_documents, build_vectorstore
from rag import load_vectorstore, ask
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
if "company_name"  not in st.session_state:
    st.session_state.company_name  = "Company"
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
    if score <= 3:   return "low-risk",    "🟢 LOW"
    elif score <= 6: return "medium-risk", "🟡 MEDIUM"
    else:            return "high-risk",   "🔴 HIGH"

def process_uploaded_file(uploaded_file, company_name):


    with st.spinner("Creating knowledge base..."):
        chunks      = chunk_documents(documents)
        vectorstore = build_vectorstore(chunks)

    st.session_state.vectorstore   = vectorstore
    st.session_state.company_name  = company_name
    st.session_state.doc_processed = True
    st.session_state.chat_history  = []
    st.session_state.risk_results  = None
    return vectorstore


st.markdown('<p class="main-header">📊 FinSight AI</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Financial Document Intelligence — Powered by LLaMA 3.3 70B</p>',
            unsafe_allow_html=True)
st.divider()


col_left, col_main, col_right = st.columns([1, 2, 1])


with col_left:
    st.subheader("📁 Document")

    company_name = st.text_input(
        "Company name",
        value="Apple Q4 2024",
        placeholder="e.g. Tesla 2024"
    )

    uploaded_file = st.file_uploader(
        "Upload financial PDF",
        type=["pdf"],
        help="Upload any financial report, 10-K, 10-Q, or annual report"
    )

    if uploaded_file and st.button("Process Document", type="primary"):
        with st.spinner("Processing..."):
            process_uploaded_file(uploaded_file, company_name)
        st.success(f"Document ready!")

    
    if not st.session_state.doc_processed:
        try:
            st.session_state.vectorstore   = load_vectorstore()
            st.session_state.company_name  = company_name
            st.session_state.doc_processed = True
            st.info("Existing knowledge base loaded!")
        except:
            st.warning("Upload a PDF to get started.")

    st.divider()

    
    if st.session_state.doc_processed:
        if st.button("🔍 Run Risk Analysis", type="secondary"):
            with st.spinner("Analyzing risk across 6 categories..."):
                overall, scores_dict, summary = run_risk_analysis(
                    st.session_state.vectorstore,
                    company_name=st.session_state.company_name
                )
                st.session_state.risk_results = {
                    "overall":     overall,
                    "scores_dict": scores_dict,
                    "summary":     summary
                }
            st.success("Risk analysis complete!")

    st.divider()
    st.caption("Built with LangChain · ChromaDB · Groq · Streamlit")


with col_main:
    st.subheader("💬 Ask the AI Analyst")

    
    if st.session_state.doc_processed:
        user_input = st.chat_input("Ask about the financial document...")
        if user_input:
            st.session_state.chat_history.append(
                {"role": "user", "content": user_input}
            )
            with st.spinner("Thinking..."):
                answer, sources = ask(user_input, st.session_state.vectorstore)
            st.session_state.chat_history.append({
                "role":    "assistant",
                "content": answer,
                "source":  str(sources)
            })
            st.rerun()
    else:
        st.info("Upload and process a document to start chatting.")

    
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
                    answer, sources = ask(suggestion, st.session_state.vectorstore)
                st.session_state.chat_history.append({
                    "role":    "assistant",
                    "content": answer,
                    "source":  str(sources)
                })
                st.rerun()

    
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["content"])
                if "source" in msg:
                    st.caption(f"Source: {msg['source']}")

with col_right:
    st.subheader("📈 Risk Dashboard")

    if st.session_state.risk_results:
        results      = st.session_state.risk_results
        overall      = results["overall"]
        scores_dict  = results["scores_dict"]
        summary      = results["summary"]

        
        st.plotly_chart(create_gauge(overall), use_container_width=True)

        
        st.markdown("**Category Breakdown:**")
        for category, (score, reason) in scores_dict.items():
            css_class, label = get_risk_color(score)
            short_name       = category.replace(" Risk", "")
            st.markdown(
                f'<div class="risk-box {css_class}">'
                f'<b>{short_name}</b>: {score}/10 {label}<br>'
                f'<small>{reason}</small></div>',
                unsafe_allow_html=True
            )

        
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
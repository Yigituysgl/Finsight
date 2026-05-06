# 📊 FinSight AI — Financial Document Intelligence

> An end-to-end RAG-based financial risk analysis platform powered by LLaMA 3.3 70B.
> Upload any financial PDF and get instant AI-generated risk scores, Q&A, and executive summaries.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![LangChain](https://img.shields.io/badge/LangChain-0.4-green)
![Streamlit](https://img.shields.io/badge/Streamlit-1.x-red)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🎯 What is FinSight?

FinSight is an AI-powered financial analyst that reads real SEC filings, annual reports,
and quarterly documents — then answers questions and scores risk automatically.

**No more reading 200-page financial reports manually.**

---

## ✨ Features

- **📄 Universal Document Support** — Upload any financial PDF (10-K, 10-Q, annual reports)
- **💬 AI Q&A Chat** — Ask questions in plain English, get cited answers from the document
- **📊 Risk Scoring Engine** — Automatic 0-100 risk score across 6 categories
- **🤖 LLM-Powered Analysis** — LLaMA 3.3 70B via Groq for fast, accurate responses
- **🔍 Semantic Search** — ChromaDB vector store for intelligent document retrieval
- **📈 Interactive Dashboard** — Plotly gauge charts and color-coded risk breakdown
- **🏢 Multi-Company Support** — Switch between any company's documents instantly

---

## 🏗️ Architecture

Financial PDF
↓
PyMuPDF (text extraction)
↓
RecursiveCharacterTextSplitter (chunking)
↓
HuggingFace Embeddings (all-MiniLM-L6-v2)
↓
ChromaDB (vector storage)
↓
Semantic Search (retrieval)
↓
Groq LLaMA 3.3 70B (generation)
↓
Streamlit Dashboard (presentation)
---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| LLM | LLaMA 3.3 70B via Groq API |
| Embeddings | HuggingFace all-MiniLM-L6-v2 |
| Vector DB | ChromaDB |
| RAG Framework | LangChain |
| Frontend | Streamlit |
| Charts | Plotly |
| PDF Parsing | PyMuPDF |

---

## 📁 Project Structure

finsight/
├── src/
│   ├── app.py           # Streamlit dashboard (main UI)
│   ├── ingest.py        # PDF ingestion pipeline
│   ├── rag.py           # RAG Q&A engine
│   ├── risk_scorer.py   # 6-category risk scoring
│   └── agent.py         # Intent classification agent
├── data/                # Financial PDFs (not committed)
├── vectorstore/         # ChromaDB storage (not committed)
├── .env                 # API keys (not committed)
├── requirements.txt
└── README.md

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/Yigituysgl/finsight.git
cd finsight
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Mac/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up API key
```bash
# Create .env file in root folder
echo GROQ_API_KEY=your_groq_api_key_here > .env
```
Get your free Groq API key at: https://console.groq.com

### 5. Run the app
```bash
cd src
streamlit run app.py
```

### 6. Use FinSight
- Upload any financial PDF (10-K, 10-Q, annual report)
- Ask questions in the chat interface
- Click "Run Risk Analysis" for the full risk dashboard

---

## 📊 Risk Scoring Categories

| Category | What it measures |
|----------|-----------------|
| 🟢 Liquidity Risk | Cash flow, debt levels, credit access |
| 🔴 Revenue Risk | Sales decline, demand weakness |
| 🔴 Legal Risk | Litigation, regulatory exposure |
| 🟡 Market Risk | Competition, FX, interest rates |
| 🔴 Operational Risk | Supply chain, workforce, costs |
| 🔴 Guidance Risk | Forward-looking uncertainty |

---

## 💡 Example Results

**Apple Q4 2024 (10-Q):**
- Overall Risk Score: **67/100 — MEDIUM RISK**
- Highest risk: Revenue (8/10), Legal (8/10), Operational (8/10)
- Lowest risk: Liquidity (2/10) — $160B+ cash reserves

**Tesla 2025 (10-K):**
- Overall Risk Score: **63/100 — MEDIUM RISK**
- Total Revenue 2024: $391,035 million

---

## 🧠 How RAG Works

1. **Ingest** — PDF text is extracted and split into 500-character chunks
2. **Embed** — Each chunk is converted to a 384-dimensional vector
3. **Store** — Vectors saved in ChromaDB for persistent retrieval
4. **Retrieve** — User question is embedded and matched to top-k chunks
5. **Generate** — LLaMA reads the chunks and generates a cited answer

---

## 👤 Author

**Yigit Uysaloglu** — Data Scientist | Data Analyst
- LinkedIn: [linkedin.com/in/yigit-uysaloglu](https://linkedin.com/in/yigit-uysaloglu)
- GitHub: [github.com/Yigituysgl](https://github.com/Yigituysgl)
- Email: uysalogluyigit86@gmail.com

---

## 📄 License

MIT License — feel free to use and adapt this project.

---

*Built with LangChain · ChromaDB · Groq · Streamlit · Python*
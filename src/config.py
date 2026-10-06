import os
from pathlib import Path
from dotenv import load_dotenv

# Paths are anchored at the repository root, so the app works from any
# working directory (e.g. `streamlit run src/app.py` from the root).
ROOT_DIR        = Path(__file__).resolve().parent.parent
DATA_DIR        = ROOT_DIR / "data"
VECTORSTORE_DIR = ROOT_DIR / "vectorstore"

load_dotenv(ROOT_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Single sampling temperature for every LLM call (Q&A, risk scoring,
# summary). Evaluation scripts must read this value, not hardcode one.
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

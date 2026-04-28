import os
from dotenv import load_dotenv
from groq import Groq
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

load_dotenv("../.env")

VECTORSTORE_DIR = "../vectorstore"
EMBED_MODEL     = "all-MiniLM-L6-v2"
GROQ_MODEL      = "llama-3.3-70b-versatile"

def load_vectorstore():
    print("  Loading vector store from disk...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectorstore = Chroma(
        persist_directory=VECTORSTORE_DIR,
        embedding_function=embeddings
    )
    print("  Vector store loaded!")
    return vectorstore

def ask(question, vectorstore):
    docs = vectorstore.similarity_search(question, k=3)
    context = "\n\n".join([doc.page_content for doc in docs])
    sources  = list(set([doc.metadata.get("source","unknown") for doc in docs]))

    prompt = f"""You are a professional financial analyst AI assistant.
Use ONLY the context below to answer the question.
If the answer is not in the context, say "I could not find this information in the document."

CONTEXT:
{context}

QUESTION: {question}

Provide a clear, structured answer with specific numbers where available."""

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )

    answer = response.choices[0].message.content
    return answer, sources

if __name__ == "__main__":
    print("\n=== FinSight: Day 2 RAG Q&A ===\n")
    vectorstore = load_vectorstore()

    questions = [
        "What was Apple's total revenue?",
        "What are the main risk factors mentioned?",
        "How did net income change compared to last year?"
    ]

    for q in questions:
        print(f"\nQ: {q}")
        answer, sources = ask(q, vectorstore)
        print(f"A: {answer}")
        print(f"Source: {sources}")
        print("-" * 60)
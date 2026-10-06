from groq import Groq
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from config import (COLLECTION_NAME, EMBED_MODEL, GROQ_API_KEY, GROQ_MODEL,
                    LLM_TEMPERATURE, VECTORSTORE_DIR)

def load_vectorstore():
    print("  Loading vector store from disk...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(VECTORSTORE_DIR),
        embedding_function=embeddings
    )
    print("  Vector store loaded!")
    return vectorstore

def has_documents(vectorstore):
    return bool(vectorstore.get(limit=1)["ids"])

SOURCE_FIELDS = ["company", "form", "fiscal_year", "section", "section_title",
                 "resolved_from", "accession", "source_url"]

def source_label(source):
    """E.g. "Philip Morris International Inc. · 10-K FY2025 · Item 7A (Item 7, Market Risk)"."""
    item = f"Item {source['section']}"
    if source.get("resolved_from"):
        item += f" ({source['resolved_from']})"
    return f"{source['company']} · {source['form']} FY{source['fiscal_year']} · {item}"

def unique_sources(docs):
    """One entry per filing section, in retrieval order."""
    sources = []
    for doc in docs:
        source = {field: doc.metadata.get(field, "") for field in SOURCE_FIELDS}
        if source not in sources:
            sources.append(source)
    return sources

def ask(question, vectorstore):
    docs = vectorstore.similarity_search(question, k=3)
    context = "\n\n".join([doc.page_content for doc in docs])
    sources  = unique_sources(docs)

    prompt = f"""You are a professional financial analyst AI assistant.
Use ONLY the context below to answer the question.
If the answer is not in the context, say "I could not find this information in the document."

CONTEXT:
{context}

QUESTION: {question}

Provide a clear, structured answer with specific numbers where available."""

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=LLM_TEMPERATURE
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
        for source in sources:
            print(f"Source: {source_label(source)}")
        print("-" * 60)
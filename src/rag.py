from groq import Groq
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from config import (COLLECTION_NAME, EMBED_MODEL, GROQ_API_KEY, GROQ_MODEL,
                    LLM_TEMPERATURE, VECTORSTORE_DIR)
from sections import INCOME

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

def has_documents(vectorstore, ticker=None):
    where = {"ticker": ticker} if ticker else None
    return bool(vectorstore.get(where=where, limit=1)["ids"])

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

QA_K        = 3  # best matches anywhere in the selected filing
QA_ITEM_8_K = 1  # plus the best match from the financial statements

def chunk_key(doc):
    return (doc.metadata.get("accession"), doc.metadata.get("section"),
            doc.metadata.get("chunk_index"))

def income_statement(vectorstore, ticker):
    """The filing's income-statement chunks, in document order."""
    found = vectorstore.get(where={"$and": [{"ticker": ticker}, {"statement": INCOME}]})
    docs  = [Document(page_content=text, metadata=metadata)
             for text, metadata in zip(found["documents"], found["metadatas"])]
    return sorted(docs, key=lambda doc: doc.metadata["chunk_index"])

def retrieve_for_question(question, vectorstore, ticker):
    # Retrieve only from the selected company's filing, and always include
    # Item 8 so reported figures are in context even when MD&A ranks higher.
    # The income statement is always included too: otherwise a note table
    # with a similar line (e.g. equity investees' "Consolidated net income")
    # can be the only source of a headline figure.
    docs = vectorstore.similarity_search(question, k=QA_K, filter={"ticker": ticker})
    docs += vectorstore.similarity_search(
        question, k=QA_ITEM_8_K, filter={"$and": [{"ticker": ticker}, {"section": "8"}]})
    docs += income_statement(vectorstore, ticker)
    unique, seen = [], set()
    for doc in docs:
        if chunk_key(doc) not in seen:
            unique.append(doc)
            seen.add(chunk_key(doc))
    return unique

def ask(question, vectorstore, ticker):
    docs = retrieve_for_question(question, vectorstore, ticker)
    context = "\n\n".join([doc.page_content for doc in docs])
    sources  = unique_sources(docs)

    prompt = f"""You are a professional financial analyst AI assistant.
Use ONLY the context below to answer the question.
Use figures exactly as they are stated in the context. Never derive a figure by
calculating it from other figures, rounded or not. If a figure is not stated in
the context, say that it is not in the provided context.
When the answer covers several years, label each figure with its fiscal year.
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
        answer, sources = ask(q, vectorstore, "AAPL")
        print(f"A: {answer}")
        for source in sources:
            print(f"Source: {source_label(source)}")
        print("-" * 60)
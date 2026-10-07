from groq import Groq
from langchain_core.documents import Document
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

# Chunks on each side of a hit that are added to the context, so a table or
# argument cut at a chunk boundary is read whole. Off by default: it
# roughly triples the context, and a third Item 7A chunk for FX Risk already
# brings in the PM value-at-risk table, which ranks third in that Item.
NEIGHBOURS  = 0
MIN_OVERLAP = 20

def chunk_id(accession, section, index):
    return f"{accession}:{section}:{index}"

def strip_overlap(previous, text):
    """Drop the start of text that repeats the end of the chunk before it.
    Matches shorter than MIN_OVERLAP are taken as coincidence, not overlap."""
    for n in range(min(len(previous), len(text)), MIN_OVERLAP - 1, -1):
        if previous.endswith(text[:n]):
            return text[n:].lstrip()
    return text

def with_neighbours(docs, vectorstore):
    """Each hit with the chunks either side of it, in rank order of the hits
    and document order within each hit, without duplicates."""
    if not NEIGHBOURS:
        return docs
    wanted = []
    for doc in docs:
        accession, section, index = chunk_key(doc)
        for i in range(index - NEIGHBOURS, index + NEIGHBOURS + 1):
            key = (accession, section, i)
            if i >= 0 and key not in wanted:
                wanted.append(key)
    found = vectorstore.get(ids=[chunk_id(*key) for key in wanted])
    by_key = {(m["accession"], m["section"], m["chunk_index"]): (text, m)
              for text, m in zip(found["documents"], found["metadatas"])}

    expanded = []
    for key in wanted:
        if key not in by_key:
            continue  # before the first or after the last chunk of the Item
        text, metadata = by_key[key]
        previous = expanded[-1] if expanded else None
        if previous is not None and chunk_key(previous) == (key[0], key[1], key[2] - 1):
            text = strip_overlap(previous.page_content, text)
        expanded.append(Document(page_content=text, metadata=metadata))
    return expanded

def retrieve_for_question(question, vectorstore, ticker):
    # Retrieve only from the selected company's filing, and always include
    # Item 8 so reported figures are in context even when MD&A ranks higher.
    docs = vectorstore.similarity_search(question, k=QA_K, filter={"ticker": ticker})
    seen = {chunk_key(doc) for doc in docs}
    for doc in vectorstore.similarity_search(
            question, k=QA_ITEM_8_K, filter={"$and": [{"ticker": ticker}, {"section": "8"}]}):
        if chunk_key(doc) not in seen:
            docs.append(doc)
    return with_neighbours(docs, vectorstore)

def ask(question, vectorstore, ticker):
    docs = retrieve_for_question(question, vectorstore, ticker)
    context = "\n\n".join([doc.page_content for doc in docs])
    sources  = unique_sources(docs)

    prompt = f"""You are a professional financial analyst AI assistant.
Use ONLY the context below to answer the question.
Use figures exactly as they are stated in the context. Never derive a figure by
calculating it from other figures, rounded or not. If a figure is not stated in
the context, say that it is not in the provided context.
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
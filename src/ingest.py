import os
import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

PDF_DIR         = "../data"
VECTORSTORE_DIR = "../vectorstore"
CHUNK_SIZE      = 500
CHUNK_OVERLAP   = 50
EMBED_MODEL = "all-MiniLM-L6-v2"

def extract_text_from_pdfs(pdf_dir):
    documents = []
    for filename in os.listdir(pdf_dir):
        if not filename.endswith(".pdf"):
            continue
        filepath = os.path.join(pdf_dir, filename)
        doc = fitz.open(filepath)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        documents.append({"text": full_text, "source": filename})
        print(f"  Extracted {len(full_text):,} characters from '{filename}'")
    return documents

def chunk_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    all_chunks = []
    for doc in documents:
        chunks = splitter.split_text(doc["text"])
        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "text": chunk,
                "metadata": {"source": doc["source"], "chunk_id": i}
            })
    print(f"  Created {len(all_chunks)} chunks total")
    return all_chunks

def build_vectorstore(chunks):
    print("  Loading embedding model (first run downloads ~90MB)...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    texts     = [c["text"]     for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    print(f"  Embedding {len(texts)} chunks and saving to ChromaDB...")
    vectorstore = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        persist_directory=VECTORSTORE_DIR
    )
    print(f"  Done! Saved to '{VECTORSTORE_DIR}'")
    return vectorstore

def test_retrieval(vectorstore):
    test_queries = [
        "What was the total revenue?",
        "What are the main risk factors?",
        "How did operating expenses change?"
    ]
    print("\n  --- SEMANTIC SEARCH TEST ---")
    for query in test_queries:
        results = vectorstore.similarity_search(query, k=2)
        print(f"\n  Q: '{query}'")
        for i, doc in enumerate(results):
            source  = doc.metadata.get("source", "unknown")
            preview = doc.page_content[:120].replace("\n", " ")
            print(f"    [{i+1}] ({source}) {preview}...")

if __name__ == "__main__":
    print("\n=== FinSight: Day 1 Ingestion Pipeline ===\n")
    print("[1/4] Reading PDFs...")
    documents = extract_text_from_pdfs(PDF_DIR)
    print("\n[2/4] Chunking text...")
    chunks = chunk_documents(documents)
    print("\n[3/4] Building vector store...")
    vectorstore = build_vectorstore(chunks)
    print("\n[4/4] Testing semantic search...")
    test_retrieval(vectorstore)
    print("\n=== Day 1 Complete! ===")
    print(f"  Knowledge base saved in '{VECTORSTORE_DIR}'")
    print("  Tomorrow: connect to Groq LLM for real Q&A answers.\n")

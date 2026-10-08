import re
from decimal import Decimal

from groq import Groq
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from config import (COLLECTION_NAME, EMBED_MODEL, GROQ_API_KEY, GROQ_MODEL,
                    LLM_TEMPERATURE, VECTORSTORE_DIR)
from sections import BALANCE_SHEET, CASH_FLOW, INCOME

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

STATEMENT_NAMES = {INCOME: "Income statement", BALANCE_SHEET: "Balance sheet",
                   CASH_FLOW: "Cash flow statement"}

def passage_label(metadata):
    """source_label plus the primary statement the chunk belongs to, if any."""
    label = source_label(metadata)
    statement = STATEMENT_NAMES.get(metadata.get("statement", ""))
    return f"{label} · {statement}" if statement else label

def numbered_context(docs):
    """Each chunk as "[n] label", then its text; n counts from 1 in retrieval order."""
    return "\n\n".join(f"[{n}] {passage_label(doc.metadata)}\n{doc.page_content}"
                       for n, doc in enumerate(docs, 1))

# "[2]", "[1, 3]"; "[1][2]" is two citations. gpt-oss also writes its own
# full-width style, "【2】", sometimes with a line reference, "【1†L1-L3】".
CITATION = re.compile(r"[\[【](\d+(?:\s*,\s*\d+)*)(?:†[^\]】]*)?[\]】]")

def cited_numbers(answer):
    """Passage numbers the answer cites, in order of first citation."""
    numbers = []
    for group in CITATION.findall(answer):
        for n in map(int, group.split(",")):
            if n not in numbers:
                numbers.append(n)
    return numbers

def passages(docs, answer):
    """One entry per context passage: its number, label, source fields, text
    and whether the answer cites it."""
    cited = set(cited_numbers(answer))
    return [{**{field: doc.metadata.get(field, "") for field in SOURCE_FIELDS},
             "n": n, "label": passage_label(doc.metadata),
             "text": doc.page_content, "cited": n in cited}
            for n, doc in enumerate(docs, 1)]

# A number in an answer, with its "$" and "%" if any; not the tail of a word
# ("FY2025", "Q4") or part of a longer number.
ANSWER_NUMBER  = re.compile(r"(?<![\w.,])(\$\s*\(?)?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
                            r"(?!\d|[.,]\d)(\s*%)?")
PASSAGE_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
YEAR_NUMBER    = re.compile(r"(19|20)\d\d")

def number_value(text):
    return Decimal(text.replace(",", "")).normalize()

# A ratio the model computed itself is marked "≈ 2%" or "≈ 2.9x" (risk scoring).
RATIO_SUFFIX = re.compile(r"\s*[x×]")

def figure_matches(answer):
    """(figure, approximate) for each figure stated in the answer: numbers with a
    "$", "%", thousands separator or decimals, or of three or more digits. Plain
    years, citation markers and small counts ("Item 7", "3 years") are left out.
    approximate: a percentage or multiple marked with a preceding "≈"."""
    text, found = CITATION.sub("", answer), []
    for match in ANSWER_NUMBER.finditer(text):
        dollar, number, percent = match.groups()
        if not (dollar or percent or "," in number or "." in number or len(number) >= 3):
            continue
        if not (dollar or percent) and YEAR_NUMBER.fullmatch(number):
            continue
        multiple    = RATIO_SUFFIX.match(text, match.end())
        approximate = bool(percent or multiple) and text[:match.start()].rstrip().endswith("≈")
        figure      = match.group(0).strip() + (multiple.group(0).strip() if multiple else "")
        if (figure, approximate) not in found:
            found.append((figure, approximate))
    return found

def answer_figures(answer):
    figures = []
    for figure, _ in figure_matches(answer):
        if figure not in figures:
            figures.append(figure)
    return figures

def unverified_figures(answer, cited_passages, allow_approximate=False):
    """Figures in the answer whose value appears in none of the cited passages.
    Values are compared without "$", "%", signs or thousands separators, so
    "$11,348 million" matches a table cell "11,348". A warning only: a figure
    can appear in a cited passage on a different line than the answer implies.
    With allow_approximate, ratios marked "≈" are not checked."""
    values = {number_value(n) for p in cited_passages
              for n in PASSAGE_NUMBER.findall(p["text"])}
    figures = [figure for figure, approximate in figure_matches(answer)
               if not (allow_approximate and approximate)]
    return [figure for figure in dict.fromkeys(figures)
            if number_value(ANSWER_NUMBER.search(figure).group(2)) not in values]

def check_answer(answer, passages, allow_approximate=False):
    """Cited passage numbers, those that match no passage, and the answer's
    figures that are not in any cited passage. With allow_approximate (risk
    scoring), "≈" ratios are listed apart as approximate_ratios and not
    checked; Q&A answers may not derive figures, so they are checked."""
    cited = cited_numbers(answer)
    check = {"cited":              cited,
             "invalid_citations":  [n for n in cited if not 1 <= n <= len(passages)],
             "unverified_figures": unverified_figures(
                 answer, [p for p in passages if p["n"] in cited], allow_approximate)}
    if allow_approximate:
        check["approximate_ratios"] = list(dict.fromkeys(
            f"≈ {figure}" for figure, approximate in figure_matches(answer) if approximate))
    return check

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

def qa_prompt(context, question):
    return f"""You are a professional financial analyst AI assistant.
Use ONLY the context below to answer the question.
Use figures exactly as they are stated in the context. Never derive a figure by
calculating it from other figures, rounded or not. If a figure is not stated in
the context, say that it is not in the provided context.
When the answer covers several years, label each figure with its fiscal year.
For net income, report the figure attributable to the company itself (the
headline figure, the basis of earnings per share): the income-statement line
containing "attributable to" the company or its common stockholders or
shareowners, e.g. "Net income attributable to common stockholders",
"Net Income Attributable to Shareowners of The Coca-Cola Company",
"Net earnings attributable to PMI". Do not report the plain "Net income" or
"Net earnings" line above it as net income when such a line exists; that line
includes noncontrolling interests and may only be mentioned as a clearly
labelled secondary figure.
Take headline figures (total revenue, net income) from a passage labelled
"Income statement" whenever the context contains one. Never take them from
note tables about equity method investees, segments or related parties, even
when a line there has the same name (e.g. "Consolidated net income").
The context is a list of numbered passages. After every figure and every
statement taken from the context, cite the passage it comes from in square
brackets, e.g. [2] or [1, 3]. Cite only passage numbers that appear in the context.
If the answer is not in the context, say "I could not find this information in the document."

CONTEXT:
{context}

QUESTION: {question}

Provide a clear, structured answer with specific numbers where available."""

def ask(question, vectorstore, ticker):
    docs = retrieve_for_question(question, vectorstore, ticker)
    context = numbered_context(docs)
    prompt  = qa_prompt(context, question)

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=LLM_TEMPERATURE
    )

    answer = response.choices[0].message.content
    return answer, passages(docs, answer)

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")  # answers quote dashes from the filings
    print("\n=== FinSight: Day 2 RAG Q&A ===\n")
    vectorstore = load_vectorstore()

    questions = [
        "What was Apple's total revenue?",
        "What are the main risk factors mentioned?",
        "How did net income change compared to last year?"
    ]

    for q in questions:
        print(f"\nQ: {q}")
        answer, retrieved = ask(q, vectorstore, "AAPL")
        print(f"A: {answer}")
        for passage in retrieved:
            print(f"[{passage['n']}]{' (cited)' if passage['cited'] else ''} {passage['label']}")
        print("-" * 60)
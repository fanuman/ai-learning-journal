# Day 11 - LangChain fundamentals: rebuild RAG with framework abstractions

**Date completed:** _(fill in)_

## What I learned

**What LangChain actually is**
A Python library, not a service or infrastructure - runs inside your own script, calling the same
OpenAI/Chroma APIs you'd call directly. It doesn't do anything conceptually new; every piece of
today's `rag_chain` mapped one-to-one to code already written by hand in Project 2 (retriever ~=
`collection.query()`, `format_docs` ~= the `"\n\n".join()` line, `RunnablePassthrough()` ~= just
using the query variable as-is, `prompt` ~= the f-string in `build_prompt()`, `model` ~=
`client.chat.completions.create()`, `StrOutputParser()` ~= `.choices[0].message.content`).

**Runnables and the pipe operator**
Every LangChain component (prompt, model, parser, retriever, custom function) implements a shared
`Runnable` interface (`.invoke()`, `.stream()`, `.batch()`). The `|` operator is Python's normal
operator overloading (`__or__`) - not special LangChain syntax - redefined to mean "run the left
side, feed its output into the right side." `prompt | model | parser` is method chaining wearing
a different costume.

**The LCEL RAG chain, piece by piece**
```python
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | model | StrOutputParser()
)
```
The dict runs two branches in parallel on the same input: the question flows through
`retriever | format_docs` to produce labeled context text, and separately through
`RunnablePassthrough()` completely unchanged. Both results merge into one dict, which fills the
`prompt` template, gets sent to `model`, and `StrOutputParser()` extracts the plain text reply.

**Rebuilding ingestion - two real, free upgrades**
- `PyPDFLoader().load()` returns one `Document` per *page* with `source` and `page` already in
  metadata - genuine upgrade over Project 2's file-only source tracking, enabling precise
  page-level citations for free.
- `RecursiveCharacterTextSplitter.split_documents()` (vs `.split_text()`) carries metadata through
  the split automatically - no manual metadata-tagging loop needed.
- `Chroma.from_documents()` collapses embed + store into one call.

## Real bugs found and fixed (five today, more than any prior day)

**1. `glob.glob("data/*.pdf")` found 0 files.** Relative paths in Python resolve against the
current working directory, not the script's own location - running from the repo root looked for
`ai-learning-journal/data/` instead of the script's own `data/` subfolder. Fixed with
`Path(__file__).parent / "data"`, making the path independent of wherever the script is run from.

**2. Chunking comparison: proved whole-doc vs per-page chunking produce genuinely different
results, not just different counts.** Built a tiny two-fake-page test: chunking the combined text
first (Project 2's approach) produced a chunk that literally fused the tail of page 1 with the
start of page 2 ("bank. Meanwhile in a distant town..."); chunking each page independently first
(today's approach) never allowed this - every chunk stayed cleanly within one page. Real trade-off
identified: per-page chunking guarantees no cross-page content mixing and enables accurate page
citations, but *guarantees* a sentence spanning an actual page break gets split even when there's
no real topic change - a structural boundary, not necessarily a meaning boundary (same underlying
tension as Day 9's chunking lesson, from a new angle).

**3. Duplicate chunks: 601 -> 1803 after reruns.** `Chroma.from_documents()` assigns a random UUID
per chunk with no way to say "this already exists, update it" - every rerun added a fresh copy
rather than overwriting. Fixed with a deterministic ID (`hashlib.md5` of source + page + content),
so a rerun with unchanged data maps to the same IDs and correctly upserts instead of duplicating.
Verified by deleting the tripled collection, rerunning once (601), then rerunning again without
deleting anything (still 601, not 1202).

**4. Citation path leak.** `doc.metadata['source']` stores the full local file path, not just the
filename - citations were leaking full local paths (`/Users/app/ML AWS Road Map/...`), which
would expose local folder structure/username if this were ever wired into a real API response.
Fixed with `os.path.basename(doc.metadata['source'])`.

**5. Deprecated imports.** `langchain_community.vectorstores.Chroma` is being sunset; updated both
`ingest_langchain.py` and `rag_langchain.py` to `from langchain_chroma import Chroma` for
consistency (leaving one file on the old package while the other used the new one would be an
inconsistency worth avoiding before the old one is eventually removed).

## Bonus: similarity_score_threshold retriever

**Diagnostic script bug (a repeat of a known gotcha, not a new one):** first attempt at
`similarity_search_with_relevance_scores` started downloading a local embedding model
(`all-MiniLM-L6-v2`) - caused by omitting `embedding_function=embeddings` when constructing the
`Chroma` vectorstore, silently falling back to Chroma's default local model instead of OpenAI's.
Exactly the Day 7 "always be explicit about which embedding model" gotcha, resurfacing in a new
context.

**Real diagnostic finding: no clean threshold exists for this near-miss.** Unlike Day 8/10, the
GDPR near-miss question's scores (0.4585-0.4830) overlapped with the real match's scores
(0.2934-0.5027) - no single threshold value keeps all the real answer's supporting chunks while
rejecting the near-miss. This is consistent with Day 10's finding from a different angle (raw
Chroma distances for the same GDPR question were closer to real matches than an obviously
unrelated question's).

**Also found: LangChain's relevance-score normalization can go negative**, breaking its own
documented 0-1 contract (`UserWarning: Relevance scores must be between 0 and 1, got [...
-0.084, -0.086, ...]`) - a real, visible rough edge in the framework's own conversion from
Chroma's raw distance, surfaced by genuinely irrelevant content (Python-library-security chunks
retrieved for a "best programming language for beginners" query, matched on the word "Python"
alone despite being about vulnerabilities, not programming advice).

**Confirmed the two-layer defense design, with clean separation:**
- Obviously unrelated query ("best programming language for beginners") -> threshold (0.35)
  filtered every chunk (all scored negative) -> empty context reached the model -> model still
  correctly refused rather than answering from its own general knowledge, proving the prompt's
  grounding instruction holds even with zero context.
- Genuine near-miss (GDPR question) -> threshold let real chunks through (no filtering message) ->
  model read actual NIST content and correctly determined it doesn't answer a GDPR-specific
  question -> refused based on judgment, not on any score.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
Rebuilt Project 2's ingestion and RAG pipeline using LangChain (`PyPDFLoader`,
`RecursiveCharacterTextSplitter.split_documents()`, `Chroma.from_documents()`, LCEL chain with
`RunnablePassthrough`). Found and fixed five real bugs (path resolution, duplicate chunks from
non-deterministic IDs, a citation path leak, a deprecated import, and a diagnostic script
re-triggering the Day 7 embedding-model mismatch gotcha). Ran a hands-on chunking comparison
proving whole-doc vs per-page chunking produce genuinely different, non-interchangeable results.
Completed the bonus `similarity_score_threshold` exercise, confirming no clean threshold separates
a genuine near-miss and that the model's own judgment - not the score - is what correctly catches
it. Located in `week-03/day-11/practice/`.
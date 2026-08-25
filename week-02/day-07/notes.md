# Day 7 - Vector databases: local search with Chroma

**Date completed:** _(fill in)_

## What I learned

**Why a vector database, not a manual loop**
Day 6's cosine similarity loop compared a query against every sentence directly - fine for a
handful of sentences, but doesn't scale to thousands/millions of documents. A vector database
stores embeddings and finds the closest matches without a manual comparison loop, using indexing
that's far faster than brute-force at scale.

**Approximate nearest neighbor search (HNSW)**
At real scale, vector databases don't compare a query against every stored vector - most use an
algorithm like HNSW (Hierarchical Navigable Small World): long-range graph connections jump
quickly to roughly the right neighborhood, then short-range connections refine the search from
there. Trades a small amount of accuracy for a large speed gain - "approximate" nearest neighbor,
not exact, but close enough in practice.

**Chroma basics**
- `PersistentClient(path=...)` - persists the index to disk across runs
- `get_or_create_collection(name=..., configuration={"hnsw": {"space": "cosine"}})` - explicitly
  set the distance metric
- `collection.add(ids=..., documents=..., embeddings=...)` - store documents with precomputed
  embeddings
- `collection.query(query_embeddings=..., n_results=...)` - returns top-k matches

**FAISS - deferred**
Noted as a lower-level library (not a full database) for fast similarity search - no built-in
persistence or metadata filtering, works directly with numpy arrays. Common at large production
scale. Decided to defer hands-on FAISS work until after the full 8-week roadmap is complete,
since Day 7's actual practice focused entirely on Chroma.

## Bugs found and fixed

**Real bug: distances looked like cosine but were actually stale L2.** First run returned
distances like `1.4447` and `1.8387` - too large to be valid cosine distances (which range 0-2,
and values that high would imply strongly negative similarities, which real OpenAI embeddings
essentially never produce for related sentences). Suspected the `configuration={"hnsw":
{"space": "cosine"}}` argument wasn't actually taking effect.

**Root cause:** Chroma's HNSW distance metric (`space`) is set once at index creation time and
cannot be changed afterward. An earlier run had already created the `my_documents` collection
(likely without the cosine configuration, defaulting to Chroma's default L2). Every later
`get_or_create_collection(...)` call just fetched that existing L2 index - the `configuration`
argument was silently ignored because the collection already existed.

**Fix:** deleted the existing collection (`chroma_client.delete_collection(name="my_documents")`)
and let it rebuild fresh, so the cosine configuration actually applied this time.

**Verification, not just assumption:** converted the broken L2 output back to an implied cosine
similarity using the approximate relationship for near-unit-length vectors
(`similarity ≈ 1 - distance/2`), predicting ~0.28 and ~0.08 for the two pairs. After the fix, the
real cosine distances came back as 0.7223 and 0.9194 - converting those (`similarity = 1 -
distance`) gives 0.2777 and 0.0806, an almost exact match to the prediction. Confirms the
before/after really was the same underlying data, just measured with two different (and
incompatible) metrics.

**Key gotcha this surfaced:** cosine similarity (higher = more similar) and cosine distance
(lower = more similar) point in opposite directions - same math, inverted scale. Easy to
misread results if not tracking which one a tool actually returns.

## Test results - negation retrieval (the real point of today)

Added the Day 6 negation pair ("The movie was excellent." / "The movie was not excellent.") into
the collection and queried with `"Was the movie good?"`:
```
0.3298 - The movie was excellent.
0.4243 - The movie was not excellent.
0.8395 - She baked a chocolate cake for the party.
```

Both movie sentences rank as the top 2 results, clearly separated from the genuinely unrelated
cake sentence (0.33/0.42 vs 0.84) - confirming Day 6's negation-blindness finding actually plays
out in a real retrieval scenario, not just as an abstract similarity score. A real RAG system
asking "was the movie good?" would retrieve *both* the positive and negative review as strong
candidates and hand both to the LLM as context - retrieval alone does not distinguish "yes" from
"no" here. Whatever the final answer ends up being depends entirely on the generation step
reading the retrieved text carefully, not on retrieval having already resolved it. This is the
concrete problem Day 12 (hybrid search + re-ranking) exists to address.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
`day7_vectordb.py` - Chroma `PersistentClient` collection configured for cosine distance, loaded
with Day 6's test sentences plus the negation pair, queried with multiple search texts. Found and
fixed a stale-index distance-metric bug, verified the fix by converting distances back to cosine
similarity and matching against predictions, and confirmed the negation-blindness limitation
found on Day 6 reproduces in an actual retrieval scenario. Located in `practice/`.
# Day 12 - Hybrid search (keyword + semantic) and re-ranking

**Date completed:** _(fill in)_

## What I learned

**Why hybrid search - and its real, honest limit**
Semantic search is blind to exact words; BM25 keyword search is blind to meaning but always
notices whether a specific word is literally present. Hybrid search combines both signals. Key
nuance found through actual testing, not just theory: hybrid search only helps when the *query
itself* contains a distinguishing word - it does not retroactively solve negation-blindness or
any other embedding limitation when the query gives keyword search nothing to grab onto.

**BM25**
Scores documents higher for containing exact query terms, especially rare/distinctive ones, with
length normalization. Deterministic, no model, extremely fast.

**Why not average BM25 and cosine scores directly**
Incompatible scales - cosine similarity roughly -1 to 1, BM25 an unbounded positive number.
Reciprocal Rank Fusion (RRF) solves this by operating on *rank position*, not raw scores:
`score(doc) = sum over each ranking system of 1/(k + rank)`, k=60 standard. Rewards documents that
rank well across multiple independent signals.

**RRF's real limitation, found through testing, not assumed**
RRF's fused scores cluster tightly together regardless of whether the underlying signals showed a
landslide or a coin-flip margin, because it only encodes rank position, discarding magnitude
entirely. The *ranking order* from RRF is trustworthy; the *fused score itself* is not a
confidence signal the way raw cosine distance or BM25 score is.

**Bi-encoder vs cross-encoder (re-ranking)**
Every embedding model used so far is a bi-encoder - encodes query and document separately,
enabling precomputed/reusable document vectors. A cross-encoder takes query and document
*together* as one input and directly outputs a relevance score - more accurate (can model
fine-grained query-document relationships), but nothing can be precomputed, so it's only run on a
small shortlist (e.g. top 20 from hybrid search) rather than the whole corpus.

## Experiment 1: revisiting the Day 6/7 negation question - the honest, complete answer

Ran three different queries against the same "movie was/was not excellent" toy sentences to
isolate exactly when hybrid search helps:

- **"Find reviews that were not positive"** (query contains "not"): BM25 gave a decisive signal
  (0.5394 vs 0.0000), fused ranking correctly favored "not excellent." But semantic search
  *alone* also got this right (0.2364 vs 0.1487) - because the query's own wording ("not
  positive") already nudges the embedding toward matching a sentence containing "not," independent
  of BM25 entirely. This wasn't really "hybrid search fixed semantic search" - both signals
  happened to point the same direction here.
- **"Was the movie good?"** (no lexical hint - this is Day 6/7's original phrasing): semantic
  search alone reproduced the *exact* Day 6/7 finding - "excellent" (0.6702) ranked above "not
  excellent" (0.5758), negation-blindness fully intact. BM25 gave only a weak, non-discriminating
  signal (0.0438 vs 0.0401, both nonzero due to the toy corpus being too small for BM25's
  rarity-statistics to work as intended) that didn't correct anything. Fused ranking inherited
  the wrong order.

**Conclusion: hybrid search does not fix negation-blindness in general** - only when the query
itself carries the distinguishing word. When it doesn't, hybrid search quietly degrades back to
whatever semantic search alone would have produced. The actual fix, confirmed across Day 10/11's
GDPR near-miss too, is the model reading and reasoning about retrieved content at generation time
- a generation-quality safeguard, not a retrieval-ranking one.

## Experiment 2: the GDPR near-miss, on the real 601-chunk corpus

Predicted BM25 would return near-zero scores for "What does GDPR say about AI risk management?"
since none of the 3 documents mention GDPR. Prediction was wrong: top score was 7.9684, clearly
nonzero.

**Real explanation, verified directly (`"gdpr" in top_chunk.lower()` returned `False`):** BM25
doesn't require every query word to match - it sums credit from whichever words do. "AI," "risk,"
and "management" are extremely common throughout this AI-risk-focused corpus, so the query scored
well purely from generic shared vocabulary, while "GDPR" (the one word that actually determines
relevance) contributed nothing at all. A high BM25 score here doesn't mean "this is about GDPR" -
it means "this document reuses common corpus vocabulary," which is close to tautological in a
narrow-topic corpus.

**Conclusion:** hybrid search's keyword signal is strongest against *rare, distinctive* terms
(proven separately via the OWASP "LLM01" bonus test) and structurally weak against a query whose
irrelevant term is rare but whose relevant-sounding terms are common in the corpus. Same overall
conclusion as Experiment 1: the model's own judgment at generation time remains the most reliable
backstop across every near-miss found so far (Day 8, Day 10/11 x2, and today).

## Re-ranking - a real, demonstrated improvement

Built the full pipeline: BM25 + semantic search -> RRF fusion (top 20) -> cross-encoder rerank
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) -> final top 5, using stable document IDs from Chroma
throughout (not list position or re-matched text) to avoid the exact class of fragility Day 8's
deterministic-ID lesson and Day 11's duplicate-chunk bug both already surfaced.

**Real result on "What is prompt injection and how do you prevent it?":** semantic-only ranking
placed the bare section heading `"LLM01:2025 Prompt Injection . . . ."` at #2 - a chunk that
matches well on words but contains almost no actual explanatory content. The cross-encoder
correctly demoted this heading entirely out of the final top 5, replacing it with a chunk
containing genuine substance. This is exactly what cross-encoders are supposed to do differently
from bi-encoders: reading query and document *together* lets the model recognize "this is a
table-of-contents entry, not an answer" in a way separately-encoded embeddings structurally can't.

## Environment issue: sentence-transformers install conflict

`pip install sentence-transformers` into the main pinned `venv` triggered a dependency resolution
deadlock (every historical sentence-transformers version incompatible with the exact-pinned
`torch`-adjacent packages already locked in requirements.txt). Fixed properly by isolating the
exploration into a dedicated `reranking_venv` rather than fighting the resolver - heavy/exploratory
ML dependencies like `torch` don't need to live permanently in the main project environment, and
bundling them in would risk reintroducing Day 4's image-bloat problem if ever containerized.

**A second, separate issue inside the fresh venv:** `torch` itself failed with "Could not find a
version that satisfies the requirement torch (from versions: none)" - diagnosed as a pip/PyPI
connectivity failure, not a real dependency conflict, most likely the same unresolved SNI-based
network filtering from Day 10 resurfacing against `pypi.org` this time. Resolved (mechanism not
fully confirmed - flagged as a loose end worth understanding later, not just accepting that "it
works now").

Added `reranking_venv/` to `.gitignore`.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Still not fully confirmed: exactly what fixed the torch/pip network issue. Worth asking
  directly what changed, rather than treating "it works now" as sufficient understanding - same
  principle as every other debugging session this roadmap has pushed for.

## Practice task
Implemented `bm25_search()` and `reciprocal_rank_fusion()`, ran two honest (non-cherry-picked)
experiments testing hybrid search against the deferred Day 6/7 negation question and the Day
10/11 GDPR near-miss, and built a full BM25 + semantic + RRF + cross-encoder re-ranking pipeline
using stable Chroma IDs throughout. Confirmed a real, concrete improvement from re-ranking
(demoting a low-content section heading that matched well on words alone). Located in
`week-03/day-12/practice/`.
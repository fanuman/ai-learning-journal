# Day 6 - Embeddings fundamentals and similarity metrics

**Date completed:** _(fill in)_

## What I learned

**What an embedding is**
Converts text into a list of numbers (a vector) that captures meaning - similar meanings produce
similar vectors, even with zero shared words. Like GPS coordinates, but for meaning instead of
physical location. This is the foundation everything in RAG is built on: it's what lets a search
match by concept instead of exact keywords.

**What embeddings look like**
`text-embedding-3-small` produces 1536 floating-point numbers per piece of text. No single number
is individually meaningful - only the overall pattern across all 1536 encodes meaning, and vectors
are only ever compared to each other, never read directly.

**Cosine similarity**
Measures the angle between two vectors, ignoring magnitude - preferred over raw distance because
it's magnitude-invariant (a short sentence and a longer paraphrase of the same idea can still
score close). Range -1 to 1: 1 = same direction (very similar), 0 = unrelated, -1 = opposite
(rare in practice).
```python
def cosine_similarity(vec_a, vec_b):
    vec_a = np.array(vec_a)
    vec_b = np.array(vec_b)
    return np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
```

**Model choice**
`text-embedding-3-small` (1536 dims, ~$0.02/1M tokens) is the right default for almost all RAG
use cases. `text-embedding-3-large` (3072 dims) scores somewhat higher on benchmarks but costs
~6x more - worth it mainly for high-stakes domains (legal/medical) where a wrong match matters a
lot. Both support a `dimensions` parameter to truncate the vector with only minor accuracy loss.

## Code I wrote

Built `day6_embeddings.py`: `get_embedding()` + `cosine_similarity()` functions, run across a
14-sentence test set designed to probe specific properties (not just random sentences) - paraphrase
pairs, a near-duplicate, polysemous words used in different senses, a negation pair, and a
casual-vs-formal paraphrase, plus one clean unrelated baseline.

## Test results and findings

**Negation - the most important finding today.** "The movie was excellent." vs. "The movie was
not excellent." scored **0.7128** - higher than the original cat/feline paraphrase (0.6631)!
Predicted low similarity (opposite meanings); got high similarity instead. Embeddings primarily
encode topic/content, not logical truth value - both sentences are about evaluating a movie, and
that topical overlap dominates the vector. **Practical consequence:** pure embedding similarity
cannot reliably distinguish "positive review" from "negative review" - a RAG/search system needing
that distinction needs a different technique layered on top (classifier, structured filtering),
not embeddings alone.

**Casual vs. formal paraphrase - very high, as hoped.** "Can u send me that file asap?" vs.
"Could you please send me that file as soon as possible?" scored **0.8339** - even higher than
the cat/feline pair, close to the near-duplicate score. Good news for real use: sloppy/casual user
queries will still reliably match cleanly-written formal documents.

**Polysemy (bank, spring) - correctly separated, but not fully.** "Bank" (finance) vs. "bank"
(river) scored **0.1764**; the two "spring" sentences (mattress vs. season) scored **0.2131**.
Both correctly well below genuine synonym pairs (0.66-0.89) - the model does distinguish the
meanings. But both are still noticeably above the true-unrelated baseline (~0.03-0.15) - sharing
a literal word exerts a small pull on similarity even when meanings genuinely differ. Same effect
showed up unprompted: "The cat sat on the mat." vs "I sat by the river bank." scored 0.3114,
elevated purely from sharing "sat" and similar sentence structure despite unrelated topics.

**Near-duplicate ceiling.** "The cat sat on the mat." vs. the same sentence + "today" scored
**0.8945** - the highest score in the whole matrix, but notably not 1.0 even for a one-word
difference. Useful calibration for later: a real high-confidence match in practice looks like
~0.85+, not a clean 1.0.

**Clean baseline confirmed.** Every comparison against "The Great Wall of China stretches
thousands of miles." landed at the bottom of the table, several near zero and one slightly
negative (-0.0367 vs. "bank raised interest rates") - correctly registering as genuinely
unrelated.

**Overall takeaway:** embeddings are powerful but not "pure meaning" - they're pulled toward
lexical/topical overlap even when logical meaning diverges (negation) or word sense differs
(polysemy). Both are real, known limitations worth knowing before relying on embeddings alone in
Week 2's RAG work.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Worth exploring later: how RAG systems in practice handle the negation-blindness problem (e.g.
  combining embeddings with metadata filters or a lightweight classifier).

## Practice task
`day6_embeddings.py` - embedding generation + cosine similarity across a 14-sentence test set
covering paraphrase, near-duplicate, polysemy, negation, register-shift, and unrelated-baseline
pairs. Predictions made before running; negation and lexical-overlap effects confirmed against
the actual similarity matrix. Located in `practice/`.
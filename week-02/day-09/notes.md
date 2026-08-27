# Day 9 - Chunking strategies: fixed, recursive, semantic

**Date completed:** _(fill in)_

## What I learned

**Why chunking matters**
Chunk quality directly determines retrieval quality - a perfect vector DB and a perfect prompt
can't compensate for chunks that mix unrelated topics together or cut through content mid-idea.

**Three strategies**
- **Fixed-size** - split every N characters, blind to content. Simple and fast, but will cut
  through sentences, words, or even topic boundaries with no awareness at all.
- **Recursive** (`RecursiveCharacterTextSplitter`) - tries natural separators in priority order
  (paragraph breaks, then newlines, then sentence endings, then words, then raw characters),
  falling back to the next option only if a piece is still too big. Industry-standard default.
- **Semantic** - embeds each sentence, compares consecutive sentences with cosine similarity, and
  starts a new chunk when similarity drops below a threshold (a real topic shift) - reads meaning
  directly rather than relying on formatting.

**Chunk overlap**
Consecutive chunks share a bit of text at their boundary so information sitting right at a seam
isn't orphaned from context in both directions.

## Code I wrote

Built `fixed_size_chunk()`, a `RecursiveCharacterTextSplitter` setup, and `semantic_chunk()`
(reusing Day 6's `cosine_similarity()`), tested on a two-topic document (Acme's remote work
policy, then Acme's marketing strategy) designed specifically to expose differences between the
three methods.

## Bug found and fixed: semantic chunking threshold

**Initial run degenerated into one-sentence-per-chunk** with `similarity_threshold=0.5` - every
single sentence became its own chunk, including consecutive sentences from the same topic. Looked
superficially fine (clean sentences, no visible corruption) but was actually the least useful
possible output - the threshold was doing nothing to detect real topic shifts.

**Diagnosis:** printed the raw similarity value at every sentence transition instead of guessing:
```
0.3496 - Manager approval...          (within remote-work topic)
0.2811 - Employees must maintain...   (within remote-work topic)
0.2571 - This policy was updated...   (within remote-work topic)
0.4632 - The updated policy also...   (within remote-work topic)
0.1223 - Acme Corp's marketing...     (THE ACTUAL TOPIC SHIFT)
0.3426 - The team plans...            (within marketing topic)
0.3431 - A new influencer...          (within marketing topic)
0.2070 - Budget allocation...         (within marketing topic)
0.3275 - Early results...             (within marketing topic)
```
The real topic shift (0.1223) sits clearly below every within-topic value (0.207-0.4632) - a
genuine, detectable gap exists in the data. The bug wasn't the method, it was that `0.5` sat
above every single value in the list, so everything looked like a "shift."

**Fix:** set `similarity_threshold=0.18` (between the real shift at 0.1223 and the lowest
within-topic value at 0.207). Rerun produced exactly 2 chunks, split precisely at the true topic
boundary.

**Key lesson - twice now in two days (Day 8's distance cutoff, today's similarity threshold):**
don't pick a threshold from intuition. Print the actual number distribution for the real data and
set the cutoff where the genuine gap is. A badly-set threshold doesn't error or crash - it just
silently produces a different, worse behavior that can look fine at a glance.

## The real test: removing the paragraph break

Stripped the `\n\n` between the two topics (joined with a single space - zero formatting signal
left) and reran all three methods:

- **Fixed-size** - unaffected, because it was never using the paragraph break in the first place.
  Still blends both topics into one chunk (just at a slightly different cut point than before).
- **Recursive** - this is the one that actually reveals the mechanism. With `\n\n` present, it
  split cleanly on the paragraph break. With it removed, it fell back to sentence-boundary
  splitting (`". "`) and fused both topics into a single chunk - it produces clean sentences
  either way, but has no concept of *topic*, only structure. It succeeded before purely because
  the formatting happened to align with the real topic boundary, and failed silently once that
  alignment was gone.
- **Semantic** - completely unchanged, identical 2-chunk output at the identical split point.
  Never read `\n\n` to begin with - it only compares sentence meaning - so removing a formatting
  cue it never used had zero effect.

**This is the concrete, proven distinction between structural and semantic chunking:** recursive
respects structure and gets lucky when structure lines up with meaning; semantic reads meaning
directly and doesn't depend on luck.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
Built and compared `fixed_size_chunk()`, `RecursiveCharacterTextSplitter`, and `semantic_chunk()`
on a two-topic test document, both with and without a paragraph break present. Found and fixed a
threshold-tuning bug in semantic chunking using the same empirical-calibration approach as Day 8.
Confirmed with real before/after data that semantic chunking finds topic boundaries independent
of formatting, while recursive chunking only succeeds when formatting happens to align with
topic structure. Located in `practice/`.
# LLM Test Day 1 - Measuring retrieval

Date: Thu 12 Nov 2026
Track: TrailPeak professional testing (plan: Project doc `claude/trailpeak-testing-plan.md`, Day 1 of 4)
Code: `metrics_demo.py` in this folder

## Goal of the day
Before changing how TrailPeak searches (hybrid search on Day 3, re-ranking on Day 4), learn to **measure** search.
If we cannot measure it, we cannot say whether a change helped.

---

## 1. What "evaluating" means
An evaluation has three parts:
1. **Test set**: questions where a human already knows the right outcome.
2. **Output**: what the system returned for each question.
3. **Score**: a number that compares the two.

LLM apps need this because they **fail silently**: a broken search still produces a fluent answer, so "it looked right in the demo" proves very little.

## 2. Chunks, IDs and labels (TrailPeak facts)
- `ingest.py` splits each file in `data/` into **chunks** of about 800 characters (150 characters overlap).
- Each chunk gets a stable **ID**: `md5("<filename>-<position>")`. Re-ingesting the same files gives the same IDs.
- `RETRIEVAL_K = 5`: each search returns the 5 closest chunks.
- A **relevance label** is a human decision: "for this question, these chunks contain what is needed". The set of labels is the **ground truth** (answer key).
- Today TrailPeak labels by **file** (`expected_sources: ["product_catalog.txt"]`). Too coarse: the catalogue is more than half of all the text, so "right file" is almost always true even when the right chunk was missed. We will label by **chunk**.
- A question that needs two facts (jacket price *and* poles price) has **two** relevant chunks. Getting one is a real miss.
- Out-of-scope questions ("What's the weather?") have **no** relevant chunk, so retrieval metrics do not apply. They are scored as behaviour (refuse or answer) on Day 2.

## 3. The confusion matrix, applied to retrieval
Treat each returned chunk as the system saying "this one is relevant".

|                      | Relevant chunk | Not relevant |
|----------------------|----------------|--------------|
| Returned in top k    | TP (good)      | FP (noise)   |
| Not returned         | FN (a miss)    | TN (correctly left out) |

- TP = true positive, FP = false positive, FN = false negative, TN = true negative.
- **Accuracy is useless for retrieval** because TN is huge: with 40 chunks and 2 relevant, returning nothing is already 95% "accurate". That is why we use precision and recall.

## 4. Why recall@k matters most
- The model can only use chunks it receives. If the needed chunk is not in the top k, no prompt or model can fix the answer.
- Bigger k raises recall but adds noise, tokens and cost. Precision and the ranking metrics show that cost.
- Anthropic reports the same idea as "retrieval failure rate" = 1 - recall@20.

## 5. How scores are combined
Compute every metric **per question**, then take the **average** over questions (macro average). Do not pool all chunks of all questions into one count.

---

## 6. Worked example (by hand)
Relevant (answer key): `{c2, c4}`. The search returned, best first: `[c7, c2, c9, c4, c1]`.

| Metric | Working | Result |
|---|---|---|
| Precision@5 | 2 relevant out of 5 returned | 0.40 |
| Recall@5 | found 2 of the 2 needed | 1.00 |
| Recall@3 | top 3 = c7, c2, c9 -> 1 of 2 | 0.50 |
| Hit rate@5 | at least one relevant in top 5? yes | 1 |
| MRR | first relevant at position 2 -> 1/2 | 0.50 |
| nDCG@5 | (0.63 + 0.43) / (1.00 + 0.63) = 1.06 / 1.63 | 0.65 |

## 7. Code and result
`metrics_demo.py` implements the five ranking metrics and scores three result lists for the same question.

```
search           P@5   R@5   R@3  hit@5   MRR  nDCG@5
vector only     0.40  1.00  0.50    1.0  0.50   0.651
after re-rank   0.40  1.00  1.00    1.0  1.00   1.000
bad search      0.00  0.00  0.00    0.0  0.00   0.000
```

**What it shows:** "after re-rank" has the **same five chunks**, only reordered. Precision@5, recall@5 and hit rate did not move; MRR, nDCG and recall@3 improved.
So a re-ranker's gain is invisible in plain precision/recall@5. That is why we track rank-aware metrics (MRR, nDCG).

## 8. nDCG step by step (the confusing one)
The name is four ideas stacked: **n**ormalised **D**iscounted **C**umulative **G**ain.

1. **Gain**: each chunk earns points. Relevant = 1, not relevant = 0. For `[c7, c2, c9, c4, c1]` -> `[0, 1, 0, 1, 0]`.
2. **Cumulative**: add them up: 2. On its own this ignores order (`[c2, c4, ...]` and `[..., c2, c4]` both score 2).
3. **Discounted**: divide each chunk's points by a penalty that grows with position: worth = 1 / log2(position + 1).

   | Position | 1 | 2 | 3 | 4 | 5 |
   |---|---|---|---|---|---|
   | Worth | 1.00 | 0.63 | 0.50 | 0.43 | 0.39 |

   DCG = 0.63 (c2 at position 2) + 0.43 (c4 at position 4) = **1.06**.
   Why discount: the model pays most attention to what comes first, and if k is later cut from 5 to 3, positions 4-5 disappear.
   The log makes the discount **gentle**: position 5 keeps 39% of its value (MRR would give a first hit at position 5 only 0.20).
4. **Normalised**: divide by the best possible score (**ideal DCG**, relevant chunks at the top): 1.00 + 0.63 = 1.63.
   nDCG = 1.06 / 1.63 = **0.65**. Always between 0 and 1; 1.0 = perfect ordering.

**Why normalise:** question A has 1 relevant chunk at position 1 (DCG 1.00); question B has 3 at positions 1-3 (DCG 2.13). Both are perfect, but raw DCG differs. Dividing each by its own ideal gives both **1.0**, so questions can be averaged fairly.

**nDCG vs MRR:** MRR looks only at the **first** relevant chunk; nDCG looks at **all** of them.

| Result list (relevant: c2, c4) | MRR | nDCG@5 |
|---|---|---|
| `[c2, c4, c7, c9, c1]` | 1.00 | 1.000 |
| `[c2, c7, c9, c1, c4]` | 1.00 | 0.850 |
| `[c7, c2, c9, c4, c1]` | 0.50 | 0.651 |

Rows 1 and 2 have the same MRR, but in row 2 the second needed chunk sank to position 5; only nDCG notices. For two-fact questions that matters.

**Graded relevance:** nDCG also allows gains like 2 (fully answers), 1 (partly helps), 0 (useless). Search engines use that. TrailPeak keeps 0/1 because grades are harder to label consistently.

---

## 9. Common mistakes
- Labelling by file instead of chunk.
- Reading recall@5 = 1.0 as "the answer will be right". Search can be perfect while the generated answer is wrong.
- Including out-of-scope questions in retrieval averages.
- Judging a change from 5 questions: one question moves the average by 0.2.
- Using hit rate for multi-fact questions: it says "fine" when only one of two needed chunks came back.

## 10. Interview one-liners
- "I measure retrieval separately from generation: recall@k tells me whether the right chunk reached the model, MRR and nDCG tell me how high it ranked, and I label at chunk level so the numbers mean something."
- "nDCG gives each relevant chunk credit that shrinks with its position, then divides by the best possible score, so 1.0 means perfect ordering and it is comparable across questions."

## 11. Self-check questions
1. Why is accuracy a poor metric for retrieval, while precision and recall are useful?
2. In the demo, why did precision@5 stay at 0.40 after re-ranking while nDCG went to 1.0?
3. A question needs two chunks and the search returns only one. What do hit rate and recall@5 say?
4. Why are out-of-scope questions excluded from retrieval metrics?
5. Why is a label on `product_catalog.txt` weaker than a label on one chunk?

---

## 12. Metric reference
Notation: `k` = how many top results we look at; `relevant` = the answer-key chunks for the question; `retrieved[:k]` = the top k results; `rel_i` = 1 if the result at position i is relevant, else 0.

### Accuracy
- **Definition:** share of all decisions that were correct.
- **Formula:** `accuracy = (TP + TN) / (TP + FP + FN + TN)`
- **Explanation:** fine when both classes are common; misleading when one class is rare or TN is huge (retrieval, rare refusals). A system that always says "no" can score high.
- **Range:** 0 to 1.

### Precision
- **Definition:** of everything the system said "yes" to, how much was really "yes".
- **Formula:** `precision = TP / (TP + FP)`
- **Explanation:** measures noise / false alarms. High precision = what it returns can be trusted.
- **Range:** 0 to 1.

### Recall
- **Definition:** of everything that really was "yes", how much the system found.
- **Formula:** `recall = TP / (TP + FN)`
- **Explanation:** measures misses. High recall = it rarely leaves something important out.
- **Range:** 0 to 1. Precision and recall usually trade off against each other.

### F1
- **Definition:** one number that balances precision and recall.
- **Formula:** `F1 = 2 * precision * recall / (precision + recall)`
- **Explanation:** harmonic mean, so it is high only when **both** are high (precision 1.0 with recall 0.1 gives F1 0.18, not 0.55).
- **Range:** 0 to 1.

### Precision@k
- **Definition:** share of the top k results that are relevant.
- **Formula:** `P@k = (number of relevant chunks in retrieved[:k]) / k`
- **Explanation:** how much noise reaches the model. Ignores order inside the top k. Its maximum is below 1 when a question has fewer than k relevant chunks (2 relevant, k = 5 -> max 0.40).
- **Range:** 0 to 1.

### Recall@k
- **Definition:** share of the relevant chunks that appear in the top k.
- **Formula:** `R@k = (number of relevant chunks in retrieved[:k]) / len(relevant)`
- **Explanation:** the most important retrieval metric for RAG: did what the model needs actually reach it? Ignores order inside the top k. Undefined when there are no relevant chunks (out-of-scope questions).
- **Range:** 0 to 1. `retrieval failure rate = 1 - R@k`.

### Hit rate@k
- **Definition:** did at least one relevant chunk appear in the top k?
- **Formula:** `hit@k = 1 if any relevant chunk is in retrieved[:k] else 0` (averaged over questions = share of questions with a hit)
- **Explanation:** simple and lenient. Hides partial misses on multi-fact questions; use recall@k for those.
- **Range:** 0 or 1 per question; 0 to 1 averaged.

### MRR (Mean Reciprocal Rank)
- **Definition:** how early the **first** relevant chunk appears.
- **Formula (one question):** `RR = 1 / (position of the first relevant chunk)`, 0 if none. `MRR = average of RR over all questions`.
- **Explanation:** rewards putting a useful chunk at the very top. Position 1 = 1.0, 2 = 0.5, 3 = 0.33, 5 = 0.2. Ignores every relevant chunk after the first.
- **Range:** 0 to 1.

### DCG@k and nDCG@k (normalised Discounted Cumulative Gain)
- **Definition:** a score for the **whole order** of the top k, relative to the best possible order.
- **Formulas:**
  - `DCG@k = sum over i = 1..k of rel_i / log2(i + 1)`
  - `IDCG@k = DCG@k of the ideal order` (all relevant chunks first) `= sum over i = 1..min(len(relevant), k) of 1 / log2(i + 1)`
  - `nDCG@k = DCG@k / IDCG@k`
- **Explanation:** every relevant chunk earns credit, shrinking gently with position; dividing by the ideal makes questions comparable. Best metric for judging **ordering** changes such as re-ranking. With graded relevance, `rel_i` can be 2, 1 or 0.
- **Range:** 0 to 1 (1 = perfect ordering).

### Quick chooser
| Question you are asking | Metric |
|---|---|
| Did the model receive what it needs? | Recall@k |
| How much noise is in the prompt? | Precision@k |
| Is a useful chunk near the top? | MRR |
| Is the whole order good (did re-ranking help)? | nDCG@k |
| A yes/no decision (refuse, call a tool)? | Precision, recall, F1 (accuracy only if classes are balanced) |

---

## 13. What we built in TrailPeak today
| File | What it does |
|---|---|
| `src/evaluation/inspect_chunks.py` (new) | Lists every chunk as `<file>#<position>` (position recovered from the md5 ID). Full text with a file name argument. |
| `src/evaluation/golden_set.py` | Each question now has `expected_chunks` (the chunk-level answer key). `expected_sources` kept for the old harness. |
| `src/evaluation/retrieval_metrics.py` (new) | precision@k, recall@k, hit rate@k, reciprocal rank@k, nDCG@k, plus per-question and averaged scores. Pure functions. |
| `tests/test_retrieval_metrics.py` (new) | 12 tests with hand-calculated numbers. |
| `src/rag/pipeline.py` | New `search()` returns id, text, source, distance per chunk; `retrieve()` now uses it (same return as before). |
| `src/evaluation/run_retrieval_eval.py` (new) | Scores the real search against the answer key, prints per question, saves `eval_results/retrieval_<time>.json`. No LLM calls. |
| `tests/test_stream_events.py` | The fake Chroma collection now returns `ids`, like real Chroma. |

Answer key decisions: label only the **must-have** chunks; with overlap, label the chunk that has the real content (SummitCarry = #4, not #3); prices and stock are not in the documents (inventory tool), so for price questions the relevant chunk is the one that names the product and SKU.

## 14. First real results (vector-only search, 5 questions)

| Run | Precision | Recall | Hit rate | MRR | nDCG |
|---|---|---|---|---|---|
| k = 5 | 0.360 | 1.000 | 1.000 | 0.900 | 0.914 |
| k = 3 | 0.533 | 0.900 | 1.000 | 0.900 | 0.861 |

Per question (k = 5): every needed chunk was found. Two were not at the top:
- **Winter tent** (MRR 0.50, nDCG 0.69): position 1 was `product_catalog.txt#7`, the **sleeping bag** chunk ("prevent heat loss", "20F rating"). Vector search matched the *meaning* of "winter" (cold, warmth) instead of the word "tent". The tent chunks came 2nd and 3rd. Keyword search (BM25, Day 3) should push "tent" up.
- **Warranty policy** (nDCG 0.88): the warranty-periods chunk (#1, a bare list "Outerwear: 2 years ...") came 4th. At k = 3 it falls out entirely (recall 0.50). Lists with little prose embed weakly; a re-ranker (Day 4) reads question and chunk together and may lift it.

What the numbers teach:
- **Precision 0.36 is the maximum possible here**, not a bad score. The 5 questions have 9 relevant chunks in total; with k = 5 the best average is 9 / 25 = 0.36. Precision@k is capped when a question has fewer relevant chunks than k.
- **k trade-off seen for real**: k = 3 raises precision (less noise) but loses the warranty-periods chunk (recall 0.90).
- **Ceiling effect**: recall@5 is already 1.0 on all 5 questions, so these questions cannot show whether hybrid search helps. We need harder and more varied questions (Day 2: about 40-50, with categories). Room left to improve is in the **ordering** (MRR 0.90, nDCG 0.91).
- The old file-level `context_precision` baseline was 1.0; chunk-level precision is 0.36. Same idea, very different strictness.

## 15. Lessons from today's problems
- **Outside Docker, services have different addresses.** Inside Compose, the app reaches Redis at `redis`; from the Mac terminal it is `localhost`. Run scripts with `export REDIS_HOST=localhost CHROMA_HOST=localhost CHROMA_PORT=8001`.
- **Check what tests fake, not just what they call.** Changing `retrieve()` broke 44 tests because a test faked Chroma one level lower and that fake returned no `ids`. The fix was the fake (real Chroma always returns ids), not the app. A fake must behave like the real thing.
- The retrieval eval does not need Redis, but building `RAGPipeline` connects to it anyway. To fix before the CI gate (Day 4).

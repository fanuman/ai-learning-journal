# Day 13 - RAG evaluation: faithfulness/relevancy metrics, eval harness

**Date completed:** _(fill in)_

## What I learned

**Why formal evaluation, not eyeballing**
All week, retrieval/prompt changes were judged by hand-checking a few questions. This doesn't
scale past a handful of examples, and it's biased in a specific way: already knowing what answer
to expect makes it easy to unconsciously rate a mediocre answer as "good enough" - a real user
asking cold has no such generosity. A formal eval harness runs a fixed set of test questions (a
"golden dataset") through a pipeline every time, scores each response the same way, and produces
numbers that can be honestly compared across pipeline variants, prompt changes, or chunking
strategies - the same kind of controlled, repeatable measurement Day 8/9 already reached for
informally (empirically-tuned thresholds) but never fully systematized.

**RAG has exactly two places things can go wrong - retrieval and generation**
Retrieval can fail by fetching the wrong context (or missing the right context entirely).
Generation can fail by using good context badly - ignoring it, misreading it, or answering from
its own training knowledge instead of what was actually retrieved. Every RAG evaluation metric
exists to catch one of these two failure points, never both at once - which is exactly why a
single "does this answer look right?" check is insufficient: it can't tell you *which* stage
failed when something goes wrong.

**The four canonical metrics, one per quadrant of that retrieval/generation split**
- **Context precision** (retrieval) - of what was retrieved, how much was actually relevant?
- **Context recall** (retrieval) - of what was needed to answer the question, how much did
  retrieval actually find?
- **Faithfulness** (generation) - does the answer only make claims that are directly supported by
  the retrieved context? Formula: (number of supported claims) / (total number of claims). A claim
  is "supported" if it can be directly inferred from the context - nothing more, nothing assumed.
- **Answer relevancy** (generation) - does the answer actually address what the question asked,
  independent of whether it's factually correct?

**Faithfulness and answer relevancy are deliberately independent, not two views of one thing.**
An answer can be perfectly faithful to context that is itself wrong or irrelevant. An answer can
also be highly relevant (directly addresses the question, reads well) while being unfaithful
(correct-sounding, but not actually traceable to what was retrieved this run) - which is exactly
what happened with the AI RMF question today (see findings below). Measuring only one of the two
would have hidden that finding completely.

**This four-metric breakdown is not something invented for this exercise - it's the standard
industry framework**, formalized by an open-source library called RAGAS. The typical tool
lifecycle in real production teams: RAGAS for exploration and prototyping, DeepEval for wiring
evaluation into CI/CD pipelines (so a bad prompt or retrieval change gets caught automatically on
every commit), and dedicated tools like Patronus or Langfuse for ongoing production monitoring.
Built both generation-side metrics by hand today specifically to understand the mechanism before
ever touching the library - same pattern as hand-building RAG before Day 11's LangChain rebuild.
Context precision/recall deferred to Day 27 (need a labeled ground-truth dataset - heavier setup
than today's scope); RAGAS/DeepEval itself has no dedicated hands-on day in the remaining
roadmap, so it goes on the post-roadmap exploration list, with a brief pointer planned for Day 19
where DeepEval's CI/CD angle is directly relevant.

**The LLM-as-judge pattern**
Since faithfulness and relevancy are both subjective/semantic judgments (not exact-match
testable), the standard technique is using an LLM itself to make the call - "given this context
and this claim, is the claim supported?" This reuses Day 2's structured output technique exactly
(Pydantic model + `.parse()`), just applied to *evaluating* output instead of *classifying* input.
Important, non-obvious consequence proven today (see finding #3): the judge is still an LLM, and
is fully capable of the same failure mode - including hallucination - that it's being used to
detect. LLM-as-judge is a genuinely useful pattern, not an infallible one.

## Code structure
Split into `eval_metrics.py` (scoring logic, no pipeline dependency), `pipeline_semantic.py`
(Day 8/11-style retrieval wrapped as `run_semantic(query) -> (answer, chunks)`), and
`run_eval.py` (golden dataset + harness). Deliberately kept `pipeline_hybrid.py` (Day 12's
hybrid+rerank) out of today's scope to keep the core faithfulness/relevancy concept clear before
adding a second variable - noted as unfinished, optional follow-up work for later.

## Bugs and real findings (three today)

**1. Collection mismatch caught before running.** First draft of `pipeline_semantic.py` pointed
at Day 8's tiny `acme_handbook` collection while the golden dataset asked about prompt
injection/AI RMF/GDPR - would have silently tested against completely unrelated data. Fixed by
pointing at the same `ai_governance_docs_lc` collection both Day 11 and Day 12 already use, so
both future pipelines are comparable against the same corpus. Also switched
`get_or_create_collection` to `get_collection` so a wrong path/name fails loudly instead of
silently creating an empty collection.

**2. Threshold reused from the wrong dataset - the biggest bug of the day.** Carried Day 8's
`0.5` cosine-distance threshold onto the real 601-chunk corpus unchanged. Result: 4 of 5 questions
incorrectly hit the "No Document Matches" fallback, including "What is prompt injection..." - a
query that has worked correctly every single time this week (Day 8, 10, 11, 12). Diagnosed by
printing real distances: even a genuinely excellent match landed at 0.70-0.99 in this corpus,
while Day 8's tiny corpus had real matches under 0.40. Also clarified a real misunderstanding
along the way: cosine distance ranges 0-2, not 0-1 (distance = 1 - similarity, and similarity
itself ranges -1 to 1) - a "known-irrelevant" query scored ~1.53, i.e. genuinely negative cosine
similarity, not just "far." Recalibrated empirically against real match (0.70-0.99) vs
known-irrelevant (1.53-1.54) ranges, landing on `1.2` with real margin on both sides. Same lesson
as Day 8 itself already warned in writing: a threshold is tuned to one dataset/embedding model,
not a universal constant - re-validate it before reusing it elsewhere, don't just carry the number
over.

**3. The eval scorer hallucinated inside its own hallucination-detection logic.** After fixing
the threshold, correct refusals ("I don't have information about that.") scored 0.00 faithfulness
- the worst possible score for the safest possible answer. Diagnosed by testing
`extract_claims()` directly: given the single sentence "I don't have information about that.", it
returned **two** claims, one of which ("I don't know about that.") was never actually said -
invented outright. The claim-extraction step, itself built to catch hallucination, hallucinated.
Real, general lesson: an LLM-as-judge is still an LLM, capable of the exact failure mode it's
meant to detect - especially on degenerate edge cases (a one-sentence refusal has nothing
meaningful to decompose into "claims"). Fixed with an explicit short-circuit: known refusal
phrases skip claim extraction entirely and return a clean `1.0, []`. Acknowledged trade-off: this
is a hardcoded pattern match specific to this pipeline's known refusal wording, not a general
solution.

## Two genuine findings surfaced by the (now-fixed) harness itself

**AI RMF question: 5/5 relevancy, only 0.20 faithfulness.** The answer ("GOVERN, MAP, MEASURE, and
MANAGE") is correct and reads perfectly - but checking the actual retrieved chunks, that exact
four-item list never appears together in what was retrieved; the words are scattered across
fragments. Likely explanation: NIST's AI RMF is well-known enough that the model reconstructed a
confident, correct answer partly or fully from its own training knowledge rather than the specific
context handed to it this run. A plausibility check alone would never catch this - it takes
faithfulness and relevancy actively disagreeing to surface it. Probably the single most valuable
result of the day: proof that "the answer sounds right" and "the answer is grounded in what was
actually retrieved" are genuinely different questions.

**LLM01 question: retrieval itself failed.** Query "What is LLM01?" retrieved chunks about LLM02,
LLM06, and unrelated scenarios - not one chunk about LLM01 itself, despite that content existing
in the corpus (confirmed working in Day 12). Explanation: "LLM01" is an ID/code, not a natural-
language concept - exactly the case Day 6 (embeddings capture meaning) and Day 12's bonus task
(BM25 should excel at exact rare tokens where semantic search struggles) already predicted in
theory. Independently reproduced that exact predicted failure mode from real data today, without
deliberately engineering the test for it - concrete, corpus-native justification for why Day 12's
hybrid search work matters, discovered rather than assumed.

## Final results (plain semantic pipeline, post-fix)
```
Avg faithfulness: 0.83 | Avg relevancy: 2.80/5
[0.94 | 5/5] What is prompt injection and how do you prevent it?
[0.20 | 5/5] What are the core functions of the AI RMF?          <- faithfulness/relevancy disagree
[1.00 | 2/5] What is LLM01?                                       <- retrieval failure (ID-like query)
[1.00 | 1/5] What does GDPR say about AI risk management?         <- correct refusal
[1.00 | 1/5] What's the best programming language for beginners?  <- correct refusal
```
Note: the judge scored correct refusals as low relevancy (1-2/5) - a defensible but debatable
interpretation (does explaining *why* you can't answer count as addressing the question?), worth
knowing as the judge's specific choice rather than an objective fact.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Deferred: `pipeline_hybrid.py` + comparative run against the semantic pipeline - good candidate
  for Saturday's Project 3 integration work, now that the real question ("does hybrid+rerank
  actually score measurably better on this corpus, formally, not just by eye") has a concrete
  harness ready to answer it.

## Practice task
Built `eval_metrics.py` (claim-based faithfulness scoring, LLM-as-judge answer relevancy) and
`run_eval.py` against a 5-question golden dataset covering a clear answerable question, a
known-tricky answerable question (AI RMF), a known retrieval-weak question (LLM01), and two known
refusals (GDPR, programming language). Found and fixed three real bugs (wrong collection, stale
threshold, hallucinating claim extractor) and surfaced two genuine findings the fixed harness
correctly caught (ungrounded-but-correct answer, ID-query retrieval failure). Located in
`week-03/day-13/practice/`.
# Day 27 - Automated evaluation: regression + A/B testing for prompts

**Date completed:** _(fill in)_

## What I learned

**Two new metrics, extending Day 13's harness**
- `context_precision` - deterministic, no LLM call. Of the sources actually retrieved, what
  fraction were genuinely relevant (checked against a golden set's `expected_sources`)? Cheap,
  but only checks source *files* - a mislabeled chunk inside a correctly-named source file is
  invisible to it entirely.
- `context_recall` - LLM-judged (same `response_format=Model` pattern as every other judge in
  `metrics.py`). Did retrieval find *enough* to answer, even with irrelevant or wrong content
  mixed in alongside the useful part? Deliberately tolerant of noise, by design (the prompt says
  so explicitly) - meaning it also can't catch mislabeled-but-present content.

**Confirmed directly, not just theorized**: ran both new metrics against the SummitCarry backpack
question, which has a known mislabeled tent-content chunk (Day 26's finding) sitting in its
retrieved context. Both metrics scored a clean 1.00 anyway - real content is present and
sufficient, so recall is satisfied, and the source file itself is correctly named, so precision is
satisfied. **Neither metric, as designed, can detect a mislabeled-but-present chunk** - a real,
honest limitation worth documenting, not a bug in today's implementation. Catching that class of
issue would need a different kind of check (e.g. "does each retrieved chunk's content actually
match its claimed topic"), not attempted today.

**A genuine new finding, not previously known**: the "What tent works for winter camping?"
question fails `context_recall` legitimately - not a data-labeling bug like the SummitCarry case,
but a real content gap. The catalog's only tent (AlpinePeak) is explicitly not rated for winter
conditions, so no product in the corpus actually satisfies the question. The model handled it
reasonably (explained the limitation rather than fabricating a recommendation), but honestly
still doesn't fully answer the question, which is exactly what `context_recall` correctly flagged.

**Golden set** (`golden_set.py`) - a fixed list of test questions with expected sources, the
shared foundation both regression testing and A/B testing need to compare against consistently.
Removed a duplicate, drifting list of plain-string test questions that had accumulated in
`run_eval.py` separately from this - the two were quietly out of sync (different wording, no
`expected_sources`) before consolidating to one source of truth.

**Regression testing** (`regression.py`) - saves eval scores as a baseline, flags any future run
where a metric drops by more than `REGRESSION_THRESHOLD` (0.1, an initial guess). The threshold
exists specifically to tolerate normal judge-model variance (see below) without constant false
alarms, while still catching a real, meaningful drop. Not yet calibrated against actual measured
run-to-run variance - noted as a real follow-up, not done today.

**A/B testing** (`ab_test.py`) - runs the same golden set through two differently-configured
pipelines (here: two different `FINAL_ANSWER_INSTRUCTION` variants) and compares real scores
side by side, rather than eyeballing a couple of sample answers.

## The real bug found while building the A/B test

**First A/B run produced meaningless results** - both variants returned near-identical text for
three of five questions, and `context_precision` read `0.00` across the board where it should
have varied. Root cause, traced precisely: `SemanticCache.check()` keys purely on the query's
embedding, with no awareness that a *different* pipeline configuration is asking. Variant A's run
cached its answers first; when Variant B ran the same questions moments later, it silently
received Variant A's old cached text back, never actually exercising its own new instruction at
all - except on the two tool-using questions, which are correctly excluded from caching by Day
24's design, and so were the only ones genuinely testing anything.

**The `prec 0.00` readings were a second, related symptom of the same root cause**: a cache hit
hardcodes `sources: []` (a known gap from Day 26 - sources were never captured in what gets
cached), and `context_precision`'s first line returns `0.0` whenever `retrieved_sources` is
empty - so every cached answer was mathematically guaranteed to score zero precision, unrelated
to actual retrieval quality.

**Fix**: added a `use_cache` constructor flag to `RAGPipeline`, defaulting to `True` for normal
use, set to `False` for both A/B test pipelines so each variant's real behavior is genuinely
exercised. Applied the flag to both `answer()` and `answer_stream()` - not because today's test
needed the streaming path, but because `use_cache` describes what a *pipeline instance* does, and
leaving it only half-wired would silently misrepresent that, the same shape of gap as Day 24's
original "forgot answer_stream() entirely" bug.

## The corrected A/B test - a live example of judge-model noise, caught in real data

With caching correctly bypassed, the StormShield/TrekLight question scored `faith 0.33` under
Variant A - a sharp drop from the `1.00` it scored in every other run today, despite Variant A's
and Variant B's actual answer text being essentially identical ("combined cost... is $278.00" in
both). Concluded this is very likely LLM-judge scoring noise rather than a real faithfulness
issue - a concrete, real instance of the exact judge-inconsistency problem discussed earlier in
the session as the reason `REGRESSION_THRESHOLD` needs to exist at all.

**The real, honest result**: the tent question - the one actually designed to test Variant B's
"explicitly flag when context doesn't fully answer" instruction - scored *worse* on relevancy
under B (0.80 -> 0.40), the opposite of the hypothesis. Plausible explanation: more explicit
hedging about a gap may read to a relevancy judge as less directly addressing the question, even
if it's the more honest response - a real, worth-documenting tension between honesty and
"directness" as a naive judge might score it.

**Concluded the test as inconclusive, deliberately, rather than oversell the aggregate averages**
(faithfulness 0.83 -> 0.96 looked like a clean win for B, but that swing is mostly explained by
the noisy StormShield outlier on a question where both variants' real output was nearly
identical). With n=1 per hypothesis-relevant question, neither "B is better" nor "B is worse" is
a defensible conclusion from this run alone - a legitimate, worth-reporting outcome rather than
forcing a winner.

**Also noted**: `context_precision` relies on `parsed.sources_used`, which is the model's own
self-reported list of sources from the final structured-output call - not a hard, independently
verified ground truth. Some of the precision variance seen between otherwise-similar runs may
stem from this self-reporting varying slightly, not from retrieval itself changing.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- How to properly calibrate `REGRESSION_THRESHOLD` against real, measured run-to-run judge
  variance rather than an initial guess - a genuine open follow-up
- Whether to add a genuine winter-rated tent SKU (or explicit "we don't currently carry one"
  language) to the corpus, given today's finding that no honest answer to that question exists
  in the current catalog

## Practice task
Added `context_precision` (deterministic) and `context_recall` (LLM-judged) to the evaluation
harness, plus a golden set, baseline-comparison regression checking, and an A/B test comparing two
`FINAL_ANSWER_INSTRUCTION` variants. Confirmed both new metrics correctly cannot detect Day 26's
mislabeled-content bug (a real, documented limitation) while independently discovering a genuine
new content gap - no tent in the catalog is actually winter-rated. Found and fixed a real bug
where the semantic cache silently invalidated the A/B test's independence between variants, adding
a `use_cache` flag applied consistently to both `answer()` and `answer_stream()`. Used a live,
in-session example of LLM-judge scoring inconsistency to ground the earlier discussion of why the
regression threshold needs to exist, and reported the corrected A/B test's result honestly as
inconclusive rather than overselling a noise-driven aggregate average.
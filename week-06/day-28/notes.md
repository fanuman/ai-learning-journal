# Day 28 - Fine-tuning fundamentals: fine-tune vs RAG vs prompt

**Date completed:** _(fill in)_

## What I learned

**Three ways to shape an LLM's behavior, and when each one is the right tool**
- Prompting - instructions per call. Zero setup, fully flexible, but re-sent and re-processed on
  every single request.
- RAG - inject external knowledge at query time (the whole `RAGPipeline`). Stays current without
  retraining, gives source attribution, but only ever adds context - can't change how the model
  fundamentally behaves or writes.
- Fine-tuning - actually adjusts the model's own weights via additional training. Genuinely
  changes default behavior, but costs real money to train and update, and doesn't reliably
  "memorize" new facts the way retrieval does.

**The core decision rule**: fine-tuning is a poor tool for adding new *knowledge* (that's RAG's
job - fine-tuning is expensive to update and unreliable at injecting specific facts). Fine-tuning
is a strong tool for consistent *behavior* - format, tone, or a pattern that's hard to fully pin
down via prompting alone, especially one you'd otherwise have to keep re-explaining in a growing
system prompt.

**They combine, not compete.** `RAGPipeline` already combines prompting + RAG; today's exercise
adds a genuine, well-motivated case for layering fine-tuning on top of both, rather than treating
the three as mutually exclusive choices.

## Today's exercise - grounded in a real finding from Day 27

Built a small fine-tuning dataset teaching a consistent response pattern for "no product in the
catalog actually satisfies this request" - directly motivated by Day 27's genuine finding that no
tent in the catalog is winter-rated, and the model's current handling of that case, while
reasonable, isn't backed by any consistent, deliberately-taught structure. This is a clean example
of the decision framework in practice: the problem isn't missing knowledge (RAG already correctly
surfaces the AlpinePeak tent's 3-season limitation) - it's an inconsistent *behavior pattern*
across every possible "no good match" scenario, which is exactly what fine-tuning is suited for
and what prompting alone struggles to nail down reliably.

12 training examples, each following the same three-part structure: acknowledge the gap honestly,
offer the closest real alternative if one exists, offer to help further - varied across different
out-of-catalog product categories (climbing gear, kayaks, ski equipment, running shoes, fishing
gear, mountaineering hardware, swimwear, bikes, drones, hunting gear, an oversized tent) so the
model would learn the general pattern rather than memorize one specific answer.

## Cost, understood precisely rather than assumed

**Confirmed directly (not assumed): `client.files.create(...)` is free.** No cost for uploading a
training file to OpenAI - that step is just storage. **The real cost is `client.fine_tuning.jobs.
create(...)`** - charged per training token, multiplied by the number of epochs (default 3, so
effectively tripling the token cost versus a single pass through the data). A fine-tuned model
also costs more per token at inference than the base model, ongoing, for every future call.

**Deliberate decision: did not submit the actual fine-tuning job today.** Given this is a small,
12-example illustrative dataset rather than a production-quality one (which would likely want
50-100+ varied examples), the real training cost wasn't worth spending for what would be a
minimal, not-fully-reliable behavioral improvement. `upload_and_train.py` structures this as an
explicit, commented-out decision point rather than something that could run by accident -
`upload_file()` runs and is free; `create_job()` stays commented until deliberately uncommented.

## Repo organization

New `src/finetuning/` module, matching the existing lowercase, single-responsibility convention
(`tools`, `rag`, `evaluation`, `core`, `api`):
- `training_data.py` - the training examples as Python, plus a `build_dataset()` function that
  writes them to JSONL
- `datasets/no_match_pattern.jsonl` - the generated dataset, small enough to commit and useful as
  documentation of what the model would be trained on even without ever training it
- `upload_and_train.py` - upload (runs) and job creation (guarded, commented out)

## Test results
- `python -m src.finetuning.training_data` -> wrote 12 examples cleanly
- `python -m src.finetuning.upload_and_train` -> uploaded successfully, real file ID returned
  (`file-LxhFWSAkuyswo27uAYGx1v`, 5625 bytes) - confirms the JSONL format passed OpenAI's
  validation, the main thing worth proving today without spending on an actual training run
- Renamed `check_status`'s local variable from `status` to `job` - the function returns the whole
  job object (id, model, status, fine_tuned_model, timestamps), not just a status string;
  `job.status` reads correctly where `status.status` was confusing

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether to eventually expand this to 50-100+ examples and actually run the job, now that the
  mechanism is proven to work end-to-end up through upload

## Practice task
Learned the decision framework for prompting vs RAG vs fine-tuning, with fine-tuning correctly
scoped as a tool for consistent behavior rather than new knowledge. Built a genuinely motivated
12-example training dataset addressing a real gap found in Day 27's evaluation work (inconsistent
"no good match" responses), organized into a new `src/finetuning/` module. Confirmed file upload
is free and fine-tuning job creation is the real cost boundary, and deliberately left the actual
training job unrun - proving the upload mechanism works without spending money on a dataset too
small to expect a meaningfully reliable production improvement from yet.
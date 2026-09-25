# Day 30 - Cost optimization: token tracking + a routing decision deliberately deferred

**Date completed:** _(fill in)_

## What I learned

**Token tracking and model routing are two separable problems, often conflated.** Tracking is
just turning `response.usage.prompt_tokens`/`completion_tokens` - already on every OpenAI response
- into an actual dollar figure and logging it somewhere. Routing is a separate decision: sending
different requests to different-cost models based on how much reasoning they actually need.
Today built the first properly and deliberately stopped short of the second.

**A genuinely useful trick for seeing a routing decision's value without paying for it**: since
routing savings are just arithmetic over token counts you already have, `cost/tracker.py` logs
what the *same* call would have cost under `gpt-4o`'s pricing alongside the real cost - without
ever calling `gpt-4o`. Real evidence for the routing argument (see Test results below), zero extra
spend. Decided against actually implementing routing today - see "Deliberate decision" below.

## Today's exercise

New `src/cost/` module (its own module, not folded into `core/` - same reasoning that gave
`evaluation/` and `finetuning/` their own space rather than crowding `core/`, which already holds
embeddings, vectorstore, secrets, and the semantic cache):
- `pricing.py` - a small per-model USD/1M-token table (`gpt-4o-mini`, `gpt-4o`,
  `text-embedding-3-small`) and `estimate_cost()`, the only place that turns tokens into dollars
- `tracker.py` - `cost_tracker.record(model, input_tokens, output_tokens, label)`, called after
  every OpenAI call, logs both the real cost and the hypothetical `gpt-4o` cost for the same
  tokens, appends to `logs/cost_log.jsonl`
- `report.py` - reads the persisted log file (not just one process's memory, so cost visibility
  survives across separate CLI/API runs) and prints totals, a real-vs-hypothetical comparison, and
  a breakdown by pipeline stage

Wired into `rag/pipeline.py` at three call sites: `_run_agent_loop()`'s per-iteration completion
call (label `agent_iteration`), `answer()`'s final structured-output call (label `final_answer`),
and `answer_stream()`'s streaming call (label `stream_answer`) - which needed
`stream_options={"include_usage": True}` added, since a streamed response doesn't include token
usage by default; it arrives as one extra chunk after the content, with `chunk.choices` empty and
`chunk.usage` set.

**Deliberately not tracked today**: `get_embedding()` calls (`text-embedding-3-small`), which run
at the top of both `answer()` and `answer_stream()`. Real cost, but embeddings are roughly two
orders of magnitude cheaper than a chat completion at this scale - a real gap, but not one that
would move today's numbers meaningfully.

## Deliberate decision: no actual model routing built today

Explicitly chose not to route any calls to `gpt-4o` - didn't want to spend on the more expensive
tier just to demonstrate the pattern. This shaped the whole day's design: instead of building
`choose_model()` and actually calling a stronger model on some queries, `cost/tracker.py` computes
the *hypothetical* cost of the same tokens at `gpt-4o` pricing alongside the real cost - pure
arithmetic on numbers already in hand from the real (cheap) call. Gets the actual point of
Day 30's lesson (cheap/expensive routing has a real, measurable payoff) without spending to prove
it. Whether to build real routing logic later - and what signal it should key off (a keyword
heuristic, a cheap classifier call, or a fallback-on-failure pattern that only escalates when the
cheap model's answer looks incomplete) - is left as an open question, not a bug.

## Test results

Ran four questions from the golden set through `/ask` (not the CLI - wanted to confirm cost
tracking works identically regardless of entry point):
```
What is the return policy?
What is the warranty policy?
Is the SummitCarry backpack in stock?
How much would the StormShield jacket and TrekLight poles cost together?
```

```
Total calls: 11
Actual cost (current model): $0.002678
Cost if every call had run on gpt-4o instead: $0.044633
Current setup is 16.7x cheaper than always using gpt-4o

By pipeline stage:
  agent_iteration: $0.001738
  final_answer: $0.000940
```

**The call count checks out exactly against the pipeline's real behavior**: 2 calls each for the
two simple RAG-only questions (one `agent_iteration` where the model decides no tool is needed,
then `final_answer`), 3 for the single-lookup tool question, and 4 for the StormShield/TrekLight
question - confirming its two tool calls happen **sequentially** (jacket, then poles, then a final
no-more-tools check), genuine multi-step ReAct behavior (Day 16's pattern), not a single batched
call. 2+2+3+4 = 11, matches exactly.

**`agent_iteration` costs almost twice `final_answer`** ($0.0017 vs $0.0009) despite there being
more `final_answer` calls in aggregate structure - each agent-loop iteration carries the growing
tool-call message history, while the final structured-output call is one clean pass.

**The real payoff number**: 16.7x cheaper than always using `gpt-4o` - concrete, real evidence for
why routing matters, obtained without a single `gpt-4o` API call.

## A real infra side-quest: hot-reload for local dev

Along the way, fixed a genuine friction point unrelated to cost tracking directly: `docker-compose.yml`
already bind-mounted `src/`, `data/`, and `logs/` into the `app` container, but the container still
ran the Dockerfile's plain `CMD` (no `--reload`), so code edits needed a full `--build` to take
effect. Added a `command:` override in `docker-compose.yml` instead of editing the Dockerfile
directly - the same Dockerfile is what CI/CD builds and pushes to ECR for the ECS/Fargate
deployment, so baking `--reload` into it would ship a dev-only file-watcher into production.
Compose's `command:` overrides the image's `CMD` for local runs only; ECS never reads
`docker-compose.yml` at all, so production stays untouched. One-line addition:
`command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload`.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- What signal should actually drive routing if it gets built later - a keyword heuristic (cheap,
  brittle, decides before knowing if a tool will really be needed), a dedicated cheap classifier
  call (more reliable, but itself a cost), or a fallback pattern (try cheap first, escalate only if
  the answer looks incomplete)
- Whether to also instrument `get_embedding()` calls for completeness, given they're real cost even
  if small at this scale

## Practice task
Built a standalone `src/cost/` module (pricing table, tracker, report) and wired real token-usage
tracking into all three OpenAI call sites in `RAGPipeline`, including the streaming path, which
needed `stream_options={"include_usage": True}` to expose usage at all. Deliberately skipped
building actual cheap/expensive model routing to avoid spending on `gpt-4o`, and got the same
lesson anyway by logging a hypothetical `gpt-4o` cost alongside every real call - confirmed a
16.7x cost difference across four real test questions run through the `/ask` endpoint, with the
exact call count (11) matching the pipeline's real agent-loop behavior. Also fixed a local-dev
friction point by adding a Compose-level `--reload` override, kept out of the Dockerfile itself
since that image is also what ships to production.
# Day 26 - LLM observability: tracing with LangSmith

**Date completed:** _(fill in)_

## What I learned

**Why observability matters more for LLM apps specifically**
Ordinary logging tells you a function ran with some args and returned something. An LLM app has
more worth capturing: the exact prompt after templating, which tools were called and what they
returned, how many agent-loop iterations it took, token counts, latency per step, and (since Day
24) whether a request was a cache hit. The value of this was concrete after last night's ECS
debugging session - hours spent manually parsing raw CloudWatch log lines and tracing a Python
stack trace by hand through five framework layers. LangSmith turns that into a structured,
visual trace instead.

**`@traceable`, not automatic LangChain tracing**
`RAGPipeline` is hand-built on raw OpenAI SDK calls (since Day 8), not LangChain - so the
near-automatic environment-variable-only tracing that would work for a LangChain pipeline doesn't
apply here. The standalone `langsmith` package's `@traceable` decorator wraps any Python function
and captures its inputs/outputs/timing, independent of LangChain.

**Nested traceable calls form a tree automatically** - decorating `answer()`, `retrieve()`, and
`_run_agent_loop()` produces one visual trace per request, with the nested calls appearing as
child spans under the top-level `rag_answer` span, matching the real call structure with no manual
wiring needed.

**Setup**: `pip install langsmith`, three env vars (`LANGCHAIN_TRACING_V2=true`,
`LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT=production-rag-agent` - the project name matters, without
it traces land in an unlabeled default project).

**Scope decision, deliberate**: only `answer()` (non-streaming) traced today. `answer_stream()`
uses `yield`; tracing a generator correctly needs more care than today's introduction covers -
noted as a real, honest gap rather than rushed.

## Real findings from actually reading full traces closely

**Testing note, not a bug**: repeatedly asking the SummitCarry backpack question and expecting a
cache hit was based on a misunderstanding, not a real issue - that question always triggers
`CheckAvailability`, and Day 24 deliberately excludes every tool-using answer from caching, by
design, every time. Confirmed cache hits work correctly using a pure-content question ("What is
your return policy?") instead - `from_cache: false` -> `from_cache: true` on the second call, with
`full_context` correctly present on the cached response too (Day 24's Option B design).

**Bug 1 - mislabeled content in `product_catalog.txt`**: the first chunk retrieved under the
"SUMMITCARRY 65L BACKPACK" header describes a *tent* - "Aluminum DAC poles," "rainfly providing
full weather protection," "Included: tent body, rainfly, poles, stakes, guy lines." Almost
certainly a copy-paste error from whichever tent entry this was drafted from. The final answer
came out correct anyway, because a second, genuinely backpack-related chunk and the live
`CheckAvailability` tool result both happened to override the corrupted content for this specific
question - but a differently-phrased question relying more heavily on that first chunk (e.g. "how
long does the SummitCarry backpack take to set up?") could plausibly produce a nonsensical
tent-based answer. Found only by reading the full trace's `full_context` closely, not from the
clean-looking final answer.

**Bug 2 - mislabeled content in `returns_policy.txt`/`warranty_policy.txt`**: a chunk headed
"REFUND TIMING" actually describes warranty-claim proof-of-purchase requirements, not refund
processing time - the same shape of bug as Bug 1, content that belongs under a different header
bleeding into the wrong section, likely a chunking-boundary or copy-paste issue.

**Both left unfixed today, deliberately** - noted here for a dedicated data-quality pass rather
than fixed reactively mid-lesson.

**A separate, minor design gap noticed while reviewing the cache-hit trace**: `sources` is always
empty (`[]`) on every cached response, permanently - `SemanticCache.store()`'s signature
(`prompt, response, query_embedding, full_context`) never captured `sources` in the first place,
so there's nothing to reconstruct it from on a hit. Not fixed today; noted as a known,
permanent characteristic of the current design rather than an intermittent bug.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether `sources` should be added to what gets cached (a real, small follow-up), and how
  `@traceable` would need to be adapted for `answer_stream()`'s generator-based flow

## Practice task
Set up LangSmith tracing on `RAGPipeline` via the standalone `@traceable` decorator (not
LangChain-based, since the pipeline is hand-built on raw OpenAI SDK calls), tracing `answer()`,
`retrieve()`, and `_run_agent_loop()` as a nested tree per request. Used real traces to find two
genuine data-quality bugs in the source corpus - content mislabeled under the wrong product/policy
header in each case - that a clean-looking final answer had been quietly hiding, plus one smaller
design gap (sources never captured in cached responses). Corrected a testing misunderstanding
about which questions can validly show a cache hit, tied directly back to Day 24's deliberate
tool-answer exclusion rule.
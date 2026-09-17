# Day 24 - Redis caching: semantic caching for LLM responses

**Date completed:** _(fill in)_

## What I learned

**Why semantic caching, not exact-match caching**
A plain cache keyed on the literal query string misses paraphrases ("Is the SummitCarry backpack
in stock?" vs "is summitcarry available?"). Semantic caching checks *meaning* instead - embed the
incoming query, and if it's close enough (cosine distance, the same concept used for every
retrieval threshold since Day 8) to a previously answered query, return that cached answer instead
of re-running the whole pipeline. Real payoff: skip an entire retrieval + generation round trip,
saving both latency and API cost.

**Redis needed a different image**
Plain `redis:7-alpine` (Day 21) has no vector search capability at all. Semantic caching needs
**RediSearch**, a module that adds vector KNN search inside Redis - switched to
`redis/redis-stack-server:latest`, same port, same protocol underneath.

**Two design decisions made deliberately, not skipped past**
1. Never cache an answer that used a tool (`CheckAvailability`, `CalculateTotal`) - these return
   live data (price, stock) that can genuinely change; caching them risks serving stale info for
   the whole TTL window.
2. Never cache a fallback or `hit_cap` (agent loop exhausted) response - a cached *failure* would
   become a **permanent** failure for every semantically similar future question, for the whole
   TTL, turning one bad answer into a recurring one.

## The SemanticCache class, in plain terms

```python
class SemanticCache:
    def __init__(self, host="redis", port=6379, threshold=0.05, ttl_seconds=3600):
        self.client = redis.Redis(host=host, port=port, decode_responses=False)
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self._ensure_index()
```
Runs once, when `self.cache = SemanticCache()` is created inside `RAGPipeline.__init__` - same
"connect once, reuse the connection" pattern as every other class this project.
- `decode_responses=False` matters specifically: an embedding is 1536 raw numbers stored as
  **binary bytes**, not text. Default decoding would try to treat everything as text and corrupt
  the embedding data.
- `threshold`/`ttl_seconds` saved onto `self` so every method can use them without being passed
  in again each time.

```python
    def _ensure_index(self):
        try:
            self.client.ft("cache_idx").info()
            return  # already exists
        except redis.exceptions.ResponseError:
            pass
        schema = (...)
        self.client.ft("cache_idx").create_index(...)
```
Same idea as `CREATE TABLE IF NOT EXISTS`. `.info()` asks "does this index already exist?" - if
yes, exit early. If not (throws an error, caught by `except`), create it. Necessary because
`RAGPipeline.__init__` (and therefore this method) runs again on every app restart - without this
check, every restart would try to create the same index twice and crash.

```python
    def check(self, query_embedding):
        vector_bytes = np.array(query_embedding, dtype=np.float32).tobytes()
        q = (Query("*=>[KNN 1 @embedding $vec AS distance]")
             .sort_by("distance").return_fields("response", "full_context", "distance")
             .dialect(2))
        results = self.client.ft("cache_idx").search(q, query_params={"vec": vector_bytes})
        if results.docs and float(results.docs[0].distance) <= self.threshold:
            return {"response": results.docs[0].response, "full_context": results.docs[0].full_context}
        return None
```
- `vector_bytes` - converts the query's embedding (a plain Python list of numbers) into the raw
  binary format Redis's vector search expects. Must be `float32` specifically, matching what
  was stored.
- The query string is Redis's own query language: `*` = consider every cached entry, `KNN 1` =
  find the single nearest neighbor (not a list to filter through - Redis already sorts and picks
  the closest one internally before Python ever sees a result), `@embedding` = which field to
  search, `$vec` = placeholder for the real vector, `AS distance` = name the result field.
- `.dialect(2)` - required. RediSearch's query syntax has versions ("dialects"); version 1
  predates vector/KNN search entirely and can't parse this query at all. Without this, the query
  fails outright, not just behaves oddly.
- `results.docs[0]` - `results.docs` has at most one item, since `KNN 1` already asked for exactly
  one match. The `[0]` is just how the list-shaped return value works, not a real "choice" between
  multiple candidates - the actual nearest-neighbor decision already happened inside Redis.
- The `if` check is the real decision point: is this one closest match *actually* close enough to
  count, or just the least-bad thing Redis could find? Same judgment call as every retrieval
  threshold this project has used.

```python
    def store(self, prompt, response, query_embedding, full_context=""):
        key = f"cache:{uuid.uuid4().hex}"
        self.client.hset(key, mapping={
            "prompt": prompt, "response": response, "full_context": full_context,
            "embedding": np.array(query_embedding, dtype=np.float32).tobytes(),
            "created_ts": int(time.time()),
        })
        self.client.expire(key, self.ttl_seconds)
```
- `cache:{uuid}` - a random unique key name. Random is fine here (unlike Chroma's content-derived
  chunk IDs) since cache entries don't need stable, content-based IDs. The `cache:` prefix matters
  because `_ensure_index` told Redis to only watch keys with that exact prefix.
- `hset` writes a Redis **Hash** (like a dictionary/record) with all the fields needed to both
  answer a future cache hit and search on it later.
- `expire(key, ttl_seconds)` - Redis automatically deletes this entry after the TTL, no manual
  cleanup code needed. This is what keeps the cache from serving increasingly stale answers
  forever.

## Bugs found and fixed

1. **`ModuleNotFoundError: No module named 'redis'`** - forgot to add `redis` to
   `requirements.txt`, the same class of bug as Day 18's `boto3` and Day 19's `pytest`: a
   dependency that happened to be available locally but was never declared for the actual
   container build. Noted this as now a *recurring* pattern worth a standing habit: check
   `requirements.txt` immediately after adding any new import, not after a failed build.
2. **f-string quote collision**: `f"data: {cached["response"]}\n\n"` - both the outer f-string and
   the inner dict access used double quotes, a genuine syntax error. Fixed with single quotes
   inside: `f"data: {cached['response']}\n\n"`.
3. **`answer_stream()` initially had no caching logic at all** - only the non-streaming `/ask`
   endpoint had it wired in, meaning the actual browser frontend (which uses `/ask/stream`) would
   have gotten zero benefit from today's whole feature. Added the same check/store logic,
   accumulating the full reply via `full_reply += delta` as tokens stream out, since a streaming
   response has no single "final answer" variable unless built manually.
4. **`RagResponse` never exposed `from_cache`** - the pipeline returned it correctly, but the
   Pydantic response model (defined before caching existed) had no field for it, so it was
   silently dropped before reaching the API response. Added `from_cache: bool = False` to
   `RagResponse` in `api/models.py` and threaded it through in `api/main.py`.
5. **The Day 21 collection-caching bug resurfaced in practice**, not just in theory - re-running
   `ingest.py` against an already-running app container caused the exact same "Collection does not
   exist" error documented back then. Fixed the same way (`docker compose restart app`) - now a
   second real, practical confirmation that leaving this as a documented "restart required"
   behavior (rather than fetching the collection fresh per query) has a real, recurring cost.

## The threshold investigation - a real, converged finding

Tested whether `0.05` was too conservative, using two different real paraphrase pairs against one
genuinely different topic:
```
"return policy" vs "how do returns work" (paraphrase)          -> distance 0.4524
"return policy" vs "warranty policy" (should be a miss)         -> distance 0.2968
"return policy" vs "refund on tried-on gloves" (paraphrase)      -> distance 0.5478
```

**Both paraphrases scored farther away than the genuinely different topic** - the ordering needed
for a working threshold is inverted, not just imprecise. No single threshold value could catch
either paraphrase as a hit without also catching the warranty question as a false hit, which would
mean serving a customer the wrong cached policy entirely - a correctness failure, strictly worse
than the current "sometimes slower than ideal" behavior.

**Decision: kept the threshold at `0.05`, documented as a deliberate trade-off, not a bug to keep
chasing.** Semantic caching here intentionally favors safety (some real paraphrases miss the
cache, a latency/cost loss) over recall (never risk serving a wrong cached answer, a correctness
loss). Root cause: short, topically-adjacent policy questions can share more surface vocabulary
("return," "policy," "items") with an unrelated topic than two genuine paraphrases share with each
other - a real, general limitation of raw embedding-distance caching, not specific to this corpus.

## Test results
- Repeat question: `from_cache: false` -> `from_cache: true`, confirmed via Redis (`KEYS cache:*`
  showing a real stored entry) and a noticeably faster response
- Paraphrase ("how do returns work"): correctly missed at the current threshold - later explained
  and justified by the distance investigation above
- Genuinely different question (warranty): correctly missed, correct real answer retrieved
- Tool-using question (SummitCarry backpack), asked twice: `from_cache: false` both times -
  confirmed live-data answers are never cached, as designed

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
Switched Redis to `redis-stack-server` for vector search support. Built a `SemanticCache` class
(index creation, KNN-based lookup, hash-based storage with TTL) and wired it into both `answer()`
and `answer_stream()`, deliberately excluding tool-using and fallback/failed answers from caching.
Found and fixed five real bugs (a missing dependency, a quote-collision syntax error, missing
streaming-path caching, a missing response-model field, and a recurrence of Day 21's known
collection-caching issue). Investigated a real cache-miss case with actual distance measurements
across two independent paraphrase pairs, confirmed the ordering was fundamentally inverted rather
than just miscalibrated, and made a deliberate, justified decision to keep the threshold
conservative rather than loosen it.
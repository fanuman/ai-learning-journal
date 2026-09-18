# Day 25 - Rate limiting + load testing with Locust

**Date completed:** _(fill in)_

## What I learned

**Why rate limiting matters here specifically**
Every `/ask` request costs real OpenAI money. A buggy client stuck in a retry loop, or a
malicious script hammering the API, could rack up real cost fast - rate limiting defends against
that, the same cost-consciousness theme as this whole roadmap, now applied to defending against
the API's own abuse potential rather than personal usage.

**`slowapi` and why it needs Redis, not in-memory storage**
```python
limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379/0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
```
Without `storage_uri`, `slowapi` defaults to in-memory counting - which silently breaks the
moment the app runs as more than one instance (recall ECS's "desired count" from Day 22): each
replica would track its own separate counter, letting a client through `N x replica-count`
requests instead of `N`. Redis-backed counting is shared state, correct regardless of how many
app instances exist - reused the same `redis-stack-server` container from Day 24, different key
prefix internally, no conflict with the semantic cache sharing the same Redis instance.

**Route functions need `request: Request` as a parameter** - `slowapi` needs the raw request
object to identify the client (by IP, via `get_remote_address`). A real signature change, not
optional boilerplate.

**Bug found**: initially wired up all the rate limiter infrastructure (Limiter, exception handler,
middleware, and changed every route to accept `Request`) but forgot to actually add
`@limiter.limit(...)` to any route - meaning rate limiting was fully configured but not actually
active anywhere. Added `@limiter.limit("10/minute")` to `/chat`, `/ask`, and `/ask/stream`.
Deliberately left `/health` and `/cost` unlimited - free to serve (no OpenAI call, no real cost),
and shouldn't trip a limit meant to protect expensive endpoints.

## Confirming rate limiting directly, before Locust

```bash
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"message": "What is your return policy?"}'; done
```
Result: 10 consecutive `200`s, then `429` starting exactly on the 11th call. Precise confirmation
the Redis-backed counter tracks real request counts exactly, not approximately - `10/minute` means
10 allowed, the 11th is the first rejection.

## Locust - what it is and why it matters here

Every test this whole project has been one request at a time - a single `curl`, a single browser
message. Locust simulates many real users making requests **simultaneously**, which is the only
way to actually prove rate limiting and caching hold up under real concurrent traffic rather than
just trusting the code in isolation.

### The locustfile, explained line by line

```python
# locustfile.py
from locust import HttpUser, task, between

class TrailPeakUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def ask_policy_question(self):
        self.client.post("/ask", json={"message": "What is your return policy?"})

    @task(1)
    def ask_product_question(self):
        self.client.post("/ask", json={"message": "Is the SummitCarry backpack in stock, and what does it cost?"})

    @task(1)
    def health_check(self):
        self.client.get("/health")
```

- **`class TrailPeakUser(HttpUser)`** - defines what one *simulated user* does. Locust spins up
  many independent copies of this class at once, each acting as a separate concurrent visitor to
  the app.
- **`wait_time = between(1, 3)`** - after each action, a simulated user pauses somewhere between 1
  and 3 seconds before doing its next action, chosen randomly each time. This mimics a real
  person's think-time between messages rather than a script hammering the API with zero delay,
  which wouldn't resemble real traffic at all.
- **`@task(3)` / `@task(1)`** - these numbers are *relative weights*, not counts. A task weighted
  `3` is three times more likely to be picked than one weighted `1` whenever a simulated user
  decides what to do next. Here, the return-policy question gets chosen roughly 3x as often as
  the product question or the health check - simulating realistic, uneven traffic (some questions
  really are more common than others) instead of every possible action being equally likely.
- **`self.client.post(...)` / `self.client.get(...)`** - `self.client` is Locust's own built-in
  HTTP client, already configured to hit whatever `--host` was passed on the command line. Using
  it (instead of, say, `requests.post`) is what lets Locust automatically measure and report the
  response time and success/failure of every single call across every simulated user.

### Running it

```bash
pip install locust
locust -f locustfile.py --host=http://localhost:8000
```
Opens a web UI at `localhost:8089` - set a number of simulated users and a spawn rate, click
start, and watch live response times, failure rates, and requests/sec update in real time as the
test runs.

**Important, non-obvious networking detail, predicted before running and then confirmed**: since
Locust and the app both run on the same machine, every simulated user shares one real source IP.
`get_remote_address` treats them all as a single client - meaning the `10/minute` limit applies to
the *combined* traffic of every simulated user together, not 10-per-simulated-user. This is
actually the correct, realistic thing to test: it's exactly what a single real high-traffic
client, or an attacker, would experience.

## Locust results and what they actually show

| Type | Requests | Fails | Median | 95%ile | 99%ile | Average |
|------|----------|-------|--------|--------|--------|---------|
| POST /ask | 37 | 27 | 6ms | 4400ms | 4800ms | 584.84ms |
| GET /health | 13 | 0 | 5ms | 11ms | 11ms | 4.99ms |

**The shared-IP prediction confirmed precisely, not approximately**: 37 total `/ask` requests, 27
failures - exactly 10 successes, matching the `10/minute` limit exactly. Real, direct proof of the
earlier reasoning about shared source IPs.

**The median (6ms) is genuinely misleading, worth understanding why rather than trusting it at
face value.** A `429` rejection is essentially instant - `slowapi` checks the Redis counter and
refuses before the request ever reaches retrieval or OpenAI at all. With 27 of 37 `/ask` requests
being these near-zero-cost rejections, they dominate the median completely. **The 95th/99th
percentiles (4400-4800ms) are the honest picture of what a real, successful `/ask` call actually
costs** - a full embedding + retrieval + LLM generation round trip, several seconds, consistent
with every prior manual test this project.

`/health` stayed fast and fully unaffected (0 failures, 4-11ms) - confirms the earlier decision to
leave it unrated-limited is working as intended.

## A real, honest limitation surfaced by this specific test run

With only 10 successful `/ask` calls total, there wasn't enough real traffic volume to clearly
observe Day 24's caching behavior within the successful requests - the tight rate limit cut off
traffic before enough repeated policy-question calls could accumulate to show an obvious
"cache hits are fast, cache misses are slow" split. **Testing rate limiting and testing caching
under load genuinely pull in opposite directions**: a tight limit proves rate limiting works
quickly (fewer requests needed to see a rejection), but starves the test of the volume needed to
properly exercise caching (which needs many successful, repeated requests to show its effect).

**Follow-up identified but not yet run**: temporarily loosen the limit (e.g.
`@limiter.limit("100/minute")`) for a dedicated caching-under-load test, rerun Locust, and check
whether the *successful* `/ask` calls show their own bimodal split (fast cache hits vs. slow cache
misses) this time. Left as a deliberate next step rather than rushed into the same test run.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether to run the loosened-limit follow-up test today or treat it as a distinct future
  exercise - noted above, not yet decided

## Practice task
Added Redis-backed rate limiting (`slowapi`) to `/chat`, `/ask`, and `/ask/stream`, deliberately
leaving `/health` and `/cost` unlimited. Found and fixed a real gap where the limiter
infrastructure was fully wired up but never actually applied to any route. Confirmed exact
rate-limit behavior via a sequential curl loop (10 successes, then 429 starting precisely on the
11th call). Built a Locust load test simulating weighted, realistic traffic with think-time
between actions, and used it to prove - under genuine concurrent load rather than a single manual
request - that the shared-IP rate-limiting behavior works exactly as predicted, and that the
misleadingly low median response time is an artifact of many instant rejections rather than a
sign the app itself is fast. Identified a real, honest tension between testing rate limiting and
testing caching under the same load profile, and deferred a loosened-limit follow-up test as
deliberate next work rather than rushing it into today's session.
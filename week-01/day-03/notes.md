# Day 3 - Production API wrapper (retries, rate limits, error handling, cost tracking)

**Date completed:** _(fill in)_

## What I learned

**Three categories of failure, not two**
- **Transient** - request reached the API, server had a temporary issue (rate limit, timeout,
  5xx). Worth retrying, ideally with backoff.
- **Permanent** - request reached the API, rejected for a reason that won't change on retry (bad
  request, invalid model name, auth failure). Fail fast, don't retry.
- **Configuration** - request never even reached the API (e.g. missing API key). Not really
  transient or permanent in the API-error sense - it's a local setup problem that should be
  checked once at startup (`__init__`), not inside the retry loop. Retrying it is pointless in
  the same way retrying a permanent error is.

**Exponential backoff with jitter**
If a call fails, wait before retrying - and wait longer each time it fails again (double the
delay). Add a small random amount ("jitter") on top so that if many requests fail at once, they
don't all retry at exactly the same moment and cause a fresh spike.

**The SDK already retries some things automatically**
The OpenAI Python client has built-in retries (default: 2) for transient errors. Our custom
wrapper isn't replacing that - it's adding visibility (logging what's happening and why) and cost
tracking on top of it.

## Code I wrote

Built `ProductionLLMClient` in `day3_production_wrapper.py`:
- `__init__` checks for `OPENAI_API_KEY` up front and fails with a clear message if missing -
  this is the "configuration error" category, handled before any API call is attempted
- `chat()` wraps `client.chat.completions.create()` in a retry loop: transient errors
  (`RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError`) trigger
  exponential backoff and retry; other recognized errors fail immediately
- `_calculate_cost()` computes real cost per call from `response.usage`, using OpenAI's actual
  per-token pricing (not a tiktoken estimate)
- `report()` prints total calls, total retries, and cumulative estimated cost across the whole
  session

**Design discussion: redundant exception types.** Initially wrote:
```python
except (AuthenticationError, BadRequestError, OpenAIError) as e:
```
`AuthenticationError` and `BadRequestError` are both subclasses of `OpenAIError`, so listing them
separately was redundant - `except OpenAIError:` alone already catches both. The bigger issue:
this made the "permanent" branch a silent catch-all for *any* OpenAI error not in the transient
list, including ones never explicitly considered. Resolved by testing what error actually occurs
(see below) and being explicit about it instead of relying on a catch-all.

**Real finding: invalid model name raises `NotFoundError`, not `AuthenticationError` or
`BadRequestError`.** Assumed a typo'd model name would hit one of the two "obvious" permanent
error types - it didn't. It came back as a 404 `NotFoundError` ("model does not exist"). Without
having tested this for real, the original exception list would have let this specific error slip
past uncaught. Fixed by explicitly adding `NotFoundError` to the permanent-error tuple. Lesson:
verify actual error types by triggering them, don't assume based on what seems logical.

**Print-then-raise is intentional, not a bug.** Both error branches print a clean log line *and*
still `raise` (or let the exception propagate), so the full traceback still shows for deep
debugging even though there's also a readable one-line summary. This is a deliberate production
pattern - swapping `raise` for `return None` would let the script continue instead of crashing,
but crash-with-context is usually the right call for a genuine failure.

## Test results

**Permanent error (invalid model name `gpt-4o-mini-typo`):**
```
Permanent error, not retrying: Error code: 404 - {'error': {'message': 'The model
`gpt-4o-mini-typo` does not exist or you do not have access to it.', ...}}
```
Failed immediately, no retries, full traceback preserved below the clean log line - all correct.

**Transient error (forced via `timeout=0.01`):**
```
Transient error (APITimeoutError), retrying in 1.7s (attempt 1/4)
Transient error (APITimeoutError), retrying in 2.4s (attempt 2/4)
Transient error (APITimeoutError), retrying in 4.9s (attempt 3/4)
Failed after 4 attempts: Request timed out.
```
Verified the backoff math against `base_delay=1.0`, `wait = base_delay * 2^attempt + jitter(0-1)`:
- Attempt 0: expected 1.0-2.0s -> got 1.7s (matches)
- Attempt 1: expected 2.0-3.0s -> got 2.4s (matches)
- Attempt 2: expected 4.0-5.0s -> got 4.9s (matches)

All three within expected range - backoff doubling and jitter both working correctly.

**Normal run (3 successful calls):**
```
Four.
Nine.
Eleven.
Total calls: 3 | Retries: 0 | Estimated cost: $0.000017
```
Correct answers, zero retries (as expected with no errors), and a real non-zero cost computed
from actual `response.usage` token counts rather than an estimate - confirms the cost tracking
math is wired correctly end to end.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
`day3_production_wrapper.py` - `ProductionLLMClient` class with exponential backoff retries for
transient errors, fail-fast handling for permanent errors and missing API keys, and per-call cost
tracking. Verified all three failure paths (config, permanent, transient) plus a normal
multi-call run with cost reporting. Located in `practice/`.
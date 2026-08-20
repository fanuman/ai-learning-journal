# Day 5 - Python packaging, secrets management, wrap wrapper in FastAPI

**Date completed:** _(fill in)_

## What I learned

**Secrets management, done properly**
`load_dotenv()` belongs in the application's entrypoint (`main.py`), not inside a reusable class
like `ProductionLLMClient`. A class quietly loading files as a side effect of being instantiated
makes it harder to reuse/test - the entrypoint is responsible for environment setup, classes just
assume `os.getenv()` already has what it needs by the time they run.

**Packaging - pin dependencies**
`pip freeze > requirements.txt` captures exact installed versions instead of loose package names.
Matters because an unpinned library update could silently change behavior; pinning means anyone
(including future-me on a new machine) gets the exact same versions that were actually tested.
Noted `pyproject.toml` + Poetry/uv as the more advanced standard for larger projects (dependency
resolution, lockfiles) - not needed yet at this project's scale.

**FastAPI wraps the wrapper**
Turned the Day 3 `ProductionLLMClient` from a script into a real HTTP service:
- `GET /health` - liveness check (the pattern load balancers/orchestrators use later in AWS/K8s)
- `POST /chat` - main functionality, request/response validated via Pydantic models
- `GET /cost` - exposes `.report()`'s data as JSON instead of a print statement

**The `lifespan` pattern**
`llm_client` is created once at server startup (inside `lifespan`), not per-request. Confirmed
this is actually working (not just assumed) by checking `total_cost` matched exactly between a
`/chat` call and a following `/cost` call - proof the same client instance is persisting state
across requests, not being recreated each time.

**FastAPI is the framework, uvicorn is the server**
FastAPI handles routing/validation; `uvicorn main:app --reload` is what actually listens on a
port and serves real HTTP traffic. `/docs` gives a free interactive UI for every endpoint.

## Bugs found and fixed

**Duplicate function name (`chat` used twice).** Two endpoint functions were both named `chat` -
worked correctly at runtime because FastAPI's decorator captures the function object at
definition time, before the name gets reassigned. But this only worked by accident of execution
order - a linter would flag it (`F811`), and reordering the functions or importing `chat`
elsewhere would break silently. Fixed by renaming the second to `get_cost`.

**`return HTTPException(...)` instead of `raise`.** `HTTPException` isn't a response object, it's
a signal FastAPI's framework code watches for via `raise`. Returning it instead means FastAPI
treats it as a normal successful return value and tries to validate it against `response_model
=ChatResponse` - which fails (no `reply`/`total_cost` fields), producing a confusing
`500 ResponseValidationError` instead of the intended clean `502`. One-word fix (`raise` instead
of `return`), completely different behavior. Verified fixed by deliberately triggering a bad
model name and confirming a real `502` came back with the intended error message.

**`total_calls`/`total_retries` typed as `float` instead of `int`.** Pydantic silently coerces
ints to floats with no error, so nothing crashed - but the API would return `3.0` instead of `3`
for a count, which reads oddly to any consumer. Fixed both fields to `int` in `models.py`.

## Code structure

Split into `models.py` (Pydantic request/response models: `ChatRequest`, `ChatResponse`,
`ChatMetaData`) and `main.py` (FastAPI app, `lifespan` startup, three endpoints). Cleaner
separation than cramming everything into one file - worth continuing this pattern as the app
grows in later weeks.

## Test results

- `GET /health` -> `{"status": "ok"}`
- `POST /chat` -> `{"reply": "Hello! How can I assist you today?", "total_cost": 0.0000081}`
- `GET /cost` -> `{"total_calls": 1, "total_retries": 0, "total_cost": 0.0000081}` - cost matches
  `/chat`'s exactly, confirming the `lifespan`-created client persists state across requests
- **502 test** (deliberately broke the model name) -> real `502` status with the actual OpenAI
  error message in `detail` - confirms `raise HTTPException` fires correctly, not the generic
  crash or validation error seen before the fix
- **422 test** (sent `{"msg": "hi"}` instead of `{"message": "hi"}`) -> automatic, structured,
  field-level error from Pydantic (`type: missing`, `loc: [body, message]`, echoes back what was
  sent) - generated entirely for free, no validation code written manually. Good contrast against
  the 502: one is framework-generated and field-specific, the other is a string I constructed
  myself for a downstream failure.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
Built `main.py` (FastAPI app with `/health`, `/chat`, `/cost`) and `models.py` (Pydantic
request/response schemas) wrapping the Day 3 `ProductionLLMClient`. Pinned dependencies via
`pip freeze > requirements.txt`. Verified all three endpoints, the `lifespan` singleton pattern,
and both error paths (502 for downstream API failure, 422 for malformed requests). Located in
`practice/`.
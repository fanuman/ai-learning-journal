# Day 21 - Docker Compose: multi-container apps (app + vector DB + Redis)

**Date completed:** _(fill in)_

## What I learned

**Why Compose, and why today specifically moves Chroma to server mode**
Every deploy through Month 1 ran Chroma in *embedded* mode - `PersistentClient(path=...)`, reading
and writing local files baked directly into the app's own container. That's fine for one instance,
but it means each container would hold its own separate, potentially-inconsistent copy of the
vector index if more than one ever ran side by side (relevant for Day 22's ECS deployment).
Docker Compose coordinates multiple containers defined in one file; today's real architectural
shift is running Chroma as its own standalone server, so any number of app instances can share one
real source of truth instead of each embedding its own copy.

**Chroma server mode vs. embedded mode**
`chromadb.PersistentClient(path=...)` (embedded, local files) replaced with
`chromadb.HttpClient(host=..., port=...)` (networked, talking to a separate Chroma server
process). The server itself runs via `chroma run --host 0.0.0.0 --port 8001 --path /chroma_data`.

**Compose networking basics**
Services in the same `docker-compose.yml` get automatic DNS names matching their service name -
`chroma` and `redis` are reachable by those exact hostnames from any other service in the file, no
IP addresses needed. Named volumes (`chroma_data:`) persist data independently of any container's
lifecycle, replacing the old approach of baking `chroma_db/` into the image itself.

**Refactor: centralized `get_chroma_client()` in `vectorstore.py`**
Moved `ingest.py`'s ad-hoc collection-delete logic into `vectorstore.py` as a shared
`delete_collection()` function, built on one shared `get_chroma_client()`. This wasn't just
tidiness - it fixed a real bug: `ingest.py`'s delete block was still using the *old* embedded
`PersistentClient(path=CHROMA_PATH)`, completely disconnected from the new networked Chroma server
the rest of the app now talks to. It was silently checking/deleting against local files the
running Chroma server never touched at all.

## Real bug found and understood (left as a known, documented trade-off)

**Symptom:** after re-running `ingest.py` against an already-running app (`docker compose up`
already active), `/ask` failed with `Collection [uuid] does not exist.` - despite ingestion itself
reporting success and a correct chunk count.

**Root cause:** `RAGPipeline.__init__()` calls `get_collection()` once at construction and caches
that reference for the app's entire lifetime (confirmed directly in Chroma's own server logs - a
`POST .../collections` call visible at app startup). `ingest.py`'s `delete_collection()` deletes
that exact collection and `get_collection()` then creates a **new one with a different internal
UUID**. The already-running app's cached reference still points at the old, now-deleted UUID -
Chroma correctly reports it as gone, since it genuinely is.

**Why this never surfaced before:** every previous workflow ran ingestion *before* starting the
app - never against an app that was already live and had already cached a collection reference.
Compose's long-running `app` service, combined with re-ingesting from a separate terminal, is the
first time this specific sequence was actually exercised.

**Fix applied:** restart the app container after re-ingesting
(`docker compose restart app`) - confirmed this resolves it, re-verified against the same
known-good SummitCarry backpack test question.

**Deliberate decision, not an oversight:** considered fetching the collection fresh per query in
`retrieve()` instead of caching it at `__init__` (would make re-ingestion take effect immediately,
no restart needed, at the cost of one extra lightweight network call per request). Chose to keep
the current cached-reference behavior for now and document the restart requirement explicitly
rather than make the change today - tracked in `ai-learning-journal`'s known issues list, worth
revisiting before Day 22's multi-instance ECS deployment makes "just restart the one app
container" a less convenient workaround than it is today.

## Test results
- Compose logs confirmed real cross-container networking: the app's first action at startup was a
  series of HTTP calls to `http.host: chroma:8001`, proving DNS resolution and network reachability
  across containers, not local file access
- Ingestion against the running stack (`CHROMA_HOST=localhost CHROMA_PORT=8001 python -m
  src.ingest`) correctly reported the delete-and-rebuild cycle and a 36-chunk count
- `/ask` returned the correct, known-good SummitCarry backpack result ($249.00, out of stock)
  after restarting the app to pick up the fresh collection reference
- Redis confirmed reachable via `redis-cli ping` → `PONG` - no caching logic wired up yet
  (Day 24's job), today only required proving connectivity

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Removed the obsolete `version:` key from `docker-compose.yml` - modern Compose infers the file
  format automatically and warns if it's still present

## Practice task
Converted the single-container deployment into a three-service Docker Compose stack: the FastAPI
app, a standalone Chroma server (replacing embedded-mode `PersistentClient`), and Redis
(connectivity-only, no caching logic yet). Centralized Chroma client construction in
`vectorstore.py`, fixing a real bug where `ingest.py`'s delete step was still using the old,
disconnected embedded client. Found, diagnosed, and understood a genuine collection-caching bug
exposed specifically by Compose's long-running-service model, and made a deliberate, documented
decision to leave it as a known restart-required behavior rather than fix it today. Verified the
full stack end-to-end against the same known-good test question used throughout this project.
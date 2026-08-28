# Day 10 - Managed vector DB: Pinecone (local Chroma vs. managed, hands-on Pinecone)

**Date completed:** _(fill in)_

## What I learned

**Why move beyond local Chroma**
Local Chroma stores vectors in a folder on one machine - fine for learning, but breaks down once
deployed: container filesystems are often ephemeral (a redeployed Docker container can lose local
disk data), multiple running instances can't safely share one local file, and someone has to
operate backups/scaling/availability. A managed vector database solves this - someone else runs
the servers, you just call an API from anywhere.

**Two managed options**
- **Pinecone** - purpose-built, fully managed vector DB-as-a-service. No infrastructure to think
  about at all.
- **pgvector on AWS RDS** - adds vector search to a normal Postgres database. Popular specifically
  when a team already runs Postgres for other data (one system to manage, can join vector search
  with relational data), but requires managing/tuning the Postgres instance yourself.

**Scoping decision:** since AWS fundamentals (IAM, RDS) aren't covered until Week 4, did hands-on
work with Pinecone only today; pgvector-on-RDS hands-on deferred to the post-roadmap exploration
list alongside FAISS.

**Pinecone basics, and key differences from Chroma**
- `pc.create_index(name, dimension, metric, spec=ServerlessSpec(...))` - creates an index (~=
  Chroma's collection)
- `index.upsert(vectors=[(id, embedding, metadata_dict), ...])` - Pinecone does **not** store
  original text automatically like Chroma does - must put it in `metadata` manually
- `index.query(vector=..., top_k=..., include_metadata=True)` - `vector` takes the flat embedding
  directly, NOT wrapped in a list (unlike Chroma's `query_embeddings=[...]`)
- Results are accessed via **attributes** (`results.matches`, `match.score`, `match.metadata`),
  not dict keys like Chroma
- **`match.score` is a similarity (higher = better)**, opposite direction from Chroma's cosine
  *distance* (lower = better) - same cosine math, inverted scale. Threshold comparisons must flip
  accordingly (`<=` instead of `>=`).
- Delete operations: `pc.delete_index(name)` (whole index, ~= Chroma's `delete_collection`),
  `index.delete(ids=[...])` (specific records), `index.delete(delete_all=True, namespace=...)`
  (everything in a namespace). Serverless indexes do **not** support deleting by metadata filter -
  only by ID or full namespace wipe.

## Code I wrote and bugs fixed

Rebuilt Day 8's `retrieve()`/`build_prompt()`/`generate_answer()` pipeline against Pinecone
instead of Chroma, reusing the same Acme Corp documents.

**Bug 1:** `index.query(vector=[query_embedding], ...)` - wrapped the embedding in an extra list.
Pinecone's `vector` parameter expects the flat embedding directly. Fixed to
`vector=query_embedding`.

**Bug 2:** `build_prompt(query, results.matches)` - passed match objects directly into a function
expecting strings (`"\n\n".join(chunks)` requires actual strings). Fixed by extracting text first:
`chunks = [match.metadata["text"] for match in results.matches]`.

**Correctly applied on the first attempt:** flipped the threshold comparison to
`if all(match.score <= 0.5 ...)` to match Pinecone's similarity-not-distance scoring - correct
adaptation of the Day 8 pattern to a different tool's convention.

## The networking investigation

A large part of today ended up being real infrastructure debugging rather than RAG content -
documenting the process since the diagnostic method is worth remembering on its own.

**Symptom:** `index.upsert()` consistently failed with
`PineconeConnectionError: [Errno 54] Connection reset by peer`, failing specifically during the
TLS handshake (`start_tls`), while index creation (a different, control-plane API call) succeeded
fine.

**Diagnostic steps, in order:**
1. Confirmed via Pinecone's dashboard that the index really was created successfully - isolating
   the failure to specifically the data-plane call (upsert/query to the per-index host), not
   Pinecone generally.
2. Tested the exact failing host with `curl -v` outside of Python entirely - failed identically,
   ruling out anything Python/SDK-specific (certificates, library bugs).
3. Investigated Cloudflare WARP as the suspect (also connects back to an unexplained Cloudflare
   IP that hit the Docker container back on Day 5 Week 1) - found the WARP daemon still running
   as a root-owned background process even after "quitting" the app from the menu bar; disabled
   it via Login Items & Extensions, fully restarted the machine. `curl` still failed identically
   afterward, ruling WARP out as the cause despite being a strong initial suspect.
4. Found an unidentified third-party "Firewall" app listed (inactive-looking) in Network settings
   - not yet identified by name, flagged for follow-up.
5. **Root cause confirmed via a targeted code fix**, not just further guessing: a monkey-patch
   stripping the SNI (Server Name Indication) field from the TLS handshake specifically for
   `pinecone.io` hosts made the connection succeed. SNI is the part of the *unencrypted* TLS
   ClientHello that names the target hostname in plain text - the fact that removing only that
   field fixed the connection is conclusive proof that something on the network was reading that
   plaintext hostname and resetting the connection for not matching an allowed pattern. Almost
   certainly the unidentified Firewall app from step 4, using SNI-based filtering (a common
   mechanism for consumer security/parental-control software).

**The fix, and its honest trade-off:**
```python
_start_tls = httpcore._backends.sync.SyncStream.start_tls

def _start_tls_without_sni(self, ssl_context, server_hostname=None, timeout=None):
    if server_hostname and server_hostname.endswith("pinecone.io"):
        ssl_context.check_hostname = False
        server_hostname = None
    return _start_tls(self, ssl_context, server_hostname, timeout)

httpcore._backends.sync.SyncStream.start_tls = _start_tls_without_sni
```
Certificate chain verification still happens - this isn't a full bypass. But `check_hostname =
False` does remove the check that the certificate's name matches `pinecone.io`, narrowing but not
eliminating interception risk on this specific network. Scoped intentionally to `pinecone.io`
hosts only, not applied globally. Treating this as a temporary workaround for this network, not
something to carry into `production-rag-agent` without reconsidering it - the real fix is
identifying and reconfiguring/removing the actual Firewall app, planned as unhurried follow-up
work rather than blocking the roadmap.

**Also worth noting:** patches a private `httpcore` internal
(`_backends.sync.SyncStream.start_tls`), so it's fragile against future library version changes -
intentionally left as a clearly-commented, removable block.

## Test results

**Question 1 ("How many days can I work from abroad?"):** correct answer (45 days), correct top
match at 0.6026 similarity. Matches Day 8's Chroma result on the same question - same correct
retrieval across two completely different vector DB backends.

**Question 2 ("What is Acme's stock price?"):** correctly triggered the "no match" fallback -
best available score only 0.4589, below the 0.5 threshold. Mirrors Day 8's Chroma behavior on the
same unanswerable question (different metric direction, same underlying shape: real matches score
measurably better than irrelevant ones).

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Still unresolved: the actual identity of the third-party Firewall app causing the SNI filtering.
  Worth identifying and reconfiguring properly when there's unhurried time, rather than relying on
  the SNI-stripping workaround long-term.

## Practice task
Rebuilt the Day 8 Acme RAG pipeline against Pinecone (`retrieve()`, `build_prompt()`,
`generate_answer()`), fixed two integration bugs (vector wrapping, match-object-vs-string
mismatch), and diagnosed + worked around a real network-level TLS/SNI filtering issue blocking
Pinecone's data-plane hosts specifically. Verified both the answerable and unanswerable test
questions produce results consistent with Day 8's Chroma-based pipeline. Located in `practice/`.
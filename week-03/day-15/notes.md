# Day 15 - Streaming to a real frontend: JS UI via SSE

**Date completed:** _(fill in)_

## What I learned

**Why SSE, not WebSockets, for a chat UI**
WebSockets are full bidirectional, persistent connections - genuinely necessary when either side
needs to push data at any time (collaborative editing, multiplayer). A chat UI's actual shape is
simpler: user sends one question, server streams one answer back. Server-Sent Events (SSE) fit
that shape directly - a one-directional stream over plain HTTP, less protocol overhead than a
WebSocket for a job that doesn't need bidirectional push.

**The SSE wire format**
`data: {content}\n\n` isn't a style choice - it's the actual protocol format the client needs to
parse. `StreamingResponse` in FastAPI takes a generator and sends each `yield`ed piece to the
client as soon as it's produced, instead of buffering the full response first.

**Why `fetch()` + manual reader, not the browser's built-in `EventSource` API**
`EventSource` only supports GET requests with no custom body - doesn't fit "send a JSON message."
Real chat UIs (including ChatGPT's own) work around this the same way: `fetch()` with
`response.body.getReader()` for manual streaming reads, parsing the `data: ` format by hand.
`getReader()` gives raw access to the response as bytes arrive over the network, unlike
`response.json()`/`.text()`, which silently buffer the *entire* response before returning
anything. `TextDecoder()` is needed because the raw stream delivers bytes (`Uint8Array`), not
strings.

**CORS**
Browsers block JavaScript from calling a different origin (e.g. a local HTML file calling
`localhost:8000`) by default, as a security measure. `CORSMiddleware` with `allow_origins=["*"]`
fixes this for local dev - explicitly noted as unsafe for production, since it would let any
website's JS call the API from a user's browser.

**Deliberate scope decision: a separate streaming endpoint, not a streaming `ProductionLLMClient`**
`/chat/stream` bypasses the Day 3 retry wrapper entirely and calls the OpenAI client directly with
`stream=True` - a conscious trade-off flagged back on Project 1 Saturday (retrying a
partially-streamed response, where some content is already sent to the client, is a genuinely hard
problem with no clean answer). Documented this gap with an explicit code comment rather than
leaving it silent, so a future reader doesn't assume `.stream_response()` carries the same
production guarantees as `.chat()`.

## Bugs found and fixed

**1. Wrong working directory running uvicorn.** Ran `uvicorn main:app` from the repo root instead
of `week-03/day-15/practice/` - same class of bug as Day 11's `glob` path issue. Python module
paths also can't contain hyphens, so `week-03.day-15...` isn't valid syntax either - `cd`-ing into
the folder first is the only real option given the folder naming.

**2. `global` missing for `openai_client` in `lifespan`.** `global llm_client` was declared but not
`global openai_client` - meant `openai_client = OpenAI()` created a function-local variable that
vanished once `lifespan` finished, leaving the module-level `openai_client` permanently `None`.
Would have crashed `/chat/stream` with `AttributeError` the moment it was called. Fixed by adding
both names to one `global` line. (Later made moot entirely by moving streaming onto
`llm_client.stream_response()` instead of a separate module-level client - simpler design that
also sidesteps this whole class of bug.)

**3. Stuck port from a leftover uvicorn process.** `[Errno 48] Address already in use` even after
a `kill <PID>` - the plain `kill` sends `SIGTERM` (a polite request), which the process seemingly
ignored. `lsof -i :8000` showed the port still occupied by the same PID afterward. Fixed with
`kill -9 <PID>` (`SIGKILL`, cannot be ignored by the process). Same underlying lesson as Day 5's
suspended (`^Z`) job - a process can outlive what looks like a shutdown command.

**4. Streaming calls were completely invisible to cost tracking.** `.chat()` calls
`_calculate_cost()` and increments `total_calls` on every path; `.stream_response()` originally did
neither - meant `/cost` would silently under-report real spend the moment anyone used
`/chat/stream` instead of `/chat`. Fixed by adding `stream_options={"include_usage": True}` (Day
1's bonus insight, used for the first time since learning it) so the final chunk carries real
usage data, with the same `if chunk.choices:` guard from Day 1 protecting against that final
chunk's empty `choices` list. Verified fixed by checking `/cost` after 3 streamed exchanges and
confirming `total_calls: 3` with a real nonzero cost - not just trusting the code looked right.

**5. The real functional bug: no conversation memory in the browser chat.** Multi-turn testing
("What's python...", then "Elaborate more in one sentence") revealed the assistant had no idea
what "elaborate" referred to - it treated every message as a fresh, contextless question. Root
cause: `/chat/stream` only ever sent one `system` message plus the *current* user message, with
nothing accumulating turn to turn - unlike every CLI chatbot built since Day 1, which grew a real
`messages` list. Fixed on both ends together: added a `StreamChatRequest` Pydantic model (list of
`ChatMessage`, distinct from the existing single-message `ChatRequest` used by `/chat`) so the
endpoint accepts a full history; added a `conversationHistory` JS array on the frontend that
`.push()`es both the user's message and the assembled assistant reply
(`assistantReply += content`, same accumulation pattern as Day 1's `response_text += delta`, now
running in the browser) and sends the whole array on every request. Verified fixed with the exact
same three-message sequence that originally failed - "elaborate more" correctly built on the prior
Python answer the second time.

**Note on `StreamChatRequest`:** FastAPI parses incoming JSON into real Pydantic `ChatMessage`
objects, not plain dicts - had to explicitly convert back to
`[{"role": m.role, "content": m.content} for m in request.messages]` before handing them to the
OpenAI SDK, which expects plain dicts, not Pydantic instances.

## Bonus: disable input while streaming
Wrapped the fetch/read loop in `try/finally` so the input and button reliably re-enable even if
the request throws or the stream errors mid-read - not just on the successful path. Without
`finally`, a network failure would leave the UI permanently locked with no way to send another
message short of reloading the page.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
Added CORS middleware, a `/chat/stream` SSE endpoint (`StreamingResponse` + manual SSE format),
and a real HTML/JS chat frontend using `fetch()` + `getReader()` for token-by-token display. Found
and fixed five bugs across backend and frontend, most significantly a missing-conversation-history
bug that broke multi-turn context entirely, and a cost-tracking gap that made streamed calls
invisible to `/cost`. Added an input-disable bonus with proper `finally`-based cleanup. Located in
`week-03/day-15/practice/`.
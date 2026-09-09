# Day 18 - Serverless: AWS Lambda + API Gateway

**Date completed:** _(fill in)_

## What I learned

**The conceptual shift from EC2**
EC2 (Day 17) gives a machine that runs continuously - billed per hour whether handling a request
or idle. Lambda has no "always on" state at all: AWS runs the function only when triggered, for
exactly as long as the request takes, then shuts down. Pay per invocation and per millisecond of
execution - near-zero cost for occasional traffic, versus a server running 24/7 regardless of use.

**The real mismatch: ASGI vs. Lambda's event model**
FastAPI expects a long-running server (`uvicorn`) in a continuous loop. Lambda invokes code with
one JSON event per request and no persistent server loop at all. **Mangum** bridges this by
translating API Gateway's event format into ASGI calls FastAPI understands, and translating the
response back - `handler = Mangum(app)` is the entire integration, no route/logic changes needed.

**IAM roles vs. IAM users**
Day 17 created an IAM *user* - for a person to log in. Lambda needs an IAM *role* - permissions a
*service* assumes on its own behalf. Creating a function prompts for (or auto-creates) an
execution role; this is a different IAM concept than yesterday's user, not a variation of it.

**Cold starts, and a direct, now-measured callback to Day 5's lifespan pattern**
First invocation after idle time is slower - a fresh container starts, imports libraries, and runs
module-level code before handling the request. Warm invocations reuse that container and skip
init entirely. Confirmed directly in today's own CloudWatch logs: `Init Duration: 3086.94 ms` for
the first request - real, measured proof that constructing `ProductionLLMClient()` at module level
(not inside the handler) costs real time once per container, exactly the reasoning behind Day 5's
`lifespan` pattern, now visible as an actual number instead of just a concept.

**Scope decision, stated honestly**
Deployed only `/health` + `/chat` (no vector DB dependency) today, not the full RAG app. Lambda's
package size limits and lack of persistent local disk between invocations make a locally-persisted
Chroma index a genuinely poor fit without extra machinery (S3-backed loading, EFS, or migrating to
a managed vector store like Pinecone from Day 10) - real future work, not solved today.

## Bugs found and fixed (five distinct, real problems)

**1. IAM permission gaps, three separate times, same pattern as Day 17.** `numan-dev` needed
`AWSLambda_FullAccess` and `AmazonAPIGatewayAdministrator` added before Lambda/API Gateway pages
would even load, then `IAMFullAccess` separately once function creation attempted
`iam:CreateRole` (needed to auto-create the execution role) and hit "not authorized." Noted
`IAMFullAccess` as the broadest permission granted to `numan-dev` so far - a real, acknowledged
trade-off versus hand-authoring a narrower custom policy, same simplification logic as yesterday's
service-specific FullAccess policies.

**2. Platform-mismatch package error: `No module named 'pydantic_core._pydantic_core'`.**
`pydantic_core` has a compiled binary component; packages built via plain `pip install -t .` on a
Mac produce Mac-specific binaries that don't run on Lambda's actual Linux/x86_64 environment. Never
hit in Docker, since the Dockerfile's Linux base image builds everything inside a real Linux
container - Lambda has no equivalent build step, only a pre-built zip upload. Fixed with
`pip install --platform manylinux2014_x86_64 --target . --only-binary=:all: ...`, forcing
Linux-compatible wheels regardless of the host OS.

**3. `RuntimeError: unable to infer a handler` on the console's built-in Test tab.** Not a bug -
the generic sample test event isn't shaped like a real API Gateway request (no `httpMethod`,
`path`, etc.), so Mangum correctly couldn't route it. Confirmed the actual code/imports worked
(this error only appears *after* successful import), then moved straight to testing via a real
API Gateway trigger instead of fighting to hand-construct a fake event.

**4. API Gateway route existed but had no integration attached.** Adding a `{proxy+}` wildcard
route (needed so `/health` and `/chat` reach the function, not just the exact base path) creates
the route as a separate object from wiring it to a Lambda function - checked the route's
Integration panel directly ("No integration is attached") before assuming it worked, then attached
the same integration the original exact-match route already used.

**5. The most obscure bug: HTTP API's non-`$default` stage naming quirk.** `{"detail":"Not
Found"}` (FastAPI's own 404, confirming requests were reaching the app) despite
`api_gateway_base_path="/production-rag-chat"` being set correctly. Root cause, confirmed via
direct source evidence (a GitHub issue titled exactly "HTTP API non-$default stage includes stage
in rawPath as a prefix," plus AWS Powertools' own source code showing `if stage != "$default":
strip the stage prefix`): since this API's stage is literally named `default` (not the special
reserved value `$default`), the actual path Lambda receives is `/default/production-rag-chat/health`
- the stage name prefixed on top of the route path, not just the route path alone. Fixed by
correcting `api_gateway_base_path` to `/default/production-rag-chat`, matching the real string
rather than the assumed one.

## Test results

- `curl .../health` → `{"status":"ok"}` - confirmed platform fix, handler config, and routing all
  correct together
- `curl -X POST .../chat` (first attempt) → generic `{"message":"Internal Server Error"}` from API
  Gateway itself (not FastAPI) - diagnosed via CloudWatch logs showing
  `Duration: 3000.00 ms ... Status: timeout` against the default 3-second Lambda timeout, not a
  code bug
- Fixed by raising Timeout to 30s and Memory to 256MB; retest → `{"reply":"2 + 2 equals 4."}` -
  full, working serverless FastAPI deployment

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Cold-start timing comparison (calling `/chat` twice quickly, then again after a gap) - worth
  trying as a follow-up, not done today since the timeout issue took priority.

## Practice task
Deployed a Mangum-wrapped FastAPI app (`/health` + `/chat`, using `ProductionLLMClient`) to AWS
Lambda behind an API Gateway HTTP API. Found and fixed five distinct, real problems: repeated IAM
permission gaps, a Mac-vs-Linux binary platform mismatch, a misleading console test-event error,
a route with no integration attached, and an obscure HTTP API stage-naming quirk affecting path
stripping - the last one root-caused via primary source evidence (a GitHub issue and AWS
Powertools' own source) rather than guesswork. Diagnosed and fixed a Lambda timeout via
CloudWatch logs, which also directly confirmed Day 5's module-level-initialization lesson with a
real measured `Init Duration` number. Work done directly in the AWS Console, not
`ai-learning-journal` code files.
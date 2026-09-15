# Day 22 - AWS ECS/Fargate: deploy dockerized app to ECS

**Date completed:** _(fill in)_

## What I learned

**Where ECS/Fargate sits relative to EC2 and Lambda**
EC2 (Day 17): manage the whole server yourself. Lambda (Day 18): no server, but only short,
request-scoped functions - a poor fit for a long-running app with its own process. ECS/Fargate is
the middle ground: real, long-running containers, but AWS manages the underlying servers entirely
- the "no server to patch" appeal of Lambda, applied to containers instead of functions.

**Core vocabulary**: Cluster (logical grouping) -> Service (keeps a desired number of tasks
running, restarts on failure) -> Task (one running instance of a) Task Definition (the blueprint:
image, CPU/memory, ports, env vars per container - AWS's own format for what `docker-compose.yml`
already describes).

**The critical networking difference from Compose**: Compose gives each service a DNS hostname
(`chroma`, `redis`). ECS's `awsvpc` network mode works differently - all containers within *one
task* share a single network interface and reach each other via `localhost`, not by service name.
This worked in our favor: `vectorstore.py`'s existing `localhost` default (originally just a local-
dev fallback) turned out to already be the correct production value for ECS - no environment
override needed, unlike Compose which required explicitly setting `CHROMA_HOST=chroma`.

**Two distinct IAM roles, continuing Day 20's exact reasoning**: Task Execution Role (used by ECS
itself to pull the image and write logs - infrastructure-level) vs. Task Role (used by the app's
own code to make AWS calls, e.g. fetching the Secrets Manager secret) - the same EC2-instance-role
concept from Day 20, just for a container instead of a server. Reused the identical scoped
Secrets Manager policy on the new Task Role.

**A shared-network-namespace port conflict, found and resolved properly**: since all containers
in one ECS task share one network interface, `app` (listening on 8000) and Chroma's own default
(also 8000) would genuinely conflict if run together unmodified - unlike Docker Compose, where
each service gets its own separate network namespace and this conflict doesn't exist at all. This
needed a real decision, not just a flag.

## The real investigation: how to change Chroma's port safely

**First attempt: pass `--port 8001` as a command override on the Chroma container.** Hit two real
obstacles: the ECS console's "Command" field for this container wasn't where expected in this
console version (confirmed absent after checking multiple locations), and - more importantly -
research surfaced a real, documented bug in Chroma's own GitHub issues: explicitly passing
`--port`, even to restate the default value, has been reported to break inter-container
connectivity in some configurations.

**Considered pivoting to changing the app's port instead** (moving `uvicorn` to 8080, leaving
Chroma fully default) - a safer mechanism (uvicorn's own well-established `--port` flag) but a
real change to the Dockerfile and CI/CD pipeline. Correctly pushed back on this pivot in favor of
keeping the original intent (app stays on its standard 8000, Chroma moves instead).

**Resolved properly via a different mechanism entirely**: Chroma's own official docs list
`CHROMA_PORT` as a current, supported *environment variable* (explicitly distinguished on their
reference page from older, now-legacy configuration methods) - a completely separate code path
from the buggy `--port` CLI flag. Set `CHROMA_PORT=8001` as a plain environment variable on the
Chroma container (using the Environment Variables section already located earlier), sidestepping
both the missing UI field and the documented flag bug at once.

## Bugs and gaps found and fixed

**1. ECS service-linked role creation failure on first cluster creation** - "Unable to assume the
service linked role" on the very first `Create cluster` attempt. Resolved on retry - AWS's
automatic first-time service-linked role creation needed a few seconds to propagate.

**2. Compute options defaulted to "Capacity provider strategy" during service creation** -
switched to plain "Launch type -> Fargate," the correct simple choice for a single, non-mixed-
compute deployment.

**3. No "My IP" auto-detect option in this security-group creation flow** (unlike EC2's) - only
Custom/Anywhere/Source group were offered. Worked around by manually running `curl ifconfig.me`
and entering the result as explicit `/32` CIDR notation - functionally identical to "My IP,"
just without the convenience auto-fill.

**4. Ingestion against the new task's Chroma failed with a connection timeout** - correctly
predicted before running: the service's security group only had port 8000 open (for `app`), never
port 8001 (for `chroma`), since the original security group rule was scoped to what should be
externally reachable, and direct ingestion access wasn't accounted for as a legitimate exception
at that point. Fixed by adding a second inbound rule (port 8001, same IP) directly on the
service's actual security group (found via Configuration and networking tab, not immediately
obvious from the cluster overview page).

**5. Cluster overview's summary cards ("0 active services," "0 running tasks") contradicted the
task list showing a genuinely Running task** - stale cached counts, not a real problem; the task
list itself (freshly polled) was the trustworthy source. A "CloudWatch Action logs: Access
denied" also appeared, unrelated to anything built today - a separate, minor IAM gap not blocking
the actual deployment.

## Test results
- `curl .../health` -> `{"status":"ok"}` immediately after the task reached Running state
- Ingestion against the ECS task's Chroma (after the port 8001 security group fix) -> 36 chunks,
  matching the known baseline count exactly
- `curl .../ask` (SummitCarry backpack question) -> `$249.00, out of stock`, exact match to every
  prior deployment's result (local, Docker Compose, EC2) - full round-trip proof that two
  containers correctly coordinating within one ECS task, via `localhost` networking and a
  non-default Chroma port set through the correct (non-buggy) mechanism, produces an identical,
  correct result to every earlier deployment model

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether to leave the port 8001 security group rule open permanently or remove it after each
  ingestion run - left open for now, scoped to a single IP, low risk either way

## Practice task
Deployed the app + Chroma as a two-container ECS Fargate task, with a new Task Role reusing Day
20's exact Secrets Manager policy and a separate Task Execution Role for image pulls/logging.
Diagnosed and resolved a genuine multi-container port conflict specific to ECS's shared-network-
namespace model (absent in Docker Compose), including researching and avoiding a real, documented
Chroma CLI flag bug in favor of its officially-supported environment variable equivalent. Found
and fixed a real security-group gap blocking direct ingestion access. Verified the full deployment
against the same known-good test question used across every prior deployment model this project.
Work done directly in the AWS Console, not `ai-learning-journal` code files.
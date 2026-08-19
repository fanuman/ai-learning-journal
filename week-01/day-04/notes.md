# Day 4 - Docker fundamentals (images, containers, first Dockerfile)

**Date completed:** _(fill in)_

## What I learned

**Why Docker exists**
Solves the "works on my machine" problem - packages an app plus everything it needs (Python
version, libraries, OS-level dependencies) into one standardized unit that runs identically
anywhere. Same idea as a shipping container: looks and behaves the same regardless of what's
carrying it.

**Image vs container - class vs instance**
An image is like a class definition (a frozen blueprint). A container is a running instance of
that image - just like instantiating an object from a class. One image can produce many
independent containers, each isolated from the others, the same way multiple objects can be
created from one class.

**Dockerfile instructions**
- `FROM` - base image to start from (e.g. `python:3.13-slim`)
- `WORKDIR` - sets the working directory inside the container (like `cd`)
- `COPY` - copies files from the host into the image
- `RUN` - executes a command during the build (e.g. installing dependencies)
- `ENV` - sets environment variables inside the image
- `CMD` - the default command that runs when a container starts

**Layers and caching**
Every instruction creates a cached layer. Docker reuses a layer if its inputs haven't changed.
This is why `requirements.txt` gets copied and `pip install` run *before* copying the rest of the
app code - dependencies change rarely, code changes constantly, so this ordering means a
code-only change reuses the cached dependency-install layer instead of reinstalling everything on
every build.

**`.dockerignore`**
Same idea as `.gitignore` but for the Docker build context - keeps `venv/`, `__pycache__`,
`.env`, `.git` out of the image. Matters for more than tidiness: without it, `.env` (with real API
keys) could get copied straight into the image and be extractable by anyone who later
inspects/pulls it.

**Secrets at runtime, not build time**
`docker run --env-file .env <image>` passes environment variables in when the container starts,
so secrets never get baked into the image itself.

## Commands used today
```
docker build -t day4-wrapper .
docker run --env-file .env day4-wrapper
docker images
docker ps
docker ps -a
docker run -it day4-wrapper bash
```

## Test results and findings

Built and ran the image successfully - output matched the local (non-Docker) run exactly:
```
Four.
Nine.
Eleven.
Total calls: 3 | Retries: 0 | Estimated cost: $0.000017
```

**Exit code 0 vs 137.** `docker ps -a` showed my container as `Exited (0)`, while several older
containers from a previous project showed `Exited (137)`. `0` = finished cleanly, no errors.
`137` = `128 + 9`, where `9` is the signal number for `SIGKILL` - meaning those containers were
forcibly killed rather than shutting down on their own (commonly happens when `docker stop` times
out and Docker escalates to a hard kill). Useful pair of numbers to recognize on sight going
forward.

**Real finding: `COPY . .` copied the entire repo, not just the app.** Ran `docker run -it
day4-wrapper bash` and `ls` inside the container - the image contained every week-01 through
week-08 folder from the whole `ai-learning-journal` repo, not just the Day 3/4 script. `.gitignore`
`/`.dockerignore` correctly blocked `venv/`, `.env`, `__pycache__`, `.git` - but `COPY . .` still
swept up the entire monorepo structure into a 248MB image meant to run one script.

**Why this matters going forward:** this is the concrete, hands-on reason `production-rag-agent`
and `multiagent-platform` are separate repos from `ai-learning-journal` rather than folders inside
it. Once those get containerized starting Week 4, their build context will only ever contain that
app's own code - nothing else. Seeing the actual bloat here makes that earlier repo-separation
decision make sense as a real consequence, not just an abstract best practice.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Worth exploring later: multi-stage builds or a narrower build context (e.g. running `docker
  build` from inside the specific day's folder rather than the repo root) as ways to avoid the
  monorepo-bloat issue found today.

## Practice task
Wrote `requirements.txt`, `.dockerignore`, and a `Dockerfile` for the Day 3 production wrapper
script. Built the image (`day4-wrapper`), ran it with `--env-file .env` and confirmed output
matched the local run, inspected it with `docker images`/`docker ps -a`, and opened an interactive
shell inside the running container with `docker run -it day4-wrapper bash` to verify dependencies
installed correctly and to discover the `COPY . .` bloat issue above.
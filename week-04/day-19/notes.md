# Day 19 - CI/CD with GitHub Actions: test, build, push to ECR

**Date completed:** _(fill in)_

## What I learned

**What CI/CD actually automates**
Every deploy through Day 18 was manual - `docker build`/`docker run` typed by hand each time.
CI/CD means a pipeline runs automatically on every push: install dependencies, run tests, and
only if those pass, build and push the image. The point is catching a broken change before it
reaches deployment, not after.

**GitHub Actions basics**
Workflow YAML files in `.github/workflows/`, triggered by events (`on: push`), made of jobs and
steps, run on GitHub-hosted virtual machines ("runners"). `needs: <job>` is a real gate - a
downstream job simply doesn't run at all if the job it depends on fails.

**ECR (Elastic Container Registry)**
AWS's own Docker registry, parallel to Docker Hub. Unlike every prior deploy, CI/CD doesn't run
the image immediately - it pushes it somewhere durable, so it can be pulled and deployed by
anything later, without needing the original build environment or laptop at all. The repository
itself must be created ahead of time in the ECR console - pushing doesn't auto-create it.

**GitHub Secrets**
Encrypted, per-repo secret storage referenced in workflows as `${{ secrets.NAME }}` - never
visible in logs, never present in the workflow file itself. Same discipline as `.env`/`.gitignore`
this whole roadmap, just a different storage mechanism. Noted AWS's own current guidance actually
recommends OIDC role assumption over long-lived access keys (no stored secret at all) - access
keys used today as the same honest simplification pattern as `EC2FullAccess`/`IAMFullAccess` on
Days 17-18, OIDC flagged as the more secure real-world approach worth adopting later.

**Image tagging with the commit SHA, not just `latest`**
`IMAGE_TAG: ${{ github.sha }}` tags each build with the exact commit that produced it, alongside
`latest`. Real practice: `latest` is convenient, but the SHA tag means any specific image can
always be traced back to (and rolled back to) the exact commit that built it.

**Why the "test" step is a cheap import-check, not the full eval harness**
Running Day 13's full LLM-as-judge eval on every single push would cost real API calls per commit
- not economical for routine CI. Instead, `tests/test_imports.py` imports every module in `src/`
and confirms none of them raise an error. This is a genuinely well-targeted test, not a
placeholder: every real bug found this week (the `inventory_tool` missing `src.` prefix, the bare
`run_eval.py` import, the missing `global` declaration) was exactly the class of failure this test
would have caught automatically, before ever running the app by hand.

## The real architectural decision of the day: rebuild vs. copy `chroma_db/`

**First CI failure:** `COPY chroma_db/ ./chroma_db/` failed - `chroma_db/` is correctly gitignored
(generated data), so a fresh `git clone` on the GitHub runner never has it, same root cause as
Day 17's EC2 deploy hitting the identical gap.

**Day 17's fix (`scp` a pre-built copy from the laptop) doesn't apply here** - there's no laptop
to copy from in a disposable CI runner. The correct fix is architecturally different: rebuild
`chroma_db/` from source, fresh, on every run.

**A real, worthwhile question raised before implementing:** wouldn't committing the pre-built
`chroma_db/` directly be more efficient than re-embedding on every push? Checked the actual
numbers rather than assuming - embeddings are typically *larger* than the source text they
represent (1536 floats × 4 bytes = 6,144 bytes per chunk, before index/storage overhead, against
~20KB of source text for the whole corpus), so "efficient" doesn't hold up even on pure size
grounds.

**The real reason to rebuild from source, though, is correctness, not size:** committing a
pre-built binary index creates a second source of truth that can silently drift from the actual
source documents - editing `returns_policy.txt` without remembering to rebuild and recommit the
index would leave a deployed app quietly serving stale, contradicted answers with no warning at
all. Rebuilding fresh from `data/*.txt` on every CI run makes that drift structurally impossible -
the deployed image is always provably derived from whatever the source files currently say.

**Also revisited a related gitignore decision:** `data/*.txt` (the TrailPeak product catalog and
policies) had been gitignored following Week 2's PDF pattern - but Week 2's PDFs were externally-
sourced copyrighted documents meant to be re-downloaded, while these `.txt` files are original
content written for this project. No reason to exclude them; committed them as real source files,
since the CI rebuild step depends on them actually being present in the cloned repo.

## Bugs found and fixed

**1. `pytest` missing from `requirements.txt`.** CI failed with `No module named pytest` -
`pytest` had never been formally declared as a dependency, since it was only ever run manually on
a laptop that already had it installed globally. A genuine example of what CI catches that a
laptop won't: a fresh environment has none of the accumulated global packages that quietly paper
over a missing declaration.

**2. `chroma_db/` missing entirely in the CI environment**, described in detail above - fixed by
adding an ingestion step to the workflow (`python -m src.ingest`) before the Docker build, using a
real `OPENAI_API_KEY` GitHub secret (distinct from the test job's fake string-only key, since
ingestion makes genuine embedding API calls).

## Test results

Pulled the CI-built image directly from ECR (`docker pull ...:latest`), ran it locally, and
confirmed both `/health` and `/ask` against the exact same known-good question and answer used on
Day 17's EC2 deploy and Project 3 - `$249.00, out of stock, Small/Medium and Medium/Large` -
identical result. Confirms the fully automated, rebuilt-from-source pipeline produces a genuinely
correct artifact, not just one that completes without erroring.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
Built a two-job GitHub Actions pipeline (`test` gated before `build-and-push`) for
`production-rag-agent`: an import-check test targeting the exact class of bug found repeatedly
this week, and a build job that authenticates to AWS, rebuilds the Chroma vector index from
source `.txt` documents, builds the Docker image, and pushes it to ECR tagged both by commit SHA
and `latest`. Made a deliberate, reasoned architectural choice to rebuild the vector index from
source on every run rather than commit a pre-built copy, for correctness (drift prevention) rather
than the (incorrect, checked) assumption that committing it would be more efficient. Verified the
final ECR image by pulling and running it locally, confirming an identical, correct result against
a known-good test question from Day 17 and Project 3. Work done directly in `production-rag-agent`
(GitHub Actions workflow + AWS console), not `ai-learning-journal`.
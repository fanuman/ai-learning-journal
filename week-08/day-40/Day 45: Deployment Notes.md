# Day 45 notes: FreightLens on AWS

Date: Mon 26 Oct 2026 (work started Fri 23 Oct with the container images).
Goal: run the whole app (web + API + database + file storage) on AWS from code, test it in a browser, then destroy it.
Result: **deployed, tested, destroyed. 30 resources created and 30 destroyed, nothing left running.**

---

## 1. Concepts (plain language)

**Image vs container.** An image is a frozen recipe plus files (like an installer). A container is one running copy of it.
We build two images: `api` (Python/FastAPI) and `web` (Next.js).

**Layers and caching.** Each Dockerfile line makes a layer. Docker reuses a layer if that line and everything above it did not change.
So we copy `pyproject.toml` and install dependencies *before* copying the source: editing code does not reinstall packages.

**`.dockerignore`.** A list of files that never go into the build. `.env` is on it: a secret baked into an image can be pulled out by anyone
who gets the image.

**Non-root user.** The containers run as an unprivileged user (`app`, uid 10001). If the app is attacked, the attacker does not own the container.

**Config from environment variables.** The same image runs on a laptop, in Compose and on AWS; only the environment differs.
This is why `config.py` reads `DB_HOST`, `STORAGE_BACKEND`, `S3_BUCKET` and so on.

**Multi-stage build.** The web image has three stages (install, build, run). Only the small final stage is shipped, without the build tools.
Next.js `output: "standalone"` produces a self-contained server for that last stage.

**Stateless container.** The container keeps nothing it cannot lose. Uploads go to S3, data goes to Postgres. You can stop, replace or
add copies of the container freely. (This is why local disk storage had to become an `S3Storage` class first.)

**Storage backend (one interface, two implementations).** `LocalStorage` (a folder) and `S3Storage` (a bucket) both offer `save`, `path`
and `delete`. The pipeline code did not change at all. Tests inject a fake S3 client, so no AWS is needed to test.

**IAM roles (two jobs).**
- *Execution role*: used by ECS **before** our code starts: pull images, write logs, fetch the four secrets.
- *Task role*: used by **our code** while running: read/write one bucket. No access keys exist anywhere; AWS hands the task short-lived
  credentials. Least privilege = each role can do only what it must.

**Security groups (firewalls) chained.** internet → load balancer (80) → app task (3000) → database (5432). Each group accepts traffic only from
the one before it, so the database is unreachable from the internet.

**Load balancer, target group, health check.** The ALB is the single public door. It forwards to a *target group* and asks `/login` every
30 s; a task that stops answering is replaced.

**ECS Fargate.** Containers without managing servers. *Task definition* = recipe (images, CPU/memory, env, secrets). *Service* = keeps N copies
running and wires them to the load balancer. One task holds two containers (web and api) that share one network address, so web reaches
the API at `127.0.0.1:8000`.

**Secrets Manager.** Secrets are fetched by ECS at start and passed as environment variables (`valueFrom`). RDS can create and own the master
password (`manage_master_user_password`), so no human or Terraform file ever sees it; we reference one JSON field with `...:password::`.

**Terraform.** Infrastructure as code. `init` (download providers, write the lock file), `validate` (syntax), `plan` (what would change),
`apply` (do it), `destroy` (undo everything). The **state file** is Terraform's memory of what it built; it holds the generated secrets, so
it is private and git-ignored. The **lock file** (`.terraform.lock.hcl`) pins provider versions and *is* committed.

**Bootstrapping.** Getting an empty system to the point where it can run itself. Locally Docker ran `init-app-role.sh`; RDS has no such hook,
so `python -m freight_intel.bootstrap` does it: (1) create the limited app role that row-level security applies to, (2) run the migrations,
(3) create LangGraph's checkpoint tables. Order matters: role first, then tables, so default privileges cover the new tables. Safe to repeat.

**Why `desired_count = 0` first.** The tasks need images in the registry, a prepared database and a filled OpenAI secret. Starting them
earlier would just crash-loop. So: apply infrastructure → push images → bootstrap → store key → start.

**Cost control.** About $0.09/hour (ALB + one Fargate task + small RDS). A NAT gateway (about $32/month) was avoided on purpose by using the
default VPC with public subnets. Destroy right after testing.

---

## 2. What was built (files)

Repo side: `Dockerfile`, `.dockerignore`, `web/Dockerfile`, `web/.dockerignore`, `web/next.config.ts` (standalone + `/api` rewrite),
`docker-compose.yml` (profile `app`), `src/freight_intel/storage.py` (S3Storage), `config.py` (storage settings), `bootstrap.py`,
`tests/test_storage.py`, `tests/test_bootstrap.py`.

`infra/`: `versions.tf`, `variables.tf`, `network.tf`, `storage.tf` (ECR + bucket), `secrets.tf`, `database.tf`, `iam.tf`, `alb.tf`,
`ecs.tf`, `outputs.tf`, `README.md` (runbook), `.terraform.lock.hcl`.

Key design choices worth remembering:
- Default VPC, public subnets, no NAT (cost) → documented as a limit, not hidden.
- One task, two containers, API only reachable through the web container's `/api` rewrite.
- `random_password` for JWT and app-role password; RDS-managed master password; OpenAI secret created empty and filled from the operator's terminal.
- `force_delete` / `force_destroy` / `skip_final_snapshot` / `recovery_window_in_days = 0` so destroy leaves nothing (demo-only settings).

---

## 3. Commands that mattered

```
terraform init && terraform validate && terraform plan      # Plan: 30 to add
terraform apply                                             # database took ~6 min
docker build --platform linux/arm64 -t ${API_REPO}:latest ..
docker push ${API_REPO}:latest                              # same for web
eval "$(terraform output -raw run_bootstrap_command)"       # one-off ECS task
aws secretsmanager put-secret-value --secret-id freightlens/openai-api-key --secret-string "$(grep '^OPENAI_API_KEY=' ../.env | cut -d= -f2-)"
terraform apply -var desired_count=1
terraform destroy                                           # 30 destroyed
```

---

## 4. Results

- Tests: **314 passed** (includes the new storage and bootstrap tests).
- `terraform validate`: success. First plan: 30 to add. After a permission fix the apply completed.
- Bootstrap task log: `1/3 app role and its rights`, `2/3 tables`, `3/3 checkpoint tables`, `the database is ready`.
- In the browser on the load-balancer address: sign-up, upload of a quote and an invoice (both **Processed**), the arithmetic check caught the
  invoice total (printed 4,106.00 vs lines 4,205.00, difference -99.00), compare with the quote worked.
- S3 listing showed both uploads under the tenant's id prefix: proof that storage is not on the container disk.
- `aws ecs describe-services` → running 1, desired 1.
- After `terraform destroy`: RDS `[]`, load balancers `[]`, ECS clusters `[]`, no bucket. Billing stops.

---

## 5. Bugs and gotchas (the interview stories)

1. **File modes after `COPY`.** Files copied from the Mac were not readable by the non-root user: `PermissionError: pyproject.toml`, then
   "No module named freight_intel…". Fix: `chmod -R a+rX` on the copied folders in the Dockerfile.
2. **`AccessDenied` on `rds:CreateDBSubnetGroup`.** Terraform acts as *your IAM user*, which needs permission for every service it touches.
   Apply had created 28 of 30 resources and stopped; state was saved, so a second apply resumed. Lesson: partial applies are normal and safe to re-run.
3. **"Exceeds this account's quota" when attaching a policy.** An IAM user can have at most 10 managed policies. Workaround: an *inline*
   policy (`rds:*` plus a service-linked-role statement limited to `rds.amazonaws.com`). Remove it after the project if you like.
4. **zsh variable modifier.** `$API_REPO:latest` became `...apiatest` because zsh reads `:l` as "lowercase". Always write `${API_REPO}:latest`.
   Fixed in the runbook. Recovery was a `docker tag`, no rebuild.
5. **Wrong folder.** `terraform output` run from the repo root printed nothing, so `aws s3 ls s3:///` listed all buckets instead. Terraform commands
   belong in `infra/`.
6. **First ARM build was slow** (the Python install layer took ~26 minutes). Layer caching makes later builds fast; this is why dependency
   install sits above the source copy.
7. **Account number in pasted output.** Not a secret, but mask it in anything shared; secrets (API keys, passwords) never go in chat.

---

## 6. How to say it in an interview (60 seconds)

"I took a multi-tenant document-intelligence app and deployed it to AWS with Terraform. A load balancer fronts one ECS Fargate task running the web
and API containers; data is in RDS Postgres and uploads are in S3, so the containers are stateless. Secrets live in Secrets Manager and the app
authenticates through an IAM task role, so there are no keys in the code or images. An empty database is prepared by a one-off bootstrap task that
creates the limited role row-level security depends on. I verified it end to end in the browser, then destroyed the stack, so it cost a couple of
dollars. Known limits: HTTP only, public subnets without a NAT, local Terraform state and no alarms yet; I know what I would change for production."

Resume-style bullets (edit to taste):
- Deployed a multi-tenant LLM document-processing SaaS to AWS (ECS Fargate, ALB, RDS Postgres, S3, Secrets Manager) with 30 Terraform-managed resources; stood up and tore down in one session.
- Made the app stateless by adding an S3 storage backend behind the existing interface (fake-client tests, no pipeline changes) and a bootstrap command that prepares an empty database for row-level security.
- Applied least privilege: separate ECS execution and task roles, chained security groups, RDS-managed database password, secrets injected at start, never baked into images.

---

## 7. Self-check questions

1. What is the difference between an image and a container?
2. Why do we copy `pyproject.toml` and install dependencies before copying `src`?
3. Why is `.env` in `.dockerignore`?
4. What does "stateless container" mean, and which two AWS services made ours stateless?
5. What is the difference between the ECS *execution role* and the *task role*?
6. Why can the database not be reached from the internet even though the app task has a public IP?
7. Why does the service start with `desired_count = 0`?
8. What does the bootstrap task do, and why must the app role be created before the tables?
9. What is in the Terraform state file that makes it sensitive, and which file should you commit instead?
10. A partial `terraform apply` failed with `AccessDenied`. Is anything broken? What do you do next?
11. What does `${API_REPO}:latest` fix compared with `$API_REPO:latest` in zsh?
12. Name three things you would change to make this production-ready.

### Answer key

1. An image is the frozen recipe plus files; a container is one running copy of it.
2. So Docker can reuse the cached dependency layer. Editing code only rebuilds the layers from the `COPY src` line down.
3. A secret baked into an image can be extracted by anyone who gets the image. Secrets arrive at run time as environment variables instead.
4. The container keeps nothing it cannot lose, so it can be replaced or duplicated freely. RDS (data) and S3 (uploads).
5. The execution role is used by ECS before our code starts (pull images, write logs, read the secrets). The task role is used by our code at run time (the uploads bucket only).
6. The security groups chain: the database group accepts port 5432 only from the task group, and the task group accepts port 3000 only from the load balancer group. The database itself is also marked not publicly accessible.
7. The tasks need images in the registry, a prepared database and a filled OpenAI secret. Starting earlier would just crash and restart.
8. It creates the limited app role, runs the migrations and creates the checkpoint tables. The role comes first so its default privileges cover tables created afterwards, and so row-level security applies to it.
9. The generated JWT secret and app-role password (and infrastructure details). Commit `.terraform.lock.hcl` (provider versions); keep the state private and git-ignored.
10. Nothing is broken: Terraform saved what it created. Give the user the missing permission and run `terraform apply` again; it continues with the remaining resources.
11. zsh treats `$VAR:l` as a "lowercase" modifier, so the tag turned into `...atest`. Braces end the variable name before the colon.
12. For example: HTTPS with a domain and certificate, private subnets with NAT or VPC endpoints, remote encrypted Terraform state with locking, database backups/standby/deletion protection, a queue and workers instead of in-process background tasks, CloudWatch alarms, and a deploy pipeline (GitHub Actions with OIDC).

---

## 8. Still open

- Alarms and notifications, HTTPS, deploy pipeline (planned).
- Demo video and final evaluation report.
- Optional cleanup: remove the inline IAM policy `freightlens-rds` from the `numan-dev` user, and delete the local Docker images (`docker image prune`).
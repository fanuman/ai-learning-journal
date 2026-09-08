# Day 17 - AWS fundamentals: IAM, EC2, S3, manual EC2 deploy

**Date completed:** _(fill in)_

## What I learned

**Why this day matters - first time off the laptop**
Everything through Week 3 ran on a personal machine or local Docker. Today: a real cloud account,
real (if small) money, and a container reachable from the actual internet for the first time.

**AWS's 2025 Free Tier changes - a real, current fact, not the old "750 free hours" model**
As of July 15, 2025, new AWS accounts no longer get an unlimited-within-limits free tier.
Instead: a **Free Plan** (up to $200 in credit over 6 months, or until credits deplete, whichever
comes first) or a **Paid Plan** (same credit, but full service access with no Free Plan
restrictions). Free Plan explicitly states "your account does not get charged" while credits
last - a real dollar balance being drawn down, not a separate "free hours" bucket running in
parallel. Two independent expiration clocks: credit expires 12 months from account creation; Free
Plan status itself expires after 6 months or when credit hits zero. A valid payment card is
required even for the Free Plan, for identity verification (small temporary hold, not a charge).

**IAM - the core security model**
Never do daily work as root - it has unauthorized-limitless power over the whole account. Create
an IAM user for real work instead, with only the permissions actually needed
(`AmazonEC2FullAccess` + `AmazonS3FullAccess` today, deliberately not `AdministratorAccess`).
IAM policies are attached directly to a user (or, in more mature setups, to a group the user
belongs to). Console access needs explicit enabling at user-creation time, separate from
programmatic access keys - conflating the two was worth getting right, since only console access
was actually needed for today's browser-based work.

**S3 - object storage, and public access as a demonstrated (not just described) safeguard**
Buckets need globally unique names. "Block all public access" is the correct default, verified
directly: a file visible fine through the authenticated S3 console returned a real `AccessDenied`
XML error when opened via a bare, unauthenticated URL - the exact mechanism that prevents the
classic "open S3 bucket" data leak, seen working rather than just read about.

**EC2 - virtual servers, and the two settings that actually matter**
AMI choice affects which package manager and setup commands work (Ubuntu's `apt`, not Amazon
Linux's `yum`/`dnf` - had to switch after initially defaulting to Amazon Linux). Security groups
are the real safety-critical setting: SSH (22) and the app port (8000) both scoped to "My IP,"
never `0.0.0.0/0` - the difference between a private, personal test deploy and a genuinely public,
attackable one.

**Docker on a fresh Linux server - one real new mechanic**
`sudo usermod -aG docker $USER` adds the current user to the `docker` group so Docker commands
don't require `sudo` on every call. Critically, this only takes effect on a **new** login session
- Linux checks group membership once at login and caches it, so the SSH session has to be closed
and reopened before `docker ps` works without a permission error. Verified this precisely:
confirmed the fix only worked after reconnecting, not before.

**Terminate, not Stop**
"Stop" halts compute billing but leaves the EBS storage volume attached and billing. "Terminate"
removes everything. Given the account's real credit-balance billing model, this was the one step
that actually protected the account, and it was done at the end.

## Real debugging journey (this day had substantially more troubleshooting than a typical lesson)

**1. Existing/reused account handling.** Signup initially failed with "email already associated
with an account" - traced to an existing account (retail Amazon or an old AWS registration) that
had never completed AWS-specific setup. Chose to continue with the existing account rather than
create a new one, reasoning: AWS limits free-tier offers to one per customer (enforced partly via
card/phone reuse), so a second signup risked landing on standard pay-as-you-go with no safety net
- higher risk than finishing setup on the account already in hand. Correctly diagnosed via the
account's own "Complete your AWS registration" flow (payment info, step 3 of 5) rather than
guessing.

**2. Verified the account was genuinely clean before touching anything.** Checked EC2 instances
across all regions (via AWS Global View, not just the default region) - a real habit worth having
specifically because a resource in an unchecked region is invisible unless you explicitly look.
Found zero compute/storage resources; the account's real MFA device had already been created
automatically during the signup flow itself (not a separate step).

**3. EC2 launch wizard's simplified UI didn't expose an "Add rule" button for the custom port
8000 rule.** Worked around it by launching with just the SSH rule, then editing the security
group's inbound rules after the instance was already running - confirmed security groups can be
edited live with no restart needed.

**4. `git clone` on the EC2 instance didn't include `chroma_db/`** - correctly gitignored per
Day 7's lesson, but that meant the fresh server genuinely had no vector index at all. Real
decision point: re-run `ingest.py` on the server (more architecturally correct - the server builds
its own state from source) vs. `scp` the already-built local `chroma_db/` up directly (faster).
Chose to copy directly for time; noted the more correct approach for later.

**5. Self-caught false alarm, worth being honest about.** After deployment succeeded, tested
`/ask` with a Week 2/3 AI-governance-corpus question ("What is prompt injection...") against the
now-e-commerce-only production pipeline - my own mistake in choosing the test question, not a
deployment bug. `used_fallback: true` was actually the *correct* answer to a genuinely
out-of-scope question, identical in shape to Project 3's "best programming language" test case.
Confirmed by checking the actual code and the container's real Chroma collections
(`trailpeak_docs` and `ai_governance_docs`, both present) before concluding anything was wrong,
then retesting with a real in-domain question (SummitCarry backpack) which returned the exact
correct result from Project 3 - $249.00, out of stock, correct sizes - now running on a real
server instead of a laptop.

## Test results - full verification

- `curl http://<ec2-ip>:8000/health` → `{"status":"ok"}` - first confirmation of a container
  reachable from a completely separate machine over the real internet
- `curl -X POST .../ask` with the SummitCarry backpack question → correct price, correct stock
  status, correct sizes, `used_fallback: false` - confirms the full pipeline (retrieval, function
  calling, structured self-audited sources) works identically on EC2 as it did locally
- Billing: root login required specifically because `numan-dev`'s scoped policies correctly denied
  Billing console access - IAM working exactly as designed, not a bug. Cost anomaly detection: none
  detected. Instance terminated cleanly, confirmed via "Terminated" state in the console.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Exact dollar cost of today's exercise not yet visible - AWS's cost data can take up to 24 hours
  to populate after first meaningful Billing console use on this account; worth checking back.

## Practice task
Signed up for and fully configured a real AWS account (root MFA, IAM user with scoped
`EC2FullAccess`/`S3FullAccess` policies, budget alert). Created and tested an S3 bucket, verifying
public access blocking with a real failed anonymous request. Launched an EC2 instance with a
correctly-scoped security group, SSH'd in, installed Docker and Git, resolved a missing
`chroma_db/` gap from `.gitignore`, and deployed `production-rag-agent`'s actual Docker image.
Verified both `/health` and a full RAG + function-calling `/ask` request from a separate machine
over the real internet, then terminated the instance and confirmed no billing anomalies. Work
done directly in the AWS Console (browser-based), not `ai-learning-journal` code files.
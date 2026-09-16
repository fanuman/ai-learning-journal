# Day 23 - Terraform basics: first IaC script (S3 bucket + IAM role)

**Date completed:** _(fill in)_

## What I learned

**What Infrastructure as Code actually solves**
Every AWS day this week involved manual console clicking - easy to forget a step, hard to review,
and requiring a separate manual cleanup checklist to avoid leaving something running (the exact
EC2/Lambda/ECS pattern from Days 17-22). Terraform describes infrastructure as text, checked into
git like any other code - reviewable, re-runnable identically, and torn down with one command
instead of a manual, order-dependent sequence.

**Core concepts**
- **Provider** (`aws`) - which cloud, authenticated via the same AWS CLI credentials already
  configured for `numan-dev` since Day 19, nothing new to set up
- **Resource** - a declarative description of an end state (`aws_iam_role`, `aws_s3_bucket`), not
  a sequence of steps
- **State file** (`terraform.tfstate`) - Terraform's own record of what it actually created,
  used to compute what's changed on the next run. Never hand-edited; excluded from git (can
  contain sensitive resource details), same reasoning as `.env`/`venv/`

**The workflow: init -> plan -> apply -> destroy**
`init` downloads the provider plugin. `plan` is a genuine dry run - shows exactly what would
change (`+` create, `~` modify, `-` destroy) *before* anything happens, something no AWS console
click gives you. `apply` creates the real resources. `destroy` removes everything the state file
knows about, in one command.

**Automatic dependency ordering - proven, not just claimed**
Referencing `aws_iam_role.ec2_secrets_role.id` inside the policy resource was the only ordering
information given. Confirmed directly in the real `apply` output: the role finished creating
*before* the policy resource even started - Terraform correctly sequenced them from the reference
alone, no manual ordering needed. Confirmed the reverse on `destroy` too: the policy was destroyed
*before* the role, exactly the safe teardown order (can't cleanly detach a policy from an
already-deleted role) - Terraform reversed its own dependency graph automatically for teardown as
well.

## Today's exercise: recreating a known role as code

Deliberately recreated Day 20's EC2 Secrets Manager role (same trust policy, same scoped
`secretsmanager:GetSecretValue` permission) as Terraform code, alongside a new S3 bucket - using
something already built by hand made the value of IaC concrete rather than abstract. Used a
`-tf` suffix (`production-rag-agent-ec2-role-tf`) to avoid a naming collision with the real,
still-existing role from Day 20, since IAM role names must be unique per account.

## Setup note
`brew install terraform` failed outright - HashiCorp removed Terraform from Homebrew's default
formula list over a licensing change. Fixed with HashiCorp's own tap:
```
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```
(A `brew install --cask termora` happened by accident along the way, from a fuzzy-match suggestion
during the failed search - harmless, unrelated terminal app, not Terraform.)

## Test results
- `terraform plan` correctly previewed exactly 3 resources to create, matching `main.tf` - no
  surprises between plan and apply
- `terraform apply` -> `Apply complete! Resources: 3 added, 0 changed, 0 destroyed.` Verified both
  the IAM role (with correct trust policy and inline permission) and S3 bucket directly in the AWS
  console, matching what `plan` predicted
- `terraform destroy` -> `Destroy complete! Resources: 3 destroyed.` - confirmed the dependency-
  aware reverse-order teardown described above, and confirmed nothing left behind afterward

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Noted but not used today: `terraform apply -out=plan.tfplan` locks in exactly what was
  previewed, closing the small gap where real-world state could theoretically shift between
  `plan` and `apply` - the more rigorous production pattern, not needed for today's isolated,
  single-user exercise

## Practice task
Installed Terraform via HashiCorp's own tap after the default Homebrew formula was removed. Wrote
`infra/terraform/main.tf` recreating Day 20's EC2 Secrets Manager IAM role plus a new S3 bucket,
deliberately choosing a resource already built by hand to make the IaC comparison concrete. Ran
the full `init` -> `plan` -> `apply` -> `destroy` cycle, verifying resources directly in the AWS
console after `apply` and confirming complete, correctly-ordered teardown after `destroy`.
Excluded `terraform.tfstate` and `.terraform/` from git. Committed `main.tf` to
`production-rag-agent`.
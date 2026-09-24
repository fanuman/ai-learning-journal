# Day 29 - Managed model serving: AWS Bedrock vs. OpenAI vs. SageMaker

**Date completed:** _(fill in)_

## What I learned

**Three ways to get a model to actually respond to a prompt, and what each one trades away**
- **OpenAI (direct API)** - simplest possible integration, always has OpenAI's own newest models
  first. Traffic leaves AWS entirely, separate vendor relationship and billing, no IAM/VPC
  integration, locked to OpenAI's models only.
- **AWS Bedrock** - one API (the Converse API) in front of multiple providers' models
  (Anthropic, Meta, Amazon, others), while traffic, IAM, and billing all stay inside the same AWS
  account already used for everything else in this project. The real cost is setup friction, not
  runtime friction - today's session hit that friction directly (below), not in theory.
- **SageMaker** - full control: host literally any model, including open-source weights or a
  fine-tuned model's own weights, with full control over hardware and scaling. The cost is that
  *you* become the infrastructure operator - provisioning endpoints, paying for capacity even
  when idle. Not evaluated hands-on today (see Known gaps / Questions) - genuinely only worth it
  when a specific model isn't available as anyone's hosted API.

**The Converse API specifically**: Bedrock's current, unified way to call any supported model -
`bedrock.converse(modelId=..., messages=[...])` - replacing the older, provider-specific
`invoke_model` calls. Meant to make swapping providers close to a one-line change once the
plumbing exists, which held up in practice: the actual call in `bedrock_comparison.py` differs
from an OpenAI chat call mostly in shape, not in complexity.

## Today's exercise - a real side-by-side, not a reputation-based comparison

Wrote `bedrock_comparison.py` to call the same prompt against the OpenAI API
(`gpt-4o-mini`) and against Bedrock's Converse API for a Claude model, timing both and printing
the actual output side by side - deliberately real infrastructure, not a description of how it
*should* work.

**Result** (single sample, see caveat below):
```
OpenAI (3.61s): RAG (Retrieval-Augmented Generation) combines retrieval of relevant documents
with generative language modeling to produce responses, while fine-tuning involves training a
pre-existing model on specific datasets to improve its performance on particular tasks.

Bedrock/Claude (1.57s): RAG retrieves external documents to augment prompts before generation,
while fine-tuning updates model weights to internalize new knowledge or behaviors.
```
Both answers correct, Bedrock notably faster on this one call. **This is one sample per backend,
not a benchmark** - real comparison would need multiple runs to separate genuine latency
differences from ordinary network/API noise on a given call.

## The real debugging log - five distinct issues, in the order they actually happened

Getting to that one working comparison took five separate, genuine obstacles:

1. **The Bedrock console's "Model access" page has been retired** - AWS's own platform change
   since original training knowledge, replacing the old manual "request access per model" flow
   with automatic enablement on first invocation. Adjusted the plan on the spot rather than
   following outdated instructions.
2. **Wrong model ID for the region**: `anthropic.claude-3-haiku-20240307-v1:0` returned
   `ValidationException: the provided model identifier is invalid` in `eu-north-1` - that model
   simply isn't offered there. Fixed by calling `bedrock.list_foundation_models()` (the
   *control-plane* client, `boto3.client("bedrock", ...)`, distinct from the inference client
   `bedrock-runtime`) to get the account's real, region-specific list instead of guessing.
3. **`AccessDeniedException` on `bedrock:ListFoundationModels`**, then again on
   `bedrock:ListInferenceProfiles`** - fixed by attaching Bedrock permissions to `numan-dev`.
   First attempt used the `AmazonBedrockFullAccess` managed policy, which hit **IAM's 10-managed-
   policy-per-user quota** (accumulated from many days of prior AWS setup). Switched to a scoped
   **inline** policy instead - not just a workaround, actually the more correct choice (narrower
   permissions), and inline policies don't count against that quota at all.
4. **`ValidationException: on-demand throughput isn't supported` for
   `anthropic.claude-haiku-4-5-20251001-v1:0`** - some newer/higher-demand Bedrock models require
   an **inference profile ID** instead of the raw model ID. Found the right one
   (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`) via `list_inference_profiles()` and used that
   as `modelId` instead.
5. **The exact same access-denied error reappeared immediately after fixing the policy** - not a
   wrong fix, just normal **IAM policy propagation delay**. Retrying a short time later worked
   without any further change.

**Handled honestly, not guessed at**: the account's Bedrock model list included several
unfamiliar names (`gpt-6-astra`, `claude-opus-5`, `grok-4.6` among them) that post-date reliable
knowledge. Declined to speak confidently about their characteristics and picked a model there was
real grounding on (Claude Haiku 4.5) for the actual test, rather than assuming.

## A sixth issue, from redeploying the infrastructure itself

Separately, redeploying the Terraform-managed ECS stack (torn down between sessions per the
"destroyed between active use" pattern) hit its own new permission gap:
**`AccessDeniedException` on `logs:PutRetentionPolicy`** when Terraform tried to create the
CloudWatch log group with `retention_in_days = 3` - a permission distinct from the general
logging access `numan-dev` already had. Added to the same scoped inline policy used for Bedrock
(rather than a second managed policy, for the same quota reason above). The first failed
`apply` left the log group **tainted** in Terraform's state, so the next `apply` destroyed and
recreated it (`-/+`) rather than updating in place - expected Terraform behavior after a failed
create, not a new problem. Final apply: `2 added, 1 changed, 1 destroyed`, clean.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether it's worth doing a real, hands-on SageMaker exercise (deploying an open-source or the
  Day 28 fine-tuned model as a self-hosted endpoint) to complete the three-way comparison with
  actual infrastructure rather than the conceptual pros/cons discussed today
- Whether Bedrock's per-model inference-profile requirement is something that can be checked in
  advance (a specific field in `list_foundation_models()`'s response) rather than discovered only
  by hitting the `ValidationException`

## Practice task
Compared AWS Bedrock's Converse API against the OpenAI API directly, using a real side-by-side
script (`bedrock_comparison.py`) rather than a described comparison, and confirmed Bedrock's
latency advantage on one sample while being honest that one sample isn't a benchmark. Worked
through a full, real AWS Bedrock onboarding sequence from scratch - a retired console flow, a
wrong-region model ID, an IAM managed-policy quota wall, an inference-profile requirement, and IAM
propagation delay - diagnosing each directly against the live AWS account rather than assuming a
fix. Also hit and fixed a sixth, unrelated permission gap (`logs:PutRetentionPolicy`) while
redeploying the existing Terraform-managed ECS infrastructure for this exercise. Landed on a plain-
English decision framework for OpenAI vs. Bedrock vs. SageMaker: simplest, AWS-native middle
ground, and maximum-control-maximum-responsibility, respectively - with SageMaker's evaluation
staying conceptual only, not yet exercised hands-on.
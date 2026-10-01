# Day 35 - Monitoring & alerting: CloudWatch dashboards, alarms, and a real fire drill

**Date completed:** _(fill in)_

## What I learned

**A log line nobody's watching might as well not exist.** `secrets.py` has logged a warning on
Secrets Manager failures since Week 4/5 - genuinely useful information, completely inert, because
nothing ever read it unless someone happened to be tailing logs at the right moment. Today's real
lesson: monitoring isn't about collecting more data, it's about turning data that already exists
into something that actively reaches a person.

**The actual chain, piece by piece:**
- **Metric filter** - CloudWatch scanning a log group for one exact phrase, incrementing a counter
  every time it matches. Turns an unstructured log line into a real, queryable number.
- **Alarm** - watches a metric on a timer and asks one question: has it crossed a threshold. Two
  genuinely different shapes used today: the secret-fallback alarm fires the instant the count is
  ever above zero (any occurrence is real), while the CPU/memory alarms require 2 consecutive
  breaching minutes (brief spikes are normal, sustained load isn't).
- **SNS** - the actual notifier. An alarm only flips an internal OK/ALARM state; SNS is what turns
  that state change into an email landing in an inbox. Required an explicit subscription
  confirmation (a real link click) before anything could be delivered - a legitimate anti-spam/
  consent step, not busywork.
- **Dashboard** - just a saved view of the same metrics as live graphs, nothing more.

**`AWS/ECS`'s `CPUUtilization`/`MemoryUtilization` metrics need zero extra setup** - no Container
Insights, no code change - they're published automatically per service. The only real work was the
custom secret-fallback metric, since that one didn't exist anywhere until a metric filter created it
from a log line.

**A genuinely surprising ECS behavior, found live, not read about**: without a load balancer or
health check configured on this service, a rolling deployment's decision about *which* task to keep
during a scale-down is less predictable than expected. The very first task (`8807ed68`, always
healthy) survived through *two* separate `force-new-deployment` calls while newer tasks came and
went around it, before eventually being replaced on its own timeline. This didn't break anything -
a different available task was always serving traffic - but it meant an early post-fix `curl` test
was actually hitting the original never-broken task, not proof of the fix specifically. Real
evidence came from checking CloudWatch Logs directly instead of trusting which task a curl happened
to land on.

**Log-metric-filter-based alarms clear slower than they trigger.** Our secret-fallback alarm
reached `ALARM` almost immediately (well within a minute of the log line existing), but took several
minutes longer to settle back to `OK` even after the underlying problem was fixed and no new
warnings were being logged. `treat_missing_data: notBreaching` is correct and did eventually resolve
it, but a sparse, push-only custom metric needs more successive empty periods to confirm "quiet" than
a continuously-reporting one does.

## Today's exercise

New `infra/terraform/monitoring.tf`, added to the existing ECS Terraform stack:
- `aws_sns_topic` + `aws_sns_topic_subscription` (email) - the actual alert channel
- `aws_cloudwatch_log_metric_filter` matching the exact Day 34 warning text
  (`"Could not load secret from Secrets Manager"`) - closes that exact gap
- Three `aws_cloudwatch_metric_alarm` resources: secret-fallback (threshold 0, 1 period),
  high-CPU and high-memory (threshold 80%, 2 periods) - all three wired to the same SNS topic
- `aws_cloudwatch_dashboard` combining CPU/memory and the secret-fallback count in one view

New `alert_email` variable in `variables.tf`; the actual address lives in the gitignored
`terraform.tfvars`, same pattern as `my_ip`.

## Test results - a real fire drill, not just a `terraform apply`

Deployed the full stack fresh, confirmed the app healthy (ingest + a real `/ask` call), confirmed
the SNS email subscription, then deliberately corrupted the production secret:
```bash
aws secretsmanager put-secret-value --secret-id production-rag-agent/openai-api-key \
  --secret-string 'not-valid-json' --region eu-north-1
aws ecs update-service --cluster production-rag-agent-tf-cluster \
  --service production-rag-agent-tf-service --force-new-deployment --region eu-north-1
```

**Confirmed via direct log query**, not assumption, that the new task actually hit the broken path:
```
Could not load secret from Secrets Manager, falling back to existing env: Expecting value: line 1 column 1 (char 0)
```
exactly matching `json.loads` failing on the corrupted (non-JSON) string.

**The alarm fired for real** (`ALARM`, `"Threshold Crossed: 1 datapoint [1.0] was greater than the
threshold (0.0)"`), and **the email actually arrived** - confirmed, not assumed.

Fixed the secret with the real key, forced another redeploy, and after navigating the task-churn
confusion above, confirmed on a genuinely fresh task (started after the fix, verified via a clean
re-ingest + `/ask` call returning a correct, sourced answer) that the fix held. The alarm settled
back to `OK` a few minutes later, once no new warnings had appeared.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether this service should get an actual health check / load balancer eventually, given today's
  evidence that rolling deployments behave less predictably without one
- Whether the CPU/memory alarm thresholds (80%, 2 minutes) are reasonable defaults or just
  convenient round numbers - never actually tested under real load (a Locust run) to see if they'd
  trigger sensibly

## Practice task
Added a real CloudWatch monitoring layer to the existing ECS Terraform stack - a metric filter and
alarm closing Day 34's "logged but nobody's watching" secret-fallback gap, two standard CPU/memory
health alarms, an SNS email channel, and a combined dashboard. Validated the entire chain with a
genuine fire drill rather than trusting the Terraform plan alone: corrupted the real secret,
confirmed via direct CloudWatch Logs query that the failure was actually hit, watched the alarm
fire and a real email arrive, then fixed the secret and confirmed the alarm cleared once the
problem was genuinely resolved. Along the way, hit and correctly diagnosed a real, non-obvious ECS
behavior - without a health check, a rolling deployment's choice of which task to retain during
scale-down isn't fully predictable - without it undermining the validity of the actual test.
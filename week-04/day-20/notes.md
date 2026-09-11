# Day 20 - Secrets Manager + CloudWatch logging/monitoring

**Date completed:** _(fill in)_

## What I learned

**Why Secrets Manager over a plain Lambda env var**
Day 18's `OPENAI_API_KEY` environment variable is plain text, visible to anyone with read access
to the function config, with no separate access control or audit trail. Secrets Manager encrypts
the secret at rest, controls read access via its own IAM permissions distinct from "can view this
Lambda function," and logs every access. Real upgrade path from Day 3's original "someday, a
proper secrets service" note.

**Extending Day 18's IAM role-vs-user distinction, concretely**
The permission to read the secret goes on the Lambda **execution role**, not on the `numan-dev`
**user** - two different identities doing two different jobs. `numan-dev` needs permission to
*create* the secret in the console; the *running function* needs its own, separate permission to
*read* it at invocation time. Unlike this week's broad FullAccess simplifications, this permission
was genuinely easy to scope tightly - one action (`secretsmanager:GetSecretValue`), one specific
resource ARN.

**Code change**
```python
def load_secret_into_env():
    client = boto3.client("secretsmanager", region_name="eu-north-1")
    response = client.get_secret_value(SecretId="production-rag-agent/openai-api-key")
    secret_dict = json.loads(response["SecretString"])
    os.environ["OPENAI_API_KEY"] = secret_dict["OPENAI_API_KEY"]

load_secret_into_env()  # module level - fetched once per container
llm_client = ProductionLLMClient()
```
`boto3` is pre-installed in every Lambda Python runtime - no need to bundle it. Setting
`os.environ` rather than refactoring `ProductionLLMClient` lets Day 3's existing, tested class
work completely unchanged. Fetching happens at module level for the same reason Day 18 measured
directly (`Init Duration`) - once per container, not once per request.

**Real logging instead of `print()`**
Replaced prints with Python's `logging` module (`logger.info`, `logger.error`) - shows up in
CloudWatch with real severity levels and timestamps, filterable at scale, unlike undifferentiated
print statements.

**CloudWatch Alarms - same pattern as Day 17's Budget alert, applied to app health**
Metric: `AWS/Lambda` → `Errors`, FunctionName `production-rag-chat`, Statistic **Sum** (not
Average - Sum is the correct choice for count metrics generally, even though today's specific
"greater than 0" threshold happens to behave identically either way), threshold `> 0`, notifying
via a new SNS topic + email subscription.

## Bugs and permission gaps found and fixed

**Permission gaps (five, same pattern as every AWS day this week):**
1. `numan-dev` needed `SecretsManagerReadWrite` to create the secret at all
2. The Lambda execution role needed a new inline policy (`secretsmanager:GetSecretValue`, scoped
   to the specific secret ARN) to read it at runtime
3. `numan-dev` needed `AmazonSNSFullAccess` to create the alarm's notification topic
4. A one-off, unrelated wizard side-check (`rds:DescribeDBInstances`) blocked the Secrets Manager
   "Store" button entirely, despite having nothing to do with the actual secret being stored -
   worked around with a temporary, narrowly-scoped inline RDS-list policy, removed again
   immediately after confirming the secret was actually created (not left attached, since it had
   no ongoing legitimate use for this project)
5. Confirmed `SecretsManagerReadWrite`, unlike the RDS workaround, has genuine ongoing use and was
   kept

**Code bugs, found via careful review and one real accidental regression:**
- Removed a leftover `load_dotenv()` call at the top of `lambda_app.py` - dead code, since Lambda
  has no `.env` file in its deployment package at all; this call was silently doing nothing every
  invocation
- Added a missing `logger.error(...)` inside `/chat`'s exception handler - without it, a real
  production error would return a 502 to the caller with zero trace in CloudWatch, defeating much
  of today's monitoring purpose
- **Caught, before redeploying:** the rewritten `lambda_app.py` was missing
  `api_gateway_base_path="/default/production-rag-chat"` on the `Mangum(app, ...)` line entirely -
  would have reintroduced Day 18's exact stage-naming path bug. Caught by explicitly comparing
  against the known-working Day 18 file rather than assuming a rewritten file carried everything
  forward correctly.
- **A genuine, unplanned bug during testing:** `Runtime.ImportModuleError: No module named
  'lambda_app'` - not the deliberate secret-break test, but a real zip-packaging mistake (almost
  certainly re-zipping from one directory level off, nesting `lambda_app.py` inside a subfolder
  instead of at the zip root). Diagnosed directly via CloudWatch Logs (`INIT_REPORT ... Status:
  error Error Type: Runtime.ImportModuleError`), fixed by re-zipping correctly from inside
  `lambda_package/` (`zip -r ../lambda_deploy.zip .`, with the trailing dot mattering).

## The SNS/Gmail auto-unsubscribe quirk - a real, known issue, deliberately left unresolved

Repeatedly received "Unsubscribe Confirmation" emails immediately after confirming and
resubscribing to the SNS topic. Root-caused via search to a well-documented AWS/Gmail interaction:
email security scanners "pre-fetch" every link in an email to check it's safe *before* the user
ever sees it - this pre-fetch itself counts as a real click to AWS, silently unsubscribing without
any actual human action. Confirmed this is a known issue (AWS's own re:Post knowledge center
documents it directly), not a mistake in today's setup.

**Decision made deliberately, not left as an unnoticed gap:** the CloudWatch Alarm itself is
correctly configured and will fire regardless of whether the email notification reliably reaches
Gmail - alarm state is always directly checkable in the console even if email delivery is
unreliable. The real, permanent fix (restricting unsubscribe to the topic/subscription owner only)
requires more setup than today's lesson scope, and nothing later in the roadmap depends on this
specific email arriving reliably. Chose to postpone rather than over-invest in an email
deliverability side-quest unrelated to the actual AWS/monitoring concepts today was teaching.

## Test results

- `/health` and `/chat` both working after all fixes, confirmed against the same Day 18 URLs
- CloudWatch Logs confirmed `Secret loaded successfully` - real proof the key came from Secrets
  Manager, not a leftover plaintext env var
- The accidental `lambda_app` import bug served as a genuine, live test of the observability
  chain: a real unhandled exception, caught and diagnosed directly via CloudWatch Logs
  (`INIT_REPORT ... Error Type: Runtime.ImportModuleError`), without needing to deliberately break
  anything - stronger evidence the logging/monitoring setup works than a scripted test would have
  been

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- SNS email deliverability to Gmail - documented as a known issue, intentionally not fully
  resolved today (see above)

## Practice task
Migrated the Lambda function's OpenAI API key from a plain environment variable (Day 18) to AWS
Secrets Manager, with a correctly-scoped IAM policy on the Lambda execution role (not `numan-dev`)
granting read access to just that one secret. Upgraded from `print()` to Python's `logging`
module. Set up a CloudWatch Alarm on Lambda Errors with SNS email notification. Found and fixed a
real, unplanned zip-packaging bug via CloudWatch Logs during testing, and caught a self-introduced
regression (missing `api_gateway_base_path`) before it reached deployment. Investigated and made a
deliberate, reasoned decision to postpone a known SNS/Gmail email-deliverability quirk rather than
over-invest in resolving it, since it doesn't block anything downstream. Work done directly in the
AWS Console, not `ai-learning-journal` code files.
# Day 2 - Prompt engineering (zero-shot, few-shot, chain-of-thought, structured output)

**Date completed:** _(fill in)_

## What I learned

**The core idea**
The model only knows what you type - prompt engineering is phrasing requests so the model
reliably gives back what you actually need, the same way clear instructions get better results
from a new employee.

**Four techniques**
- **Zero-shot** - just ask directly, no examples. Fine for simple/common tasks, gets shaky on
  anything needing a specific style or format.
- **Few-shot** - show 2-3 worked examples (input -> output) before the real question, so the
  model picks up the pattern. Best for consistency (exact wording/format), not just correctness.
- **Chain-of-thought** - add "let's think step by step" for multi-step reasoning tasks (math,
  logic). Improves accuracy the same way showing your work does on a test.
- **Structured output** - force the reply into an exact schema using Pydantic + `.parse()`
  instead of `.create()`, so the response comes back as a validated Python object, not free text
  you have to hope is parseable.

**Best practices for combining them**
- Use delimiters (`"""`) to separate instructions from the actual data being processed - also a
  lightweight defense against the data itself containing text that looks like an instruction
  (early preview of prompt-injection, covered properly in Week 7).
- Be specific about format, length, and tone - vague instructions like "summarize it" produce
  wildly inconsistent results across calls.
- Few-shot + structured output together is the standard production pattern: few-shot examples
  nudge the model's *judgment* (is this really High urgency?), structured output guarantees the
  *shape* is always parseable regardless.

## Code I wrote

Built `day2_prompting.py` - a ticket classifier comparing zero-shot vs few-shot vs a "best"
prompt (few-shot + structured output + tone/length spec + delimiter instruction), tested against
5 deliberately ambiguous support tickets.

```python
class TicketClassification(BaseModel):
    category: str   # Billing | Technical | General
    urgency: str     # Low | Medium | High
    summary: str

def classify_ticket_best_prompt(ticket_text: str) -> TicketClassification:
    user_prompt = f'Ticket:\n"""\n{ticket_text}\n"""'
    completion = openai_client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": BEST_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        response_format=TicketClassification
    )
    return completion.choices[0].message.parsed
```

**Bug found and fixed:** the zero-shot/few-shot function was type-hinted `-> TicketClassification`
but actually returned `completion.choices[0].message.content` (a plain string, since it used
`.create()` with no `response_format`). Fixed the type hint to `-> str` - a reminder that type
hints aren't enforced at runtime, so a mismatch like this won't crash, it'll just quietly mislead
anyone reading the function signature.

## Test results and findings

Ran 5 deliberately ambiguous tickets through all three prompt versions:

1. **Payment declined but locked out (Billing vs Technical symptom)** - all three agreed
   Billing/High. Expected this one to be the clearest few-shot effect; it wasn't - the model
   handled it fine even zero-shot.
2. **Export data before closing account** - **real few-shot effect found.** Zero-shot said
   Urgency: Medium, few-shot and "best" both said Low. The few-shot examples included a similar
   informational how-to question labeled Low, which anchored the model toward the same judgment
   here.
3. **Recurring freeze, angry tone** - all three agreed Technical/High, but the *raw formatting*
   of the zero-shot reply was inconsistent with every other zero-shot response (comma-separated
   on one line instead of newline-separated). This is the clearest practical argument for
   structured output: free text isn't even reliably consistent with itself, which would silently
   break a naive string-parsing approach.
4. **Annual discount question** - category flipped: zero-shot said Billing, few-shot said
   General, "best" flipped back to Billing. Genuinely ambiguous case (pricing question, not a
   problem/complaint like the few-shot examples). Can't fully separate "few-shot changed the
   model's judgment" from "temperature-driven randomness" without a controlled rerun.
5. **Can't login, no reset email** - fully consistent across all three, Technical/High.

**Key follow-up insight: determinism matters for testing.** Re-ran the script and ticket #1 came
back slightly differently worded both times with identical code/prompt - caused by the default
`temperature` setting (from Day 1) not being fixed. To properly test whether a prompt change
*causes* a different result (vs. random variation), set `temperature=0` and rerun multiple times
- planned as a follow-up experiment on ticket #4 to confirm if the category flip was a real
few-shot effect or noise.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Follow-up to try: rerun ticket #4 three times at `temperature=0` under each prompt version to
  confirm whether the Billing/General flip is a genuine few-shot effect or temperature noise.

## Practice task
`day2_prompting.py` - ticket classifier comparing zero-shot, few-shot, and structured-output
(few-shot + Pydantic schema) prompting across 5 ambiguous test tickets. Located in `practice/`.
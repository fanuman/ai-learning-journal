# Day 14 - Structured output and function calling: Pydantic validation

**Date completed:** _(fill in)_

## What I learned

**The distinction between structured output (Day 2) and function calling (today)**
Structured output always produces the same fixed shape every time - "format your answer this
way." Function calling is fundamentally different: the model is given a list of *available
actions* and decides whether it needs zero, one, or several of them before it can answer. The
model never executes anything itself - it only tells your code which function to call and with
what arguments (validated via the same Pydantic pattern as always). Your code does the real
execution and hands the result back.

**The full round-trip loop**
1. Send the user's message plus a list of available `tools` to the model
2. Model responds with either normal text (no tool needed) or a `tool_calls` list (name + JSON
   arguments)
3. Your code parses the arguments (`json.loads()` - they arrive as a string) and actually calls
   the real Python function
4. The result gets appended to the conversation as a new message with `role="tool"`, tagged with
   `tool_call_id` so the model knows which call it answers
5. **A second API call** sends the updated conversation (now including the tool's result) back to
   the model, which writes the actual final answer

**`pydantic_function_tool()`**
Auto-generates the JSON schema the model needs directly from a Pydantic class - same modeling
skill as every day since Day 2, just handed to `tools=` instead of `response_format=`. The class
docstring and field descriptions are not just documentation - they're literally what the model
reads to decide *when* to reach for each tool, so they need to be written with real care.

**This is the direct foundation for Day 16's agents.** Today is the single-step version of tool
use; agents just run this same loop repeatedly, letting the model call a tool, read the result,
and decide whether it needs to call another one before finally answering.

## Two real findings: the mechanism works, trust doesn't come free

Both tests today revealed the same underlying problem in two different shapes: giving a model a
tool does not guarantee it gets called, or trusted, by default. The model's own trained priors
can override or bypass a correctly-available tool.

**Finding 1: "What time is it?" - tool called and correct, but the model denied having the
capability anyway.** `GetCurrentTime` executed successfully (`result: 2026-09-03 11:21:35`),
correctly appended to `messages` as a `role="tool"` entry - verified directly by printing
`messages` before the second call, confirming the data really was there. The model's final
answer still claimed it had no real-time capability at all, flatly contradicting the correct
result sitting three messages back in its own context. This is the same class of failure as Day
1's confident wrong date and Day 6's negation-blindness - strong trained-in priors can override
correct information that's directly present in context. Fixed with an explicit system prompt:
"When a tool returns a result, treat it as ground truth... do not claim you lack this capability."
Rerun with identical tool execution and identical correct data produced the correct final answer
- proof the mechanism was never broken, only the model's willingness to trust its own tool output.

**Finding 2: "What is prompt injection?" - tool not called at all, despite being available and
directly relevant.** The model answered entirely from its own training knowledge - `tool_calls`
was `None`. The answer was plausible and reasonably correct-sounding, but invented its own
three-category framework ("Manipulating Input Structure," "Injecting Instructions," "Contextual
Misleading") that appears nowhere in the actual OWASP document. Quieter and more dangerous than
Finding 1: a confident, well-formed answer that could be from the corpus or could just be general
knowledge, with no obvious signal telling them apart. Same root cause as Day 13's AI RMF finding
(model leaning on training knowledge instead of retrieved context) surfacing here in a tool-use
context rather than a pure RAG one. Fixed with a stronger, explicitly scoped system prompt
("for ANY question about AI governance/security/prompt injection/risk management topics, you MUST
call SearchDocuments first... even if you believe you already know the answer"). Rerun
successfully triggered the tool call - verified as genuinely grounded, not just claimed, by
matching the final answer's exact structure (two named injection types, two named mitigation
strategies) against the real retrieved chunk, which even carried table-of-contents formatting
artifacts only present in the actual extracted PDF text.

**Verified the fix didn't overcorrect.** "What's 2+2?" still produced `tool_calls=None` and a
direct answer - confirming the forceful "you MUST call SearchDocuments" instruction was scoped
narrowly enough (specific topics named) that it didn't cause reflexive tool-calling on unrelated
questions.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Worth carrying into Day 16: this same trust-calibration problem will likely compound in a
  multi-step agent loop, where several tool-use decisions happen in sequence rather than just
  once.

## Practice task
Built `GetCurrentTime` and `SearchDocuments` tools with `pydantic_function_tool()`, wired up the
full call -> execute -> feed-back -> final-answer loop. Found and fixed two real trust-calibration
failures (a correct tool result being denied, and a relevant tool not being called at all despite
being available), both traced to root cause via debug printing of the raw `messages` list rather
than assumption, and both fixed with explicit system prompt instructions rather than any change
to the mechanism itself, which worked correctly from the first attempt. Confirmed the fix doesn't
cause unnecessary tool calls on unrelated questions. Located in `week-03/day-14/practice/`.
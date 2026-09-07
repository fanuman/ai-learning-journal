# Day 16 - AI agents: ReAct pattern, tool use, multi-tool agent

**Date completed:** _(fill in)_

## What I learned

**Why today is genuinely different from Day 14 and Project 3**
Day 14 and Project 3 both followed a single-decision shape: ask the model, it optionally calls
*one* tool, feed the result back, get an answer. Today's question this couldn't answer: what if
answering requires several *dependent* steps, where the model can't know it needs step 3 until
it's seen the result of step 2 (e.g. can't apply a discount before knowing the subtotal, can't
know the subtotal before knowing both item prices)? That requires a genuine loop, not one round
trip.

**ReAct - Reasoning, Acting, Observing, repeated**
The original ReAct pattern had the model write explicit "Thought:" text before acting. With
native function calling, that internal reasoning happens mostly implicitly - the model just emits
`tool_calls` directly. The actually load-bearing part isn't the verbalized thought, it's the loop
itself: keep calling the API, letting the model act and observe, until *it* stops requesting tools
on its own.

**The structural difference, in code**
Day 14: `if tool_calls: execute once, call the API a second time.` Today: a `for` loop that keeps
calling the API as many times as needed, appending each tool result back into the conversation,
only stopping when a response comes back with no `tool_calls` at all. That's the entire mechanism
- everything else (three tools instead of one, a richer system prompt) is scaffolding around that
one structural change.

**`max_iterations` is a real safety guard, not decoration**
Without a hard ceiling, a model stuck in a non-productive loop (calling the same tool repeatedly
without making progress - a genuine real-world agent failure mode) would run indefinitely, burning
real API cost with no natural stopping point. Same defensive instinct as Day 3's retry limits,
applied to a new failure shape.

## Code I wrote

Built three chained tools (`CheckAvailability`, `CalculateTotal`, `ApplyDiscount`) where the
second and third genuinely depend on outputs the model doesn't have at the start - deliberately
designed so a single tool call could never answer the test question, forcing a real multi-step
loop. Built `run_agent()`: a `for` loop up to `max_iterations`, appending each assistant message
and each tool result into `messages`, returning as soon as a response has no `tool_calls`.

## Bug found and fixed: fabricated tool arguments from a missing information source

**First run:** the model called `CheckAvailability({'sku': 'StormShield-jacket'})` and
`CheckAvailability({'sku': 'TrekLight-poles'})` - both invented, plausible-looking SKU strings
derived from the product names in the question, neither matching the real SKUs
(`TP-JKT-001`, `TP-POLE-006`). Both lookups correctly returned "not found," and the model
gave up and asked for clarification instead of proceeding.

**Root cause, and why this never happened in Project 3:** in Project 3, `CheckAvailability` was
always called *after* RAG retrieval, and the retrieved product catalog chunk contained the real
SKU directly next to the product name - the model read the correct SKU from context before ever
calling the tool. Today's standalone agent has no retrieval step at all - just tools and a system
prompt - so there was genuinely no source anywhere in the conversation for the real SKU values.
Not a reasoning failure; a real information gap the model filled in the only way it could
(plausible guessing from the name).

**Fix:** added an explicit name-to-SKU mapping directly into the system prompt - the standalone
equivalent of what RAG provided for free in Project 3. Rerun correctly called
`CheckAvailability({'sku': 'TP-JKT-001'})` with the real code.

**General principle worth remembering:** a tool is only as reliable as the information available
to fill in its arguments correctly. This is exactly why agentic RAG systems pair retrieval with
action tools - retrieval's job is often resolving a vague human reference ("the jacket") into the
precise identifier ("TP-JKT-001") an action tool actually needs.

## Test results - all three behaviors verified

**1. Full multi-step chain (real question, no constraints):** 4 actions across 3 iterations -
`CheckAvailability` x2 (same iteration, correctly requested in parallel since they don't depend on
each other), then `CalculateTotal` only after seeing both real prices, then `ApplyDiscount` only
after seeing the actual subtotal (`278`, not a guess). Final answer correctly synthesized all four
observations - both prices, both stock statuses, subtotal, and discounted total - into one
coherent response.

**2. Deliberately triggered failure (`max_iterations=1`):** both lookups fired correctly in the
single allowed iteration (confirming iteration limits don't block legitimate parallel actions
within one turn), but the loop exhausted its cap before reaching `CalculateTotal`/`ApplyDiscount`.
Returned the honest "stopped after reaching max iterations without a final answer" message,
**not** a fabricated or guessed total. This is the safe version of running out of steps - real
risk would have been the model eyeballing two prices in context and guessing a plausible-sounding
subtotal in prose without actually calling `CalculateTotal`, which didn't happen.

**3. Zero-tool question ("What's 2+2?"):** no iterations printed at all - direct answer on the
first pass, confirming the loop doesn't reflexively reach for tools when none are needed.

## Questions / things that confused me
- _(fill in anything still fuzzy)_

## Practice task
Built a 3-tool agent (`CheckAvailability`, `CalculateTotal`, `ApplyDiscount`) with a genuine
ReAct-style loop (`run_agent()`, looping on `tool_calls` until none remain). Found and fixed a
fabricated-SKU bug caused by a real information gap (no retrieval step to supply real SKUs, unlike
Project 3). Verified three distinct behaviors: a correct multi-step dependent chain, a safe
(non-fabricating) failure when artificially iteration-capped, and a correct zero-tool-call no-op
on a question needing no action. Located in `week-04/day-16/practice/`.
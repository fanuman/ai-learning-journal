# Day 38 - Extraction pipeline, LangGraph, LangSmith, first eval

## What was built
parse -> classify -> (extract_quote | extract_invoice | unsupported) -> validate, as a LangGraph StateGraph.
The LLM only copies text ("1.234,50", "USD 4 195.00"). Code converts to integer cents and dates, and code validates.
LangSmith traces every run. An evaluation harness scores the pipeline against truth.json from the synthetic generator.

## LangGraph vocabulary
- State: one TypedDict (DocState) holding everything known about a document; nodes add to it.
- Node: function(state) -> dict of the keys it changes.
- Edge: fixed arrow. Conditional edge: a router function returns a string, a dict maps it to the next node.
- START / END, compile() (validates the graph), invoke() (runs one input, returns final state).
- Nodes and routers are plain functions, so they are testable without LangGraph; a test proves graph == sequential run.

## Key design points
- Prompt-injection defence: no tools, document fenced in <document> tags with closing tags defused, prompt says document is DATA,
  and money decisions are made by code. Result: 7/7 injected invoices handled, 0 leaked.
- Failure of one document must not kill a batch: API errors become ExtractionFailed -> status "failed".
- Evaluate the evaluator: an "oracle" pretend model must score 100%, and deliberately damaged models must score lower in the damaged places.

## Results (90 synthetic documents, gpt-4o-mini, temperature 0)
| | v1 baseline | v2 (prompt fix) |
|---|---|---|
| Classification | 100% | 100% |
| Field accuracy | 100% | 100% |
| Charge F1 (strict) | 78.5% | 99.8% |
| Exact-match documents | 78.9% | 98.9% |
| Real arithmetic errors flagged | 5/5 | 5/5 |
| False total alarms | 0/40 | 1/40 |
| Injection leaked | 0/7 | 0/7 |
| Cost / run | ~$0.03 | ~$0.03 |

v1 problem: on 3-column PDF tables (Charge | Basis | Amount) the model appended the basis to the label
("O/F per container"); every amount was right. Found by reading the mismatch list, fixed by one prompt rule
("a label is only the name; leave out basis/unit columns"). The strict metric was NOT loosened; a separate
"amount only" diagnostic was added to tell mislabelled from wrong-number.

v2 remaining error: case-044 invoice, "USD 4 195.00" returned as "195.00" (space thousands separator).
The validator caught it (charges no longer sum to the printed total) -> sent to review. Day 39 repair loop target.

## Honest caveats
- Data is synthetic and from our own generator; the prompt was tuned on the same 90 documents it is scored on.
  Treat 99.8% as "works on this dataset", not as a real-world accuracy claim.
- One error in 180 documents-calls is too few to estimate a real error rate; more cases and a held-out set would be needed.

## Next (Day 39)
repair loop (max 2 retries, with a hint built from the failed check), normalize to canonical ports/equipment/charge codes
(+ eval of those), persist to Postgres under RLS, reconciliation quote-vs-invoice with discrepancy types,
human-review interrupt(), CI eval gate.
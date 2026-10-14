# Day 39 - Loops in a graph: bounded retry with feedback

Status: Part 1 (concept + toy example). The repo's real repair loop is built next, and these notes get a "Part 2" at the end.

## The problem this solves
On Day 38, case-044 had `USD 4 195.00` and the model returned `195.00` (it dropped the "4").
Our validator noticed the charges did not add up to the printed total and sent the invoice to human review.
That is safe but wasteful: the model would probably read it correctly if asked to look again.
A person does the same: re-read the line, and only escalate if it still does not add up.

## Concepts

**Cycle (loop).** An edge that goes back to an earlier node. Until now our graph only moved forward.
LangGraph allows cycles; "try, check, try again" is a cycle.

**Bounded loop.** Every retry costs an API call and time, and a bug or a stubborn model could loop forever.
So the state carries an `attempts` counter and the router stops the loop when the limit is passed.
The limit is OUR rule. LangGraph also has a `recursion_limit` (default 25 steps) that raises an error,
but that is a last-resort alarm, not the design.

**Feedback.** The same input usually gives the same answer. A failed check produces a `hint`
that goes into the next attempt: "Your charges add up to X but the printed total is Y. Re-read each amount."

**Router as decision-maker.** After `check`, a router function returns one word:
`done`, `retry` or `review`. A mapping dict turns each word into the next node.
Same conditional-edge pattern as Day 38; the only new thing is that one arrow points backwards (`retry` -> `read`).

**Counting reads.** `attempts` counts reads so far. With `MAX_RETRIES = 2`: first read + 2 re-reads = 3 reads total.
The router test is `attempts > MAX_RETRIES`.

## Two design rules (the important part)
1. **Code decides pass/fail, the model only re-reads.** The model cannot pass the check by claiming it is right;
   the check is arithmetic done by our code.
2. **The hint states facts, never the answer.** It may say "your charges sum to X, the printed total is Y".
   It must not say "the first charge should be 4,195.00". Otherwise the model invents numbers to make the sum fit,
   and a retry loop that adjusts numbers until they fit would hide REAL overcharges and arithmetic errors.
   Invoice C in the toy is the proof: its printed total is really wrong, so the loop must fail and go to a human.

## The experiments and what they showed
| Run | Setting | A: clean | B: model misreads | C: invoice really wrong |
|---|---|---|---|---|
| 1 | `MAX_RETRIES = 2` (default) | ok, 1 read | ok, 2 reads (loop fixed it) | needs_review, 3 reads |
| 2 | `MAX_RETRIES = 0` | ok, 1 read | needs_review, 1 read, charges `[195, ...]` | needs_review, 1 read |
| 3 | `MAX_RETRIES = 5` | ok, 1 read | ok, 2 reads | needs_review, 6 reads |

- Run 2: with no retries, B is never given a second chance, so a fixable misread goes to a human. Retries save human time.
- Run 3: more retries did NOT help C (3 extra reads, same wrong total); it only cost 3 more calls. Retrying cannot fix a document that is really wrong, so the limit should be small. B was fixed on the first retry in every run.
- Experiment 4 (not run yet): with `hint` set to `""`, the toy reader is never told a check failed, so B keeps misreading and ends in `needs_review` after 3 reads. Feedback is what makes a retry worth doing.

## Self-check (answer key)
1. A loop = an edge that points back to an earlier node (here `retry` -> `read`), so the graph is no longer strictly forward.
2. Without a counter a bug or stubborn model loops forever, costing money and time; the counter plus router guarantees an exit.
3. If the hint contains the answer, the model will invent numbers that fit, so real errors (invoice C) would be "repaired" away and never reach a human.

## The toy example (standalone, not part of the repo)
Run with the venv active: `python loop_demo.py`. Expected output: A ok/1 read, B ok/2 reads, C needs_review/3 reads, each followed by "graph: same result".

```python
"""Day 39 toy: a bounded retry loop. NOT part of the repo; run it from anywhere.

Three invoices. The 'reader' stands in for the LLM, the 'check' stands in for our validator.
"""
from typing import TypedDict

MAX_RETRIES = 2  # first read + at most 2 re-reads = 3 reads in total

DOCS = {
    "A: clean":          {"charges": [4195, 355, 140], "total": 4690, "misread_first": False},
    "B: model misreads": {"charges": [4195, 355, 140], "total": 4690, "misread_first": True},
    "C: invoice is wrong": {"charges": [4195, 355, 140], "total": 5000, "misread_first": False},
}


def fake_reader(doc: dict, hint: str) -> list[int]:
    """Pretend LLM. It drops a digit on the first read of doc B, but reads correctly
    when it has been told a check failed (that is what a real model often does)."""
    amounts = list(doc["charges"])
    if doc["misread_first"] and not hint:
        amounts[0] = 195  # '4 195.00' read as '195.00'
    return amounts


# ---- the pieces, written as plain functions (same shape as LangGraph nodes) ----------

class State(TypedDict, total=False):
    doc: dict
    charges: list[int]
    attempts: int
    hint: str
    status: str


def read(state: State) -> dict:
    charges = fake_reader(state["doc"], state.get("hint", ""))
    return {"charges": charges, "attempts": state.get("attempts", 0) + 1}


def check(state: State) -> dict:
    got, printed = sum(state["charges"]), state["doc"]["total"]
    if got == printed:
        return {"status": "ok", "hint": ""}
    # The hint states facts the model can see for itself. It never says what the answer should be.
    return {"status": "check_failed",
            "hint": f"Your charges add up to {got} but the printed total is {printed}. Re-read each amount."}


def give_up(state: State) -> dict:
    return {"status": "needs_review"}


def route(state: State) -> str:
    if state["status"] == "ok":
        return "done"
    if state["attempts"] > MAX_RETRIES:  # attempts counts reads so far
        return "review"
    return "retry"


# ---- version 1: a plain Python loop --------------------------------------------------

def run_plain(doc: dict) -> State:
    state: State = {"doc": doc}
    while True:
        state.update(read(state))
        state.update(check(state))
        decision = route(state)
        if decision == "retry":
            continue  # <- this "go back" is the whole idea of a loop in a graph
        if decision == "review":
            state.update(give_up(state))
        return state


# ---- version 2: the same pieces as a LangGraph graph with a cycle -----------------------

def build_graph():
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(State)
    g.add_node("read", read)
    g.add_node("check", check)
    g.add_node("give_up", give_up)
    g.add_edge(START, "read")
    g.add_edge("read", "check")
    g.add_conditional_edges("check", route, {"done": END, "review": "give_up", "retry": "read"})
    g.add_edge("give_up", END)
    return g.compile()


if __name__ == "__main__":
    try:
        graph = build_graph()
    except ImportError:
        graph = None
    for name, doc in DOCS.items():
        s = run_plain(doc)
        line = f"{name:<22} plain loop -> status={s['status']:<12} reads={s['attempts']} charges={s['charges']}"
        if graph:
            g = graph.invoke({"doc": doc})
            assert (g["status"], g["attempts"], g["charges"]) == (s["status"], s["attempts"], s["charges"])
            line += "   | graph: same result"
        print(line)
```

## How the toy maps to the real pipeline (preview, nothing built yet)
| Toy | Real pipeline |
|---|---|
| `fake_reader` | the extract node calling the LLM, with the hint added to the user message |
| `check` | `validate_node` (TOTAL_MISMATCH is the failing check) |
| `route` + `MAX_RETRIES` | a new router after validate; only TOTAL_MISMATCH triggers a retry |
| `give_up` | status `needs_review` (what happens today on first failure) |
| `attempts` | a new key in `DocState` |

## Part 2 - The real repair loop in the repo

### What changed and why
| File | Change | Purpose |
|---|---|---|
| `pipeline/money.py` | new `format_minor(minor)` -> `"5,040.00"` | Inverse of `parse_money`; one home for money formatting (reconciliation will need it too). Assumes 2 decimals. |
| `pipeline/prompts.py` | `build_user_message(document_text, hint="")` appends `Your previous reading failed an automatic check: {hint}` after the closing `</document>` tag | Lets a retry carry feedback. Outside the fence on purpose: our code wrote it, the document did not. |
| `pipeline/nodes.py` | `MAX_RETRIES = 2`; `DocState` gains `attempts` and `hint` | The loop's limit and the two values that travel through it. |
| `pipeline/nodes.py` | extract node passes `state.get("hint", "")` and returns `attempts + 1` | Uses the hint, counts the read. |
| `pipeline/nodes.py` | new `build_hint(typed, issues)`; `validate_node` also returns `hint` | Empty unless TOTAL_MISMATCH. States the two sums, never the right amount. |
| `pipeline/nodes.py` | new `route_after_validate`: retry while there is a hint and `attempts <= MAX_RETRIES`, returns `extract_quote` / `extract_invoice` / `end` | The router that makes the back-arrow. |
| `pipeline/nodes.py` | `run_sequentially` tail becomes a `while True` loop | Keeps the plain-Python twin identical to the graph. |
| `pipeline/graph.py` | `add_edge("validate", END)` replaced by `add_conditional_edges("validate", route_after_validate, {...})` | The cycle in LangGraph. |
| `evaluation/metrics.py`, `runner.py` | `attempts` per document; `repair_loop` summary and a report line | Measure the loop: retried / fixed / extra extractions. |
| `synth/oracle.py` | `OracleLLM(..., fix_when_hinted=True)` | Pretend model that misreads once and reads right when told a check failed. |
| tests | read counts (3 for a really wrong invoice, 1 for clean), hint contains facts but never the answer, router stops at the limit, misread-then-fixed over all 90 docs, no-hint model stays wrong, `format_minor` round trip | The loop's rules are tested without spending money. |

### The hint (what the model sees on a retry)
`Your previous reading failed an automatic check: the charge amounts you returned add up to 3,845.00, but the printed total is 5,040.00. Re-read every amount in the charge table, digit by digit, and extract again.`
Facts the model can verify itself; the correct amount is never given.

### Results on the 90 synthetic documents (gpt-4o-mini)
| | v2 (before loop) | v3 (with loop) |
|---|---|---|
| Charge F1 | 99.8% | 100% |
| Exact-match documents | 98.9% | 100% |
| False total alarms | 1/40 | 0/40 |
| Real arithmetic errors flagged | 5/5 | 5/5 |
| Repair loop | n/a | 6 retried, 1 fixed, 11 extra extractions |
| LLM calls / cost | 180 / $0.030 | 191 / $0.033 |

- Fixed: case-044 (`USD 4 195.00` read as `195.00`), after one retry.
- The 5 invoices with a really wrong total were each read 3 times and still went to review. Exact-match stayed 100%, which also shows the model did not change their amounts to fit the wrong total.
- Oracle run (free): `retried 5, fixed 0, 10 extra extractions` - the 5 really-wrong invoices, as predicted.

### Lessons
- A repair loop must never be able to "pass" a document that is really wrong; keep the pass/fail check in code and keep answers out of the hint.
- Bound every loop with your own counter (`attempts`) and measure it (retried / fixed / extra cost).
- Add a metric BEFORE trusting a new behaviour: `wrong totals flagged 5/5` was the guard that proved the loop was not hiding errors.
- Caveat: one repaired document is a tiny sample; the logic is proven by tests, but the real-world fix rate is unmeasured.

### Next (Day 40)
Normalization: map different names for the same thing ("O/F", "Ocean Freight", "Basic Ocean Freight") to one canonical charge code, plus ports and container types, and evaluate the mapping.
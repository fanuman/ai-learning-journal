# Day 31 - Multi-agent orchestration: LangGraph, a Researcher + Writer pipeline

**Date completed:** _(fill in)_

## What I learned

**An agent with tools isn't the same thing as a multi-agent system.** `RAGPipeline`'s ReAct loop
(Day 16) is one agent, one prompt, deciding whether to call a tool and repeating until done.
Multi-agent orchestration is a different idea: multiple distinct *roles*, each with its own
narrower prompt and responsibility, handing off structured state between them - specialists
collaborating, not one generalist doing everything.

**LangGraph's core primitives**, replacing the hand-rolled `for` loop from Day 16:
- **State** - a shared object (`TypedDict` here) flowing through every node
- **Nodes** - plain functions, each reading state and returning an updated state
- **Edges** - how control moves between nodes (`add_edge` for a fixed handoff today; conditional
  edges exist for branching, not needed for a straight two-step pipeline)
- **`StateGraph(...).compile()`** - turns nodes + edges into something runnable via `.invoke()`

**Two genuinely different multi-agent topologies exist, not just one "multi-agent pattern":**
a **pipeline** (fixed sequence, every request flows through every stage - today's Researcher then
Writer) versus a **router** (one orchestrator classifies a request and sends it to exactly one of
several specialists, each running its own independent loop). Confirmed this distinction directly
today after finding an old orchestrator/specialist exercise (billing/technical/general triage) from
earlier in this same project's history that never actually became this repo's real Day 21 - Day 21
here was genuinely Docker Compose, confirmed by real terminal output and the README. Decided to add
the router pattern as a second exercise on Saturday, on top of today's pipeline, rather than
treating the two as competing options - they're genuinely different tools for different shapes of
problem.

## Today's exercise

New `src/agents/` module (own module, not folded into `rag/` - the two agents here don't touch the
live chat pipeline at all):
- `state.py` - `ContentState` TypedDict: `topic`, `research_notes`, `sources`, `draft`
- `researcher.py` - `researcher_node()`: retrieves from the same Chroma collection the chatbot
  already uses, then extracts *plain factual bullet points only* - deliberately no marketing
  language, no prose. Keeping this node's job narrow (facts, not copy) is what makes the split
  real rather than one agent's logic arbitrarily divided into two functions.
- `writer.py` - `writer_node()`: takes only the Researcher's notes and drafts a customer-facing
  buying-guide paragraph. Never touches the vectorstore directly - a wrong fact is the
  Researcher's bug to fix, not something the Writer should guess around.
- `graph.py` - wires `researcher -> writer -> END` with `StateGraph`, exposes `run_content_pipeline(topic)`

Added `langgraph` to `requirements.txt`.

## Test results - the honesty test was the real point

Ran two topics through the compiled graph, inside Docker Compose
(`docker compose exec app python -m src.agents.graph "<topic>"`, needed a `--build` first since
`langgraph` is a new dependency):

**"winter camping tents"** - deliberately the same topic Day 27's `context_recall` flagged as a
real, unresolved content gap (no tent in the catalog is actually winter-rated). The Researcher's
notes surfaced the limitation as a plain fact ("not fully supported... a 4-season tent is
recommended for winter mountaineering") rather than omitting it, and the Writer's draft led with
that honest caveat rather than writing around it into false marketing copy. This was the test that
actually mattered - confirming a known real limitation survives a two-LLM-call handoff intact,
rather than getting lost or spun somewhere in the pipeline.

**"rain jackets"** - clean positive case. Every claim in the final draft (waterproof rating,
breathability, care instructions, the cold-weather limit) traces back to a real bullet in the
Researcher's notes - confirmed the Writer's "use only these facts" instruction actually held, no
fabricated specs.

Both runs stayed on `gpt-4o-mini` throughout - cheap to iterate on repeatedly.

## A real project-history mix-up, resolved honestly

Found an old orchestrator/specialist exercise (billing/technical/general classify-and-route,
`multiagent-platform` repo, labeled "Day 21") that didn't match this project's actual, confirmed
history - real Day 21 here was Docker Compose. Traced it as far as verifiable: checked this
session's own transcript for earlier mentions and found none, meaning it's genuinely unclear
whether that exercise happened earlier in this same project's history and simply wasn't preserved
through a context-compaction summary, or came from confusion with a different session entirely.
Resolved pragmatically rather than left unresolved: whatever its origin, it didn't become this
repo's real Day 21, and its actual technique (structured-output routing to independent specialist
loops) is worth doing on its own merits - added to Saturday's project instead of relitigating where
it came from.

## Router pattern - documented, not built (a deliberate Week 7 Saturday decision)

Originally planned to build the orchestrator/specialist router as a second hands-on exercise this
Saturday, on top of the pipeline above. Revisited that plan once Week 7's project actually started:
Week 8's capstone (`week-08-capstone-plan.md`) already commits to LangGraph as a core, first-class
tool from day one, which is exactly where conditional-edge routing would get real, sustained
practice. Building a second, lighter LangGraph exercise this Saturday just to touch the same
primitive once would be duplicated effort - better to bank the concept precisely in writing now and
get the hands-on repetition when it's actually load-bearing for the capstone's design. The
EKS deployment work moved into the time this freed up.

**The concept, for the record:**

A **router** differs from today's **pipeline** in exactly one structural way: today's graph is
`researcher -> writer -> END`, a fixed sequence where every request visits every node in the same
order. A router is a *branch*, not a sequence - one orchestrator node classifies an incoming
request (via structured output, e.g. a Pydantic model naming `billing` / `technical` / `general`),
and that classification decides which *one* of several independent specialist nodes the request
goes to next. The other specialists never run at all for that request.

In LangGraph terms, this is what **conditional edges** are for, as opposed to today's `add_edge`
fixed handoff: a node's return value (the classification) picks which edge the graph actually
follows, via `add_conditional_edges` mapping classification values to destination nodes. Each
specialist can be as independent as the Researcher/Writer nodes were today - its own prompt, its
own tools, its own narrow responsibility - the only new idea is that which specialist runs is
decided at runtime instead of fixed at graph-definition time.

This is also the resolution to the old `multiagent-platform` billing/technical/general exercise
found in project history (see above): its actual technique - structured-output classification routed
to independent specialist loops - is a real router pattern and conceptually correct, it's just not
being rebuilt as code in *this* project. The concept transfers; the implementation is deliberately
deferred to Week 8.

### The pattern in code (illustrative only - not part of this project's pipeline)

Stripped down to its simplest possible form, a router is just a classification call followed by an
`if`/`elif`/`else`. Using the billing/technical/general categories from the old exercise:

```python
from enum import Enum
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI()


class RequestCategory(str, Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    GENERAL = "general"


class Classification(BaseModel):
    category: RequestCategory
    reasoning: str


def classify_request(user_message: str) -> Classification:
    """The orchestrator's only job: decide which specialist should handle this.
    Nothing else - no answering, no tool calls, just routing."""
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify the customer's message into exactly one category: "
                    "billing, technical, or general. Give a one-sentence reason."
                ),
            },
            {"role": "user", "content": user_message},
        ],
        response_format=Classification,
    )
    return response.choices[0].message.parsed


def handle_billing(user_message: str) -> str:
    # Its own narrow prompt + its own tools, e.g. look_up_order(), issue_refund()
    # A full ReAct loop in its own right - not a shared one with technical/general.
    ...


def handle_technical(user_message: str) -> str:
    # Its own narrow prompt + its own tools, e.g. search_docs(), check_product_spec()
    ...


def handle_general(user_message: str) -> str:
    # No specialist needed - falls back to the existing RAG pipeline from Day 8/16.
    ...


def route_request(user_message: str) -> str:
    """The router itself: classify, then branch to exactly one specialist."""
    classification = classify_request(user_message)

    if classification.category == RequestCategory.BILLING:
        return handle_billing(user_message)
    elif classification.category == RequestCategory.TECHNICAL:
        return handle_technical(user_message)
    else:  # RequestCategory.GENERAL
        return handle_general(user_message)
```

**Why this is the same thing as LangGraph's `add_conditional_edges`, not a simpler substitute for
it**: `add_conditional_edges` takes a function that returns a string, and a dict mapping each
possible string to a destination node - which is exactly what the `if`/`elif`/`else` above does by
hand. LangGraph doesn't add a new idea here; it formalizes an ordinary dispatch pattern as a graph
edge so that state threading, composing it with other nodes (a pipeline *and* a router in the same
graph), and visualizing the whole thing come for free. The router pattern itself - classify once,
branch to exactly one independent handler - is a general software pattern with or without any
framework at all. That's the part worth remembering cold; the LangGraph syntax for it is the part
Week 8 will actually drill.

Each `handle_*` stub above would, in a real build, be a complete ReAct loop with its own tools - the
same shape as `RAGPipeline`'s agent from Day 16 - just scoped to one category's concerns instead of
being one generalist prompt trying to handle everything.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether to eventually combine both topologies - e.g., an orchestrator that could route a request
  to *either* the single-agent chat pipeline *or* the researcher/writer content pipeline, depending
  on what kind of request it is - this is now explicitly a Week 8 question, not a Week 7 one, since
  the router pattern itself is deferred there

## Practice task
Built a genuine two-agent LangGraph pipeline (Researcher + Writer) as a new, standalone
`src/agents/` module, generating customer-facing buying-guide content from the same product
catalog the live chatbot already uses. Confirmed the split is real, not cosmetic: a previously-
documented content gap (no winter-rated tent) survived the handoff between both agents honestly,
and the Writer's output stayed fully grounded in the Researcher's facts with no fabrication.
Initially planned a second multi-agent topology (orchestrator + independent specialists) as a
hands-on follow-on exercise this Saturday, then deliberately deferred the actual build to Week 8
(where LangGraph conditional edges get real, sustained practice as a core tool) - documented the
concept precisely instead, including a plain `if`/`elif`/`else` version of the same router logic to
make concrete exactly what `add_conditional_edges` formalizes into a graph edge.
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

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether to eventually combine both topologies - e.g., an orchestrator that could route a request
  to *either* the single-agent chat pipeline *or* the researcher/writer content pipeline, depending
  on what kind of request it is - once the router pattern exists on Saturday

## Practice task
Built a genuine two-agent LangGraph pipeline (Researcher + Writer) as a new, standalone
`src/agents/` module, generating customer-facing buying-guide content from the same product
catalog the live chatbot already uses. Confirmed the split is real, not cosmetic: a previously-
documented content gap (no winter-rated tent) survived the handoff between both agents honestly,
and the Writer's output stayed fully grounded in the Researcher's facts with no fabrication.
Decided to add a second multi-agent topology (orchestrator + independent specialists) as a
follow-on exercise this Saturday, alongside the EKS deployment work already planned for Week 7's
project.
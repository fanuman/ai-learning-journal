"""Day 39 toy: a bounded retry loop. NOT part of the repo; run it from anywhere.

Three invoices. The 'reader' stands in for the LLM, the 'check' stands in for our validator.
"""
from typing import TypedDict

MAX_RETRIES = 5  # first read + at most 2 re-reads = 3 reads in total

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
"""A tiny mock multi-agent 'support bot' — the system AgentDiff monitors.

This is the STORY, not the seed. It shows what a monitored agent looks like:
an orchestrator that fans out to three sub-agents, each of which makes an LLM
call. AgentDiff watches which sub-agents actually fire on real inputs.

The regression it demonstrates is the classic silent one: a latency "fix" adds
an early return to the Fact Checker, so it stops calling the LLM entirely. The
answer still comes back and every output-level eval still passes — but the
system quietly stopped fact-checking. That is exactly what AgentDiff catches.

Run `demo/seed_run.py` to turn this story into a real run on your AgentDiff
stack and see the Fact Checker node go ember in the before/after graph.
"""
from __future__ import annotations

# Toggle this to represent the "bad commit". False == the latency fix that
# silently disabled fact-checking (the candidate branch).
FACT_CHECKER_ENABLED = True


def retriever(query: str) -> str:
    # Sub-agent: makes an LLM call to pull relevant context.
    return llm_call("retriever", f"Find docs for: {query}")


def fact_checker(draft: str) -> str:
    # Sub-agent: verifies claims with an LLM call.
    if not FACT_CHECKER_ENABLED:
        return draft  # <-- the "bad commit": skip the LLM call for latency
    return llm_call("fact_checker", f"Verify the claims in: {draft}")


def summarizer(context: str) -> str:
    # Sub-agent: makes an LLM call to compose the final answer.
    return llm_call("summarizer", f"Summarize for the user: {context}")


def orchestrator(query: str) -> str:
    context = retriever(query)
    draft = summarizer(context)
    answer = fact_checker(draft)
    return answer


def llm_call(agent: str, prompt: str) -> str:
    # Stand-in for a real provider call. In production this is where AgentDiff's
    # capture shim sees the request and records which sub-agent fired.
    return f"[{agent}] response"


if __name__ == "__main__":
    print(orchestrator("What is the capital of France?"))

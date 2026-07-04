"""Support-bot orchestrator: fans out to retriever → fact_checker → summarizer.

The orchestrator calls each sub-agent in order. The fact_checker makes a real
Anthropic SDK call (captured by AgentDiff's shim); the retriever and summarizer
are lightweight helpers that don't hit the LLM.
"""
from __future__ import annotations

from agents.retriever import retriever
from agents.fact_checker import fact_checker
from agents.summarizer import summarizer


def orchestrator(input: dict) -> dict:
    """Run the three-stage support pipeline."""
    query = input.get("query", "")

    # Stage 1 — retrieval (no LLM call, just text lookup)
    context = retriever(query)

    # Stage 2 — fact checking (real LLM call via anthropic SDK shim)
    verified = fact_checker(context, query)

    # Stage 3 — summarization (no LLM call, simple text join)
    answer = summarizer(verified, query)

    return {"answer": answer, "stages": ["retriever", "fact_checker", "summarizer"]}

"""Retriever sub-agent: returns canned context (no LLM call)."""
from __future__ import annotations


def retriever(query: str) -> str:
    """Look up context for the query (mocked — no LLM call)."""
    return f"Relevant context for '{query}': AgentDiff monitors behavioral changes in AI pipelines."

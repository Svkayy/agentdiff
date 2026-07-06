"""Summarizer sub-agent: composes the final answer (no LLM call)."""
from __future__ import annotations


def summarizer(verified_context: str, query: str) -> str:
    """Compose a final answer from verified context (mocked — no LLM call)."""
    return f"Answer to '{query}': {verified_context}"

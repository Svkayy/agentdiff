"""Orchestrator — the top-level research agent.

Unconditionally runs the retriever, fact-checker, and summarizer sub-agents,
then returns the final answer. Routing is deterministic (no model decides which
sub-agents run), so a behavioral diff between two versions is reproducible.
"""
from agents.fact_checker import fact_checker_agent
from agents.llm import chat
from agents.retriever import retriever_agent
from agents.summarizer import summarizer_agent


def run_research(query: str) -> str:
    # A short planning call so the orchestrator itself shows up as an agent.
    chat(f"List the steps to research this question in one line: {query}", max_tokens=80)

    findings = retriever_agent(query)
    verification = fact_checker_agent(query, findings)
    return summarizer_agent(query, findings, verification)

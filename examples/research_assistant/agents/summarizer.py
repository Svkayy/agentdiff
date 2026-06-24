"""Summarizer sub-agent — writes the final answer from findings + verification."""
from agents.llm import chat


def summarizer_agent(query: str, findings: str, verification: str) -> str:
    return chat(
        f"Write a concise final answer to '{query}'.\n"
        f"Findings: {findings}\nVerification: {verification}"
    )

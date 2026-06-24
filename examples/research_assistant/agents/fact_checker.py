"""Fact-checker sub-agent — verifies the retriever's findings against evidence.

This is the agent the demo regression disables. The candidate version inserts an
early `return ""` in place of the marker line below, which silently skips the
evidence lookup and the verification LLM call — the final answer still reads
fine, so traditional output-eval passes while AgentDiff catches the regression
and attributes it to this file.
"""
from agents.llm import chat
from tools import calculator, web_search


def fact_checker_agent(query: str, findings: str) -> str:
    # AGENTDIFF_DEMO_MARKER (the candidate replaces this line to disable the step)
    evidence = web_search(f"verify the claims in: {query}")
    confidence = calculator(f"{len(findings)} / 100")
    return chat(
        f"Fact-check these findings against the evidence (confidence {confidence}).\n"
        f"Findings: {findings}\nEvidence: {evidence}"
    )

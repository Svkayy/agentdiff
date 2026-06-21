"""Bounded LLM explanation layer.

Produces a 1-3 sentence natural-language explanation for a single attributed
behavioral delta. The prompt is strictly templated and the model is NEVER asked
to choose the attribution — that's already decided by the deterministic rules.
"""
from agentdiff.attribution.rules import Attribution
from agentdiff.llm_client import LLMClient

_SYSTEM = (
    "You explain, in 1-3 sentences, why an AI agent's observed behavior changed, "
    "given a deterministically-detected code or prompt change. Be specific and "
    "factual. Do not speculate beyond the provided evidence, and do not second-guess "
    "the attribution — it is already established."
)

_MAX_HUNK = 1500


def explain(
    client: LLMClient,
    agent_name: str,
    delta_summary: str,
    verdict: str,
    primary: Attribution,
) -> str | None:
    """Return a short explanation, or None if the LLM call yields nothing."""
    hunk = (primary.hunk or "")[:_MAX_HUNK]
    prompt = (
        f"Agent: {agent_name}\n"
        f"Observed behavioral change: {delta_summary} (verdict: {verdict})\n"
        f"Attributed cause (rule: {primary.rule}): {primary.target_path}\n"
        f"Reason: {primary.reason}\n"
        f"Relevant diff:\n{hunk}\n\n"
        "In 1-3 sentences, explain why this change likely produced the behavioral change."
    )
    text = client.complete(_SYSTEM, prompt, max_tokens=200).strip()
    return text or None

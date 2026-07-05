"""Bounded LLM explanation layer.

Produces a 1-3 sentence natural-language explanation for a single attributed
behavioral delta. The prompt is strictly templated and the model is NEVER asked
to choose the attribution — that's already decided by the deterministic rules.
"""
import os

from agentdiff.attribution.rules import Attribution
from agentdiff.llm_client import LLMClient

_SYSTEM = (
    "You explain, in 1-3 sentences, why an AI agent's observed behavior changed, "
    "given a deterministically-detected code or prompt change. Be specific and "
    "factual. Do not speculate beyond the provided evidence, and do not second-guess "
    "the attribution — it is already established."
)

_MAX_HUNK = 1500


def explain_default(
    agent_name: str,
    delta_summary: str,
    verdict: str,
    primary: Attribution,
    *,
    client: LLMClient | None = None,
) -> str:
    """Return an LLM explanation when configured, otherwise a deterministic one."""
    resolved = client or _auto_client()
    if resolved is not None:
        llm_text = explain(resolved, agent_name, delta_summary, verdict, primary)
        if llm_text:
            return llm_text
    return fallback_explanation(agent_name, delta_summary, verdict, primary)


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
    result = client.generate(_SYSTEM, prompt, max_tokens=200)
    if result.error is not None or not result.text:
        return None
    text = result.text.strip()
    return text or None


def fallback_explanation(
    agent_name: str,
    delta_summary: str,
    verdict: str,
    primary: Attribution,
) -> str:
    """Evidence-only explainer used when no LLM credential is configured."""
    target = f"`{primary.target_path}`" if primary.target_path else "the observed run data"
    rule = primary.rule.replace("_", " ")
    return (
        f"AgentDiff attributed {agent_name}'s {delta_summary} ({verdict}) to {target} "
        f"via the {rule} rule. {primary.reason}"
    )


def _auto_client() -> LLMClient | None:
    provider = os.environ.get("AGENTDIFF_LLM_PROVIDER", "anthropic")
    key_env = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    if not os.environ.get(key_env):
        return None
    try:
        return LLMClient(provider=provider)
    except Exception:  # noqa: BLE001 - explanation falls back deterministically
        return None

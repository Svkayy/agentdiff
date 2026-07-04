"""Server-side LLM explanation layer.

After process_run_sync returns finding_dicts, this module optionally enriches
the first (up to 3) non-pass findings with a natural-language LLM explanation.

Rules:
- If no Anthropic API key is configured, leave the existing rule-based
  explanation untouched (never overwrite with worse output).
- Per-finding try/except: one failure never kills the rest.
- Never raises out of explain_findings.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("agentdiff.explain")

_MAX_FINDINGS = 3


def _make_client(api_key: str, model: str | None = None):
    """Build an LLMClient from a direct API key (not env-based)."""
    from agentdiff.llm_client import LLMClient
    return LLMClient(provider="anthropic", api_key=api_key, model=model or None)


def _explain_one(finding_dict: dict, client, *, is_drift: bool) -> None:
    """Write an LLM explanation into finding_dict['explanation'] in-place."""
    from agentdiff.attribution.rules import Attribution
    from agentdiff.attribution.explainer import explain

    cause_path = finding_dict.get("cause_path")
    cause_rule = finding_dict.get("cause_rule")
    cause_hunk = finding_dict.get("cause_hunk")

    if is_drift:
        # Drift: no git hunk, explain the suspected upstream-drift narrative.
        agent_name = finding_dict.get("title", "agent").replace(" invocation changed", "")
        delta_summary = finding_dict.get("impact_summary", "behavioral delta observed")
        verdict = finding_dict.get("verdict", "warn")
        primary = Attribution(
            rule=cause_rule or "upstream_drift",
            target_path=cause_path or "",
            hunk=cause_hunk,
            weight=0.5,
            reason=(
                "No attributable code change in this window — if no deploy occurred, "
                "suspect upstream model/provider drift."
            ),
        )
        explanation = explain(client, agent_name, delta_summary, verdict, primary)
    elif cause_path:
        agent_name = finding_dict.get("title", "agent").replace(" invocation changed", "")
        delta_summary = finding_dict.get("impact_summary", "behavioral delta observed")
        verdict = finding_dict.get("verdict", "fail")
        primary = Attribution(
            rule=cause_rule or "unknown",
            target_path=cause_path,
            hunk=cause_hunk,
            weight=0.8,
            reason=finding_dict.get("explanation") or f"change in {cause_path}",
        )
        explanation = explain(client, agent_name, delta_summary, verdict, primary)
    else:
        return  # no cause to explain

    if explanation:
        finding_dict["explanation"] = explanation


async def explain_findings(
    finding_dicts: list[dict],
    *,
    run,
) -> None:
    """Enrich up to _MAX_FINDINGS non-pass findings with an LLM explanation.

    Mutates finding_dicts in-place. Never raises.
    """
    from server.config import get_settings

    settings = get_settings()
    api_key = settings.anthropic_api_key
    if not api_key:
        return  # no key — leave rule-based explanations intact

    try:
        model = settings.llm_model or None
        client = _make_client(api_key, model)
    except Exception as exc:
        log.debug("explain_findings: could not build LLM client: %s", exc)
        return

    is_drift = getattr(run, "kind", None) == "drift"

    processed = 0
    for fd in finding_dicts:
        if fd.get("verdict") == "pass":
            continue
        if processed >= _MAX_FINDINGS:
            break
        # Only explain findings that have a cause or drift context
        if not fd.get("cause_path") and not is_drift:
            continue
        try:
            await asyncio.to_thread(_explain_one, fd, client, is_drift=is_drift)
        except Exception as exc:  # noqa: BLE001
            log.debug("explain_findings: finding explanation failed (swallowed): %s", exc)
        processed += 1

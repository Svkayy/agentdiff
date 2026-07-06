"""Render incident findings for PR checks, Slack, and postmortem drafts."""
from __future__ import annotations

from typing import Any

from agentdiff.incident.findings import IncidentContext, IncidentSummary

_LABEL = {"pass": "STABLE", "warn": "NOTICE", "fail": "CHANGE"}
# DESIGN.md semantic verdict colors: pass green, warn amber, fail ember.
_COLOR = {"pass": "#3FB27F", "warn": "#E8A33D", "fail": "#FF4D2E"}
_EMOJI = {"pass": "\U0001f7e2", "warn": "\U0001f7e1", "fail": "\U0001f534"}

_MAX_SLACK_FINDINGS = 3


def render_pr_check(summary: IncidentSummary, *, context: IncidentContext | None = None) -> str:
    lines = [f"# AgentDiff CI Gate: {_LABEL[summary.verdict]}", ""]
    if context is not None and (ctx_line := _context_line(context)):
        lines.extend([f"_{ctx_line}_", ""])
    if summary.warnings:
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in summary.warnings)
        lines.append("")
    if not summary.findings:
        lines.append("No behavioral changes detected.")
        return "\n".join(lines) + "\n"
    lines.append("## Findings")
    for finding in summary.findings:
        cause = f" Cause: `{finding.cause_path}`.{_low_confidence_suffix(finding)}" if finding.cause_path else ""
        lines.append(
            f"- **{_LABEL[finding.verdict]}** `{finding.test_case_id}`: "
            f"{finding.impact_summary}{cause}"
        )
    return "\n".join(lines) + "\n"


def _low_confidence_suffix(finding) -> str:
    return " (low-confidence heuristic)" if finding.cause_confidence == "low" else ""


def render_postmortem(summary: IncidentSummary, *, context: IncidentContext | None = None) -> str:
    lines = ["# AgentDiff Incident Postmortem Draft", ""]
    if context is not None:
        if context.repository:
            lines.append(f"- **Repository:** {context.repository}")
        if context.pr_number:
            lines.append(f"- **Pull request:** #{context.pr_number}")
        if context.baseline_ref or context.candidate_ref:
            lines.append(
                f"- **Range:** `{context.baseline_ref or '?'}` → `{context.candidate_ref or 'working'}`"
            )
        if context.tier:
            lines.append(f"- **Tier:** {context.tier}")
    lines.extend(
        [
            f"- **Verdict:** {_LABEL[summary.verdict]}",
            f"- **Findings:** {len(summary.findings)}",
            "",
            "## Impact",
            "",
        ]
    )
    if not summary.findings:
        lines.append("No behavioral changes detected.")
    for finding in summary.findings:
        lines.append(f"- {finding.impact_summary}")
    if summary.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in summary.warnings)
    lines.extend(["", "## Likely Cause", ""])
    caused = [f for f in summary.findings if f.cause_path]
    if not caused:
        lines.append("No code or prompt hunk was attributed.")
    for finding in caused:
        lines.append(f"- `{finding.cause_path}` via `{finding.cause_rule}`{_low_confidence_suffix(finding)}")
    lines.extend(["", "## Follow-Up", "", "- Confirm owner and remediation status."])
    return "\n".join(lines) + "\n"


def render_slack_blocks(
    summary: IncidentSummary,
    *,
    context: IncidentContext | None = None,
    detail_url: str | None = None,
) -> list[dict[str, Any]]:
    """Block list for the incident brief (also written to slack_blocks.json)."""
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": _headline(summary)}},
    ]
    if context is not None and (ctx_line := _context_line(context)):
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": ctx_line}]}
        )
    if summary.warnings:
        blocks.append(_section("*Warning:* " + summary.warnings[0]))
    if summary.findings:
        top = summary.findings[0]
        cause = ""
        if top.cause_path:
            rule = f" — {top.cause_rule}" if top.cause_rule else ""
            cause = f"\n*Likely cause:* `{top.cause_path}`{rule}{_low_confidence_suffix(top)}"
        blocks.append(_section(f"*Impact:* {top.impact_summary}{cause}"))
        extra = summary.findings[1:_MAX_SLACK_FINDINGS]
        if extra:
            listed = "\n".join(f"• {f.title}: {f.impact_summary}" for f in extra)
            remaining = len(summary.findings) - _MAX_SLACK_FINDINGS
            if remaining > 0:
                listed += f"\n_+ {remaining} more in the full report_"
            blocks.append(_section(f"*Also affected:*\n{listed}"))
    else:
        blocks.append(_section("No behavioral changes detected."))
    buttons = _buttons(context, detail_url)
    if buttons:
        blocks.append({"type": "actions", "elements": buttons})
    return blocks


def render_slack_payload(
    summary: IncidentSummary,
    *,
    context: IncidentContext | None = None,
    detail_url: str | None = None,
) -> dict[str, Any]:
    """Full chat.postMessage payload: color-barred attachment + text fallback."""
    return {
        "text": _fallback_text(summary),
        "attachments": [
            {
                "color": _COLOR[summary.verdict],
                "blocks": render_slack_blocks(summary, context=context, detail_url=detail_url),
            }
        ],
    }


def _headline(summary: IncidentSummary) -> str:
    emoji = _EMOJI[summary.verdict]
    if summary.verdict == "pass":
        return f"{emoji} AgentDiff: no behavioral changes"
    if summary.verdict == "warn":
        if summary.findings:
            return f"{emoji} AgentDiff notice: {summary.findings[0].title}"
        return f"{emoji} AgentDiff: gate ran with notices"
    if len(summary.findings) > 1:
        return f"{_EMOJI['fail']} AgentDiff: {len(summary.findings)} behavioral changes detected"
    title = summary.findings[0].title if summary.findings else "behavioral change"
    return f"{_EMOJI['fail']} AgentDiff: {title}"


def _fallback_text(summary: IncidentSummary) -> str:
    head = f"AgentDiff {_LABEL[summary.verdict]}"
    if summary.findings:
        top = summary.findings[0]
        cause = f" — cause {top.cause_path}" if top.cause_path else ""
        return f"{head}: {top.title}{cause}"
    if summary.warnings:
        return f"{head}: {summary.warnings[0]}"
    return f"{head}: no behavioral changes"


def _context_line(context: IncidentContext) -> str:
    parts: list[str] = []
    if context.repository:
        parts.append(context.repository)
    if context.pr_number:
        parts.append(f"PR #{context.pr_number}")
    if context.baseline_ref or context.candidate_ref:
        parts.append(f"`{context.baseline_ref or '?'}` → `{context.candidate_ref or 'working'}`")
    if context.tier:
        parts.append(f"{context.tier} tier")
    return " · ".join(parts)


def _buttons(context: IncidentContext | None, detail_url: str | None) -> list[dict[str, Any]]:
    buttons: list[dict[str, Any]] = []
    if detail_url:
        buttons.append(_button("Open AgentDiff report", detail_url))
    if context is not None:
        if (pr_url := context.pr_url()) is not None:
            buttons.append(_button("View PR", pr_url))
        if context.run_url:
            buttons.append(_button("CI run", context.run_url))
    return buttons


def _button(label: str, url: str) -> dict[str, Any]:
    return {"type": "button", "text": {"type": "plain_text", "text": label}, "url": url}


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

"""Slack notification helper — degrades gracefully on any delivery error."""
from __future__ import annotations

import logging
from typing import Any, Callable

import httpx
from sqlalchemy import func, select

from agentdiff.incident.findings import IncidentFinding, IncidentSummary
from agentdiff.incident.renderers import render_slack_payload
from agentdiff.incident.slack import SlackClient

from server import crypto
from server.config import get_settings
from server.models import Project, SlackConfig, Trajectory

log = logging.getLogger("agentdiff.notify")

# ── Injectable webhook POST function (monkeypatched in tests) ─────────────────


def _default_webhook_post(url: str, json: dict, timeout: int) -> httpx.Response:
    return httpx.post(url, json=json, timeout=timeout)


webhook_post_fn: Callable[[str, dict, int], httpx.Response] = _default_webhook_post


# ── Slack mrkdwn escape (minimal: only & < >) ────────────────────────────────


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Truncate hunk to max 12 lines / 900 chars ────────────────────────────────


def _truncate_hunk(hunk: str, max_lines: int = 12, max_chars: int = 900) -> str:
    lines = hunk.splitlines()
    truncated_lines = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated_lines = True
    result = "\n".join(lines)
    truncated_chars = False
    if len(result) > max_chars:
        result = result[:max_chars]
        truncated_chars = True
    if truncated_lines or truncated_chars:
        result += "…"
    return result


# ── Section block helper ──────────────────────────────────────────────────────


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


# ── Statistical evidence compact line ────────────────────────────────────────


def _stat_line(evidence: dict | None) -> str | None:
    """Render a compact stat summary, e.g. 'p<0.001 · 100%→0% · 95% CI [0%, 0%]'.

    Returns None when there's nothing useful to show.
    """
    if not evidence:
        return None

    parts: list[str] = []

    # p-value
    p = evidence.get("p_value")
    if p is not None:
        if p < 0.001:
            p_str = "p<0.001"
        else:
            p_str = f"p={p:.3f}"
        if evidence.get("significant"):
            p_str += "*"
        parts.append(p_str)

    # baseline_rate → candidate_rate as percents (from AgentInvocationDelta)
    # These aren't stored in statistical_evidence directly, but the finding's
    # impact_summary already shows them. Instead extract from evidence.baseline_n
    # and candidate_n as raw invocation fractions are not in the stats object.
    # We can render n= counts instead.
    bn = evidence.get("baseline_n")
    cn = evidence.get("candidate_n")
    if bn is not None and cn is not None:
        parts.append(f"n={bn}/{cn}")

    # Confidence interval
    ci = evidence.get("confidence_interval")
    if ci and len(ci) == 2:
        lo_pct = round(ci[0] * 100)
        hi_pct = round(ci[1] * 100)
        parts.append(f"95% CI [{lo_pct}%, {hi_pct}%]")

    if not parts:
        return None
    return " · ".join(parts)


# ── Shared delivery mechanics ─────────────────────────────────────────────────


async def _deliver(session_or_cfg: Any, run: Any, payload: dict) -> None:
    """Bot-first, webhook-fallback delivery. Any failure is logged and swallowed."""
    # session_or_cfg may be a SQLAlchemy session (we query it) or a SlackConfig directly.
    if hasattr(session_or_cfg, "execute"):
        session = session_or_cfg
        cfg: SlackConfig | None = (
            await session.execute(
                select(SlackConfig).where(SlackConfig.project_id == run.project_id)
            )
        ).scalar_one_or_none()
    else:
        cfg = session_or_cfg

    if cfg is None or not cfg.enabled:
        return

    try:
        bot_ok = False
        if cfg.bot_token_encrypted:
            try:
                token = crypto.decrypt(cfg.bot_token_encrypted)
                result = SlackClient(token).post_payload(cfg.channel_id, payload)
                if result.ok:
                    bot_ok = True
                else:
                    log.info(
                        "slack bot post not ok for run %s: %s", run.id, result.error
                    )
            except Exception as exc:
                log.info(
                    "slack bot post raised for run %s: %s", run.id, type(exc).__name__
                )

        if bot_ok:
            return

        if cfg.webhook_url_encrypted:
            webhook_url = crypto.decrypt(cfg.webhook_url_encrypted)
            resp = webhook_post_fn(webhook_url, payload, 10)
            if not resp.is_success:
                raise RuntimeError(f"webhook returned HTTP {resp.status_code}")

    except Exception as exc:  # degrade — never let a Slack failure fail the run
        log.warning("slack delivery failed for run %s: %s", run.id, type(exc).__name__)


# ── Payload enrichment ────────────────────────────────────────────────────────


async def _enrich_payload(
    session: Any,
    run: Any,
    payload: dict,
    finding_dicts: list[dict],
    *,
    extra_context: dict | None = None,
) -> None:
    """Mutate payload["attachments"][0]["blocks"] in-place with context, cause detail,
    and deep-link button. All errors are silently swallowed (degrade preserved)."""
    try:
        blocks: list[dict] = payload["attachments"][0]["blocks"]

        # A1 — Context block (insert after header, index 0)
        project = (
            await session.execute(
                select(Project).where(Project.id == run.project_id)
            )
        ).scalar_one_or_none()
        project_name = project.name if project else str(run.project_id)

        kind_label = "LIVE DRIFT" if run.kind == "drift" else "CI"
        baseline = run.baseline_ref or "?"
        candidate = run.candidate_ref or "?"

        if extra_context and run.kind == "drift":
            # A4 — drift: sample counts come from extra_context
            nb = extra_context.get("baseline_samples", 0)
            nc = extra_context.get("candidate_samples", 0)
            wm = extra_context.get("window_minutes", 0)
            hours = wm / 60
            if hours == int(hours):
                window_str = f"{int(hours)}h"
            else:
                window_str = f"{hours:.1f}h"
            ctx_text = (
                f"*{_slack_escape(project_name)}* · {kind_label} · "
                f"`{_slack_escape(baseline)}` → `{_slack_escape(candidate)}` · "
                f"{window_str} window · n={nb} vs {nc} samples"
            )
        else:
            # Count trajectories from DB for CI runs
            side_counts = (
                await session.execute(
                    select(Trajectory.side, func.count(Trajectory.id))
                    .where(Trajectory.run_id == run.id)
                    .group_by(Trajectory.side)
                )
            ).all()
            counts = {row[0]: row[1] for row in side_counts}
            nb = counts.get("baseline", 0)
            nc = counts.get("candidate", 0)
            ctx_text = (
                f"*{_slack_escape(project_name)}* · {kind_label} · "
                f"`{_slack_escape(baseline)}` → `{_slack_escape(candidate)}` · "
                f"n={nb} vs {nc} samples"
            )

        # Insert context block after header (position 1)
        ctx_block = {"type": "context", "elements": [{"type": "mrkdwn", "text": ctx_text}]}
        if blocks and blocks[0].get("type") == "header":
            blocks.insert(1, ctx_block)
        else:
            blocks.insert(0, ctx_block)

        # A2 — Cause detail for top finding
        if finding_dicts:
            top = finding_dicts[0]
            cause_hunk = top.get("cause_hunk")
            explanation = top.get("explanation")
            if cause_hunk:
                truncated = _truncate_hunk(cause_hunk)
                blocks.append(_section(f"```{_slack_escape(truncated)}```"))
            if explanation:
                blocks.append(_section(f"> {_slack_escape(explanation)}"))
            # P3 — Statistical evidence compact line
            stat = _stat_line(top.get("statistical_evidence"))
            if stat:
                blocks.append(_section(_slack_escape(stat)))

        # A3 — Deep link button
        run_url = f"{get_settings().dashboard_url}/runs/{run.id}"
        view_button: dict[str, Any] = {
            "type": "button",
            "text": {"type": "plain_text", "text": "View in AgentDiff"},
            "url": run_url,
        }
        # Check if there's already an actions block; if so append into it
        actions_idx = next(
            (i for i, b in enumerate(blocks) if b.get("type") == "actions"), None
        )
        if actions_idx is not None:
            existing_elements = blocks[actions_idx].get("elements", [])
            existing_elements.append(view_button)
            blocks[actions_idx]["elements"] = existing_elements
        else:
            blocks.append({"type": "actions", "elements": [view_button]})

    except Exception as exc:
        log.debug("slack enrichment failed for run %s: %s", run.id, exc)


# ── Public API ────────────────────────────────────────────────────────────────


async def maybe_post_slack(
    session: Any,
    run: Any,
    finding_dicts: list[dict],
    verdict: str,
    *,
    extra_context: dict | None = None,
) -> None:
    if verdict not in {"warn", "fail"}:
        return
    cfg = (
        await session.execute(
            select(SlackConfig).where(SlackConfig.project_id == run.project_id)
        )
    ).scalar_one_or_none()
    if cfg is None or not cfg.enabled:
        return
    try:
        summary = IncidentSummary(
            verdict=verdict,
            findings=[IncidentFinding.model_validate(fd) for fd in finding_dicts],
        )
        payload = render_slack_payload(summary)

        # Enrich the payload server-side
        await _enrich_payload(
            session, run, payload, finding_dicts, extra_context=extra_context
        )

        await _deliver(cfg, run, payload)

    except Exception as exc:  # degrade — never let a Slack failure fail the run
        log.warning("slack delivery failed for run %s: %s", run.id, type(exc).__name__)


async def post_recovery(session: Any, run: Any) -> None:
    """Post a green recovery notification when a CI run passes after a prior fail/warn."""
    cfg = (
        await session.execute(
            select(SlackConfig).where(SlackConfig.project_id == run.project_id)
        )
    ).scalar_one_or_none()
    if cfg is None or not cfg.enabled:
        return

    try:
        project = (
            await session.execute(
                select(Project).where(Project.id == run.project_id)
            )
        ).scalar_one_or_none()
        project_name = project.name if project else str(run.project_id)

        baseline = run.baseline_ref or "?"
        candidate = run.candidate_ref or "?"
        run_url = f"{get_settings().dashboard_url}/runs/{run.id}"

        payload: dict[str, Any] = {
            "text": f"AgentDiff: {project_name} recovered",
            "attachments": [
                {
                    "color": "#3FB27F",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"\U0001f7e2 AgentDiff: {project_name} recovered",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": (
                                        f"CI · "
                                        f"`{_slack_escape(baseline)}` → `{_slack_escape(candidate)}`"
                                    ),
                                }
                            ],
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "View in AgentDiff"},
                                    "url": run_url,
                                }
                            ],
                        },
                    ],
                }
            ],
        }

        await _deliver(cfg, run, payload)

    except Exception as exc:
        log.warning(
            "slack recovery notification failed for run %s: %s", run.id, type(exc).__name__
        )

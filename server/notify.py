"""Slack notification helper — degrades gracefully on any delivery error."""
from __future__ import annotations

import logging

from sqlalchemy import select

from agentdiff.incident.findings import IncidentFinding, IncidentSummary
from agentdiff.incident.renderers import render_slack_payload
from agentdiff.incident.slack import SlackClient

from server import crypto
from server.models import SlackConfig

log = logging.getLogger("agentdiff.notify")


async def maybe_post_slack(session, run, finding_dicts: list[dict], verdict: str) -> None:
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
        token = crypto.decrypt(cfg.bot_token_encrypted)
        SlackClient(token).post_payload(cfg.channel_id, payload)
    except Exception as exc:  # degrade — never let a Slack failure fail the run
        log.warning("slack delivery failed for run %s: %s", run.id, type(exc).__name__)

"""Slack notification helper — degrades gracefully on any delivery error."""
from __future__ import annotations

import logging
from typing import Callable

import httpx
from sqlalchemy import select

from agentdiff.incident.findings import IncidentFinding, IncidentSummary
from agentdiff.incident.renderers import render_slack_payload
from agentdiff.incident.slack import SlackClient

from server import crypto
from server.models import SlackConfig

log = logging.getLogger("agentdiff.notify")

# ── Injectable webhook POST function (monkeypatched in tests) ─────────────────


def _default_webhook_post(url: str, json: dict, timeout: int) -> httpx.Response:
    return httpx.post(url, json=json, timeout=timeout)


webhook_post_fn: Callable[[str, dict, int], httpx.Response] = _default_webhook_post


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

        # ── Bot-first path ────────────────────────────────────────────────────
        # If the bot token is set, try chat.postMessage (bot appears as a channel
        # member and is @mentionable). This is the common/public-channel case.
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

        # ── Webhook fallback ──────────────────────────────────────────────────
        # Used when: (a) bot post failed (e.g. not_in_channel on private channel),
        # or (b) only a webhook is configured (legacy/manual).
        if cfg.webhook_url_encrypted:
            webhook_url = crypto.decrypt(cfg.webhook_url_encrypted)
            resp = webhook_post_fn(webhook_url, payload, 10)
            if not resp.is_success:
                raise RuntimeError(f"webhook returned HTTP {resp.status_code}")

    except Exception as exc:  # degrade — never let a Slack failure fail the run
        log.warning("slack delivery failed for run %s: %s", run.id, type(exc).__name__)

"""Notification stubs — Slack integration is fleshed out in Task 2.3."""
from __future__ import annotations


async def maybe_post_slack(session, run, finding_dicts: list[dict], verdict: str) -> None:
    """No-op until Task 2.3 wires a real Slack client."""
    return None

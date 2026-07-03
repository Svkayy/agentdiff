"""Slack OAuth routes — install, callback, status, disconnect."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Callable
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import crypto
from server.config import get_settings
from server.db import get_session
from server.deps import get_user_ctx, own_project
from server.models import Org, SlackConfig, User

log = logging.getLogger("agentdiff.slack_oauth")

router = APIRouter()

# ── Injectable exchange function (monkeypatched in tests) ─────────────────────


def _default_exchange(url: str, data: dict, timeout: int) -> httpx.Response:
    return httpx.post(url, data=data, timeout=timeout)


exchange_fn: Callable[[str, dict, int], httpx.Response] = _default_exchange


# ── Install endpoint ──────────────────────────────────────────────────────────


@router.get("/v1/slack/install")
async def slack_install(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings = get_settings()
    if not settings.slack_client_id:
        raise HTTPException(status_code=503, detail="Slack OAuth not configured")

    _user, org = ctx
    # Guard: project must belong to the requesting org.
    await own_project(session, org, project_id)

    state = crypto.encrypt(json.dumps({"project_id": str(project_id)}))
    params = urlencode(
        {
            "client_id": settings.slack_client_id,
            "scope": "incoming-webhook,chat:write",
            "redirect_uri": settings.slack_redirect_url,
            "state": state,
        }
    )
    url = f"https://slack.com/oauth/v2/authorize?{params}"
    return {"url": url}


# ── Callback endpoint (unauthenticated — Slack redirects the browser here) ────


@router.get("/v1/slack/callback")
async def slack_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    settings = get_settings()

    # Validate state (signed + TTL 600s).
    if not state:
        raise HTTPException(status_code=400, detail="missing state parameter")
    try:
        payload = json.loads(crypto.decrypt(state, ttl=600))
        project_id = uuid.UUID(payload["project_id"])
    except Exception:
        raise HTTPException(status_code=400, detail="invalid or expired state")

    error_redirect = RedirectResponse(
        url=f"{settings.dashboard_url}/projects/{project_id}?slack=error",
        status_code=307,
    )

    # Slack may redirect back with an error param (e.g., user cancelled).
    if error or not code:
        return error_redirect

    # Exchange the code for an access token.
    try:
        resp = exchange_fn(
            "https://slack.com/api/oauth.v2.access",
            {
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": settings.slack_redirect_url,
            },
            10,
        )
        data = resp.json()
    except Exception as exc:
        log.warning("Slack token exchange failed: %s", type(exc).__name__)
        return error_redirect

    if not data.get("ok"):
        # Slack error codes ("access_denied" etc.) are safe to log — never tokens.
        log.warning("Slack token exchange returned ok=false: %s", data.get("error"))
        return error_redirect

    access_token = data.get("access_token", "")
    webhook_info = data.get("incoming_webhook", {})
    webhook_url = webhook_info.get("url", "")
    channel_id = webhook_info.get("channel_id", "")

    if not access_token or not (channel_id or "").strip():
        log.warning("Slack token exchange missing required fields")
        return error_redirect

    # Upsert SlackConfig.
    cfg = (
        await session.execute(
            select(SlackConfig).where(SlackConfig.project_id == project_id)
        )
    ).scalar_one_or_none()

    if cfg is None:
        cfg = SlackConfig(
            project_id=project_id,
            channel_id=channel_id,
            bot_token_encrypted=crypto.encrypt(access_token),
            webhook_url_encrypted=crypto.encrypt(webhook_url) if webhook_url else None,
            enabled=True,
        )
        session.add(cfg)
    else:
        cfg.channel_id = channel_id
        cfg.bot_token_encrypted = crypto.encrypt(access_token)
        cfg.webhook_url_encrypted = crypto.encrypt(webhook_url) if webhook_url else None
        cfg.enabled = True

    await session.commit()

    return RedirectResponse(
        url=f"{settings.dashboard_url}/projects/{project_id}?slack=connected",
        status_code=307,
    )


# ── Status endpoint ───────────────────────────────────────────────────────────


@router.get("/v1/projects/{project_id}/slack")
async def get_slack_status(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    await own_project(session, org, project_id)

    cfg = (
        await session.execute(
            select(SlackConfig).where(SlackConfig.project_id == project_id)
        )
    ).scalar_one_or_none()

    if cfg is None or not cfg.enabled:
        return {"connected": False, "channel_id": None, "via": None}

    via = "oauth" if cfg.webhook_url_encrypted else "manual"
    return {"connected": True, "channel_id": cfg.channel_id, "via": via}


# ── Disconnect endpoint ───────────────────────────────────────────────────────


@router.delete("/v1/projects/{project_id}/slack", status_code=204)
async def disconnect_slack(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> None:
    _user, org = ctx
    await own_project(session, org, project_id)

    cfg = (
        await session.execute(
            select(SlackConfig).where(SlackConfig.project_id == project_id)
        )
    ).scalar_one_or_none()

    if cfg is not None:
        await session.delete(cfg)
        await session.commit()

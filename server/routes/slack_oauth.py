"""Slack OAuth routes — install, callback, status, disconnect."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Callable
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import crypto
from server.audit import record_audit
from server.config import get_settings
from server.db import get_session
from server.deps import get_user_ctx, own_project
from server.models import Org, Project, SlackConfig, User

# Actor recorded when the OAuth callback's state carries no actor (e.g. a
# stale/pre-Task-11 install link) — the callback is otherwise unauthenticated
# so there is no Clerk user context to fall back to.
_FALLBACK_ACTOR = "slack-oauth"

log = logging.getLogger("agentdiff.slack_oauth")

router = APIRouter()

# ── Injectable exchange function (monkeypatched in tests) ─────────────────────


def _default_exchange(url: str, data: dict, timeout: int) -> httpx.Response:
    return httpx.post(url, data=data, timeout=timeout)


exchange_fn: Callable[[str, dict, int], httpx.Response] = _default_exchange


def _default_join(bot_token: str, channel_id: str) -> dict:
    resp = httpx.post(
        "https://slack.com/api/conversations.join",
        headers={"Authorization": f"Bearer {bot_token}"},
        json={"channel": channel_id},
        timeout=10,
    )
    return resp.json()


join_fn: Callable[[str, str], dict] = _default_join


def _state_nonce_key(state: str) -> str:
    """Redis key for the single-use install-state nonce."""
    return "slack:state:" + hashlib.sha256(state.encode()).hexdigest()


# ── Install endpoint ──────────────────────────────────────────────────────────


@router.get("/v1/slack/install")
async def slack_install(
    project_id: uuid.UUID,
    request: Request,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings = get_settings()
    if not settings.slack_client_id:
        raise HTTPException(status_code=503, detail="Slack OAuth not configured")

    user, org = ctx
    # Guard: project must belong to the requesting org.
    await own_project(session, org, project_id)

    # Carry the initiating user's Clerk id through state so the (unauthenticated)
    # callback can attribute the audit row to a real actor.
    state = crypto.encrypt(
        json.dumps({"project_id": str(project_id), "actor": user.clerk_user_id})
    )
    params = urlencode(
        {
            "client_id": settings.slack_client_id,
            "scope": "incoming-webhook,chat:write,channels:join",
            "redirect_uri": settings.slack_redirect_url,
            "state": state,
        }
    )
    url = f"https://slack.com/oauth/v2/authorize?{params}"

    # Single-use guard: register a nonce so the unauthenticated callback
    # accepts each state exactly once — a leaked or replayed install URL
    # within the 600s TTL can't rebind a project's Slack config.
    redis_pool = getattr(request.app.state, "redis_pool", None)
    if redis_pool is not None:
        await redis_pool.set(_state_nonce_key(state), "1", ex=600)

    return {"url": url}


# ── Callback endpoint (unauthenticated — Slack redirects the browser here) ────


@router.get("/v1/slack/callback")
async def slack_callback(
    request: Request,
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

    # Consume the single-use nonce minted at install (enforced whenever a
    # Redis pool is wired — i.e. in every real deployment).  A state that
    # was never minted here, or was already consumed, is rejected even if
    # its signature and TTL are valid.
    redis_pool = getattr(request.app.state, "redis_pool", None)
    if redis_pool is not None:
        consumed = await redis_pool.getdel(_state_nonce_key(state))
        if consumed is None:
            raise HTTPException(status_code=400, detail="invalid or expired state")

    actor = payload.get("actor") or _FALLBACK_ACTOR

    error_redirect = RedirectResponse(
        url=f"{settings.dashboard_url}/projects/{project_id}?slack=error",
        status_code=307,
    )

    # Slack may redirect back with an error param (e.g., user cancelled).
    if error or not code:
        return error_redirect

    # Exchange the code for an access token.
    try:
        resp = await asyncio.to_thread(
            exchange_fn,
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

    project_org_id = (
        await session.execute(select(Project.org_id).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project_org_id is not None:
        await record_audit(
            session,
            project_org_id,
            actor,
            "slack.connected",
            "project",
            str(project_id),
            project_id=project_id,
        )

    await session.commit()

    # Best-effort: join the channel as a bot member (public channels only).
    # Private channels → Slack returns method_not_supported_for_channel_type; we log + continue.
    # The webhook fallback covers channels the bot could not join.
    try:
        join_result = await asyncio.to_thread(join_fn, access_token, channel_id)
        if not join_result.get("ok"):
            log.info(
                "Slack conversations.join skipped for channel %s: %s",
                channel_id,
                join_result.get("error"),
            )
    except Exception as exc:
        log.info("Slack conversations.join raised for channel %s: %s", channel_id, type(exc).__name__)

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
    user, org = ctx
    await own_project(session, org, project_id)

    cfg = (
        await session.execute(
            select(SlackConfig).where(SlackConfig.project_id == project_id)
        )
    ).scalar_one_or_none()

    # Idempotent: only write an audit row when there was actually a config to
    # disconnect — a repeat DELETE must not produce a second audit row.
    if cfg is not None:
        await session.delete(cfg)
        await record_audit(
            session,
            org.id,
            user.clerk_user_id,
            "slack.disconnected",
            "project",
            str(project_id),
            project_id=project_id,
        )
        await session.commit()

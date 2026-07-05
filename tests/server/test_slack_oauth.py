"""Tests for Slack OAuth install/callback/status/disconnect routes."""
import json
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from server import crypto
from server.db import get_session
from server.deps import get_user_ctx
from server.main import app
from server.models import AuditLog, Org, Project, SlackConfig, User
from server.routes import slack_oauth


async def _client(session, user_ctx):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = lambda: user_ctx
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── 1. Install endpoint ───────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_install_returns_authorize_url(session, monkeypatch):
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_SECRET", "test-client-secret")
    # Clear lru_cache so settings picks up the patched env vars.
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="install-org")
    project = Project(org=org, name="install-proj")
    session.add(project)
    await session.commit()

    user = User(org_id=org.id, clerk_user_id="u_install", email="i@i")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/slack/install?project_id={project.id}")
            assert r.status_code == 200
            data = r.json()
            assert "url" in data
            url = data["url"]
            assert "slack.com/oauth/v2/authorize" in url
            assert "test-client-id" in url
            assert "incoming-webhook" in url
            assert "channels%3Ajoin" in url or "channels:join" in url
            # state round-trips to the project id
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            state = qs["state"][0]
            payload = json.loads(crypto.decrypt(state))
            assert payload["project_id"] == str(project.id)
            # state also carries the initiating user (Clerk id) so the OAuth
            # callback can attribute the audit row to a real actor.
            assert payload["actor"] == user.clerk_user_id
            # redirect_uri is URL-encoded in the query string
            assert "redirect_uri" in url
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_install_cross_org_404(session, monkeypatch):
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    from server.config import get_settings
    get_settings.cache_clear()

    orgA = Org(name="cross-org-A")
    orgB = Org(name="cross-org-B")
    proj_b = Project(org=orgB, name="proj-b")
    session.add_all([orgA, proj_b])
    await session.commit()

    user_a = User(org_id=orgA.id, clerk_user_id="u_cross", email="cross@a")
    session.add(user_a)
    await session.commit()

    try:
        async with await _client(session, (user_a, orgA)) as c:
            r = await c.get(f"/v1/slack/install?project_id={proj_b.id}")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_install_no_client_id_503(session, monkeypatch):
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "")
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="no-client-id-org")
    project = Project(org=org, name="no-client-id-proj")
    session.add(project)
    await session.commit()

    user = User(org_id=org.id, clerk_user_id="u_no_cid", email="nc@nc")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/slack/install?project_id={project.id}")
            assert r.status_code == 503
            assert "not configured" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


# ── 2. Callback happy path ────────────────────────────────────────────────────


def _make_exchange_fn(ok: bool, access_token: str = "xoxb-test", channel_id: str = "C99", webhook_url: str = "https://hooks.slack.com/test"):
    def exchange_fn(url, data, timeout):
        mock = MagicMock()
        if ok:
            mock.json.return_value = {
                "ok": True,
                "access_token": access_token,
                "incoming_webhook": {
                    "url": webhook_url,
                    "channel_id": channel_id,
                },
            }
        else:
            mock.json.return_value = {"ok": False, "error": "access_denied"}
        return mock
    return exchange_fn


@pytest.mark.asyncio(loop_scope="session")
async def test_callback_happy_path(session, monkeypatch):
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AGENTDIFF_DASHBOARD_URL", "http://localhost:5173")
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="callback-org")
    project = Project(org=org, name="callback-proj")
    session.add(project)
    await session.commit()

    user = User(org=org, clerk_user_id="u_callback_actor", email="cb@cb.com")
    session.add(user)
    await session.commit()

    # Build a valid state — carries both project_id and the actor who initiated
    # the OAuth flow (threaded through from /v1/slack/install).
    state = crypto.encrypt(
        json.dumps({"project_id": str(project.id), "actor": user.clerk_user_id})
    )

    # Monkeypatch the exchange function and join_fn.
    monkeypatch.setattr(slack_oauth, "exchange_fn", _make_exchange_fn(ok=True))

    join_calls: list[tuple[str, str]] = []

    def fake_join(bot_token: str, channel_id: str) -> dict:
        join_calls.append((bot_token, channel_id))
        return {"ok": True}

    monkeypatch.setattr(slack_oauth, "join_fn", fake_join)

    # Callback is unauthenticated — no user_ctx override.
    app.dependency_overrides[get_session] = lambda: session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                f"/v1/slack/callback?code=test-code&state={state}",
                follow_redirects=False,
            )
            assert r.status_code == 307
            assert r.headers["location"].startswith("http://localhost:5173/projects/")
            assert "slack=connected" in r.headers["location"]

        # join_fn must be called exactly once with the channel_id.
        assert len(join_calls) == 1
        _tok, joined_channel = join_calls[0]
        assert joined_channel == "C99"

        # SlackConfig row should exist.
        cfg = (
            await session.execute(
                select(SlackConfig).where(SlackConfig.project_id == project.id)
            )
        ).scalar_one_or_none()
        assert cfg is not None
        assert cfg.channel_id == "C99"
        assert cfg.enabled is True
        # Token decrypt round-trip.
        assert crypto.decrypt(cfg.bot_token_encrypted) == "xoxb-test"
        # Webhook URL decrypt round-trip.
        assert cfg.webhook_url_encrypted is not None
        assert crypto.decrypt(cfg.webhook_url_encrypted) == "https://hooks.slack.com/test"

        # Audit row written for slack.connected, actor = the user who initiated install.
        rows = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "slack.connected",
                    AuditLog.target_id == str(project.id),
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].target_type == "project"
        assert rows[0].target_id == str(project.id)
        assert rows[0].org_id == org.id
        assert rows[0].actor == user.clerk_user_id
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


# ── 3. Callback bad state + exchange error ────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_callback_bad_state_400(session, monkeypatch):
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    from server.config import get_settings
    get_settings.cache_clear()

    app.dependency_overrides[get_session] = lambda: session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                "/v1/slack/callback?code=anything&state=not-a-valid-token",
                follow_redirects=False,
            )
            assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_callback_exchange_error_redirects_to_error(session, monkeypatch):
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AGENTDIFF_DASHBOARD_URL", "http://localhost:5173")
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="err-org")
    project = Project(org=org, name="err-proj")
    session.add(project)
    await session.commit()

    state = crypto.encrypt(json.dumps({"project_id": str(project.id)}))
    monkeypatch.setattr(slack_oauth, "exchange_fn", _make_exchange_fn(ok=False))

    app.dependency_overrides[get_session] = lambda: session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                f"/v1/slack/callback?code=bad-code&state={state}",
                follow_redirects=False,
            )
            assert r.status_code == 307
            assert r.headers["location"].startswith("http://localhost:5173/projects/")
            assert "slack=error" in r.headers["location"]

        # No SlackConfig should have been written.
        cfg = (
            await session.execute(
                select(SlackConfig).where(SlackConfig.project_id == project.id)
            )
        ).scalar_one_or_none()
        assert cfg is None
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


# ── 4. Status + disconnect ────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_status_and_disconnect(session, monkeypatch):
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AGENTDIFF_DASHBOARD_URL", "http://localhost:5173")
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="status-org")
    project = Project(org=org, name="status-proj")
    session.add(project)
    await session.commit()

    user = User(org_id=org.id, clerk_user_id="u_status", email="s@s")
    session.add(user)
    await session.commit()

    # Seed a connected config with webhook (simulating OAuth path).
    cfg = SlackConfig(
        project=project,
        channel_id="C77",
        bot_token_encrypted=crypto.encrypt("xoxb-status"),
        webhook_url_encrypted=crypto.encrypt("https://hooks.slack.com/s"),
        enabled=True,
    )
    session.add(cfg)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            # Status: connected, via=oauth.
            r = await c.get(f"/v1/projects/{project.id}/slack")
            assert r.status_code == 200
            data = r.json()
            assert data["connected"] is True
            assert data["channel_id"] == "C77"
            assert data["via"] == "oauth"
            # Must NOT include token or webhook material.
            assert "xoxb" not in str(data)
            assert "hooks.slack.com" not in str(data)

            # Disconnect.
            r2 = await c.delete(f"/v1/projects/{project.id}/slack")
            assert r2.status_code == 204

            # Status: disconnected.
            r3 = await c.get(f"/v1/projects/{project.id}/slack")
            assert r3.status_code == 200
            assert r3.json()["connected"] is False

            # Second DELETE is idempotent.
            r4 = await c.delete(f"/v1/projects/{project.id}/slack")
            assert r4.status_code == 204

            # Audit row written exactly once for slack.disconnected.
            rows = (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "slack.disconnected")
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].actor == user.clerk_user_id
            assert rows[0].target_type == "project"
            assert rows[0].target_id == str(project.id)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


# ── 5. Manual via=manual path ─────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_status_via_manual_when_no_webhook(session, monkeypatch):
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="manual-org")
    project = Project(org=org, name="manual-proj")
    session.add(project)
    await session.commit()

    user = User(org_id=org.id, clerk_user_id="u_manual_s", email="m@m")
    session.add(user)
    await session.commit()

    # No webhook — only bot token (manual setup).
    cfg = SlackConfig(
        project=project,
        channel_id="C55",
        bot_token_encrypted=crypto.encrypt("xoxb-manual"),
        webhook_url_encrypted=None,
        enabled=True,
    )
    session.add(cfg)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/projects/{project.id}/slack")
            assert r.status_code == 200
            data = r.json()
            assert data["connected"] is True
            assert data["via"] == "manual"
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


# ── 6. join_fn failure does NOT break callback ────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_callback_join_ok_false_still_connected(session, monkeypatch):
    """join_fn returns ok=false (private channel) → callback still 307 slack=connected."""
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AGENTDIFF_DASHBOARD_URL", "http://localhost:5173")
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="join-fail-org")
    project = Project(org=org, name="join-fail-proj")
    session.add(project)
    await session.commit()

    state = crypto.encrypt(json.dumps({"project_id": str(project.id)}))
    monkeypatch.setattr(slack_oauth, "exchange_fn", _make_exchange_fn(ok=True, channel_id="C77"))

    def join_ok_false(bot_token: str, channel_id: str) -> dict:
        return {"ok": False, "error": "method_not_supported_for_channel_type"}

    monkeypatch.setattr(slack_oauth, "join_fn", join_ok_false)

    app.dependency_overrides[get_session] = lambda: session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                f"/v1/slack/callback?code=test-code&state={state}",
                follow_redirects=False,
            )
            assert r.status_code == 307
            assert "slack=connected" in r.headers["location"]

        # Config must still be written.
        cfg = (
            await session.execute(
                select(SlackConfig).where(SlackConfig.project_id == project.id)
            )
        ).scalar_one_or_none()
        assert cfg is not None
        assert cfg.channel_id == "C77"
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_callback_join_raises_still_connected(session, monkeypatch):
    """join_fn raises → callback still 307 slack=connected, config still written."""
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AGENTDIFF_SLACK_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AGENTDIFF_DASHBOARD_URL", "http://localhost:5173")
    from server.config import get_settings
    get_settings.cache_clear()

    org = Org(name="join-raise-org")
    project = Project(org=org, name="join-raise-proj")
    session.add(project)
    await session.commit()

    state = crypto.encrypt(json.dumps({"project_id": str(project.id)}))
    monkeypatch.setattr(slack_oauth, "exchange_fn", _make_exchange_fn(ok=True, channel_id="C88"))

    def join_raises(bot_token: str, channel_id: str) -> dict:
        raise RuntimeError("network error")

    monkeypatch.setattr(slack_oauth, "join_fn", join_raises)

    app.dependency_overrides[get_session] = lambda: session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                f"/v1/slack/callback?code=test-code&state={state}",
                follow_redirects=False,
            )
            assert r.status_code == 307
            assert "slack=connected" in r.headers["location"]

        # Config must still be written.
        cfg = (
            await session.execute(
                select(SlackConfig).where(SlackConfig.project_id == project.id)
            )
        ).scalar_one_or_none()
        assert cfg is not None
        assert cfg.channel_id == "C88"

        # State carried no "actor" (e.g. pre-Task-11 link) — falls back to a
        # fixed sentinel rather than erroring or leaving actor blank.
        rows = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "slack.connected",
                    AuditLog.target_id == str(project.id),
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].actor == "slack-oauth"
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

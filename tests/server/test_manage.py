"""
Tests for the Tier-1 management API:
  GET  /v1/me
  POST /v1/projects
  POST /v1/projects/{id}/keys
  GET  /v1/projects/{id}/keys
  DELETE /v1/keys/{id}
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from server import security
from server.db import get_session
from server.deps import get_user_ctx
from server.main import app
from server.models import ApiKey, Org, Project, User


# ── helpers ──────────────────────────────────────────────────────────────────


def _override(session, user_ctx):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = lambda: user_ctx


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── /v1/me ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_me_returns_user_and_org(session):
    org = Org(name="Me-Org")
    user = User(org=org, clerk_user_id="me_test_user", email="me@test.example")
    session.add(user)
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.get("/v1/me")
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["id"] == str(user.id)
        assert body["user"]["email"] == user.email
        assert body["user"]["clerk_user_id"] == user.clerk_user_id
        assert body["org"]["id"] == str(org.id)
        assert body["org"]["name"] == org.name
    finally:
        app.dependency_overrides.clear()


# ── POST /v1/projects ────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_create_project_appears_in_list(session):
    org = Org(name="CreateProj-Org")
    user = User(org=org, clerk_user_id="create_proj_user", email="cp@test.example")
    session.add(user)
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.post("/v1/projects", json={"name": "new-project"})
            assert r.status_code == 201
            created_id = r.json()["id"]
            assert r.json()["name"] == "new-project"

            # Verify it appears in the existing reads endpoint.
            list_r = await c.get("/v1/projects")
            assert list_r.status_code == 200
            ids = [p["id"] for p in list_r.json()]
            assert created_id in ids
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_create_project_empty_name_422(session):
    org = Org(name="EmptyName-Org")
    user = User(org=org, clerk_user_id="empty_name_user", email="en@test.example")
    session.add(user)
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            for bad_name in ["", "   ", "\t\n"]:
                r = await c.post("/v1/projects", json={"name": bad_name})
                assert r.status_code == 422, f"Expected 422 for name={bad_name!r}"
    finally:
        app.dependency_overrides.clear()


# ── POST + GET /v1/projects/{id}/keys ────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_mint_key_reveal_once_and_list(session):
    org = Org(name="MintKey-Org")
    user = User(org=org, clerk_user_id="mint_key_user", email="mk@test.example")
    proj = Project(org=org, name="proj-mint")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            # Mint a key.
            r = await c.post(f"/v1/projects/{proj.id}/keys")
            assert r.status_code == 201
            body = r.json()
            assert "key" in body
            assert "prefix" in body
            assert "id" in body
            full_key = body["key"]
            prefix = body["prefix"]
            key_id = body["id"]

            # Full key must start with adk_.
            assert full_key.startswith("adk_")
            # Prefix must match the first 12 chars of the key.
            assert full_key[:12] == prefix

            # The returned full key must verify against the stored hash.
            row = (
                await session.execute(
                    select(ApiKey).where(ApiKey.id == key_id)
                )
            ).scalar_one()
            assert security.verify_api_key(full_key, row.key_hash)

            # List endpoint shows prefix but NOT key/hash.
            lr = await c.get(f"/v1/projects/{proj.id}/keys")
            assert lr.status_code == 200
            keys = lr.json()
            our = next((k for k in keys if k["id"] == key_id), None)
            assert our is not None
            assert our["prefix"] == prefix
            assert "key" not in our
            assert "key_hash" not in our
    finally:
        app.dependency_overrides.clear()


# ── End-to-end auth proof ─────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_minted_key_authenticates_ingest(session):
    """Mint a key via manage endpoint, then use it for POST /v1/runs (ingest)."""
    org = Org(name="E2E-Org")
    user = User(org=org, clerk_user_id="e2e_ingest_user", email="e2e@test.example")
    proj = Project(org=org, name="proj-e2e")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.post(f"/v1/projects/{proj.id}/keys")
            assert r.status_code == 201
            full_key = r.json()["key"]
    finally:
        app.dependency_overrides.clear()

    # Now call ingest with only the session override (real API key auth).
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = lambda rid: None
    try:
        run_payload = {
            "idempotency_key": "e2e-manage-proof",
            "baseline_ref": "origin/main",
            "candidate_ref": "feat/x",
            "tier": "hermetic",
            "config": {"agents": []},
            "attribution": None,
            "trajectories": [
                {"side": "baseline", "test_case_id": "tc1", "payload": {"events": []}}
            ],
        }
        async with _client() as c:
            r = await c.post(
                "/v1/runs",
                json=run_payload,
                headers={"Authorization": f"Bearer {full_key}"},
            )
        assert r.status_code == 202
    finally:
        app.dependency_overrides.clear()
        app.state.enqueue = None


# ── DELETE /v1/keys/{id} — revoke ────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_revoke_key_idempotent_and_blocks_ingest(session):
    org = Org(name="Revoke-Org")
    user = User(org=org, clerk_user_id="revoke_key_user", email="rv@test.example")
    proj = Project(org=org, name="proj-revoke")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.post(f"/v1/projects/{proj.id}/keys")
            assert r.status_code == 201
            full_key = r.json()["key"]
            key_id = r.json()["id"]

            # Revoke the key → 204.
            del_r = await c.delete(f"/v1/keys/{key_id}")
            assert del_r.status_code == 204

            # Revoke again → still 204 (idempotent).
            del_r2 = await c.delete(f"/v1/keys/{key_id}")
            assert del_r2.status_code == 204
    finally:
        app.dependency_overrides.clear()

    # Revoked key must fail ingest auth.
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = lambda rid: None
    try:
        run_payload = {
            "idempotency_key": "revoked-key-test",
            "baseline_ref": "origin/main",
            "candidate_ref": "feat/y",
            "tier": "hermetic",
            "config": {"agents": []},
            "attribution": None,
            "trajectories": [
                {"side": "baseline", "test_case_id": "tc2", "payload": {"events": []}}
            ],
        }
        async with _client() as c:
            r = await c.post(
                "/v1/runs",
                json=run_payload,
                headers={"Authorization": f"Bearer {full_key}"},
            )
        assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()
        app.state.enqueue = None


# ── Cross-org isolation ───────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_cross_org_mint_keys_404(session):
    """User in org_a cannot mint keys on org_b's project."""
    org_a = Org(name="IsoA-Mint")
    user_a = User(org=org_a, clerk_user_id="iso_mint_user_a", email="ia@test.example")
    org_b = Org(name="IsoB-Mint")
    proj_b = Project(org=org_b, name="proj-iso-b-mint")
    session.add_all([user_a, proj_b])
    await session.commit()

    _override(session, (user_a, org_a))
    try:
        async with _client() as c:
            r = await c.post(f"/v1/projects/{proj_b.id}/keys")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_cross_org_list_keys_404(session):
    """User in org_a cannot list keys on org_b's project."""
    org_a = Org(name="IsoA-List")
    user_a = User(org=org_a, clerk_user_id="iso_list_user_a", email="ila@test.example")
    org_b = Org(name="IsoB-List")
    proj_b = Project(org=org_b, name="proj-iso-b-list")
    session.add_all([user_a, proj_b])
    await session.commit()

    _override(session, (user_a, org_a))
    try:
        async with _client() as c:
            r = await c.get(f"/v1/projects/{proj_b.id}/keys")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_cross_org_revoke_key_404(session):
    """User in org_a cannot revoke a key belonging to org_b's project."""
    org_a = Org(name="IsoA-Revoke")
    user_a = User(org=org_a, clerk_user_id="iso_revoke_user_a", email="ira@test.example")
    org_b = Org(name="IsoB-Revoke")
    user_b = User(org=org_b, clerk_user_id="iso_revoke_user_b", email="irb@test.example")
    proj_b = Project(org=org_b, name="proj-iso-b-revoke")
    session.add_all([user_a, user_b, proj_b])
    await session.commit()

    # Mint a key as org_b.
    _override(session, (user_b, org_b))
    try:
        async with _client() as c:
            r = await c.post(f"/v1/projects/{proj_b.id}/keys")
            assert r.status_code == 201
            key_id = r.json()["id"]
    finally:
        app.dependency_overrides.clear()

    # Try to revoke it as org_a — expect 404.
    _override(session, (user_a, org_a))
    try:
        async with _client() as c:
            r = await c.delete(f"/v1/keys/{key_id}")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()

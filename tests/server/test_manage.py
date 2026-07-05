"""
Tests for the Tier-1 management API:
  GET  /v1/me
  POST /v1/projects
  PATCH /v1/projects/{id}
  DELETE /v1/projects/{id}
  POST /v1/projects/{id}/keys
  GET  /v1/projects/{id}/keys
  DELETE /v1/keys/{id}
  GET  /v1/projects/{id}/audit
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from server import security
from server.db import get_session
from server.deps import get_user_ctx
from server.main import app
from server.models import ApiKey, AuditLog, Org, Project, Run, User


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
            ids = [p["id"] for p in list_r.json()["items"]]
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
            # Active key must expose revoked_at=None (not a boolean "revoked" field).
            assert "revoked_at" in our
            assert our["revoked_at"] is None
            assert "revoked" not in our
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

            # List endpoint must show revoked_at as a non-None ISO string.
            list_r = await c.get(f"/v1/projects/{proj.id}/keys")
            assert list_r.status_code == 200
            revoked_key = next((k for k in list_r.json() if k["id"] == key_id), None)
            assert revoked_key is not None
            assert revoked_key["revoked_at"] is not None
            assert isinstance(revoked_key["revoked_at"], str)
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


# ── PATCH /v1/projects/{id} — rename ─────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_rename_project(session):
    org = Org(name="Rename-Org")
    user = User(org=org, clerk_user_id="rename_user", email="rn@test.example")
    proj = Project(org=org, name="old-name")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.patch(f"/v1/projects/{proj.id}", json={"name": "new-name"})
            assert r.status_code == 200
            body = r.json()
            assert body["id"] == str(proj.id)
            assert body["name"] == "new-name"

            # Audit row written.
            rows = (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "project.renamed")
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].actor == user.clerk_user_id
            assert rows[0].target_type == "project"
            assert rows[0].target_id == str(proj.id)
            assert rows[0].org_id == org.id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_rename_project_empty_name_422(session):
    org = Org(name="RenameEmpty-Org")
    user = User(org=org, clerk_user_id="rename_empty_user", email="rne@test.example")
    proj = Project(org=org, name="old-name-2")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.patch(f"/v1/projects/{proj.id}", json={"name": "   "})
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_rename_project_cross_org_404(session):
    org_a = Org(name="RenameIsoA")
    user_a = User(org=org_a, clerk_user_id="rename_iso_a", email="ria@test.example")
    org_b = Org(name="RenameIsoB")
    proj_b = Project(org=org_b, name="proj-iso-b-rename")
    session.add_all([user_a, proj_b])
    await session.commit()

    _override(session, (user_a, org_a))
    try:
        async with _client() as c:
            r = await c.patch(f"/v1/projects/{proj_b.id}", json={"name": "hijacked"})
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ── DELETE /v1/projects/{id} — cascade delete ────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_project_cascades(session):
    org = Org(name="DeleteProj-Org")
    user = User(org=org, clerk_user_id="delete_proj_user", email="dp@test.example")
    proj = Project(org=org, name="proj-to-delete")
    session.add_all([user, proj])
    await session.commit()
    proj_id = proj.id

    _override(session, (user, org))
    try:
        async with _client() as c:
            # Mint a key so we can prove cascade deletes it too.
            kr = await c.post(f"/v1/projects/{proj_id}/keys")
            assert kr.status_code == 201

            r = await c.delete(f"/v1/projects/{proj_id}")
            assert r.status_code == 204

            # Project gone.
            gr = await c.get("/v1/projects")
            assert gr.status_code == 200
            ids = [p["id"] for p in gr.json()["items"]]
            assert str(proj_id) not in ids
    finally:
        app.dependency_overrides.clear()

    # Cascade: no orphaned ApiKey rows remain.
    remaining_keys = (
        await session.execute(select(ApiKey).where(ApiKey.project_id == proj_id))
    ).scalars().all()
    assert remaining_keys == []

    # Audit row for delete.
    rows = (
        await session.execute(
            select(AuditLog).where(AuditLog.action == "project.deleted")
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_id == str(proj_id)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_project_cross_org_404(session):
    org_a = Org(name="DeleteIsoA")
    user_a = User(org=org_a, clerk_user_id="delete_iso_a", email="dia@test.example")
    org_b = Org(name="DeleteIsoB")
    proj_b = Project(org=org_b, name="proj-iso-b-delete")
    session.add_all([user_a, proj_b])
    await session.commit()

    _override(session, (user_a, org_a))
    try:
        async with _client() as c:
            r = await c.delete(f"/v1/projects/{proj_b.id}")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ── DELETE /v1/runs/{id} ──────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_run(session):
    org = Org(name="DeleteRun-Org")
    user = User(org=org, clerk_user_id="delete_run_user", email="dr@test.example")
    proj = Project(org=org, name="proj-delete-run")
    run = Run(
        project=proj,
        idempotency_key="del-run-1",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        config={},
        status="done",
        verdict="pass",
    )
    session.add_all([user, run])
    await session.commit()
    run_id = run.id

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.delete(f"/v1/runs/{run_id}")
            assert r.status_code == 204

            gr = await c.get(f"/v1/runs/{run_id}")
            assert gr.status_code == 404
    finally:
        app.dependency_overrides.clear()

    rows = (
        await session.execute(
            select(AuditLog).where(AuditLog.action == "run.deleted")
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_id == str(run_id)
    assert rows[0].target_type == "run"


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_run_cross_org_404(session):
    org_a = Org(name="DeleteRunIsoA")
    user_a = User(org=org_a, clerk_user_id="delete_run_iso_a", email="dria@test.example")
    org_b = Org(name="DeleteRunIsoB")
    proj_b = Project(org=org_b, name="proj-iso-b-run")
    run_b = Run(
        project=proj_b,
        idempotency_key="del-run-iso",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        config={},
        status="done",
        verdict="pass",
    )
    session.add_all([user_a, run_b])
    await session.commit()

    _override(session, (user_a, org_a))
    try:
        async with _client() as c:
            r = await c.delete(f"/v1/runs/{run_b.id}")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ── Named API keys ────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_mint_key_with_name(session):
    org = Org(name="NamedKey-Org")
    user = User(org=org, clerk_user_id="named_key_user", email="nk@test.example")
    proj = Project(org=org, name="proj-named-key")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.post(f"/v1/projects/{proj.id}/keys", json={"name": "CI key"})
            assert r.status_code == 201
            assert r.json()["name"] == "CI key"

            lr = await c.get(f"/v1/projects/{proj.id}/keys")
            assert lr.status_code == 200
            our = next(k for k in lr.json() if k["id"] == r.json()["id"])
            assert our["name"] == "CI key"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_mint_key_without_name_defaults_null(session):
    org = Org(name="UnnamedKey-Org")
    user = User(org=org, clerk_user_id="unnamed_key_user", email="uk@test.example")
    proj = Project(org=org, name="proj-unnamed-key")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.post(f"/v1/projects/{proj.id}/keys", json={"name": None})
            assert r.status_code == 201
            assert r.json()["name"] is None

            # Also works with no body at all.
            r2 = await c.post(f"/v1/projects/{proj.id}/keys")
            assert r2.status_code == 201
            assert r2.json()["name"] is None
    finally:
        app.dependency_overrides.clear()


# ── Audit rows for key mint/revoke ────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_key_mint_and_revoke_write_audit(session):
    org = Org(name="KeyAudit-Org")
    user = User(org=org, clerk_user_id="key_audit_user", email="ka@test.example")
    proj = Project(org=org, name="proj-key-audit")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.post(f"/v1/projects/{proj.id}/keys", json={"name": "audit-key"})
            key_id = r.json()["id"]

            mint_rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "key.minted",
                        AuditLog.target_id == key_id,
                    )
                )
            ).scalars().all()
            assert len(mint_rows) == 1
            assert mint_rows[0].actor == user.clerk_user_id
            assert mint_rows[0].target_type == "api_key"
            assert mint_rows[0].target_id == key_id

            dr = await c.delete(f"/v1/keys/{key_id}")
            assert dr.status_code == 204

            revoke_rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "key.revoked",
                        AuditLog.target_id == key_id,
                    )
                )
            ).scalars().all()
            assert len(revoke_rows) == 1
            assert revoke_rows[0].actor == user.clerk_user_id
            assert revoke_rows[0].target_id == key_id

            # Revoking again is idempotent and must NOT write a second audit row.
            dr2 = await c.delete(f"/v1/keys/{key_id}")
            assert dr2.status_code == 204
            revoke_rows_2 = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "key.revoked",
                        AuditLog.target_id == key_id,
                    )
                )
            ).scalars().all()
            assert len(revoke_rows_2) == 1
    finally:
        app.dependency_overrides.clear()


# ── project.created audit row ─────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_create_project_writes_audit(session):
    org = Org(name="CreateAudit-Org")
    user = User(org=org, clerk_user_id="create_audit_user", email="ca@test.example")
    session.add(user)
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            r = await c.post("/v1/projects", json={"name": "audited-project"})
            assert r.status_code == 201
            proj_id = r.json()["id"]

            rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "project.created",
                        AuditLog.target_id == proj_id,
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].actor == user.clerk_user_id
            assert rows[0].target_type == "project"
            assert rows[0].target_id == proj_id
            assert rows[0].org_id == org.id
    finally:
        app.dependency_overrides.clear()


# ── GET /v1/projects/{id}/audit ───────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_endpoint_pagination(session):
    org = Org(name="AuditPage-Org")
    user = User(org=org, clerk_user_id="audit_page_user", email="ap@test.example")
    proj = Project(org=org, name="proj-audit-page")
    session.add_all([user, proj])
    await session.commit()

    _override(session, (user, org))
    try:
        async with _client() as c:
            # Rename 3 times to generate 3 audit rows (+ project.created = 0 since
            # project already exists here, so exactly 3 rows expected).
            for i in range(3):
                r = await c.patch(f"/v1/projects/{proj.id}", json={"name": f"name-{i}"})
                assert r.status_code == 200

            ar = await c.get(f"/v1/projects/{proj.id}/audit?limit=2&offset=0")
            assert ar.status_code == 200
            body = ar.json()
            assert body["total"] == 3
            assert len(body["items"]) == 2
            item = body["items"][0]
            assert set(["id", "actor", "action", "target_type", "target_id", "meta", "created_at"]) <= set(item.keys())

            ar2 = await c.get(f"/v1/projects/{proj.id}/audit?limit=2&offset=2")
            assert ar2.status_code == 200
            assert len(ar2.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_endpoint_cross_org_404(session):
    org_a = Org(name="AuditIsoA")
    user_a = User(org=org_a, clerk_user_id="audit_iso_a", email="aia@test.example")
    org_b = Org(name="AuditIsoB")
    proj_b = Project(org=org_b, name="proj-iso-b-audit")
    session.add_all([user_a, proj_b])
    await session.commit()

    _override(session, (user_a, org_a))
    try:
        async with _client() as c:
            r = await c.get(f"/v1/projects/{proj_b.id}/audit")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()

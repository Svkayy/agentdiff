"""Tests for usage metering + monthly quotas (Task 12)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from server import security
from server.db import get_session
from server.main import app
from server.models import ApiKey, Org, Project, UsageCounter
from server.usage import check_quota, current_period, increment_usage


@pytest.fixture(autouse=True)
def _reset_app_state():
    yield
    app.dependency_overrides.clear()
    app.state.enqueue = None
    app.state.redis_pool = None


@pytest_asyncio.fixture(loop_scope="session")
async def _free_project_and_key(session):
    org = Org(name="FreeOrg", plan="free")
    project = Project(org=org, name="free-project")
    full, prefix, kh = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=kh, prefix=prefix))
    await session.commit()
    return full, org, project


def _run_payload(**overrides):
    p = {
        "idempotency_key": str(uuid.uuid4()),
        "baseline_ref": "origin/main",
        "candidate_ref": "working",
        "tier": "hermetic",
        "config": {},
        "attribution": None,
        "trajectories": [
            {"side": "baseline", "test_case_id": "tc1", "payload": {}},
            {"side": "candidate", "test_case_id": "tc1", "payload": {}},
        ],
    }
    p.update(overrides)
    return p


# ── increment_usage UPSERT ─────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_increment_usage_upsert(session):
    org = Org(name="MeterOrg", plan="free")
    session.add(org)
    await session.commit()

    await increment_usage(session, org.id, runs=1, trajectories=10)
    await increment_usage(session, org.id, runs=2, trajectories=5)

    counter = (
        await session.execute(
            select(UsageCounter).where(
                UsageCounter.org_id == org.id,
                UsageCounter.period == current_period(),
            )
        )
    ).scalar_one()
    assert counter.runs == 3
    assert counter.trajectories == 15


# ── check_quota math ────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_check_quota_free_under_limit(session):
    org = Org(name="UnderOrg", plan="free")
    session.add(org)
    await session.commit()
    await increment_usage(session, org.id, runs=3, trajectories=100)

    status = await check_quota(session, org)
    assert status.exceeded is False
    assert status.runs_used == 3
    assert status.runs_limit == 500
    assert status.trajectories_limit == 50000


@pytest.mark.asyncio(loop_scope="session")
async def test_check_quota_unlimited_plan_no_cap(session):
    org = Org(name="ProOrg", plan="pro")
    session.add(org)
    await session.commit()
    await increment_usage(session, org.id, runs=99999, trajectories=99999999)

    status = await check_quota(session, org)
    assert status.exceeded is False
    assert status.runs_limit is None
    assert status.trajectories_limit is None


@pytest.mark.asyncio(loop_scope="session")
async def test_check_quota_free_over_runs_limit(session):
    org = Org(name="OverOrg", plan="free")
    session.add(org)
    await session.commit()
    # Push runs to the cap.
    await increment_usage(session, org.id, runs=500, trajectories=0)

    status = await check_quota(session, org)
    assert status.exceeded is True
    assert status.limiting_metric == "runs"
    assert status.used == 500
    assert status.limit == 500


# ── Ingest 429 + headers + counter row ─────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_ingest_quota_exceeded_429(session, _free_project_and_key):
    full, org, _project = _free_project_and_key
    # Fill the org's run quota to the cap.
    await increment_usage(session, org.id, runs=500, trajectories=0)

    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/runs",
            json=_run_payload(),
            headers={"Authorization": f"Bearer {full}"},
        )
    assert r.status_code == 429
    body = r.json()["detail"]
    assert body["detail"] == "monthly quota exceeded"
    assert body["plan"] == "free"
    assert body["used"] == 500
    assert body["limit"] == 500
    assert r.headers["X-Quota-Limit"] == "500"
    assert r.headers["X-Quota-Remaining"] == "0"


@pytest.mark.asyncio(loop_scope="session")
async def test_ingest_success_increments_usage(session, _free_project_and_key):
    full, org, _project = _free_project_and_key

    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/runs",
            json=_run_payload(idempotency_key="usage-inc-1"),
            headers={"Authorization": f"Bearer {full}"},
        )
    assert r.status_code == 202

    counter = (
        await session.execute(
            select(UsageCounter).where(
                UsageCounter.org_id == org.id,
                UsageCounter.period == current_period(),
            )
        )
    ).scalar_one()
    assert counter.runs == 1
    assert counter.trajectories == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_ingest_idempotent_replay_no_double_count(session, _free_project_and_key):
    full, org, _project = _free_project_and_key

    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None

    key = "usage-idem-1"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        await c.post(
            "/v1/runs",
            json=_run_payload(idempotency_key=key),
            headers={"Authorization": f"Bearer {full}"},
        )
        await c.post(
            "/v1/runs",
            json=_run_payload(idempotency_key=key),
            headers={"Authorization": f"Bearer {full}"},
        )

    counter = (
        await session.execute(
            select(UsageCounter).where(
                UsageCounter.org_id == org.id,
                UsageCounter.period == current_period(),
            )
        )
    ).scalar_one()
    assert counter.runs == 1, "idempotent replay must not double-count usage"


# ── GET /v1/usage math ──────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_usage_endpoint_math(session):
    org = Org(clerk_org_id="clerk-usage-org", name="UsageEP", plan="free")
    from server.models import User

    user = User(org=org, clerk_user_id="clerk-usage-user", email="u@x.com")
    session.add_all([org, user])
    await session.commit()
    await increment_usage(session, org.id, runs=7, trajectories=1234)

    from server.deps import get_user_ctx

    async def _fake_ctx():
        return user, org

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = _fake_ctx

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/v1/usage", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    data = r.json()
    assert data["plan"] == "free"
    assert data["period"] == current_period()
    assert data["runs_used"] == 7
    assert data["runs_limit"] == 500
    assert data["trajectories_used"] == 1234
    assert data["trajectories_limit"] == 50000


@pytest.mark.asyncio(loop_scope="session")
async def test_usage_endpoint_unlimited_null_limits(session):
    org = Org(clerk_org_id="clerk-usage-pro", name="UsageProEP", plan="unlimited")
    from server.models import User

    user = User(org=org, clerk_user_id="clerk-usage-pro-user", email="p@x.com")
    session.add_all([org, user])
    await session.commit()

    from server.deps import get_user_ctx

    async def _fake_ctx():
        return user, org

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = _fake_ctx

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/v1/usage", headers={"Authorization": "Bearer x"})
    data = r.json()
    assert data["runs_limit"] is None
    assert data["trajectories_limit"] is None

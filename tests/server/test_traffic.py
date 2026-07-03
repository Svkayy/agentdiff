"""Tests for POST /v1/traffic live trajectory ingest endpoint."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from server import security
from server.db import get_session
from server.main import app
from server.models import ApiKey, LiveTrajectory, Org, Project


@pytest.fixture(autouse=True)
def _reset_app_state():
    yield
    app.dependency_overrides.clear()
    app.state.enqueue = None
    app.state.redis_pool = None


@pytest_asyncio.fixture(loop_scope="session")
async def traffic_api_key(session):
    org = Org(name="TrafficOrg")
    project = Project(org=org, name="traffic-proj")
    full, prefix, kh = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=kh, prefix=prefix))
    await session.commit()
    return full, project.id


@pytest.mark.asyncio(loop_scope="session")
async def test_traffic_post_stores_rows_returns_202(session, traffic_api_key):
    """Authenticated POST stores rows and returns 202 {accepted: N}."""
    full, project_id = traffic_api_key
    app.dependency_overrides[get_session] = lambda: session

    payloads = [{"events": [], "test_case_id": f"tc{i}"} for i in range(5)]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/traffic",
            json={"trajectories": payloads},
            headers={"Authorization": f"Bearer {full}"},
        )

    assert r.status_code == 202, r.text
    body = r.json()
    assert body["accepted"] == 5

    # Verify rows in DB
    count = (
        await session.execute(
            select(func.count()).select_from(LiveTrajectory).where(
                LiveTrajectory.project_id == project_id
            )
        )
    ).scalar_one()
    assert count >= 5


@pytest.mark.asyncio(loop_scope="session")
async def test_traffic_bad_key_returns_401(session):
    """Invalid API key returns 401."""
    app.dependency_overrides[get_session] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/traffic",
            json={"trajectories": [{"events": []}]},
            headers={"Authorization": "Bearer adk_invalid_key"},
        )

    assert r.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_traffic_batch_over_1000_returns_422(session, traffic_api_key):
    """Batch with more than 1000 trajectories returns 422."""
    full, _ = traffic_api_key
    app.dependency_overrides[get_session] = lambda: session

    payloads = [{"events": []} for _ in range(1001)]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/traffic",
            json={"trajectories": payloads},
            headers={"Authorization": f"Bearer {full}"},
        )

    assert r.status_code == 422

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from server.main import app
from server.db import get_session
from server import security
from server.models import Org, Project, ApiKey


# Fix 1: autouse fixture isolates app state across tests
@pytest.fixture(autouse=True)
def _reset_app_state():
    yield
    app.dependency_overrides.clear()
    app.state.enqueue = None


@pytest.fixture
def payload():
    return {
        "idempotency_key": "idem-1",
        "baseline_ref": "origin/main",
        "candidate_ref": "working",
        "tier": "hermetic",
        "config": {"agents": []},
        "attribution": None,
        "trajectories": [{"side": "baseline", "test_case_id": "tc1", "payload": {"events": []}}],
    }


@pytest_asyncio.fixture(loop_scope="session")
async def api_key(session):
    org = Org(name="Acme")
    project = Project(org=org, name="p")
    full, prefix, kh = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=kh, prefix=prefix))
    await session.commit()
    return full, project.id


@pytest.mark.asyncio(loop_scope="session")
async def test_post_run_returns_202_and_persists(session, api_key, payload):
    full, project_id = api_key
    app.dependency_overrides[get_session] = lambda: session
    enqueued = []
    app.state.enqueue = lambda rid: enqueued.append(rid)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/v1/runs", json=payload, headers={"Authorization": f"Bearer {full}"})
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    # Fix 3: assert run_id is a valid UUID
    uuid.UUID(r.json()["run_id"])
    assert enqueued == [r.json()["run_id"]]


@pytest.mark.asyncio(loop_scope="session")
async def test_duplicate_idempotency_key_returns_same_run(session, api_key):
    full, _ = api_key
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = lambda rid: None
    # Fix 2: use a distinct idempotency_key not shared with other tests
    dup_payload = {
        "idempotency_key": "idem-dup",
        "baseline_ref": "origin/main",
        "candidate_ref": "working",
        "tier": "hermetic",
        "config": {"agents": []},
        "attribution": None,
        "trajectories": [{"side": "baseline", "test_case_id": "tc1", "payload": {"events": []}}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r1 = await c.post("/v1/runs", json=dup_payload, headers={"Authorization": f"Bearer {full}"})
        r2 = await c.post("/v1/runs", json=dup_payload, headers={"Authorization": f"Bearer {full}"})
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["run_id"] == r2.json()["run_id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_bad_key_rejected(session, payload):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/v1/runs", json=payload, headers={"Authorization": "Bearer adk_no"})
    assert r.status_code == 401

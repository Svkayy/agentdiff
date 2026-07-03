import pytest
from httpx import ASGITransport, AsyncClient
from server.main import app
from server.db import get_session
from server.deps import get_user_ctx
from server.models import Org, Project, Run, User


@pytest.mark.asyncio(loop_scope="session")
async def test_cannot_read_other_orgs_run(session):
    orgA = Org(name="A")
    userA = User(org=orgA, clerk_user_id="ua_iso", email="a@a")
    orgB = Org(name="B")
    pB = Project(org=orgB, name="pb")
    runB = Run(
        project=pB,
        idempotency_key="b",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="fail",
    )
    session.add_all([userA, runB])
    await session.commit()

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = lambda: (userA, orgA)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(f"/v1/runs/{runB.id}")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()

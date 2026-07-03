import pytest
from httpx import ASGITransport, AsyncClient
from server.main import app
from server.db import get_session
from server.deps import get_user_ctx
from server.models import Org, Project, Run


async def _client(session, user_ctx):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = lambda: user_ctx
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio(loop_scope="session")
async def test_lists_only_own_org_runs(session):
    orgA = Org(name="A")
    pA = Project(org=orgA, name="pa")
    runA = Run(
        project=pA,
        idempotency_key="a",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="pass",
    )
    orgB = Org(name="B")
    pB = Project(org=orgB, name="pb")
    session.add_all([runA, pB])
    await session.commit()

    from server.models import User

    userA = User(org_id=orgA.id, clerk_user_id="ua_reads", email="a@a")
    session.add(userA)
    await session.commit()

    try:
        async with await _client(session, (userA, orgA)) as c:
            r = await c.get(f"/v1/projects/{pA.id}/runs")
            assert r.status_code == 200
            assert len(r.json()) == 1
            # Cross-org project -> 404
            r2 = await c.get(f"/v1/projects/{pB.id}/runs")
            assert r2.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_projects_own_org(session):
    orgC = Org(name="C")
    pC = Project(org=orgC, name="pc")
    session.add(pC)
    await session.commit()

    from server.models import User

    userC = User(org_id=orgC.id, clerk_user_id="uc_reads", email="c@c")
    session.add(userC)
    await session.commit()

    try:
        async with await _client(session, (userC, orgC)) as c:
            r = await c.get("/v1/projects")
            assert r.status_code == 200
            ids = [p["id"] for p in r.json()]
            assert str(pC.id) in ids
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_get_run_with_findings(session):
    orgD = Org(name="D")
    pD = Project(org=orgD, name="pd")
    runD = Run(
        project=pD,
        idempotency_key="d",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="pass",
    )
    session.add(runD)
    await session.commit()

    from server.models import User

    userD = User(org_id=orgD.id, clerk_user_id="ud_reads", email="d@d")
    session.add(userD)
    await session.commit()

    try:
        async with await _client(session, (userD, orgD)) as c:
            r = await c.get(f"/v1/runs/{runD.id}")
            assert r.status_code == 200
            body = r.json()
            assert body["id"] == str(runD.id)
            assert "findings" in body
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_set_slack_config(session):
    orgE = Org(name="E")
    pE = Project(org=orgE, name="pe")
    session.add(pE)
    await session.commit()

    from server.models import User

    userE = User(org_id=orgE.id, clerk_user_id="ue_reads", email="e@e")
    session.add(userE)
    await session.commit()

    try:
        async with await _client(session, (userE, orgE)) as c:
            r = await c.put(
                f"/v1/projects/{pE.id}/slack",
                json={"channel_id": "C123", "bot_token": "xoxb-secret"},
            )
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()

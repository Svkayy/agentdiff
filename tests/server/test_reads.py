from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory
from server.main import app
from server.db import get_session
from server.deps import get_user_ctx
from server.models import Finding, Org, Project, Run, Trajectory, User


async def _client(session, user_ctx):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = lambda: user_ctx
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _engine_payload(tc_id: str, tag: str, fires: bool) -> dict:
    events = []
    if fires:
        events.append(
            LLMRequestEvent(
                call_id=uuid4(),
                canonical=CanonicalLLMCall(provider="anthropic"),
                captured_by="sdk_shim",
                callsite=CallSite(file="agents.py", function="fact_checker", line=10),
                inferred_agent="Fact Checker",
            )
        )
    return EngineTrajectory(
        test_case_id=tc_id,
        version_tag=tag,
        input={},
        events=events,
    ).model_dump(mode="json")


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

    userA = User(org_id=orgA.id, clerk_user_id="ua_reads", email="a@a")
    session.add(userA)
    await session.commit()

    try:
        async with await _client(session, (userA, orgA)) as c:
            r = await c.get(f"/v1/projects/{pA.id}/runs")
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1
            assert len(body["items"]) == 1
            run_item = body["items"][0]
            assert "kind" in run_item
            assert "created_at" in run_item
            # Cross-org project -> 404
            r2 = await c.get(f"/v1/projects/{pB.id}/runs")
            assert r2.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_projects_own_org(session):
    orgC = Org(name="C")
    pC = Project(org=orgC, name="pc")
    # Seed a project in a DIFFERENT org — it must NOT appear in orgC's listing.
    orgX = Org(name="X")
    pX = Project(org=orgX, name="px")
    session.add_all([pC, pX])
    await session.commit()

    userC = User(org_id=orgC.id, clerk_user_id="uc_reads", email="c@c")
    session.add(userC)
    await session.commit()

    try:
        async with await _client(session, (userC, orgC)) as c:
            r = await c.get("/v1/projects")
            assert r.status_code == 200
            body = r.json()
            ids = [p["id"] for p in body["items"]]
            assert str(pC.id) in ids
            assert str(pX.id) not in ids
            assert body["total"] == len(body["items"])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_projects_search_q(session):
    org = Org(name=f"search-org-{uuid4()}")
    p_match = Project(org=org, name="alpha-widget")
    p_other = Project(org=org, name="beta-gadget")
    session.add_all([p_match, p_other])
    await session.commit()

    user = User(org=org, clerk_user_id=f"search-user-{uuid4()}", email="search@s.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get("/v1/projects?q=alpha")
            assert r.status_code == 200
            body = r.json()
            ids = [p["id"] for p in body["items"]]
            assert str(p_match.id) in ids
            assert str(p_other.id) not in ids
            assert body["total"] == 1
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
            assert "kind" in body
            assert "created_at" in body
            assert "baseline_ref" in body
            assert "candidate_ref" in body
            assert "config" in body
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_set_slack_config(session):
    orgE = Org(name="E")
    pE = Project(org=orgE, name="pe")
    session.add(pE)
    await session.commit()

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


@pytest.mark.asyncio(loop_scope="session")
async def test_cross_tenant_slack_write_rejected(session):
    """PUT /v1/projects/{other_org_project}/slack must return 404 via _own_project guard."""
    orgF = Org(name="F")
    pF = Project(org=orgF, name="pf")
    orgG = Org(name="G")
    userG = User(org=orgG, clerk_user_id="ug_reads", email="g@g")
    session.add_all([pF, userG])
    await session.commit()

    try:
        async with await _client(session, (userG, orgG)) as c:
            r = await c.put(
                f"/v1/projects/{pF.id}/slack",
                json={"channel_id": "C1", "bot_token": "xoxb-x"},
            )
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ── B1: Stats endpoint ────────────────────────────────────────────────────────


def _now():
    return datetime.now(timezone.utc)


def _at(minutes_ago: float) -> datetime:
    return _now() - timedelta(minutes=minutes_ago)


@pytest.mark.asyncio(loop_scope="session")
async def test_stats_endpoint_mixed_runs(session):
    """Stats endpoint aggregates correctly over mixed runs."""
    orgS = Org(name=f"stats-org-{uuid4()}")
    pS = Project(org=orgS, name=f"stats-proj-{uuid4()}")
    session.add_all([orgS, pS])

    # Seed: 3 CI pass, 2 CI fail, 1 drift (last 7d)
    runs = [
        Run(project=pS, idempotency_key=f"s1-{uuid4()}", baseline_ref="m", candidate_ref="w",
            tier="hermetic", kind="ci", config={}, status="done", verdict="pass",
            created_at=_at(60 * 24 * 10)),
        Run(project=pS, idempotency_key=f"s2-{uuid4()}", baseline_ref="m", candidate_ref="w",
            tier="hermetic", kind="ci", config={}, status="done", verdict="pass",
            created_at=_at(60 * 24 * 5)),
        Run(project=pS, idempotency_key=f"s3-{uuid4()}", baseline_ref="m", candidate_ref="w",
            tier="hermetic", kind="ci", config={}, status="done", verdict="fail",
            created_at=_at(60 * 24 * 2)),
        Run(project=pS, idempotency_key=f"s4-{uuid4()}", baseline_ref="m", candidate_ref="w",
            tier="hermetic", kind="ci", config={}, status="done", verdict="fail",
            created_at=_at(60)),
        Run(project=pS, idempotency_key=f"s5-{uuid4()}", baseline_ref="m", candidate_ref="w",
            tier="live", kind="drift", config={}, status="done", verdict="warn",
            created_at=_at(30)),
    ]
    session.add_all(runs)
    await session.commit()

    userS = User(org=orgS, clerk_user_id=f"us-stats-{uuid4()}", email="s@s.com")
    session.add(userS)
    await session.commit()

    try:
        async with await _client(session, (userS, orgS)) as c:
            r = await c.get(f"/v1/projects/{pS.id}/stats")
            assert r.status_code == 200
            body = r.json()

            # 5 done runs total (3 ci + 1 ci fail + 1 drift)
            assert body["total_runs"] == 5

            # pass_rate_30: 2 pass out of 4 CI runs = 0.5
            assert body["pass_rate_30"] == pytest.approx(0.5)

            # failing_streak: most-recent CI is fail (s4), before that fail (s3) → streak=2
            assert body["failing_streak"] == 2

            # last_failure_at should be set
            assert body["last_failure_at"] is not None

            # drift_runs_7d: 1 drift run in last 7 days
            assert body["drift_runs_7d"] == 1

            # recent: up to 20 items, newest first
            assert len(body["recent"]) <= 20
            assert body["recent"][0]["kind"] in {"ci", "drift"}

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_stats_endpoint_cross_org_404(session):
    """Stats endpoint returns 404 for cross-org project access."""
    orgA = Org(name=f"stats-orgA-{uuid4()}")
    pA = Project(org=orgA, name=f"stats-pA-{uuid4()}")
    orgB = Org(name=f"stats-orgB-{uuid4()}")
    userB = User(org=orgB, clerk_user_id=f"ub-stats-{uuid4()}", email="b@b.com")
    session.add_all([pA, userB])
    await session.commit()

    try:
        async with await _client(session, (userB, orgB)) as c:
            r = await c.get(f"/v1/projects/{pA.id}/stats")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_stats_pass_rate_null_when_no_ci_runs(session):
    """pass_rate_30 is null when there are no completed CI runs."""
    orgN = Org(name=f"stats-no-ci-org-{uuid4()}")
    pN = Project(org=orgN, name=f"stats-no-ci-{uuid4()}")
    session.add_all([orgN, pN])
    await session.commit()

    userN = User(org=orgN, clerk_user_id=f"un-stats-{uuid4()}", email="n@n.com")
    session.add(userN)
    await session.commit()

    try:
        async with await _client(session, (userN, orgN)) as c:
            r = await c.get(f"/v1/projects/{pN.id}/stats")
            assert r.status_code == 200
            body = r.json()
            assert body["pass_rate_30"] is None
            assert body["failing_streak"] == 0
            assert body["total_runs"] == 0
    finally:
        app.dependency_overrides.clear()


# ── B3(i): Run sample counts ──────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_get_run_sample_counts(session):
    """GET /v1/runs/{id} returns baseline_samples and candidate_samples."""
    orgSC = Org(name=f"sc-org-{uuid4()}")
    pSC = Project(org=orgSC, name=f"sc-proj-{uuid4()}")
    runSC = Run(
        project=pSC,
        idempotency_key=f"sc-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config={},
        status="done",
        verdict="pass",
    )
    session.add(runSC)
    await session.flush()

    # 5 baseline, 3 candidate
    for _ in range(5):
        session.add(Trajectory(run_id=runSC.id, side="baseline", test_case_id="tc1", payload={}))
    for _ in range(3):
        session.add(Trajectory(run_id=runSC.id, side="candidate", test_case_id="tc1", payload={}))
    await session.commit()

    userSC = User(org=orgSC, clerk_user_id=f"usc-{uuid4()}", email="sc@sc.com")
    session.add(userSC)
    await session.commit()

    try:
        async with await _client(session, (userSC, orgSC)) as c:
            r = await c.get(f"/v1/runs/{runSC.id}")
            assert r.status_code == 200
            body = r.json()
            assert body["baseline_samples"] == 5
            assert body["candidate_samples"] == 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_get_run_findings_include_hunk_and_explanation(session):
    """GET /v1/runs/{id} findings include cause_hunk and explanation."""
    orgFH = Org(name=f"fh-org-{uuid4()}")
    pFH = Project(org=orgFH, name=f"fh-proj-{uuid4()}")
    runFH = Run(
        project=pFH,
        idempotency_key=f"fh-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config={},
        status="done",
        verdict="fail",
    )
    session.add(runFH)
    await session.flush()

    session.add(Finding(
        run_id=runFH.id,
        test_case_id="tc1",
        title="Test finding",
        verdict="fail",
        metric="invocation_rate",
        impact_summary="something changed",
        cause_path="a.py",
        cause_rule="code_change",
        cause_hunk="@@ -1,3 +1,3 @@\n-old line\n+new line",
        explanation="The agent was removed.",
    ))
    await session.commit()

    userFH = User(org=orgFH, clerk_user_id=f"ufh-{uuid4()}", email="fh@fh.com")
    session.add(userFH)
    await session.commit()

    try:
        async with await _client(session, (userFH, orgFH)) as c:
            r = await c.get(f"/v1/runs/{runFH.id}")
            assert r.status_code == 200
            body = r.json()
            assert len(body["findings"]) == 1
            f = body["findings"][0]
            assert f["cause_hunk"] == "@@ -1,3 +1,3 @@\n-old line\n+new line"
            assert f["explanation"] == "The agent was removed."
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_get_run_returns_processed_graph_and_comparison(session):
    """Run detail returns engine-computed graph/comparison, not guessed UI data."""
    org = Org(name=f"graph-org-{uuid4()}")
    project = Project(org=org, name=f"graph-proj-{uuid4()}")
    structure = StructureDoc(
        agents=[
            AgentEntry(
                name="Fact Checker",
                function="fact_checker",
                file="agents.py",
                line=10,
            )
        ]
    )
    run = Run(
        project=project,
        idempotency_key=f"graph-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config=structure.model_dump(),
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.flush()

    for _ in range(8):
        session.add(
            Trajectory(
                run_id=run.id,
                side="baseline",
                test_case_id="tc1",
                payload=_engine_payload("tc1", "baseline", True),
            )
        )
    for _ in range(8):
        session.add(
            Trajectory(
                run_id=run.id,
                side="candidate",
                test_case_id="tc1",
                payload=_engine_payload("tc1", "candidate", False),
            )
        )
    await session.commit()

    user = User(org=org, clerk_user_id=f"ugraph-{uuid4()}", email="graph@g.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/runs/{run.id}")
            assert r.status_code == 200
            body = r.json()
            node = next(n for n in body["graph"]["nodes"] if n["id"] == "agent:Fact Checker")
            assert node["stopped"] is True
            delta = body["comparison"]["test_case_comparisons"][0]["agent_invocation_deltas"][0]
            assert delta["stats"]["test"] == "two_proportion_z"
            assert delta["stats"]["confidence_interval"] is not None
    finally:
        app.dependency_overrides.clear()


# ── Task 10: run payload endpoint ─────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_get_run_payload_returns_stored_payload(session):
    """GET /v1/runs/{id}/payload returns the stored report_payload dict verbatim."""
    org = Org(name=f"payload-reads-org-{uuid4()}")
    project = Project(org=org, name=f"payload-reads-proj-{uuid4()}")
    stored_payload = {
        "meta": {"baseline_ref": "main", "candidate_ref": "feat"},
        "comparison": {"overall_verdict": "pass", "test_case_comparisons": []},
        "warnings": [],
        "outputEvals": [],
        "attribution": None,
        "trajectories": {"baseline": [], "candidate": []},
    }
    run = Run(
        project=project,
        idempotency_key=f"payload-reads-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        config={},
        status="done",
        verdict="pass",
        report_payload=stored_payload,
    )
    session.add(run)
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-payload-reads-{uuid4()}", email="pr@pr.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/runs/{run.id}/payload")
            assert r.status_code == 200
            assert r.json() == stored_payload
    finally:
        app.dependency_overrides.clear()


# ── Task 11: runs pagination, verdict filter, search ──────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_list_runs_pagination_totals(session):
    org = Org(name=f"runs-page-org-{uuid4()}")
    project = Project(org=org, name=f"runs-page-proj-{uuid4()}")
    session.add(project)
    await session.commit()

    for i in range(5):
        session.add(
            Run(
                project=project,
                idempotency_key=f"page-{i}-{uuid4()}",
                baseline_ref="main",
                candidate_ref="feat",
                tier="hermetic",
                config={},
                status="done",
                verdict="pass",
            )
        )
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-runs-page-{uuid4()}", email="rp@rp.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/projects/{project.id}/runs?limit=2&offset=0")
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 5
            assert len(body["items"]) == 2

            r2 = await c.get(f"/v1/projects/{project.id}/runs?limit=2&offset=4")
            assert r2.status_code == 200
            assert len(r2.json()["items"]) == 1
            assert r2.json()["total"] == 5
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_runs_limit_clamped_to_200(session):
    org = Org(name=f"runs-clamp-org-{uuid4()}")
    project = Project(org=org, name=f"runs-clamp-proj-{uuid4()}")
    session.add(project)
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-runs-clamp-{uuid4()}", email="rc@rc.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/projects/{project.id}/runs?limit=9999&offset=0")
            assert r.status_code == 200
            # No error; server clamps rather than 422s. Total is 0 (no runs seeded).
            assert r.json()["total"] == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_runs_verdict_filter(session):
    org = Org(name=f"runs-verdict-org-{uuid4()}")
    project = Project(org=org, name=f"runs-verdict-proj-{uuid4()}")
    session.add(project)
    await session.commit()

    verdicts = ["pass", "pass", "warn", "fail"]
    for i, v in enumerate(verdicts):
        session.add(
            Run(
                project=project,
                idempotency_key=f"verdict-{i}-{uuid4()}",
                baseline_ref="main",
                candidate_ref="feat",
                tier="hermetic",
                config={},
                status="done",
                verdict=v,
            )
        )
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-runs-verdict-{uuid4()}", email="rv@rv.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/projects/{project.id}/runs?verdict=pass")
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 2
            assert all(item["verdict"] == "pass" for item in body["items"])

            r2 = await c.get(f"/v1/projects/{project.id}/runs?verdict=fail")
            assert r2.status_code == 200
            assert r2.json()["total"] == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_runs_search_q(session):
    org = Org(name=f"runs-search-org-{uuid4()}")
    project = Project(org=org, name=f"runs-search-proj-{uuid4()}")
    session.add(project)
    await session.commit()

    r_match = Run(
        project=project,
        idempotency_key=f"search-match-{uuid4()}",
        baseline_ref="release/v1.2.3",
        candidate_ref="feat/special-branch",
        tier="hermetic",
        config={},
        status="done",
        verdict="pass",
    )
    r_other = Run(
        project=project,
        idempotency_key=f"search-other-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat/unrelated",
        tier="hermetic",
        config={},
        status="done",
        verdict="pass",
    )
    session.add_all([r_match, r_other])
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-runs-search-{uuid4()}", email="rs@rs.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/projects/{project.id}/runs?q=special-branch")
            assert r.status_code == 200
            body = r.json()
            ids = [item["id"] for item in body["items"]]
            assert str(r_match.id) in ids
            assert str(r_other.id) not in ids
            assert body["total"] == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_runs_cross_org_404_with_query_params(session):
    org_a = Org(name=f"runs-iso-a-{uuid4()}")
    user_a = User(org=org_a, clerk_user_id=f"u-runs-iso-a-{uuid4()}", email="ria@ria.com")
    org_b = Org(name=f"runs-iso-b-{uuid4()}")
    proj_b = Project(org=org_b, name=f"runs-iso-b-proj-{uuid4()}")
    session.add_all([user_a, proj_b])
    await session.commit()

    try:
        async with await _client(session, (user_a, org_a)) as c:
            r = await c.get(f"/v1/projects/{proj_b.id}/runs?limit=10&offset=0&verdict=pass&q=x")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ── Task 11: Slack manual connect/disconnect audit rows ─────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_slack_manual_set_writes_audit(session):
    from server.models import AuditLog

    org = Org(name=f"slack-audit-org-{uuid4()}")
    project = Project(org=org, name=f"slack-audit-proj-{uuid4()}")
    session.add(project)
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-slack-audit-{uuid4()}", email="sa@sa.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.put(
                f"/v1/projects/{project.id}/slack",
                json={"channel_id": "C123", "bot_token": "xoxb-secret"},
            )
            assert r.status_code == 200

            rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "slack.connected",
                        AuditLog.target_id == str(project.id),
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].actor == user.clerk_user_id
            assert rows[0].target_type == "project"
            assert rows[0].target_id == str(project.id)
    finally:
        app.dependency_overrides.clear()

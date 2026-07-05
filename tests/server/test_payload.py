"""Tests for GET /v1/runs/{run_id}/payload — Task 10."""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory

from server.db import get_session
from server.deps import get_user_ctx
from server.main import app
from server.models import Org, Project, Run, Trajectory, User

STRUCTURE = StructureDoc(
    agents=[
        AgentEntry(name="Fact Checker", function="fact_checker", file="agents.py", line=10)
    ]
)
CONFIG = STRUCTURE.model_dump()


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
        test_case_id=tc_id, version_tag=tag, input={}, events=events,
    ).model_dump(mode="json")


def _make_run(org_name: str, project_name: str, **kwargs) -> tuple[Org, Project, Run]:
    org = Org(name=org_name)
    project = Project(org=org, name=project_name)
    fields = {
        "project": project,
        "idempotency_key": f"payload-{uuid4()}",
        "baseline_ref": "main",
        "candidate_ref": "feat",
        "tier": "hermetic",
        "kind": "ci",
        "config": CONFIG,
        "status": "pending",
    }
    fields.update(kwargs)
    run = Run(**fields)
    return org, project, run


@pytest.mark.asyncio(loop_scope="session")
async def test_processed_run_exposes_payload_with_run_metrics(session):
    """A run with a populated report_payload returns it verbatim, including
    the Task 6-8 run_metrics/warnings/skipped_checks/confidence fields."""
    payload = {
        "meta": {"baseline_ref": "main", "candidate_ref": "feat"},
        "runQuality": {"baseline_trajectories": 8, "candidate_trajectories": 8},
        "graph": {"nodes": [], "edges": []},
        "comparison": {
            "overall_verdict": "fail",
            "warnings": ["low sample size for tc1"],
            "test_case_comparisons": [
                {
                    "test_case_id": "tc1",
                    "run_metrics": [
                        {
                            "metric": "latency_ms",
                            "baseline_mean": 500.0,
                            "candidate_mean": 8000.0,
                            "delta": 7500.0,
                            "p_value": 0.01,
                            "adjusted_p_value": 0.01,
                            "verdict": "fail",
                            "low_power": False,
                        }
                    ],
                }
            ],
        },
        "warnings": ["low sample size for tc1"],
        "outputEvals": [
            {
                "test_case_id": "tc1",
                "verdict": "pass",
                "skipped_checks": [{"check": "judge", "reason": "no LLM credential"}],
            }
        ],
        "attribution": {
            "attributions": [
                {
                    "test_case_id": "tc1",
                    "agent_name": "Fact Checker",
                    "function": "fact_checker",
                    "metric": "invocation_rate",
                    "delta_summary": "100% -> 0%",
                    "verdict": "fail",
                    "primary": {
                        "target_path": "agents.py",
                        "rule": "code_change",
                        "confidence": "high",
                    },
                }
            ]
        },
        "trajectories": {"baseline": [], "candidate": []},
    }
    org, project, run = _make_run(
        "payload-org", "payload-proj", status="done", verdict="fail", report_payload=payload
    )
    session.add(run)
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-payload-{uuid4()}", email="p@p.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/runs/{run.id}/payload")
            assert r.status_code == 200
            body = r.json()
            tcc = body["comparison"]["test_case_comparisons"][0]
            run_metric = tcc["run_metrics"][0]
            for key in (
                "metric", "baseline_mean", "candidate_mean", "delta",
                "p_value", "adjusted_p_value", "verdict", "low_power",
            ):
                assert key in run_metric
            assert body["warnings"] == ["low sample size for tc1"]
            assert body["outputEvals"][0]["skipped_checks"][0]["check"] == "judge"
            assert (
                body["attribution"]["attributions"][0]["primary"]["confidence"] == "high"
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_payload_unauthorized_org_404(session):
    """A run belonging to a different org must 404, not leak the payload."""
    org, project, run = _make_run(
        "payload-org-owner", "payload-proj-owner",
        status="done", verdict="pass", report_payload={"meta": {}},
    )
    other_org = Org(name="payload-org-intruder")
    other_user = User(org=other_org, clerk_user_id=f"u-intruder-{uuid4()}", email="i@i.com")
    session.add_all([run, other_user])
    await session.commit()

    try:
        async with await _client(session, (other_user, other_org)) as c:
            r = await c.get(f"/v1/runs/{run.id}/payload")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_unprocessed_run_payload_not_ready_404(session):
    """A run whose report_payload is still NULL returns 404 'payload not ready'."""
    org, project, run = _make_run(
        "payload-org-pending", "payload-proj-pending", status="processing",
    )
    session.add(run)
    await session.commit()

    user = User(org=org, clerk_user_id=f"u-pending-{uuid4()}", email="pe@pe.com")
    session.add(user)
    await session.commit()

    try:
        async with await _client(session, (user, org)) as c:
            r = await c.get(f"/v1/runs/{run.id}/payload")
            assert r.status_code == 404
            assert r.json()["detail"] == "payload not ready"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_worker_populates_report_payload(session):
    """process_run stores a full payload (with run_metrics) on Run.report_payload."""
    from contextlib import asynccontextmanager

    from server.worker import process_run

    org = Org(name="payload-worker-org")
    project = Project(org=org, name="payload-worker-proj")
    run = Run(
        project=project,
        idempotency_key=f"payload-worker-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        config=CONFIG,
        status="pending",
    )
    for _ in range(8):
        run.trajectories.append(
            Trajectory(side="baseline", test_case_id="tc1", payload=_engine_payload("tc1", "baseline", True))
        )
    for _ in range(8):
        run.trajectories.append(
            Trajectory(side="candidate", test_case_id="tc1", payload=_engine_payload("tc1", "candidate", False))
        )
    session.add(run)
    await session.commit()

    @asynccontextmanager
    async def factory():
        yield session

    await process_run({"session_factory": factory}, str(run.id))

    await session.refresh(run)
    assert run.report_payload is not None
    tcc = run.report_payload["comparison"]["test_case_comparisons"][0]
    assert "run_metrics" in tcc
    assert all(
        key in tcc["run_metrics"][0]
        for key in ("metric", "baseline_mean", "candidate_mean", "delta", "p_value", "adjusted_p_value", "verdict", "low_power")
    )

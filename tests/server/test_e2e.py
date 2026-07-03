"""End-to-end test: HTTP ingest → inline worker → findings read-back (Task 2.4)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from agentdiff.capture.events import (
    CallSite,
    CanonicalLLMCall,
    LLMRequestEvent,
)
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory

from server.db import get_session
from server.main import app
from server.models import ApiKey, Finding, Org, Project, Run
from server.worker import process_run
from server import security

# ---------------------------------------------------------------------------
# Real engine fixtures (mirrored from tests/server/test_worker.py Task 2.2)
# ---------------------------------------------------------------------------
STRUCTURE = StructureDoc(
    agents=[
        AgentEntry(
            name="Fact Checker",
            function="fact_checker",
            file="agents.py",
            line=10,
        )
    ]
)
CONFIG = STRUCTURE.model_dump()


def _engine_traj(tc_id: str, tag: str, agent_fires: bool) -> EngineTrajectory:
    """Build a real EngineTrajectory that fires (or not) the Fact Checker agent."""
    cid = uuid4()
    events = []
    if agent_fires:
        events.append(
            LLMRequestEvent(
                call_id=cid,
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
    )


def _payload(tc_id: str, tag: str, agent_fires: bool) -> dict:
    """Serialise an EngineTrajectory to the dict stored in Trajectory.payload."""
    return _engine_traj(tc_id, tag, agent_fires).model_dump(mode="json")


def _make_session_factory(session):
    """Wrap the open test session as an async context manager factory.

    process_run calls ``async with factory() as session:``.  Our context
    manager yields the existing session and does nothing on exit so the
    caller doesn't close it prematurely.
    """

    @asynccontextmanager
    async def factory():
        yield session

    return factory


# ---------------------------------------------------------------------------
# End-to-end test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_ingest_to_findings(session):
    """Full hosted path: POST /v1/runs → inline worker → findings persisted.

    Baseline fires Fact Checker on every sample; candidate never does.
    With 8 samples per side the engine produces a "fail" verdict and writes
    at least one Finding row.
    """
    # --- seed org / project / api key ---
    org = Org(name=f"Acme-e2e-{uuid4()}")
    project = Project(org=org, name="e2e-proj")
    full, prefix, kh = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=kh, prefix=prefix))
    await session.commit()

    # --- build trajectory payload list (8 baseline fire, 8 candidate silent) ---
    trajectories = []
    for i in range(8):
        trajectories.append(
            {
                "side": "baseline",
                "test_case_id": "tc1",
                "payload": _payload("tc1", "baseline", agent_fires=True),
            }
        )
    for i in range(8):
        trajectories.append(
            {
                "side": "candidate",
                "test_case_id": "tc1",
                "payload": _payload("tc1", "candidate", agent_fires=False),
            }
        )

    body = {
        "idempotency_key": f"e2e-{uuid4()}",
        "baseline_ref": "main",
        "candidate_ref": "feat",
        "tier": "hermetic",
        "config": CONFIG,
        "attribution": None,
        "trajectories": trajectories,
    }

    # --- inline enqueue: run worker synchronously in-process ---
    factory = _make_session_factory(session)

    async def inline_enqueue(run_id: str) -> None:
        await process_run({"session_factory": factory}, run_id)

    # --- wire overrides ---
    # FastAPI calls the override function and uses the return value as the
    # resolved dependency.  For an async generator dependency, the override
    # must itself be an async generator function (not a lambda returning one).
    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.state.enqueue = inline_enqueue

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            r = await client.post(
                "/v1/runs",
                json=body,
                headers={"Authorization": f"Bearer {full}"},
            )
    finally:
        app.dependency_overrides.clear()
        app.state.enqueue = None

    # --- assert HTTP layer ---
    assert r.status_code == 202, f"expected 202, got {r.status_code}: {r.text}"
    run_id = r.json()["run_id"]

    # --- assert worker wrote findings ---
    run = (
        await session.execute(select(Run).where(Run.id == run_id))
    ).scalar_one()
    await session.refresh(run)

    assert run.status == "done", f"expected done, got {run.status!r}"
    assert run.verdict in {"warn", "fail"}, f"unexpected verdict {run.verdict!r}"

    findings = (
        await session.execute(select(Finding).where(Finding.run_id == run_id))
    ).scalars().all()
    assert len(findings) >= 1, "expected at least one Finding row persisted"



"""Tests for server/worker.py process_run — TDD Task 2.2."""
from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select

from agentdiff.capture.events import (
    CallSite,
    CanonicalLLMCall,
    LLMRequestEvent,
)
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory

from server.models import Finding, Org, Project, Run, Trajectory
from server.worker import process_run

# ---------------------------------------------------------------------------
# Real engine fixture helpers
# ---------------------------------------------------------------------------
# The structure doc config stored in Run.config must be a full AgentEntry shape.
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
    """Build a real EngineTrajectory that fires (or not) the Fact Checker agent.

    Agent detection in agentdiff.compare uses `t.agents_invoked()`, which
    looks for events where `inferred_agent` matches the agent's *display name*
    (not function).  LLMRequestEvent is the right vehicle.
    """
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


def _factory(session):
    """Inject the open test session as the async_session factory."""

    @asynccontextmanager
    async def factory():
        yield session

    return factory


# ---------------------------------------------------------------------------
# Happy-path test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="session")
async def test_process_run_writes_findings(session):
    """Baseline fires Fact Checker on every run; candidate never does.

    With 8 samples per side the delta (-1.0) is both effect-sized (≥0.5) and
    statistically significant, so the verdict is 'fail' and a Finding row is
    written for tc1.
    """
    org = Org(name="Acme-worker")
    project = Project(org=org, name="proj-worker")
    run = Run(
        project=project,
        idempotency_key=f"worker-happy-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        config=CONFIG,
        status="pending",
    )
    # 8 baseline trajectories (agent fires) + 8 candidate (agent silent)
    for _ in range(8):
        run.trajectories.append(
            Trajectory(
                side="baseline",
                test_case_id="tc1",
                payload=_payload("tc1", "baseline", agent_fires=True),
            )
        )
    for _ in range(8):
        run.trajectories.append(
            Trajectory(
                side="candidate",
                test_case_id="tc1",
                payload=_payload("tc1", "candidate", agent_fires=False),
            )
        )
    session.add(run)
    await session.commit()

    await process_run({"session_factory": _factory(session)}, str(run.id))

    await session.refresh(run)
    findings = (
        await session.execute(select(Finding).where(Finding.run_id == run.id))
    ).scalars().all()

    assert run.status == "done", f"expected done, got {run.status!r}"
    assert run.verdict in {"warn", "fail"}, f"unexpected verdict {run.verdict!r}"
    assert len(findings) >= 1, "expected at least one Finding row"
    assert any(
        f.metric == "invocation_rate" for f in findings
    ), "expected an invocation_rate finding"
    assert all(
        f.impact_summary for f in findings
    ), "impact_summary must be populated"
    assert any(
        f.statistical_evidence and f.statistical_evidence["test"] == "two_proportion_z"
        for f in findings
    ), "statistical evidence must be persisted with findings"


# ---------------------------------------------------------------------------
# Failure path: engine error → status=failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="session")
async def test_process_run_engine_error_sets_failed(session):
    """If the engine raises, status→failed and error is stored; no Finding rows."""
    org = Org(name="Acme-err")
    project = Project(org=org, name="proj-err")
    run = Run(
        project=project,
        idempotency_key=f"worker-err-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        # Intentionally broken config — null values for required 'function'/'file'/'line'
        # fields cause StructureDoc.model_validate to raise before trajectories are touched.
        config={"agents": [{"name": "Bad", "function": None, "file": None, "line": None}]},
        status="pending",
    )
    # Need at least one trajectory so the engine is actually invoked.
    run.trajectories.append(
        Trajectory(
            side="baseline",
            test_case_id="tc1",
            payload=_payload("tc1", "baseline", agent_fires=True),
        )
    )
    session.add(run)
    await session.commit()

    await process_run({"session_factory": _factory(session)}, str(run.id))

    await session.refresh(run)
    findings = (
        await session.execute(select(Finding).where(Finding.run_id == run.id))
    ).scalars().all()

    assert run.status == "failed", f"expected failed, got {run.status!r}"
    assert run.error, "error field must be populated"
    assert len(findings) == 0, "no findings should be written on engine error"

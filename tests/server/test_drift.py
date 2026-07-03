"""Tests for server/drift.py drift detection logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory

from server.drift import check_drift_for_project
from server.models import Finding, LiveTrajectory, Org, Project, Run

# ---------------------------------------------------------------------------
# Shared fixture shapes (mirror test_worker.py)
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

_DRIFT_EXPLANATION = (
    "No attributable code change in this window — if no deploy occurred, "
    "suspect upstream model/provider drift."
)


def _engine_traj(tag: str, agent_fires: bool) -> EngineTrajectory:
    """Build a real EngineTrajectory that fires (or not) the Fact Checker."""
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
        test_case_id="live_traffic",
        version_tag=tag,
        input={},
        events=events,
    )


def _payload(tag: str, agent_fires: bool) -> dict:
    return _engine_traj(tag, agent_fires).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="session")
async def drift_project(session):
    """Return (project, ci_run) with a valid CI run for CONFIG."""
    org = Org(name=f"DriftOrg-{uuid4()}")
    project = Project(org=org, name=f"drift-proj-{uuid4()}")
    ci_run = Run(
        project=project,
        idempotency_key=f"ci-drift-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="done",
        verdict="pass",
    )
    session.add(org)
    session.add(project)
    session.add(ci_run)
    await session.commit()
    return project, ci_run


def _now():
    return datetime.now(timezone.utc)


def _at(minutes_ago: float) -> datetime:
    return _now() - timedelta(minutes=minutes_ago)


# ---------------------------------------------------------------------------
# Happy-path drift test: baseline fires, candidate silent → warn/fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_check_drift_creates_run_on_warn_fail(session, drift_project):
    """12 baseline (firing) + 12 candidate (silent) → drift run with findings."""
    project, _ = drift_project
    W = 60  # window minutes

    # Baseline: captured in [-2W, -W) — agent fires
    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("baseline", agent_fires=True),
                captured_at=_at(W + 10),  # well within [-2W, -W)
            )
        )
    # Candidate: captured in [-W, now) — agent silent
    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("candidate", agent_fires=False),
                captured_at=_at(W - 10),  # well within [-W, now)
            )
        )
    await session.commit()

    run_id = await check_drift_for_project(
        session, project.id, window_minutes=W, min_samples=10
    )

    assert run_id is not None, "Expected a drift run to be created"
    run_uuid = __import__("uuid").UUID(run_id)

    drift_run = (
        await session.execute(select(Run).where(Run.id == run_uuid))
    ).scalar_one()
    assert drift_run.kind == "drift"
    assert drift_run.verdict in {"warn", "fail"}
    assert drift_run.status == "done"
    assert drift_run.tier == "live"

    findings = (
        await session.execute(select(Finding).where(Finding.run_id == run_uuid))
    ).scalars().all()
    assert len(findings) >= 1, "Expected at least one finding"
    for f in findings:
        assert f.explanation == _DRIFT_EXPLANATION, f"Wrong explanation: {f.explanation!r}"
        assert f.cause_path is None
        assert f.cause_rule is None
        assert f.cause_hunk is None


@pytest.mark.asyncio(loop_scope="session")
async def test_check_drift_slack_posted_on_warn_fail(session, drift_project):
    """When SlackConfig is enabled, Slack post is attempted on drift."""
    project, _ = drift_project
    W = 60

    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("baseline", agent_fires=True),
                captured_at=_at(W + 10),
            )
        )
    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("candidate", agent_fires=False),
                captured_at=_at(W - 10),
            )
        )
    await session.commit()

    mock_slack = MagicMock()
    with patch("server.notify.SlackClient", return_value=mock_slack):
        with patch("server.notify.crypto.decrypt", return_value="token"):
            from server.models import SlackConfig

            cfg = SlackConfig(
                project_id=project.id,
                channel_id="C12345",
                bot_token_encrypted="enc_token",
                enabled=True,
            )
            session.add(cfg)
            await session.commit()

            run_id = await check_drift_for_project(
                session, project.id, window_minutes=W, min_samples=10
            )
    # If drift was detected (warn/fail), Slack client should have been called
    if run_id is not None:
        mock_slack.post_payload.assert_called_once()


# ---------------------------------------------------------------------------
# Under min_samples → None, no run created
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_check_drift_no_run_when_under_min_samples(session, drift_project):
    """If either window has < min_samples rows, returns None without creating a run."""
    project, _ = drift_project
    W = 60

    # Only 3 rows total — below min_samples=10
    for _ in range(3):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("baseline", agent_fires=True),
                captured_at=_at(W + 10),
            )
        )
    await session.commit()

    run_id = await check_drift_for_project(
        session, project.id, window_minutes=W, min_samples=10
    )
    assert run_id is None


# ---------------------------------------------------------------------------
# No prior CI run → None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_check_drift_no_ci_run_returns_none(session):
    """Project with no CI run → cannot classify agents → returns None."""
    org = Org(name=f"NoCiOrg-{uuid4()}")
    project = Project(org=org, name=f"no-ci-proj-{uuid4()}")
    session.add(org)
    session.add(project)
    await session.commit()

    W = 60
    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("baseline", agent_fires=True),
                captured_at=_at(W + 10),
            )
        )
    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("candidate", agent_fires=False),
                captured_at=_at(W - 10),
            )
        )
    await session.commit()

    run_id = await check_drift_for_project(
        session, project.id, window_minutes=W, min_samples=10
    )
    assert run_id is None


# ---------------------------------------------------------------------------
# Pass verdict (both windows firing) → None, no drift run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_check_drift_pass_verdict_returns_none(session, drift_project):
    """Both windows firing → no behavioral change → returns None."""
    project, _ = drift_project
    W = 60

    # Both windows: agent fires in both → no delta → pass
    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("baseline", agent_fires=True),
                captured_at=_at(W + 10),
            )
        )
    for _ in range(12):
        session.add(
            LiveTrajectory(
                project_id=project.id,
                payload=_payload("candidate", agent_fires=True),
                captured_at=_at(W - 10),
            )
        )
    await session.commit()

    run_id = await check_drift_for_project(
        session, project.id, window_minutes=W, min_samples=10
    )
    assert run_id is None, "Expected None when both windows have same agent invocation rate"

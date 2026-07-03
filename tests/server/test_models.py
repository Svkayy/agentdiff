import uuid
import pytest
from server.models import Org, Project, Run, Trajectory, Finding


@pytest.mark.asyncio(loop_scope="session")
async def test_run_persists_with_trajectories_and_findings(session):
    org = Org(name="Acme")
    project = Project(org=org, name="support-bot")
    run = Run(
        project=project,
        idempotency_key="idem-1",
        baseline_ref="origin/main",
        candidate_ref="working",
        tier="hermetic",
        config={"agents": []},
        status="pending",
    )
    run.trajectories.append(Trajectory(side="baseline", test_case_id="tc1", payload={"events": []}))
    run.findings.append(Finding(
        test_case_id="tc1",
        title="Fact Checker invocation changed",
        verdict="fail",
        metric="invocation_rate",
        impact_summary="fired 100% -> 0%",
    ))
    session.add(run)
    await session.commit()

    assert isinstance(run.id, uuid.UUID)
    assert run.status == "pending"
    assert run.trajectories[0].side == "baseline"
    assert run.findings[0].title == "Fact Checker invocation changed"

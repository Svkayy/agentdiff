import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdiff.compare import ComparisonResult, compare_all
from agentdiff.graph_model import build as build_graph
from agentdiff.structure.structure_yaml import StructureDoc
from server import crypto
from server.config import get_settings
from server.audit import record_audit
from server.db import get_session
from server.deps import get_user_ctx, own_project
from server.models import Finding, LiveTrajectory, Org, Project, Run, SlackConfig, Trajectory, User
from server.usage import check_quota

router = APIRouter()


# Backward-compat alias so existing call-sites stay unchanged.
_own_project = own_project


def _clamp_limit(limit: int) -> int:
    return max(0, min(limit, 200))


@router.get("/v1/projects")
async def list_projects(
    q: str | None = None,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    stmt = select(Project).where(Project.org_id == org.id)
    count_stmt = select(func.count(Project.id)).where(Project.org_id == org.id)
    if q:
        needle = f"%{q}%"
        stmt = stmt.where(Project.name.ilike(needle))
        count_stmt = count_stmt.where(Project.name.ilike(needle))

    total: int = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [{"id": str(p.id), "name": p.name} for p in rows],
        "total": total,
    }


@router.get("/v1/projects/{project_id}/runs")
async def list_runs(
    project_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    verdict: str | None = None,
    q: str | None = None,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    project = await _own_project(session, org, project_id)
    clamped_limit = _clamp_limit(limit)
    clamped_offset = max(0, offset)

    filters = [Run.project_id == project.id]
    if verdict:
        filters.append(Run.verdict == verdict)
    if q:
        needle = f"%{q}%"
        filters.append(
            or_(Run.baseline_ref.ilike(needle), Run.candidate_ref.ilike(needle))
        )

    total: int = (
        await session.execute(select(func.count(Run.id)).where(*filters))
    ).scalar_one()

    rows = (
        await session.execute(
            select(Run)
            .where(*filters)
            .order_by(Run.created_at.desc())
            .limit(clamped_limit)
            .offset(clamped_offset)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "status": r.status,
                "verdict": r.verdict,
                "baseline_ref": r.baseline_ref,
                "candidate_ref": r.candidate_ref,
                "kind": r.kind,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "total": total,
    }


@router.get("/v1/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    run = (
        await session.execute(
            select(Run).join(Project).where(Run.id == run_id, Project.org_id == org.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    findings = (
        await session.execute(select(Finding).where(Finding.run_id == run.id))
    ).scalars().all()

    trajectory_rows = (
        await session.execute(select(Trajectory).where(Trajectory.run_id == run.id))
    ).scalars().all()
    counts = {
        "baseline": sum(1 for row in trajectory_rows if row.side == "baseline"),
        "candidate": sum(1 for row in trajectory_rows if row.side == "candidate"),
    }
    processed = _processed_run_payload(run, trajectory_rows)

    return {
        "id": str(run.id),
        "status": run.status,
        "verdict": run.verdict,
        "kind": run.kind,
        "created_at": run.created_at.isoformat(),
        "baseline_ref": run.baseline_ref,
        "candidate_ref": run.candidate_ref,
        "config": run.config,
        "error": run.error,
        "baseline_samples": counts.get("baseline", 0),
        "candidate_samples": counts.get("candidate", 0),
        "findings": [
            {
                "test_case_id": f.test_case_id,
                "title": f.title,
                "verdict": f.verdict,
                "metric": f.metric,
                "impact_summary": f.impact_summary,
                "statistical_evidence": f.statistical_evidence,
                "cause_path": f.cause_path,
                "cause_rule": f.cause_rule,
                "cause_hunk": f.cause_hunk,
                "explanation": f.explanation,
                # Aggregation context — populated when findings were built from
                # build_incident_summary; falls back to 1/1 for legacy rows that
                # pre-date aggregation.
                "test_cases_affected": (
                    (f.statistical_evidence or {}).get("test_cases_affected", 1)
                ),
                "test_cases_total": (
                    (f.statistical_evidence or {}).get("test_cases_total", 1)
                ),
            }
            for f in findings
        ],
        **processed,
    }


@router.get("/v1/runs/{run_id}/payload")
async def get_run_payload(
    run_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    run = (
        await session.execute(
            select(Run).join(Project).where(Run.id == run_id, Project.org_id == org.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.report_payload is None:
        raise HTTPException(status_code=404, detail="payload not ready")
    return run.report_payload


def _processed_run_payload(run: Run, trajectory_rows: list[Trajectory]) -> dict:
    """Build honest dashboard data from stored trajectories and run artifacts.

    The graph is built with the full agent structure (from run.config) so ALL
    agents render — not just the one(s) whose delta crossed a threshold.  If
    trajectory payloads don't re-validate (old rows), we still return a valid
    (possibly sparse) graph from whatever deltas the comparison yields plus the
    structure fallback.
    """
    from agentdiff.trajectory import Trajectory as EngineTrajectory, TrajectorySet

    def _side(side: str) -> TrajectorySet:
        trajectories = []
        for row in trajectory_rows:
            if row.side != side:
                continue
            try:
                trajectories.append(EngineTrajectory.model_validate(row.payload))
            except Exception:  # noqa: BLE001 - old rows may not contain full payloads
                continue
        return TrajectorySet(version_tag=side, trajectories=trajectories)

    baseline = _side("baseline")
    candidate = _side("candidate")
    try:
        structure = StructureDoc.model_validate(run.config or {})
    except Exception:  # noqa: BLE001 - keep old failed runs readable
        structure = StructureDoc()
    test_case_ids = sorted({row.test_case_id for row in trajectory_rows})
    # compare/graph must never 500 a done run: a malformed-but-parseable
    # trajectory could otherwise raise here and take down the whole endpoint.
    # Degrade to an empty comparison + structure-only graph instead.
    try:
        comparison = compare_all(baseline, candidate, structure, test_case_ids)
    except Exception:  # noqa: BLE001 - keep the run readable even if compare fails
        comparison = ComparisonResult()
    # Pass structure so healthy agents (not in any delta) still appear as green
    # nodes in the graph — the full system view, not just the changed agent.
    try:
        graph = build_graph(comparison, run.attribution, baseline, candidate, structure)
    except Exception:  # noqa: BLE001 - a graph should never break the run view
        graph = build_graph(ComparisonResult(), None, baseline, candidate, structure)
    return {
        "comparison": comparison.model_dump(mode="json"),
        "graph": graph.model_dump(mode="json"),
        "attribution": run.attribution,
        "trajectories": {
            "baseline": [t.model_dump(mode="json") for t in baseline.trajectories],
            "candidate": [t.model_dump(mode="json") for t in candidate.trajectories],
        },
    }


# B1 — Project stats endpoint
@router.get("/v1/projects/{project_id}/stats")
async def get_project_stats(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    project = await _own_project(session, org, project_id)

    # Total completed runs
    total_runs: int = (
        await session.execute(
            select(func.count(Run.id)).where(
                Run.project_id == project.id, Run.status == "done"
            )
        )
    ).scalar_one()

    # Pass rate over last 30 completed CI runs
    last_30_ci = (
        await session.execute(
            select(Run.verdict)
            .where(Run.project_id == project.id, Run.status == "done", Run.kind == "ci")
            .order_by(Run.created_at.desc())
            .limit(30)
        )
    ).scalars().all()
    if last_30_ci:
        pass_count = sum(1 for v in last_30_ci if v == "pass")
        pass_rate_30: float | None = pass_count / len(last_30_ci)
    else:
        pass_rate_30 = None

    # Failing streak: consecutive most-recent completed CI runs with warn/fail
    all_ci_verdicts = (
        await session.execute(
            select(Run.verdict)
            .where(Run.project_id == project.id, Run.status == "done", Run.kind == "ci")
            .order_by(Run.created_at.desc())
        )
    ).scalars().all()
    failing_streak = 0
    for v in all_ci_verdicts:
        if v in {"warn", "fail"}:
            failing_streak += 1
        else:
            break

    # Last failure timestamp
    last_failure_row = (
        await session.execute(
            select(Run.created_at)
            .where(
                Run.project_id == project.id,
                Run.status == "done",
                Run.verdict.in_(["warn", "fail"]),
            )
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    last_failure_at: str | None = last_failure_row.isoformat() if last_failure_row else None

    # Drift runs in last 7 days
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    drift_runs_7d: int = (
        await session.execute(
            select(func.count(Run.id)).where(
                Run.project_id == project.id,
                Run.status == "done",
                Run.kind == "drift",
                Run.created_at >= seven_days_ago,
            )
        )
    ).scalar_one()

    # Recent 20 completed runs (any kind), newest first
    recent_rows = (
        await session.execute(
            select(Run.id, Run.verdict, Run.kind, Run.created_at)
            .where(Run.project_id == project.id, Run.status == "done")
            .order_by(Run.created_at.desc())
            .limit(20)
        )
    ).all()
    recent = [
        {
            "id": str(r.id),
            "verdict": r.verdict,
            "kind": r.kind,
            "created_at": r.created_at.isoformat(),
        }
        for r in recent_rows
    ]

    # Drift readiness: is there enough live traffic in the most recent window
    # for the drift cron to actually classify behavior?  Surfaces the same
    # min_samples gate the worker enforces so the dashboard can explain a
    # "quiet" drift lane instead of implying it's broken.
    settings = get_settings()
    if settings.drift_window_minutes <= 0 or settings.drift_check_interval_minutes <= 0:
        drift_status = "disabled"
    else:
        window_start = datetime.now(timezone.utc) - timedelta(
            minutes=settings.drift_window_minutes
        )
        live_count: int = (
            await session.execute(
                select(func.count(LiveTrajectory.id)).where(
                    LiveTrajectory.project_id == project.id,
                    LiveTrajectory.captured_at >= window_start,
                )
            )
        ).scalar_one()
        drift_status = (
            "ok" if live_count >= settings.drift_min_samples else "insufficient_samples"
        )

    return {
        "total_runs": total_runs,
        "pass_rate_30": pass_rate_30,
        "failing_streak": failing_streak,
        "last_failure_at": last_failure_at,
        "drift_runs_7d": drift_runs_7d,
        "drift_status": drift_status,
        "recent": recent,
    }


@router.get("/v1/usage")
async def get_usage(
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Current-period usage + plan limits for the caller's org."""
    _user, org = ctx
    status = await check_quota(session, org)
    return {
        "plan": status.plan,
        "period": status.period,
        "runs_used": status.runs_used,
        "runs_limit": status.runs_limit,
        "trajectories_used": status.trajectories_used,
        "trajectories_limit": status.trajectories_limit,
    }


class SlackConfigIn(BaseModel):
    channel_id: str
    bot_token: str


@router.put("/v1/projects/{project_id}/slack")
async def set_slack(
    project_id: uuid.UUID,
    body: SlackConfigIn,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user, org = ctx
    project = await _own_project(session, org, project_id)
    cfg = (
        await session.execute(
            select(SlackConfig).where(SlackConfig.project_id == project.id)
        )
    ).scalar_one_or_none()
    enc = crypto.encrypt(body.bot_token)
    if cfg is None:
        session.add(
            SlackConfig(
                project_id=project.id,
                channel_id=body.channel_id,
                bot_token_encrypted=enc,
                enabled=True,
            )
        )
    else:
        cfg.channel_id = body.channel_id
        cfg.bot_token_encrypted = enc
        cfg.enabled = True
        # Manual reconfigure supersedes any prior OAuth install: clear the
        # stored webhook so the delivery fallback can't post to the old
        # OAuth channel, and status stops reporting via="oauth".
        cfg.webhook_url_encrypted = None
    await record_audit(
        session,
        org.id,
        user.clerk_user_id,
        "slack.connected",
        "project",
        str(project.id),
        project_id=project.id,
    )
    await session.commit()
    return {"status": "ok"}

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server import crypto
from server.db import get_session
from server.deps import get_user_ctx, own_project
from server.models import Finding, Org, Project, Run, SlackConfig, Trajectory, User

router = APIRouter()


# Backward-compat alias so existing call-sites stay unchanged.
_own_project = own_project


@router.get("/v1/projects")
async def list_projects(
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _user, org = ctx
    rows = (
        await session.execute(select(Project).where(Project.org_id == org.id))
    ).scalars().all()
    return [{"id": str(p.id), "name": p.name} for p in rows]


@router.get("/v1/projects/{project_id}/runs")
async def list_runs(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _user, org = ctx
    project = await _own_project(session, org, project_id)
    rows = (
        await session.execute(select(Run).where(Run.project_id == project.id))
    ).scalars().all()
    return [
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
    ]


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

    # B3(i) — trajectory counts by side
    side_counts = (
        await session.execute(
            select(Trajectory.side, func.count(Trajectory.id))
            .where(Trajectory.run_id == run.id)
            .group_by(Trajectory.side)
        )
    ).all()
    counts = {row[0]: row[1] for row in side_counts}

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
                "cause_path": f.cause_path,
                "cause_rule": f.cause_rule,
                "cause_hunk": f.cause_hunk,
                "explanation": f.explanation,
            }
            for f in findings
        ],
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

    return {
        "total_runs": total_runs,
        "pass_rate_30": pass_rate_30,
        "failing_streak": failing_streak,
        "last_failure_at": last_failure_at,
        "drift_runs_7d": drift_runs_7d,
        "recent": recent,
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
    _user, org = ctx
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
    await session.commit()
    return {"status": "ok"}

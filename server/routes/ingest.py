import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import get_settings
from server.db import get_session
from server.deps import get_project_from_api_key
from server.metrics import METRICS
from server.models import Org, Project, Run, Trajectory
from server.ratelimit import check_rate_limit
from server.schemas import RunAccepted, RunUpload
from server.usage import check_quota, increment_usage

router = APIRouter()
logger = logging.getLogger("agentdiff.ingest")


async def _load_org(session: AsyncSession, org_id) -> Org:
    return (
        await session.execute(select(Org).where(Org.id == org_id))
    ).scalar_one()


async def _enforce_quota(session: AsyncSession, project: Project) -> None:
    """Raise 429 with quota headers/body when the org's monthly cap is met."""
    org = await _load_org(session, project.org_id)
    status = await check_quota(session, org)
    if status.exceeded:
        METRICS.inc("agentdiff_quota_rejections_total")
        raise HTTPException(
            status_code=429,
            detail={
                "detail": "monthly quota exceeded",
                "plan": status.plan,
                "used": status.used,
                "limit": status.limit,
            },
            headers={
                "X-Quota-Limit": str(status.limit),
                "X-Quota-Remaining": "0",
            },
        )


@router.post("/v1/runs", status_code=202, response_model=RunAccepted)
async def create_run(
    body: RunUpload,
    request: Request,
    project: Project = Depends(get_project_from_api_key),
    session: AsyncSession = Depends(get_session),
) -> RunAccepted:
    # Per-project rate limiting.
    redis_pool = getattr(request.app.state, "redis_pool", None)
    if redis_pool is not None:
        try:
            settings = get_settings()
            rl_key = f"rl:runs:{project.id}"
            allowed = await check_rate_limit(redis_pool, rl_key, settings.rate_limit_runs_per_minute, 60)
            if not allowed:
                raise HTTPException(status_code=429, detail="rate limit exceeded")
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("Rate-limit check failed (fail-open) for project %s", project.id)

    existing = (
        await session.execute(
            select(Run).where(
                Run.project_id == project.id,
                Run.idempotency_key == body.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Idempotent replay — never double-count usage.
        return RunAccepted(run_id=str(existing.id), status=existing.status)

    # Monthly quota enforcement (429 for capped plans past their cap).
    await _enforce_quota(session, project)

    run = Run(
        project_id=project.id,
        idempotency_key=body.idempotency_key,
        baseline_ref=body.baseline_ref,
        candidate_ref=body.candidate_ref,
        tier=body.tier,
        config=body.config,
        attribution=body.attribution,
        status="pending",
    )
    for t in body.trajectories:
        run.trajectories.append(
            Trajectory(side=t.side, test_case_id=t.test_case_id, payload=t.payload)
        )
    session.add(run)
    await session.commit()

    # Meter usage on successful ingest: one run + its trajectory count.
    await increment_usage(
        session,
        project.org_id,
        runs=1,
        trajectories=len(body.trajectories),
    )

    await _maybe_enqueue(request, str(run.id))
    return RunAccepted(run_id=str(run.id), status="pending")


async def _maybe_enqueue(request: Request, run_id: str) -> None:
    enqueue = getattr(request.app.state, "enqueue", None)
    if enqueue is None:
        return
    try:
        result = enqueue(run_id)
        if hasattr(result, "__await__"):
            await result
    except Exception:  # noqa: BLE001
        logger.warning("Enqueue failed for run %s; run persisted as pending", run_id)

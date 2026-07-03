from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db import get_session
from server.deps import get_project_from_api_key
from server.models import Project, Run, Trajectory
from server.schemas import RunAccepted, RunUpload

router = APIRouter()


@router.post("/v1/runs", status_code=202, response_model=RunAccepted)
async def create_run(
    body: RunUpload,
    request: Request,
    project: Project = Depends(get_project_from_api_key),
    session: AsyncSession = Depends(get_session),
) -> RunAccepted:
    existing = (
        await session.execute(
            select(Run).where(
                Run.project_id == project.id,
                Run.idempotency_key == body.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return RunAccepted(run_id=str(existing.id), status=existing.status)

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

    await _maybe_enqueue(request, str(run.id))
    return RunAccepted(run_id=str(run.id), status="pending")


async def _maybe_enqueue(request: Request, run_id: str) -> None:
    enqueue = getattr(request.app.state, "enqueue", None)
    if enqueue is None:
        return
    result = enqueue(run_id)
    if hasattr(result, "__await__"):
        await result

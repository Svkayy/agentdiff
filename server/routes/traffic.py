"""Live traffic ingest — POST /v1/traffic."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import get_settings
from server.db import get_session
from server.deps import get_project_from_api_key
from server.models import LiveTrajectory, Project
from server.ratelimit import check_rate_limit

router = APIRouter()
logger = logging.getLogger("agentdiff.traffic")


class TrafficUpload(BaseModel):
    trajectories: list[dict] = Field(max_length=1000)


class TrafficAccepted(BaseModel):
    accepted: int


@router.post("/v1/traffic", status_code=202, response_model=TrafficAccepted)
async def ingest_traffic(
    body: TrafficUpload,
    request: Request,
    project: Project = Depends(get_project_from_api_key),
    session: AsyncSession = Depends(get_session),
) -> TrafficAccepted:
    """Accept a batch of live trajectories for the authenticated project."""
    redis_pool = getattr(request.app.state, "redis_pool", None)
    if redis_pool is not None:
        try:
            settings = get_settings()
            rl_key = f"rl:traffic:{project.id}"
            limit = getattr(settings, "rate_limit_traffic_per_minute", 600)
            allowed = await check_rate_limit(redis_pool, rl_key, limit, 60)
            if not allowed:
                raise HTTPException(status_code=429, detail="rate limit exceeded")
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("Rate-limit check failed (fail-open) for project %s", project.id)

    for payload in body.trajectories:
        session.add(LiveTrajectory(project_id=project.id, payload=payload))

    await session.commit()
    return TrafficAccepted(accepted=len(body.trajectories))

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import crypto
from server.db import get_session
from server.deps import get_user_ctx, own_project
from server.models import Finding, Org, Project, Run, SlackConfig, User

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
        "findings": [
            {
                "test_case_id": f.test_case_id,
                "title": f.title,
                "verdict": f.verdict,
                "metric": f.metric,
                "impact_summary": f.impact_summary,
                "cause_path": f.cause_path,
                "cause_rule": f.cause_rule,
            }
            for f in findings
        ],
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

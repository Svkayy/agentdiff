import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server import security
from server.audit import record_audit
from server.db import get_session
from server.deps import get_user_ctx, own_project
from server.models import ApiKey, AuditLog, Org, Project, Run, User

router = APIRouter()


# ── /v1/me ───────────────────────────────────────────────────────────────────


@router.get("/v1/me")
async def me(
    ctx: tuple[User, Org] = Depends(get_user_ctx),
) -> dict:
    user, org = ctx
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "clerk_user_id": user.clerk_user_id,
        },
        "org": {
            "id": str(org.id),
            "name": org.name,
            "clerk_org_id": org.clerk_org_id,
        },
    }


# ── /v1/projects ─────────────────────────────────────────────────────────────


class ProjectIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty or whitespace")
        if len(v) > 255:
            raise ValueError("name must be at most 255 characters")
        return v


@router.post("/v1/projects", status_code=201)
async def create_project(
    body: ProjectIn,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user, org = ctx
    project = Project(org_id=org.id, name=body.name)
    session.add(project)
    await session.flush()
    await record_audit(
        session, org.id, user.clerk_user_id, "project.created", "project", str(project.id)
    )
    await session.commit()
    return {"id": str(project.id), "name": project.name}


@router.patch("/v1/projects/{project_id}")
async def rename_project(
    project_id: uuid.UUID,
    body: ProjectIn,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user, org = ctx
    project = await own_project(session, org, project_id)
    project.name = body.name
    await record_audit(
        session, org.id, user.clerk_user_id, "project.renamed", "project", str(project.id)
    )
    await session.commit()
    return {"id": str(project.id), "name": project.name}


@router.delete("/v1/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> Response:
    user, org = ctx
    project = await own_project(session, org, project_id)
    await record_audit(
        session, org.id, user.clerk_user_id, "project.deleted", "project", str(project.id)
    )
    await session.delete(project)
    await session.commit()
    return Response(status_code=204)


# ── /v1/projects/{project_id}/keys ───────────────────────────────────────────


class KeyIn(BaseModel):
    name: str | None = None


@router.post("/v1/projects/{project_id}/keys", status_code=201)
async def create_key(
    project_id: uuid.UUID,
    body: KeyIn | None = None,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user, org = ctx
    project = await own_project(session, org, project_id)
    name = body.name if body is not None else None
    full, prefix, key_hash = security.generate_api_key()
    api_key = ApiKey(project_id=project.id, key_hash=key_hash, prefix=prefix, name=name)
    session.add(api_key)
    await session.flush()
    await record_audit(
        session,
        org.id,
        user.clerk_user_id,
        "key.minted",
        "api_key",
        str(api_key.id),
        {"project_id": str(project.id)},
    )
    await session.commit()
    # Full key is returned exactly once here — never stored in plain text, never logged.
    return {"id": str(api_key.id), "prefix": prefix, "key": full, "name": api_key.name}


@router.get("/v1/projects/{project_id}/keys")
async def list_keys(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _user, org = ctx
    project = await own_project(session, org, project_id)
    rows = (
        await session.execute(select(ApiKey).where(ApiKey.project_id == project.id))
    ).scalars().all()
    return [
        {
            "id": str(k.id),
            "prefix": k.prefix,
            "name": k.name,
            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in rows
    ]


# ── /v1/keys/{key_id} ────────────────────────────────────────────────────────


@router.delete("/v1/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> Response:
    user, org = ctx
    # Join ApiKey → Project to enforce org ownership — same 404-not-403 pattern.
    row = (
        await session.execute(
            select(ApiKey)
            .join(Project, ApiKey.project_id == Project.id)
            .where(ApiKey.id == key_id, Project.org_id == org.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    # Idempotent: revoking an already-revoked key is still 204, and must NOT
    # write a second audit row.
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await record_audit(
            session, org.id, user.clerk_user_id, "key.revoked", "api_key", str(row.id)
        )
        await session.commit()
    return Response(status_code=204)


# ── /v1/runs/{run_id} ─────────────────────────────────────────────────────────


@router.delete("/v1/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> Response:
    user, org = ctx
    run = (
        await session.execute(
            select(Run).join(Project).where(Run.id == run_id, Project.org_id == org.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    await record_audit(
        session,
        org.id,
        user.clerk_user_id,
        "run.deleted",
        "run",
        str(run.id),
        {"project_id": str(run.project_id)},
    )
    await session.delete(run)
    await session.commit()
    return Response(status_code=204)


# ── /v1/projects/{project_id}/audit ──────────────────────────────────────────


@router.get("/v1/projects/{project_id}/audit")
async def list_audit(
    project_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    project = await own_project(session, org, project_id)
    clamped_limit = max(0, min(limit, 200))
    clamped_offset = max(0, offset)

    # A row belongs to this project's audit trail either because it targets
    # the project directly (project.created/renamed/deleted) or because its
    # meta carries the owning project_id (key.*, run.deleted, slack.*).
    project_scope = or_(
        AuditLog.target_id == str(project.id),
        AuditLog.meta["project_id"].as_string() == str(project.id),
    )

    total: int = (
        await session.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.org_id == org.id,
                project_scope,
            )
        )
    ).scalar_one()

    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.org_id == org.id, project_scope)
            .order_by(AuditLog.created_at.desc())
            .limit(clamped_limit)
            .offset(clamped_offset)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": str(row.id),
                "actor": row.actor,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "meta": row.meta,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "total": total,
    }

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import security
from server.db import get_session
from server.deps import get_user_ctx, own_project
from server.models import ApiKey, Org, Project, User

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
    _user, org = ctx
    project = Project(org_id=org.id, name=body.name)
    session.add(project)
    await session.commit()
    return {"id": str(project.id), "name": project.name}


# ── /v1/projects/{project_id}/keys ───────────────────────────────────────────


@router.post("/v1/projects/{project_id}/keys", status_code=201)
async def create_key(
    project_id: uuid.UUID,
    ctx: tuple[User, Org] = Depends(get_user_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _user, org = ctx
    project = await own_project(session, org, project_id)
    full, prefix, key_hash = security.generate_api_key()
    api_key = ApiKey(project_id=project.id, key_hash=key_hash, prefix=prefix)
    session.add(api_key)
    await session.commit()
    # Full key is returned exactly once here — never stored in plain text, never logged.
    return {"id": str(api_key.id), "prefix": prefix, "key": full}


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
    _user, org = ctx
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
    # Idempotent: revoking an already-revoked key is still 204.
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()
    return Response(status_code=204)

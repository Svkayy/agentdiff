from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import security
from server.db import get_session
from server.models import ApiKey, Project


async def get_project_from_api_key(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Project:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    full = authorization.removeprefix("Bearer ").strip()
    if not full.startswith("adk_"):
        raise HTTPException(status_code=401, detail="invalid api key")
    prefix = full[:12]
    rows = (await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))).scalars().all()
    for key in rows:
        if key.revoked_at is None and security.verify_api_key(full, key.key_hash):
            key.last_used_at = datetime.now(timezone.utc)
            await session.commit()
            return (await session.execute(select(Project).where(Project.id == key.project_id))).scalar_one()
    raise HTTPException(status_code=401, detail="invalid api key")

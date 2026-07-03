from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import clerk, security
from server.config import get_settings
from server.db import get_session
from server.models import ApiKey, Org, Project, User


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


async def get_user_ctx(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> tuple[User, Org]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    settings = get_settings()
    try:
        pub = clerk.load_jwks_pubkey(settings.clerk_jwks_url)
        claims = clerk.verify_token(token, pub, settings.clerk_issuer)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid clerk token") from exc

    clerk_org_id = claims.get("org_id") or f"personal_{claims['sub']}"
    org = (
        await session.execute(select(Org).where(Org.clerk_org_id == clerk_org_id))
    ).scalar_one_or_none()
    if org is None:
        org = Org(clerk_org_id=clerk_org_id, name=claims.get("org_slug", "personal"))
        session.add(org)
        await session.flush()
    user = (
        await session.execute(select(User).where(User.clerk_user_id == claims["sub"]))
    ).scalar_one_or_none()
    if user is None:
        user = User(org_id=org.id, clerk_user_id=claims["sub"], email=claims.get("email", ""))
        session.add(user)
    await session.commit()
    return user, org

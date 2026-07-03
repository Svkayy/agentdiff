from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from server import security
from server.deps import get_project_from_api_key
from server.models import Org, Project, ApiKey


def test_generate_and_verify_roundtrip():
    full, prefix, key_hash = security.generate_api_key()
    assert full.startswith("adk_")
    assert full.startswith(prefix)
    assert security.verify_api_key(full, key_hash) is True
    assert security.verify_api_key("adk_wrong", key_hash) is False


@pytest.mark.asyncio(loop_scope="session")
async def test_dependency_resolves_project(session):
    org = Org(name="Acme")
    project = Project(org=org, name="p")
    full, prefix, key_hash = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=key_hash, prefix=prefix))
    await session.commit()

    resolved = await get_project_from_api_key(f"Bearer {full}", session)
    assert resolved.id == project.id


@pytest.mark.asyncio(loop_scope="session")
async def test_dependency_rejects_bad_key(session):
    with pytest.raises(HTTPException) as exc:
        await get_project_from_api_key("Bearer adk_nope", session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_dependency_rejects_revoked_key(session):
    org = Org(name="RevokedOrg")
    project = Project(org=org, name="revoked-project")
    full, prefix, key_hash = security.generate_api_key()
    key = ApiKey(project=project, key_hash=key_hash, prefix=prefix)
    session.add(key)
    await session.commit()

    key.revoked_at = datetime.now(timezone.utc)
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await get_project_from_api_key(f"Bearer {full}", session)
    assert exc.value.status_code == 401

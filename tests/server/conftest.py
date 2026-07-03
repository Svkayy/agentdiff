import os

from cryptography.fernet import Fernet

os.environ.setdefault("AGENTDIFF_SECRET_ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db import Base
import server.models  # noqa: F401  (registers all tables on Base.metadata)

TEST_DB_URL = "postgresql+asyncpg://agentdiff:agentdiff@localhost:5432/agentdiff_test"
assert "_test" in TEST_DB_URL, "refusing schema reset on a non-test database"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _engine():
    engine = create_async_engine(TEST_DB_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def session(_engine) -> AsyncSession:
    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()

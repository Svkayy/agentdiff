import pytest
from sqlalchemy import text


@pytest.mark.asyncio(loop_scope="session")
async def test_session_connects(session):
    result = await session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1

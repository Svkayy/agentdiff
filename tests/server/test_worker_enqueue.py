import pytest
import fakeredis.aioredis as fakeredis_aio
from arq import ArqRedis

from server.worker import make_enqueue


@pytest.mark.asyncio(loop_scope="session")
async def test_enqueue_puts_job():
    fake = fakeredis_aio.FakeRedis()
    pool = ArqRedis(connection_pool=fake.connection_pool)
    enqueue = make_enqueue(pool)
    job = await enqueue("run-123")
    assert job is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_enqueue_forwards_function_and_arg():
    calls = []

    class SpyPool:
        async def enqueue_job(self, function, *args):
            calls.append((function, args))
            return "SENTINEL_JOB"

    enqueue = make_enqueue(SpyPool())
    result = await enqueue("run-abc")
    assert calls == [("process_run", ("run-abc",))]
    assert result == "SENTINEL_JOB"

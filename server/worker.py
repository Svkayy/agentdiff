from arq.connections import RedisSettings

from server.config import get_settings


def make_enqueue(pool):
    async def enqueue(run_id: str):
        return await pool.enqueue_job("process_run", run_id)

    return enqueue


async def process_run(ctx, run_id: str) -> None:
    # Body implemented in Task 2.2.
    return None


class WorkerSettings:
    functions = [process_run]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

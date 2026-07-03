"""arq background worker."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from arq import ArqRedis
from arq.connections import RedisSettings
from sqlalchemy import select

from server.config import get_settings
from server.db import async_session
from server.engine_runner import process_run_sync
from server.models import Finding, Run, Trajectory
from server.notify import maybe_post_slack


def make_enqueue(pool: ArqRedis):
    async def enqueue(run_id: str):
        return await pool.enqueue_job("process_run", run_id)

    return enqueue


def _session_factory(ctx):
    """Return the session factory from ctx (injectable in tests) or the real one."""
    return ctx.get("session_factory", async_session)


async def process_run(ctx, run_id: str) -> None:
    """Execute the agentdiff engine for a run and persist findings."""
    factory = _session_factory(ctx)
    async with factory() as session:
        run = (
            await session.execute(select(Run).where(Run.id == run_id))
        ).scalar_one()

        run.status = "processing"
        await session.commit()

        rows = (
            await session.execute(
                select(Trajectory).where(Trajectory.run_id == run.id)
            )
        ).scalars().all()

        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                verdict, finding_dicts = await loop.run_in_executor(
                    pool, process_run_sync, run, rows
                )
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            await session.commit()
            return

        for fd in finding_dicts:
            session.add(Finding(run_id=run.id, **fd))

        run.status = "done"
        run.verdict = verdict
        await session.commit()

        await maybe_post_slack(session, run, finding_dicts, verdict)


class WorkerSettings:
    functions = [process_run]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

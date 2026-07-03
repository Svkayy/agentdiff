"""arq background worker."""
from __future__ import annotations

import asyncio
import logging

from arq import ArqRedis, cron
from arq.connections import RedisSettings
from sqlalchemy import select

from server.config import get_settings
from server.db import async_session
from server.drift import check_drift_for_project
from server.engine_runner import process_run_sync
from server.models import Finding, LiveTrajectory, Run, Trajectory
from server.notify import maybe_post_slack, post_recovery

log = logging.getLogger("agentdiff.worker")


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

        # Extract plain data from ORM objects while the session is live,
        # so the thread receives no SQLAlchemy objects.
        config = run.config
        attribution = run.attribution
        traj_data = [
            {"side": r.side, "test_case_id": r.test_case_id, "payload": r.payload}
            for r in rows
        ]
        test_case_ids = sorted({r.test_case_id for r in rows})

        try:
            verdict, finding_dicts = await asyncio.to_thread(
                process_run_sync, config, attribution, traj_data, test_case_ids
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

        # A5 — Recovery notification: CI pass after previous CI warn/fail
        if verdict == "pass" and run.kind == "ci":
            prev_run = (
                await session.execute(
                    select(Run)
                    .where(
                        Run.project_id == run.project_id,
                        Run.status == "done",
                        Run.kind == "ci",
                        Run.created_at < run.created_at,
                    )
                    .order_by(Run.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if prev_run is not None and prev_run.verdict in {"warn", "fail"}:
                await post_recovery(session, run)


async def check_drift_all(ctx) -> None:
    """Cron job: run drift detection for every project with recent live traffic."""
    from datetime import timedelta, timezone
    from datetime import datetime

    factory = _session_factory(ctx)
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(minutes=2 * get_settings().drift_window_minutes)

    async with factory() as session:
        # Find all project_ids that have any LiveTrajectory in the last 2W
        rows = (
            await session.execute(
                select(LiveTrajectory.project_id)
                .where(LiveTrajectory.captured_at >= two_weeks_ago)
                .distinct()
            )
        ).scalars().all()

    project_ids = list(rows)
    log.info("drift sweep: checking %d projects", len(project_ids))

    for project_id in project_ids:
        try:
            async with factory() as session:
                run_id = await check_drift_for_project(session, project_id)
                if run_id:
                    log.info("drift run created: %s for project %s", run_id, project_id)
        except Exception as exc:  # noqa: BLE001
            log.error("drift check failed for project %s: %s", project_id, exc)


class WorkerSettings:
    functions = [process_run]
    cron_jobs = [cron(check_drift_all, minute=set(range(0, 60, 5)), run_at_startup=False)]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

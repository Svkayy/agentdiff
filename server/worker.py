"""arq background worker."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from arq import ArqRedis, cron, func
from arq.connections import RedisSettings
from sqlalchemy import delete, select

from server.config import get_settings
from server.db import async_session
from server.drift import check_drift_for_project
from server.engine_runner import run_engine
from server.metrics import METRICS
from server.models import Finding, LiveTrajectory, Run, Trajectory
from server.notify import maybe_post_slack, post_recovery

log = logging.getLogger("agentdiff.worker")

# Cron lease keys — a worker must acquire the lease (Redis SET NX EX) before it
# runs a cron body, so that when N worker replicas fire the same cron minute
# only one actually executes.  TTL is shorter than the cron interval so a crash
# can't hold the lease forever, but long enough to cover a normal run.
_DRIFT_LEASE_KEY = "agentdiff:cron:drift"
_RETENTION_LEASE_KEY = "agentdiff:cron:retention"
_LEASE_TTL_SECONDS = 240


# ── Optional Sentry ──────────────────────────────────────────────────────────
def _maybe_init_sentry() -> None:
    """Initialise Sentry if AGENTDIFF_SENTRY_DSN is set (guarded import)."""
    dsn = get_settings().sentry_dsn
    if not dsn:
        return
    try:
        import sentry_sdk  # noqa: PLC0415
    except ImportError:
        log.warning("AGENTDIFF_SENTRY_DSN set but sentry_sdk is not installed")
        return
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
    log.info("Sentry initialised")


def make_enqueue(pool: ArqRedis):
    async def enqueue(run_id: str):
        return await pool.enqueue_job("process_run", run_id)

    return enqueue


def _session_factory(ctx):
    """Return the session factory from ctx (injectable in tests) or the real one."""
    return ctx.get("session_factory", async_session)


async def _acquire_lease(ctx, key: str, ttl: int = _LEASE_TTL_SECONDS) -> bool:
    """Try to acquire a Redis SET NX EX lease; return True if acquired.

    ``ctx['redis']`` is the arq pool in production.  Tests may inject a fake
    redis via the same key.  Fails OPEN? No — a cron lease must FAIL CLOSED:
    if we cannot prove we hold the lease, we must not run the cron body, else
    N workers double-fire.  Absent redis (None) means single-process/test mode,
    so we allow the run.
    """
    redis = ctx.get("redis")
    if redis is None:
        return True
    try:
        acquired = await redis.set(key, "1", ex=ttl, nx=True)
        return bool(acquired)
    except Exception as exc:  # noqa: BLE001
        log.warning("cron lease acquire failed for %s: %s", key, exc)
        return False


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

        # Fold-in B: run the engine ONCE — findings + payload from a single
        # compare_all — instead of computing the comparison twice.
        try:
            verdict, finding_dicts, report_payload = await asyncio.to_thread(
                run_engine, config, attribution, traj_data, test_case_ids
            )
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            await session.commit()
            return

        # LLM explanation (default-on when AGENTDIFF_ANTHROPIC_API_KEY is set)
        from server.explain import explain_findings
        await explain_findings(finding_dicts, run=run)

        # Strip aggregation-only fields that are not stored as DB columns;
        # they live in statistical_evidence JSON for the reads endpoint.
        _finding_db_keys = {
            "test_case_id", "title", "verdict", "metric", "impact_summary",
            "statistical_evidence", "cause_path", "cause_rule", "cause_hunk", "explanation",
        }
        for fd in finding_dicts:
            db_fd = {k: v for k, v in fd.items() if k in _finding_db_keys}
            session.add(Finding(run_id=run.id, **db_fd))

        run.status = "done"
        run.verdict = verdict
        run.report_payload = report_payload
        await session.commit()

        METRICS.inc("agentdiff_runs_processed_total")

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
    """Cron job: run drift detection for every project with recent live traffic.

    Guarded by a Redis lease so that with N worker replicas only one executes
    the sweep per interval.
    """
    if not await _acquire_lease(ctx, _DRIFT_LEASE_KEY):
        log.debug("drift cron lease not acquired — another worker is running it")
        return

    factory = _session_factory(ctx)
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(
        minutes=2 * get_settings().drift_window_minutes
    )

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
                METRICS.inc("agentdiff_drift_checks_total")
                if run_id:
                    log.info("drift run created: %s for project %s", run_id, project_id)
        except Exception as exc:  # noqa: BLE001
            log.error("drift check failed for project %s: %s", project_id, exc)


async def cleanup_retention(ctx) -> None:
    """Cron job: delete Runs and LiveTrajectories past their retention window.

    ``AGENTDIFF_RETENTION_DAYS`` (default 90) governs Runs; ``0`` disables.
    ``AGENTDIFF_LIVE_RETENTION_DAYS`` (default 30) governs LiveTrajectories;
    ``0`` disables.  Guarded by a Redis lease so N workers don't double-delete.
    """
    if not await _acquire_lease(ctx, _RETENTION_LEASE_KEY):
        log.debug("retention cron lease not acquired — another worker is running it")
        return

    settings = get_settings()
    factory = _session_factory(ctx)
    now = datetime.now(timezone.utc)

    async with factory() as session:
        if settings.retention_days > 0:
            cutoff = now - timedelta(days=settings.retention_days)
            result = await session.execute(
                delete(Run).where(Run.created_at < cutoff)
            )
            log.info("retention: deleted %s runs older than %d days",
                     result.rowcount, settings.retention_days)

        if settings.live_retention_days > 0:
            live_cutoff = now - timedelta(days=settings.live_retention_days)
            result = await session.execute(
                delete(LiveTrajectory).where(LiveTrajectory.captured_at < live_cutoff)
            )
            log.info("retention: deleted %s live trajectories older than %d days",
                     result.rowcount, settings.live_retention_days)

        await session.commit()


_maybe_init_sentry()


class WorkerSettings:
    # process_run registered with max_tries=3 so a transient DB/Redis blip
    # retries rather than dropping the run.
    functions = [func(process_run, max_tries=3)]
    cron_jobs = [
        cron(check_drift_all, minute=set(range(0, 60, 5)), run_at_startup=False),
        cron(cleanup_retention, hour={3}, minute={0}, run_at_startup=False),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

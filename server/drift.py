"""Drift detection: compare live traffic windows and create drift Runs."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import get_settings
from server.engine_runner import process_run_sync
from server.models import Finding, LiveTrajectory, Run
from server.notify import maybe_post_slack

log = logging.getLogger("agentdiff.drift")

_DRIFT_EXPLANATION = (
    "No attributable code change in this window — if no deploy occurred, "
    "suspect upstream model/provider drift."
)


async def check_drift_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    window_minutes: int | None = None,
    min_samples: int | None = None,
) -> str | None:
    """Check for behavioral drift in live traffic for a project.

    Compares [now-2W, now-W) (baseline) against [now-W, now) (candidate) where
    W = window_minutes.  Returns the created Run id (str) on a warn/fail
    verdict, or None if there is insufficient data or no drift.
    """
    settings = get_settings()
    W = window_minutes if window_minutes is not None else settings.drift_window_minutes
    min_s = min_samples if min_samples is not None else settings.drift_min_samples

    now = datetime.now(timezone.utc)
    baseline_start = now - timedelta(minutes=2 * W)
    baseline_end = now - timedelta(minutes=W)
    candidate_start = baseline_end
    candidate_end = now

    # Load baseline window trajectories
    baseline_rows = (
        await session.execute(
            select(LiveTrajectory)
            .where(
                LiveTrajectory.project_id == project_id,
                LiveTrajectory.captured_at >= baseline_start,
                LiveTrajectory.captured_at < baseline_end,
            )
            .order_by(LiveTrajectory.captured_at)
        )
    ).scalars().all()

    candidate_rows = (
        await session.execute(
            select(LiveTrajectory)
            .where(
                LiveTrajectory.project_id == project_id,
                LiveTrajectory.captured_at >= candidate_start,
                LiveTrajectory.captured_at < candidate_end,
            )
            .order_by(LiveTrajectory.captured_at)
        )
    ).scalars().all()

    if len(baseline_rows) < min_s or len(candidate_rows) < min_s:
        log.debug(
            "project %s: insufficient samples (baseline=%d, candidate=%d, min=%d) — skipping",
            project_id,
            len(baseline_rows),
            len(candidate_rows),
            min_s,
        )
        return None

    # Find the most recent CI run for its config
    ci_run = (
        await session.execute(
            select(Run)
            .where(Run.project_id == project_id, Run.kind == "ci")
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if ci_run is None:
        log.debug("project %s: no prior CI run — cannot classify agents, skipping", project_id)
        return None

    config = ci_run.config

    # Build trajectory dicts, all with test_case_id="live_traffic"
    traj_data = []
    for row in baseline_rows:
        payload = dict(row.payload)
        payload["test_case_id"] = "live_traffic"
        traj_data.append({"side": "baseline", "test_case_id": "live_traffic", "payload": payload})
    for row in candidate_rows:
        payload = dict(row.payload)
        payload["test_case_id"] = "live_traffic"
        traj_data.append({"side": "candidate", "test_case_id": "live_traffic", "payload": payload})

    test_case_ids = ["live_traffic"]

    try:
        verdict, finding_dicts = await asyncio.to_thread(
            process_run_sync, config, None, traj_data, test_case_ids
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("project %s: engine error during drift check: %s", project_id, exc)
        return None

    if verdict == "pass":
        return None

    # Stamp the model-drift explanation on every finding
    for fd in finding_dicts:
        fd["cause_path"] = None
        fd["cause_rule"] = None
        fd["cause_hunk"] = None
        fd["explanation"] = _DRIFT_EXPLANATION

    baseline_ref = f"window[-{2*W}m,-{W}m)"
    candidate_ref = f"window[-{W}m,now)"

    drift_run = Run(
        project_id=project_id,
        idempotency_key=f"drift-{project_id}-{int(now.timestamp())}-{uuid4().hex[:8]}",
        baseline_ref=baseline_ref,
        candidate_ref=candidate_ref,
        tier="live",
        kind="drift",
        config=config,
        attribution=None,
        status="done",
        verdict=verdict,
    )
    session.add(drift_run)
    await session.flush()  # get drift_run.id

    for fd in finding_dicts:
        session.add(Finding(run_id=drift_run.id, **fd))

    await session.commit()

    await maybe_post_slack(
        session,
        drift_run,
        finding_dicts,
        verdict,
        extra_context={
            "window_minutes": W,
            "baseline_samples": len(baseline_rows),
            "candidate_samples": len(candidate_rows),
        },
    )

    log.info(
        "project %s: drift run %s created with verdict=%s findings=%d",
        project_id,
        drift_run.id,
        verdict,
        len(finding_dicts),
    )
    return str(drift_run.id)

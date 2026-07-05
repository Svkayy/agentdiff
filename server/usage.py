"""Usage metering and monthly quota enforcement.

Metering is per-org, per-calendar-month.  A ``UsageCounter`` row exists per
``(org_id, period)`` where ``period`` is ``YYYYMM`` (UTC).  Ingest increments
the counter on success and, for capped plans, rejects with 429 once the cap is
reached.

# ── Stripe / subscription seam ───────────────────────────────────────────────
# Plan is currently read straight off ``Org.plan`` (a String column set to
# "free" / "pro" / "unlimited").  When billing lands, this is where Stripe
# subscription state plugs in:
#
#   1. A Stripe webhook handler (customer.subscription.updated / .deleted)
#      writes the entitled plan tier onto ``Org.plan`` (or a dedicated
#      ``Subscription`` table keyed by ``Org.stripe_customer_id``).
#   2. ``_limits_for_plan`` below reads the tier — no change to the quota-check
#      call sites (ingest.py) is needed; they already consult ``check_quota``.
#   3. For usage-based billing, the ``UsageCounter`` rows are the metering
#      source of truth: a monthly job reports ``runs`` / ``trajectories`` per
#      org to Stripe's usage-record API before invoicing.
# Nothing below assumes a specific billing provider; only ``Org.plan`` and the
# env-configured free-tier caps are load-bearing today.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import get_settings
from server.models import Org, UsageCounter

# Plans that are not metered (no monthly cap).
_UNLIMITED_PLANS = {"pro", "unlimited"}


def current_period(now: datetime | None = None) -> str:
    """Return the current UTC billing period as ``YYYYMM``."""
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m")


@dataclass
class QuotaStatus:
    """Result of a quota check for one org in the current period."""

    plan: str
    period: str
    runs_used: int
    trajectories_used: int
    runs_limit: int | None  # None → unlimited
    trajectories_limit: int | None
    exceeded: bool
    # Which dimension tripped the limit ("runs" | "trajectories" | None).
    limiting_metric: str | None
    used: int | None
    limit: int | None


def _limits_for_plan(plan: str) -> tuple[int | None, int | None]:
    """Return ``(runs_limit, trajectories_limit)`` for a plan; None = unlimited."""
    if plan in _UNLIMITED_PLANS:
        return None, None
    settings = get_settings()
    return settings.free_runs_per_month, settings.free_trajectories_per_month


async def increment_usage(
    session: AsyncSession,
    org_id,
    runs: int = 0,
    trajectories: int = 0,
) -> None:
    """Atomically add to the org's usage counter for the current period.

    UPSERT on ``(org_id, period)`` — a concurrent first-write race resolves to
    a single row and both writers' deltas are applied (``+=`` on conflict).
    """
    if runs == 0 and trajectories == 0:
        return
    period = current_period()
    stmt = pg_insert(UsageCounter).values(
        org_id=org_id,
        period=period,
        runs=runs,
        trajectories=trajectories,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["org_id", "period"],
        set_={
            "runs": UsageCounter.runs + stmt.excluded.runs,
            "trajectories": UsageCounter.trajectories + stmt.excluded.trajectories,
        },
    )
    await session.execute(stmt)
    await session.commit()


async def _current_counter(session: AsyncSession, org_id, period: str) -> UsageCounter | None:
    from sqlalchemy import select

    return (
        await session.execute(
            select(UsageCounter).where(
                UsageCounter.org_id == org_id,
                UsageCounter.period == period,
            )
        )
    ).scalar_one_or_none()


async def check_quota(session: AsyncSession, org: Org) -> QuotaStatus:
    """Return the org's quota status for the current period.

    ``exceeded`` is True when a capped plan has met-or-passed either its runs
    or trajectories limit.  Unlimited plans always report ``exceeded=False``
    with ``None`` limits.
    """
    period = current_period()
    runs_limit, traj_limit = _limits_for_plan(org.plan)
    counter = await _current_counter(session, org.id, period)
    runs_used = counter.runs if counter else 0
    traj_used = counter.trajectories if counter else 0

    limiting_metric: str | None = None
    used: int | None = None
    limit: int | None = None
    exceeded = False

    if runs_limit is not None and runs_used >= runs_limit:
        exceeded = True
        limiting_metric = "runs"
        used = runs_used
        limit = runs_limit
    elif traj_limit is not None and traj_used >= traj_limit:
        exceeded = True
        limiting_metric = "trajectories"
        used = traj_used
        limit = traj_limit

    return QuotaStatus(
        plan=org.plan,
        period=period,
        runs_used=runs_used,
        trajectories_used=traj_used,
        runs_limit=runs_limit,
        trajectories_limit=traj_limit,
        exceeded=exceeded,
        limiting_metric=limiting_metric,
        used=used,
        limit=limit,
    )

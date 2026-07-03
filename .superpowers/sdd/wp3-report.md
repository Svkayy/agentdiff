# WP3 Report — Tier 3 Live Production Monitoring

**Date:** 2026-07-03  
**Branch:** feat/report-ui  
**Commits:** ff1fc6e, 402fc66, cb4d569

---

## Piece 1 — Schema (models + alembic)

**What was done:**
- Added `kind: Mapped[str]` column to `Run` (`String(16)`, default `"ci"`, `server_default="ci"`). Values: `ci` | `drift`.
- Added `LiveTrajectory` model: `id UUID pk`, `project_id FK→projects.id` (indexed), `payload JSONB`, `captured_at DateTime(timezone=True)` (indexed, default `_now()`).
- Added `live_trajectories` relationship to `Project`.
- Added `Index` import to models.py.
- Wrote alembic revision `c1a2b3d4e5f6` manually (autogenerate was blocked by the async `env.py` pattern — `asyncio.run()` nested inside alembic's synchronous runner; the schema was applied via `Base.metadata.create_all` on the main DB and stamped).

**Design decision:** The test conftest uses `Base.metadata.create_all`, so tests pick up the new schema automatically without touching the alembic version.

**Files changed:** `server/models.py`, `server/config.py`, `server/migrations/versions/c1a2b3d4e5f6_live_trajectories_run_kind.py`

---

## Piece 2 — Live Ingest Endpoint

**What was done:**
- `server/routes/traffic.py`: `POST /v1/traffic` — API-key auth via `get_project_from_api_key`, body `TrafficUpload(trajectories: list[dict], max_length=1000)`, rate-limit key `rl:traffic:{project.id}` using `rate_limit_traffic_per_minute=600`, stores each payload as a `LiveTrajectory`, returns `202 {accepted: N}`.
- Registered in `server/main.py`.
- Added `rate_limit_traffic_per_minute: int = 600`, `drift_window_minutes: int = 60`, `drift_min_samples: int = 10`, `drift_check_interval_minutes: int = 5` to `Settings`.

**Files changed:** `server/routes/traffic.py` (new), `server/main.py`, `server/config.py`

---

## Piece 3 — Drift Detection

**What was done:**
- `server/drift.py`: `async def check_drift_for_project(session, project_id, *, window_minutes, min_samples) -> str | None`.
  - Baseline window `[now-2W, now-W)`, candidate `[now-W, now)`.
  - Guards: `< min_samples` → `None`; no prior CI run → `None`.
  - Injects `test_case_id="live_traffic"` into every payload dict before engine call.
  - Calls `process_run_sync` via `asyncio.to_thread` (same pattern as worker).
  - Pass verdict → `None`.
  - Warn/fail: stamps every finding with `cause_path=None, cause_rule=None, cause_hunk=None, explanation="No attributable code change..."`.
  - Creates `Run(kind="drift", ...)`, persists findings, calls `maybe_post_slack`.
- `server/worker.py`: `check_drift_all(ctx)` cron — queries distinct project IDs with `LiveTrajectory.captured_at >= now-2W`, iterates each with isolated `try/except`, calls `check_drift_for_project`. `WorkerSettings.cron_jobs = [cron(check_drift_all, minute={0,5,10,...,55})]`.

**Design decision:** The synthetic test case `"live_traffic"` treats the entire window as one case, so `compare_all` computes invocation-rate delta across the pool. The engine requires trajectories with matching `version_tag` values (`baseline`/`candidate`) — these are set via the `TrajectorySet` in `engine_runner._to_set()`, not from the payload. The payload's `version_tag` field is overwritten by the side label.

**Files changed:** `server/drift.py` (new), `server/worker.py`

---

## Piece 4 — Live Collector Client

**What was done:**
- `collector/live.py`: `class LiveCollector(api_url, api_key, *, flush_every=20, post_fn=None)`.
  - `record(trajectory: dict)`: appends to buffer; grabs batch and flushes outside the lock when `len(buffer) >= flush_every` (thread-safe via `threading.Lock`).
  - `flush()`: drains buffer and POSTs; fail-soft on any exception (log warning + drop batch).
  - `install()`: no-op if `agentdiff.capture.activator` is unavailable; logs debug.
  - Injectable `post_fn` for testing; default uses `httpx.post` (lazy import).

**Files changed:** `collector/live.py` (new)

---

## Piece 5 — Tests

**What was done:**

### tests/server/test_traffic.py (3 tests)
- `test_traffic_post_stores_rows_returns_202`: authenticated POST, checks DB count.
- `test_traffic_bad_key_returns_401`.
- `test_traffic_batch_over_1000_returns_422`.

### tests/server/test_drift.py (5 tests)
- `test_check_drift_creates_run_on_warn_fail`: 12 baseline (firing) + 12 candidate (silent) → drift Run created, `kind=drift`, `verdict in {warn, fail}`, ≥1 finding, all with model-drift explanation.
- `test_check_drift_slack_posted_on_warn_fail`: SlackConfig present → `SlackClient.post_payload` called once.
- `test_check_drift_no_run_when_under_min_samples`: 3 rows → `None`.
- `test_check_drift_no_ci_run_returns_none`: no CI run → `None`.
- `test_check_drift_pass_verdict_returns_none`: both windows firing → `None`.

### tests/collector/test_live.py (7 tests)
- Buffer, auto-flush at threshold, bearer token, URL, fail-soft error swallowed, empty flush noop.

**Test results:** 70 passed (55 prior + 15 new). Ruff: clean.

---

## Self-Review

**What went well:**
- The engine trajectory fixture pattern from `test_worker.py` translated cleanly — same `LLMRequestEvent` + `inferred_agent` = `"Fact Checker"` approach produces real drift signal.
- The `process_run_sync` / `asyncio.to_thread` path was reused as-is; no duplication.
- Fail-soft patterns consistent across traffic endpoint, drift engine call, Slack notify, and collector flush.

**Concerns / known gaps:**

1. **Alembic async env.py** — The existing env.py uses `asyncio.run()` which conflicts with alembic's synchronous context. Migration was written manually and schema applied via `Base.metadata.create_all`. The env.py should be fixed to use `run_sync` with a sync engine for true alembic compatibility; deferred to a separate PR.

2. **Idempotency on drift runs** — The `idempotency_key` uses `drift-{project_id}-{timestamp_seconds}`. If two cron ticks land within the same second (unlikely at 5-min interval) they'd conflict. A UUID suffix would be safer but complicates deduplication.

3. **`install()` is a no-op stub** — The ambient wiring (`agentdiff.capture.activator`) doesn't exist yet; the method degrades gracefully with a debug log. This is by design per spec but noted for future wiring.

4. **Engine `version_tag` vs payload tag** — The drift engine call uses side labels ("baseline"/"candidate") set by `_to_set()`, not the payload's `version_tag` field. Any `version_tag` in stored live payload dicts is ignored at engine time (which is correct).

---

## Files Changed Summary

| File | Type | Description |
|------|------|-------------|
| `server/models.py` | modified | Run.kind, LiveTrajectory model, Project relationship |
| `server/config.py` | modified | Rate limit + drift settings |
| `server/migrations/versions/c1a2b3d4e5f6_live_trajectories_run_kind.py` | new | Alembic migration |
| `server/routes/traffic.py` | new | POST /v1/traffic endpoint |
| `server/main.py` | modified | Register traffic router |
| `server/drift.py` | new | check_drift_for_project() |
| `server/worker.py` | modified | check_drift_all cron + WorkerSettings.cron_jobs |
| `collector/live.py` | new | LiveCollector class |
| `tests/server/test_traffic.py` | new | 3 traffic tests |
| `tests/server/test_drift.py` | new | 5 drift tests |
| `tests/collector/test_live.py` | new | 7 collector tests |

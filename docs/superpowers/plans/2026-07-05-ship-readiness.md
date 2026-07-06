# Ship-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve every gap from the 2026-07-05 product audit: capture redaction, statistical rigor, new behavioral metrics (latency/tokens/error-rate) surfaced end-to-end, hosted-platform hardening (CRUD, pagination, quotas, audit, retention, TLS deploy), the full report experience in the hosted dashboard, landing→login wiring, a LangChain-style Docs tab, and release governance.

**Architecture:** Six workstreams over one branch (`feat/ship-readiness`). WS0 lands all new config schema first so later tasks never contend on `config.py`. Python engine changes (WS1/WS2) flow into the server (WS3) via the shared `report_payload`; the hosted dashboard (WS4) consumes new server endpoints; landing (WS5) and governance (WS6) are independent.

**Tech Stack:** Python 3.10+ (Pydantic v2, Click, FastAPI, SQLAlchemy async, Alembic, arq), React 18 + Vite + Tailwind (frontend, landing), `marked` for docs rendering, GitHub Actions.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-05-ship-readiness-design.md` — read it before any task.
- Follow existing code style; UI work must follow `DESIGN.md`.
- Every Python task lands with pytest coverage; gates are `.venv/bin/ruff check src/ tests/`, `.venv/bin/mypy src/agentdiff`, `.venv/bin/pytest tests/ -q`.
- Frontend gates: `npm --prefix frontend run build` (+ vitest where present); landing gate: `npm --prefix landing run build`.
- Never print or commit values from `.env`. Never weaken existing tests to make them pass.
- Commit after each task with a conventional message ending in the Claude co-author trailer.
- New list endpoints return `{"items": [...], "total": N}` (breaking change is fine; we own both sides).

---

### Task 1 (WS0): Config schema for everything downstream

**Files:**
- Modify: `src/agentdiff/config.py`
- Test: `tests/test_config.py`

**Interfaces (produced — later tasks import these names):**
- `RedactionConfig`: `mode: Literal["standard","strict","off"] = "standard"`, `patterns: list[str] = []`, `redact_fields: list[str] = []`, `capture_raw_bodies: bool = False`; attached as `CaptureConfig.redaction`.
- `SamplingConfig` gains `timeout_seconds: float = 300.0` (0 disables), `retries: int = 1`, `retry_backoff_seconds: float = 2.0` (validators: non-negative).
- Thresholds config gains `latency_ms`, `tokens`, `error_rate` as `MetricThreshold` fields (defaults: latency warn 1000/fail 5000 ms delta; tokens warn 200/fail 1000; error_rate warn 0.1/fail 0.25).
- New `StatsConfig`: `correction: Literal["benjamini_hochberg","none"] = "benjamini_hochberg"`, `alpha: float = 0.05`, `min_samples_warn: int = 5`; attached as `AgentDiffConfig.stats`.
- New `OutputEvalThresholds`: `semantic_fail=0.70, semantic_warn=0.85, length_fail=0.50, length_warn=0.80, structural_fail=0.70, structural_warn=0.90, judge_fail=2.0, judge_warn=3.5`; attached as `AgentDiffConfig.output_eval`.

- [ ] Write failing tests in `tests/test_config.py`: defaults load from empty YAML; each new field round-trips from YAML; invalid values (negative timeout, alpha outside (0,1], unknown correction) raise.
- [ ] Run: `.venv/bin/pytest tests/test_config.py -q` — expect failures on missing fields.
- [ ] Implement the models following the file's existing Pydantic patterns and docstrings; update `docs/reference-config.md` with every new option (type, default, effect).
- [ ] Run config tests, then full gates. Commit: `feat(config): redaction, sampling resilience, stats, and output-eval config surface`.

### Task 2 (WS1): Redaction layer

**Files:**
- Modify: `src/agentdiff/capture/http/redact.py` (extend), `src/agentdiff/capture/http/httpx_shim.py`, `requests_shim.py`, `aiohttp_shim.py`, `src/agentdiff/capture/sdk/anthropic_shim.py`, `openai_shim.py`
- Test: `tests/test_redaction.py` (new)

**Interfaces (produced):**
- `redact.py`: `SECRET_PATTERNS: list[re.Pattern]` (OpenAI `sk-[A-Za-z0-9]{20,}`, Anthropic `sk-ant-…`, Slack `xox[bpars]-…`, `Bearer <token>`, AWS `AKIA[0-9A-Z]{16}`, PEM blocks, generic `api[_-]?key\s*[:=]\s*\S+`), `redact_text(text: str, cfg: RedactionConfig) -> str`, `redact_headers(headers: Mapping[str, str], cfg) -> dict[str, str]` (drops/masks Authorization, X-Api-Key, Api-Key, Cookie always unless mode=="off"), `redact_body(body: bytes | str, cfg) -> bytes | str`, `redact_canonical(call: CanonicalLLMCall, cfg) -> CanonicalLLMCall` (masks secrets in system/messages/tool args; `strict` mode replaces message/system content with `sha256:<hex>` digests).
- Behavior: applied at event-build time in all shims before events reach the tracer; raw-body capture for unknown providers only when `capture_raw_bodies=True`; `mode=="off"` bypasses everything except it still never stores Authorization headers is FALSE — off means off, documented loudly.

- [ ] Write failing tests: each secret pattern masked in text/body/canonical; Authorization header dropped in standard mode; strict mode hashes message content but keeps roles/counts; off mode passes through; unknown-provider raw body absent by default and present when `capture_raw_bodies: true`.
- [ ] Run `.venv/bin/pytest tests/test_redaction.py -q` — expect import errors/failures.
- [ ] Implement `redact.py` functions; thread `RedactionConfig` from active config through each shim's event construction (find where `LLMRequestEvent`/`LLMResponseEvent`/canonical are built; redact immediately before event creation). Keep existing query-string stripping.
- [ ] Verify existing capture tests still pass (`tests/test_http_shim.py`, `tests/test_sdk_shims.py`, `tests/test_capture_path.py`), full gates. Commit: `feat(capture): default-on secret redaction across HTTP and SDK shims`.

### Task 3 (WS1): Loud degradation + sampling resilience + fast-fail validation

**Files:**
- Modify: `src/agentdiff/capture/activator.py`, `src/agentdiff/capture/framework/base.py`, `src/agentdiff/capture/http/provider_registry.py`, `src/agentdiff/sampling.py`, `src/agentdiff/cli/compare.py`, `src/agentdiff/cli/ci.py`, `src/agentdiff/capture/session.py`, `src/agentdiff/cli/quickstart.py`
- Test: `tests/test_capture_warnings.py` (new), extend `tests/test_sampling.py`

**Interfaces (produced):**
- `activator.install()` emits one `warnings.warn(..., AgentDiffCaptureWarning)` per enabled-but-unavailable shim; new `AgentDiffCaptureWarning(UserWarning)` exported from `agentdiff.capture`.
- `sampling`: per-sample timeout via `concurrent.futures` `future.result(timeout=cfg.sampling.timeout_seconds)` (0 disables); timed-out/failed samples retried up to `cfg.sampling.retries` with `retry_backoff_seconds * attempt` sleep; timeout failures count toward the failure budget with message `"sample timed out after Ns"`.
- `compare`/`ci`: before sampling, import the runner module/callable and exit 1 with the doctor hint (`Run 'agentdiff doctor' — could not import <module>: <error>`) on failure.
- `session.record()`: when truncating an existing capture file, print `[yellow]Overwriting existing capture '<name>' at <path> (record() truncates per process; use a new name to keep it).`
- `quickstart`: when writing the NotImplementedError template, print the absolute template path and the line to edit.

- [ ] Failing tests: enabled `httpx` flag with import monkeypatched away → warning emitted once; provider-yaml bad regex → logged skip (caplog); sample that sleeps beyond a 0.1s timeout fails with the timeout message and retries N times; runner import failure in `compare` exits 1 mentioning the module.
- [ ] Implement; run gates. Commit: `feat(cli,capture): loud capture degradation, sample timeout/retry, fast-fail runner validation`.

### Task 4 (WS1): Implement `agentdiff structure` (refresh & merge)

**Files:**
- Modify: `src/agentdiff/cli/structure.py`, `src/agentdiff/structure/structure_yaml.py`
- Test: `tests/test_structure_refresh.py` (new)

**Interfaces (produced):**
- `structure_yaml.merge_structures(existing: StructureDoc, fresh: StructureDoc) -> tuple[StructureDoc, StructureDiff]` where `StructureDiff` is a dataclass with `added: list[str]`, `removed: list[str]`, `kept: list[str]`; merge keeps user-edited display names/roles for entries whose `file:qualname` still exists, adds new candidates, drops vanished ones.
- CLI `agentdiff structure` (no longer a stub): re-runs the same inference as `init`, merges, writes `structure.yaml`, prints an added/removed/kept summary; `--dry-run` prints without writing.

- [ ] Failing tests: merge preserves a renamed display name for an existing agent; new function appears in `added`; deleted function lands in `removed`; `--dry-run` leaves the file untouched (CliRunner).
- [ ] Implement; update the README CLI table (remove "stub in v0" for `structure`). Run gates. Commit: `feat(cli): implement 'agentdiff structure' refresh with user-edit-preserving merge`.

### Task 5 (WS1): Implement `agentdiff replay`

**Files:**
- Modify: `src/agentdiff/cli/replay.py`
- Test: `tests/test_replay_cli.py` (new)

**Interfaces (produced):**
- `agentdiff replay --cassette PATH [--report-dir PATH] [--samples N]`: loads config + test cases, runs the runner for each case with the cassette in replay mode (reuse `capture/cassette.py` plumbing exactly as `ci --tier hermetic` does), writes a fresh report directory, exits 1 with the missing-request key when `CassetteMissError` fires (message tells the user to re-record with `agentdiff ci run --cassette-mode record`).

- [ ] Failing tests: replay with a recorded cassette (reuse the cassette fixtures from `tests/test_cassette.py` / `tests/test_ci_cli.py`) produces trajectories identical across two invocations; missing cassette → exit 1 naming the path; cassette miss → exit 1 naming the request.
- [ ] Implement by extracting the hermetic-sampling path already used in `cli/ci.py` into a shared helper both commands call (DRY — do not duplicate). Update README CLI table. Run gates. Commit: `feat(cli): implement 'agentdiff replay' for deterministic cassette re-runs`.

### Task 6 (WS2): Latency, token, and error-rate deltas end-to-end

**Files:**
- Modify: `src/agentdiff/compare.py`, `src/agentdiff/report.py`, `src/agentdiff/report_payload.py`, `src/agentdiff/incident/findings.py`, `frontend/src/types.ts` (type additions only)
- Test: extend `tests/test_compare.py`, `tests/test_report_payload.py`

**Interfaces (produced):**
- `compare.py` emits three new delta records per test case in the comparison result, following the existing tool-usage delta shape, with `metric` values `"latency_ms"`, `"total_tokens"`, `"error_rate"`: latency/tokens use Mann-Whitney over per-trajectory `total_latency_ms`/`total_tokens`; error_rate uses the existing two-proportion test over `status != "success"`; verdicts from Task 1 thresholds.
- `report_payload` gains `run_metrics` entries so the dashboard can render them: for each new metric `{metric, baseline_mean, candidate_mean, delta, p_value, adjusted_p_value, verdict, low_power}`.
- `frontend/src/types.ts`: matching optional fields added to the payload types (no UI yet — Task 13 renders them).

- [ ] Failing tests: two synthetic trajectory sets with a large latency shift → latency delta FAIL with p < 0.05; identical sets → PASS p=1.0; error-rate delta fires when candidate has failures; payload includes the three metrics with the exact field names above.
- [ ] Implement; ensure `report.md` gets a "Runtime deltas" section listing the three metrics. Run gates. Commit: `feat(compare): latency, token, and error-rate behavioral deltas`.

### Task 7 (WS2): Statistical rigor — BH correction, sample-size warnings

**Files:**
- Modify: `src/agentdiff/stats.py`, `src/agentdiff/compare.py`, `src/agentdiff/report.py`, `src/agentdiff/report_payload.py`
- Test: extend `tests/test_stats.py`, `tests/test_compare.py`

**Interfaces (produced):**
- `stats.benjamini_hochberg(pvalues: Sequence[float]) -> list[float]` — returns adjusted p-values, monotone, clipped to 1.0. Reference implementation:

```python
def benjamini_hochberg(pvalues: Sequence[float]) -> list[float]:
    n = len(pvalues)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvalues[i])
    adjusted = [0.0] * n
    running_min = 1.0
    for rank_from_end, idx in enumerate(reversed(order)):
        rank = n - rank_from_end
        value = min(running_min, pvalues[idx] * n / rank)
        running_min = value
        adjusted[idx] = min(value, 1.0)
    return adjusted
```

- Every delta in a comparison gets `adjusted_p_value`; significance/verdict-downgrade logic switches to adjusted p when `config.stats.correction == "benjamini_hochberg"`; raw p retained.
- Deltas with per-side n < `config.stats.min_samples_warn` get `low_power: True`; report and payload carry a run-level `warnings: list[str]` including a low-power notice.

- [ ] Failing tests: BH on `[0.01, 0.02, 0.03, 0.04]` returns `[0.04, 0.04, 0.04, 0.04]`; empty list → `[]`; a delta significant at raw p but not adjusted p is downgraded to warn; n=3 sides set `low_power` and the run warning.
- [ ] Implement; document the correction in `docs/METHODOLOGY.md`. Run gates. Commit: `feat(stats): Benjamini-Hochberg correction and low-power warnings`.

### Task 8 (WS2): Attribution confidence, eval-completeness, judge hardening, configurable eval thresholds

**Files:**
- Modify: `src/agentdiff/attribution/engine.py`, `src/agentdiff/attribution/rules.py`, `src/agentdiff/output_eval.py`, `src/agentdiff/llm_client.py`, `src/agentdiff/report.py`, `src/agentdiff/report_payload.py`, `src/agentdiff/incident/renderers.py`
- Test: extend `tests/test_attribution.py`, `tests/test_output_eval.py`, `tests/test_llm_client.py`

**Interfaces (produced):**
- Attribution results gain `confidence: Literal["high","medium","low"]` (weight ≥ 0.7 high, ≥ 0.5 medium, else low); renderers append `(low-confidence heuristic)` for low.
- `output_eval` result gains `skipped_checks: list[dict]` (`{check, reason}` e.g. `{"check": "semantic", "reason": "sentence-transformers not installed"}`); report/payload surface them; thresholds read from `config.output_eval` (Task 1) instead of module constants.
- Judge: prompt demands `{"score": <1-5>, "reason": "<short>"}` JSON; parse via `json.loads` with one retry on failure; result distinguishes `{"status": "ok"|"error", ...}`; `llm_client.generate()` returns `LLMResult(text: str | None, error: str | None)` instead of bare `""`, and falls back anthropic→openai (or reverse) when the primary provider errors and the other key is configured.

- [ ] Failing tests: rule-5 attribution → `confidence == "low"` and renderer includes the label; missing embeddings → `skipped_checks` entry (monkeypatch import); judge non-JSON reply retried then `status="error"`; provider fallback used when primary raises; custom `output_eval` thresholds from config change a verdict.
- [ ] Implement; run gates. Commit: `feat(eval,attribution): confidence labels, eval-completeness signals, hardened judge`.

### Task 9 (WS2): Storage WAL + schema versioning

**Files:**
- Modify: `src/agentdiff/storage.py`
- Test: extend `tests/test_storage.py`

**Interfaces:** connections opened with `PRAGMA journal_mode=WAL`; `schema_version` table written as 1 on create; opening a DB with a newer version raises `StorageVersionError` naming both versions.

- [ ] Failing tests: new DB has WAL mode + version 1; version bumped to 99 → `StorageVersionError`.
- [ ] Implement; run gates. Commit: `feat(storage): WAL mode and schema version guard`.

### Task 10 (WS3): Server models, migration, run payload endpoint

**Files:**
- Modify: `server/models.py`, `server/worker.py`, `server/engine_runner.py`, `server/routes/reads.py`, `server/schemas.py`
- Create: `server/migrations/versions/<gen>_ship_readiness.py` (single revision)
- Test: `tests/server/test_payload.py` (new), extend `tests/server/test_reads.py`

**Interfaces (produced):**
- Model changes (one Alembic revision, autogenerate then hand-check): `Run.report_payload` (JSONB, nullable), `ApiKey.name` (String(120), nullable), `Org.plan` (String(20), default `"free"`), new `AuditLog` (id, org_id FK, actor, action, target_type, target_id, meta JSONB, created_at, index on (org_id, created_at)), new `UsageCounter` (org_id FK, period `"YYYYMM"`, runs int, trajectories int, unique (org_id, period)).
- `process_run` builds the full report payload via the engine's `report_payload` builder and stores it on `Run.report_payload`.
- `GET /v1/runs/{run_id}/payload` (Clerk auth, org check) → the JSON payload; 404 while `report_payload IS NULL` with body `{"detail": "payload not ready"}`.

- [ ] Failing tests (existing server fixtures): processed run exposes payload with `run_metrics` keys from Task 6; unauthorized org → 404; unprocessed run → 404 "payload not ready".
- [ ] Implement + migration; run server suite (`.venv/bin/pytest tests/server -q`) and full gates. Commit: `feat(server): run report payload storage and endpoint, ship-readiness schema`.

### Task 11 (WS3): CRUD, pagination/search, key names, audit log

**Files:**
- Modify: `server/routes/manage.py`, `server/routes/reads.py`, `server/schemas.py`
- Create: `server/audit.py` (`async def record_audit(session, org_id, actor, action, target_type, target_id, meta=None)`)
- Test: extend `tests/server/test_manage.py`, `tests/server/test_reads.py`

**Interfaces (produced — frontend consumes exactly these):**
- `PATCH /v1/projects/{id}` body `{"name": str}` → ProjectOut; `DELETE /v1/projects/{id}` → 204 (cascade); `DELETE /v1/runs/{id}` → 204.
- `GET /v1/projects?q=` and `GET /v1/projects/{id}/runs?limit=50&offset=0&verdict=pass|warn|fail&q=` → `{"items": [...], "total": int}` (limit clamped to 200).
- `POST /v1/projects/{id}/keys` body `{"name": str|null}`; key listings include `name`.
- `GET /v1/projects/{id}/audit?limit&offset` → `{"items": [{id, actor, action, target_type, target_id, meta, created_at}], "total"}`.
- Audit written on: project create/rename/delete, key mint/revoke, Slack connect/disconnect (manual + OAuth), run delete. Actor = Clerk user id.

- [ ] Failing tests per endpoint incl. cross-org 404s, pagination totals, verdict filter, audit rows written with correct action strings (`project.created`, `project.renamed`, `project.deleted`, `key.minted`, `key.revoked`, `slack.connected`, `slack.disconnected`, `run.deleted`).
- [ ] Implement; run gates. Commit: `feat(server): project/run CRUD, pagination and search, named keys, audit log`.

### Task 12 (WS3): Usage metering, quotas, ops hardening

**Files:**
- Modify: `server/routes/ingest.py`, `server/routes/traffic.py`, `server/config.py`, `server/main.py`, `server/worker.py`, `server/drift.py`, `server/routes/reads.py`, `docker-compose.yml`, `.env.example`
- Create: `server/usage.py`, `server/metrics.py`, `docker-compose.prod.yml`, `deploy/nginx.conf`, `docs/deploy-production.md`
- Test: `tests/server/test_usage.py` (new), extend `tests/server/test_hardening.py`

**Interfaces (produced):**
- `server/usage.py`: `async def increment_usage(session, org_id, runs=0, trajectories=0)` (UPSERT on (org_id, period)); `async def check_quota(session, org) -> QuotaStatus` with plan limits from env (`AGENTDIFF_FREE_RUNS_PER_MONTH=500`, `AGENTDIFF_FREE_TRAJECTORIES_PER_MONTH=50000`; `pro`/`unlimited` → no cap). Ingest returns 429 `{"detail": "monthly quota exceeded", "plan": ..., "used": ..., "limit": ...}` + `X-Quota-Limit/Remaining` headers when exceeded. Stripe seam: one comment block in `usage.py` describing where subscription state would plug in.
- `GET /v1/usage` (Clerk) → `{"plan", "period", "runs_used", "runs_limit", "trajectories_used", "trajectories_limit"}` (`null` limits for unlimited).
- `/health` → `{"status": "ok"|"degraded", "checks": {"database": bool, "redis": bool}}`, HTTP 503 when degraded.
- `/metrics` → Prometheus text (counters: `agentdiff_requests_total{path,method,status}`, `agentdiff_runs_processed_total`, `agentdiff_drift_checks_total`, `agentdiff_quota_rejections_total`) via a tiny in-process registry in `server/metrics.py` (no new hard dependency).
- Worker: daily retention cron (`AGENTDIFF_RETENTION_DAYS=90`, `AGENTDIFF_LIVE_RETENTION_DAYS=30`, 0 disables) deleting old Runs/LiveTrajectories; drift + retention crons guarded by Redis `SET NX EX 240` lease keys (`agentdiff:cron:drift`, `agentdiff:cron:retention`); `process_run` registered with `max_tries=3`; drift projects below `min_samples` reported via `stats` endpoint field `drift_status: "ok"|"insufficient_samples"|"disabled"`; optional `sentry_sdk.init` when `AGENTDIFF_SENTRY_DSN` set (guarded import).
- `docker-compose.prod.yml`: nginx TLS proxy (`deploy/nginx.conf`, certs mounted from `./deploy/certs`, HSTS, http→https redirect), one-shot `migrate` service (`alembic upgrade head`) that api/worker `depends_on: service_completed_successfully`; API container no longer migrates at boot in prod file. `docs/deploy-production.md`: TLS/certbot, backups (pg_dump cron + tested restore steps), scaling notes, CORS tightening, secret rotation (MultiFernet walkthrough; Slack/Clerk rotation steps).

- [ ] Failing tests: quota exceeded → 429 + headers + counter row correct; `/v1/usage` math; health degraded when DB ping monkeypatched to fail; retention deletes only old rows; cron lease prevents double-fire (two invocations, one executes); metrics endpoint exposes counters.
- [ ] Implement; run gates. Commit: `feat(server): usage quotas, retention, cron leases, health/metrics, prod TLS deploy`.

### Task 13 (WS4): Dashboard — API client, auth, lists, CRUD, usage, audit

**Files:**
- Modify: `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`, `frontend/src/pages/ProjectsPage.tsx`, `frontend/src/pages/ProjectPage.tsx`, `frontend/src/components/Shell.tsx`, `frontend/src/types.ts`
- Create: `frontend/src/lib/auth.ts`

**Interfaces (consumed):** Task 11/12 endpoints verbatim.
**Interfaces (produced):** `api.ts` adds `fetchRunsPage(projectId, {limit, offset, verdict, q})`, `renameProject`, `deleteProject`, `deleteRun`, `fetchUsage`, `fetchAudit`, `mintKey(projectId, name)`, `fetchRunPayload(runId)`; central `handleApiError` → on 401 calls `onUnauthorized()` from `auth.ts` (Clerk signOut + redirect + toast message "Session expired — please sign in again").

- [ ] Extend `api.test.ts` (vitest) for every new client function incl. 401 → onUnauthorized.
- [ ] UI: runs table gains search input, verdict filter chips, "Load more" with `total`; projects grid gains search; project header gains rename (inline) + delete (typed-confirmation modal); runs rows get delete; key mint prompts for a name and listing shows it; Setup tab gains Usage panel (plan, bars, current period) + Audit table (paginated); Shell shows org name from `fetchMe()`; StatsBar shows a visible error state with retry instead of silent skeleton.
- [ ] Gate: `npm --prefix frontend run build` + vitest pass. Commit: `feat(dashboard): pagination/search, CRUD, usage panel, audit log, session-expiry handling`.

### Task 14 (WS4): Dashboard — full report experience + new metrics + polish

**Files:**
- Modify: `frontend/src/pages/RunDetailPage.tsx`, `frontend/src/sections/*.tsx`, `frontend/src/lib/payload.ts`, `frontend/src/components/AgentGraph.tsx`, `frontend/src/components/nodes/GraphNodeCard.tsx`, ProjectPage Slack/reveal-key bits
- Create: `frontend/src/lib/payloadAdapter.ts`

**Interfaces:** `payloadAdapter.ts` exports `toReportData(raw: unknown): ReportData` mapping `GET /v1/runs/{id}/payload` JSON onto the existing `ReportData` type consumed by the five section components; sections take `data: ReportData` as a prop (refactor away their direct `useReportData()` calls; the CLI single-file entry keeps working by passing `useReportData()` result at the top).

- [ ] RunDetailPage: tab bar (Overview / Behavioral Deltas / Attribution / Timeline / Summary) rendering the five existing section components from the payload; loading/error/"payload not ready" (poll every 5s while run pending) states; keep the current graph inside Overview.
- [ ] New metrics: latency/token/error-rate deltas render in Behavioral Deltas + Overview stat chips; run-level `warnings` (low-power) and `skipped_checks` (eval incomplete) render as amber banners; attribution confidence labels visible on findings and attribution cards.
- [ ] Export/share: "Download JSON" (payload blob) + "Copy link" buttons.
- [ ] Polish: graph min-width responsive (`min-w-0` on mobile, 620px only ≥md) with nodes keyboard-focusable (tabIndex + Enter selects); aria-labels on icon-only buttons; reveal-key modal copy-first with "did you save it?" confirm; Slack manual form clears + collapses on success.
- [ ] Gate: build + vitest. Verify with preview tools against sample payload. Commit: `feat(dashboard): full five-view report experience with runtime metrics and rigor signals`.

### Task 15 (WS5): Landing — login wiring, docs tab, SEO, legal, deploy

**Files:**
- Modify: `landing/src/App.tsx`, `landing/src/components/Nav.tsx`, `Hero.tsx`, `Footer.tsx`, `landing/index.html`, `landing/vite.config.ts`, `landing/package.json`
- Create: `landing/src/docs/registry.ts`, `landing/src/components/DocsPage.tsx`, `landing/src/content/privacy.md`, `landing/src/content/terms.md`, `.github/workflows/deploy-landing.yml`

**Interfaces:** hash-based routing (`#/`, `#/docs`, `#/docs/<slug>`, `#/privacy`, `#/terms`) — keeps the single-file GH-Pages build path-free. `registry.ts` uses `import.meta.glob("../../../docs/**/*.md", { as: "raw", eager: true })` filtered to the curated nav: Getting Started (tutorial, quickstart-from-README excerpt), Guides (interpret-report, integrations, ci-troubleshooting, hosted-quickstart, deploy-production, data-handling), Reference (reference-config, METHODOLOGY, CODEBASE), Recipes, Policies (privacy, terms, security). Render with `marked` + `DOMPurify`; sidebar + in-page heading anchors + prev/next; DESIGN.md styling.

- [ ] Nav: "Sign in" (ghost) and "Get started" (primary) → `import.meta.env.VITE_APP_URL ?? "https://app.agentdiff.ai"`; "Docs" → `#/docs`. Hero CTA row gains "Get started" alongside GitHub star.
- [ ] `index.html`: OG + Twitter card tags, canonical, JSON-LD SoftwareApplication, `theme-color`, inline SVG favicon (diff-glyph mark consistent with DESIGN.md ink palette); optional Plausible script when `VITE_PLAUSIBLE_DOMAIN` set.
- [ ] Footer: Docs, Privacy, Terms, Contact (`mailto:security@agentdiff.dev` placeholder documented as needing a real inbox), GitHub issues.
- [ ] `deploy-landing.yml`: on push to main touching `landing/**` or `docs/**` → build → `actions/deploy-pages`. Note in workflow comments that Pages must be enabled in repo settings.
- [ ] Gate: `npm --prefix landing run build`; preview-verify docs route renders one doc + sidebar. Commit: `feat(landing): app CTAs, in-app docs section, SEO/meta, legal pages, Pages deploy`.

### Task 16 (WS6): Packaging, governance, release automation

**Files:**
- Modify: `pyproject.toml`, `.github/workflows/release.yml`, `README.md`, `docs/VIDEO.md`, `docs/validation/README.md`
- Create: `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/data-handling.md`

- [ ] `pyproject.toml`: `authors=[{name="Sandeep Vinay", email="sandeepvinay.sk@gmail.com"}]`, `keywords=["llm","agents","testing","regression","evaluation","ci"]`, classifiers (Dev Status 4 Beta; Intended Audience Developers; Topic Software Development Testing; License MIT; Python 3.10-3.13), `[project.urls]` (Homepage/Repository/Documentation/Changelog/Issues pointing at the GitHub repo paths).
- [ ] `CHANGELOG.md`: Keep-a-Changelog format; `[0.1.0] - 2026-07-05` summarizing this release's features (write it from this plan's commits). `CONTRIBUTING.md`: venv setup, health-stack commands from CLAUDE.md, test layout, PR expectations. `SECURITY.md`: report to the security mailto, 48h ack target, supported-versions table (0.x latest only).
- [ ] `docs/data-handling.md`: what is captured by default, redaction modes (Task 2), storage locations, hosted retention defaults (Task 12), how to disable capture.
- [ ] `release.yml`: add Node setup + `npm --prefix frontend ci && npm --prefix frontend run build && cp frontend/dist/index.html src/agentdiff/dashboard_assets/index.html` before wheel build; keep the tag-version guard.
- [ ] README: PyPI install (`pip install agentdiff`), new runtime-metrics bullet, versioning policy paragraph (SemVer, 0.x caveat), docs links to new files; remove stale stub lines. `VIDEO.md`: full 5-minute shot-by-shot script (recording = human task, stated). `validation/README.md`: reproducible validation procedure + note that external-codebase reports remain to be captured (honest status).
- [ ] Gate: `pip install -e .` still succeeds (`.venv/bin/pip install -e . -q`), `python -c "import agentdiff"`. Commit: `chore(release): PyPI metadata, governance docs, automated dashboard vendoring`.

### Task 17: Integration verification & finish

- [ ] Full gates: ruff, mypy, `pytest tests/ -q` (whole suite incl. server), `npm --prefix frontend run build` + vitest, `npm --prefix landing run build`. Fix anything that breaks; no gate-weakening.
- [ ] Regenerate the CLI sample payload if payload shape changed (`frontend/src/sample.json` regeneration instructions in `frontend/src/sample.ts`).
- [ ] Preview-verify: hosted dashboard happy path (projects → project → run tabs) against a seeded payload; landing home + docs.
- [ ] Invoke superpowers:requesting-code-review, then superpowers:finishing-a-development-branch.

## Self-review notes

- Spec coverage checked: every WS0–WS6 spec bullet maps to Tasks 1–16; out-of-scope items (Stripe payments, real secret rotation, video recording, external validation runs, enabling Pages) are documented as human tasks in Tasks 12/15/16 outputs.
- Cross-task contracts pinned: config names (Task 1) ↔ consumers (2,3,6,7,8); payload `run_metrics` (Task 6) ↔ server storage (10) ↔ adapter/UI (14); endpoint shapes (11,12) ↔ api.ts (13).
- Type consistency: `{"items", "total"}` list envelope used consistently in Tasks 11 and 13; `LLMResult` only referenced in Task 8 where defined.

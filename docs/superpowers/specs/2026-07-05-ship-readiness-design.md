# Ship-Readiness: Full Product Gap Resolution — Design

**Date:** 2026-07-05
**Branch:** `feat/ship-readiness`
**Source:** Full-codebase product audit (six-surface review). User directive: resolve every
identified gap properly, plus three new features: landing→login entry point, all new
metrics surfaced on the hosted dashboard, and a LangChain-style Docs tab on the landing page.

## Decisions already made (user-approved)

1. **Docs**: a `/docs` section inside the landing app, sidebar navigation, markdown from
   `docs/` rendered at build time. No third app.
2. **Login wiring**: landing stays a static marketing site; "Sign in" / "Get started" CTAs
   link to the hosted dashboard URL (`VITE_APP_URL`, prod default `https://app.agentdiff.ai`),
   which already carries the Clerk sign-in/register gate.
3. **Deploy**: GitHub Pages via a GitHub Actions workflow for the landing+docs build.
4. **Billing depth**: usage metering + plan quotas enforced server-side, usage panel in the
   dashboard; Stripe left as a documented seam (no payment code).

## Workstreams

### WS0 — Shared config schema (done first, single-writer)
All new config surface lands in `src/agentdiff/config.py` in one change so parallel
workstreams never contend on it:
- `capture.redaction`: `mode` (`standard`|`strict`|`off`, default `standard`), extra
  `patterns`, `redact_fields`, `capture_raw_bodies` (default false for unknown providers).
- `sampling.timeout_seconds` (default 300, 0=disabled), `sampling.retries` (default 1),
  `sampling.retry_backoff_seconds` (default 2.0).
- `thresholds.latency_ms`, `thresholds.tokens`, `thresholds.error_rate` (MetricThreshold).
- `output_eval.thresholds` (semantic/length/structural/judge warn+fail) — currently hardcoded.
- `stats.correction` (`benjamini_hochberg` default | `none`), `stats.alpha`,
  `stats.min_samples_warn` (default 5).

### WS1 — Capture SDK & CLI (Python)
- **Redaction layer** (`capture/http/redact.py` + call sites): default-on masking of
  secrets in captured request/response bodies, headers, and message content —
  Authorization/api-key headers always dropped; body values matching secret patterns
  (`sk-…`, `xoxb-…`, `Bearer …`, AWS keys, PEM blocks) masked to `"[REDACTED]"`;
  `strict` mode additionally hashes message/system content; raw-body capture for unknown
  providers becomes opt-in. Applied at event-build time in all three HTTP shims and both
  SDK shims, so nothing sensitive reaches JSONL/SQLite.
- **Loud degradation**: `activator.install()` warns (once per shim) when a capture flag is
  enabled but its dependency is missing; framework adapters and `providers.yaml` parsing
  log skips instead of silently no-opping.
- **Sampling resilience**: per-sample timeout (thread future timeout) and retry with
  backoff; timeouts count toward the failure budget with a clear message.
- **Fast-fail runner validation**: `compare` and `ci run` import the runner before
  sampling and exit with the doctor-style hint on failure.
- **`record()` footguns**: warn when an existing capture file is truncated; message names
  the file and how to keep it.
- **Implement `agentdiff structure`**: re-runs inference, three-way merges with existing
  `structure.yaml` (preserves user display-name edits), prints added/removed/renamed.
- **Implement `agentdiff replay`**: deterministically re-runs the runner for a report's
  test cases against a recorded cassette (`--cassette`, `--report-dir`), producing a new
  report; exits with a clear error naming missing cassette entries.
- `quickstart` prints the exact template path to edit when it writes a NotImplementedError
  runner.

### WS2 — Analysis engines (Python)
- **New behavioral metrics**: latency (per-trajectory `total_latency_ms`, Mann-Whitney),
  tokens (`total_tokens`, Mann-Whitney), error rate (trajectory `status!="success"`,
  two-proportion z). Each gets deltas, effect sizes, verdicts via WS0 thresholds, and
  entries in `report.md`, `report_payload`, and findings.
- **Multiple-comparison correction**: Benjamini–Hochberg across all p-values in a
  comparison; adjusted p stored alongside raw; significance/verdict downgrade logic uses
  adjusted p. `stats.correction: none` restores old behavior.
- **Sample-size warnings**: any delta with n < `min_samples_warn` per side is flagged
  `low_power: true`; report and payload carry a run-level warning.
- **Attribution confidence labels**: results carry `confidence: high|medium|low`
  (rule-weight buckets); rule-5 fallback is `low` and renderers say so.
- **Eval-completeness**: `output_eval` returns a `skipped_checks` list with reasons
  (no embeddings, no API key, timeout); report/payload/dashboard surface it so a pass
  is never mistaken for a full pass.
- **Judge hardening**: JSON-constrained prompt with retry-on-parse-failure, provider
  fallback (anthropic→openai when both configured), explicit `error` outcome
  distinguished from a low score.
- **Storage**: WAL mode on SQLite connections; `schema_version` table (v1) checked on
  open with a friendly mismatch error.

### WS3 — Hosted platform (server/)
- **Run report payload**: worker generates the full `report_payload` (same shape the CLI
  dashboard consumes) during `process_run` and stores it on the Run (JSONB);
  new `GET /v1/runs/{id}/payload`. This powers the five report sections in WS4.
- **Health**: `/health` checks DB + Redis; `{"status":"ok"|"degraded", checks:{…}}` with 503 on degraded.
- **Retention**: worker cron (daily) deletes Runs older than `AGENTDIFF_RETENTION_DAYS`
  (default 90) and LiveTrajectories older than `AGENTDIFF_LIVE_RETENTION_DAYS` (default 30);
  0 disables.
- **Audit log**: `audit_logs` table (org, actor, action, target, ts, metadata); written on
  project create/rename/delete, key mint/revoke, Slack connect/disconnect, run delete;
  `GET /v1/projects/{id}/audit` (paginated).
- **API keys**: `name` column (set at mint), returned in listing.
- **CRUD**: `PATCH /v1/projects/{id}` (rename), `DELETE /v1/projects/{id}` (cascade),
  `DELETE /v1/runs/{id}`; all audited.
- **Pagination/search**: `limit`/`offset` (defaults 50, max 200) + `total` count on
  project runs and projects lists; `verdict` filter and `q` name-search.
- **Usage metering + quotas**: `usage_counters` (org_id, yyyymm, runs, trajectories)
  incremented in ingest; plan model on Org (`plan`: free|pro|unlimited; env-configurable
  limits, free default 500 runs/mo); 429 with `X-Quota-*` headers when exceeded;
  `GET /v1/usage` for the dashboard. Stripe seam documented in code comments + docs.
- **Worker HA**: drift + retention crons take a Redis `SET NX EX` lease so N workers
  don't double-fire.
- **Job resilience**: arq `max_tries=3` with backoff for `process_run`; drift per-project
  failures logged with project id; under-sampled drift projects surfaced in
  `/v1/projects/{id}/stats` as `drift_status: insufficient_samples`.
- **Migrations**: one new Alembic revision covering all model changes.
- **Deploy hardening**: `docker-compose.prod.yml` with nginx TLS reverse proxy
  (+ certbot volume layout), API/dashboard behind it; migrations moved to a one-shot
  `migrate` service so app containers don't gate on them; `docs/deploy-production.md`
  covering TLS, backups (pg_dump cron example + restore steps), scaling, CORS, secret
  rotation (MultiFernet key rotation walkthrough, Slack/Clerk credential rotation).
- **Observability**: request-timing structured logs; optional Sentry init via
  `AGENTDIFF_SENTRY_DSN`; lightweight `/metrics` (Prometheus text format, no new hard dep)
  counting requests, processed runs, drift checks, quota rejections.

### WS4 — Hosted dashboard (frontend/)
- **Run detail becomes the full report experience**: tabs Overview / Behavioral Deltas /
  Attribution / Timeline / Summary reusing the five existing section components, fed by
  `GET /v1/runs/{id}/payload` (adapter maps payload → existing `ReportData` types).
  Sections stop importing the sample fallback in hosted mode; loading/error/empty states.
- **New metrics surfaced**: latency/token/error-rate deltas render in Behavioral Deltas
  and Overview stat chips; low-power and eval-incomplete warnings render as banners;
  attribution confidence labels shown on findings.
- **Lists**: search box + verdict filter + pagination ("Load more" with `total`) on runs;
  name search on projects.
- **CRUD UI**: project rename (inline) + delete (typed-confirmation modal); run delete;
  key names at mint time.
- **Usage panel**: plan, current-month runs/trajectories vs limit, progress bar (Setup tab).
- **Audit log**: simple paginated table (Setup tab).
- **Auth**: central 401 handler → Clerk `signOut()`+redirect to sign-in with a toast;
  StatsBar errors visible (retry affordance, no infinite skeleton).
- **Account surface**: header shows org name via `fetchMe()`.
- **Export/share**: "Download JSON" (payload) and "Copy link" buttons on run detail.
- **A11y/mobile**: graph container responsive (min-width only ≥md), keyboard-focusable
  nodes, aria-labels on icon buttons; reveal-key modal copy-first layout; Slack manual
  form resets on success.

### WS5 — Landing + docs (landing/)
- **Nav/CTAs**: "Sign in" and "Get started" → `VITE_APP_URL`; Docs tab → `/docs`.
- **Docs section**: client-side route (`hash`-based to stay GH-Pages/single-file safe)
  with LangChain-style left sidebar (Getting Started / Guides / Reference / CI & CD /
  Hosted Platform / Policies), content from `docs/*.md` imported at build time
  (`import.meta.glob` + `marked` + sanitizer), styled per DESIGN.md, in-page heading anchors,
  prev/next links.
- **SEO**: OG + Twitter cards, canonical, JSON-LD (SoftwareApplication), `theme-color`,
  inline SVG favicon; optional Plausible via `VITE_PLAUSIBLE_DOMAIN`.
- **Legal**: Privacy Policy and Terms pages (docs routes), Contact (mailto) + GitHub
  issues link in footer.
- **Deploy**: `.github/workflows/deploy-landing.yml` → GitHub Pages on push to main.

### WS6 — Packaging, governance, docs (repo root)
- `pyproject.toml`: authors, keywords, classifiers, `[project.urls]`, license expression.
- `CHANGELOG.md` (Keep-a-Changelog, 0.1.0 entry), `CONTRIBUTING.md` (setup, tests, PR
  flow), `SECURITY.md` (reporting contact, supported versions), versioning policy section
  in README.
- `docs/data-handling.md`: exactly what is captured, defaults, redaction modes, retention.
- `docs/deploy-production.md` (see WS3) + secret-rotation guide.
- Release workflow: build the frontend and vendor `dashboard_assets/index.html`
  automatically before wheel build (removes the manual step).
- README: PyPI install instructions, new metrics, docs links; VIDEO.md becomes a concrete
  recording script/storyboard (recording itself needs a human); validation README updated
  with the reproducible procedure + one committed hermetic validation report from the
  bundled example (true external-codebase validation remains a human task, stated
  honestly).

## Explicitly out of scope (needs resources I can't provision)
Stripe payments, real Slack/Clerk secret rotation (guide provided; rotation is a human
action), recording the walkthrough video (script provided), running validation on truly
external codebases, and enabling GitHub Pages in repo settings (workflow provided).

## Error handling & testing strategy
Every Python change lands with pytest coverage in the existing suites (redaction,
new deltas, BH correction, timeout/retry, structure merge, replay, retention, quotas,
audit, pagination). Server changes tested via the existing `tests/server` FastAPI
fixtures. Frontend: `npm run build` (tsc) + existing vitest suite extended for the API
client additions; landing: build must pass. Full gates before finish: `ruff`, `mypy`,
`pytest -q`, both frontend builds.

## Sequencing
WS0 → (WS1 ∥ WS2) → WS3 → (WS4 ∥ WS5 ∥ WS6) → integration & verification.
WS3 precedes WS4 because the payload endpoint feeds the report tabs. Single working
tree; workstreams own disjoint file sets; `config.py` owned by WS0 only.

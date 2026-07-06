# TODOS

## Deployment

### Clerk production instance
**Priority:** P1
Create a Clerk production instance and swap the dev keys before deploying:
`VITE_CLERK_PUBLISHABLE_KEY` (pk_live), `AGENTDIFF_CLERK_JWKS_URL`,
`AGENTDIFF_CLERK_ISSUER`. Dev instances have strict usage limits.

### Stable Slack OAuth redirect URL
**Priority:** P1
`AGENTDIFF_SLACK_REDIRECT_URL` points at a dead trycloudflare quick-tunnel.
Replace with the production `https://api.<domain>/v1/slack/callback` (or a
fresh tunnel for local testing) and update the Slack app's redirect settings.

## Server

### Serve stored report_payload from GET /v1/runs/{id}
**Priority:** P1
The endpoint re-validates every trajectory and re-runs compare_all+build_graph
per request, synchronously on the event loop, despite the worker persisting
run.report_payload for exactly this. Serve the stored payload when present
(legacy fallback via asyncio.to_thread). Flagged by 4 reviewers, 2026-07-06.

### Bulk-delete project children instead of ORM cascade
**Priority:** P1
delete_project lazy-loads every Run/Trajectory/Finding/LiveTrajectory into
memory. Use bulk core deletes in FK-safe order (mirror cleanup_retention) or
DB-level ON DELETE CASCADE. (Performance review, 2026-07-06.)

### Restrict /metrics (and consider /health) in nginx
**Priority:** P1
deploy/nginx.conf proxies /metrics publicly — request volumes and quota
rejections are visible to anonymous visitors. Allowlist scrape IPs or require
a token. (Security review, 2026-07-06.)

### Worker-side Prometheus counters always read zero
**Priority:** P2
agentdiff_runs_processed_total / drift_checks_total increment in the worker
process but /metrics is served by the api process — scrapes report 0 forever.
Expose a worker metrics port or move counters to Redis. (Adversarial, 2026-07-06.)

### Cap explain_findings attempts
**Priority:** P2
Failures don't count toward the 3-explanation cap, so a down LLM endpoint
means one 20s timeout per non-pass finding, serially, in the worker/drift
cron. Cap total attempts. (Adversarial M3, 2026-07-06.)

### Drift cron lease shorter than worst-case sweep
**Priority:** P2
240s lease vs unbounded sweep (now including LLM explanations) — overlapping
sweeps double-fire drift runs and Slack posts. Renew the lease per project or
size TTL >= interval. (Performance/adversarial, 2026-07-06.)

### Redaction config doesn't reach user-spawned threads
**Priority:** P2
RedactionConfig lives in a ContextVar; threads the runner's own code spawns
(ThreadPoolExecutor etc.) silently fall back to standard mode — a strict-mode
leak path. Module-level global with contextvar override. (Adversarial H5.)

### Cassette response bodies bypass redaction
**Priority:** P2
Cassettes store full raw response bodies (body_hex) — strict-mode users still
get conversation content on disk. URL query creds are now stripped; decide
body policy (redact in standard mode / document the strict-mode conflict).
(Adversarial H3, 2026-07-06.)

### Stats endpoint query waterfall + unbounded streak scan
**Priority:** P2
get_project_stats runs ~7 sequential queries incl. an unbounded verdict scan,
polled every 15s per viewer. Collapse via SQL aggregates and cap the streak
scan; gate the frontend poll on visibilitystate. (Performance, 2026-07-06.)

### Batch retention deletes
**Priority:** P3
cleanup_retention deletes all expired rows in single statements in one
transaction — lock/WAL spike on large backlogs. Delete in bounded batches.

### Legacy sqlite grandfathering stamps CURRENT_SCHEMA_VERSION
**Priority:** P3
storage._connect stamps un-versioned artifacts with the current version (not
1), defeating the guard after a future bump; also mutates artifacts on read
paths and leaks conn on StorageVersionError. (Checklist, 2026-07-06.)

### audit_logs.created_at has no server default
**Priority:** P2
`created_at` is NOT NULL with only an ORM-side python default. Add
`server_default=now()` via a follow-up migration so raw-SQL inserts work and
timestamps are DB-clock ordered. (Data-migration review, 2026-07-06.)

### Org-deletion FK semantics undecided
**Priority:** P2
`audit_logs.org_id` / `usage_counters.org_id` FKs default to RESTRICT. Decide
and document: orgs never hard-delete (keep RESTRICT) or mirror the
`project_id` retention approach. (Data-migration review, 2026-07-06.)

### Destructive downgrade in 0c7fdcec7587_ship_readiness
**Priority:** P2
`downgrade()` drops audit_logs, usage_counters, and orgs.plan outright.
Document as destructive and/or archive before dropping. (Data-migration
review, 2026-07-06.)

### Audit list query can't use its project index
**Priority:** P2
`list_audit`'s OR fallback over `target_id`/`meta->project_id` prevents use of
`ix_audit_logs_project_id_created_at`. Backfill `project_id` for legacy rows
and drop the fallback once done. (Data-migration review, 2026-07-06.)

### Boot migration races under --scale api>1 (base compose)
**Priority:** P3
Base-compose api runs `alembic upgrade head` at boot; two replicas race.
Prod overlay is safe (one-shot migrate service). Guard the dev boot migration
with a pg advisory lock, or note the single-replica constraint.

## Frontend

### Split the 346KB sample report out of the hosted bundle
**Priority:** P1
lib/payload.ts statically imports sample.json into the SPA bundle served to
every marketing visitor. Dynamic-import it as the dev/CLI fallback only, or
restrict to the CLI build. Consider route-level code splitting (React.lazy)
for the dashboard while in there. (Performance review, 2026-07-06.)

### Restyle docs prose typography onto the brutalist system
**Priority:** P2
.doc-prose keeps legacy Cabinet Grotesk/Geist headings and rounded code
blocks. Deferred by decision 2026-07-06 (D9) — do with /design-review on the
rendered page.

### Surface drift_status in the dashboard
**Priority:** P3
GET /projects/{id}/stats returns drift_status specifically so the UI can
explain a quiet drift lane; ProjectStats omits it. (API-contract, 2026-07-06.)

### Component tests for ProjectPage
**Priority:** P2
ProjectsPage / RunDetail usePayload / RequireAuth / useTheme are now covered;
ProjectPage (stats fetch, runs pagination/filter, tab state) still has no
component tests.

### lib/auth toast + sign-out idempotency tests
**Priority:** P3
`onUnauthorized`'s toast and repeated-401 idempotency guard are untested
(only the dispatch is spied in api.test.ts).

## Completed

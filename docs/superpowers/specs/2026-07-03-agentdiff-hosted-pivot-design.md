# AgentDiff Hosted Pivot — Walking Skeleton Design

Date: 2026-07-03
Status: approved (pending user review of this written spec)
Scope: first slice of a larger hosted-SaaS pivot

## Context and motivation

AgentDiff today is a pip-installed CLI + library + GitHub Action. The capture
mechanism is in-process monkey-patching (`src/agentdiff/capture/activator.py`
installs HTTP/SDK shims inside the running agent's process), which is why an
install is required: to observe an agent's behavior, AgentDiff must run where
the agent runs.

We are pivoting toward a **multi-tenant hosted SaaS**: teams sign up, log in
via a managed auth provider (Clerk — not Slack), connect a project, and see
behavioral regression results in a hosted dashboard. Slack is wired in as a
reporting/notification channel, not as auth.

### Data-plane decision (settled)

A container cannot observe another team's agent from the outside without
losing the moat (in-process depth) or becoming an in-path LLM proxy (which puts
us in the customer's production critical path). We therefore use the
**thin-collector model**: a small client runs in the customer's environment,
captures full in-process behavior using the existing `capture/` code, and ships
trajectories to a hosted ingest API. This is the Sentry/Datadog/LangSmith model.
The moat stays intact; the install shrinks and points at our cloud.

### Architectural placement (settled)

AgentDiff is an **out-of-band observability/quality plane**, never in the
serving path. The collector is a passive tap at the agent-to-LLM-call boundary;
everything hosted is fed asynchronously. If the hosted plane is down, the
customer's agent keeps serving users — they simply stop getting diffs. This is
what makes it safe to adopt.

### CI is the primary insertion point, off the bat

For this first slice the collector's **only** integration is the CI path. It
reuses the existing `ci run` capture and the shipped GitHub Action, and instead
of writing local artifacts it POSTs the run (baseline + candidate trajectories)
to the hosted ingest API. The generic in-app / production SDK path is deferred
to a later slice (it rides along with production monitoring). So off the bat,
AgentDiff hosted = a CI gate that reports into a hosted multi-tenant dashboard.

## Scope of this slice — the walking skeleton

The thinnest vertical that proves the whole hosted model end to end:

> A CI collector captures a run and POSTs it to a containerized ingestion API,
> which authenticates the tenant by API key, stores it in Postgres, enqueues a
> job, and an engine worker runs compare + attribution, writes findings, and
> posts a Slack notification when the project has Slack configured. The
> Clerk-authed dashboard then displays the run and its findings.

Multi-tenant isolation is built in from day 1 so it is not a rewrite later.

### Explicitly deferred to later slices

- Generic in-app / production collector + live production monitoring
- Billing
- Horizontal scale-out beyond a single worker

(Slack notifications and managed auth, previously deferred, are now in this
slice per the decisions below. Social logins like GitHub are Clerk config, not
in-house code, so they are no longer a deferred item.)

## Backend topology (settled)

Production-shaped: FastAPI API + a Redis-backed `arq` worker for the engine +
Postgres + the existing React dashboard, all via docker-compose. Five services:
`api`, `worker`, `postgres`, `redis`, `dashboard`. The engine
(`compare` + `stats` + `attribution`) moves server-side into the worker,
unchanged. Ingestion never runs the engine inline; it enqueues.

```
  CUSTOMER CI                             HOSTED PLATFORM (docker-compose)
  ┌────────────────┐                     ┌──────────────────────────────────┐
  │ CI collector   │   POST /v1/runs     │  ┌──────────┐      ┌───────────┐  │
  │ (Action +      │ ──── API key ─────▶ │  │ FastAPI  │─enqueue▶│  Redis  │  │
  │  capture/)     │   trajectories      │  │   api    │      └─────┬─────┘  │
  └────────────────┘                     │  └────┬─────┘            │        │
                                         │       │            ┌─────▼─────┐  │
  ┌────────────────┐   Clerk login       │       ▼            │  arq      │  │
  │ React dashboard│ ◀── JWT-authed API ─▶│  ┌──────────┐◀────│  worker   │  │
  │ (existing UI)  │   runs, findings    │  │ Postgres │      │ (engine)  │  │
  └────────────────┘                     │  └──────────┘      └───────────┘  │
                                         └──────────────────────────────────┘
```

## Components

- **CI collector** (`collector/`) — thin client. Reuses `capture/` + trajectory
  serialization; adds an uploader that POSTs a run with a project API key. Slots
  into the existing Action / `ci run` flow. Does not ship the heavy engine.
- **API** (`server/app/`, FastAPI) — ingestion endpoints (in-house API-key
  auth), dashboard reads (Clerk JWT auth), and a per-project Slack config
  endpoint. Enqueues engine jobs; never runs the engine inline.
- **Worker** (`server/worker/`, arq) — consumes jobs from Redis; runs
  `compare_all` -> `attribute_range` -> `build_incident_summary` (all existing);
  writes findings; updates run status; posts a Slack notification when the
  project has Slack configured (reuses `incident/` renderers + Slack client).
- **Storage** — Postgres, SQLAlchemy 2.0 async + Alembic migrations.
- **Dashboard** (`frontend/`) — existing Vite/React, now a Clerk-authed SPA
  hitting the API instead of reading a static JSON file.

## Data model (tenant boundary = project)

```
orgs          (id, clerk_org_id, name, created_at)
users         (id, org_id, clerk_user_id, email, created_at)   -- no passwords; Clerk owns credentials
projects      (id, org_id, name, created_at)                   -- tenant boundary
api_keys      (id, project_id, key_hash, prefix, revoked_at, last_used_at)  -- collector ingest auth (in-house)
slack_configs (id, project_id, channel_id, bot_token_encrypted, enabled)   -- per-project; token encrypted at rest
runs         (id, project_id, idempotency_key, baseline_ref, candidate_ref, tier,
              config JSONB,   -- structure config the collector sends with the run
              status[pending|processing|done|failed], verdict, error, created_at)
trajectories (id, run_id, side[baseline|candidate], test_case_id, payload JSONB)
findings     (id, run_id, test_case_id, verdict, metric, impact_summary,
              cause_path, cause_rule, cause_hunk, explanation)  -- IncidentFinding shape
```

Every data query is scoped by `project_id` (and project -> `org_id`). One API
key maps to exactly one project.

## Data flow

1. In the customer's CI, the collector captures baseline + candidate (existing
   capture) and calls `POST /v1/runs` with the project API key. The request
   carries the trajectories plus the project's structure config (the collector
   has it locally in CI, so the worker does not depend on any server-side config
   file). The API creates `run(status=pending)`, persists the config on the run,
   and stores trajectories.
2. The API enqueues `process_run(run_id)` on Redis and returns `202` with the run id.
3. The worker loads the run's trajectories + config, runs the engine, writes
   `findings`, and sets `run.status=done`, `verdict`.
4. If the project has Slack configured and the verdict is warn/fail, the worker
   renders the incident brief (existing `incident/` renderers) and posts it via
   the Slack client. Delivery failure degrades: it never fails the run.
5. A dashboard user logs in via Clerk, lists projects -> runs -> run detail
   (findings, behavioral deltas, attribution) via the JWT-authed API.

## Auth and tenancy

- **Ingest (machine-to-machine, in-house):** per-project API key, hashed at rest
  (argon2), shown once on creation, sent as `Authorization: Bearer adk_...`.
  This stays in-house — it is not a human login.
- **Dashboard users (managed — Clerk):** login/signup via Clerk's React
  components. Clerk issues a JWT; FastAPI verifies it against Clerk's JWKS on
  each request. We store no passwords or sessions. Clerk Organizations map to
  our `orgs` (via `clerk_org_id`) and Clerk users to our `users` (via
  `clerk_user_id`), synced on first login or via a Clerk webhook. Social logins
  (GitHub, Google) are Clerk config, not code.
- **Isolation:** every read filters by the caller's org/project. Covered by an
  explicit test: tenant A must not read tenant B's run by id.

## Error handling (degrade, never swallow)

Same principle as the CI design: failures are visible, never silent.

- Bad/revoked API key -> `401`; malformed batch -> `422` (Pydantic); oversized
  payload -> `413`.
- Idempotency key on `POST /v1/runs` so collector retries do not double-create.
- Worker engine exception -> `run.status=failed` with the error stored and shown
  in the dashboard; arq retries with backoff. A failed run is never invisible.
- DB/Redis unavailable -> API `503`; collector buffers and retries with backoff.
- Slack delivery failure -> logged; the run is unaffected and the dashboard
  remains the source of truth.

## Testing

- Reuse the existing engine tests untouched (210+ passing).
- API route tests (httpx `AsyncClient`); auth tests (ingest API-key hash/verify;
  Clerk JWT verification against a mock JWKS with signed test tokens); worker
  task test (enqueue -> process -> findings written) against a real Postgres test
  db + fakeredis; worker Slack test (brief posts on a configured failing run and
  degrades on a Slack error).
- One end-to-end test: ingest -> enqueue -> worker -> read-back proves the skeleton.
- One security test: cross-tenant isolation (A cannot read B).

## Repo layout (monorepo, evolves this repo)

```
src/agentdiff/     engine + capture (core, largely unchanged)
collector/         thin CI client (capture + uploader)
server/app/        FastAPI: routes, auth, deps
server/models/     SQLAlchemy models
server/schemas/    Pydantic API schemas
server/worker/     arq tasks
server/migrations/ Alembic
frontend/          dashboard, now Clerk-authed SPA
docker-compose.yml + server/Dockerfile + frontend/Dockerfile
```

## Confirmed technology decisions

- Worker: **arq** (async, Redis-backed, lightweight) over Celery.
- Dashboard auth: **Clerk** (managed). FastAPI verifies Clerk JWTs via JWKS;
  Clerk Organizations map to our orgs. Ingest stays on in-house project API keys.
- Notifications: **Slack** via the existing `incident/` renderers + Slack client,
  fired from the worker on run completion; per-project config, bot token
  encrypted at rest.
- API: FastAPI + Pydantic; DB: Postgres + SQLAlchemy 2.0 async + Alembic;
  queue/cache: Redis; containerization: Docker + docker-compose.

## Success criteria

- `docker-compose up` brings up all five services healthy.
- A CI collector run POSTs to the API and returns `202`.
- The worker processes the run and writes findings; run status reaches `done`.
- When a project has Slack configured, a failing run posts an incident brief to
  the channel; a Slack failure does not fail the run.
- A Clerk-authed dashboard user sees the run and its findings, scoped to their
  project only.
- Full test suite green, including the end-to-end and cross-tenant isolation tests.

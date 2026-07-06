# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) — with
the 0.x caveat described in the README's versioning policy: minor version
bumps may still contain breaking changes until 1.0.0.

## [0.2.0] - 2026-07-06

### Added

- Hosted-platform hardening: usage quotas, retention crons, health/metrics
  endpoints, and a production TLS deploy path for the self-hosted stack.
- Server CRUD, pagination/search, named API keys, and an audit log across
  projects, runs, and Slack connections.
- Dashboard: paginated/searchable runs and projects, project rename/delete,
  run delete, named key minting, a Setup usage panel, and a paginated audit
  table.
- Dashboard: full five-view report experience (Overview, Behavioral Deltas,
  Attribution, Timeline, Summary) wired to the new run-payload endpoint, with
  runtime-metric deltas, run-level warnings, and attribution confidence
  surfaced in the UI.
- UI: landing page, docs, legal pages, and Clerk-gated dashboard now ship as
  one Vite SPA under `frontend/`, with `/projects` as the primary dashboard
  entry point, Vercel-ready SPA rewrites, and a unified GitHub Pages workflow.
- UI: brutalist AgentDiff restyle for the public landing/docs routes and hosted
  dashboard chrome, including the before/after stopped-agent topology and the
  preserved pass/warn/fail verdict mapping.
- Landing: the methodology baseline→candidate topology is now interactive —
  hover or tap a node to highlight it in both columns and read its
  baseline→candidate invocation rates in the panel readout.
- Dev CORS: optional `AGENTDIFF_CORS_ORIGIN_REGEX` lets the API accept the
  Vite dev server's dynamic localhost ports without loosening production CORS.
- Frontend component-test infrastructure (jsdom + Testing Library) with
  coverage for the auth gate, projects list error/retry, run-report polling,
  and theme persistence.

### Changed

- README comprehensively restructured: quick start up front, table of
  contents, badges, accurate install instructions, and consolidated coverage,
  CI-gate, and hosted-platform sections.
- Landing hero pipeline diagram renders at its full size.

### Fixed

- Dashboard URLs (`/projects`, `/projects/:id`, `/runs/:id`) no longer 404
  after sign-in (nested-router mismatch), and signing in now lands on
  `/projects` instead of the marketing home. Unknown URLs get a proper 404
  page.
- Docs body text was nearly invisible in both light and dark themes (legacy
  color tokens resolving to surface colors).
- The worker no longer reprocesses an already-completed run, so duplicate
  queue deliveries can't duplicate findings.
- The production compose overlay no longer publishes Postgres/Redis host
  ports, and the one-shot migrate service's database URL is overridable for
  managed-Postgres deployments.
- The projects page fetched its list twice on every mount; it now fetches
  once.
- The dashboard header wordmark links back to the landing page.
- Pre-landing review hardening: Slack OAuth install states are single-use
  (replay of a leaked install link is rejected); worker run-claiming is
  atomic (concurrent duplicate deliveries can't double-insert findings);
  Slack HTTP calls no longer block the event loop; manual Slack reconfigure
  clears a stale OAuth webhook; quota 429 bodies use a flat shape; a pending
  run whose enqueue was lost is re-enqueued on idempotent replay; unmatched
  request paths no longer mint unbounded metrics label series; cassettes
  store query-stripped URLs so provider API keys never land in committed
  cassette files; and `trajectories.run_id` / `findings.run_id` /
  `runs.created_at` gained indexes.
- Note: `agentdiff diff` / `agentdiff ci` now generate LLM attribution
  explanations by default when `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) is
  set — code hunks from your diff are sent to the configured provider. Unset
  the key or disable the explainer to opt out.

## [0.1.0] - 2026-07-05

Initial public release.

### Added

- **Universal capture** over `httpx`, `requests`, `aiohttp`, and gRPC, with
  optional SDK shims for Anthropic, OpenAI, and MCP, plus soft-import
  framework adapters for LangGraph, CrewAI, AutoGen, and LlamaIndex.
- **Causal attribution** engine mapping behavioral deltas back to the
  changed file and diff hunk via a deterministic rule pipeline over an
  AST-derived agent manifest and the git diff.
- **`agentdiff compare`**: samples baseline and candidate refs, computes
  behavioral deltas (agent invocation rate, tool usage, tool-set overlap)
  with two-proportion and Mann-Whitney significance testing, and produces a
  Markdown report plus a dashboard-ready payload.
- **Runtime metric deltas**: latency, token-usage, and error-rate deltas are
  computed alongside behavioral deltas and rendered in the report's Runtime
  Deltas section and the dashboard payload.
- **Statistical rigor**: Benjamini-Hochberg multiple-comparison correction
  and low-sample-size warnings on every comparison run. Note: because the
  correction now also applies to the zero-config `agentdiff diff` path, a
  multi-delta `diff` may report a softer verdict than in a pre-0.1.0 build;
  set `stats.correction: none` to restore the uncorrected behavior.
- **Default-on secret redaction** across all capture shims, with `standard`
  (pattern masking + credential header stripping), `strict` (content
  digests), and `off` modes — see `docs/data-handling.md`.
- **Resilient sampling**: per-sample timeout and retry, loud (not silent)
  degradation when a capture shim can't be enabled, and fast-fail Runner
  import/config validation before a comparison starts.
- **`agentdiff structure`**: refreshes `structure.yaml`, merging in
  added/removed functions while preserving user-edited display names.
- **`agentdiff replay`**: deterministically re-runs a Runner against a
  recorded HTTP cassette for reproducible, hermetic comparisons.
- **Local dashboard** (`agentdiff dashboard --serve`): a single-file
  React + React Flow + Tailwind UI with five views — Overview, Behavioral
  Deltas, Causal Attribution, Trajectory Timeline, and Run Summary.
- **CI gate** (`agentdiff ci run`): hermetic (cassette-replay) and live
  execution tiers, PR check + comment, Slack brief, postmortem draft, and
  reconstructable JSON artifacts.
- **Hosted platform** (optional, self-hosted via `docker compose`):
  multi-tenant API, background worker, and dashboard for teams that want
  live drift monitoring instead of (or alongside) local/CI runs.
- **Storage**: WAL-mode SQLite plus JSONL trajectory files under
  `.agentdiff/`, with schema-version guards.
- **Traffic discovery** (`agentdiff traffic discover`): seeds regression
  test cases from existing JSONL/JSON/CSV/text traffic samples.

[0.2.0]: https://github.com/Svkayy/agentdiff/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Svkayy/agentdiff/releases/tag/v0.1.0

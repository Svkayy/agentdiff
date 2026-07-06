# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) — with
the 0.x caveat described in the README's versioning policy: minor version
bumps may still contain breaking changes until 1.0.0.

## [Unreleased]

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

[Unreleased]: https://github.com/Svkayy/agentdiff/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Svkayy/agentdiff/releases/tag/v0.1.0

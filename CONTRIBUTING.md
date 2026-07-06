# Contributing to AgentDiff

Thanks for considering a contribution. AgentDiff is a Python engine (with an
optional FastAPI hosted platform) plus a TypeScript dashboard. This guide
covers the Python engine; see `frontend/` and `landing/` for the dashboard and
marketing-site toolchains respectively.

## Setup

```bash
git clone https://github.com/Svkayy/agentdiff.git
cd agentdiff
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Requires Python 3.10–3.13. Install additional extras as needed for the area
you're touching (`.[server]`, `.[server-dev]`, `.[anthropic]`, `.[openai]`,
`.[mcp]`, `.[all]` — see `pyproject.toml`).

## Health stack

Run all four before opening a PR — this is also what CI runs:

```bash
.venv/bin/ruff check src/ tests/       # lint
.venv/bin/pytest tests/ -q             # tests
.venv/bin/mypy src/agentdiff           # typecheck
.venv/bin/vulture src/agentdiff        # dead code
```

For hosted-platform (`server/`) changes, also run the server suite
specifically:

```bash
.venv/bin/pytest tests/server -q
```

For dashboard (`frontend/`) or landing-site (`landing/`) changes:

```bash
npm --prefix frontend ci && npm --prefix frontend run build   # tsc --noEmit && vite build
npm --prefix landing ci && npm --prefix landing run build
```

## Test layout

- `tests/` — engine unit and integration tests (capture, redaction, compare,
  attribution, storage, CLI). Mirrors `src/agentdiff/` roughly one test file
  per module or feature area (e.g. `test_redaction.py`, `test_compare.py`,
  `test_cli.py`).
- `tests/server/` — hosted-platform tests (auth, models, worker, drift
  detection, hardening) against the FastAPI app in `server/`.
- `tests/fixtures/` and `tests/_sample_run.py` — shared trajectory/report
  fixtures used across multiple test modules.
- `tests/collector/` — `LiveCollector` client tests.
- `examples/research_assistant/` — a runnable sample agent used both as a
  worked example and as the basis for `docs/validation/README.md`'s
  reproducible validation procedure.

External LLM/HTTP calls are mocked throughout, so the suite runs hermetically
and offline — do not add tests that require a live API key or network access.

## Making a change

1. Follow test-driven development where practical: write a failing test
   first, then implement.
2. Keep capture, comparison, and attribution deterministic — the LLM is only
   used for the optional output-eval judge and per-finding explanations,
   never to decide a verdict or attribution. New code should preserve that
   split.
3. Update the relevant doc under `docs/` in the same PR (`reference-config.md`
   for new config fields, `METHODOLOGY.md` for pipeline changes, etc.).
4. Run the full health stack locally before pushing.

## Pull request expectations

- One logical change per PR; keep unrelated refactors out.
- PR description states what changed and why, and calls out any config or
  schema migrations.
- All four health-stack checks pass, plus `tests/server` and the frontend/
  landing builds if those areas were touched.
- New behavior has test coverage; bug fixes include a regression test.
- No secrets, API keys, or real trajectory data with unredacted content in
  fixtures — see `docs/data-handling.md`.
- Update `CHANGELOG.md`'s `[Unreleased]` section for user-visible changes.

## Reporting bugs / requesting features

Open a GitHub issue at
[github.com/Svkayy/agentdiff/issues](https://github.com/Svkayy/agentdiff/issues).
For security vulnerabilities, see `SECURITY.md` instead of a public issue.

# AgentDiff

**Behavioral regression testing for Python AI agent systems — any LLM provider, any framework, none required.**

When you change an agent's prompts, model parameters, or routing code, the final
output often still looks fine while the *internal* behavior has silently shifted:
a sub-agent stops firing, a tool gets called twice as often, a different document
gets retrieved. Traditional output evaluation misses this. **AgentDiff catches
these behavioral regressions and tells you exactly which code or prompt change
caused each one.**

## Two differentiators

1. **Universal capture.** The foundation is HTTP-level interception (`httpx` +
   `requests`), so AgentDiff captures every LLM call regardless of provider or
   wrapper — Anthropic, OpenAI, Gemini, Mistral, Bedrock, Cohere, Azure OpenAI,
   LiteLLM, or a raw `httpx.post` to a provider it's never heard of. SDK shims
   (Anthropic, OpenAI, MCP) add richer metadata when present, but capture never
   depends on them.
2. **Causal attribution.** For each behavioral delta, AgentDiff maps it back to a
   specific changed file — and where possible, the exact unified-diff hunk — using
   a deterministic rule engine over a dynamically-built agent manifest plus the
   git diff. The LLM is only used to write a 1–3 sentence explanation, never to
   decide the attribution.

## Quick start

```bash
pip install -e .

# 1. Infer structure, runner, starter config, and starter test cases.
agentdiff quickstart

# 2. Review .agentdiff/config.yaml and add at least one real input.
agentdiff doctor --project .

# 3. Compare against an inferred git baseline, or run a smoke comparison
#    when no git baseline exists yet.
agentdiff compare --baseline auto --samples 3
```

The report lands in `.agentdiff/reports/<timestamp>/report.md`.
The same directory also contains raw trajectory JSONL files and
`agentdiff.sqlite`, a queryable SQLite artifact for the run, plus a local
`dashboard.html`.

## The Runner

The only code you write is a **Runner** — a `Callable[[dict], dict | str | None]`
that fires one observable invocation of your agent and returns its outcome.
AgentDiff supports four trigger shapes out of the box, each with a copy-paste
recipe in [`docs/recipes/`](docs/recipes/README.md):

| Trigger shape    | Recipe |
|------------------|--------|
| Request-response | [`request_response.py`](docs/recipes/request_response.py) |
| Event-driven     | [`event_driven.py`](docs/recipes/event_driven.py) |
| Scheduled / cron | [`scheduled.py`](docs/recipes/scheduled.py) |
| Multi-turn chat  | [`multi_turn.py`](docs/recipes/multi_turn.py) |

The only project-specific decisions AgentDiff can't infer are **settling** (when
is one invocation done?) and **outcome collection** (what's the observable
result?). The recipes show the common patterns.

You may also decorate in-process Python tools dispatched from LLM `tool_use`
blocks with `@agentdiff.tool` so they appear in the trajectory.

## What the report contains

1. **Header** — refs, sample math, overall verdict.
2. **Traditional eval vs AgentDiff** — the headline side-by-side. Traditional
   output evaluation can say PASS while AgentDiff says FAIL. That contrast is the
   point.
3. **Behavioral findings** — per-agent invocation rates, tool-usage counts, and
   tool-set overlap, with PASS/WARN/FAIL verdicts.
4. **Causal attribution** — for each non-passing delta: the primary cause file,
   the rule that fired, the diff hunk, and a short explanation.
5. **Reproduction command.**

## Provider coverage

Canonical parsers ship for: Anthropic Messages, OpenAI Chat, OpenAI Responses,
Google Gemini (incl. streaming), Mistral, AWS Bedrock (Anthropic, Titan, Nova,
Llama, Mistral, Cohere, AI21 + generic fallback), Azure OpenAI, and Cohere.
**Anything else** is still captured via the raw HTTP layer (request/response
bytes tagged with the URL) — add a parser in
`src/agentdiff/capture/http/parsers/` or a pattern to `.agentdiff/providers.yaml`
to upgrade it to canonical fields.

Streaming HTTP bodies in SSE, NDJSON, and JSON-array forms are reconstructed into
`stream_chunk` timeline events when captured via `httpx`, `requests`, or
`aiohttp`.

## Framework and transport adapters

AgentDiff now installs optional, soft-import adapters for:

| Adapter | Captures |
|---|---|
| LangGraph | graph invokes, `StateGraph.add_node` node spans, edge registrations |
| CrewAI | crew kickoff, agent task execution, task execution |
| AutoGen | speaker turns, message receives, reply generation |
| LlamaIndex | query engines, retrievers, router retrievers |
| aiohttp | provider-aware HTTP LLM request/response capture |
| gRPC | unary/stream RPC call spans as framework events |

These adapters are enabled in `.agentdiff/config.yaml` under `capture:` and do
not require the dependencies to be installed. If the dependency is absent, the
adapter no-ops.

Existing traffic can seed regression cases without hand-written personas:

```bash
agentdiff traffic discover --from prod-sample.jsonl --output .agentdiff/test_cases.yaml
```

Local monitoring/dashboard commands:

```bash
agentdiff dashboard --serve
agentdiff monitor --once
agentdiff monitor --run-compare --interval 300
```

## Installation extras

Base install brings only `httpx` + `requests` (plus comparison/report deps). SDK
shims are optional and auto-detected:

```bash
pip install -e ".[anthropic]"   # or [openai], [mcp], [aiohttp], [grpc], [frameworks], [all]
```

AgentDiff's own LLM use (output-eval judge + attribution explainer) needs one of
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, selected by `AGENTDIFF_LLM_PROVIDER`
(default `anthropic`). If no key is set, the judge and explanation are skipped;
behavioral findings and rule-based attribution still run.

Semantic output similarity uses sentence-transformers and is optional:

```bash
pip install -e ".[embeddings]"
```

Without that extra, AgentDiff still runs behavioral comparison, structural
output diffs, length checks, and optional LLM judging.

## CLI

```
agentdiff init       Scan a project, infer structure, scaffold .agentdiff/.
agentdiff quickstart Infer structure + runner and create a runnable starter setup.
agentdiff compare    Sample baseline + candidate, compare behavior, evaluate output, attribute deltas.
agentdiff traffic    Discover test cases from JSONL/JSON/CSV/text traffic samples.
agentdiff dashboard  Generate or serve a local HTML dashboard for a run.
agentdiff monitor    Run local compare monitoring or summarize the latest report.
agentdiff doctor     Validate config, runner imports, git refs, hook status, and optional deps.
agentdiff hook       Manage the optional autoload hook: status/install/uninstall.
agentdiff structure  Refresh structure.yaml (stub in v0 — re-run init).
agentdiff replay     Replay captured tool calls (stub in v0).
```

`agentdiff compare` also supports hardened release settings:

```bash
agentdiff compare --baseline main --samples 20 --workers 4 --no-install-deps --max-failure-rate 0.05
```

Thresholds, capture shims, dependency installation, and sample failure budgets
can be configured in `.agentdiff/config.yaml`.

The optional autoload hook is explicit:

```bash
agentdiff hook install
agentdiff hook status
agentdiff hook uninstall
```

## What is still not hosted/distributed

AgentDiff has local quickstart, traffic discovery, framework adapters, stream
timelines, worker-based sampling, monitoring, and dashboard artifacts. It is not
yet a hosted SaaS dashboard, distributed load generator, or production tap that
continuously ingests live traffic without a Runner boundary. See
[`docs/recipes/limitations.md`](docs/recipes/limitations.md) for the current
line.

## How it works

See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the capture → comparison →
attribution pipeline in detail.

## License

See [LICENSE](LICENSE).

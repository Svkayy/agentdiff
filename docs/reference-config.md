# Configuration Reference

AgentDiff configuration lives in `.agentdiff/config.yaml` at your project root.
All fields are optional — the defaults work for most projects.

`agentdiff init` and `agentdiff quickstart` write this file for you with
commented defaults. `agentdiff doctor` validates it.

---

## Full example

```yaml
runner:
  module: .agentdiff.runner
  callable: run

samples_per_case: 20
llm_provider: anthropic

sampling:
  install_deps: true
  max_failure_rate: 0.0
  workers: 1

thresholds:
  agent_invocation_rate:
    warn: 0.2
    fail: 0.5
  tool_usage_avg:
    warn: 0.5
    fail: 1.0

capture:
  httpx: true
  requests: true
  aiohttp: true
  grpc: true
  openai_sdk: true
  anthropic_sdk: true
  mcp: true
  langgraph: true
  crewai: true
  autogen: true
  llamaindex: true
```

---

## `runner`

Tells AgentDiff where to find your Runner function.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `module` | string | `null` | Python module path to your Runner. Use dotted notation (`my_app.testing.runner`) or a relative path (`".agentdiff.runner"`). |
| `callable` | string | `"run"` | Name of the callable inside `module`. Must accept `(input: dict)` and return `dict \| str \| None`. |

**Example:**
```yaml
runner:
  module: my_app.testing.agentdiff_runner
  callable: run
```

---

## `samples_per_case`

| Type | Default | Range |
|------|---------|-------|
| int | `20` | ≥ 1 |

Number of Runner invocations per test case per side. Higher values give
tighter statistical bounds and reduce false WARN at the cost of more API
calls and run time.

Rule of thumb: start with 5 for fast iteration, use 20+ for CI gates, 50+
for subtle behavioral shifts.

---

## `llm_provider`

| Type | Default | Values |
|------|---------|--------|
| string | `"anthropic"` | `"anthropic"` \| `"openai"` |

Which provider AgentDiff uses for its **own** internal LLM calls: the output
evaluation judge and the attribution explainer. This is separate from the
provider your agent uses.

Requires the matching environment variable:
- `anthropic` → `ANTHROPIC_API_KEY`
- `openai` → `OPENAI_API_KEY`

If no key is set, the judge and attribution explanation are skipped.
Behavioral comparison and rule-based attribution still run.

---

## `sampling`

Controls how samples are collected.

### `sampling.install_deps`

| Type | Default |
|------|---------|
| bool | `true` |

When running the baseline (a git-archive checkout), whether to run
`pip install -e .` or `pip install -r requirements.txt` in the checkout.
Set to `false` if your baseline dependencies are already installed or you
want to skip the install step.

Equivalent CLI flag: `--no-install-deps`

### `sampling.max_failure_rate`

| Type | Default | Range |
|------|---------|-------|
| float | `0.0` | 0.0 – 1.0 |

Maximum fraction of Runner invocations allowed to fail (raise an exception
or time out) before the comparison aborts. `0.0` means any single failure
aborts the run.

Set to `0.1` to tolerate up to 10% flaky invocations.

Equivalent CLI flag: `--max-failure-rate`

### `sampling.workers`

| Type | Default | Range |
|------|---------|-------|
| int | `1` | ≥ 1 |

Number of parallel worker threads for sampling. `1` is sequential (safest).
Only increase if your Runner and all its dependencies are thread-safe and
you have shared state reset between invocations.

Equivalent CLI flag: `--workers`

---

## `thresholds`

Controls when a behavioral delta becomes WARN or FAIL in the report.

### `thresholds.agent_invocation_rate`

The fraction of trajectories in which each agent appears.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `warn` | float | `0.2` | Absolute change of ≥ 0.2 in invocation rate → WARN |
| `fail` | float | `0.5` | Absolute change of ≥ 0.5 in invocation rate → FAIL |

**Note:** both thresholds are gated by a two-proportion z-test (p < 0.05). A
delta that is large but not statistically significant is downgraded one level
(FAIL → WARN, WARN → PASS). The p-value appears in the report next to a `*`
significance marker.

### `thresholds.tool_usage_avg`

Mean number of tool invocations per trajectory.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `warn` | float | `0.5` | Change of ≥ 0.5 in mean tool calls → WARN |
| `fail` | float | `1.0` | Change of ≥ 1.0 in mean tool calls → FAIL |

Gated by a Mann-Whitney U test (no scipy dependency).

---

## `capture`

Fine-grained control over which capture shims are installed. All shims are
on by default. Set any to `false` to disable.

| Field | Default | What it captures |
|-------|---------|-----------------|
| `httpx` | `true` | All HTTP/HTTPS calls via httpx (sync + async) |
| `requests` | `true` | All HTTP calls via the requests library |
| `aiohttp` | `true` | Async HTTP calls via aiohttp |
| `grpc` | `true` | gRPC unary and streaming calls |
| `anthropic_sdk` | `true` | Anthropic Python SDK (richer metadata when available) |
| `openai_sdk` | `true` | OpenAI Python SDK (richer metadata when available) |
| `mcp` | `true` | MCP `call_tool` invocations |
| `langgraph` | `true` | LangGraph graph invokes and node spans |
| `crewai` | `true` | CrewAI crew kickoff and task execution |
| `autogen` | `true` | AutoGen speaker turns and message receives |
| `llamaindex` | `true` | LlamaIndex query engines and retrievers |

**Note:** SDK shims (`anthropic_sdk`, `openai_sdk`) add richer typed metadata
(system prompt, tool schemas, token counts) on top of what the HTTP layer
captures. If the SDK library is not installed, the shim silently no-ops. HTTP
capture still works.

Disabling an HTTP shim (`httpx`, `requests`) is unusual — the HTTP layer is
the foundation of capture. Disable a framework adapter if it conflicts with
how you initialize that framework in tests.

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Required for `llm_provider: anthropic` (judge + explainer) |
| `OPENAI_API_KEY` | Required for `llm_provider: openai` |
| `AGENTDIFF_LLM_PROVIDER` | Override `llm_provider` without editing config.yaml |

---

## Per-project provider registry

Custom providers that AgentDiff doesn't know about out of the box can be
registered in `.agentdiff/providers.yaml`:

```yaml
providers:
  - name: my_private_llm
    url_pattern: "api\\.myllm\\.internal/v1/generate"
```

The pattern is a Python regex matched against the full request URL. Custom
providers override built-in ones when the name collides. The raw
request/response bytes are still captured even without a parser; add a parser
module in `src/agentdiff/capture/http/parsers/` to get canonical fields.

---

## Related

- [Tutorial: Getting Started](tutorial-getting-started.md)
- [How-to: Interpret the Report](howto-interpret-report.md)
- [CODEBASE.md](CODEBASE.md) — internal config module reference (`config.py`)

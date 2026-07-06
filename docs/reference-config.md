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
  timeout_seconds: 300.0
  retries: 1
  retry_backoff_seconds: 2.0

thresholds:
  agent_invocation_rate:
    warn: 0.2
    fail: 0.5
  tool_usage_avg:
    warn: 0.5
    fail: 1.0
  latency_ms:
    warn: 1000
    fail: 5000
  tokens:
    warn: 200
    fail: 1000
  error_rate:
    warn: 0.1
    fail: 0.25

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
  redaction:
    mode: standard
    patterns: []
    redact_fields: []
    capture_raw_bodies: false

stats:
  correction: benjamini_hochberg
  alpha: 0.05
  min_samples_warn: 5

output_eval:
  semantic_fail: 0.70
  semantic_warn: 0.85
  length_fail: 0.50
  length_warn: 0.80
  structural_fail: 0.70
  structural_warn: 0.90
  judge_fail: 2.0
  judge_warn: 3.5
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

### `sampling.timeout_seconds`

| Type | Default | Range |
|------|---------|-------|
| float | `300.0` | ≥ 0 (`0` disables the timeout) |

Maximum wall-clock time allowed for a single Runner invocation before it is
treated as a failure. Set to `0` to disable the per-invocation timeout
entirely (not recommended for CI, where a hung Runner would block the run
indefinitely).

### `sampling.retries`

| Type | Default | Range |
|------|---------|-------|
| int | `1` | ≥ 0 |

Number of additional attempts made for a single sample after it fails or
times out, before counting it as a failure toward `max_failure_rate`. `0`
disables retries — the first failure counts immediately.

### `sampling.retry_backoff_seconds`

| Type | Default | Range |
|------|---------|-------|
| float | `2.0` | ≥ 0 |

Delay before each retry attempt. Helps ride out transient issues (rate
limits, brief network blips) without hammering the Runner immediately after
a failure.

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

### `thresholds.latency_ms`

Change in per-invocation latency, in milliseconds.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `warn` | float | `1000` | Absolute change of ≥ 1000ms in latency → WARN |
| `fail` | float | `5000` | Absolute change of ≥ 5000ms in latency → FAIL |

### `thresholds.tokens`

Change in tokens consumed per invocation.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `warn` | float | `200` | Absolute change of ≥ 200 tokens → WARN |
| `fail` | float | `1000` | Absolute change of ≥ 1000 tokens → FAIL |

### `thresholds.error_rate`

Change in the fraction of invocations that error out.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `warn` | float | `0.1` | Absolute change of ≥ 0.1 in error rate → WARN |
| `fail` | float | `0.25` | Absolute change of ≥ 0.25 in error rate → FAIL |

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

### `capture.redaction`

Controls what sensitive data is scrubbed from captured request/response
bodies before they are stored in a trajectory.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `mode` | string | `"standard"` | `"standard"`: redact common secret-shaped fields (auth headers, API keys, tokens). `"strict"`: also redact free-text fields that match `patterns` and anything listed in `redact_fields`. `"off"`: disable redaction entirely (not recommended — raw bodies may contain credentials). |
| `patterns` | list[string] | `[]` | Extra regexes (Python `re` syntax) matched against body text; matches are replaced with a redaction marker. Only applied when `mode: strict`. |
| `redact_fields` | list[string] | `[]` | Extra JSON field names (case-insensitive) to redact wherever they appear in a captured body, on top of the built-in list. Only applied when `mode: strict`. |
| `capture_raw_bodies` | bool | `false` | When `true`, also stores the pre-redaction raw body alongside the redacted one, for local debugging. Never enable this in a shared or CI environment — it defeats the purpose of redaction. |

**Example:**
```yaml
capture:
  redaction:
    mode: strict
    patterns:
      - '\d{3}-\d{2}-\d{4}'   # SSN-shaped strings
    redact_fields:
      - authorization
      - x-api-key
    capture_raw_bodies: false
```

---

## `stats`

Controls the statistical correction applied when many metrics are compared
at once, to limit false positives from multiple comparisons.

| Field | Type | Default | Values | Meaning |
|-------|------|---------|--------|---------|
| `correction` | string | `"benjamini_hochberg"` | `"benjamini_hochberg"` \| `"none"` | Multiple-comparison correction applied to per-metric p-values before gating WARN/FAIL. `"none"` disables correction (each metric's p-value is used as-is). |
| `alpha` | float | `0.05` | `0 < alpha <= 1` | Significance level used by the correction and by the underlying tests (z-test, Mann-Whitney U). |
| `min_samples_warn` | int | `5` | ≥ 0 | If `samples_per_case` is below this value, the report emits a WARN noting that statistical power is low and results may be noisy. |

---

## `output_eval`

Thresholds for the output-quality evaluators (semantic similarity, length
ratio, structural diff, and LLM-judge score) that compare baseline and
candidate outputs directly, independent of the behavioral trajectory
comparison.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `semantic_fail` | float | `0.70` | Semantic similarity score below this → FAIL |
| `semantic_warn` | float | `0.85` | Semantic similarity score below this (and ≥ `semantic_fail`) → WARN |
| `length_fail` | float | `0.50` | Output length ratio below this → FAIL |
| `length_warn` | float | `0.80` | Output length ratio below this (and ≥ `length_fail`) → WARN |
| `structural_fail` | float | `0.70` | Structural similarity score below this → FAIL |
| `structural_warn` | float | `0.90` | Structural similarity score below this (and ≥ `structural_fail`) → WARN |
| `judge_fail` | float | `2.0` | LLM-judge score (1–5 scale) below this → FAIL |
| `judge_warn` | float | `3.5` | LLM-judge score below this (and ≥ `judge_fail`) → WARN |

Requires `llm_provider` and its API key to be configured for `judge_fail`
and `judge_warn` to take effect; otherwise the judge evaluator is skipped
and only semantic/length/structural thresholds apply.

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

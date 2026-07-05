# Data Handling

AgentDiff's core job is intercepting HTTP traffic and SDK calls to your LLM
provider. That data can contain secrets and sensitive content, so this page
documents — truthfully, against the current implementation — what is
captured, what is redacted by default, where it's stored, and how to turn
capture off entirely.

## What is captured

Every LLM (and, where enabled, tool/framework) call observed via the `httpx`,
`requests`, `aiohttp`, and gRPC capture layers, plus the optional Anthropic,
OpenAI, and MCP SDK shims. For a captured call this includes the request URL
(query string stripped — see below), headers, request/response bodies, and,
for recognized providers, a normalized `CanonicalLLMCall` (system prompt,
messages, tool-use blocks, response text, token usage, stop reason, sampling
parameters).

Query strings are always stripped from captured URLs regardless of redaction
mode (`redact_url` in `src/agentdiff/capture/http/redact.py`) — this runs
before any `RedactionConfig` mode check.

## Redaction modes (default-on)

Redaction is **on by default** and applies to everything above — headers,
raw bodies, and canonical fields — immediately before a capture event is
constructed. Configure it under `capture.redaction` in `.agentdiff/config.yaml`
(`RedactionConfig` in `src/agentdiff/config.py`):

```yaml
capture:
  redaction:
    mode: standard        # standard (default) | strict | off
    patterns: []          # extra regexes to mask, in addition to the built-ins
    redact_fields: []      # extra header names to drop, in addition to the built-ins
    capture_raw_bodies: false
```

### `standard` (default)

- Known secret patterns are masked to **`[REDACTED]`** wherever they appear
  in text, bodies, or canonical fields: OpenAI-style `sk-...` keys, Anthropic
  `sk-ant-...` keys, Slack `xox[bpars]-...` tokens, `Bearer ...` values,
  AWS `AKIA...` access key IDs, PEM key/cert blocks, and generic
  `api_key: ...` / `api-key=...` assignments.
- Headers **`Authorization`, `X-Api-Key`, `Api-Key`, and `Cookie`**
  (case-insensitive) are always dropped from captured header maps, plus any
  header name listed in `redact_fields`.
- Message/system/tool content is otherwise stored as captured (after pattern
  masking) — this mode is diffable and human-readable while stripping known
  credential shapes.

### `strict`

Everything `standard` does, **plus**: the `system` prompt, every message's
`content`, and `response_text` are replaced with a `sha256:<hex>` digest of
the original text (`hash_content` in `redact.py`). Roles, message counts,
tool names/args structure, token usage, and other metadata are preserved so
before/after trajectory comparison still works — but the actual conversation
content is never persisted, even as a masked string.

### `off` — loud opt-out

Redaction is **fully disabled**. No pattern masking, no header stripping —
request/response data is stored byte-for-byte / value-for-value, including
`Authorization` and friends. There is no partial-off behavior. This exists as
a deliberate escape hatch for local debugging only. **Do not** set
`mode: off` in any config that produces a trajectory file you might share,
commit, or upload — the reports and JSONL/SQLite artifacts described below
will contain unredacted secrets.

## Raw bodies for unrecognized providers

AgentDiff ships canonical parsers for the major providers (Anthropic, OpenAI
Chat/Responses, Gemini, Mistral, Bedrock, Azure OpenAI, Cohere). Traffic to an
unrecognized endpoint is still captured at the raw HTTP layer, but the raw
body is **not** persisted by default — only request/response metadata (URL,
status, timing). Set `capture_raw_bodies: true` in `RedactionConfig` to opt in
to persisting raw bodies for unknown providers; when enabled, those bodies
still pass through the same redaction mode (`standard`/`strict`/`off`) as
everything else before being written.

## Where data is stored

- **`.agentdiff/`** in your project root is the local artifact directory
  created by `agentdiff init` / `quickstart` / `compare`.
- Trajectories are streamed as **JSONL**, one file per baseline/candidate side,
  under `.agentdiff/reports/<timestamp>/` (`TrajectoryStore` in
  `src/agentdiff/storage.py`).
- The same run also gets a queryable **SQLite** artifact,
  `.agentdiff/reports/<timestamp>/agentdiff.sqlite` (WAL mode, schema-versioned),
  containing the loaded trajectory set plus generated report artifacts
  (comparison, attribution, payload).
- `report.md` and the dashboard payload derived from that run live alongside
  the JSONL/SQLite files in the same timestamped directory.
- Cassettes recorded for `agentdiff ci run --tier hermetic` or `agentdiff
  replay` (`.agentdiff/cassettes/*.jsonl` by convention) are regular JSONL
  files subject to the same redaction pipeline at record time.

None of this leaves your machine or CI runner unless you explicitly push it
somewhere (e.g. committing a cassette, uploading a CI artifact, or opting into
the hosted platform below).

## Hosted platform retention

The optional self-hosted platform (`server/` — multi-tenant API + worker +
dashboard, run via `docker compose`) stores ingested Runs and live
trajectories in Postgres rather than local JSONL/SQLite. Retention is
enforced by a daily worker cron and controlled by two environment variables:

| Variable                        | Default | Effect                                              |
|----------------------------------|---------|------------------------------------------------------|
| `AGENTDIFF_RETENTION_DAYS`       | `90`    | Deletes Runs older than N days. `0` disables deletion. |
| `AGENTDIFF_LIVE_RETENTION_DAYS`  | `30`    | Deletes LiveTrajectories older than N days. `0` disables deletion. |

Setting either to `0` keeps data indefinitely for that table — do this
deliberately, and be aware it also means any unredacted content captured
under `mode: off` persists indefinitely in the hosted store as well.

## Disabling capture

- **Per-run, no code changes**: set `capture.<shim>: false` for the shim(s)
  you want off (e.g. `httpx: false`) under `capture:` in
  `.agentdiff/config.yaml`. Each of `httpx`, `requests`, `aiohttp`, `grpc`,
  `openai_sdk`, `anthropic_sdk`, `mcp`, `langgraph`, `crewai`, `autogen`,
  `llamaindex` can be toggled independently.
- **Everything, everywhere**: don't call `agentdiff.record(...)` / run
  `agentdiff compare` / install the autoload hook — capture is opt-in at the
  process level (it only activates inside a `record()` context, a `compare`
  sample, or with the `agentdiff hook` autoloader installed). There is no
  background always-on capture.
- **Autoload hook**: if you've installed the optional import hook
  (`agentdiff hook install`), remove it with `agentdiff hook uninstall`;
  check current status with `agentdiff hook status`.
- **Content only, keep behavioral capture**: use `mode: strict` instead of
  disabling capture — you keep invocation/tool-usage/timing signal for
  regression detection without retaining any conversation content.

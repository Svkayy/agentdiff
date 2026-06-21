# AgentDiff Codebase Reference

A complete, module-by-module, function-by-function walkthrough of the codebase
as it stands. Read this top-to-bottom to understand every moving part, or jump to
a section. Cross-references use `module.function` notation.

---

## 0. Mental model in one paragraph

You point AgentDiff at a Python agent project. `agentdiff init` AST-walks it and
writes `.agentdiff/structure.yaml` (which functions are agents/tools/entry points)
plus config scaffolding. `agentdiff compare --baseline <ref>` then runs your
**Runner** N times on the baseline (a git checkout) and N times on the candidate
(your working tree), with capture shims active. Every LLM/tool call becomes an
**event**; events for one run group into a **trajectory** (one JSONL line). The
**comparison engine** diffs baseline-vs-candidate behavior per agent; the **output
evaluator** does the traditional text comparison; the **attribution engine** maps
each behavioral delta back to a changed file via a manifest diff + git diff + a
rule pipeline. A Markdown **report** ties it together.

The foundational design choice: capture is at the **HTTP layer**, so it works for
any provider; SDK shims are optional enrichment, deduplicated against the HTTP
layer so each logical call produces exactly one event pair.

---

## 1. Directory map

```
src/agentdiff/
├── __init__.py              install()/uninstall()/tool — the public surface
├── capture/
│   ├── tracer.py            Tracer (ContextVar), dedup, inferred_agent, JSONL flush
│   ├── events.py            all Pydantic event models + CanonicalLLMCall
│   ├── callstack.py         capture + classify Python stack frames
│   ├── activator.py         install/uninstall all shims in order
│   ├── decorators.py        @agentdiff.tool
│   ├── http/
│   │   ├── httpx_shim.py     patches httpx Client/AsyncClient.send
│   │   ├── requests_shim.py  patches requests HTTPAdapter.send
│   │   ├── provider_registry.py  URL → provider name; custom providers.yaml
│   │   ├── canonical.py      provider → parser dispatch
│   │   └── parsers/          one module per provider family
│   └── sdk/
│       ├── anthropic_shim.py openai_shim.py mcp_shim.py
├── structure/
│   ├── ast_walker.py        project → CandidateFunction list
│   ├── heuristic_classifier.py  CandidateFunction list → StructureDoc (no LLM)
│   ├── llm_classifier.py    optional LLM refinement (--llm)
│   └── structure_yaml.py    StructureDoc model + load/save/load_nearest
├── trajectory.py            Trajectory + TrajectorySet
├── config.py                typed config.yaml defaults + threshold extraction
├── storage.py               JSONL → TrajectorySet; SQLite run artifact
├── sampling.py              run sync/async Runner N×/side; git-archive checkout
├── stats.py                 two-proportion z-test + Mann-Whitney U (no scipy)
├── compare.py               behavioral comparison + significance → ComparisonResult
├── output_eval.py           text semantic OR structural diff + judge + length
├── llm_client.py            thin Anthropic/OpenAI wrapper (judge + explainer)
├── report.py                ComparisonResult + evals + attribution → Markdown
├── attribution/
│   ├── git_diff.py          per-file unified diffs
│   ├── manifest.py          dynamic per-agent fingerprint
│   ├── manifest_diff.py     ManifestDelta
│   ├── reachability.py      static import-graph BFS (rule 5)
│   ├── rules.py             the 5 attribution rules
│   ├── explainer.py         bounded LLM explanation
│   └── engine.py            attribute() orchestrator
└── cli/
    ├── main.py              click group; registers all commands
    ├── init.py              agentdiff init
    ├── compare.py           agentdiff compare
    ├── doctor.py hook.py    setup diagnostics + autoload hook lifecycle
    ├── structure.py replay.py  v0 stubs
```

---

## 2. Data model

### 2.1 `capture/events.py`

The serialized vocabulary. All models are Pydantic v2 `BaseModel`s (mutable by
default — the Tracer mutates `inferred_agent`/`sequence` after construction).

**`CallSite`** — the nearest user-code location that issued a call.
- `file: str`, `function: str`, `line: int`

**`StackFrame`** — one frame of the captured Python stack, pre-classified.
- `file, function, line`
- `is_user_code: bool` — the user's own project code
- `is_framework_internal: bool` — langchain/langgraph/crewai/etc.
- `is_agentdiff_internal: bool` — agentdiff's own frames
- `is_sdk_internal: bool` — httpx/requests/anthropic/openai/etc.

**`CanonicalLLMCall`** — the provider-normalized representation of one LLM call.
Populated by HTTP parsers (known providers) or SDK shims; the single most
important payload in the system.
- `provider: str` — `"anthropic"`, `"openai_chat"`, `"gemini"`, `"unknown"`, …
- `model: str | None`
- `system: str | None` — flattened system prompt
- `messages: list[dict]` — normalized to `[{"role","content"}, …]`
- `tools: list[dict] | None`
- `sampling_params: dict` — **everything not in a dedicated slot** (temperature,
  max_tokens, top_p, stop_sequences, …). Built by an *exclusion set*, never a
  hardcoded allowlist, so novel params are never dropped.
- `response_text: str | None`
- `tool_use_blocks: list[dict]` — `[{"tool_use_id","name","args"}, …]`
- `stop_reason: str | None`
- `usage: dict[str,int]` — `{"input_tokens","output_tokens","total_tokens"}`

**`LLMRequestEvent`** — emitted before the call returns.
- `event_type="llm_request"`, `event_id: UUID`, `timestamp`, `sequence: int`
- `call_id: UUID` — ties request↔response
- `canonical: CanonicalLLMCall` — request side filled, response side empty
- `captured_by: "sdk_shim" | "http_shim"`
- `sdk_method: str | None` (e.g. `"anthropic.messages.create"`)
- `request_url: str | None`, `raw_body: bytes | None` (only for unknown providers)
- `callsite: CallSite`, `call_stack: list[StackFrame]`, `inferred_agent: str | None`

**`LLMResponseEvent`** — emitted after the call returns.
- `event_type="llm_response"`, `latency_ms: int`
- `call_id`, `canonical` (response side filled), `captured_by`, `raw_body`, `is_error`
- *Note:* no `call_stack`/`inferred_agent` — it correlates to its request by `call_id`.

**`MCPToolInvokedEvent` / `MCPToolReturnedEvent`** — MCP tool calls.
- Invoked: `call_id, server_name, tool_name, arguments, correlates_to_tool_use_id,
  callsite, call_stack, inferred_agent`
- Returned: `call_id, output, is_error, latency_ms`

**`LocalToolInvokedEvent` / `LocalToolReturnedEvent`** — in-process tools wrapped
by `@agentdiff.tool`. Same shape as the MCP pair (Invoked carries `call_stack` +
`inferred_agent`).

**`Event`** — a discriminated union of all six event types, keyed on
`event_type`. This is what lets `Trajectory.events` round-trip through JSON.

### 2.2 `trajectory.py`

**`Trajectory`** — one Runner invocation's full captured behavior.
- `run_id: UUID`, `test_case_id: str`, `version_tag: "baseline"|"candidate"`
- `input: dict`, `final_output: str | None`
- `events: list[Event]`
- `status: "success"|"failed"|"incomplete"`, `error: str | None`
- `total_tokens: int`, `total_latency_ms: int`, `timestamp`
- **`agents_invoked() -> list[str]`** — sorted unique `inferred_agent` values
  across events. After the Tracer's resolution these are structure.yaml *display
  names*.
- **`llm_calls(by_agent=None) -> list[LLMRequestEvent]`** — request events,
  optionally filtered by agent.
- **`tool_calls(by_agent=None) -> list[Event]`** — MCP + local tool *invoked*
  events, optionally filtered.

**`TrajectorySet`** — all trajectories for one side.
- `version_tag`, `trajectories: list[Trajectory]`
- **`for_test_case(id) -> list[Trajectory]`** — filter by test case.

---

## 3. Capture layer

### 3.1 `capture/tracer.py`

Two module-level **ContextVars**:
- `_active_tracer` — the Tracer for the current (possibly async) context. Shims
  read it via `get_active_tracer()`; if `None`, they pass through untouched.
- `_sdk_shim_marker` — `True` while an SDK shim is the outer wrapper. Set/reset
  via `set_sdk_shim_marker()`/`reset_sdk_shim_marker()`.

**`Tracer`** — a context manager owning one trajectory's capture.
- `__init__(test_case_id, version_tag, input_data, output_path, structure_root=None)`
  — loads the nearest `structure.yaml` (via `structure_yaml.load_nearest`) and
  builds `self._agent_map = doc.agent_names_for_functions()` (`{function → display
  name}`, plus simple-name aliases for class methods). Failures degrade to `{}`.
- `__enter__` — binds itself to `_active_tracer`.
- `__exit__` — if an exception propagated, marks `status="failed"` + records the
  error; unbinds; then `_flush()`. (This is why `sampling.run_samples` puts the
  `try` *outside* the `with`: a Runner error reaches `__exit__` and produces a
  `failed` trajectory before being swallowed.)
- **`record(event)`** — under a lock: assigns the next `sequence`; if the event is
  an `http_shim` event captured while `_sdk_shim_marker` is set, tags it
  `_superseded_by_sdk_shim=True` (via `object.__setattr__`, so it's not a model
  field and isn't serialized); then **resolves `inferred_agent`**: walks
  `call_stack` for the first `is_user_code` frame whose `function` is in
  `_agent_map`, and sets the display name — **overriding** the raw function name
  the shim pre-filled. If nothing maps (or no structure.yaml), the shim's raw
  value is kept.
- `set_final_output(output)` — stores the Runner's return value.
- **`_flush()`** — drops superseded events, sums `total_tokens`/`total_latency_ms`,
  builds a `Trajectory`, and appends it as one JSON line to `output_path`.

> **Dedup mechanism in full:** an SDK shim records its own request event (marker
> off), sets the marker, calls the real SDK method (which calls into the patched
> httpx — the HTTP shim records request+response events that get tagged
> superseded), resets the marker, then records its own response event (marker
> off). At flush, superseded events are filtered out → exactly one SDK-enriched
> pair per call. Sequence numbers may have gaps; that's expected.

### 3.2 `capture/callstack.py`

- `capture_call_stack(skip=0) -> list[StackFrame]` — `inspect.stack()`, drops
  itself + `skip` more frames, classifies each via `_classify_frame`.
- `_classify_frame(filename, module_name)` — returns the four booleans. Rules:
  agentdiff modules → agentdiff-internal; stdlib (under `sys.prefix/lib` but not
  site-packages) → all-false; site-packages matching a known SDK/framework
  substring → sdk/framework-internal; other site-packages → sdk-internal;
  everything else → user code.
- `classify_call_stack(frames) -> str | None` — the nearest user-code function
  name (skipping `<module>`). This is the shims' fallback `inferred_agent`.
- `callsite_from_stack(frames) -> CallSite` — nearest user-code frame, falling
  back to the first non-agentdiff frame, then `<unknown>`.

### 3.3 `capture/activator.py` and `__init__.py`

- `activator.install()` — installs shims in order: httpx, requests, anthropic,
  openai, mcp. `uninstall()` reverses it.
- `agentdiff.install()` / `uninstall()` — idempotent wrappers (guarded by a module
  `_INSTALLED` flag). `agentdiff.tool` is re-exported here. This is the entire
  public API: `install`, `uninstall`, `tool`.

### 3.4 `capture/decorators.py`

**`tool(fn=None, *, name=None)`** — decorator for in-process tools dispatched from
LLM `tool_use` blocks. Supports both `@tool` and `@tool(name="x")`. Handles sync
and async (`inspect.iscoroutinefunction`). When a Tracer is active it records a
`LocalToolInvokedEvent` (with bound arguments via `inspect.Signature.bind` +
`apply_defaults`, falling back to raw kwargs) before the call and a
`LocalToolReturnedEvent` after — including the error path (`is_error=True`, output
= `str(exc)`, then re-raise). When no Tracer is active it's fully transparent.

### 3.5 HTTP capture

**`http/provider_registry.py`**
- `ProviderPattern(name, url_re)` — a compiled URL regex + provider name.
- `_PATTERNS` — the 8 built-ins (anthropic, openai_chat, openai_responses, gemini
  incl. streaming, mistral, bedrock, azure_openai, cohere).
- `register(pattern)` — append a custom pattern (later registrations win).
- `match_provider(url) -> str` — first matching pattern name (iterates
  `reversed(_PATTERNS)` so custom patterns beat built-ins), else `"unknown"`.
- `load_custom_providers(project_root) -> int` — reads
  `<root>/.agentdiff/providers.yaml` (`providers: [{name, url_pattern}]`),
  compiles + registers each. Idempotent per name; best-effort (bad regex/file
  skipped). Called from `sampling.run_samples`.

**`http/canonical.py`**
- `_PARSER_MAP` — provider name → parser module.
- `build_canonical_from_http(provider, request, response) -> CanonicalLLMCall` —
  dispatches to the parser; on **any** parser exception (or unknown provider)
  returns `CanonicalLLMCall(provider=provider)` (provider tagged, fields empty).
  `response` is `None` on the request side, or a `(response_obj, body_bytes)`
  tuple on the response side.

**`http/httpx_shim.py`** — patches `httpx.Client.send` (sync) and
`AsyncClient.send` (async) at class level.
- `install()/uninstall()` — swap in/out wrappers; idempotent; no-op if httpx
  absent.
- The wrappers fetch the active tracer (pass through if none), then `_capture_*`:
  match provider, capture stack, build request canonical, record
  `LLMRequestEvent`; call the original; `response.read()` (idempotent — the user's
  later `.json()` still works) / `await response.aread()`; build response
  canonical; record `LLMResponseEvent`. **Every capture step is wrapped in
  try/except that only logs** — the shim never breaks the user's call.

**`http/requests_shim.py`** — patches `requests.adapters.HTTPAdapter.send`
(sync-only). Same flow. Because `requests.PreparedRequest` lacks httpx's
`.content`/`.url`, it wraps the request in **`_RequestsRequestAdapter`** which
exposes both `.content` (body as bytes) and `.url` (so URL-keyed parsers —
bedrock/gemini/azure — work). `_RequestsResponseAdapter` is a minimal wrapper
(parsers only use the body bytes).

**`http/parsers/`** — each exports `parse(request, response) -> CanonicalLLMCall`.
All follow the same shape: parse the request JSON, normalize to canonical request
fields (everything outside the structural set → `sampling_params`); if `response`
is `None` return the request-only canonical; else parse the response body and fill
response fields.
- `anthropic_messages.py` — `messages`/`system` (str or block list)/`tools`;
  response `content[]` text + tool_use blocks; `usage.input/output_tokens`.
- `openai_chat.py` — system extracted from the messages list; response
  `choices[0].message.content` + `tool_calls` (arguments JSON-decoded);
  `prompt/completion_tokens`.
- `openai_responses.py` — `input` (str→one user msg, or list) + `instructions`→
  system; response `output[]` (`message`→`output_text`, `function_call`→tool use).
- `gemini.py` — `contents[]`→messages, `system_instruction`→system,
  `generationConfig` etc.→sampling_params; `_parse_response_body` handles a single
  JSON object, a JSON array, or newline-delimited/SSE chunks (streaming), then
  accumulates text and takes the last `usageMetadata`. Model parsed from the URL.
- `bedrock.py` — routes by model-id prefix (`anthropic`/`amazon`/`meta`/`mistral`/
  `cohere`/`ai21`/`writer`) to family parsers (Anthropic delegates to
  `anthropic_messages`; Amazon → Titan or Nova; Llama/Mistral/Cohere/AI21
  prompt-style). `_parse_generic` + `_extract_text_generic` is the best-effort
  fallback trying every known response shape in order.
- `mistral.py` — delegates to `openai_chat`, overrides `provider="mistral"`.
- `azure_openai.py` — delegates to `openai_chat`, overrides `provider` and pulls
  `model` from the `/deployments/<name>/` URL segment.
- `cohere.py` — `message.content[]` text + `tool_calls`; `usage.tokens` or
  `billed_units`.

### 3.6 SDK shims

**`sdk/anthropic_shim.py`** — patches `Messages.create` / `AsyncMessages.create`.
`_canonical_from_request(kwargs)` reads typed kwargs (model, system as str/blocks,
messages, tools), excluding `_STRUCTURAL` (model/messages/system/tools) and
`_SDK_INTERNAL` (extra_headers/extra_query/extra_body/timeout) from
`sampling_params`. `_canonical_from_response` reads the typed SDK response object
(`block.type`/`.text`/`.id`/`.name`/`.input`, `usage.input/output_tokens`). The
wrapper records the request event (marker off), sets the dedup marker, calls the
original inside try/finally (marker always reset), records the response event.

**`sdk/openai_shim.py`** — same structure for `Completions.create` /
`AsyncCompletions.create`; system pulled from the messages list; response from
`choices[0].message` + `usage.prompt/completion/total_tokens`.

**`sdk/mcp_shim.py`** — patches `ClientSession.call_tool` (async). Records
`MCPToolInvokedEvent` (server name from `self._session.name` if present) then
`MCPToolReturnedEvent` in `finally` (output `None` on error). No dedup marker —
MCP isn't HTTP.

---

## 4. Structure inference

### 4.1 `structure/ast_walker.py`

**`CandidateFunction`** (Pydantic) — `name` (`ClassName.method` for methods),
`file` (relative), `line`, `is_async`, `decorators`, `docstring`, `calls_llm`,
`has_agentdiff_tool_decorator`, `module_imports_llm_sdk`, `class_name`.

- **`walk_project(root) -> list[CandidateFunction]`** — `rglob("*.py")` (skipping
  venv/cache/etc. via `_SKIP_DIRS`), AST-parses each file; for every top-level
  function **and** every method inside a top-level class, builds a
  `CandidateFunction`. **Class methods are only kept if they call an LLM or carry
  a tool decorator** (plain helper methods are skipped to avoid noise).
- `_extract(node, file, imports_sdk, class_name=None)` — collects decorators,
  docstring, runs `_LLMCallVisitor` over the body, and qualifies the name for
  methods.
- `_module_imports_llm_sdk(tree)` — any import of anthropic/openai/mcp/litellm/
  together/cohere.
- `_has_tool_decorator(node)` — `@agentdiff.tool` or `@tool`.
- `_LLMCallVisitor` — detects an LLM call when a call's attribute chain contains
  one of `{create, complete, generate}` **and** one of `{messages, completions,
  chat, responses}`. **Does not recurse into nested function defs** (so a helper
  defined inside an agent isn't miscredited).

### 4.2 `structure/heuristic_classifier.py`

**`classify(candidates) -> StructureDoc`** — maps each candidate via
`_classify_one`, with priority:
1. has tool decorator → **tool**
2. calls LLM → **agent**
3. module imports an LLM SDK **and** name hints agent (contains agent/run_agent/…)
   → **agent**
4. simple name (last dotted segment, so class methods work) in
   `{main, run, start, entrypoint, entry_point}` → **entry_point**
5. else → irrelevant

In the heuristic path, an entry's `name` and `function` are both the candidate's
name (so display name == function name unless the `--llm` pass changes it).

### 4.3 `structure/llm_classifier.py`

**`refine(heuristic_doc, candidates, api_key, model=…) -> StructureDoc`** — one
Anthropic call classifying the candidate list; on import failure returns the
heuristic doc unchanged.
- `_build_prompt` — serializes candidate summaries to JSON.
- **`_parse_response(raw, candidates, heuristic_doc)`** — extracts the JSON array
  (tolerating markdown). **On unparseable output it returns `heuristic_doc`, never
  an empty doc** (so a malformed LLM response can't wipe a valid classification).
  Candidates are keyed by **`(name, file)`** so duplicate function names in
  different files don't collide, with a name-only fallback for minor path
  differences.

### 4.4 `structure/structure_yaml.py`

**Models:** `AgentEntry(name, function, file, line)`,
`ToolEntry(name, function, file, line)`, `EntryPointEntry(function, file, line)`,
**`StructureDoc(version, agents, tools, entry_points)`**.

- **`StructureDoc.agent_names_for_functions() -> dict[str,str]`** — `{function →
  display name}`. For `ClassName.method` agents it **also** registers the bare
  `method` name (without overriding an exact match), because Python call-stack
  frames only carry the bare method name. This is exactly what the Tracer uses to
  resolve `inferred_agent`.
- `tool_names_for_functions()` — analogous for tools.
- `save(doc, project_root) -> Path` — writes `<root>/.agentdiff/structure.yaml`
  (human-readable, `sort_keys=False`).
- `load(project_root) -> StructureDoc | None`.
- `load_nearest(cwd=None) -> StructureDoc | None` — walks up from `cwd` looking for
  `.agentdiff/structure.yaml`. Used by the Tracer at capture time.

---

## 5. Sampling & storage

### 5.1 `sampling.py`

- **`run_samples(runner_module, runner_callable, test_cases, samples_per_case,
  version_tag, output_path, structure_root=None, progress=True) -> int`** — the
  in-process loop, importable so the subprocess path reuses it. Loads custom
  providers from `structure_root`, imports the Runner, and for each test case ×
  sample wraps a `Tracer` (with `structure_root` for agent resolution), calls
  `runner(input)`, and stores the normalized output. The `try` is *outside* the
  `with` so a Runner exception yields a `failed` trajectory without aborting the
  run. Returns the count written.
- **`sample_for_side(*, git_ref, runner_module, runner_callable, test_cases,
  samples_per_case, version_tag, output_path, repo_root)`** — calls
  `agentdiff.install()`, then: `git_ref=None` → `run_samples` in place (working
  tree); otherwise `_checked_out` (`git archive <ref> | tar -x` into a temp dir +
  `_install_deps`) and `_sample_in_checkout`.
- `_load_runner` — import + validate callable.
- `_normalize_output(result)` — `None`→`""`, `str`→as-is, else `json.dumps(..,
  default=str)`.
- `_checked_out` / `_install_deps` — temp-dir checkout + best-effort
  `pip install -e .` or `-r requirements.txt`.
- `_sample_in_checkout` — writes params JSON, runs `_SUBPROCESS_TEMPLATE` via
  `python -c` (prepends the checkout to `sys.path`, installs shims, calls
  `run_samples`) so the checked-out code wins on import.

### 5.2 `storage.py`

- **`load_trajectory_set(filepath, version_tag) -> TrajectorySet`** — reads JSONL,
  validates each line into a `Trajectory` (the `Event` discriminated union
  deserializes each event by `event_type`), tolerating blank/corrupt lines.
  Missing file → empty set.
- `append_trajectory(filepath, traj)` — append one JSONL line (used by tests/tools;
  the Tracer writes the same way directly).

---

## 6. Comparison — `compare.py`

**Result models:** `AgentInvocationDelta`, `ToolUsageDelta`, `TestCaseComparison`
(`__test__ = False` so pytest doesn't try to collect it), `ComparisonResult`. Each
carries a `verdict ∈ {pass, warn, fail}`.

- `compute_invocation_rates(trajectories, structure)` — fraction of trajectories
  each agent (by **display name**) appears in (via `agents_invoked()`).
- `compute_tool_averages(trajectories)` — mean invocations per trajectory, keyed by
  observed `tool_name`.
- `_jaccard(a, b)` — set overlap (`None` if both empty).
- **`compare_test_case(id, baseline, candidate, structure) -> TestCaseComparison`**
  — per-agent invocation deltas (verdict thresholds: |Δ| ≥ 0.5 fail, ≥ 0.2 warn),
  per-tool average deltas (|Δ| ≥ 1.0 fail, ≥ 0.5 warn), tool-set Jaccard overlap,
  and an overall verdict = worst component.
- **`compare_all(baseline_set, candidate_set, structure, test_case_ids=None) ->
  ComparisonResult`** — runs `compare_test_case` per test case; overall verdict =
  worst.

> Because invocation rates key on `agent.name` and `agents_invoked()` now returns
> display names (Tracer resolution), the two line up regardless of whether the
> display name differs from the function name.

---

## 7. Output evaluation

### 7.1 `output_eval.py`

**`OutputEvalResult`** — `test_case_id, semantic_similarity, judge_score,
length_ratio, verdict, notes`.

- `_get_model()` — lazily loads `SentenceTransformer("all-MiniLM-L6-v2")`
  (singleton). `_default_embed(texts)` encodes; `_cosine` computes similarity.
- `_representative(outputs)` — first non-empty output per side.
- `_length_ratio` — shorter/longer length.
- **`evaluate_output(test_case_id, baseline_outputs, candidate_outputs,
  llm_client=None, embed_fn=None) -> OutputEvalResult`** — picks representatives;
  if both empty → PASS with a note (side-effecting agent); else computes semantic
  similarity (`embed_fn` injectable for tests), length ratio, and an optional LLM
  judge; combines via `_combine_verdict` (semantic < 0.70 fail / < 0.85 warn;
  judge ≤ 2 fail / ≤ 3.5 warn; length < 0.50 fail / < 0.80 warn; overall = worst).
- `_run_judge` — prompts the LLM for a 1–5 integer; parses the first 1–5 token.

### 7.2 `llm_client.py`

**`LLMClient(provider=None, api_key=None, model=None)`** — the **only** LLM caller
inside AgentDiff itself (judge + explainer). Its constructor **asserts no Tracer is
active** (`get_active_tracer() is None`) so AgentDiff's own calls are never
captured as agent behavior. `provider` defaults from `AGENTDIFF_LLM_PROVIDER`.
`model` defaults to `claude-3-5-haiku` / `gpt-4o-mini`. `complete(system, prompt,
max_tokens)` lazily builds the client and returns text, degrading to `""` on any
error.

---

## 8. Attribution

### 8.1 `attribution/git_diff.py`

**`collect_git_diff(baseline_ref, candidate_ref_or_working, repo_root) ->
dict[file, diff_text]`** — `git diff --name-only` then per-file `git diff`.
`"working"` diffs the working tree against the baseline ref. Best-effort (returns
`{}` on git failure).

### 8.2 `attribution/manifest.py`

**`AgentManifest`** — `agent_name, function, code_file, code_hash, prompt_files,
prompt_hashes, prompt_content_hash, model_params` (named `model_params`, **not**
`model_config`, to avoid pydantic's reserved name).

- `read_source_at(repo_root, ref, relpath)` — file content at a side: working
  tree (`ref=None`) reads disk; a ref uses `git show ref:path`.
- `_tool_names(tools)` — extracts tool names from Anthropic- or OpenAI-shaped tool
  dicts.
- `_collect_observed_prompts(agent_name, trajectories)` — unique `canonical.system`
  strings from events whose `inferred_agent == agent_name` (the display name).
- `_aggregate_model_params(agent_name, trajectories)` — most-common observed
  `(model, sampling_params, tools)` for that agent.
- `_attribute_prompts_to_files(repo_root, prompts)` — finds which working-tree file
  each prompt string lives in (scans `.txt/.md/.py/.yaml/.j2/…`), else a synthetic
  `<inline-prompt:hash>`. Used to *name* the prompt's file; change detection is
  done via the content hash + git diff.
- `_extract_function_source(source, qualname)` — AST-extracts a top-level function
  or `Class.method` source segment (for the code hash).
- **`build_manifest_for_side(repo_root, ref, trajectories, structure) ->
  dict[function, AgentManifest]`** — per agent: observed prompts + files, function
  source hash (read at that side), aggregated model params, content hashes.

### 8.3 `attribution/manifest_diff.py`

**`ManifestDelta`** — per agent: `prompt_changed`, `prompt_files`, `code_changed`,
`code_file`, `model_params_changed`, `model_params_before/after`, `tools_changed`,
`tools_before/after`; `has_any_change()`.

**`diff_manifests(baseline, candidate) -> dict[function, ManifestDelta]`** —
compares hashes/params; model-params change is computed *excluding* tools (tools
get their own flag).

### 8.4 `attribution/rules.py`

**`Attribution`** — `rule, target_path, hunk, weight, reason`.

`apply_rules(md, git_diff, structure)` runs all direct rules and only falls back to
`reachable_change` if none fired:
1. `_rule_direct_prompt_change` (0.9) — a changed prompt file in the diff (or 0.75
   if the prompt is inline in the agent's code file).
2. `_rule_code_change` (0.8) — the agent's function body changed and its file is in
   the diff.
3. `_rule_model_config_change` (0.7) — model/sampling params changed (targets the
   code file).
4. `_rule_tool_schema_change` (0.6, or 0.5) — the agent's tool set changed (targets
   a changed tool file from structure, else the code file).
5. `_rule_reachable_change` (0.2) — fallback: something changed but nothing direct
   matched (v0 heuristic; full reachability is v1).

### 8.5 `attribution/explainer.py`

**`explain(client, agent_name, delta_summary, verdict, primary) -> str | None`** —
a strictly-templated, bounded LLM call producing a 1–3 sentence explanation. The
model is **never** asked to choose the attribution — that's already decided by the
rules.

### 8.6 `attribution/engine.py`

**`BehavioralAttribution`** — `test_case_id, agent_name, function, metric,
delta_summary, verdict, primary, alternatives, explanation`.
**`AttributionResult`** — `attributions: list[BehavioralAttribution]`.

**`attribute(comparison, structure, baseline_trajectories, candidate_trajectories,
repo_root, baseline_ref, candidate_ref, llm_client=None) -> AttributionResult`** —
collects the git diff (`candidate_ref=None` → `"working"`), builds both sides'
manifests, diffs them, and for **every non-passing agent invocation delta** runs
`apply_rules`, ranks by weight (primary = highest, rest = alternatives), and
optionally attaches an explanation.

---

## 9. Report — `report.py`

**`render_report(comparison, output_evals, meta, attribution=None) -> str`** —
assembles the Markdown:
1. `_header` — refs, sample math, overall verdict.
2. `_summary_table` — the headline `| test case | traditional | AgentDiff |` row.
3. `_behavioral_findings` — per test case: agent invocation-rate table, tool-usage
   table, Jaccard overlap.
4. `_attribution_section` — per non-passing delta: primary cause file + rule +
   confidence + reason + (optional) explanation + diff hunk + alternatives.
5. `_repro` — the reproduction command.

Verdicts render as text `PASS/WARN/FAIL` (no emojis).

---

## 10. CLI

- **`cli/main.py`** — the `click` group; registers `init`, `compare`, `doctor`,
  `hook`, `structure`, `replay`. Entry point `agentdiff` (pyproject
  `[project.scripts]`).
- **`cli/init.py`** — `agentdiff init [PATH] [--llm] [--install-hook/--no-install-hook]`:
  `walk_project` → `classify` (→ optional `refine`) → `structure_yaml.save`;
  `_write_default_configs` writes `config.yaml`/`test_cases.yaml`/`providers.yaml`
  (never clobbering existing); `--install-hook` explicitly writes
  `agentdiff_autoload.pth` (`import agentdiff; agentdiff.install()`) into
  site-packages (path overridable for tests via `autoload_pth_path`). Prints a
  Rich table of Function | Role | File.
- **`cli/compare.py`** — `agentdiff compare [--baseline --candidate --test-cases
  --samples --output --project --install-deps/--no-install-deps
  --max-failure-rate]`: loads typed config + test cases + structure; samples
  baseline (git ref) and candidate (working/ref) into JSONL; enforces the sample
  failure budget; loads both sets; `compare_all` with configured thresholds; builds
  an `LLMClient` *only if the matching API key is present*; `evaluate_output` per
  test case; `attribution_engine.attribute`; renders the report + writes
  `metadata.json` and `agentdiff.sqlite`.
- **`cli/doctor.py`** — validates config, structure.yaml, test cases, runner
  importability, git baseline, hook state, API keys, and optional dependencies.
- **`cli/hook.py`** — `agentdiff hook status/install/uninstall` for the optional
  `.pth` startup hook.
- **`cli/structure.py` / `cli/replay.py`** — v0 stubs that print a "not implemented"
  message.

---

## 11. End-to-end data flow (`agentdiff compare`)

```
config.yaml + test_cases.yaml + structure.yaml
        │
        ▼
sampling.sample_for_side(baseline ref)  ── git archive → subprocess → run_samples
sampling.sample_for_side(working)       ── in-process run_samples
        │  each run: Tracer → shims capture events → inferred_agent resolved
        ▼
baseline_trajectories.jsonl + candidate_trajectories.jsonl
        │
storage.load_trajectory_set ×2
        ▼
compare.compare_all ────────────► ComparisonResult (configured thresholds)
output_eval.evaluate_output ────► [OutputEvalResult]   (semantic + judge + length)
attribution.engine.attribute ──► AttributionResult     (manifest diff + git diff + rules)
        │
report.render_report
        ▼
.agentdiff/reports/<timestamp>/report.md
        │
        ▼
metadata.json + agentdiff.sqlite + the two JSONL files
```

---

## 12. Tests (what proves what)

- `test_providers.py` — every provider parser + sampling-param passthrough; Gemini
  streaming; Bedrock families.
- `test_sdk_shims.py` — dedup contextvar behavior; `@agentdiff.tool` sync/async/
  error/transparency; SDK/MCP shims (skipped if SDK absent).
- `test_init.py` — AST walker, heuristic classifier, structure.yaml round-trip,
  `agentdiff init` end-to-end.
- `test_storage.py` — JSONL round-trip, corrupt-line tolerance, SQLite run-store
  round-trip.
- `test_config.py` — typed config defaults, thresholds, and capture config.
- `test_compare.py` — invocation/tool deltas, configurable verdict thresholds,
  Jaccard, worst-of aggregation.
- `test_sampling.py` — in-place loop, async runners, output normalization,
  failed-runner → `failed` trajectory.
- `test_output_eval.py` — identical/different/empty/length/judge paths (embeddings
  injected).
- `test_report.py` — all sections render; the PASS-vs-FAIL headline.
- `test_attribution.py` — manifest diff, each rule, and an end-to-end prompt-change
  attribution with a diff hunk (real git repo).
- `test_cli.py` — command registration, init scaffolding, autoload hook lifecycle.
- `test_integration_compare.py` — full `agentdiff compare` across a real git ref
  (git-archive → subprocess path), embeddings stubbed, no API key.
- `test_fixtures.py` — the event-driven recipe fixture runs offline + is
  structure-inferable.
- `test_review_fixes.py` — the three review patches (display-name resolution,
  requests `.url`, providers.yaml loading).

Current status should be checked with `pytest`; optional SDK/provider tests still
skip when their dependencies are not installed.

---

## 13. Upgrades beyond the original v0 spec

These were originally deferred but are now implemented:

- **Statistical significance** (`stats.py`) — invocation deltas use a two-proportion
  z-test, tool-usage deltas a Mann-Whitney U test (normal approximation,
  tie-corrected; no scipy). A non-significant effect is **downgraded** (fail→warn,
  warn→pass), so a large-but-uncertain delta at small N surfaces as WARN rather than
  a hard FAIL. p-values + a significance marker (`*`) appear in the report.
- **Structural output evaluation** (`output_eval.py`) — dict/list outputs (Runner
  structured returns) get a recursive structural diff (`_structural_compare`:
  matching leaves / union of leaf paths + a list of differing paths) instead of text
  semantic similarity. `OutputEvalResult.output_kind ∈ {text, structured, empty}`.
- **Real reachability** (`attribution/reachability.py`) — rule 5 (`reachable_change`)
  now does a static import-graph BFS from the agent's code file; a changed file that
  is provably reachable is attributed with higher confidence (0.35) than the blind
  heuristic fallback (0.2).
- **Cohere v1 + v2** — the parser handles both the v2 `message.content[]` shape and
  the v1 top-level `text` / `generations[]` shape; the registry matches `/v[12]/chat`.
- **MCP output is serialized safely** — `_safe_output` dumps pydantic results to
  JSON and falls back to `str()` for exotic objects, so trajectories always
  serialize.
- **Graceful git validation** — `agentdiff compare` validates the repo + baseline/
  candidate refs up front (`git_validation_error`) and prints a clear message
  instead of a deep traceback.
- **Infra hardening** — typed config (`config.py`), configurable thresholds,
  selective capture shim installation, explicit hook lifecycle commands,
  `agentdiff doctor`, async runner support, fail-loud checkout dependency install,
  sample failure budgets, and a SQLite run artifact (`agentdiff.sqlite`).

## 14. Remaining v0 simplifications (still deferred)

- JSONL is still the streaming capture format; SQLite is written as a post-run
  artifact, not yet the live capture backend. Sampling is sequential.
- Streaming LLM-body reconstruction, framework enrichment adapters, tool replay, and
  `aiohttp`/grpc capture are v1+ (the HTTP layer still captures these providers; only
  the richer handling is deferred).
- Reachability is file-level (not symbol-level) and resolves project-local imports
  only; src-layout absolute imports may under-resolve (degrades to the blind
  fallback).
```

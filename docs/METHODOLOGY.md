# Methodology

How AgentDiff goes from "you changed some code" to "here's the behavioral
regression and the file that caused it."

## 1. Capture

Two layers, installed by `agentdiff.install()` (which the venv autoload hook and
the sampling engine call for you):

- **HTTP layer** — monkey-patches `httpx.Client.send` / `AsyncClient.send` and
  `requests`' `HTTPAdapter.send`. Every outbound request is matched against a
  provider registry (URL → provider). Known providers get a canonical parser;
  unknown ones are captured as raw request/response bytes tagged with the URL.
  This is why capture works on any provider.
- **SDK layer** — optional shims for the Anthropic and OpenAI SDKs and for MCP
  `call_tool`. When an SDK shim wraps a call, it sets a contextvar so the HTTP
  shim's would-be duplicate event is marked and dropped at flush time. Result:
  exactly one richly-typed event per logical call.

Each captured call becomes an `LLMRequestEvent` + `LLMResponseEvent` pair with a
provider-normalized `CanonicalLLMCall` (system prompt, messages, model, sampling
params, tools, response text, tool-use blocks, token usage). Tool calls become
`MCPToolInvoked/Returned` or `LocalToolInvoked/Returned` events. Every event
carries a call stack and an `inferred_agent` label.

## 2. Structure inference

`agentdiff init` AST-walks the project, collecting candidate functions (top-level
and class methods) with signals: does it call an LLM SDK? does it carry
`@agentdiff.tool`? does the module import an LLM SDK? A heuristic classifier maps
each to **agent**, **tool**, **entry_point**, or **irrelevant**, and writes
`.agentdiff/structure.yaml`. An optional `--llm` pass refines the classification;
if its output is unparseable it falls back to the heuristic result rather than
discarding it.

At capture time the Tracer loads the nearest `structure.yaml` and labels each
event's `inferred_agent` by matching the call stack against the agent map — so
every LLM/tool event is attributed to the agent that issued it.

## 3. Sampling

For a test case, AgentDiff runs your Runner N times per side. The **baseline**
side is checked out with `git archive <ref> | tar -x` into a temp dir and sampled
in a subprocess (so the checked-out code wins on import); the **candidate** side
is the working tree (or another ref). Each run is wrapped in a Tracer that writes
one trajectory per line to JSONL.

## 4. Comparison

Per test case, over the loaded `structure.yaml` (nothing hardcoded):

- **Agent invocation rate** — fraction of trajectories each agent appears in.
  Effect-size thresholds |Δ| ≥ 0.5 → FAIL, ≥ 0.2 → WARN, **gated by a
  two-proportion z-test**.
- **Tool usage** — mean invocations per trajectory, per tool. |Δ| ≥ 1.0 → FAIL,
  ≥ 0.5 → WARN, **gated by a Mann-Whitney U test** on the per-trajectory counts.
- **Behavioral overlap** — Jaccard of the tool sets exercised on each side.

**Statistical gating:** a flagged effect that is *not* statistically significant
(p ≥ alpha, default 0.05) is downgraded one level (FAIL→WARN, WARN→PASS). So a big
difference seen across only a handful of samples surfaces as WARN ("possible
regression — collect more samples"), not a hard FAIL. p-values appear in the report
(a `*` marks significance). The tests live in `stats.py` (two-proportion z-test +
Mann-Whitney U with a normal approximation and tie correction — no scipy
dependency), and the same significance/downgrade logic applies uniformly to agent
invocation deltas, tool usage deltas, and run-metric deltas (latency, tokens, error
rate).

**Multiple-comparison correction (Benjamini-Hochberg):** a single comparison run
produces one p-value per delta — one per agent, one per tool, one per run metric,
for every test case. Testing that many hypotheses at an uncorrected alpha of 0.05
means false positives ("significant" deltas that are just noise) pile up as the
number of agents/tools/test cases grows. `config.stats.correction` controls how
this is handled:

- `benjamini_hochberg` (default) — every p-value across the *entire* comparison
  (every delta, every test case) is treated as one family and corrected with the
  Benjamini-Hochberg step-up procedure (`stats.benjamini_hochberg`), which controls
  the expected false discovery rate rather than the per-test error rate. The
  correction runs once, after every test case has been compared — not per test case
  — so the family size reflects the true number of hypotheses tested in the run.
  Each delta keeps its raw `p_value` and gains an `adjusted_p_value`; `significant`
  and the verdict-downgrade in the previous section switch to using
  `adjusted_p_value` instead of `p_value`. A delta that looked significant (and
  therefore FAIL) at the raw p can end up downgraded to WARN once corrected for the
  size of the family — this is expected and is the point of the correction.
- `none` — restores pre-correction behavior: `adjusted_p_value` mirrors `p_value`,
  and gating uses the raw p-value directly.

`config.stats.alpha` (default 0.05) is the significance threshold applied to
whichever p-value (raw or adjusted) is in effect.

**Low-power warnings:** a p-value — corrected or not — is only as trustworthy as
the sample it was computed from. Any delta where either side has fewer trajectories
than `config.stats.min_samples_warn` (default 5) is flagged `low_power: True`. The
comparison result carries a run-level `warnings: list[str]` with one entry per
affected test case, surfaced both in the Markdown report (a "Warnings" section
near the top) and in the dashboard JSON payload, so a clean-looking PASS/FAIL
verdict from a 3-sample run doesn't get read with more confidence than it deserves.

## 5. Output evaluation

The "traditional eval" half of the headline row. The path depends on the output
shape:

- **Text outputs** — semantic similarity (sentence-transformers cosine) + an
  optional LLM judge (1–5 equivalence) + a length-consistency ratio.
- **Structured outputs** (the Runner returned a dict/list, JSON-serialized by the
  sampler) — a recursive **structural diff**: similarity = matching leaves / union of
  leaf paths, plus the list of differing key paths. Optionally combined with the
  judge.

Either way it combines into PASS/WARN/FAIL. The whole point is that this can report
PASS while the behavioral comparison reports FAIL.

## 6. Causal attribution

For every non-passing agent invocation delta:

1. Build a **manifest** per agent on each side — observed prompts (+ the files
   they live in), the agent function's source hash, and observed model config —
   from the captured trajectories plus source read at that side.
2. **Diff** the manifests: prompt changed? code changed? model config changed?
   tools changed?
3. Collect the **git diff** (baseline ref vs candidate ref/working).
4. Run the **rule pipeline**, ranked by confidence:
   - `direct_prompt_change` (0.9) — a changed prompt file in the diff
   - `code_change` (0.8) — the agent's function body changed
   - `model_config_change` (0.7) — model/sampling params changed
   - `tool_schema_change` (0.6) — the agent's tool set changed
   - `reachable_change` (0.35 / 0.2) — fallback when nothing direct matched. A
     static import-graph BFS from the agent's code file (`reachability.py`)
     determines which changed files are actually reachable; a reachable changed file
     gets 0.35, otherwise a blind heuristic gets 0.2.
5. The highest-weight attribution is the **primary cause**; the rest are
   alternatives. An optional bounded LLM call writes a 1–3 sentence explanation —
   it is never asked to choose the attribution.

## 7. Report

A Markdown report assembles the header, the traditional-vs-AgentDiff side-by-side,
the behavioral findings, the attribution (primary cause + rule + diff hunk +
explanation + alternatives), and a reproduction command.

## Storage

v0 uses JSONL (one trajectory per line), written incrementally by the Tracer.
SQLite with privacy views is v1.

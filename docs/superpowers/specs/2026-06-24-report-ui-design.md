# AgentDiff Report UI + Real Demo — Design Spec

- **Date:** 2026-06-24
- **Branch:** `feat/report-ui` (off `origin/main` @ `c722502`)
- **Status:** Approved design, pending spec review
- **Baseline:** 189 passed, 2 skipped (`pytest tests/ -q`)

## 1. Goal

Make AgentDiff the portfolio capstone: a YC-grade report/dashboard UI that renders
**AgentDiff's real report data**, demonstrated with **GIFs of the actual UI on a real
`agentdiff compare` run**, plus a strong README and GitHub profile page.

Non-negotiables (from the user's standards):
- **Real proof only.** Every screen renders data AgentDiff genuinely produced. No mockups, no fabricated output.
- **Tests stay green.** Extend the suite for new UI↔backend glue; externals mocked; pristine output; keep/extend CI.
- **No secrets committed.** `.gitignore` covers `.env`/`node_modules`/caches; `.env.example` only; secret-scan tree + history before any push.
- **Branch + PR.** Small reviewed commits; PR at the end; never push to main directly.

## 2. Explicit non-goal: do NOT reinstrument AgentDiff

The AgentDiff engine (`src/agentdiff/capture`, `attribution`, `compare`, `stats`,
`storage`, `report`, `cli`) keeps all of its capture / diff / attribution / stats logic
**unchanged**. The only additive, non-invasive glue (§4) is: a new **read-only** payload
module plus the dashboard injection that surfaces it to the UI, and one additive **Ollama
branch** on the LLM client. The "multi-agent framework" in this spec is the **sample app
under test** (agent-under-test), not a reimplementation of AgentDiff.

## 3. The demo: a real run with a real regression

### 3.1 The sample app (agent-under-test)
A small but real **research-assistant** multi-agent framework at
`examples/research_assistant/`:

```
examples/research_assistant/
  agents/
    orchestrator.py      # deterministic, rule-based router (no LLM coin-flips for routing)
    retriever.py         # retriever_agent — Ollama call
    fact_checker.py      # fact_checker_agent — Ollama call (the one that will stop firing)
    summarizer.py        # summarizer_agent — Ollama call
  tools.py               # @agentdiff.tool web_search, calculator
  prompts/
    orchestrator.md      # routing policy text (the file the regression edits)
  runner.py              # AgentDiff Runner: run(input) -> str
  .agentdiff/
    structure.yaml       # maps functions -> agent names (drives inferred_agent)
    config.yaml          # runner module/callable, llm_provider, capture, samples
    test_cases.yaml      # a handful of real queries
  README.md              # how to run the demo
  run_demo.sh            # reproducible: git-init temp copy, commit baseline, apply
                         # candidate, run `agentdiff compare`, copy report to docs/demo/
```

- Sub-agents call **Ollama `llama3.1:8b`** via the `openai` SDK pointed at
  `http://localhost:11434/v1`. AgentDiff's SDK/HTTP shim captures these as real LLM calls.
- **Routing is deterministic in code** (the orchestrator decides which sub-agents fire
  from the query via a rule, not by asking the model). This is what makes the behavioral
  delta 100% reproducible across samples even though the sub-agents' Ollama outputs vary.

### 3.2 The regression (baseline → candidate)
One clean diff in `prompts/orchestrator.md` + the matching routing rule:
- **Primary (hero):** `fact_checker` stops being routed → **STOPS firing → FAIL (ember).**
- **Secondary:** `web_search` gets called more often → **tool-usage WARN/FAIL.**
- Final answers still read fine → **traditional output-eval PASSES while AgentDiff FAILS**,
  and attribution maps the fact_checker drop to the exact `orchestrator.md` hunk.
- The Ollama model also writes the 1–3 sentence explanation per attributed delta.

### 3.3 Reproducibility
`run_demo.sh` produces the run without polluting agentdiff's own git history:
1. Copy `examples/research_assistant/` to a temp dir; `git init`; commit baseline.
2. Apply the candidate change (edit `orchestrator.md` + routing rule); leave as working tree.
3. `agentdiff compare --baseline <baseline-commit> --samples N` (Ollama running).
4. Copy the resulting report dir into `docs/demo/sample-report/` (committed — small, real).

Model: `llama3.1:8b` (fast, available). Sample count chosen so the primary delta is
statistically significant (target ~12–20/side; tune during build).

## 4. Backend glue (additive, all unit-tested, externals mocked)

### 4.1 `src/agentdiff/report_payload.py` (new, read-only)
Pure function `build(report_dir: Path) -> dict` that assembles the full UI payload from
the artifacts a `compare` run already wrote (`agentdiff.sqlite` + `metadata.json`). It
**computes nothing new** — it surfaces existing data via `storage.read_artifact` and
`storage.load_trajectory_set_from_sqlite`. Payload shape:

```jsonc
{
  "meta":        { baseline_ref, candidate_ref, samples_per_case, timestamp, smoke_mode },
  "runQuality":  { baseline_trajectories, candidate_trajectories,
                   baseline_failed, candidate_failed, max_failure_rate, thresholds },
  "graph":       { ...existing AgentGraph (graph_model.build)... },
  "comparison":  { overall_verdict, test_case_comparisons: [
                   { test_case_id, overall_verdict, behavioral_overlap,
                     agent_invocation_deltas: [...], tool_usage_deltas: [...] } ] },
  "outputEvals": [ { test_case_id, output_kind, semantic_similarity,
                     structural_similarity, length_ratio, judge_score, verdict, notes } ],
  "attribution": { attributions: [ { agent_name, delta_summary, verdict,
                     primary: { target_path, rule, weight, reason, hunk },
                     alternatives: [...], explanation } ] },
  "trajectories": {
     "baseline":  [ { trajectory_id, test_case_id, status, final_output,
                      total_tokens, total_latency_ms, timeline: [ <event> ] } ],
     "candidate": [ ... ] }
}
```
`timeline` events are projected to the UI's needs: `seq`, `kind`
(`llm_request`/`llm_response`/`mcp_tool_invoked`/`local_tool_invoked`/…), `inferred_agent`,
`provider`, `model`, `latency_ms`, `usage`, `tool_name`, and short request/response
previews (truncated; redaction already applied upstream by capture).

`graph`, `meta` keep their existing shape so the **graph keeps rendering on old payloads**.

### 4.2 `src/agentdiff/dashboard.py` (extend injection)
`summarize_report` / `_payload_json` extended to inject the §4.1 payload as
`window.__AGENTDIFF__`. Existing `{graph, meta}` keys remain; new keys are added. The
`</` → `<\/` script-escape stays.

### 4.3 `src/agentdiff/llm_client.py` (Ollama path, additive)
On the **openai** path only: honor `OPENAI_BASE_URL` (passed to `openai.OpenAI(base_url=...)`)
and a model override (`AGENTDIFF_LLM_MODEL`), so the judge/explainer can target Ollama
(`base_url=http://localhost:11434/v1`, `api_key="ollama"`, `model="llama3.1:8b"`).
`_make_llm_client` in `cli/compare.py` accepts this Ollama-style config. Anthropic and
default OpenAI behavior unchanged. The "never captured" invariant is preserved (these
calls run after sampling exits the Tracer).

### 4.4 Tests (Python)
- `report_payload.build` from a fixture sqlite → asserts every section + timeline projection.
- Ollama client path: mocked `openai.OpenAI`, asserts `base_url`/model wiring; default paths unchanged.
- Dashboard injection includes the new keys and stays valid HTML/JSON; old payloads still render.
- Python↔TS key-parity check (keys the UI reads exist in the payload builder).

## 5. The UI — React + Vite + TS + Tailwind + shadcn/ui, to DESIGN.md

Add **shadcn/ui** to `frontend/` (not present yet); keep `@xyflow/react`. App shell =
left-rail nav + main content. **Dark default**, ember `#FF4D2E` single-signal, Cabinet
Grotesk / Geist / JetBrains Mono (self-hosted), comfortable spacing, subtle motion + the
one-time ember pulse on the stopped node. Sections:

1. **Overview (hero)** — verdict banner (PASS/FAIL, ember on fail), the before/after
   React Flow agent graph (refined, the screenshot moment), trust banner, and the
   "traditional output-eval says PASS / AgentDiff says FAIL" contrast callout + stat chips
   (verdict, # flagged deltas, samples/side, behavioral overlap).
2. **Behavioral Deltas** — full sortable table for agent-invocation + tool-usage deltas:
   baseline/candidate rate, delta, p-value, significance marker, verdict chip. Stopped
   sub-agent lit ember.
3. **Causal Attribution** — per-delta cards: cause file, the unified-diff hunk (JetBrains
   Mono, diff-highlighted), rule + confidence %, the Ollama explanation, alternatives.
4. **Trajectory Timeline** — choose test case + side (baseline/candidate). Renders the
   captured LLM/tool-call timeline: sequence, agent, provider/model, latency, tokens,
   expandable request/response preview. The missing `fact_checker` calls in candidate are
   visually obvious next to baseline.
5. **Run Summary** — run-quality table (trajectories / failed / budget), thresholds,
   output-eval details, and the reproduction command.

**Backward compatibility:** a payload with only `{graph, meta}` (older runs) still renders
the Overview graph; data-dependent sections show an empty/"not available for this run" state.

### 5.1 Data contract & dev fallback
- Extend `frontend/src/types.ts` to mirror the §4.1 payload (single source of truth for the UI).
- Rebuild `frontend/src/sample.ts` (the `npm run dev` fallback) by **exporting the real demo
  run's payload** from the actual sqlite — dev mode shows real data, not fabricated data.
- Re-vendor the built `frontend/dist/index.html` to `src/agentdiff/dashboard_assets/index.html`
  so the CLI serves the new UI.

## 6. Testing & CI
- Keep the 189 green; add §4.4 tests (pristine output, externals mocked).
- Keep the `tsc --noEmit && vite build` gate. Add a light vitest render-smoke test for the
  payload→sections mapping if cheap; otherwise rely on typecheck + Python parity test.
- Extend CI (`.github/workflows`) to build the frontend so the vendored bundle can't drift.

## 7. Demo capture → README → profile (after the UI renders real data)
- Serve the UI on the real `docs/demo/sample-report/` run; screen-record interactions;
  convert to optimized GIFs (<~5 MB, 480–720px) under `docs/demo/`; keep the source mp4.
- README: hero GIF at top; the two differentiators (universal capture, causal attribution);
  **Mermaid architecture diagram** (capture → trajectory store → diff/attribution → report/UI)
  and a **tech-stack diagram**; quickstart, usage, report/UI walkthrough, testing; real
  GIFs/screenshots throughout.
- GitHub profile (`Svkayy/Svkayy`, create if absent): hero GIF, one-line pitch, AgentDiff
  repo link, "selected projects" (anomalai, moveify, SmartMonitor); ensure AgentDiff is pinned.

## 8. Hygiene

Current `.gitignore` already covers `.env`, `.env.*`, `node_modules/`, `frontend/node_modules/`,
`__pycache__/`, `.venv/`, `dist/`, `frontend/dist/`, `.pytest_cache/`, `.mypy_cache/`,
`.ruff_cache/`, `*.log`, `*.jsonl`, `.agentdiff/reports/`, `.DS_Store`. Two consequences to
handle deliberately:
- **`.env.example` is currently ignored** by `.env.*`. If the demo ships one, add
  `!.env.example` so it can be committed. The demo's only env is non-secret
  (`OPENAI_BASE_URL=http://localhost:11434/v1`, `OPENAI_API_KEY=ollama`,
  `AGENTDIFF_LLM_MODEL=llama3.1:8b`).
- **`*.jsonl` is ignored**, so the committed `docs/demo/sample-report/` relies on
  `agentdiff.sqlite` (+ `report.md`, `metadata.json`, and the exported payload JSON) — the
  raw trajectory jsonl is intentionally not committed; the sqlite already contains the
  trajectories. `docs/demo/` is outside `.agentdiff/reports/`, so it is tracked.

The vendored `src/agentdiff/dashboard_assets/index.html` is **not** under any ignored
`dist/`, so it stays tracked (that's the bundle the CLI serves).

Small reviewed commits. `.env.example` only (no real `.env`). **Secret-scan working tree
AND git history before any push** (`.env`, `sk-…`, `AIza…`, JWT `eyJ…`, Supabase
service-role). Do not commit `node_modules`, model weights, or large dumps. Open a PR at the
end; do not push to main.

## 9. Build order (phases)
1. Backend glue + tests (`report_payload.py`, dashboard injection, Ollama client path).
2. Demo sample app + `run_demo.sh`; produce the first real report → `docs/demo/sample-report/`.
3. UI build (shadcn install, types, 5 sections, fonts/theme) wired to the real payload;
   re-vendor bundle.
4. Capture GIFs on the real run.
5. README + Mermaid diagrams + embedded GIFs.
6. GitHub profile page + pin.
7. Hygiene pass + secret scan + PR.

## 10. Open risks / tuning during build
- **Delta significance vs sample count / Ollama speed.** Deterministic routing makes the
  primary delta certain; tune samples so p-values land significant without slow runs.
- **`inferred_agent` resolution.** `structure.yaml` must map each agent function so capture
  tags events correctly; verify the call-stack walker picks up the framework's functions.
- **Attribution requires a non-smoke git baseline.** `run_demo.sh` supplies a real baseline
  commit so attribution (differentiator #2) actually runs.

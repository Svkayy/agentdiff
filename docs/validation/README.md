# Validation Deployments

v0 ships when AgentDiff has been deployed end-to-end on **at least two
external Python codebases** — one using an SDK with a registered shim
(Anthropic/OpenAI), one going through the HTTP-only capture path — with a
saved report from each here as evidence. At least one deployment should
exercise a non-request-response Runner recipe.

**Honest status: not yet done.** The two external-codebase reports below are
placeholders. This section states that plainly rather than implying
validation is complete — replace both placeholder files with real saved
reports before making an external-validation claim anywhere else (README,
launch post, etc.).

- `codebase_a_report.md` — external deployment #1 (registered SDK shim path).
  **Not yet captured.**
- `codebase_b_report.md` — external deployment #2 (HTTP-only capture path).
  **Not yet captured.**

## Reproducible validation procedure (in-repo, done today)

The one validation artifact that *is* reproducible right now, end to end, in
this repo, is the bundled sample-agent regression in
`examples/research_assistant/`. It doubles as the smoke test for "does
AgentDiff actually catch a behavioral regression" and as the source of the
dashboard screenshots/GIFs in `docs/demo/`.

### Prerequisites

- A local [Ollama](https://ollama.com) with the demo model pulled:
  ```bash
  ollama pull llama3.1:8b
  ```
- The engine installed with the OpenAI-compatible extra (Ollama is driven
  through the OpenAI-compatible API):
  ```bash
  pip install -e ".[openai]"
  ```

### Run it

```bash
bash examples/research_assistant/run_demo.sh
```

What this script does (see the script itself for the exact steps):

1. Copies `examples/research_assistant/` into a throwaway temp directory and
   `git init`s it, so the comparison has a real git history to attribute
   against.
2. Commits the **baseline**: the research-assistant orchestrator with
   `retriever`, `fact_checker`, and `summarizer` all wired up.
3. Applies the **candidate** regression: a one-line change that disables
   `fact_checker` (early return at the `AGENTDIFF_DEMO_MARKER` in
   `agents/fact_checker.py`).
4. Runs `agentdiff compare` against both refs (sample count controlled by
   `SAMPLES`, default 8) using the local Ollama model for generation.
5. Copies the resulting real report into `docs/demo/sample-report/`.

Override the model or sample count via environment variables, e.g.:

```bash
SAMPLES=12 AGENT_MODEL=llama3.1:8b bash examples/research_assistant/run_demo.sh
```

### Inspect the result

```bash
agentdiff dashboard --report-dir docs/demo/sample-report --serve
```

Expected outcome: traditional output-eval **PASS** (the answer still reads
fine without fact-checking), AgentDiff **FAIL** on `fact_checker`'s
invocation-rate delta, with causal attribution pointing at
`agents/fact_checker.py` and the exact diff hunk that disabled it. This is
the same run behind the hero GIF and behavioral-deltas/attribution
screenshots in the top-level README.

### Re-running to refresh the committed demo artifacts

If `examples/research_assistant/` or the comparison engine changes in a way
that should update the committed `docs/demo/sample-report/` and GIFs/screenshots,
re-run `run_demo.sh` and re-capture the dashboard views — there is currently
no automated screenshot pipeline for this, so treat it as a manual refresh
step alongside the change that motivated it.

## Producing an external-codebase report (the two placeholders above)

```bash
cd <external-project>
pip install -e /path/to/agentdiff
agentdiff init
# adapt a recipe from docs/recipes/ into .agentdiff/config.yaml + test_cases.yaml
agentdiff compare --baseline <ref>
cp .agentdiff/reports/<timestamp>/report.md \
   /path/to/agentdiff/docs/validation/codebase_a_report.md
```

Repeat against a second, unrelated codebase that goes through the HTTP-only
capture path (no registered SDK shim) for `codebase_b_report.md`, and ideally
exercise a non-request-response Runner recipe (event-driven, scheduled, or
multi-turn — see `docs/recipes/README.md`) in at least one of the two.

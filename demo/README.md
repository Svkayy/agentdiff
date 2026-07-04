# AgentDiff demo

**The demo** is `run_real_demo.py` — AgentDiff diagnoses everything itself.
Nothing is precomputed: the script builds a real mini agent project in a
throwaway git repo, executes it on two real commits, and the engine does the
capture, comparison, and attribution end-to-end.

## The genuine demo: `run_real_demo.py`

A support-bot pipeline (orchestrator → retriever → fact_checker → summarizer)
lives in `demo/real/`. The fact_checker makes a real HTTP call to a local mock
LLM provider (started by the script), which AgentDiff's capture shims genuinely
intercept. The script:

1. Copies `demo/real/` into a throwaway git repo and commits the **baseline**
   (fact_checker calls the LLM on every request).
2. Commits a **candidate** with a real behavioral regression:
   - `--scenario code` (default): an early return in `agents/fact_checker.py`
     skips the LLM call — a silent "latency fix".
   - `--scenario prompt`: the `[FACT_CHECK_ENABLED]` marker line is removed
     from `prompts/fact_checker.txt`; the code gates the LLM call on that
     marker, so the prompt edit genuinely silences the agent.
3. Starts the mock provider and invokes the real
   `agentdiff ci run --tier live --baseline <sha> --candidate <sha>`:
   capture → compare → attribution from the real git range → upload.
4. Prints the verdict and where to look in the dashboard.

The engine detects the Fact Checker's invocation rate dropping 100% → 0% and
attributes it to the exact file — `agents/fact_checker.py` via `code_change`,
or `prompts/fact_checker.txt` via `direct_prompt_change` — with the real git
hunk attached. No trajectories, attribution, or structure are supplied by the
script; the platform derives everything from execution.

### Run it

The stack must be up (`docker compose up -d` from the repo root) and the venv
active:

```bash
source .venv/bin/activate
```

1. Open the dashboard at http://localhost:5173, sign in, and **create a project**.
2. In the project's **Setup** tab, **mint an API key** and copy it (`adk_...`).
3. Run the demo:

   ```bash
   export AGENTDIFF_API_URL=http://localhost:8000
   export AGENTDIFF_API_KEY=adk_...        # the key you just minted
   python demo/run_real_demo.py                    # code-change scenario
   python demo/run_real_demo.py --scenario prompt  # prompt-change scenario
   ```

4. Back in the dashboard: your project → **Runs** → open the new run. The
   agent graph shows the Fact Checker going silent on the candidate, with the
   cause attributed to the real changed file and the actual git hunk.

If `AGENTDIFF_ANTHROPIC_API_KEY` is configured on the worker (or
`ANTHROPIC_API_KEY` in your CLI environment), the finding's explanation is a
genuine LLM-written narrative; otherwise a deterministic rule-based
explanation is used.

## Synthetic seed (no execution — for UI smoke only)

`seed_run.py` posts precomputed trajectories and attribution directly to
`POST /v1/runs`, skipping capture and the attribution engine entirely. Use it
only to smoke-test the dashboard rendering without running anything:

```bash
export AGENTDIFF_API_URL=http://localhost:8000
export AGENTDIFF_API_KEY=adk_...
python demo/seed_run.py
```

`support_agent.py` is the illustrative story that `seed_run.py` encodes: an
orchestrator fanning out to three sub-agents, with a `FACT_CHECKER_ENABLED`
toggle standing in for the bad commit.

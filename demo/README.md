# AgentDiff demo project

A tiny mock "support bot" to try AgentDiff against, with a built-in regression:
a latency "fix" silently disables the Fact Checker sub-agent. Output-level evals
still pass; AgentDiff catches that the agent stopped fact-checking and names the
commit.

- `support_agent.py` — the story: an orchestrator fanning out to three sub-agents
  (Retriever, Fact Checker, Summarizer), with a `FACT_CHECKER_ENABLED` toggle
  standing in for the bad commit.
- `seed_run.py` — turns that story into a real run on your AgentDiff stack. No
  LLM API keys needed; it builds the baseline vs candidate trajectories directly.

## Run it (30 seconds)

The stack must be up (`docker compose up` from the repo root) and you need the
Python venv active for the engine imports:

```bash
source .venv/bin/activate
```

1. Open the dashboard at http://localhost:5173, sign in, and **create a project**.
2. In the project's **Setup** tab, **mint an API key** and copy it (`adk_...`).
3. Seed the demo run:

   ```bash
   export AGENTDIFF_API_URL=http://localhost:8000
   export AGENTDIFF_API_KEY=adk_...        # the key you just minted
   python demo/seed_run.py
   ```

4. Back in the dashboard: your project → **Runs** → open the new run. The
   before/after agent graph shows all three agents healthy on the baseline and
   the **Fact Checker in ember ("stopped")** on the candidate, with the cause
   attributed to `agents/fact_checker.py`.

Re-run `seed_run.py` any time — each call creates a fresh run (unique
idempotency key).

## What it's exercising

`seed_run.py` posts to `POST /v1/runs` exactly the way the real CI collector
does: baseline trajectories where all three sub-agents fire, candidate
trajectories where the Fact Checker is silent, plus the structure config and a
precomputed attribution. The hosted worker runs the same statistical engine as
CI, writes the finding, and (if you configure Slack on the project) posts the
incident brief.

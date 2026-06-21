# How to Interpret an AgentDiff Report

This guide explains how to read `report.md` and what action to take for each
outcome. It assumes you've already run `agentdiff compare` and have a report in
`.agentdiff/reports/<timestamp>/report.md`.

---

## Prerequisites

- A completed `agentdiff compare` run
- Basic familiarity with what your agent does (which sub-agents fire, what tools they use)

---

## Step 1: Read the header

The header tells you the scope of the comparison:

```
## AgentDiff Report

baseline:  main (abc1234)
candidate: working tree (def5678)
samples:   20 per side per test case
overall:   WARN
```

- **baseline** — the git ref your candidate is being compared against
- **candidate** — usually `working tree` (your uncommitted changes) or another ref
- **samples** — how many Runner invocations per side per test case. Fewer samples
  means wider confidence intervals; WARN more often, even when real.
- **overall** — the worst verdict across all test cases and metrics

---

## Step 2: Check the side-by-side table

```
| test case     | traditional output eval | AgentDiff behavioral |
|---------------|------------------------|---------------------|
| qa_query      | PASS (similarity 0.92) | FAIL (agent delta)  |
| summarize     | PASS (similarity 0.89) | PASS                |
```

The key insight: **traditional output eval can PASS while AgentDiff FAILs.**

If `traditional: PASS, AgentDiff: FAIL`, your agent's output looks similar but
its internal behavior has shifted — a sub-agent stopped firing, a tool is being
called twice as often, a different retriever is being used. This is the class of
regression that output evaluation misses entirely.

If `traditional: FAIL, AgentDiff: PASS`, the output text changed but behavior
was stable (perhaps the model rephrased an answer without routing differently).
This may still be worth investigating if output quality matters.

---

## Step 3: Read the behavioral findings

For each test case with a non-PASS verdict:

```
### qa_query

Agent invocation rates:
  research_agent   baseline: 1.00  candidate: 0.60  Δ=-0.40  WARN*
  summarizer       baseline: 0.85  candidate: 0.85  Δ=0.00   PASS

Tool usage (mean calls per trajectory):
  web_search       baseline: 2.1   candidate: 3.4   Δ=+1.3   FAIL*

Tool set Jaccard overlap: 0.82
```

**Reading agent invocation rates:**
- `baseline: 1.00` means the agent fired in 100% of baseline trajectories
- `candidate: 0.60` means it only fired in 60% of candidate trajectories
- `Δ=-0.40` is the absolute change
- `WARN*` — the `*` means the delta is statistically significant (p < 0.05)
- `WARN` without `*` — the delta is above the warn threshold but not yet statistically certain at this sample size; collect more samples

**Reading tool usage:**
- `Δ=+1.3` means the agent is now calling `web_search` an average of 1.3 more
  times per trajectory in the candidate
- `FAIL*` — large change, statistically significant

**Jaccard overlap:** measures how similar the *set* of tools exercised was on
each side. 0.82 means 82% of the tool-use overlap; a value below 0.7 suggests
the candidate is taking a different tool-use path.

---

## Step 4: Read the causal attribution

```
### Attribution: research_agent — invocation rate WARN

Primary cause:
  File:       prompts/system_prompt.txt
  Rule:       direct_prompt_change (confidence: 0.90)
  Reason:     The system prompt file changed and the research_agent uses it.

  Diff hunk:
  @@ -1,3 +1,3 @@
  -You are a research assistant. Be thorough.
  +You are a concise assistant. Answer briefly.

Alternatives:
  - agent.py (code_change, confidence: 0.80)
```

**Attribution tells you the most likely cause file, not a guarantee.** The
rule engine is deterministic and works from observable evidence (manifest diff +
git diff). Confidence scores:

| Score | Rule | Meaning |
|-------|------|---------|
| 0.90 | direct_prompt_change | A file containing this agent's prompt changed |
| 0.80 | code_change | The agent function's body changed |
| 0.70 | model_config_change | Model or sampling parameters changed |
| 0.60 | tool_schema_change | The agent's tool set changed |
| 0.35 | reachable_change | A changed file is statically reachable from the agent |
| 0.20 | heuristic fallback | Something changed; no direct signal |

A confidence of 0.90 with the diff hunk shown is strong evidence. A
confidence of 0.20 means the engine couldn't trace a direct path — inspect
the git diff manually.

---

## Step 5: Decide what to do

| Verdict | With `*` (significant) | Without `*` (not significant) |
|---------|------------------------|-------------------------------|
| PASS | Nothing to do | Nothing to do |
| WARN | Investigate the attribution, decide if acceptable | Collect more samples (`--samples 50`) |
| FAIL | Fix or explicitly accept the regression | Collect more samples, may resolve to WARN |

**"Investigate the attribution"** means: open the diff hunk in the report,
understand why the behavioral change followed from that code change, and decide
if it's intentional.

Common outcomes:
- **Intentional:** you changed the prompt to make the agent more concise and it
  now routes differently. That's expected. Document it and move on.
- **Unintentional:** you refactored a utility function and didn't realize it was
  being used by the agent's routing logic. The attribution's diff hunk will show
  you what changed.
- **False positive at low N:** WARN without `*` at 5 samples per side. Run with
  `--samples 20` before investigating.

---

## Step 6: Use the reproduction command

Every report ends with:

```bash
agentdiff compare --baseline abc1234 --candidate def5678 --samples 20 \
  --project /path/to/project
```

Copy this and run it again to confirm the same result, or share it with a
teammate to reproduce your finding.

---

## Troubleshooting

**All verdicts are WARN without `*`:** sample size is too small. Run with
`--samples 20` or more.

**Attribution shows "heuristic fallback (0.20)":** the engine couldn't find a
direct connection between the behavioral change and any changed file. Check
whether the behavioral delta could be due to non-determinism in the model (run
with `--samples 50` on the same refs to see if the delta persists) or an
environment difference (API key, env vars, external service state).

**Traditional eval shows FAIL but AgentDiff shows PASS:** the output text
changed but the agent's routing and tool usage didn't. This usually means the
model rephrased its answer without changing behavior — normal for small prompt
edits. Check the semantic similarity score to see how different the outputs are.

**The report says "judge skipped" or "explanation unavailable":** no API key is
set. Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. Behavioral comparison and
attribution still run; only the output judge and the 1-3 sentence explanation
are missing.

---

## Related

- [Tutorial: Getting Started](tutorial-getting-started.md)
- [Reference: config.yaml](reference-config.md)
- [METHODOLOGY.md](METHODOLOGY.md) — full pipeline explanation

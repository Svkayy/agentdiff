# AgentDiff Report

- **Generated:** 2026-06-24_183422
- **Baseline:** `309b7404fa643f675a908e801ef302e342ea978f`
- **Candidate:** `working`
- **Samples per case:** 8
- **Test cases:** 3
- **Overall verdict:** **FAIL**
- **SQLite store:** `/private/var/folders/1b/0959_c9507j2q7wx5q4w0ycm0000gn/T/tmp.Q5KBZftaqw/.agentdiff/reports/2026-06-24_183422/agentdiff.sqlite`

## Run Quality

| Side | Trajectories | Failed | Failure budget |
|---|---:|---:|---:|
| baseline | 24 | 0 | 20% |
| candidate | 24 | 0 | 20% |

**Behavior thresholds:** agent invocation warn/fail = 0.2/0.5; tool usage warn/fail = 0.5/1.0.

## Summary: Traditional Eval vs AgentDiff

The central claim: traditional output evaluation can report PASS while internal behavior has changed. Compare the two rightmost columns.

| Test case | Traditional output eval | AgentDiff behavioral |
|---|---|---|
| `capital_of_france` | WARN | FAIL |
| `tallest_mountain` | PASS | FAIL |
| `speed_of_light` | WARN | FAIL |

## Output Evaluation Details

| Test case | Kind | Semantic | Structural | Length | Judge | Notes |
|---|---|---:|---:|---:|---:|---|
| `capital_of_france` | text | 0.86 | n/a | 0.61 | 5.00 | length ratio 0.61 below 0.8 |
| `tallest_mountain` | text | 0.97 | n/a | 0.89 | 5.00 |  |
| `speed_of_light` | text | 0.85 | n/a | 0.63 | 5.00 | semantic similarity 0.85 below 0.85; length ratio 0.63 below 0.8 |

## Behavioral Findings

### `capital_of_france` — FAIL

**Agent invocation rates**

| Agent | Baseline | Candidate | Delta | p-value | Verdict |
|---|---|---|---|---|---|
| orchestrator | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |
| retriever | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |
| fact_checker | 100% (8/8) | 0% (0/8) | -100% | <0.001* | FAIL |
| summarizer | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |

**Tool usage (avg per trajectory)**

| Tool | Baseline | Candidate | Delta | p-value | Verdict |
|---|---|---|---|---|---|
| calculator | 1.00 | 0.00 | -1.00 | <0.001* | FAIL |
| web_search | 2.00 | 1.00 | -1.00 | <0.001* | FAIL |

**Tool-set overlap (Jaccard):** 0.50

### `tallest_mountain` — FAIL

**Agent invocation rates**

| Agent | Baseline | Candidate | Delta | p-value | Verdict |
|---|---|---|---|---|---|
| orchestrator | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |
| retriever | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |
| fact_checker | 100% (8/8) | 0% (0/8) | -100% | <0.001* | FAIL |
| summarizer | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |

**Tool usage (avg per trajectory)**

| Tool | Baseline | Candidate | Delta | p-value | Verdict |
|---|---|---|---|---|---|
| calculator | 1.00 | 0.00 | -1.00 | <0.001* | FAIL |
| web_search | 2.00 | 1.00 | -1.00 | <0.001* | FAIL |

**Tool-set overlap (Jaccard):** 0.50

### `speed_of_light` — FAIL

**Agent invocation rates**

| Agent | Baseline | Candidate | Delta | p-value | Verdict |
|---|---|---|---|---|---|
| orchestrator | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |
| retriever | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |
| fact_checker | 100% (8/8) | 0% (0/8) | -100% | <0.001* | FAIL |
| summarizer | 100% (8/8) | 100% (8/8) | +0% | 1.000 | PASS |

**Tool usage (avg per trajectory)**

| Tool | Baseline | Candidate | Delta | p-value | Verdict |
|---|---|---|---|---|---|
| calculator | 1.00 | 0.00 | -1.00 | <0.001* | FAIL |
| web_search | 2.00 | 1.00 | -1.00 | <0.001* | FAIL |

**Tool-set overlap (Jaccard):** 0.50

## Causal Attribution

Each non-passing behavioral delta is mapped to the specific changed file (and where possible, the diff hunk) that most likely caused it.

### fact_checker — invocation rate 100% → 0% (-100%) (FAIL)

- **Primary cause:** `agents/fact_checker.py` (rule: `code_change`, confidence 80%)
- The body of agent 'fact_checker' (`fact_checker_agent`) changed in `agents/fact_checker.py`.
- _The observed behavioral change from 100% to 0% invocation rate of the `fact_checker` agent is likely due to the removal of the fact-checking code in the `fact_checker_agent` function, specifically the return statement that was executed in 100% of previous invocations. The new code intentionally disabled fact-checking by explicitly returning an empty string. This change in the code's logic resulted in the agent no longer executing the fact-checking step in any invocations._

```diff
diff --git a/agents/fact_checker.py b/agents/fact_checker.py
index 6db1a96..d04382b 100644
--- a/agents/fact_checker.py
+++ b/agents/fact_checker.py
@@ -11,7 +11,7 @@ from tools import calculator, web_search
 
 
 def fact_checker_agent(query: str, findings: str) -> str:
-    # AGENTDIFF_DEMO_MARKER (the candidate replaces this line to disable the step)
+    return ""  # fact-checking disabled pending the latency fix (TODO: re-enable)
     evidence = web_search(f"verify the claims in: {query}")
     confidence = calculator(f"{len(findings)} / 100")
     return chat(
```

Alternatives considered: `agents/fact_checker.py` (model_config_change, 70%)

### fact_checker — invocation rate 100% → 0% (-100%) (FAIL)

- **Primary cause:** `agents/fact_checker.py` (rule: `code_change`, confidence 80%)
- The body of agent 'fact_checker' (`fact_checker_agent`) changed in `agents/fact_checker.py`.
- _The change in the fact_checker_agent's behavior is likely due to the modification of its return statement. Initially, the function returned a verdict based on the evidence gathered and the confidence level. However, after the code change, the function now returns an empty string ("") by default, indicating that fact-checking is disabled pending a latency fix. This alteration in the function's behavior would explain the observed decline in invocation rate, as the agent is no longer producing verdicts._

```diff
diff --git a/agents/fact_checker.py b/agents/fact_checker.py
index 6db1a96..d04382b 100644
--- a/agents/fact_checker.py
+++ b/agents/fact_checker.py
@@ -11,7 +11,7 @@ from tools import calculator, web_search
 
 
 def fact_checker_agent(query: str, findings: str) -> str:
-    # AGENTDIFF_DEMO_MARKER (the candidate replaces this line to disable the step)
+    return ""  # fact-checking disabled pending the latency fix (TODO: re-enable)
     evidence = web_search(f"verify the claims in: {query}")
     confidence = calculator(f"{len(findings)} / 100")
     return chat(
```

Alternatives considered: `agents/fact_checker.py` (model_config_change, 70%)

### fact_checker — invocation rate 100% → 0% (-100%) (FAIL)

- **Primary cause:** `agents/fact_checker.py` (rule: `code_change`, confidence 80%)
- The body of agent 'fact_checker' (`fact_checker_agent`) changed in `agents/fact_checker.py`.
- _The change in the fact_checker_agent function from returning a verdict to returning an empty string ("") resulted in a 100% decline in the invocation rate. This is because the AI agent was no longer capable of producing a verdict, a critical aspect of its fact-checking function. The empty string return value likely caused the agent to be skipped or ignored by other components in the system._

```diff
diff --git a/agents/fact_checker.py b/agents/fact_checker.py
index 6db1a96..d04382b 100644
--- a/agents/fact_checker.py
+++ b/agents/fact_checker.py
@@ -11,7 +11,7 @@ from tools import calculator, web_search
 
 
 def fact_checker_agent(query: str, findings: str) -> str:
-    # AGENTDIFF_DEMO_MARKER (the candidate replaces this line to disable the step)
+    return ""  # fact-checking disabled pending the latency fix (TODO: re-enable)
     evidence = web_search(f"verify the claims in: {query}")
     confidence = calculator(f"{len(findings)} / 100")
     return chat(
```

Alternatives considered: `agents/fact_checker.py` (model_config_change, 70%)

## Reproduction

```bash
agentdiff compare --baseline 309b7404fa643f675a908e801ef302e342ea978f --samples 8
```

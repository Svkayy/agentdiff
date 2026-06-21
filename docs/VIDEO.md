# Walkthrough Video

_Placeholder — record a 5-minute walkthrough and link it here._

Suggested outline (use one of the validation deployments as the example):

1. The problem: an output that still "looks fine" after a prompt change while a
   sub-agent silently stopped firing.
2. `agentdiff init` on a real project — structure inference + scaffolding.
3. Write a Runner from the matching recipe.
4. `agentdiff compare --baseline main` — sampling both sides.
5. Read the report: traditional eval says PASS, AgentDiff says FAIL, and the
   causal attribution points at the exact changed file + diff hunk.

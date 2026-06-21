# Why Behavioral Testing: The Problem Output Evaluation Misses

This document explains the core insight behind AgentDiff and the design decisions
that follow from it. Read this if you want to understand *why* the tool works the
way it does, not just how to use it.

---

## The problem

When you change an AI agent's prompts, model, or routing code, you want to know
if the change broke anything. The natural check is to look at the output: run some
inputs, compare the results. If the outputs look similar, the change is safe.

This check fails for a class of regressions that grows as agents get more complex.

Consider an agent that answers questions by routing them through three sub-agents:
a researcher, a fact-checker, and a summarizer. You edit the system prompt to make
the researcher more concise. The final output looks almost identical — the answer
is still correct and well-phrased. But internally:

- The researcher now calls a different search tool (or calls it fewer times)
- The fact-checker fires in 40% of runs instead of 90% (it's less often triggered
  when the researcher is more confident)
- The summarizer is doing more work to compensate for less context

The output passes semantic similarity at 0.94. The agent's behavior has shifted
significantly. You'll find out in production — not in testing.

This is the class of regression AgentDiff is built to catch: **behavioral drift
that is invisible to output evaluation.**

---

## Why output evaluation misses it

Output evaluation asks: "does the result look similar?"

That's the wrong question for agents with internal structure. The output is a
collapsed view of what happened. It discards:

- Which sub-agents fired and how often
- Which tools were called, in what order, how many times
- What the model received as input (system prompt, messages, tools)
- What model was actually used
- What token counts changed
- What routing decisions were made

Two runs can produce similar text outputs through completely different internal
paths. If the internal path changes, your understanding of what the agent is doing
is wrong — even if the current outputs still look fine.

---

## The AgentDiff approach

AgentDiff captures what happens internally on each run, compares it statistically
across many runs, and when it finds a regression, traces it back to the specific
change that caused it.

### Capture: HTTP-first

The core design decision is to capture at the HTTP layer rather than requiring
SDK instrumentation. Every LLM call — regardless of provider, framework, or
whether the user uses an SDK at all — is an HTTP request. By monkey-patching
`httpx` and `requests` at the transport layer, AgentDiff captures every call
without requiring any changes to agent code.

This is why AgentDiff works out of the box on any provider: Anthropic, OpenAI,
Gemini, Bedrock, Mistral, Cohere, Azure OpenAI, or a raw `requests.post` to a
private endpoint. It does not matter how the user calls the provider — the HTTP
layer is common ground.

SDK shims (optional, for Anthropic and OpenAI) add richer typed metadata:
structured system prompts, tool schemas, token counts by type. When an SDK shim
is present, it sets a context variable so the HTTP layer's would-be duplicate
event is suppressed — exactly one event pair per logical call, with the richest
available metadata.

### Comparison: statistical not threshold

A single run of a non-deterministic agent tells you almost nothing. You need to
run it many times per side and ask: "did the distribution of behavior change?"

AgentDiff runs your Runner N times against the baseline (a git-archive checkout
of a past ref) and N times against the candidate (your working tree), then
compares per-agent invocation rates and per-tool call counts.

The comparison is gated by statistics rather than raw thresholds:
- Agent invocation rates use a two-proportion z-test
- Tool usage counts use a Mann-Whitney U test (no scipy dependency)

A large-looking delta that is not statistically significant at p < 0.05 is
downgraded one level (FAIL → WARN, WARN → PASS). This matters at small N: with
5 samples per side, a 40% change in invocation rate might be noise. With 20
samples it almost certainly isn't. The report shows p-values and marks
significant results with `*` so you can make that judgment.

### Attribution: deterministic rules, not LLM

When a regression is found, AgentDiff maps it back to the specific file (and
diff hunk) most likely responsible. The attribution engine:

1. Builds a "manifest" for each agent on each side — the observed system prompts
   (and the files they live in), the agent function's source hash, and the
   observed model and sampling parameters
2. Diffs the manifests to detect: prompt changed? code changed? model config
   changed? tools changed?
3. Runs the git diff to find which files actually changed
4. Applies a rule pipeline, ranked by confidence:
   - Direct prompt change (0.90): a changed file contains this agent's prompt
   - Code change (0.80): the agent function's body changed
   - Model config change (0.70): model or sampling params changed
   - Tool schema change (0.60): the agent's tool set changed
   - Reachable change (0.35): a static import-graph BFS finds the changed file
     is reachable from the agent's code
   - Heuristic fallback (0.20): something changed but nothing direct matched

The LLM is only used at the end — to write a 1-3 sentence plain-English
explanation of the highest-confidence attribution. It is never asked to choose
the attribution. The rule pipeline is deterministic and auditable.

This design choice matters: an LLM picking the attribution could hallucinate a
plausible-sounding cause. The rule engine can only report what is structurally
true — the diff hunk is real, the file hash changed, the manifest shows a prompt
difference.

---

## Trade-offs

**Running N times per side is expensive.** Twenty samples per side at 20 test
cases is 400 LLM calls for the baseline alone. This is a deliberate trade-off:
behavioral comparison is only meaningful at meaningful N. Start at 5 samples for
fast iteration; use 20+ for CI gates.

**Capture by monkey-patching is a double-edged sword.** It's invisible to agent
code (no instrumentation required) but it means capture is installed for the
entire Python process. In tests, this is usually what you want. In production,
`agentdiff.install()` and `agentdiff.uninstall()` are explicit. The autoload hook
(`agentdiff hook install`) installs capture at interpreter startup via a `.pth`
file — convenient but less explicit.

**Attribution is confident, not certain.** A confidence of 0.90 means the
evidence strongly points at this file. It does not mean the file is the only cause
or that the attribution algorithm found the root cause at the symbolic level. For
the hard cases (0.20 fallback), inspect the git diff manually.

**JSONL is v0 streaming format.** Each trajectory is one JSON line written
incrementally during the run. SQLite is a post-run artifact for querying. The
JSONL format is durable and grep-able; it's also the format the comparison engine
reads. A live-capture SQLite backend is planned for a future version.

---

## Related

- [METHODOLOGY.md](METHODOLOGY.md) — the full pipeline, step by step
- [Tutorial: Getting Started](tutorial-getting-started.md)
- [CODEBASE.md](CODEBASE.md) — module-by-module implementation reference

# Walkthrough Video

**Status: script only.** Recording, editing, and publishing the video is a
human task — not automatable from this repo. This document is the
shot-by-shot script to record against; once recorded, link the final video
at the top of this file and in the README.

Target runtime: **5 minutes**. Record at 1280x800 minimum, terminal font size
large enough to read on a phone screen. Use the bundled sample agent
(`examples/research_assistant/`) so the recording is reproducible by anyone
following along — see `docs/validation/README.md` for the exact commands.

## Pre-recording checklist

- [ ] `ollama pull llama3.1:8b` completed, Ollama running locally.
- [ ] Clean checkout, `pip install -e ".[openai]"` already run (don't record
      the install — cut to a warm shell).
- [ ] Terminal theme with high contrast; font size ~18pt.
- [ ] Browser window pre-sized for the dashboard (1280x800), zoom reset to 100%.
- [ ] Close notifications / do-not-disturb on.
- [ ] `docs/demo/hero.gif` and screenshots already exist as a fallback if a
      live take needs a cutaway.

## Shot list

### 0:00–0:40 — The problem (talking head or slides over terminal)

- Open on the hook: "You change a prompt, the output still looks fine — but
  an agent inside your pipeline silently stopped firing. Traditional output
  eval can't see that."
- Show a split-screen or slide of the thesis: **output eval PASS, but the
  internal behavior changed.**
- State the one-line pitch: "AgentDiff catches these behavioral regressions
  and tells you exactly which code or prompt change caused each one."

### 0:40–1:10 — Zero-setup capture (no Runner, no config)

- Terminal: open the `agentdiff.record` example inline (or a short
  `python -c` snippet) showing:
  ```python
  import agentdiff
  with agentdiff.record("before"):
      run_my_agent("some input")
  ```
- Voiceover: "The fastest path is two `record()` blocks around code you
  already run — no Runner, no YAML, no git baseline required."
- Cut to `agentdiff diff before after --serve` opening the dashboard.

### 1:10–1:40 — The sample agent + the regression

- `cat examples/research_assistant/agents/fact_checker.py` — show the
  orchestrator routes to `retriever`, `fact_checker`, `summarizer`.
- Show the one-line diff that disables `fact_checker` (an early `return`).
- Voiceover: "The answer still reads fine. Traditional output-eval passes.
  Let's see what AgentDiff says."

### 1:40–2:20 — Running the comparison

- Terminal: `bash examples/research_assistant/run_demo.sh` running live
  (speed up in post if it's slow; keep at least the tail of the output
  visible — verdict line, report path).
- Voiceover: "This samples both the baseline and candidate refs, captures
  every LLM and tool call via the HTTP layer, and computes behavioral deltas
  with proper significance testing."

### 2:20–2:45 — Opening the dashboard, Overview tab

- `agentdiff dashboard --report-dir docs/demo/sample-report --serve`
- Dashboard opens on **Overview**: point at the before/after agent graph,
  `fact_checker` lit ember (stopped firing), and the verdict banner.
- Callout: "Output eval: PASS. AgentDiff: FAIL." — zoom on that contrast box.

### 2:45–3:15 — Behavioral Deltas tab

- Click into **Behavioral Deltas**. Point at the table: `fact_checker`
  100%→0% invocation rate, FAIL; `web_search`/`calculator` tool usage down;
  p-values shown per row.
- Voiceover: "Every delta is a real statistical test — two-proportion or
  Mann-Whitney — not a heuristic guess."

### 3:15–3:45 — Causal Attribution tab

- Click into **Causal Attribution**. Point at the finding: cause file
  `agents/fact_checker.py`, the exact diff hunk, the rule that fired, and the
  short LLM-written explanation.
- Voiceover: "Attribution is deterministic — a rule engine over the agent
  manifest and the git diff. The LLM only writes the sentence explaining it,
  it never decides the cause."

### 3:45–4:10 — Trajectory Timeline tab

- Click into **Trajectory Timeline**. Toggle baseline → candidate live and
  let the viewer watch `fact_checker`'s calls disappear from the sequence.

### 4:10–4:30 — Run Summary tab + CI gate mention

- Click into **Run Summary**: run quality, thresholds, output-eval details,
  copy-paste reproduction command.
- Quick cut to `agentdiff ci run --tier hermetic` in a terminal (or a
  screenshot of a GitHub PR check + Slack brief) — one sentence: "The same
  engine gates every PR for free, no API keys required, using a recorded
  cassette."

### 4:30–5:00 — Close

- Recap: "Universal capture, deterministic attribution, five-view dashboard,
  runs locally or as a CI gate."
- CTA: `pip install agentdiff`, link to the GitHub repo and docs.
- End card: repo URL + docs link.

## Post-production notes

- Caption the verdict banner and the PASS/FAIL contrast box — it's the whole
  thesis and needs to land even muted.
- Keep cuts tight in the 1:40–2:20 sampling section; nobody needs to watch a
  progress bar in real time.
- Export at 1080p, add to `docs/demo/` alongside the existing GIFs/screenshots,
  and link the final URL at the top of this file once published.

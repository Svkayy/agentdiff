# Demo assets

Real GIFs and a real report from AgentDiff's dashboard — **not** mockups. Every
frame renders data from an actual `agentdiff compare` run.

| Asset | Window | What it shows |
|---|---|---|
| [`hero.gif`](hero.gif) | Overview | Verdict banner, before/after agent graph (`fact_checker` + `calculator` lit ember as *stopped*), and the "output eval PASS / AgentDiff FAIL" thesis card. |
| [`behavioral-deltas.png`](behavioral-deltas.png) | Behavioral Deltas | Per-test-case table of agent-invocation + tool-usage deltas with p-values, significance, and verdicts. |
| [`attribution.gif`](attribution.gif) | Causal Attribution | `fact_checker`'s drop mapped to `agents/fact_checker.py` (`code_change`, 80%) with the exact diff hunk and an Ollama-written explanation. |
| [`timeline.gif`](timeline.gif) | Trajectory Timeline | Toggling baseline → candidate — the `fact_checker` LLM/tool calls visibly disappear. |
| [`run-summary.png`](run-summary.png) | Run Summary | Run quality, thresholds, output-evaluation details, and the reproduction command. |

`*.mp4` are the source recordings. `sample-report/` is the real run the dashboard
renders (`agentdiff.sqlite` + `report.md` + `metadata.json`).

## Regenerate

```bash
# 1. Produce the real report (needs a local Ollama with llama3.1:8b):
bash examples/research_assistant/run_demo.sh

# 2. Serve the dashboard on it:
agentdiff dashboard --report-dir docs/demo/sample-report --serve   # → http://127.0.0.1:8765/dashboard.html
#    …or run the dev app: npm --prefix frontend run dev

# 3. Record + encode (capture.mjs drives the live UI with Playwright):
node docs/demo/capture.mjs hero        # also: attribution, timeline, tour
ffmpeg -i docs/demo/video/hero/*.webm -vf "fps=12,scale=680:-1:flags=lanczos,palettegen" /tmp/p.png
ffmpeg -i docs/demo/video/hero/*.webm -i /tmp/p.png -lavfi "fps=12,scale=680:-1,paletteuse" docs/demo/hero.gif
```

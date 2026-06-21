# Benchmarks

Reproducible, measured numbers for AgentDiff. All are **controlled/synthetic**
benchmarks of the system's own behavior (not real-world deployment impact).

Environment for the recorded results: Apple M3 Max, Python 3.13, single core,
in-process.

```bash
python benchmarks/bench_detector.py      # detector calibration (FPR + power)
python benchmarks/bench_attribution.py   # attribution accuracy on known scenarios
python benchmarks/bench_throughput.py    # capture / load / compare throughput
```

## 1. Detector calibration (`bench_detector.py`)

Monte-Carlo over 2,000 trials per condition, N=20 samples/side (the default), with
ground-truth-known synthetic invocation processes.

| Condition | Result |
|---|---|
| False-positive rate, true rate 0.50→0.50 | **4.7%** |
| False-positive rate, true rate 0.80→0.80 | **4.5%** |
| Detection power, 0.90→0.50 (−40 pts) | **84.7%** |
| Detection power, 1.00→0.70 (−30 pts) | **76.3%** |
| Detection power, 0.80→0.40 (−40 pts) | **75.5%** |
| Detection power, 0.90→0.60 (−30 pts) | **61.2%** |

The false-positive rate sits just under the α=0.05 target — the significance gate is
correctly calibrated.

## 2. Attribution accuracy (`bench_attribution.py`)

50 controlled scenarios (10 per change type). Each builds a real git repo, injects
one known change, and checks the engine's **primary** attribution (rule + file)
against ground truth.

| Change type | Correct |
|---|---|
| Prompt change → `direct_prompt_change` | 10/10 |
| Code change → `code_change` | 10/10 |
| Model config change → `model_config_change` | 10/10 |
| Tool schema change → `tool_schema_change` | 10/10 |
| Indirect (reachable) change → `reachable_change` | 10/10 |
| **Overall** | **50/50 = 100%** |

## 3. Throughput (`bench_throughput.py`)

Single core, in-process.

| Stage | Result |
|---|---|
| Capture (open Tracer → 4 events → serialize + write JSONL) | **6,754 trajectories/s** (~37 µs/event) |
| Storage load (parse trajectories from JSONL) | **98,029 trajectories/s** |
| Comparison engine (incl. z-test + Mann-Whitney) | **1.4M trajectories/s** |

## Test suite & coverage

```bash
python -m pytest --cov=agentdiff --cov-report=term -q
```

- **143 tests passing, 2 skipped** (skips require optional anthropic/mcp SDKs).
- **75% line coverage overall**; core analysis modules higher: `stats.py` 98%,
  `compare.py` 97%, `tracer.py` 97%, `manifest_diff.py` 93%, `reachability.py` 89%,
  `cli/compare.py` 88%, `rules.py` 85%, `output_eval.py` 84%.

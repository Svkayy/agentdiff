# Tutorial: Your First AgentDiff Comparison

By the end of this tutorial you will have:
- Installed AgentDiff into a Python project with an AI agent
- Run your first behavioral comparison between two versions of your code
- Read the report and understood what each section means

This takes about 20 minutes. You need Python 3.10+, a git repository, and an
Anthropic or OpenAI API key.

---

## What you'll need

- Python 3.10 or later
- A git repository containing your agent code (or the sample project below)
- An API key: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

No particular agent framework is required. AgentDiff captures LLM calls at the
HTTP layer, so it works with any provider or wrapper.

---

## Step 1: Install AgentDiff

```bash
pip install -e /path/to/agentdiff
```

If you're using the Anthropic SDK (most common), add the optional shim:

```bash
pip install -e "/path/to/agentdiff[anthropic]"
```

Verify the install:

```bash
agentdiff --help
```

You should see the list of commands. If not, check that your venv is active.

---

## Step 2: Point AgentDiff at your project

Navigate to your agent project root (the directory that contains your agent
source files), then run:

```bash
agentdiff quickstart
```

This does three things:
1. AST-walks your project to find agent functions, tool functions, and entry points
2. Writes `.agentdiff/structure.yaml` (the agent map)
3. Writes `.agentdiff/config.yaml` and a starter `.agentdiff/test_cases.yaml`

You should see a table like:

```
Function            Role          File
──────────────────────────────────────────
research_agent      agent         agent.py
search_tool         tool          tools.py
main                entry_point   main.py
```

If the classification looks wrong, edit `.agentdiff/structure.yaml` directly —
it's plain YAML.

---

## Step 3: Write your Runner

Open `.agentdiff/config.yaml`. It contains a `runner:` section pointing at a
module. The Runner is the only code you write — a small function that fires one
invocation of your agent and returns its output.

Create the file it points to. The simplest case (a function that calls your
agent directly):

```python
# .agentdiff/runner.py
from my_app.agent import research_agent   # replace with your import

def run(input: dict) -> str:
    return research_agent(input["query"])
```

Point `config.yaml` at it:

```yaml
runner:
  module: .agentdiff.runner
  callable: run
```

The `input` dict comes from test cases (next step). Return whatever your agent
produces: a string, a dict, or `None` for side-effecting agents.

**If your agent is not a simple function call,** see
[`docs/recipes/`](recipes/README.md) for event-driven, scheduled, and
multi-turn patterns.

---

## Step 4: Add a test case

Open `.agentdiff/test_cases.yaml` and add at least one real input your agent
can handle:

```yaml
- id: basic_query
  input:
    query: "What is the capital of France?"
```

Add 2-3 cases for better statistical confidence. The more varied the inputs,
the more representative your comparison will be.

---

## Step 5: Validate your setup

```bash
agentdiff doctor --project .
```

This checks: config validity, runner importability, git baseline, API key,
optional dependencies. Fix any `ERROR` lines before continuing. `WARNING` lines
are advisory.

---

## Step 6: Commit your current code

AgentDiff compares two git refs. The baseline is a past commit; the candidate
is your working tree (or another ref). You need at least one commit:

```bash
git add .
git commit -m "baseline: initial agent setup"
```

---

## Step 7: Make a change

Now make a meaningful change to your agent — a prompt edit, a model swap, or a
routing change. Something you'd want to know the behavioral impact of.

For example, if your agent has a system prompt, change it slightly:

```python
# Before
messages=[{"role": "user", "content": query}]

# After — add a system prompt
messages=[
    {"role": "user", "content": query},
]
# ... plus system="You are a concise assistant."
```

Do **not** commit this change yet. Your working tree is the candidate.

---

## Step 8: Run the comparison

```bash
agentdiff compare --baseline HEAD --samples 5
```

`--baseline HEAD` compares your current working tree against the last commit.
`--samples 5` runs each test case 5 times per side (10 total per case).

You'll see a progress indicator. The baseline runs in a subprocess using a
git-archive checkout so your working-tree change doesn't leak in.

The report is written to `.agentdiff/reports/<timestamp>/report.md`.

---

## Step 9: Read the report

Open `report.md`. Here's what each section means:

**Header** — refs compared, sample math, overall verdict (PASS / WARN / FAIL).

**Traditional eval vs AgentDiff** — the key insight table:

```
| test case    | traditional output eval | AgentDiff behavioral |
|--------------|------------------------|---------------------|
| basic_query  | PASS (similarity 0.94) | WARN (agent delta)  |
```

Output can look similar while behavior has shifted. This contrast is the point.

**Behavioral findings** — per test case: which agents fired, how often, which
tools were called. A WARN means the delta is meaningful but not statistically
certain at this sample size. A FAIL means it's both large and statistically
significant.

**Causal attribution** — for each WARN/FAIL: the file most likely responsible,
the rule that fired (prompt change / code change / model config change), the
confidence score, and the diff hunk. Optionally, a 1-3 sentence explanation.

**Reproduction command** — copy-paste this to re-run the exact comparison later.

---

## What's next

- **More samples for confidence:** `agentdiff compare --baseline HEAD --samples 20`
- **Compare two commits:** `agentdiff compare --baseline main --candidate feature-branch`
- **CI integration:** add `agentdiff compare` to your test suite; it exits non-zero on FAIL
- **Custom thresholds:** adjust `thresholds:` in `config.yaml` (see [`docs/reference-config.md`](reference-config.md))
- **Dashboard:** `agentdiff dashboard --serve` opens a local HTML view of the latest run

For a complete explanation of why behavioral testing catches what output evaluation
misses, see [`docs/explanation-why-behavioral.md`](explanation-why-behavioral.md).

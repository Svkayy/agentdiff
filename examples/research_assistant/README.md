# Research-assistant demo (the agent-under-test)

A tiny multi-agent system AgentDiff is run *against* — it is **not** part of the
AgentDiff engine. It exists so the dashboard has a real `compare` run to render.

## The agents

```
run_research (orchestrator)
├─ retriever_agent      → web_search → LLM
├─ fact_checker_agent   → web_search + calculator → LLM   ← the demo disables this
└─ summarizer_agent     → LLM
```

Every LLM call goes to a local **Ollama** model (`llama3.1:8b` by default) through
the OpenAI-compatible API, captured by AgentDiff's OpenAI-SDK shim. Routing is
deterministic, so the behavioral diff is reproducible.

## The regression

The candidate inserts a one-line early `return ""` into `fact_checker_agent`,
silently skipping its evidence lookup and verification call. The final answer
still reads fine — so traditional output-eval **passes** while AgentDiff **fails**
and attributes the drop to `agents/fact_checker.py` (the `code_change` rule).

Result: `fact_checker` stops firing (100% → 0%), and `web_search` / `calculator`
usage falls because the disabled agent no longer calls them.

## Run it

```bash
# 1. Have Ollama running with the model pulled:
ollama pull llama3.1:8b

# 2. From the AgentDiff repo root, with the venv active:
bash examples/research_assistant/run_demo.sh
```

This produces a real report under `docs/demo/sample-report/` (sqlite + report.md
+ metadata.json). Open it in the dashboard:

```bash
agentdiff dashboard --report-dir docs/demo/sample-report --serve
```

Copy `.env.example` to `.env` to customize the model or endpoint. No real secrets
are involved — `OPENAI_API_KEY=ollama` is a placeholder the local server ignores.

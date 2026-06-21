# Runner Recipes

AgentDiff drives your agent through a **Runner** — a small callable you provide
that fires one observable invocation of your agent and returns its observable
outcome. It's the only code you write; capture, comparison, and attribution are
automatic.

```python
def run(input: dict) -> dict | str | None: ...
```

`input` is the opaque dict from a `test_cases.yaml` entry. The return value is
stored as the trajectory's `final_output` (a string is stored as-is; a dict is
serialized to JSON; `None` means a purely side-effecting agent).

## Which recipe matches your system?

| Your agent is triggered by…                | Recipe | File |
|--------------------------------------------|--------|------|
| A direct function call / HTTP request      | A — Request-response | [`request_response.py`](request_response.py) |
| An event on a bus or queue                 | B — Event-driven | [`event_driven.py`](event_driven.py) |
| A timer / cron schedule                    | C — Scheduled | [`scheduled.py`](scheduled.py) |
| A multi-turn conversation                  | D — Multi-turn | [`multi_turn.py`](multi_turn.py) |

Copy the closest recipe, adapt the imports to your code, and point
`.agentdiff/config.yaml` at it:

```yaml
runner:
  module: my_app.testing.runner   # where you put your adapted recipe
  callable: run
samples_per_case: 20
llm_provider: anthropic
```

## The two things only you can decide

1. **Settling** — when is one invocation "done"? A synchronous return is the
   easy case. Event-driven and async agents need an explicit signal: an
   `asyncio.Event`, `queue.join()`, a condition variable, an idle window, or a
   hard timeout. The Runner owns this.
2. **Outcome collection** — for side-effecting agents (sends an email, schedules
   a task), the Runner snapshots those effects from your existing test surface
   (mock SMTP, in-memory bus, transactional rollback).

If your agent has neither a meaningful return nor collectable side effects,
AgentDiff still produces behavioral findings from the capture layer — the report
just leans entirely on structural analysis instead of the output side-by-side.

See [`limitations.md`](limitations.md) for what v0 deliberately does **not**
support, and the workarounds.

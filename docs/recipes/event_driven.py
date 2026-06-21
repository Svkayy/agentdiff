"""Recipe B — Event-driven.

For agents triggered by an event on a bus/queue rather than a direct call. The
Runner establishes preconditions, emits the trigger, waits for the system to
settle, and snapshots the side effects it produced.

You own two system-specific decisions AgentDiff cannot infer:
  - settling: when is one invocation "done"? (idle window + hard timeout below)
  - outcome collection: what counts as the observable result? (the collector dict)

Point .agentdiff/config.yaml at this module:

    runner:
      module: docs.recipes.event_driven
      callable: run
"""
from my_app.event_bus import bus
from my_app.handlers import register_handlers


def run(input: dict) -> dict:
    # 1. Establish preconditions.
    bus.reset()
    for evt in input.get("preconditions", {}).get("seed_events", []):
        bus.replay(evt)

    # 2. Collect side effects fired during this invocation window.
    collected = {
        "emails_drafted": [],
        "events_modified": [],
        "notifications_scheduled": [],
    }
    bus.set_side_effect_collector(collected)
    register_handlers()

    # 3. Dispatch the trigger.
    trigger = input["trigger"]
    bus.emit(trigger["event_type"], trigger["payload"])

    # 4. Settle: queue idle for 500ms, or 5s hard timeout.
    bus.wait_idle(idle_window_ms=500, timeout_s=5)

    # 5. Snapshot.
    return collected

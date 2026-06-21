"""Recipe C — Scheduled / cron-triggered.

For agents that run on a timer (a morning briefing, a nightly digest). The Runner
freezes the world to a deterministic snapshot + a frozen clock, runs the scheduled
entry point, and returns its outcome.

External requirement: your code must read time from an injectable clock that
freezegun can patch (or accept `now` as a parameter).

Point .agentdiff/config.yaml at this module:

    runner:
      module: docs.recipes.scheduled
      callable: run
"""
from freezegun import freeze_time

from my_app.scheduled import morning_briefing
from my_app.world import restore_world, snapshot_world


def run(input: dict) -> dict:
    saved = snapshot_world()
    try:
        restore_world(input["world_snapshot"])
        with freeze_time(input["frozen_now"]):
            outcome = morning_briefing()
        return {
            "briefing_text": outcome.text,
            "actions_taken": outcome.actions,
        }
    finally:
        restore_world(saved)

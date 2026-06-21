"""Runner for the event-driven calendar fixture (Recipe B)."""
from handlers import register_handlers, seed_existing

from bus import bus


def run(input: dict) -> dict:
    bus.reset()
    seed_existing(input.get("preconditions", {}).get("existing_events", []))

    collected: dict = {"events_modified": [], "notifications_scheduled": []}
    bus.set_side_effect_collector(collected)
    register_handlers()

    trigger = input["trigger"]
    bus.emit(trigger["event_type"], trigger["payload"])
    bus.wait_idle(idle_window_ms=500, timeout_s=5)

    return collected

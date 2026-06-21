"""Register the bus handlers that dispatch calendar events to the agent."""
from agent import notify_user, schedule_agent

from bus import bus

_EXISTING: list[dict] = []


def seed_existing(events: list[dict]) -> None:
    _EXISTING.clear()
    _EXISTING.extend(events)


def _on_event_created(payload: dict) -> None:
    decision = schedule_agent(payload, _EXISTING)
    bus.record("events_modified", decision)
    if decision["decision"] == "reschedule":
        notify_user(f"Conflict on '{payload['title']}' — proposing a reschedule.")


def register_handlers() -> None:
    bus.on("calendar.event.created", _on_event_created)

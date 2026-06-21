"""Calendar conflict-resolution agent (offline stub for the event-driven fixture).

In a real project `schedule_agent` would call an LLM to decide how to resolve a
conflict. Here it is a deterministic stub so the fixture runs without API keys,
while still being a valid structure-inference target (it is the agent that the
handler dispatches to).
"""
import agentdiff

from bus import bus


def schedule_agent(new_event: dict, existing: list[dict]) -> dict:
    """Decide whether a newly-created event conflicts with existing ones."""
    conflicts = [e for e in existing if e["start"] == new_event["start"]]
    if conflicts:
        return {"decision": "reschedule", "conflicts_with": [c["title"] for c in conflicts]}
    return {"decision": "accept", "conflicts_with": []}


@agentdiff.tool
def notify_user(message: str) -> str:
    """Notify the user of a scheduling decision."""
    bus.record("notifications_scheduled", message)
    return "ok"

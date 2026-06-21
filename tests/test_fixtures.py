"""Day 8: the recipe fixture projects run offline and are structure-inferable."""
import sys
from pathlib import Path

import pytest

from agentdiff.structure.ast_walker import walk_project
from agentdiff.structure.heuristic_classifier import classify

EVENT_DRIVEN = Path(__file__).parent / "fixtures" / "sample_projects" / "event_driven_calendar"


@pytest.fixture
def _import_event_driven(monkeypatch):
    """Make the fixture importable by bare module name, then clean up sys.modules."""
    monkeypatch.syspath_prepend(str(EVENT_DRIVEN))
    yield
    for name in ("runner", "handlers", "agent", "bus"):
        sys.modules.pop(name, None)


def test_event_driven_runner_detects_conflict(_import_event_driven):
    import runner

    out = runner.run({
        "preconditions": {
            "existing_events": [{"title": "1:1", "start": "09:00", "duration": 60}],
        },
        "trigger": {
            "event_type": "calendar.event.created",
            "payload": {"title": "Standup", "start": "09:00", "duration": 30},
        },
    })
    # The new 09:00 event conflicts with the existing 1:1 → reschedule + notification.
    assert out["events_modified"][0]["decision"] == "reschedule"
    assert out["notifications_scheduled"], "expected a notification side effect"


def test_event_driven_runner_accepts_non_conflict(_import_event_driven):
    import runner

    out = runner.run({
        "preconditions": {"existing_events": [{"title": "1:1", "start": "09:00", "duration": 60}]},
        "trigger": {
            "event_type": "calendar.event.created",
            "payload": {"title": "Lunch", "start": "12:00", "duration": 30},
        },
    })
    assert out["events_modified"][0]["decision"] == "accept"
    assert not out["notifications_scheduled"]


def test_event_driven_structure_inference_finds_tool():
    candidates = walk_project(EVENT_DRIVEN)
    doc = classify(candidates)
    tool_fns = {t.function for t in doc.tools}
    assert "notify_user" in tool_fns

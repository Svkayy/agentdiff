"""Day 5: JSONL storage round-trip."""
from uuid import uuid4

from agentdiff.capture.events import (
    CallSite, CanonicalLLMCall, LLMRequestEvent, LocalToolInvokedEvent,
)
from agentdiff.storage import (
    append_trajectory,
    load_trajectory_set,
    load_trajectory_set_from_sqlite,
    write_run_store,
)
from agentdiff.trajectory import Trajectory, TrajectorySet


def _trajectory(tc_id: str = "tc1") -> Trajectory:
    call_id = uuid4()
    return Trajectory(
        test_case_id=tc_id,
        version_tag="baseline",
        input={"query": "hi"},
        final_output="hello",
        events=[
            LLMRequestEvent(
                call_id=call_id,
                canonical=CanonicalLLMCall(provider="anthropic", model="claude"),
                captured_by="sdk_shim",
                callsite=CallSite(file="a.py", function="agent", line=1),
                inferred_agent="My Agent",
            ),
            LocalToolInvokedEvent(
                call_id=call_id,
                tool_name="web_search",
                callsite=CallSite(file="a.py", function="web_search", line=5),
                inferred_agent="My Agent",
            ),
        ],
    )


def test_round_trip(tmp_path):
    path = tmp_path / "traj.jsonl"
    append_trajectory(path, _trajectory("tc1"))
    append_trajectory(path, _trajectory("tc2"))

    ts = load_trajectory_set(path, "baseline")
    assert len(ts.trajectories) == 2
    t = ts.trajectories[0]
    assert t.final_output == "hello"
    assert t.agents_invoked() == ["My Agent"]
    assert len(t.llm_calls()) == 1
    assert len(t.tool_calls()) == 1


def test_load_missing_file_returns_empty(tmp_path):
    ts = load_trajectory_set(tmp_path / "nope.jsonl", "candidate")
    assert ts.trajectories == []


def test_load_skips_blank_and_corrupt_lines(tmp_path):
    path = tmp_path / "traj.jsonl"
    append_trajectory(path, _trajectory("tc1"))
    with open(path, "a") as f:
        f.write("\n")
        f.write("{not valid json\n")
    ts = load_trajectory_set(path, "baseline")
    assert len(ts.trajectories) == 1


def test_for_test_case_filter(tmp_path):
    path = tmp_path / "traj.jsonl"
    append_trajectory(path, _trajectory("tc1"))
    append_trajectory(path, _trajectory("tc2"))
    ts = load_trajectory_set(path, "baseline")
    assert len(ts.for_test_case("tc1")) == 1
    assert len(ts.for_test_case("tc2")) == 1
    assert len(ts.for_test_case("nope")) == 0


def test_sqlite_run_store_round_trip(tmp_path):
    db = tmp_path / "agentdiff.sqlite"
    baseline = TrajectorySet(version_tag="baseline", trajectories=[_trajectory("tc1")])
    candidate = TrajectorySet(version_tag="candidate", trajectories=[])

    written = write_run_store(
        db,
        metadata={"run_id": "run-1", "timestamp": "t"},
        baseline_set=baseline,
        candidate_set=candidate,
    )

    assert written == db
    loaded = load_trajectory_set_from_sqlite(db, "baseline", run_id="run-1")
    assert len(loaded.trajectories) == 1
    assert loaded.trajectories[0].test_case_id == "tc1"
    assert loaded.trajectories[0].llm_calls()[0].inferred_agent == "My Agent"

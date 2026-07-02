"""Day 5: JSONL storage round-trip."""
from uuid import uuid4

from agentdiff.capture.events import (
    CallSite, CanonicalLLMCall, LLMRequestEvent, LocalToolInvokedEvent,
)
from agentdiff.storage import (
    JsonlTrajectorySink,
    append_trajectory,
    load_trajectory_set,
    load_trajectory_set_from_sqlite,
    read_artifact,
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


def test_jsonl_trajectory_sink_round_trips_by_side(tmp_path):
    sink = JsonlTrajectorySink(tmp_path / "sink")
    baseline = Trajectory(test_case_id="tc1", version_tag="baseline", input={})
    candidate = Trajectory(test_case_id="tc1", version_tag="candidate", input={})

    sink.append(baseline)
    sink.append(candidate)

    assert sink.load("baseline").trajectories == [baseline]
    assert sink.load("candidate").trajectories == [candidate]


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


# ---------------------------------------------------------------------------
# read_artifact (T1)
# ---------------------------------------------------------------------------

def _empty_sets():
    return (
        TrajectorySet(version_tag="baseline", trajectories=[]),
        TrajectorySet(version_tag="candidate", trajectories=[]),
    )


def test_read_artifact_round_trip(tmp_path):
    db = tmp_path / "agentdiff.sqlite"
    baseline, candidate = _empty_sets()
    write_run_store(
        db,
        metadata={"run_id": "run-1", "timestamp": "t"},
        baseline_set=baseline,
        candidate_set=candidate,
        output_evals=[{"test_case_id": "tc1", "verdict": "pass"}],
    )
    assert read_artifact(db, "output_evals", run_id="run-1") == [
        {"test_case_id": "tc1", "verdict": "pass"}
    ]
    # comparison was None → stored as JSON null → reads back as None.
    assert read_artifact(db, "comparison", run_id="run-1") is None


def test_read_artifact_missing_db(tmp_path):
    assert read_artifact(tmp_path / "nope.sqlite", "comparison") is None


def test_read_artifact_missing_name(tmp_path):
    db = tmp_path / "agentdiff.sqlite"
    baseline, candidate = _empty_sets()
    write_run_store(
        db,
        metadata={"run_id": "r", "timestamp": "t"},
        baseline_set=baseline,
        candidate_set=candidate,
    )
    assert read_artifact(db, "does_not_exist") is None


def test_read_artifact_defaults_to_latest_run(tmp_path):
    db = tmp_path / "agentdiff.sqlite"
    for rid, payload in [("r1", [{"v": 1}]), ("r2", [{"v": 2}])]:
        baseline, candidate = _empty_sets()
        write_run_store(
            db,
            metadata={"run_id": rid, "timestamp": "t"},
            baseline_set=baseline,
            candidate_set=candidate,
            output_evals=payload,
        )
    # run_id=None selects the most recently written run (r2).
    assert read_artifact(db, "output_evals") == [{"v": 2}]

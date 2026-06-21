"""Slice 2: ambient capture() + `agentdiff diff` (the no-Runner path)."""
from uuid import uuid4

import pytest
from click.testing import CliRunner

import agentdiff
from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.cli.diff import diff_cmd
from agentdiff.storage import append_trajectory
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc, save
from agentdiff.trajectory import Trajectory


@pytest.fixture(autouse=True)
def _clean_shims():
    yield
    agentdiff.uninstall()


@agentdiff.tool
def sample_tool(x: int) -> int:
    return x


# --- capture() --------------------------------------------------------------

def test_capture_records_one_trajectory(tmp_path):
    with agentdiff.record("before", project_root=tmp_path):
        sample_tool(1)
    cap = tmp_path / ".agentdiff" / "captures" / "before.jsonl"
    assert cap.exists()
    lines = [ln for ln in cap.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    traj = Trajectory.model_validate_json(lines[0])
    assert len(traj.tool_calls()) == 1


def test_capture_resets_then_appends_in_process(tmp_path):
    with agentdiff.record("c", project_root=tmp_path):
        sample_tool(1)
    with agentdiff.record("c", project_root=tmp_path):
        sample_tool(2)
    cap = tmp_path / ".agentdiff" / "captures" / "c.jsonl"
    lines = [ln for ln in cap.read_text().splitlines() if ln.strip()]
    # First use truncates (fresh script run), second appends (in-process loop).
    assert len(lines) == 2


def test_capture_autoinfers_structure(tmp_path):
    (tmp_path / "agent.py").write_text(
        "import anthropic\ndef research_agent(q):\n    return q\n", encoding="utf-8"
    )
    with agentdiff.record("c", project_root=tmp_path):
        sample_tool(1)
    assert (tmp_path / ".agentdiff" / "structure.yaml").exists()


# --- agentdiff diff ---------------------------------------------------------

def _traj_with_agent(agent: str | None):
    events = []
    if agent is not None:
        events.append(
            LLMRequestEvent(
                call_id=uuid4(),
                canonical=CanonicalLLMCall(provider="anthropic", model="claude"),
                captured_by="http_shim",
                callsite=CallSite(file="a.py", function=agent, line=1),
                inferred_agent=agent,
            )
        )
    return Trajectory(test_case_id="capture", version_tag="baseline", input={}, events=events)


def test_diff_two_captures_shows_stopped_agent(tmp_path):
    save(
        StructureDoc(agents=[AgentEntry(name="researcher", function="researcher", file="a.py", line=1)]),
        tmp_path,
    )
    caps = tmp_path / ".agentdiff" / "captures"
    caps.mkdir(parents=True)
    append_trajectory(caps / "before.jsonl", _traj_with_agent("researcher"))
    append_trajectory(caps / "after.jsonl", _traj_with_agent(None))  # researcher no longer fires

    result = CliRunner().invoke(diff_cmd, ["before", "after", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.output

    dashboard = next((tmp_path / ".agentdiff" / "reports").glob("*/dashboard.html"))
    html = dashboard.read_text()
    assert "window.__AGENTDIFF__" in html
    assert "researcher" in html
    # The stopped node is rate-based, so it flags red even though a single
    # sample per side gets the overall verdict stat-downgraded fail → WARN.
    assert '"stopped": true' in html
    assert "WARN" in result.output.upper()


def test_diff_missing_capture_errors(tmp_path):
    result = CliRunner().invoke(diff_cmd, ["nope", "alsonope", "--project", str(tmp_path)])
    assert result.exit_code == 1
    assert "No capture" in result.output

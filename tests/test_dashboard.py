"""Dashboard graph rendering + empty/partial states (Slice 1)."""
from agentdiff.compare import AgentInvocationDelta, ComparisonResult, TestCaseComparison
from agentdiff.dashboard import (
    _graph_section,
    render_dashboard,
    summarize_report,
    write_dashboard,
)
from agentdiff.graph_model import AgentGraph, GraphNode
from agentdiff.storage import write_run_store
from agentdiff.trajectory import TrajectorySet


def _agent_node(label, b, c, verdict="pass", stopped=False, hunk=None):
    return GraphNode(
        id=f"agent:{label}", label=label, kind="agent",
        baseline_rate=b, candidate_rate=c, verdict=verdict,
        fired=c > 0, stopped=stopped, hunk=hunk,
    )


# --- graph section states (fast, no SQLite) --------------------------------

def test_graph_section_marks_stopped_agent():
    g = AgentGraph(nodes=[_agent_node("researcher", 1.0, 0.0, "fail", stopped=True)], has_change=True)
    out = _graph_section(g)
    assert "researcher" in out
    assert "stopped firing" in out.lower()
    assert "<svg" in out


def test_graph_section_empty_state():
    out = _graph_section(AgentGraph())
    assert "No comparison data" in out
    assert "<svg" not in out


def test_graph_section_no_change_banner():
    g = AgentGraph(nodes=[_agent_node("researcher", 1.0, 1.0, "pass")], has_change=False)
    out = _graph_section(g)
    assert "No behavioral change detected" in out


def test_graph_section_embeds_hunk_payload():
    g = AgentGraph(
        nodes=[_agent_node("researcher", 1.0, 0.0, "fail", stopped=True, hunk="@@ -1 +1 @@")],
        has_change=True,
    )
    out = _graph_section(g)
    assert "@@ -1 +1 @@" in out  # carried in the HUNKS JSON for click-to-reveal


# --- end-to-end through summarize_report + render_dashboard ----------------

def _comparison(deltas, overall="pass"):
    return ComparisonResult(
        test_case_comparisons=[
            TestCaseComparison(
                test_case_id="tc1", agent_invocation_deltas=deltas, overall_verdict=overall
            )
        ],
        overall_verdict=overall,
    )


def _empty_sets():
    return (
        TrajectorySet(version_tag="baseline", trajectories=[]),
        TrajectorySet(version_tag="candidate", trajectories=[]),
    )


def test_summarize_and_render_end_to_end(tmp_path):
    report_dir = tmp_path / "run"
    report_dir.mkdir()
    db = report_dir / "agentdiff.sqlite"
    comp = _comparison(
        [
            AgentInvocationDelta(
                agent_name="researcher", function="researcher",
                baseline_rate=1.0, candidate_rate=0.0, delta=-1.0,
                baseline_count=10, candidate_count=0,
                baseline_total=10, candidate_total=10, verdict="fail",
            )
        ],
        overall="fail",
    )
    baseline, candidate = _empty_sets()
    write_run_store(
        db,
        metadata={"run_id": "r1", "timestamp": "t"},
        baseline_set=baseline,
        candidate_set=candidate,
        comparison=comp,
    )
    summary = summarize_report(report_dir)
    assert summary["graph"].has_change is True
    out = render_dashboard(summary)
    assert "researcher" in out
    assert "stopped firing" in out.lower()
    assert "<svg" in out


def test_write_dashboard_handles_run_with_no_comparison(tmp_path):
    report_dir = tmp_path / "run"
    report_dir.mkdir()
    db = report_dir / "agentdiff.sqlite"
    baseline, candidate = _empty_sets()
    write_run_store(
        db,
        metadata={"run_id": "r1", "timestamp": "t"},
        baseline_set=baseline,
        candidate_set=candidate,
    )
    out = write_dashboard(report_dir)
    assert out.exists()
    text = out.read_text()
    assert "<html" in text
    assert "No comparison data" in text  # graceful empty state, no crash

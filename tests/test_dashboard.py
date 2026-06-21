"""Dashboard: inject the run's graph payload into the vendored React bundle."""
from agentdiff.compare import AgentInvocationDelta, ComparisonResult, TestCaseComparison
from agentdiff.dashboard import render_dashboard, summarize_report, write_dashboard
from agentdiff.graph_model import AgentGraph, GraphNode
from agentdiff.storage import write_run_store
from agentdiff.trajectory import TrajectorySet


def _agent_node(label, b, c, verdict="pass", stopped=False, hunk=None):
    return GraphNode(
        id=f"agent:{label}", label=label, kind="agent",
        baseline_rate=b, candidate_rate=c, verdict=verdict,
        fired=c > 0, stopped=stopped, hunk=hunk,
    )


# --- injection contract (unit, no SQLite) ----------------------------------

def test_render_injects_graph_payload():
    g = AgentGraph(nodes=[_agent_node("researcher", 1.0, 0.0, "fail", stopped=True)], has_change=True)
    out = render_dashboard({"graph": g, "meta": {"baseline_ref": "main"}})
    assert "window.__AGENTDIFF__" in out
    assert "researcher" in out          # node label rides in the payload
    assert "true" in out                # has_change/stopped serialize as JSON true


def test_render_empty_graph_still_injects():
    out = render_dashboard({"graph": AgentGraph(), "meta": {}})
    assert "window.__AGENTDIFF__" in out
    assert '"nodes": []' in out


def test_render_escapes_closing_script_in_hunk():
    # A diff hunk containing "</script>" must not break out of the injected tag.
    g = AgentGraph(nodes=[_agent_node("x", 1.0, 0.0, "fail", stopped=True, hunk="a</script>b")])
    out = render_dashboard({"graph": g, "meta": {}})
    assert "a</script>b" not in out      # raw sequence escaped
    assert "a<\\/script>b" in out        # escaped form present


# --- end to end through summarize_report + write_dashboard -----------------

def _comparison(deltas, overall="pass"):
    return ComparisonResult(
        test_case_comparisons=[
            TestCaseComparison(test_case_id="tc1", agent_invocation_deltas=deltas, overall_verdict=overall)
        ],
        overall_verdict=overall,
    )


def _empty_sets():
    return (
        TrajectorySet(version_tag="baseline", trajectories=[]),
        TrajectorySet(version_tag="candidate", trajectories=[]),
    )


def test_summarize_builds_graph_and_meta(tmp_path):
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
        metadata={"run_id": "r1", "timestamp": "t", "baseline_ref": "main"},
        baseline_set=baseline, candidate_set=candidate, comparison=comp,
    )
    # metadata.json is what summarize_report reads for meta.
    (report_dir / "metadata.json").write_text(
        '{"baseline_ref": "main", "candidate_ref": "working", "samples_per_case": 20}'
    )

    summary = summarize_report(report_dir)
    assert summary["graph"].has_change is True
    assert any(n.label == "researcher" and n.stopped for n in summary["graph"].nodes)
    assert summary["meta"]["baseline_ref"] == "main"

    out = render_dashboard(summary)
    assert "window.__AGENTDIFF__" in out
    assert "researcher" in out


def test_write_dashboard_handles_run_with_no_comparison(tmp_path):
    report_dir = tmp_path / "run"
    report_dir.mkdir()
    db = report_dir / "agentdiff.sqlite"
    baseline, candidate = _empty_sets()
    write_run_store(
        db,
        metadata={"run_id": "r1", "timestamp": "t"},
        baseline_set=baseline, candidate_set=candidate,
    )
    out = write_dashboard(report_dir)
    assert out.exists()
    text = out.read_text()
    assert "window.__AGENTDIFF__" in text
    assert '"nodes": []' in text  # empty run → empty graph, handled at runtime

"""Graph model: before/after agent graph built from a comparison run."""
from uuid import uuid4

from agentdiff.capture.events import CallSite, LocalToolInvokedEvent
from agentdiff.compare import (
    AgentInvocationDelta,
    ComparisonResult,
    TestCaseComparison,
    ToolUsageDelta,
)
from agentdiff.graph_model import build
from agentdiff.trajectory import Trajectory, TrajectorySet


def _agent_delta(name, b_rate, c_rate, verdict="pass", *, significant=True, total=10):
    return AgentInvocationDelta(
        agent_name=name,
        function=name,
        baseline_rate=b_rate,
        candidate_rate=c_rate,
        delta=c_rate - b_rate,
        baseline_count=int(b_rate * total),
        candidate_count=int(c_rate * total),
        baseline_total=total,
        candidate_total=total,
        significant=significant,
        verdict=verdict,
    )


def _tool_delta(name, b_avg, c_avg, verdict="pass", *, significant=True):
    return ToolUsageDelta(
        tool_name=name, baseline_avg=b_avg, candidate_avg=c_avg,
        delta=c_avg - b_avg, verdict=verdict, significant=significant,
    )


def _comparison(agent_deltas, tool_deltas=(), overall="pass"):
    return ComparisonResult(
        test_case_comparisons=[
            TestCaseComparison(
                test_case_id="tc1",
                agent_invocation_deltas=list(agent_deltas),
                tool_usage_deltas=list(tool_deltas),
                overall_verdict=overall,
            )
        ],
        overall_verdict=overall,
    )


def _empty():
    return (
        TrajectorySet(version_tag="baseline", trajectories=[]),
        TrajectorySet(version_tag="candidate", trajectories=[]),
    )


def _tool_traj(version, agent, tool):
    return Trajectory(
        test_case_id="tc1",
        version_tag=version,
        input={},
        events=[
            LocalToolInvokedEvent(
                call_id=uuid4(),
                tool_name=tool,
                callsite=CallSite(file="a.py", function=agent, line=1),
                inferred_agent=agent,
            )
        ],
    )


# --- P1: the unfired agent must never vanish -------------------------------

def test_unfired_agent_still_appears():
    """An agent that fired in baseline but not candidate is the whole point —
    it must still be a node, marked stopped, so the renderer can light it red."""
    g = build(_comparison([_agent_delta("researcher", 1.0, 0.0, "fail")]), None, *_empty())
    node = next(n for n in g.nodes if n.label == "researcher")
    assert node.stopped is True
    assert node.fired is False
    assert node.verdict == "fail"
    assert g.has_change is True


def test_no_diff_means_no_change():
    g = build(_comparison([_agent_delta("researcher", 1.0, 1.0, "pass")]), None, *_empty())
    node = next(n for n in g.nodes if n.label == "researcher")
    assert node.stopped is False
    assert node.fired is True
    assert g.has_change is False


# --- edges ------------------------------------------------------------------

def test_agent_tool_edge_from_events():
    comp = _comparison(
        [_agent_delta("researcher", 1.0, 1.0)],
        [_tool_delta("web_search", 1.0, 1.0)],
    )
    baseline = TrajectorySet(
        version_tag="baseline",
        trajectories=[_tool_traj("baseline", "researcher", "web_search")],
    )
    candidate = TrajectorySet(
        version_tag="candidate",
        trajectories=[_tool_traj("candidate", "researcher", "web_search")],
    )
    g = build(comp, None, baseline, candidate)
    edges = {(e.source, e.target) for e in g.edges}
    assert ("agent:researcher", "tool:web_search") in edges


def test_edge_skipped_when_endpoint_not_a_node():
    # ghost_tool has no tool delta, so it is not a node — no dangling edge.
    comp = _comparison([_agent_delta("researcher", 1.0, 1.0)])
    candidate = TrajectorySet(
        version_tag="candidate",
        trajectories=[_tool_traj("candidate", "researcher", "ghost_tool")],
    )
    g = build(comp, None, TrajectorySet(version_tag="baseline", trajectories=[]), candidate)
    assert g.edges == []


# --- attribution ------------------------------------------------------------

def test_attribution_attached_to_node():
    attribution = {
        "attributions": [
            {
                "agent_name": "researcher",
                "primary": {"target_path": "prompts/sys.txt", "hunk": "@@ -1 +1 @@\n-a\n+b"},
                "explanation": "prompt changed",
            }
        ]
    }
    g = build(_comparison([_agent_delta("researcher", 1.0, 0.0, "fail")]), attribution, *_empty())
    node = next(n for n in g.nodes if n.label == "researcher")
    assert node.cause_file == "prompts/sys.txt"
    assert "@@" in node.hunk
    assert node.explanation == "prompt changed"


def test_missing_attribution_still_renders_node():
    g = build(_comparison([_agent_delta("researcher", 1.0, 0.0, "fail")]), None, *_empty())
    node = next(n for n in g.nodes if n.label == "researcher")
    assert node.hunk is None
    assert node.cause_file is None


# --- input shapes / empty ---------------------------------------------------

def test_comparison_accepted_as_serialized_dict():
    comp = _comparison([_agent_delta("researcher", 1.0, 0.0, "fail")])
    g = build(comp.model_dump(), None, *_empty())
    assert any(n.label == "researcher" and n.stopped for n in g.nodes)


def test_empty_comparison_is_empty_graph():
    g = build(None, None, *_empty())
    assert g.nodes == []
    assert g.edges == []
    assert g.has_change is False


# --- trust signaling (#4) ---------------------------------------------------

def test_unconfirmed_change_marks_uncertain():
    # A flagged change that is NOT statistically significant → uncertain.
    g = build(
        _comparison([_agent_delta("researcher", 1.0, 0.0, "warn", significant=False, total=1)]),
        None, *_empty(),
    )
    node = next(n for n in g.nodes if n.label == "researcher")
    assert node.significant is False
    assert g.has_uncertain is True
    assert g.min_samples == 1


def test_confirmed_change_is_certain():
    g = build(
        _comparison([_agent_delta("researcher", 1.0, 0.0, "fail", significant=True, total=20)]),
        None, *_empty(),
    )
    node = next(n for n in g.nodes if n.label == "researcher")
    assert node.significant is True
    assert g.has_uncertain is False
    assert g.min_samples == 20


def _two_tc_comparison(tc1_deltas, tc2_deltas):
    return ComparisonResult(
        test_case_comparisons=[
            TestCaseComparison(test_case_id="tc1", agent_invocation_deltas=list(tc1_deltas)),
            TestCaseComparison(test_case_id="tc2", agent_invocation_deltas=list(tc2_deltas)),
        ],
    )


def test_confirmed_worst_verdict_stays_significant_across_test_cases():
    # Same agent: a CONFIRMED fail in tc1 and an UNCERTAIN warn in tc2. The node
    # shows the fail (worst), and that fail is confirmed — so the sparse tc2 must
    # not flip the whole graph to "uncertain". (Regression for the aggregation bug.)
    g = build(
        _two_tc_comparison(
            [_agent_delta("researcher", 1.0, 0.0, "fail", significant=True, total=20)],
            [_agent_delta("researcher", 1.0, 0.5, "warn", significant=False, total=1)],
        ),
        None, *_empty(),
    )
    node = next(n for n in g.nodes if n.label == "researcher")
    assert node.verdict == "fail"
    assert node.significant is True
    assert g.has_uncertain is False


def test_min_samples_reflects_uncertain_agent_not_unrelated():
    # Agent A is a confirmed pass observed once; agent B is the uncertain change
    # at 8 runs. The banner's "N runs" must cite B's 8, not A's unrelated 1.
    g = build(
        _comparison([
            _agent_delta("stable", 1.0, 1.0, "pass", significant=True, total=1),
            _agent_delta("flaky", 1.0, 0.4, "warn", significant=False, total=8),
        ]),
        None, *_empty(),
    )
    assert g.has_uncertain is True
    assert g.min_samples == 8


def test_uncertain_tool_change_marks_graph_uncertain():
    # The only flagged change is a non-significant tool delta; agents are all
    # confirmed-pass. The trust banner must still fire on the tool's uncertainty.
    g = build(
        _comparison(
            [_agent_delta("orchestrator", 1.0, 1.0, "pass", significant=True)],
            tool_deltas=[_tool_delta("web_search", 2.0, 3.5, "warn", significant=False)],
        ),
        None, *_empty(),
    )
    tool = next(n for n in g.nodes if n.label == "web_search")
    assert tool.significant is False
    assert g.has_uncertain is True


def test_empty_side_yields_zero_min_samples():
    # An uncertain agent with an empty baseline side (baseline_total=0). The
    # limiting per-side count is 0, so the backend reports min_samples=0 honestly.
    # (The banner copy for the 0 case is a frontend follow-up, out of scope here.)
    delta = AgentInvocationDelta(
        agent_name="researcher", function="researcher",
        baseline_rate=0.0, candidate_rate=1.0, delta=1.0,
        baseline_count=0, candidate_count=5,
        baseline_total=0, candidate_total=5,
        significant=False, verdict="warn",
    )
    g = build(_comparison([delta]), None, *_empty())
    assert g.has_uncertain is True
    assert g.min_samples == 0

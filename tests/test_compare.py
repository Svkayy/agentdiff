"""Day 5: behavioral comparison engine."""
from uuid import uuid4

from agentdiff.capture.events import (
    CallSite, CanonicalLLMCall, LLMRequestEvent, LocalToolInvokedEvent,
)
from agentdiff.compare import (
    compare_all, compare_test_case, compute_invocation_rates, compute_tool_averages,
)
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc, ToolEntry
from agentdiff.trajectory import Trajectory, TrajectorySet

STRUCTURE = StructureDoc(
    agents=[AgentEntry(name="Router", function="route", file="a.py", line=1)],
    tools=[ToolEntry(name="search", function="web_search", file="a.py", line=5)],
)


def _traj(tc_id, tag, agent_names=(), tool_names=()):
    cid = uuid4()
    events = []
    for a in agent_names:
        events.append(
            LLMRequestEvent(
                call_id=cid,
                canonical=CanonicalLLMCall(provider="anthropic"),
                captured_by="sdk_shim",
                callsite=CallSite(file="a.py", function="route", line=1),
                inferred_agent=a,
            )
        )
    for tname in tool_names:
        events.append(
            LocalToolInvokedEvent(
                call_id=cid,
                tool_name=tname,
                callsite=CallSite(file="a.py", function=tname, line=5),
                inferred_agent="Router",
            )
        )
    return Trajectory(test_case_id=tc_id, version_tag=tag, input={}, events=events)


def test_invocation_rate_full_vs_none():
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(4)]
    rates = compute_invocation_rates(baseline, STRUCTURE)
    assert rates["Router"] == 1.0

    none = [_traj("tc", "baseline") for _ in range(4)]
    assert compute_invocation_rates(none, STRUCTURE)["Router"] == 0.0


def test_invocation_delta_fail_verdict():
    # A full-vs-none swing is significant even at modest N.
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(8)]
    candidate = [_traj("tc", "candidate") for _ in range(8)]  # Router never fires
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    d = cmp.agent_invocation_deltas[0]
    assert d.baseline_rate == 1.0
    assert d.candidate_rate == 0.0
    assert d.delta == -1.0
    assert d.significant is True
    assert d.p_value < 0.05
    assert d.stats is not None
    assert d.stats.test == "two_proportion_z"
    assert d.stats.effect_label == "cohens_h"
    assert d.stats.confidence_interval is not None
    assert d.verdict == "fail"
    assert cmp.overall_verdict == "fail"


def test_invocation_delta_pass_when_stable():
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(8)]
    candidate = [_traj("tc", "candidate", agent_names=["Router"]) for _ in range(8)]
    d = compare_test_case("tc", baseline, candidate, STRUCTURE).agent_invocation_deltas[0]
    assert d.verdict == "pass"
    assert d.significant is False


def test_small_n_large_delta_downgrades_to_warn():
    """A large delta that isn't statistically significant softens to WARN."""
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(2)]
    # 2/2 vs 1/2 → delta -0.5 (fail-sized) but only 2 samples → not significant.
    candidate = [_traj("tc", "candidate", agent_names=["Router"]), _traj("tc", "candidate")]
    d = compare_test_case("tc", baseline, candidate, STRUCTURE).agent_invocation_deltas[0]
    assert d.delta == -0.5           # fail-sized effect…
    assert d.significant is False     # …but only 2 samples → can't trust it
    assert d.verdict == "warn"        # downgraded from fail


def test_tool_averages_and_delta():
    baseline = [_traj("tc", "baseline", tool_names=["web_search", "web_search"]) for _ in range(20)]
    candidate = [_traj("tc", "candidate", tool_names=["web_search"]) for _ in range(20)]
    assert compute_tool_averages(baseline)["web_search"] == 2.0
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    tool_d = next(d for d in cmp.tool_usage_deltas if d.tool_name == "web_search")
    assert tool_d.baseline_avg == 2.0
    assert tool_d.candidate_avg == 1.0
    assert tool_d.delta == -1.0
    assert tool_d.significant is True
    assert tool_d.stats is not None
    assert tool_d.stats.test == "mann_whitney_u"
    assert tool_d.stats.effect_label == "cliffs_delta"
    assert tool_d.stats.effect_size < 0
    assert tool_d.verdict == "fail"


def test_behavioral_overlap_jaccard():
    baseline = [_traj("tc", "baseline", tool_names=["a", "b"])]
    candidate = [_traj("tc", "candidate", tool_names=["b", "c"])]
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    # {a,b} vs {b,c} → intersection {b}=1, union {a,b,c}=3
    assert abs(cmp.behavioral_overlap - 1 / 3) < 1e-9


def test_compare_all_aggregates_worst_verdict():
    b = TrajectorySet(version_tag="baseline", trajectories=(
        [_traj("stable", "baseline", agent_names=["Router"]) for _ in range(20)]
        + [_traj("drift", "baseline", agent_names=["Router"]) for _ in range(20)]
    ))
    c = TrajectorySet(version_tag="candidate", trajectories=(
        [_traj("stable", "candidate", agent_names=["Router"]) for _ in range(20)]
        + [_traj("drift", "candidate") for _ in range(20)]  # Router disappears
    ))
    result = compare_all(b, c, STRUCTURE, ["stable", "drift"])
    assert result.overall_verdict == "fail"
    verdicts = {tc.test_case_id: tc.overall_verdict for tc in result.test_case_comparisons}
    assert verdicts["stable"] == "pass"
    assert verdicts["drift"] == "fail"


def test_custom_thresholds_change_verdict():
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(20)]
    candidate = [_traj("tc", "candidate") for _ in range(20)]
    cmp = compare_test_case(
        "tc",
        baseline,
        candidate,
        STRUCTURE,
        thresholds={
            "agent_invocation_rate_warn": 0.9,
            "agent_invocation_rate_fail": 1.1,
            "tool_usage_avg_warn": 0.5,
            "tool_usage_avg_fail": 1.0,
        },
    )
    assert cmp.agent_invocation_deltas[0].verdict == "warn"

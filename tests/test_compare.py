"""Day 5: behavioral comparison engine."""
from uuid import uuid4

from agentdiff.capture.events import (
    CallSite, CanonicalLLMCall, LLMRequestEvent, LocalToolInvokedEvent,
)
from agentdiff.compare import (
    compare_all, compare_test_case, compute_invocation_rates, compute_tool_averages,
)
from agentdiff.config import StatsConfig
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc, ToolEntry
from agentdiff.trajectory import Trajectory, TrajectorySet

STRUCTURE = StructureDoc(
    agents=[AgentEntry(name="Router", function="route", file="a.py", line=1)],
    tools=[ToolEntry(name="search", function="web_search", file="a.py", line=5)],
)


def _traj(tc_id, tag, agent_names=(), tool_names=(), total_latency_ms=0, total_tokens=0,
          status="success"):
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
    return Trajectory(
        test_case_id=tc_id, version_tag=tag, input={}, events=events,
        total_latency_ms=total_latency_ms, total_tokens=total_tokens, status=status,
    )


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


# ---------------------------------------------------------------------------
# Task 6: latency, token, and error-rate run-level deltas.
# ---------------------------------------------------------------------------

def _run_metric(cmp, metric):
    return next(d for d in cmp.run_metric_deltas if d.metric == metric)


def test_large_latency_shift_fails_significantly():
    baseline = [_traj("tc", "baseline", total_latency_ms=500) for _ in range(20)]
    candidate = [_traj("tc", "candidate", total_latency_ms=8000) for _ in range(20)]
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    d = _run_metric(cmp, "latency_ms")
    assert d.baseline_mean == 500
    assert d.candidate_mean == 8000
    assert d.delta == 7500
    assert d.p_value is not None and d.p_value < 0.05
    assert d.significant is True
    assert d.verdict == "fail"
    assert cmp.overall_verdict == "fail"


def test_identical_latency_sets_pass_p_equals_one():
    baseline = [_traj("tc", "baseline", total_latency_ms=500) for _ in range(10)]
    candidate = [_traj("tc", "candidate", total_latency_ms=500) for _ in range(10)]
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    d = _run_metric(cmp, "latency_ms")
    assert d.delta == 0
    assert d.p_value == 1.0
    assert d.verdict == "pass"


def test_token_delta_present_with_metric_name():
    baseline = [_traj("tc", "baseline", total_tokens=100) for _ in range(10)]
    candidate = [_traj("tc", "candidate", total_tokens=100) for _ in range(10)]
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    d = _run_metric(cmp, "total_tokens")
    assert d.baseline_mean == 100
    assert d.candidate_mean == 100
    assert d.verdict == "pass"


def test_error_rate_delta_fires_on_candidate_failures():
    baseline = [_traj("tc", "baseline", status="success") for _ in range(20)]
    candidate = [
        _traj("tc", "candidate", status="failed" if i < 10 else "success")
        for i in range(20)
    ]
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    d = _run_metric(cmp, "error_rate")
    assert d.baseline_mean == 0.0
    assert d.candidate_mean == 0.5
    assert d.delta == 0.5
    assert d.p_value is not None and d.p_value < 0.05
    assert d.significant is True
    assert d.verdict == "fail"


def test_run_metric_delta_shape_matches_payload_contract():
    baseline = [_traj("tc", "baseline", total_latency_ms=500) for _ in range(5)]
    candidate = [_traj("tc", "candidate", total_latency_ms=600) for _ in range(5)]
    cmp = compare_test_case("tc", baseline, candidate, STRUCTURE)
    d = _run_metric(cmp, "latency_ms")
    # With no stats_config passed, compare_test_case defaults to "none"
    # correction (adjusted mirrors raw) for backward compatibility.
    assert d.adjusted_p_value == d.p_value
    assert {"latency_ms", "total_tokens", "error_rate"} == {
        rd.metric for rd in cmp.run_metric_deltas
    }


# ---------------------------------------------------------------------------
# Task 7: Benjamini-Hochberg correction + low-power warnings.
# ---------------------------------------------------------------------------

def test_bh_correction_downgrades_verdict_when_adjusted_p_not_significant():
    """A delta significant at raw p but not at BH-adjusted p downgrades to warn.

    Build a family where one test case has a strong, clearly significant swing
    (raw p very small) and several other test cases contribute many
    near-1.0 p-values (agents/tools that never differ). With enough noise
    p-values in the family, BH correction inflates even a fairly small raw p
    for one borderline delta past alpha, downgrading fail -> warn.
    """
    structure = StructureDoc(
        agents=[AgentEntry(name="Router", function="route", file="a.py", line=1)],
        tools=[ToolEntry(name="search", function="web_search", file="a.py", line=5)],
    )
    stats_config = StatsConfig(correction="benjamini_hochberg", alpha=0.05, min_samples_warn=5)

    # Borderline test case: small-sample big swing -> raw p significant-ish but
    # not overwhelmingly so (n=6 vs n=6, full vs none).
    borderline_baseline = [_traj("borderline", "baseline", agent_names=["Router"]) for _ in range(6)]
    borderline_candidate = [_traj("borderline", "candidate") for _ in range(3)] + [
        _traj("borderline", "candidate", agent_names=["Router"]) for _ in range(3)
    ]

    ids = ["borderline"] + [f"noise{i}" for i in range(30)]
    b = TrajectorySet(version_tag="baseline", trajectories=(
        borderline_baseline
        + [
            traj
            for i in range(30)
            for traj in (
                [_traj(f"noise{i}", "baseline", agent_names=["Router"]) for _ in range(10)]
            )
        ]
    ))
    c = TrajectorySet(version_tag="candidate", trajectories=(
        borderline_candidate
        + [
            traj
            for i in range(30)
            for traj in (
                [_traj(f"noise{i}", "candidate", agent_names=["Router"]) for _ in range(10)]
            )
        ]
    ))

    raw_result = compare_all(b, c, structure, ids, stats_config=StatsConfig(correction="none"))
    raw_delta = raw_result.test_case_comparisons[0].agent_invocation_deltas[0]
    assert raw_delta.significant is True
    assert raw_delta.verdict in ("fail", "warn")
    raw_verdict = raw_delta.verdict

    corrected_result = compare_all(b, c, structure, ids, stats_config=stats_config)
    corrected_delta = corrected_result.test_case_comparisons[0].agent_invocation_deltas[0]
    assert corrected_delta.adjusted_p_value is not None
    assert corrected_delta.adjusted_p_value > raw_delta.p_value
    assert corrected_delta.significant is False
    assert corrected_delta.verdict == "warn"
    assert raw_verdict == "fail"


def test_low_power_flag_set_for_small_n_and_run_warning():
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(3)]
    candidate = [_traj("tc", "candidate") for _ in range(3)]
    stats_config = StatsConfig(correction="benjamini_hochberg", alpha=0.05, min_samples_warn=5)
    result = compare_all(b_set(baseline), c_set(candidate), STRUCTURE, ["tc"], stats_config=stats_config)
    tcc = result.test_case_comparisons[0]
    assert tcc.agent_invocation_deltas[0].low_power is True
    assert any("low" in w.lower() and "power" in w.lower() for w in result.warnings)
    assert any("tc" in w for w in result.warnings)


def test_low_power_not_set_when_n_meets_threshold():
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(10)]
    candidate = [_traj("tc", "candidate", agent_names=["Router"]) for _ in range(10)]
    stats_config = StatsConfig(correction="benjamini_hochberg", alpha=0.05, min_samples_warn=5)
    result = compare_all(b_set(baseline), c_set(candidate), STRUCTURE, ["tc"], stats_config=stats_config)
    tcc = result.test_case_comparisons[0]
    assert tcc.agent_invocation_deltas[0].low_power is False
    assert result.warnings == []


def test_none_correction_restores_old_behavior():
    baseline = [_traj("tc", "baseline", agent_names=["Router"]) for _ in range(8)]
    candidate = [_traj("tc", "candidate") for _ in range(8)]
    stats_config = StatsConfig(correction="none", alpha=0.05, min_samples_warn=5)
    result = compare_all(b_set(baseline), c_set(candidate), STRUCTURE, ["tc"], stats_config=stats_config)
    d = result.test_case_comparisons[0].agent_invocation_deltas[0]
    assert d.adjusted_p_value == d.p_value
    assert d.verdict == "fail"


def b_set(trajectories):
    return TrajectorySet(version_tag="baseline", trajectories=trajectories)


def c_set(trajectories):
    return TrajectorySet(version_tag="candidate", trajectories=trajectories)

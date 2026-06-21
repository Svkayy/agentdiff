"""Behavioral comparison engine.

Compares baseline vs candidate trajectories at a structural level:
  - agent invocation rates (how often each agent fires per trajectory)
  - tool usage (average tool invocations per trajectory, per tool)
  - behavioral overlap (Jaccard of the set of tools exercised)

All agent identity comes from the loaded ``structure.yaml`` (via the
``inferred_agent`` field on captured events) — nothing is hardcoded.
"""
from typing import Literal

from pydantic import BaseModel, Field

from agentdiff import stats
from agentdiff.structure.structure_yaml import StructureDoc
from agentdiff.trajectory import Trajectory

Verdict = Literal["pass", "warn", "fail"]

# Invocation-rate deltas (fraction of trajectories an agent appears in).
_RATE_FAIL = 0.5
_RATE_WARN = 0.2
# Tool average-count deltas (mean invocations per trajectory).
_TOOL_FAIL = 1.0
_TOOL_WARN = 0.5

_SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


class CompareThresholds(BaseModel):
    agent_invocation_rate_warn: float = _RATE_WARN
    agent_invocation_rate_fail: float = _RATE_FAIL
    tool_usage_avg_warn: float = _TOOL_WARN
    tool_usage_avg_fail: float = _TOOL_FAIL


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class AgentInvocationDelta(BaseModel):
    agent_name: str
    function: str
    baseline_rate: float
    candidate_rate: float
    delta: float
    baseline_count: int
    candidate_count: int
    baseline_total: int
    candidate_total: int
    p_value: float | None = None
    significant: bool = False
    verdict: Verdict


class ToolUsageDelta(BaseModel):
    tool_name: str
    baseline_avg: float
    candidate_avg: float
    delta: float
    p_value: float | None = None
    significant: bool = False
    verdict: Verdict


class TestCaseComparison(BaseModel):
    __test__ = False  # not a pytest test class despite the Test* name

    test_case_id: str
    agent_invocation_deltas: list[AgentInvocationDelta] = Field(default_factory=list)
    tool_usage_deltas: list[ToolUsageDelta] = Field(default_factory=list)
    behavioral_overlap: float | None = None  # Jaccard of exercised tool sets; None if N/A
    overall_verdict: Verdict = "pass"


class ComparisonResult(BaseModel):
    test_case_comparisons: list[TestCaseComparison] = Field(default_factory=list)
    overall_verdict: Verdict = "pass"


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _rate_verdict(delta: float, thresholds: CompareThresholds | None = None) -> Verdict:
    thresholds = thresholds or CompareThresholds()
    a = abs(delta)
    if a >= thresholds.agent_invocation_rate_fail:
        return "fail"
    if a >= thresholds.agent_invocation_rate_warn:
        return "warn"
    return "pass"


def _tool_verdict(delta: float, thresholds: CompareThresholds | None = None) -> Verdict:
    thresholds = thresholds or CompareThresholds()
    a = abs(delta)
    if a >= thresholds.tool_usage_avg_fail:
        return "fail"
    if a >= thresholds.tool_usage_avg_warn:
        return "warn"
    return "pass"


def _worst(verdicts: list[Verdict]) -> Verdict:
    worst: Verdict = "pass"
    for v in verdicts:
        if _SEVERITY[v] > _SEVERITY[worst]:
            worst = v
    return worst


def _apply_significance(effect_verdict: Verdict, significant: bool) -> Verdict:
    """Downgrade a non-significant effect: a difference we can't trust is softer.

    pass → pass; fail → fail if significant else warn; warn → warn if significant
    else pass. A large but statistically-uncertain delta surfaces as WARN ("real
    regression possible — collect more samples") rather than a hard FAIL.
    """
    if effect_verdict == "pass":
        return "pass"
    if significant:
        return effect_verdict
    return "warn" if effect_verdict == "fail" else "pass"


def compute_invocation_rates(
    trajectories: list[Trajectory], structure: StructureDoc
) -> dict[str, float]:
    """Fraction of trajectories in which each agent (by display name) appears."""
    if not trajectories:
        return {a.name: 0.0 for a in structure.agents}
    rates: dict[str, float] = {}
    for agent in structure.agents:
        count = sum(1 for t in trajectories if agent.name in t.agents_invoked())
        rates[agent.name] = count / len(trajectories)
    return rates


def compute_tool_averages(trajectories: list[Trajectory]) -> dict[str, float]:
    """Mean number of invocations per trajectory, keyed by observed tool name."""
    if not trajectories:
        return {}
    totals: dict[str, int] = {}
    for t in trajectories:
        for e in t.tool_calls():
            name = getattr(e, "tool_name", None)
            if name:
                totals[name] = totals.get(name, 0) + 1
    n = len(trajectories)
    return {name: count / n for name, count in totals.items()}


def _agent_fire_count(agent_name: str, trajectories: list[Trajectory]) -> int:
    """Number of trajectories in which the agent fired at least once."""
    return sum(1 for t in trajectories if agent_name in t.agents_invoked())


def _tool_count_vector(tool_name: str, trajectories: list[Trajectory]) -> list[int]:
    """Per-trajectory invocation counts for a tool (zeros included)."""
    vector: list[int] = []
    for t in trajectories:
        n = sum(1 for e in t.tool_calls() if getattr(e, "tool_name", None) == tool_name)
        vector.append(n)
    return vector


def _exercised_tools(trajectories: list[Trajectory]) -> set[str]:
    tools: set[str] = set()
    for t in trajectories:
        for e in t.tool_calls():
            name = getattr(e, "tool_name", None)
            if name:
                tools.add(name)
    return tools


def _jaccard(a: set[str], b: set[str]) -> float | None:
    union = a | b
    if not union:
        return None
    return len(a & b) / len(union)


# ---------------------------------------------------------------------------
# Top-level comparison
# ---------------------------------------------------------------------------

def compare_test_case(
    test_case_id: str,
    baseline: list[Trajectory],
    candidate: list[Trajectory],
    structure: StructureDoc,
    thresholds: CompareThresholds | dict[str, float] | None = None,
) -> TestCaseComparison:
    """Compare one test case's baseline vs candidate trajectory sets."""
    n_b, n_c = len(baseline), len(candidate)
    if thresholds is None:
        thresholds = CompareThresholds()
    elif not isinstance(thresholds, CompareThresholds):
        thresholds = CompareThresholds.model_validate(thresholds)

    agent_deltas: list[AgentInvocationDelta] = []
    for agent in structure.agents:
        b_count = _agent_fire_count(agent.name, baseline)
        c_count = _agent_fire_count(agent.name, candidate)
        b = b_count / n_b if n_b else 0.0
        c = c_count / n_c if n_c else 0.0
        delta = c - b
        p = stats.two_proportion_pvalue(b_count, n_b, c_count, n_c)
        significant = stats.is_significant(p)
        agent_deltas.append(
            AgentInvocationDelta(
                agent_name=agent.name,
                function=agent.function,
                baseline_rate=b,
                candidate_rate=c,
                delta=delta,
                baseline_count=b_count,
                candidate_count=c_count,
                baseline_total=n_b,
                candidate_total=n_c,
                p_value=p,
                significant=significant,
                verdict=_apply_significance(_rate_verdict(delta, thresholds), significant),
            )
        )

    b_tools = compute_tool_averages(baseline)
    c_tools = compute_tool_averages(candidate)
    tool_deltas: list[ToolUsageDelta] = []
    for name in sorted(set(b_tools) | set(c_tools)):
        b = b_tools.get(name, 0.0)
        c = c_tools.get(name, 0.0)
        delta = c - b
        p = stats.mann_whitney_pvalue(
            _tool_count_vector(name, baseline), _tool_count_vector(name, candidate)
        )
        significant = stats.is_significant(p)
        tool_deltas.append(
            ToolUsageDelta(
                tool_name=name,
                baseline_avg=b,
                candidate_avg=c,
                delta=delta,
                p_value=p,
                significant=significant,
                verdict=_apply_significance(_tool_verdict(delta, thresholds), significant),
            )
        )

    overlap = _jaccard(_exercised_tools(baseline), _exercised_tools(candidate))

    verdicts = [d.verdict for d in agent_deltas] + [d.verdict for d in tool_deltas]
    overall = _worst(verdicts)

    return TestCaseComparison(
        test_case_id=test_case_id,
        agent_invocation_deltas=agent_deltas,
        tool_usage_deltas=tool_deltas,
        behavioral_overlap=overlap,
        overall_verdict=overall,
    )


def compare_all(
    baseline_set,
    candidate_set,
    structure: StructureDoc,
    test_case_ids: list[str] | None = None,
    thresholds: CompareThresholds | dict[str, float] | None = None,
) -> ComparisonResult:
    """Compare every test case present across the two TrajectorySets."""
    if thresholds is None:
        resolved_thresholds = CompareThresholds()
    elif isinstance(thresholds, CompareThresholds):
        resolved_thresholds = thresholds
    else:
        resolved_thresholds = CompareThresholds.model_validate(thresholds)

    if test_case_ids is None:
        ids = sorted(
            {t.test_case_id for t in baseline_set.trajectories}
            | {t.test_case_id for t in candidate_set.trajectories}
        )
    else:
        ids = test_case_ids

    comparisons: list[TestCaseComparison] = []
    for tc_id in ids:
        b = baseline_set.for_test_case(tc_id)
        c = candidate_set.for_test_case(tc_id)
        comparisons.append(compare_test_case(tc_id, b, c, structure, resolved_thresholds))

    overall = _worst([c.overall_verdict for c in comparisons])
    return ComparisonResult(test_case_comparisons=comparisons, overall_verdict=overall)

"""Behavioral comparison engine.

Compares baseline vs candidate trajectories at a structural level:
  - agent invocation rates (how often each agent fires per trajectory)
  - tool usage (average tool invocations per trajectory, per tool)
  - behavioral overlap (Jaccard of the set of tools exercised)

All agent identity comes from the loaded ``structure.yaml`` (via the
``inferred_agent`` field on captured events) — nothing is hardcoded.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentdiff import stats
from agentdiff.config import StatsConfig
from agentdiff.structure.structure_yaml import StructureDoc
from agentdiff.trajectory import Trajectory

Verdict = Literal["pass", "warn", "fail"]

# Invocation-rate deltas (fraction of trajectories an agent appears in).
_RATE_FAIL = 0.5
_RATE_WARN = 0.2
# Tool average-count deltas (mean invocations per trajectory).
_TOOL_FAIL = 1.0
_TOOL_WARN = 0.5
# Run-level metric deltas (absolute difference in the metric's own units).
_LATENCY_MS_WARN = 1000.0
_LATENCY_MS_FAIL = 5000.0
_TOKENS_WARN = 200.0
_TOKENS_FAIL = 1000.0
_ERROR_RATE_WARN = 0.1
_ERROR_RATE_FAIL = 0.25

_RUN_METRICS: tuple[Literal["latency_ms", "total_tokens", "error_rate"], ...] = (
    "latency_ms", "total_tokens", "error_rate",
)

_SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


class CompareThresholds(BaseModel):
    agent_invocation_rate_warn: float = _RATE_WARN
    agent_invocation_rate_fail: float = _RATE_FAIL
    tool_usage_avg_warn: float = _TOOL_WARN
    tool_usage_avg_fail: float = _TOOL_FAIL
    latency_ms_warn: float = _LATENCY_MS_WARN
    latency_ms_fail: float = _LATENCY_MS_FAIL
    tokens_warn: float = _TOKENS_WARN
    tokens_fail: float = _TOKENS_FAIL
    error_rate_warn: float = _ERROR_RATE_WARN
    error_rate_fail: float = _ERROR_RATE_FAIL


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class StatisticalEvidence(BaseModel):
    """Modeled evidence behind a behavioral delta.

    Kept alongside the legacy ``p_value`` / ``significant`` fields so older
    consumers remain compatible while newer dashboards can show the actual
    statistical model, effect size, and uncertainty interval.
    """

    test: str
    p_value: float | None = None
    significant: bool = False
    alpha: float = 0.05
    effect_size: float | None = None
    effect_label: str
    confidence_interval: tuple[float, float] | None = None
    baseline_n: int
    candidate_n: int


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
    adjusted_p_value: float | None = None
    significant: bool = False
    low_power: bool = False
    stats: StatisticalEvidence | None = None
    verdict: Verdict


class ToolUsageDelta(BaseModel):
    tool_name: str
    baseline_avg: float
    candidate_avg: float
    delta: float
    p_value: float | None = None
    adjusted_p_value: float | None = None
    significant: bool = False
    low_power: bool = False
    stats: StatisticalEvidence | None = None
    verdict: Verdict


class RunMetricDelta(BaseModel):
    """A run-level behavioral delta: latency, token usage, or error rate."""

    metric: Literal["latency_ms", "total_tokens", "error_rate"]
    baseline_mean: float
    candidate_mean: float
    delta: float
    p_value: float | None = None
    adjusted_p_value: float | None = None
    significant: bool = False
    low_power: bool = False
    stats: StatisticalEvidence | None = None
    verdict: Verdict


class TestCaseComparison(BaseModel):
    __test__ = False  # not a pytest test class despite the Test* name

    test_case_id: str
    agent_invocation_deltas: list[AgentInvocationDelta] = Field(default_factory=list)
    tool_usage_deltas: list[ToolUsageDelta] = Field(default_factory=list)
    run_metric_deltas: list[RunMetricDelta] = Field(default_factory=list)
    behavioral_overlap: float | None = None  # Jaccard of exercised tool sets; None if N/A
    overall_verdict: Verdict = "pass"


class ComparisonResult(BaseModel):
    test_case_comparisons: list[TestCaseComparison] = Field(default_factory=list)
    overall_verdict: Verdict = "pass"
    warnings: list[str] = Field(default_factory=list)


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


def _run_metric_verdict(
    metric: Literal["latency_ms", "total_tokens", "error_rate"],
    delta: float,
    thresholds: CompareThresholds | None = None,
) -> Verdict:
    thresholds = thresholds or CompareThresholds()
    if metric == "latency_ms":
        warn, fail = thresholds.latency_ms_warn, thresholds.latency_ms_fail
    elif metric == "total_tokens":
        warn, fail = thresholds.tokens_warn, thresholds.tokens_fail
    else:
        warn, fail = thresholds.error_rate_warn, thresholds.error_rate_fail
    a = abs(delta)
    if a >= fail:
        return "fail"
    if a >= warn:
        return "warn"
    return "pass"


def severity(verdict: Verdict) -> int:
    """Ordering rank for a verdict: pass(0) < warn(1) < fail(2)."""
    return _SEVERITY[verdict]


def worst_verdict(*verdicts: Verdict) -> Verdict:
    """The most severe verdict among the arguments (pass < warn < fail)."""
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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _latency_vector(trajectories: list[Trajectory]) -> list[float]:
    return [float(t.total_latency_ms) for t in trajectories]


def _tokens_vector(trajectories: list[Trajectory]) -> list[float]:
    return [float(t.total_tokens) for t in trajectories]


def _failure_count(trajectories: list[Trajectory]) -> int:
    return sum(1 for t in trajectories if t.status != "success")


def _run_metric_delta(
    metric: Literal["latency_ms", "total_tokens", "error_rate"],
    baseline: list[Trajectory],
    candidate: list[Trajectory],
    thresholds: CompareThresholds,
    stats_config: StatsConfig,
) -> RunMetricDelta:
    n_b, n_c = len(baseline), len(candidate)

    if metric == "error_rate":
        b_fail = _failure_count(baseline)
        c_fail = _failure_count(candidate)
        b_mean = b_fail / n_b if n_b else 0.0
        c_mean = c_fail / n_c if n_c else 0.0
        delta = c_mean - b_mean
        p = stats.two_proportion_pvalue(b_fail, n_b, c_fail, n_c)
        significant = stats.is_significant(p, stats_config.alpha)
        modeled = StatisticalEvidence(
            test="two_proportion_z",
            p_value=p,
            significant=significant,
            alpha=stats_config.alpha,
            effect_size=stats.cohens_h(b_fail, n_b, c_fail, n_c),
            effect_label="cohens_h",
            confidence_interval=stats.proportion_delta_ci(b_fail, n_b, c_fail, n_c),
            baseline_n=n_b,
            candidate_n=n_c,
        )
    else:
        b_vector = _latency_vector(baseline) if metric == "latency_ms" else _tokens_vector(baseline)
        c_vector = _latency_vector(candidate) if metric == "latency_ms" else _tokens_vector(candidate)
        b_mean = _mean(b_vector)
        c_mean = _mean(c_vector)
        delta = c_mean - b_mean
        p = stats.mann_whitney_pvalue(b_vector, c_vector)
        significant = stats.is_significant(p, stats_config.alpha)
        modeled = StatisticalEvidence(
            test="mann_whitney_u",
            p_value=p,
            significant=significant,
            alpha=stats_config.alpha,
            effect_size=stats.cliffs_delta(b_vector, c_vector),
            effect_label="cliffs_delta",
            confidence_interval=None,
            baseline_n=len(b_vector),
            candidate_n=len(c_vector),
        )

    verdict = _apply_significance(_run_metric_verdict(metric, delta, thresholds), significant)
    low_power = n_b < stats_config.min_samples_warn or n_c < stats_config.min_samples_warn
    return RunMetricDelta(
        metric=metric,
        baseline_mean=b_mean,
        candidate_mean=c_mean,
        delta=delta,
        p_value=p,
        adjusted_p_value=p,  # Rewritten by the family-wide BH pass in compare_all.
        significant=significant,
        low_power=low_power,
        stats=modeled,
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# Top-level comparison
# ---------------------------------------------------------------------------

def compare_test_case(
    test_case_id: str,
    baseline: list[Trajectory],
    candidate: list[Trajectory],
    structure: StructureDoc,
    thresholds: CompareThresholds | dict[str, float] | None = None,
    stats_config: StatsConfig | None = None,
) -> TestCaseComparison:
    """Compare one test case's baseline vs candidate trajectory sets.

    Raw p-values, ``low_power`` flags, and provisional (uncorrected) verdicts
    are computed here. Benjamini-Hochberg correction is a family-wide concern
    (every delta across every test case in the comparison is one family), so
    ``compare_all`` applies it once, after every test case has been computed,
    and rewrites ``adjusted_p_value``/``significant``/``verdict`` in place.
    """
    n_b, n_c = len(baseline), len(candidate)
    if thresholds is None:
        thresholds = CompareThresholds()
    elif not isinstance(thresholds, CompareThresholds):
        thresholds = CompareThresholds.model_validate(thresholds)
    if stats_config is None:
        stats_config = StatsConfig(correction="none")
    low_power_sides = n_b < stats_config.min_samples_warn or n_c < stats_config.min_samples_warn

    agent_deltas: list[AgentInvocationDelta] = []
    for agent in structure.agents:
        b_count = _agent_fire_count(agent.name, baseline)
        c_count = _agent_fire_count(agent.name, candidate)
        b = b_count / n_b if n_b else 0.0
        c = c_count / n_c if n_c else 0.0
        delta = c - b
        p = stats.two_proportion_pvalue(b_count, n_b, c_count, n_c)
        significant = stats.is_significant(p, stats_config.alpha)
        modeled = StatisticalEvidence(
            test="two_proportion_z",
            p_value=p,
            significant=significant,
            alpha=stats_config.alpha,
            effect_size=stats.cohens_h(b_count, n_b, c_count, n_c),
            effect_label="cohens_h",
            confidence_interval=stats.proportion_delta_ci(b_count, n_b, c_count, n_c),
            baseline_n=n_b,
            candidate_n=n_c,
        )
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
                adjusted_p_value=p,  # Rewritten by the family-wide BH pass in compare_all.
                significant=significant,
                low_power=low_power_sides,
                stats=modeled,
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
        b_vector = _tool_count_vector(name, baseline)
        c_vector = _tool_count_vector(name, candidate)
        p = stats.mann_whitney_pvalue(b_vector, c_vector)
        significant = stats.is_significant(p, stats_config.alpha)
        modeled = StatisticalEvidence(
            test="mann_whitney_u",
            p_value=p,
            significant=significant,
            alpha=stats_config.alpha,
            effect_size=stats.cliffs_delta(b_vector, c_vector),
            effect_label="cliffs_delta",
            confidence_interval=None,
            baseline_n=len(b_vector),
            candidate_n=len(c_vector),
        )
        tool_deltas.append(
            ToolUsageDelta(
                tool_name=name,
                baseline_avg=b,
                candidate_avg=c,
                delta=delta,
                p_value=p,
                adjusted_p_value=p,  # Rewritten by the family-wide BH pass in compare_all.
                significant=significant,
                low_power=low_power_sides,
                stats=modeled,
                verdict=_apply_significance(_tool_verdict(delta, thresholds), significant),
            )
        )

    overlap = _jaccard(_exercised_tools(baseline), _exercised_tools(candidate))

    run_metric_deltas = [
        _run_metric_delta(metric, baseline, candidate, thresholds, stats_config)
        for metric in _RUN_METRICS
    ]

    verdicts = (
        [d.verdict for d in agent_deltas]
        + [d.verdict for d in tool_deltas]
        + [d.verdict for d in run_metric_deltas]
    )
    overall = worst_verdict(*verdicts)

    return TestCaseComparison(
        test_case_id=test_case_id,
        agent_invocation_deltas=agent_deltas,
        tool_usage_deltas=tool_deltas,
        run_metric_deltas=run_metric_deltas,
        behavioral_overlap=overlap,
        overall_verdict=overall,
    )


def _all_deltas(comparisons: list[TestCaseComparison]) -> list[Any]:
    """Every delta object across every test case, in a stable, repeatable order."""
    deltas: list[Any] = []
    for tcc in comparisons:
        deltas.extend(tcc.agent_invocation_deltas)
        deltas.extend(tcc.tool_usage_deltas)
        deltas.extend(tcc.run_metric_deltas)
    return deltas


def _delta_verdict_fn(delta: Any, thresholds: CompareThresholds) -> Verdict:
    """Recompute the pre-significance effect-size verdict for one delta."""
    if isinstance(delta, AgentInvocationDelta):
        return _rate_verdict(delta.delta, thresholds)
    if isinstance(delta, ToolUsageDelta):
        return _tool_verdict(delta.delta, thresholds)
    return _run_metric_verdict(delta.metric, delta.delta, thresholds)


def _apply_bh_correction(
    comparisons: list[TestCaseComparison],
    thresholds: CompareThresholds,
    stats_config: StatsConfig,
) -> None:
    """Benjamini-Hochberg-correct every p-value in the comparison as one family.

    Every agent-invocation, tool-usage, and run-metric delta across every test
    case contributes one p-value to a single family-wide correction pass (not
    corrected per test case) — this mutates each delta's ``adjusted_p_value``
    in place and, when ``stats_config.correction == "benjamini_hochberg"``,
    recomputes ``significant``/``verdict`` from the adjusted p rather than the
    raw one.
    """
    deltas = _all_deltas(comparisons)
    if not deltas:
        return
    use_adjusted = stats_config.correction == "benjamini_hochberg"
    if not use_adjusted:
        # "none" restores pre-Task-7 behavior: adjusted mirrors raw, no
        # verdict recomputation.
        return

    raw_pvalues = [d.p_value if d.p_value is not None else 1.0 for d in deltas]
    adjusted = stats.benjamini_hochberg(raw_pvalues)

    for delta, adj_p in zip(deltas, adjusted):
        delta.adjusted_p_value = adj_p
        significant = stats.is_significant(adj_p, stats_config.alpha)
        delta.significant = significant
        if delta.stats is not None:
            delta.stats.significant = significant
        delta.verdict = _apply_significance(_delta_verdict_fn(delta, thresholds), significant)

    for tcc in comparisons:
        verdicts = (
            [d.verdict for d in tcc.agent_invocation_deltas]
            + [d.verdict for d in tcc.tool_usage_deltas]
            + [d.verdict for d in tcc.run_metric_deltas]
        )
        tcc.overall_verdict = worst_verdict(*verdicts)


def _low_power_warnings(comparisons: list[TestCaseComparison]) -> list[str]:
    """One warning per test case that has any delta with an underpowered side."""
    warnings: list[str] = []
    for tcc in comparisons:
        deltas = (
            list(tcc.agent_invocation_deltas)
            + list(tcc.tool_usage_deltas)
            + list(tcc.run_metric_deltas)
        )
        if any(d.low_power for d in deltas):
            warnings.append(
                f"Test case '{tcc.test_case_id}' has low statistical power "
                "(fewer samples than min_samples_warn on at least one side) — "
                "treat its verdicts with caution."
            )
    return warnings


def compare_all(
    baseline_set,
    candidate_set,
    structure: StructureDoc,
    test_case_ids: list[str] | None = None,
    thresholds: CompareThresholds | dict[str, float] | None = None,
    stats_config: StatsConfig | None = None,
) -> ComparisonResult:
    """Compare every test case present across the two TrajectorySets.

    Benjamini-Hochberg correction (when enabled via ``stats_config.correction``)
    and low-power warnings are computed once, across the whole family of deltas
    from every test case — not per test case.
    """
    if thresholds is None:
        resolved_thresholds = CompareThresholds()
    elif isinstance(thresholds, CompareThresholds):
        resolved_thresholds = thresholds
    else:
        resolved_thresholds = CompareThresholds.model_validate(thresholds)

    if stats_config is None:
        stats_config = StatsConfig(correction="none")

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
        comparisons.append(
            compare_test_case(tc_id, b, c, structure, resolved_thresholds, stats_config)
        )

    _apply_bh_correction(comparisons, resolved_thresholds, stats_config)
    warnings = _low_power_warnings(comparisons)

    overall = worst_verdict(*(c.overall_verdict for c in comparisons))
    return ComparisonResult(
        test_case_comparisons=comparisons, overall_verdict=overall, warnings=warnings
    )

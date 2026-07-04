"""Shared finding model for CI checks, Slack briefs, and postmortems."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agentdiff.attribution.engine import AttributionResult
from agentdiff.compare import ComparisonResult, Verdict

_SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


class IncidentContext(BaseModel):
    """Where this gate ran: repo, PR, refs, tier, and CI run link."""

    repository: str | None = None  # owner/repo
    pr_number: int | None = None
    baseline_ref: str | None = None
    candidate_ref: str | None = None
    tier: str | None = None
    run_url: str | None = None
    server_url: str = "https://github.com"

    def pr_url(self) -> str | None:
        if self.repository and self.pr_number:
            return f"{self.server_url}/{self.repository}/pull/{self.pr_number}"
        return None


class IncidentFinding(BaseModel):
    # test_case_id is kept for backward compat but is now the agent function key
    # for aggregated findings (multiple test cases share one finding per agent+metric).
    test_case_id: str
    title: str
    verdict: Verdict
    metric: str
    impact_summary: str
    statistical_evidence: dict | None = None
    cause_path: str | None = None
    cause_rule: str | None = None
    cause_hunk: str | None = None
    explanation: str | None = None
    # Aggregation context — how many test cases were affected vs. total seen.
    # Stored in statistical_evidence JSON to avoid schema migration; also
    # exposed as top-level fields for easy renderer access.
    test_cases_affected: int = 1
    test_cases_total: int = 1


class IncidentSummary(BaseModel):
    verdict: Verdict
    findings: list[IncidentFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def build_incident_summary(
    comparison: ComparisonResult,
    attribution: AttributionResult | None = None,
    *,
    input_count: int | None = None,
    min_live_samples: int | None = None,
) -> IncidentSummary:
    """Build one pure-data summary consumed by every incident renderer.

    Findings are aggregated by (function, metric) across ALL test cases so that
    a single agent change affecting N test cases produces exactly ONE finding
    (not N findings).  Counts/rates are pooled across test cases; the worst
    verdict is carried; attribution is taken from the first matched test case
    (identical across test cases for the same agent change).
    """
    attr_by_key = {}
    if attribution is not None:
        attr_by_key = {
            (a.test_case_id, a.function, a.metric): a
            for a in attribution.attributions
        }

    warnings: list[str] = []
    if input_count == 0:
        warnings.append("AgentDiff ran on 0 inputs, so this gate is not meaningful.")
    if (
        min_live_samples is not None
        and input_count is not None
        and 0 < input_count < min_live_samples
    ):
        warnings.append(
            f"AgentDiff ran on {input_count} inputs, below the live-tier minimum "
            f"of {min_live_samples}."
        )

    # ── Aggregate per-agent deltas across test cases ──────────────────────────
    # Key: (function, metric) → one finding per changed agent.
    # Accumulator holds running totals across test cases.
    total_test_cases = len(comparison.test_case_comparisons)

    class _Acc:
        def __init__(self) -> None:
            self.agent_name: str = ""
            self.function: str = ""
            self.worst_verdict: Verdict = "pass"
            self.b_count: int = 0
            self.c_count: int = 0
            self.b_total: int = 0
            self.c_total: int = 0
            self.affected_tcs: int = 0
            # Attribution — take the first non-None hit (same code, same hunk).
            self.cause_path: str | None = None
            self.cause_rule: str | None = None
            self.cause_hunk: str | None = None
            self.explanation: str | None = None
            # Statistical evidence from the most-significant delta seen.
            self.stats: dict | None = None
            self.best_p: float | None = None  # smaller = more significant

    accumulators: dict[tuple[str, str], _Acc] = {}

    for tcc in comparison.test_case_comparisons:
        for delta in tcc.agent_invocation_deltas:
            if delta.verdict == "pass":
                continue
            key = (delta.function, "invocation_rate")
            if key not in accumulators:
                acc = _Acc()
                acc.agent_name = delta.agent_name
                acc.function = delta.function
                accumulators[key] = acc
            else:
                acc = accumulators[key]

            # Verdict: carry worst
            if _SEVERITY[delta.verdict] > _SEVERITY[acc.worst_verdict]:
                acc.worst_verdict = delta.verdict

            # Pool counts for aggregate rate computation
            acc.b_count += delta.baseline_count
            acc.c_count += delta.candidate_count
            acc.b_total += delta.baseline_total
            acc.c_total += delta.candidate_total
            acc.affected_tcs += 1

            # Attribution: take first non-None hit
            if acc.cause_path is None:
                attr = attr_by_key.get((tcc.test_case_id, delta.function, "invocation_rate"))
                if attr is not None:
                    primary = attr.primary
                    acc.cause_path = primary.target_path if primary else None
                    acc.cause_rule = primary.rule if primary else None
                    acc.cause_hunk = primary.hunk if primary else None
                    acc.explanation = attr.explanation

            # Statistical evidence: keep the one with the smallest p-value
            if delta.stats is not None:
                p = delta.stats.p_value
                if acc.best_p is None or (p is not None and p < acc.best_p):
                    acc.best_p = p
                    acc.stats = delta.stats.model_dump(mode="json")

    # ── Build one IncidentFinding per accumulated (function, metric) entry ───
    findings: list[IncidentFinding] = []
    for acc in accumulators.values():
        agg_b_rate = acc.b_count / acc.b_total if acc.b_total else 0.0
        agg_c_rate = acc.c_count / acc.c_total if acc.c_total else 0.0
        agg_delta = agg_c_rate - agg_b_rate

        tc_note = (
            f" ({acc.affected_tcs} of {total_test_cases} inputs)"
            if total_test_cases > 1
            else ""
        )
        # Enrich statistical_evidence with aggregation counts
        stats_dict = acc.stats
        if stats_dict is not None:
            stats_dict = {
                **stats_dict,
                "test_cases_affected": acc.affected_tcs,
                "test_cases_total": total_test_cases,
            }

        findings.append(
            IncidentFinding(
                test_case_id=acc.function,  # stable identifier per agent
                title=f"{acc.agent_name} invocation changed",
                verdict=acc.worst_verdict,
                metric="invocation_rate",
                impact_summary=(
                    f"{acc.agent_name} fired {agg_b_rate:.0%} on baseline "
                    f"and {agg_c_rate:.0%} on candidate "
                    f"({agg_delta:+.0%}){tc_note}."
                ),
                statistical_evidence=stats_dict,
                cause_path=acc.cause_path,
                cause_rule=acc.cause_rule,
                cause_hunk=acc.cause_hunk,
                explanation=acc.explanation,
                test_cases_affected=acc.affected_tcs,
                test_cases_total=total_test_cases,
            )
        )

    verdict: Verdict = comparison.overall_verdict
    if warnings and verdict == "pass":
        verdict = "warn"
    for finding in findings:
        if _SEVERITY[finding.verdict] > _SEVERITY[verdict]:
            verdict = finding.verdict
    return IncidentSummary(verdict=verdict, findings=findings, warnings=warnings)

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
    """Build one pure-data summary consumed by every incident renderer."""
    attr_by_key = {}
    if attribution is not None:
        attr_by_key = {
            (a.test_case_id, a.function, a.metric): a
            for a in attribution.attributions
        }

    findings: list[IncidentFinding] = []
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

    for tcc in comparison.test_case_comparisons:
        for delta in tcc.agent_invocation_deltas:
            if delta.verdict == "pass":
                continue
            attr = attr_by_key.get((tcc.test_case_id, delta.function, "invocation_rate"))
            primary = attr.primary if attr is not None else None
            findings.append(
                IncidentFinding(
                    test_case_id=tcc.test_case_id,
                    title=f"{delta.agent_name} invocation changed",
                    verdict=delta.verdict,
                    metric="invocation_rate",
                    impact_summary=(
                        f"{delta.agent_name} fired {delta.baseline_rate:.0%} on baseline "
                        f"and {delta.candidate_rate:.0%} on candidate "
                        f"({delta.delta:+.0%})."
                    ),
                    statistical_evidence=(
                        delta.stats.model_dump(mode="json")
                        if delta.stats is not None else None
                    ),
                    cause_path=primary.target_path if primary is not None else None,
                    cause_rule=primary.rule if primary is not None else None,
                    cause_hunk=primary.hunk if primary is not None else None,
                    explanation=attr.explanation if attr is not None else None,
                )
            )

    verdict: Verdict = comparison.overall_verdict
    if warnings and verdict == "pass":
        verdict = "warn"
    for finding in findings:
        if _SEVERITY[finding.verdict] > _SEVERITY[verdict]:
            verdict = finding.verdict
    return IncidentSummary(verdict=verdict, findings=findings, warnings=warnings)

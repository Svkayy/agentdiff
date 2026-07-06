"""Synchronous engine runner: bridges plain data to the agentdiff engine.

No SQLAlchemy imports or ORM attribute access here — all inputs are primitives
so this function is safe to run inside a thread (via asyncio.to_thread).
"""
from __future__ import annotations

from typing import Any

from agentdiff.attribution.engine import AttributionResult
from agentdiff.compare import ComparisonResult, compare_all
from agentdiff.incident.findings import build_incident_summary
from agentdiff.report_payload import assemble_payload
from agentdiff.structure.structure_yaml import StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory, TrajectorySet


def _to_set(trajectories: list[dict], side: str) -> TrajectorySet:
    """Build a TrajectorySet from plain trajectory dicts for one side."""
    trajs = [
        EngineTrajectory.model_validate(t["payload"])
        for t in trajectories
        if t["side"] == side
    ]
    return TrajectorySet(version_tag=side, trajectories=trajs)


def _compute_output_evals(
    baseline: TrajectorySet,
    candidate: TrajectorySet,
    test_case_ids: list[str],
    llm_client: Any = None,
) -> list[Any]:
    """Compute per-test-case output evals, mirroring the CLI compare path.

    Fold-in A: ``process_run`` previously never computed output evals, so the
    stored payload's ``outputEvals`` was always ``[]``.  This mirrors
    ``src/agentdiff/cli/compare.py``: for each test case, gather baseline and
    candidate final outputs and run ``evaluate_output``.  ``llm_client=None``
    (the default server-side) simply skips the judge — semantic/structural/
    length still compute, and ``skipped_checks`` records the skip.
    """
    from agentdiff import output_eval

    output_evals: list[Any] = []
    for tc_id in test_case_ids:
        b_out = [t.final_output or "" for t in baseline.for_test_case(tc_id)]
        c_out = [t.final_output or "" for t in candidate.for_test_case(tc_id)]
        output_evals.append(
            output_eval.evaluate_output(tc_id, b_out, c_out, llm_client=llm_client)
        )
    return output_evals


def run_engine(
    config: dict,
    attribution: dict | None,
    trajectories: list[dict],
    test_case_ids: list[str],
    *,
    llm_client: Any = None,
) -> tuple[str, list[dict], dict[str, Any]]:
    """Run the agentdiff engine once and return findings **and** payload.

    Fold-in B: comparison used to be computed twice (once for findings via
    ``process_run_sync``, once for the payload via ``build_run_payload``).
    This computes ``compare_all`` a single time and reuses the result for both
    the incident summary (findings) and the dashboard payload assembly.

    Returns ``(verdict, finding_dicts, report_payload)``.
    """
    structure = StructureDoc.model_validate(config)
    baseline = _to_set(trajectories, "baseline")
    candidate = _to_set(trajectories, "candidate")
    comparison = compare_all(baseline, candidate, structure, test_case_ids)

    attr: AttributionResult | None = None
    if attribution:
        attr = AttributionResult.model_validate(attribution)

    summary = build_incident_summary(
        comparison, attr, input_count=len(test_case_ids)
    )
    finding_dicts = [f.model_dump() for f in summary.findings]

    # Fold-in A: compute output evals server-side (judge skipped if no client).
    output_evals = _compute_output_evals(
        baseline, candidate, test_case_ids, llm_client=llm_client
    )

    attribution_dict = attr.model_dump(mode="json") if attr else None
    report_payload = assemble_payload(
        comparison=comparison,
        attribution=attribution_dict,
        baseline_set=baseline,
        candidate_set=candidate,
        output_evals=output_evals,
        meta={
            "baseline_trajectories": len(baseline.trajectories),
            "candidate_trajectories": len(candidate.trajectories),
        },
        run_quality={
            "baseline_trajectories": len(baseline.trajectories),
            "candidate_trajectories": len(candidate.trajectories),
        },
        structure=structure,
    )

    return summary.verdict, finding_dicts, report_payload


def process_run_sync(
    config: dict,
    attribution: dict | None,
    trajectories: list[dict],
    test_case_ids: list[str],
) -> tuple[str, list[dict]]:
    """Run the agentdiff engine against plain trajectory data (findings only).

    Retained for callers that only need the verdict + findings (e.g. drift
    detection).  ``run_engine`` is preferred when the payload is also needed.

    Returns:
        ``(verdict, finding_dicts)`` where *verdict* is one of
        ``"pass" | "warn" | "fail"`` and *finding_dicts* is a list of dicts
        whose keys match ``server.models.Finding`` columns.
    """
    structure = StructureDoc.model_validate(config)
    baseline = _to_set(trajectories, "baseline")
    candidate = _to_set(trajectories, "candidate")
    comparison = compare_all(baseline, candidate, structure, test_case_ids)

    attr: AttributionResult | None = None
    if attribution:
        attr = AttributionResult.model_validate(attribution)

    summary = build_incident_summary(
        comparison, attr, input_count=len(test_case_ids)
    )
    finding_dicts = [f.model_dump() for f in summary.findings]
    return summary.verdict, finding_dicts


# ``ComparisonResult`` is re-exported for callers that referenced it via the
# runner; ``run_engine`` supersedes the old payload-only ``build_run_payload``
# (fold-in B: one ``compare_all`` feeds both findings and payload).
__all__ = [
    "ComparisonResult",
    "process_run_sync",
    "run_engine",
]

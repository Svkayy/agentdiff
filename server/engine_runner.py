"""Synchronous engine runner: bridges plain data to the agentdiff engine.

No SQLAlchemy imports or ORM attribute access here — all inputs are primitives
so this function is safe to run inside a thread (via asyncio.to_thread).
"""
from __future__ import annotations

from typing import Any

from agentdiff.attribution.engine import AttributionResult
from agentdiff.compare import compare_all
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


def process_run_sync(
    config: dict,
    attribution: dict | None,
    trajectories: list[dict],
    test_case_ids: list[str],
) -> tuple[str, list[dict]]:
    """Run the agentdiff engine against plain trajectory data.

    Args:
        config: The run's config dict (will be validated as ``StructureDoc``).
        attribution: The run's attribution dict, or ``None``.
        trajectories: List of dicts with keys ``side``, ``test_case_id``, ``payload``.
        test_case_ids: Sorted list of distinct test-case IDs.

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


def build_run_payload(
    config: dict,
    attribution: dict | None,
    trajectories: list[dict],
) -> dict[str, Any]:
    """Assemble the full dashboard payload for a run from plain trajectory data.

    Reuses ``agentdiff.report_payload.assemble_payload`` — the same pure
    dict-assembly seam the CLI's on-disk ``build()`` calls — so the server
    payload shape matches the CLI report shape byte-for-byte (Tasks 6-8
    fields: per-metric ``run_metrics``, run-level ``warnings``,
    ``skipped_checks`` on output evals, ``confidence`` inside attribution).

    No SQLAlchemy imports or ORM attribute access here — safe to run inside
    a thread (via ``asyncio.to_thread``), matching ``process_run_sync``.
    """
    structure = StructureDoc.model_validate(config)
    baseline = _to_set(trajectories, "baseline")
    candidate = _to_set(trajectories, "candidate")
    test_case_ids = sorted({t["test_case_id"] for t in trajectories})
    comparison = compare_all(baseline, candidate, structure, test_case_ids)

    attr: AttributionResult | None = None
    if attribution:
        attr = AttributionResult.model_validate(attribution)
    attribution_dict = attr.model_dump(mode="json") if attr else None

    return assemble_payload(
        comparison=comparison,
        attribution=attribution_dict,
        baseline_set=baseline,
        candidate_set=candidate,
        output_evals=[],
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

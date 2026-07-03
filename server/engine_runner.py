"""Synchronous engine runner: bridges server DB rows to the agentdiff engine."""
from __future__ import annotations

from agentdiff.attribution.engine import AttributionResult
from agentdiff.compare import compare_all
from agentdiff.incident.findings import build_incident_summary
from agentdiff.structure.structure_yaml import StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory, TrajectorySet


def _to_set(rows: list, side: str) -> TrajectorySet:
    """Convert Trajectory DB rows for one side into a TrajectorySet."""
    trajs = [
        EngineTrajectory.model_validate(r.payload)
        for r in rows
        if r.side == side
    ]
    return TrajectorySet(version_tag=side, trajectories=trajs)


def process_run_sync(run_row, trajectory_rows) -> tuple[str, list[dict]]:
    """Run the agentdiff engine against stored trajectories.

    Args:
        run_row: A ``server.models.Run`` ORM instance.
        trajectory_rows: A sequence of ``server.models.Trajectory`` ORM rows.

    Returns:
        ``(verdict, finding_dicts)`` where *verdict* is one of
        ``"pass" | "warn" | "fail"`` and *finding_dicts* is a list of dicts
        whose keys match ``server.models.Finding`` columns.
    """
    structure = StructureDoc.model_validate(run_row.config)
    baseline = _to_set(trajectory_rows, "baseline")
    candidate = _to_set(trajectory_rows, "candidate")
    test_case_ids = sorted({r.test_case_id for r in trajectory_rows})
    comparison = compare_all(baseline, candidate, structure, test_case_ids)

    attribution: AttributionResult | None = None
    if run_row.attribution:
        attribution = AttributionResult.model_validate(run_row.attribution)

    summary = build_incident_summary(
        comparison, attribution, input_count=len(test_case_ids)
    )
    finding_dicts = [f.model_dump() for f in summary.findings]
    return summary.verdict, finding_dicts

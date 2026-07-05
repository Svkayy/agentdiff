"""Read-only assembly of the full dashboard payload from a run's artifacts.

Surfaces the data a ``compare`` run already wrote to ``agentdiff.sqlite`` (plus
``metadata.json``) as one JSON-serializable dict for the React UI. Computes
nothing new — every value comes from an existing artifact.
"""
import json
from pathlib import Path
from typing import Any

from agentdiff.capture.events import (
    LLMRequestEvent, LLMResponseEvent, LocalToolInvokedEvent, MCPToolInvokedEvent,
)
from agentdiff.graph_model import build as build_graph
from agentdiff.storage import load_trajectory_set_from_sqlite, read_artifact
from agentdiff.trajectory import Trajectory, TrajectorySet

_PREVIEW = 280


def build(report_dir: Path) -> dict[str, Any]:
    report_dir = Path(report_dir)
    metadata_path = report_dir / "metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    db_path = Path(metadata.get("sqlite_store", report_dir / "agentdiff.sqlite"))

    baseline_set = load_trajectory_set_from_sqlite(db_path, "baseline")
    candidate_set = load_trajectory_set_from_sqlite(db_path, "candidate")
    comparison = read_artifact(db_path, "comparison")
    attribution = read_artifact(db_path, "attribution")
    graph = build_graph(comparison, attribution, baseline_set, candidate_set)
    comparison = _with_run_metrics(comparison)

    meta: dict[str, Any] = {
        "baseline_ref": metadata.get("baseline_ref"),
        "candidate_ref": metadata.get("candidate_ref"),
        "samples_per_case": metadata.get("samples_per_case"),
        "timestamp": metadata.get("timestamp"),
        "smoke_mode": metadata.get("smoke_mode", False),
    }

    return {
        "meta": meta,
        "runQuality": {
            "baseline_trajectories": metadata.get("baseline_trajectories"),
            "candidate_trajectories": metadata.get("candidate_trajectories"),
            "baseline_failed": metadata.get("baseline_failed"),
            "candidate_failed": metadata.get("candidate_failed"),
            "max_failure_rate": metadata.get("max_failure_rate"),
            "thresholds": metadata.get("thresholds"),
        },
        "graph": graph.model_dump(),
        "comparison": comparison,
        "outputEvals": read_artifact(db_path, "output_evals") or [],
        "attribution": attribution,
        "trajectories": {
            "baseline": _side(baseline_set),
            "candidate": _side(candidate_set),
        },
    }


_RUN_METRIC_FIELDS = (
    "metric", "baseline_mean", "candidate_mean", "delta",
    "p_value", "adjusted_p_value", "verdict", "low_power",
)


def _with_run_metrics(comparison: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project each test case's ``run_metric_deltas`` into a ``run_metrics`` list.

    Keeps the exact field-name contract the dashboard renders against
    (``metric``, ``baseline_mean``, ``candidate_mean``, ``delta``, ``p_value``,
    ``adjusted_p_value``, ``verdict``, ``low_power``), independent of whatever
    extra internal fields (``significant``, ``stats``) the compare engine keeps
    on ``run_metric_deltas``.
    """
    if not comparison:
        return comparison
    for tcc in comparison.get("test_case_comparisons", []):
        tcc["run_metrics"] = [
            {field: rd.get(field) for field in _RUN_METRIC_FIELDS}
            for rd in tcc.get("run_metric_deltas", [])
        ]
    return comparison


def _side(tset: TrajectorySet) -> list[dict[str, Any]]:
    return [
        {
            "trajectory_id": str(t.run_id),
            "test_case_id": t.test_case_id,
            "status": t.status,
            "final_output": t.final_output,
            "total_tokens": t.total_tokens,
            "total_latency_ms": t.total_latency_ms,
            "timeline": _project_timeline(t),
        }
        for t in tset.trajectories
    ]


def _project_timeline(traj: Trajectory) -> list[dict[str, Any]]:
    # Real captures tag the agent on the request event, not the response. Map
    # request agents by call_id so a response row still shows its agent.
    agent_by_call = {
        ev.call_id: ev.inferred_agent
        for ev in traj.events
        if isinstance(ev, LLMRequestEvent) and ev.inferred_agent
    }
    out: list[dict[str, Any]] = []
    for ev in traj.events:
        agent = getattr(ev, "inferred_agent", None)
        if agent is None and isinstance(ev, LLMResponseEvent):
            agent = agent_by_call.get(ev.call_id)
        item: dict[str, Any] = {
            "seq": getattr(ev, "sequence", 0),
            "kind": getattr(ev, "event_type", type(ev).__name__),
            "inferred_agent": agent,
            "provider": None, "model": None, "latency_ms": getattr(ev, "latency_ms", None),
            "usage": None, "tool_name": None,
            "request_preview": None, "response_preview": None,
        }
        if isinstance(ev, (LLMRequestEvent, LLMResponseEvent)):
            c = ev.canonical
            item["provider"] = c.provider
            item["model"] = c.model
            item["usage"] = c.usage or None
            item["request_preview"] = _first_user_text(c.messages)
            if isinstance(ev, LLMResponseEvent) and c.response_text:
                item["response_preview"] = c.response_text[:_PREVIEW]
        elif isinstance(ev, (MCPToolInvokedEvent, LocalToolInvokedEvent)):
            item["tool_name"] = ev.tool_name
            item["request_preview"] = json.dumps(ev.arguments, default=str)[:_PREVIEW]
        out.append(item)
    return out


def _first_user_text(messages: list[dict[str, Any]]) -> str | None:
    for m in messages:
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                return content[:_PREVIEW]
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return str(block.get("text", ""))[:_PREVIEW]
    return None

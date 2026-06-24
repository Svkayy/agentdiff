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
from agentdiff.dashboard import summarize_report
from agentdiff.storage import load_trajectory_set_from_sqlite, read_artifact
from agentdiff.trajectory import Trajectory

_PREVIEW = 280


def build(report_dir: Path) -> dict[str, Any]:
    report_dir = Path(report_dir)
    metadata_path = report_dir / "metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    db_path = Path(metadata.get("sqlite_store", report_dir / "agentdiff.sqlite"))

    summary = summarize_report(report_dir)  # reuses graph + meta builder
    return {
        "meta": {
            **summary["meta"],
            "smoke_mode": metadata.get("smoke_mode", False),
        },
        "runQuality": {
            "baseline_trajectories": metadata.get("baseline_trajectories"),
            "candidate_trajectories": metadata.get("candidate_trajectories"),
            "baseline_failed": metadata.get("baseline_failed"),
            "candidate_failed": metadata.get("candidate_failed"),
            "max_failure_rate": metadata.get("max_failure_rate"),
            "thresholds": metadata.get("thresholds"),
        },
        "graph": summary["graph"].model_dump(),
        "comparison": read_artifact(db_path, "comparison"),
        "outputEvals": read_artifact(db_path, "output_evals") or [],
        "attribution": read_artifact(db_path, "attribution"),
        "trajectories": {
            "baseline": _side(db_path, "baseline"),
            "candidate": _side(db_path, "candidate"),
        },
    }


def _side(db_path: Path, tag: str) -> list[dict[str, Any]]:
    tset = load_trajectory_set_from_sqlite(db_path, tag)  # type: ignore[arg-type]
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

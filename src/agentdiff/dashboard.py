"""Local dashboard: serve the React/React Flow frontend with a run's data.

The UI is a Vite + React + React Flow app (source in ``frontend/``), built to a
single self-contained ``index.html`` vendored at ``dashboard_assets/index.html``.
At render time we inject the run's graph + metadata as ``window.__AGENTDIFF__`` so
the same bundle renders any run, offline, with no asset paths.

The graph itself is built by ``graph_model.build`` from the artifacts a
``compare`` run already persists — see that module for the node/edge model.
"""
import json
from pathlib import Path
from typing import Any

from agentdiff.graph_model import AgentGraph, build as build_graph
from agentdiff.storage import load_trajectory_set_from_sqlite, read_artifact

_ASSET = Path(__file__).parent / "dashboard_assets" / "index.html"

_FALLBACK_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'><title>AgentDiff</title></head>"
    "<body><p>Dashboard assets are not built. Run <code>npm --prefix frontend run build</code> "
    "and re-vendor <code>frontend/dist/index.html</code> to "
    "<code>src/agentdiff/dashboard_assets/index.html</code>.</p>"
    "<script>window.__AGENTDIFF__=__PAYLOAD__;</script></body></html>"
)


def latest_report_dir(project_root: Path) -> Path | None:
    reports = Path(project_root) / ".agentdiff" / "reports"
    if not reports.exists():
        return None
    dirs = [p for p in reports.iterdir() if p.is_dir()]
    return max(dirs, key=lambda p: p.name) if dirs else None


def write_dashboard(report_dir: Path) -> Path:
    report_dir = Path(report_dir)
    summary = summarize_report(report_dir)
    target = report_dir / "dashboard.html"
    target.write_text(render_dashboard(summary), encoding="utf-8")
    return target


def summarize_report(report_dir: Path) -> dict[str, Any]:
    report_dir = Path(report_dir)
    metadata_path = report_dir / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    db_path = Path(metadata.get("sqlite_store", report_dir / "agentdiff.sqlite"))
    graph = build_graph(
        read_artifact(db_path, "comparison"),
        read_artifact(db_path, "attribution"),
        load_trajectory_set_from_sqlite(db_path, "baseline"),
        load_trajectory_set_from_sqlite(db_path, "candidate"),
    )

    meta = {
        "baseline_ref": metadata.get("baseline_ref"),
        "candidate_ref": metadata.get("candidate_ref"),
        "samples_per_case": metadata.get("samples_per_case"),
        "timestamp": metadata.get("timestamp"),
    }

    return {"report_dir": str(report_dir), "meta": meta, "graph": graph}


def _payload_json(summary: dict[str, Any]) -> str:
    graph = summary.get("graph") or AgentGraph()
    payload = {
        "graph": graph.model_dump(),
        "meta": summary.get("meta", {}),
    }
    # ``</`` is escaped so a diff hunk containing "</script>" can't break out of
    # the injected <script> tag.
    return json.dumps(payload, default=str).replace("</", "<\\/")


def render_dashboard(summary: dict[str, Any]) -> str:
    """Inject the run's data into the vendored frontend bundle."""
    payload = _payload_json(summary)
    injection = f"<script>window.__AGENTDIFF__ = {payload};</script>"

    if _ASSET.exists():
        template = _ASSET.read_text(encoding="utf-8")
        if "</head>" in template:
            return template.replace("</head>", f"{injection}</head>", 1)
        return injection + template

    return _FALLBACK_HTML.replace("__PAYLOAD__", payload)

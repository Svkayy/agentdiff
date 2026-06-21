import html
import json
import sqlite3
from pathlib import Path
from typing import Any

from agentdiff.graph_model import AgentGraph, build as build_graph
from agentdiff.storage import load_trajectory_set_from_sqlite, read_artifact


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
    counts = _sqlite_counts(db_path)

    # Build the before/after agent graph from the artifacts the compare run
    # already persisted, plus the captured trajectories (for agent→tool edges).
    graph = build_graph(
        read_artifact(db_path, "comparison"),
        read_artifact(db_path, "attribution"),
        load_trajectory_set_from_sqlite(db_path, "baseline"),
        load_trajectory_set_from_sqlite(db_path, "candidate"),
    )

    report_text = ""
    report_path = report_dir / "report.md"
    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")

    return {
        "report_dir": str(report_dir),
        "metadata": metadata,
        "counts": counts,
        "graph": graph,
        "report_excerpt": report_text[:12000],
    }


# ---------------------------------------------------------------------------
# Before/after graph rendering (self-contained inline SVG + vanilla JS).
#
# Layout: agents in a left column, tools in a right column, agent→tool edges
# between them. A node that STOPPED firing (baseline > 0, candidate 0) is filled
# red — that is the signal the whole product exists to surface. Clicking a node
# reveals the attributed diff hunk in a side panel.
# ---------------------------------------------------------------------------

_NODE_W = 168
_NODE_H = 56
_COL_AGENT_X = 60
_COL_TOOL_X = 660
_ROW_Y0 = 92
_ROW_DY = 84


def _node_colors(node) -> tuple[str, str]:
    """Return (fill, border) for a node based on its diff state."""
    if node.stopped:
        return "#fdecea", "#d93025"  # red — stopped firing
    if node.verdict == "fail":
        return "#fdecea", "#d93025"
    if node.verdict == "warn":
        return "#fff4e5", "#f29900"  # amber
    return "#ffffff", "#cfd6dd"  # neutral


def _rate_label(node) -> str:
    if node.kind == "agent":
        return f"{node.baseline_rate:.0%} → {node.candidate_rate:.0%}"
    return f"{node.baseline_rate:.1f} → {node.candidate_rate:.1f}"


def _layout(graph: AgentGraph) -> dict[str, tuple[float, float]]:
    pos: dict[str, tuple[float, float]] = {}
    agents = [n for n in graph.nodes if n.kind == "agent"]
    tools = [n for n in graph.nodes if n.kind != "agent"]
    for i, n in enumerate(agents):
        pos[n.id] = (_COL_AGENT_X, _ROW_Y0 + i * _ROW_DY)
    for i, n in enumerate(tools):
        pos[n.id] = (_COL_TOOL_X, _ROW_Y0 + i * _ROW_DY)
    return pos


def _render_graph_svg(graph: AgentGraph) -> str:
    pos = _layout(graph)
    rows = max(
        sum(1 for n in graph.nodes if n.kind == "agent"),
        sum(1 for n in graph.nodes if n.kind != "agent"),
        1,
    )
    height = _ROW_Y0 + rows * _ROW_DY
    width = _COL_TOOL_X + _NODE_W + 40

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMinYMin meet" font-family="Inter, system-ui, sans-serif">'
    ]

    # Edges first (so nodes draw on top).
    for e in graph.edges:
        if e.source not in pos or e.target not in pos:
            continue
        x1, y1 = pos[e.source]
        x2, y2 = pos[e.target]
        sx = x1 + _NODE_W
        sy = y1 + _NODE_H / 2
        tx = x2
        ty = y2 + _NODE_H / 2
        parts.append(
            f'<line x1="{sx}" y1="{sy}" x2="{tx}" y2="{ty}" '
            f'stroke="#c4ccd4" stroke-width="1.5" />'
        )

    # Nodes.
    for n in graph.nodes:
        if n.id not in pos:
            continue
        x, y = pos[n.id]
        fill, border = _node_colors(n)
        clickable = ' style="cursor:pointer"' if n.hunk else ""
        parts.append(
            f'<g data-node="{html.escape(n.id, quote=True)}"{clickable}>'
            f'<rect x="{x}" y="{y}" rx="8" width="{_NODE_W}" height="{_NODE_H}" '
            f'fill="{fill}" stroke="{border}" stroke-width="2" />'
            f'<text x="{x + 12}" y="{y + 23}" font-size="13" font-weight="640" '
            f'fill="#17202a">{html.escape(n.label)}</text>'
            f'<text x="{x + 12}" y="{y + 42}" font-size="11" fill="#5d6875">'
            f'{html.escape(_rate_label(n))}'
            + ('  • stopped firing' if n.stopped else '')
            + '</text>'
            '</g>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _graph_section(graph: AgentGraph) -> str:
    """The headline graph panel, with empty/no-change states handled."""
    if not graph.nodes:
        return (
            '<section class="panel graph-panel">'
            '<h2>Behavioral graph</h2>'
            '<p class="muted">No comparison data in this run. '
            'Run <code>agentdiff compare</code> to populate the graph.</p>'
            '</section>'
        )

    banner = ""
    if not graph.has_change:
        banner = (
            '<div class="banner ok">No behavioral change detected '
            'between baseline and candidate.</div>'
        )
    elif any(n.stopped for n in graph.nodes):
        stopped = ", ".join(n.label for n in graph.nodes if n.stopped)
        banner = (
            f'<div class="banner warn">Stopped firing in candidate: '
            f'<strong>{html.escape(stopped)}</strong></div>'
        )

    hunks = {
        n.id: {
            "label": n.label,
            "cause_file": n.cause_file,
            "hunk": n.hunk,
            "explanation": n.explanation,
        }
        for n in graph.nodes
        if n.hunk or n.explanation
    }

    svg = _render_graph_svg(graph)
    # Build the interactive JS WITHOUT an f-string (avoids brace-escaping pitfalls
    # with JS object literals). Inject the hunk data as a JSON blob via .replace.
    script = """
<script>
(function () {
  var HUNKS = __HUNKS__;
  var panel = document.getElementById('hunk-panel');
  document.querySelectorAll('#agent-graph [data-node]').forEach(function (g) {
    g.addEventListener('click', function () {
      var info = HUNKS[g.getAttribute('data-node')];
      if (!info) { panel.innerHTML = '<p class="muted">No attribution for this node.</p>'; return; }
      var h = '';
      h += '<h3>' + info.label + '</h3>';
      if (info.cause_file) { h += '<div class="muted">' + info.cause_file + '</div>'; }
      if (info.explanation) { h += '<p>' + info.explanation + '</p>'; }
      if (info.hunk) {
        var pre = document.createElement('pre');
        pre.textContent = info.hunk;
        panel.innerHTML = h;
        panel.appendChild(pre);
      } else {
        panel.innerHTML = h;
      }
    });
  });
})();
</script>
""".replace("__HUNKS__", json.dumps(hunks))

    return (
        '<section class="panel graph-panel">'
        '<h2>Behavioral graph (baseline → candidate)</h2>'
        + banner
        + '<div class="graph-wrap">'
        + f'<div id="agent-graph" class="graph-svg">{svg}</div>'
        + '<aside id="hunk-panel" class="hunk-panel">'
        '<p class="muted">Click a changed node to see the attributed diff.</p>'
        '</aside>'
        '</div>'
        + script
        + '</section>'
    )


def render_dashboard(summary: dict[str, Any]) -> str:
    meta = summary.get("metadata", {})
    counts = summary.get("counts", {})
    capture = meta.get("capture", {})
    graph = summary.get("graph") or AgentGraph()
    graph_section = _graph_section(graph)
    report_excerpt = html.escape(summary.get("report_excerpt") or "No report.md found.")
    capture_items = "".join(
        f"<li><span>{html.escape(str(k))}</span><strong>{'on' if v else 'off'}</strong></li>"
        for k, v in sorted(capture.items())
    )
    event_items = "".join(
        f"<li><span>{html.escape(str(k))}</span><strong>{v}</strong></li>"
        for k, v in sorted((counts.get("events") or {}).items())
    ) or "<li><span>No events</span><strong>0</strong></li>"
    trajectory_items = "".join(
        f"<li><span>{html.escape(str(k))}</span><strong>{v}</strong></li>"
        for k, v in sorted((counts.get("trajectories") or {}).items())
    ) or "<li><span>No trajectories</span><strong>0</strong></li>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentDiff Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f9;
      color: #17202a;
    }}
    body {{ margin: 0; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 24px; }}
    h1 {{ font-size: 34px; margin: 0; letter-spacing: 0; }}
    h2 {{ font-size: 16px; margin: 0 0 12px; }}
    h3 {{ font-size: 14px; margin: 0 0 6px; }}
    .muted {{ color: #5d6875; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .panel {{ background: #ffffff; border: 1px solid #dfe4ea; border-radius: 8px; padding: 16px; }}
    .metric {{ font-size: 26px; font-weight: 740; margin-top: 6px; }}
    .two {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }}
    ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }}
    li {{ display: flex; justify-content: space-between; gap: 10px; border-bottom: 1px solid #edf0f3; padding-bottom: 8px; }}
    li:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    pre {{ overflow: auto; white-space: pre-wrap; background: #101820; color: #f5f7fb; border-radius: 8px; padding: 16px; line-height: 1.45; }}
    a {{ color: #0969da; }}
    .graph-panel {{ margin-bottom: 18px; }}
    .graph-wrap {{ display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 16px; }}
    .graph-svg {{ overflow-x: auto; }}
    .hunk-panel {{ border-left: 1px solid #edf0f3; padding-left: 16px; }}
    .hunk-panel pre {{ font-size: 12px; }}
    .banner {{ border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; font-size: 13px; }}
    .banner.ok {{ background: #e6f4ea; color: #137333; }}
    .banner.warn {{ background: #fef7e0; color: #b06000; }}
    code {{ background: #eef1f4; padding: 1px 5px; border-radius: 4px; }}
    @media (max-width: 780px) {{
      header, .two, .graph-wrap {{ display: block; }}
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>AgentDiff Dashboard</h1>
        <div class="muted">{html.escape(str(summary.get("report_dir", "")))}</div>
      </div>
      <div class="muted">{html.escape(str(meta.get("timestamp", "unknown run")))}</div>
    </header>

    {graph_section}

    <section class="grid">
      <div class="panel"><div class="muted">Baseline</div><div class="metric">{html.escape(str(meta.get("baseline_ref", "n/a")))}</div></div>
      <div class="panel"><div class="muted">Candidate</div><div class="metric">{html.escape(str(meta.get("candidate_ref", "n/a")))}</div></div>
      <div class="panel"><div class="muted">Samples</div><div class="metric">{html.escape(str(meta.get("samples_per_case", "n/a")))}</div></div>
      <div class="panel"><div class="muted">Smoke mode</div><div class="metric">{str(bool(meta.get("smoke_mode", False))).lower()}</div></div>
    </section>

    <section class="two">
      <div class="panel">
        <h2>Trajectories</h2>
        <ul>{trajectory_items}</ul>
      </div>
      <div class="panel">
        <h2>Events</h2>
        <ul>{event_items}</ul>
      </div>
    </section>

    <section class="panel" style="margin-top:12px">
      <h2>Capture</h2>
      <ul>{capture_items}</ul>
    </section>

    <section style="margin-top:18px">
      <h2>Report</h2>
      <pre>{report_excerpt}</pre>
    </section>
  </main>
</body>
</html>
"""


def _sqlite_counts(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"events": {}, "trajectories": {}}
    with sqlite3.connect(db_path) as conn:
        events = dict(
            conn.execute(
                "select event_type, count(*) from events group by event_type order by event_type"
            ).fetchall()
        )
        trajectories = dict(
            conn.execute(
                "select version_tag || ':' || status, count(*) "
                "from trajectories group by version_tag, status"
            ).fetchall()
        )
    return {"events": events, "trajectories": trajectories}

import html
import json
import sqlite3
from pathlib import Path
from typing import Any


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

    counts = _sqlite_counts(Path(metadata.get("sqlite_store", report_dir / "agentdiff.sqlite")))
    report_text = ""
    report_path = report_dir / "report.md"
    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")

    return {
        "report_dir": str(report_dir),
        "metadata": metadata,
        "counts": counts,
        "report_excerpt": report_text[:12000],
    }


def render_dashboard(summary: dict[str, Any]) -> str:
    meta = summary.get("metadata", {})
    counts = summary.get("counts", {})
    capture = meta.get("capture", {})
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
    @media (max-width: 780px) {{
      header, .two {{ display: block; }}
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

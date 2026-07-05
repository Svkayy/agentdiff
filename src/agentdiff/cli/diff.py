"""``agentdiff diff <before> <after>`` — diff two ambient captures, no Runner.

Loads two capture files recorded with ``agentdiff.capture()``, compares them, and
reuses the full report → dashboard pipeline. Attribution is observed-only by
default (prompt/model/tool changes from the captured data); pass ``--baseline
<git-ref>`` to restore the exact code-hunk attribution when the "before" code is
a committed ref.
"""
import json
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import click
from rich.console import Console

from agentdiff import compare as compare_engine
from agentdiff import storage
from agentdiff.attribution.engine import attribute, attribute_observed
from agentdiff.capture.session import captures_dir
from agentdiff.config import load_config
from agentdiff.dashboard import write_dashboard
from agentdiff.structure import structure_yaml
from agentdiff.structure.structure_yaml import StructureDoc

console = Console()


@click.command("diff")
@click.argument("before")
@click.argument("after")
@click.option("--project", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--baseline",
    default=None,
    help="Git ref of the 'before' code for full code-hunk attribution.",
)
@click.option("--serve", is_flag=True, help="Serve the dashboard over localhost.")
@click.option("--port", default=8765, show_default=True, type=int)
def diff_cmd(
    before: str, after: str, project: str, baseline: str | None, serve: bool, port: int
) -> None:
    """Diff two captures recorded with agentdiff.record(). No Runner, no git baseline."""
    root = Path(project).resolve()
    before_path = captures_dir(root) / f"{before}.jsonl"
    after_path = captures_dir(root) / f"{after}.jsonl"
    for capture_name, p in ((before, before_path), (after, after_path)):
        if not p.exists():
            console.print(
                f"[red]No capture '{capture_name}' at {p}.[/red]\n"
                f"Record one with: [cyan]with agentdiff.record(\"{capture_name}\"): ...[/cyan]"
            )
            raise SystemExit(1)

    baseline_set = storage.load_trajectory_set(before_path, "baseline")
    candidate_set = storage.load_trajectory_set(after_path, "candidate")
    if not baseline_set.trajectories or not candidate_set.trajectories:
        console.print("[red]One of the captures is empty — nothing to diff.[/red]")
        raise SystemExit(1)

    structure = structure_yaml.load(root) or StructureDoc()
    config = load_config(root)
    comparison = compare_engine.compare_all(
        baseline_set, candidate_set, structure, stats_config=config.stats
    )

    if baseline:
        # When ANTHROPIC_API_KEY is set, LLM explanations auto-enable via AUTO_LLM_EXPLAINER default.
        attribution = attribute(
            comparison,
            structure,
            baseline_set.trajectories,
            candidate_set.trajectories,
            repo_root=root,
            baseline_ref=baseline,
            candidate_ref=None,
        )
    else:
        attribution = attribute_observed(
            comparison, structure, baseline_set.trajectories, candidate_set.trajectories, root
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = root / ".agentdiff" / "reports" / timestamp
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": timestamp,
        "timestamp": timestamp,
        "baseline_ref": before,
        "candidate_ref": after,
        "samples_per_case": max(
            len(baseline_set.trajectories), len(candidate_set.trajectories)
        ),
        "mode": "capture-diff",
    }
    sqlite_path = storage.write_run_store(
        out / "agentdiff.sqlite",
        metadata=meta,
        baseline_set=baseline_set,
        candidate_set=candidate_set,
        comparison=comparison,
        attribution=attribution,
    )
    meta["sqlite_store"] = str(sqlite_path)
    (out / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    dashboard_path = write_dashboard(out)

    console.print(f"[green]Dashboard written[/green] → {dashboard_path}")
    console.print(f"Overall verdict: [bold]{comparison.overall_verdict.upper()}[/bold]")

    if serve:
        handler = partial(SimpleHTTPRequestHandler, directory=str(out))
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        console.print(f"[bold]Serving[/bold] http://127.0.0.1:{port}/dashboard.html")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped dashboard server.[/dim]")

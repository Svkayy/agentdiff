from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import click
from rich.console import Console

from agentdiff.dashboard import latest_report_dir, summarize_report, write_dashboard

console = Console()


@click.command("dashboard")
@click.option("--project", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--report-dir", default=None, type=click.Path(file_okay=False))
@click.option("--serve", is_flag=True, help="Serve the dashboard over localhost.")
@click.option("--port", default=8765, show_default=True, type=int)
def dashboard_cmd(project: str, report_dir: str | None, serve: bool, port: int) -> None:
    """Generate or serve the local AgentDiff dashboard for a run."""
    root = Path(project).resolve()
    selected = Path(report_dir).resolve() if report_dir else latest_report_dir(root)
    if selected is None:
        console.print("[red]No report directory found. Run agentdiff compare first.[/red]")
        raise SystemExit(1)

    dashboard_path = write_dashboard(selected)
    summary = summarize_report(selected)
    console.print(f"[green]Dashboard written[/green] → {dashboard_path}")
    console.print(
        f"Events: {sum((summary.get('counts', {}).get('events') or {}).values())}; "
        f"trajectories: {sum((summary.get('counts', {}).get('trajectories') or {}).values())}"
    )

    if serve:
        handler = partial(SimpleHTTPRequestHandler, directory=str(selected))
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        console.print(f"[bold]Serving[/bold] http://127.0.0.1:{port}/dashboard.html")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped dashboard server.[/dim]")

import time
from pathlib import Path

import click
from rich.console import Console

from agentdiff.cli.compare import compare_cmd
from agentdiff.dashboard import latest_report_dir, summarize_report, write_dashboard

console = Console()


@click.command("monitor")
@click.pass_context
@click.option("--project", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--interval", default=300, show_default=True, type=int)
@click.option("--once", is_flag=True, help="Run one monitoring iteration and exit.")
@click.option("--run-compare", is_flag=True, help="Run agentdiff compare each iteration.")
@click.option("--baseline", default="auto")
@click.option("--candidate", default="working")
@click.option("--samples", type=int, default=None)
def monitor_cmd(
    ctx: click.Context,
    project: str,
    interval: int,
    once: bool,
    run_compare: bool,
    baseline: str,
    candidate: str,
    samples: int | None,
) -> None:
    """Local monitoring loop for repeated compare runs or latest report health."""
    while True:
        if run_compare:
            ctx.invoke(
                compare_cmd,
                baseline=baseline,
                candidate=candidate,
                test_cases_path=None,
                samples=samples,
                workers=None,
                output_dir=None,
                project=project,
                install_deps=None,
                max_failure_rate=None,
            )
        _print_latest(Path(project).resolve())
        if once:
            return
        time.sleep(max(interval, 1))


def _print_latest(root: Path) -> None:
    report_dir = latest_report_dir(root)
    if report_dir is None:
        console.print("[yellow]No reports yet.[/yellow]")
        return
    dashboard_path = write_dashboard(report_dir)
    summary = summarize_report(report_dir)
    meta = summary.get("metadata", {})
    counts = summary.get("counts", {})
    console.print(
        f"[bold]{meta.get('timestamp', report_dir.name)}[/bold] "
        f"baseline={meta.get('baseline_ref', 'n/a')} "
        f"candidate={meta.get('candidate_ref', 'n/a')} "
        f"events={sum((counts.get('events') or {}).values())} "
        f"dashboard={dashboard_path}"
    )

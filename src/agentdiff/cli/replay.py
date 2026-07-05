from datetime import datetime
from pathlib import Path

import click
from pydantic import ValidationError
from rich.console import Console

from agentdiff.cli.compare import HermeticSampleError, _load_test_cases, run_hermetic_sample
from agentdiff.config import load_config

console = Console()


@click.command("replay")
@click.option(
    "--cassette",
    "cassette_path",
    required=True,
    help="HTTP cassette path to replay against (recorded via "
    "`agentdiff ci run --cassette-mode record`).",
)
@click.option(
    "--report-dir",
    "report_dir",
    default=None,
    help="Directory to write the replay report to (defaults to a fresh "
    ".agentdiff/replay/<timestamp> directory).",
)
@click.option("--samples", type=int, default=None, help="Samples per test case (defaults to config).")
@click.option("--project", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--test-cases", "test_cases_path", default=None, help="Path to test_cases.yaml.")
def replay_cmd(
    cassette_path: str,
    report_dir: str | None,
    samples: int | None,
    project: str,
    test_cases_path: str | None,
) -> None:
    """Deterministically re-run the runner against a recorded HTTP cassette.

    No live network calls are made: every request must already be present
    in the cassette, or the run fails loud naming the missing request.
    """
    root = Path(project).resolve()

    try:
        config = load_config(root)
    except ValidationError as exc:
        console.print(f"[red]Invalid .agentdiff/config.yaml: {exc}[/red]")
        raise SystemExit(1)

    if not config.runner.module:
        console.print("[red]config.yaml is missing runner.module — run `agentdiff init` first.[/red]")
        raise SystemExit(1)

    test_cases = _load_test_cases(root, test_cases_path)
    if not test_cases:
        console.print("[red]No test cases found in test_cases.yaml.[/red]")
        raise SystemExit(1)

    out = Path(report_dir) if report_dir else root / ".agentdiff" / "replay" / _timestamp()
    out.mkdir(parents=True, exist_ok=True)
    trajectories_path = out / "trajectories.jsonl"

    console.print(f"[bold]Replaying[/bold] cassette: {cassette_path}")
    try:
        run_hermetic_sample(
            root=root,
            config=config,
            test_cases=test_cases,
            output_path=trajectories_path,
            version_tag="candidate",
            samples_per_case=samples,
            cassette_path=cassette_path,
            cassette_mode="replay",
        )
    except HermeticSampleError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)

    console.print(f"\n[green]Replay trajectories written[/green] → {trajectories_path}")


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")

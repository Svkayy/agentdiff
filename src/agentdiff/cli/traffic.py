from pathlib import Path

import click
import yaml
from rich.console import Console

from agentdiff.traffic import discover_test_cases

console = Console()


@click.group("traffic")
def traffic_cmd() -> None:
    """Discover replayable test cases from existing user traffic samples."""


@traffic_cmd.command("discover")
@click.option(
    "--from",
    "source",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="JSONL, JSON, CSV, or text file containing user requests.",
)
@click.option(
    "--output",
    default=".agentdiff/test_cases.yaml",
    type=click.Path(dir_okay=False),
    help="Where to write AgentDiff test cases.",
)
@click.option("--max-cases", default=25, show_default=True, type=int)
@click.option("--merge/--replace", default=True, help="Merge into existing output when present.")
def discover_cmd(source: str, output: str, max_cases: int, merge: bool) -> None:
    """Infer test_cases.yaml entries from real traffic without persona authoring."""
    cases = discover_test_cases(Path(source), max_cases=max_cases)
    if not cases:
        console.print("[yellow]No usable user-request rows were discovered.[/yellow]")
        raise SystemExit(1)

    out = Path(output)
    existing = []
    if merge and out.exists():
        data = yaml.safe_load(out.read_text(encoding="utf-8")) or {}
        existing = data.get("test_cases", [])

    merged = _merge_cases(existing, cases)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump({"test_cases": merged}, sort_keys=False), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {len(merged)} test case(s) → {out}")


def _merge_cases(existing: list[dict], discovered: list[dict]) -> list[dict]:
    seen = {case.get("id") for case in existing}
    out = list(existing)
    for case in discovered:
        if case.get("id") in seen:
            continue
        out.append(case)
    return out

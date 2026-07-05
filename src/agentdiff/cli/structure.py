from pathlib import Path

import click
from rich.console import Console

from agentdiff.cli.init import infer_structure
from agentdiff.structure import structure_yaml
from agentdiff.structure.structure_yaml import StructureDoc

console = Console()


@click.command("structure")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--llm",
    is_flag=True,
    default=False,
    help="Refine classification with an LLM call (requires ANTHROPIC_API_KEY).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the added/removed/kept summary without writing structure.yaml.",
)
def structure_cmd(path: str, llm: bool, dry_run: bool) -> None:
    """Refresh .agentdiff/structure.yaml, preserving user-edited display names.

    Re-runs the same inference `agentdiff init` uses, then merges the fresh
    scan into the existing structure.yaml (matched by file:qualname) so
    manually-edited display names/roles for still-present functions survive.
    New functions are added and vanished ones are dropped.
    """
    root = Path(path).resolve()

    existing = structure_yaml.load(root) or StructureDoc()

    console.print(f"[bold]Scanning[/bold] {root}")
    fresh = infer_structure(root, llm=llm)

    merged, diff = structure_yaml.merge_structures(existing, fresh)

    _print_diff(diff, dry_run=dry_run)

    if dry_run:
        console.print("\n[yellow]Dry run[/yellow] — structure.yaml was not written.")
        return

    out_path = structure_yaml.save(merged, root)
    console.print(f"\n[green]Wrote[/green] {out_path.relative_to(root)}")


def _print_diff(diff: structure_yaml.StructureDiff, dry_run: bool) -> None:
    prefix = "[yellow]Would[/yellow]" if dry_run else "[bold]Result[/bold]"

    if diff.added:
        console.print(f"{prefix} added ({len(diff.added)}):")
        for key in diff.added:
            console.print(f"  [green]+[/green] {key}")
    else:
        console.print(f"{prefix} added: none")

    if diff.removed:
        console.print(f"{prefix} removed ({len(diff.removed)}):")
        for key in diff.removed:
            console.print(f"  [red]-[/red] {key}")
    else:
        console.print(f"{prefix} removed: none")

    console.print(f"Kept ({len(diff.kept)}) unchanged.")

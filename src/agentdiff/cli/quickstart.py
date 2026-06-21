from pathlib import Path

import click
import yaml
from rich.console import Console

from agentdiff.structure.ast_walker import CandidateFunction, walk_project
from agentdiff.structure.heuristic_classifier import classify
from agentdiff.structure import structure_yaml

console = Console()


@click.command("quickstart")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing .agentdiff config files.")
def quickstart_cmd(path: str, force: bool) -> None:
    """Create a runnable AgentDiff setup from project structure heuristics."""
    root = Path(path).resolve()
    ad_dir = root / ".agentdiff"
    ad_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold]Quickstarting[/bold] {root}")
    candidates = walk_project(root)
    if not candidates:
        console.print("[yellow]No Python functions found. Add a Runner, then re-run quickstart.[/yellow]")
        raise SystemExit(0)

    doc = classify(candidates)
    structure_yaml.save(doc, root)
    console.print("[green]Wrote[/green] .agentdiff/structure.yaml")

    runner = _infer_runner(root, doc, candidates)
    if runner is None:
        runner = _write_runner_template(root, force=force)
        console.print("[yellow]Could not infer a safe Runner; wrote agentdiff_runner.py template.[/yellow]")
    else:
        console.print(
            f"[green]Inferred Runner[/green] {runner['module']}.{runner['callable']} "
            f"from {runner['source']}"
        )

    _write_yaml(ad_dir / "config.yaml", _config_doc(runner), force)
    _write_yaml(ad_dir / "test_cases.yaml", _test_cases_doc(candidates), force)
    _write_yaml(ad_dir / "providers.yaml", {"providers": []}, force)

    console.print("\n[bold]Next:[/bold]")
    console.print("  1. Review .agentdiff/test_cases.yaml and add one real input.")
    console.print("  2. Run [cyan]agentdiff doctor --project .[/cyan]")
    console.print("  3. Run [cyan]agentdiff compare --baseline auto --samples 3[/cyan]")


def _infer_runner(root: Path, doc, candidates: list[CandidateFunction]) -> dict | None:
    by_key = {(c.file, c.name): c for c in candidates}
    ordered: list[tuple[str, str, str, int]] = []
    for entry in doc.entry_points:
        ordered.append((entry.file, entry.function, "entry_point", entry.line))
    for agent in doc.agents:
        ordered.append((agent.file, agent.function, "agent", agent.line))

    for file, fn_name, source, line in ordered:
        candidate = by_key.get((file, fn_name))
        if candidate is None or candidate.class_name is not None:
            continue
        module = _module_path(root, file)
        if module is None:
            continue
        return {
            "module": module,
            "callable": fn_name,
            "source": f"{source} {file}:{line}",
        }
    return None


def _module_path(root: Path, rel_file: str) -> str | None:
    path = Path(rel_file)
    if path.suffix != ".py" or path.name == "__init__.py":
        return None
    parts = list(path.with_suffix("").parts)
    if not parts:
        return None
    # Only infer nested modules for package directories. This avoids generating
    # import paths that work from a shell but fail under normal Python imports.
    for i in range(1, len(parts)):
        package_dir = root.joinpath(*parts[:i])
        if not (package_dir / "__init__.py").exists():
            return None
    return ".".join(parts)


def _write_runner_template(root: Path, *, force: bool) -> dict:
    target = root / "agentdiff_runner.py"
    if force or not target.exists():
        target.write_text(
            "\"\"\"AgentDiff Runner template.\n\n"
            "Replace this with one production-style invocation of your agent.\n"
            "\"\"\"\n\n"
            "def run(input_data: dict):\n"
            "    raise NotImplementedError(\n"
            "        \"Wire agentdiff_runner.run(input_data) to call your agent once.\"\n"
            "    )\n",
            encoding="utf-8",
        )
    return {"module": "agentdiff_runner", "callable": "run", "source": "template"}


def _config_doc(runner: dict) -> dict:
    return {
        "runner": {
            "module": runner["module"],
            "callable": runner["callable"],
        },
        "samples_per_case": 10,
        "llm_provider": "anthropic",
        "sampling": {
            "install_deps": True,
            "max_failure_rate": 0.0,
            "workers": 1,
        },
        "thresholds": {
            "agent_invocation_rate": {"warn": 0.20, "fail": 0.50},
            "tool_usage_avg": {"warn": 0.50, "fail": 1.00},
        },
        "capture": {
            "httpx": True,
            "requests": True,
            "aiohttp": True,
            "grpc": True,
            "openai_sdk": True,
            "anthropic_sdk": True,
            "mcp": True,
            "langgraph": True,
            "crewai": True,
            "autogen": True,
            "llamaindex": True,
        },
    }


def _test_cases_doc(candidates: list[CandidateFunction]) -> dict:
    tags = sorted(
        {
            "async" if c.is_async else "sync"
            for c in candidates
            if c.calls_llm or c.module_imports_llm_sdk
        }
    )
    return {
        "test_cases": [
            {
                "id": "smoke_realistic_input",
                "input": {
                    "query": "Replace this with a real user request for your agent.",
                    "context": {},
                },
                "tags": tags or ["smoke"],
            }
        ]
    }


def _write_yaml(path: Path, data: dict, force: bool) -> None:
    if path.exists() and not force:
        console.print(f"[dim]Kept existing[/dim] {path.relative_to(path.parents[1])}")
        return
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {path.relative_to(path.parents[1])}")

import importlib
import importlib.util
import os
import sys
from pathlib import Path

import click
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from agentdiff.cli.compare import git_validation_error, resolve_baseline
from agentdiff.cli.init import autoload_hook_installed, autoload_pth_path
from agentdiff.config import config_path, load_config
from agentdiff.structure import structure_yaml

console = Console()


@click.command("doctor")
@click.option("--project", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--baseline", default="auto", help="Baseline ref to validate for compare.")
def doctor_cmd(project: str, baseline: str) -> None:
    """Validate project setup before running AgentDiff."""
    root = Path(project).resolve()
    checks: list[tuple[str, str, str]] = []

    cfg = None
    cfg_file = config_path(root)
    if cfg_file.exists():
        try:
            cfg = load_config(root)
            checks.append(("config.yaml", "pass", "valid"))
        except (ValidationError, yaml.YAMLError, OSError) as e:
            checks.append(("config.yaml", "fail", f"{type(e).__name__}: {e}"))
    else:
        checks.append(("config.yaml", "fail", "missing; run `agentdiff init`"))

    structure = structure_yaml.load(root)
    if structure is None:
        checks.append(("structure.yaml", "fail", "missing; run `agentdiff init`"))
    else:
        checks.append(("structure.yaml", "pass", f"{len(structure.agents)} agent(s), {len(structure.tools)} tool(s)"))

    test_cases = _load_test_cases(root)
    if test_cases:
        checks.append(("test_cases.yaml", "pass", f"{len(test_cases)} case(s)"))
    else:
        checks.append(("test_cases.yaml", "fail", "missing or empty"))

    if cfg is not None and cfg.runner.module:
        checks.append(_runner_check(root, cfg.runner.module, cfg.runner.callable))
    else:
        checks.append(("runner", "fail", "runner.module is not configured"))

    baseline_ref, baseline_label, smoke_mode = resolve_baseline(root, baseline)
    git_error = git_validation_error(root, baseline_ref, "working")
    if git_error:
        checks.append(("git baseline", "fail", git_error))
    elif smoke_mode:
        checks.append(("git baseline", "warn", "auto resolved to working-tree smoke mode"))
    else:
        checks.append(("git baseline", "pass", baseline_label))

    hook_status = "installed" if autoload_hook_installed() else f"not installed ({autoload_pth_path()})"
    checks.append(("autoload hook", "warn", hook_status))

    if cfg is not None:
        key_env = "ANTHROPIC_API_KEY" if cfg.llm_provider == "anthropic" else "OPENAI_API_KEY"
        checks.append((key_env, "pass" if os.environ.get(key_env) else "warn", "set" if os.environ.get(key_env) else "not set; judge/explainer skipped"))

    checks.append(("sentence-transformers", _optional_dep_status("sentence_transformers"), "install `agentdiff[embeddings]` for semantic output eval"))
    checks.append(("openai SDK", _optional_dep_status("openai"), "install `agentdiff[openai]` for SDK enrichment"))
    checks.append(("anthropic SDK", _optional_dep_status("anthropic"), "install `agentdiff[anthropic]` for SDK enrichment"))
    checks.append(("mcp SDK", _optional_dep_status("mcp"), "install `agentdiff[mcp]` for MCP enrichment"))
    checks.append(("aiohttp", _optional_dep_status("aiohttp"), "install `agentdiff[aiohttp]` for aiohttp capture"))
    checks.append(("grpcio", _optional_dep_status("grpc"), "install `agentdiff[grpc]` for gRPC spans"))
    checks.append(("LangGraph", _optional_dep_status("langgraph"), "install `agentdiff[frameworks]` for LangGraph node/edge spans"))
    checks.append(("CrewAI", _optional_dep_status("crewai"), "install `agentdiff[frameworks]` for CrewAI spans"))
    checks.append(("AutoGen", _optional_dep_status("autogen"), "install `agentdiff[frameworks]` for AutoGen speaker turns"))
    checks.append(("LlamaIndex", _optional_dep_status("llama_index.core"), "install `agentdiff[frameworks]` for retriever/router spans"))

    _print_checks(checks)
    if any(status == "fail" for _, status, _ in checks):
        raise SystemExit(1)


def _load_test_cases(root: Path) -> list[dict]:
    path = root / ".agentdiff" / "test_cases.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("test_cases", []) or []


def _runner_check(root: Path, module: str, callable_name: str) -> tuple[str, str, str]:
    root_str = str(root)
    old_path = list(sys.path)
    try:
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        mod = importlib.import_module(module)
        runner = getattr(mod, callable_name, None)
        if callable(runner):
            return ("runner", "pass", f"{module}.{callable_name}")
        return ("runner", "fail", f"{module}.{callable_name} is not callable")
    except Exception as e:  # noqa: BLE001
        return ("runner", "fail", f"{type(e).__name__}: {e}")
    finally:
        sys.path[:] = old_path


def _optional_dep_status(module: str) -> str:
    try:
        return "pass" if importlib.util.find_spec(module) is not None else "warn"
    except ModuleNotFoundError:
        return "warn"


def _print_checks(checks: list[tuple[str, str, str]]) -> None:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    colors = {"pass": "green", "warn": "yellow", "fail": "red"}
    for name, status, detail in checks:
        table.add_row(name, f"[{colors[status]}]{status.upper()}[/{colors[status]}]", detail)
    console.print(table)

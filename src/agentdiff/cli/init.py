import os
import sysconfig
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from agentdiff.structure.ast_walker import CandidateFunction, walk_project
from agentdiff.structure.heuristic_classifier import classify
from agentdiff.structure import structure_yaml
from agentdiff.structure.structure_yaml import StructureDoc

console = Console()

_AGENTDIFF_DIR = ".agentdiff"
_PTH_NAME = "agentdiff_autoload.pth"
_PTH_LINE = "import agentdiff; agentdiff.install()\n"

_DEFAULT_CONFIG_YAML = """\
# AgentDiff configuration.
# Point `runner` at the callable that fires one observable invocation of your
# agent. See docs/recipes/ for the four supported trigger shapes.
runner:
  module: my_app.runner   # any importable module
  callable: run           # a function, or a class instance with __call__
samples_per_case: 20
llm_provider: anthropic   # anthropic | openai — used by AgentDiff's own judge/explainer

sampling:
  install_deps: true      # install deps before sampling a git checkout
  max_failure_rate: 0.0   # fail compare if more than this fraction of samples crash
  workers: 1              # local concurrency for sampling runs

thresholds:
  agent_invocation_rate:
    warn: 0.20
    fail: 0.50
  tool_usage_avg:
    warn: 0.50
    fail: 1.00

capture:
  httpx: true
  requests: true
  aiohttp: true
  grpc: true
  openai_sdk: true
  anthropic_sdk: true
  mcp: true
  langgraph: true
  crewai: true
  autogen: true
  llamaindex: true
"""

_DEFAULT_TEST_CASES_YAML = """\
# Each test case's `input` is an opaque dict passed verbatim to your Runner.
test_cases:
  - id: example_case
    input:
      query: "Replace this with a real input for your agent."
    tags: [example]
"""

_DEFAULT_PROVIDERS_YAML = """\
# Register custom provider URL patterns here to get canonical parsing for
# providers AgentDiff doesn't ship a parser for. Example:
# providers:
#   - name: my_provider
#     url_pattern: "^https://api\\\\.myprovider\\\\.com/v1/chat"
providers: []
"""


@click.command("init")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--llm",
    is_flag=True,
    default=False,
    help="Refine classification with an LLM call (requires ANTHROPIC_API_KEY).",
)
@click.option(
    "--install-hook/--no-install-hook",
    default=False,
    help="Install the venv autoload hook so capture is automatic (default: off).",
)
def init_cmd(path: str, llm: bool, install_hook: bool) -> None:
    """Scan PATH and write .agentdiff/ (structure.yaml + config scaffolding)."""
    root = Path(path).resolve()

    console.print(f"[bold]Scanning[/bold] {root}")
    candidates = walk_project(root)

    if not candidates:
        console.print("[yellow]No Python functions found.[/yellow]")
        raise SystemExit(0)

    console.print(f"Found [bold]{len(candidates)}[/bold] candidate function(s)")

    doc = classify(candidates)

    if llm:
        doc = _refine_with_llm(doc, candidates)

    _print_summary(doc)

    out_path = structure_yaml.save(doc, root)
    console.print(f"\n[green]Wrote[/green] {out_path.relative_to(root)}")

    created = _write_default_configs(root)
    for rel in created:
        console.print(f"[green]Wrote[/green] {rel}")
    skipped = {"config.yaml", "test_cases.yaml", "providers.yaml"} - {Path(c).name for c in created}
    for name in sorted(skipped):
        console.print(f"[dim]Kept existing[/dim] {_AGENTDIFF_DIR}/{name}")

    if install_hook:
        pth = install_autoload_hook()
        if pth is not None:
            console.print(f"[green]Installed[/green] capture hook → {pth}")
        else:
            console.print(
                "[yellow]Could not install the autoload hook "
        "(call agentdiff.install() manually or run `agentdiff hook install`).[/yellow]"
            )

    console.print("\n[bold]Next:[/bold] edit .agentdiff/config.yaml and test_cases.yaml, "
                  "then run [cyan]agentdiff compare --baseline auto[/cyan]")


# ---------------------------------------------------------------------------
# Shared inference (reused by `agentdiff structure`)
# ---------------------------------------------------------------------------

def infer_structure(root: Path, llm: bool = False) -> StructureDoc:
    """Scan `root` and classify its functions into a StructureDoc.

    This is the same inference path `agentdiff init` uses, extracted so
    `agentdiff structure` can re-run it without duplicating the walk+classify
    (+ optional LLM refinement) logic.
    """
    candidates = walk_project(root)
    doc = classify(candidates)
    if llm:
        doc = _refine_with_llm(doc, candidates)
    return doc


def _refine_with_llm(doc: StructureDoc, candidates: list[CandidateFunction]) -> StructureDoc:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        console.print("[red]--llm requires ANTHROPIC_API_KEY to be set.[/red]")
        raise SystemExit(1)
    console.print("[dim]Running LLM refinement pass…[/dim]")
    from agentdiff.structure.llm_classifier import refine
    return refine(doc, candidates, api_key)


# ---------------------------------------------------------------------------
# Config scaffolding
# ---------------------------------------------------------------------------

def _write_default_configs(root: Path) -> list[str]:
    """Write default config files that don't already exist. Returns relative paths written."""
    ad_dir = root / _AGENTDIFF_DIR
    ad_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "config.yaml": _DEFAULT_CONFIG_YAML,
        "test_cases.yaml": _DEFAULT_TEST_CASES_YAML,
        "providers.yaml": _DEFAULT_PROVIDERS_YAML,
    }
    written: list[str] = []
    for name, content in files.items():
        target = ad_dir / name
        if target.exists():
            continue  # never clobber user edits
        target.write_text(content, encoding="utf-8")
        written.append(f"{_AGENTDIFF_DIR}/{name}")
    return written


# ---------------------------------------------------------------------------
# Autoload hook
# ---------------------------------------------------------------------------

def autoload_pth_path(site_packages: Path | None = None) -> Path:
    if site_packages is None:
        site_packages = Path(sysconfig.get_paths()["purelib"])
    return site_packages / _PTH_NAME


def install_autoload_hook(site_packages: Path | None = None) -> Path | None:
    """Write a .pth file into site-packages so `agentdiff.install()` runs at startup.

    The line is idempotent and zero-overhead when no Tracer is active. Returns the
    path written, or None on failure (e.g., read-only site-packages).
    """
    try:
        pth = autoload_pth_path(site_packages)
        pth.parent.mkdir(parents=True, exist_ok=True)
        pth.write_text(_PTH_LINE, encoding="utf-8")
        return pth
    except Exception:
        return None


def autoload_hook_installed(site_packages: Path | None = None) -> bool:
    """Return whether AgentDiff's startup hook exists and contains our line."""
    try:
        pth = autoload_pth_path(site_packages)
        return pth.exists() and _PTH_LINE.strip() in pth.read_text(encoding="utf-8")
    except Exception:
        return False


def uninstall_autoload_hook(site_packages: Path | None = None) -> bool:
    """Remove AgentDiff's startup hook. Returns True if a hook was removed."""
    try:
        pth = autoload_pth_path(site_packages)
        if not pth.exists():
            return False
        pth.unlink()
        return True
    except Exception:
        return False


def _print_summary(doc) -> None:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Function")
    table.add_column("Role")
    table.add_column("File")

    for a in doc.agents:
        table.add_row(a.function, "[cyan]agent[/cyan]", f"{a.file}:{a.line}")
    for t in doc.tools:
        table.add_row(t.function, "[green]tool[/green]", f"{t.file}:{t.line}")
    for e in doc.entry_points:
        table.add_row(e.function, "[yellow]entry_point[/yellow]", f"{e.file}:{e.line}")

    console.print(table)

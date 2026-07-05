import importlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import click
import yaml
from pydantic import ValidationError
from rich.console import Console

from agentdiff import compare as compare_engine
from agentdiff import output_eval, report, sampling, storage
from agentdiff.capture.cassette import CassetteMissError
from agentdiff.config import AgentDiffConfig, load_config, load_raw_config, thresholds_for_compare
from agentdiff.dashboard import write_dashboard
from agentdiff.structure import structure_yaml

console = Console()


@click.command("compare")
@click.option(
    "--baseline",
    default="auto",
    help="Git ref for baseline, or 'auto' to infer one and fall back to a smoke run.",
)
@click.option("--candidate", default="working", help="Git ref, or 'working' for the working tree.")
@click.option("--test-cases", "test_cases_path", default=None, help="Path to test_cases.yaml.")
@click.option("--samples", type=int, default=None, help="Samples per test case per side.")
@click.option("--workers", type=int, default=None, help="Concurrent local sampling workers.")
@click.option("--output", "output_dir", default=None, help="Report output directory.")
@click.option("--project", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--install-deps/--no-install-deps",
    default=None,
    help="Install dependencies before sampling git checkouts (defaults to config).",
)
@click.option(
    "--max-failure-rate",
    type=float,
    default=None,
    help="Fail if a side exceeds this sample failure rate (defaults to config).",
)
def compare_cmd(
    baseline: str,
    candidate: str,
    test_cases_path: str | None,
    samples: int | None,
    workers: int | None,
    output_dir: str | None,
    project: str,
    install_deps: bool | None,
    max_failure_rate: float | None,
) -> None:
    """Run behavioral comparison between baseline and candidate."""
    root = Path(project).resolve()

    try:
        config = load_config(root)
    except ValidationError as e:
        console.print(f"[red]Invalid .agentdiff/config.yaml: {e}[/red]")
        raise SystemExit(1)

    runner_module = config.runner.module
    runner_callable = config.runner.callable
    if not runner_module:
        console.print("[red]config.yaml is missing runner.module — run `agentdiff init` first.[/red]")
        raise SystemExit(1)

    samples_per_case = samples or config.samples_per_case
    worker_count = workers or config.sampling.workers
    llm_provider = config.llm_provider
    should_install_deps = config.sampling.install_deps if install_deps is None else install_deps
    allowed_failure_rate = (
        config.sampling.max_failure_rate
        if max_failure_rate is None else max_failure_rate
    )
    if not 0 <= allowed_failure_rate <= 1:
        console.print("[red]--max-failure-rate must be between 0 and 1.[/red]")
        raise SystemExit(1)
    if worker_count <= 0:
        console.print("[red]--workers must be positive.[/red]")
        raise SystemExit(1)

    structure = structure_yaml.load(root)
    if structure is None:
        console.print("[red]No .agentdiff/structure.yaml — run `agentdiff init` first.[/red]")
        raise SystemExit(1)

    test_cases = _load_test_cases(root, test_cases_path)
    if not test_cases:
        console.print("[red]No test cases found in test_cases.yaml.[/red]")
        raise SystemExit(1)

    runner_error = validate_runner_importable(root, runner_module, runner_callable)
    if runner_error:
        console.print(f"[red]{runner_error}[/red]")
        raise SystemExit(1)

    from agentdiff.capture.http.redact import set_active_redaction_config
    set_active_redaction_config(config.capture.redaction)

    baseline_ref, baseline_label, smoke_mode = resolve_baseline(root, baseline)
    git_error = git_validation_error(root, baseline_ref, candidate)
    if git_error:
        console.print(f"[red]{git_error}[/red]")
        raise SystemExit(1)
    if smoke_mode:
        console.print(
            "[yellow]No git baseline available; running a working-tree smoke comparison. "
            "Commit your project or pass --baseline REF for real regression detection.[/yellow]"
        )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = Path(output_dir) if output_dir else root / ".agentdiff" / "reports" / timestamp
    out.mkdir(parents=True, exist_ok=True)
    baseline_jsonl = out / "baseline_trajectories.jsonl"
    candidate_jsonl = out / "candidate_trajectories.jsonl"

    # --- Sample both sides ------------------------------------------------
    candidate_ref = None if candidate == "working" else candidate
    for tag, ref, jsonl in (
        ("baseline", baseline_ref, baseline_jsonl),
        ("candidate", candidate_ref, candidate_jsonl),
    ):
        console.print(f"[bold]Sampling {tag}[/bold] (ref: {ref or 'working'})")
        try:
            sampling.sample_for_side(
                git_ref=ref,
                runner_module=runner_module,
                runner_callable=runner_callable,
                test_cases=test_cases,
                samples_per_case=samples_per_case,
                version_tag=tag,  # type: ignore[arg-type]
                output_path=jsonl,
                repo_root=root,
                install_deps=should_install_deps,
                capture=config.capture.model_dump(),
                workers=worker_count,
                timeout_seconds=config.sampling.timeout_seconds,
                retries=config.sampling.retries,
                retry_backoff_seconds=config.sampling.retry_backoff_seconds,
                redaction_config=config.capture.redaction,
            )
        except Exception as e:  # import failure, git failure, runner setup crash
            console.print(f"[red]{tag.capitalize()} sampling failed: {type(e).__name__}: {e}[/red]")
            raise SystemExit(1)

    # --- Load + compare ---------------------------------------------------
    baseline_set = storage.load_trajectory_set(baseline_jsonl, "baseline")
    candidate_set = storage.load_trajectory_set(candidate_jsonl, "candidate")

    # An empty side means sampling itself failed (bad runner module, crash in the
    # checkout subprocess, …). Comparing against nothing would render an
    # all-PASS report that looks like a clean bill of health — refuse instead.
    for tag, ts in (("baseline", baseline_set), ("candidate", candidate_set)):
        _validate_trajectory_quality(tag, ts, allowed_failure_rate)

    test_case_ids = [tc["id"] for tc in test_cases]
    comparison = compare_engine.compare_all(
        baseline_set,
        candidate_set,
        structure,
        test_case_ids,
        thresholds=thresholds_for_compare(config),
        stats_config=config.stats,
    )

    # --- Output eval (judge optional) -------------------------------------
    console.print("[bold]Evaluating outputs[/bold]")
    llm_client = _make_llm_client(llm_provider)
    output_evals = []
    for tc_id in test_case_ids:
        b_out = [t.final_output or "" for t in baseline_set.for_test_case(tc_id)]
        c_out = [t.final_output or "" for t in candidate_set.for_test_case(tc_id)]
        output_evals.append(
            output_eval.evaluate_output(tc_id, b_out, c_out, llm_client=llm_client)
        )

    # --- Causal attribution ----------------------------------------------
    console.print("[bold]Attributing behavioral deltas[/bold]")
    attribution = None
    if not smoke_mode and baseline_ref is not None:
        from agentdiff.attribution import engine as attribution_engine
        attribution = attribution_engine.attribute(
            comparison=comparison,
            structure=structure,
            baseline_trajectories=baseline_set.trajectories,
            candidate_trajectories=candidate_set.trajectories,
            repo_root=root,
            baseline_ref=baseline_ref,
            candidate_ref=candidate_ref,
            llm_client=llm_client or attribution_engine.AUTO_LLM_EXPLAINER,
        )
    else:
        console.print("[dim]Skipping attribution for working-tree smoke comparison.[/dim]")

    # --- Render report ----------------------------------------------------
    meta = {
        "run_id": timestamp,
        "timestamp": timestamp,
        "baseline_ref": baseline_label,
        "baseline_arg": baseline,
        "baseline_sample_ref": baseline_ref or "working",
        "candidate_ref": candidate,
        "smoke_mode": smoke_mode,
        "samples_per_case": samples_per_case,
        "workers": worker_count,
        "install_deps": should_install_deps,
        "max_failure_rate": allowed_failure_rate,
        "thresholds": thresholds_for_compare(config),
        "capture": config.capture.model_dump(),
        "baseline_trajectories": len(baseline_set.trajectories),
        "candidate_trajectories": len(candidate_set.trajectories),
        "baseline_failed": _failed_count(baseline_set),
        "candidate_failed": _failed_count(candidate_set),
    }
    sqlite_path = storage.write_run_store(
        out / "agentdiff.sqlite",
        metadata=meta,
        baseline_set=baseline_set,
        candidate_set=candidate_set,
        comparison=comparison,
        output_evals=output_evals,
        attribution=attribution,
    )
    meta["sqlite_store"] = str(sqlite_path)
    md = report.render_report(comparison, output_evals, meta, attribution)
    report_path = out / "report.md"
    report_path.write_text(md, encoding="utf-8")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    dashboard_path = write_dashboard(out)

    console.print(f"\n[green]Report written[/green] → {report_path}")
    console.print(f"[green]Dashboard written[/green] → {dashboard_path}")
    console.print(f"Overall verdict: [bold]{comparison.overall_verdict.upper()}[/bold]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_baseline(root: Path, requested: str) -> tuple[str | None, str, bool]:
    """Return (git_ref_for_sampling, display_label, smoke_mode)."""
    if requested != "auto":
        return requested, requested, False

    if not _git_ok(root, ["rev-parse", "--is-inside-work-tree"]):
        return None, "working (smoke)", True

    for ref in ("origin/main", "main", "master", "HEAD~1", "HEAD"):
        if _git_ok(root, ["rev-parse", "--verify", f"{ref}^{{commit}}"]):
            return ref, ref, False
    return None, "working (smoke)", True


def git_validation_error(root: Path, baseline: str | None, candidate: str) -> str | None:
    """Return a clear error string if git can't satisfy the requested refs, else None.

    Catches the common foot-guns up front (not a repo / unknown ref) so the user
    gets a helpful message instead of a raw traceback from deep in sampling.
    """
    if baseline is None and candidate == "working":
        return None
    if not _git_ok(root, ["rev-parse", "--is-inside-work-tree"]):
        return (
            f"{root} is not a git repository (or git is not installed). "
            "Pass --baseline auto for a working-tree smoke run, or run inside "
            "your project's git repo for real regression detection."
        )
    if baseline is not None and not _git_ok(root, ["rev-parse", "--verify", f"{baseline}^{{commit}}"]):
        return (
            f"baseline ref '{baseline}' could not be resolved. "
            "Pass an existing branch/tag/commit via --baseline."
        )
    if candidate != "working" and not _git_ok(root, ["rev-parse", "--verify", f"{candidate}^{{commit}}"]):
        return (
            f"candidate ref '{candidate}' could not be resolved. "
            "Pass an existing ref or 'working' via --candidate."
        )
    return None


def validate_runner_importable(root: Path, module: str, callable_name: str) -> str | None:
    """Return an error string if the runner can't be imported, else None.

    Fails fast before sampling: a bad runner module/callable would otherwise
    only surface deep inside the sampling loop (or, worse, inside a git
    checkout subprocess), producing a confusing empty-trajectories error.
    """
    root_str = str(root)
    old_path = list(sys.path)
    try:
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        try:
            mod = importlib.import_module(module)
        except Exception as e:  # noqa: BLE001 — surfaced to the user as a fast-fail message
            return f"Run 'agentdiff doctor' — could not import {module}: {type(e).__name__}: {e}"
        runner = getattr(mod, callable_name, None)
        if not callable(runner):
            return (
                f"Run 'agentdiff doctor' — could not import {module}: "
                f"{module}.{callable_name} is not callable"
            )
        return None
    finally:
        sys.path[:] = old_path


class HermeticSampleError(RuntimeError):
    """A clean, user-facing error raised by ``run_hermetic_sample``."""


def run_hermetic_sample(
    *,
    root: Path,
    config: "AgentDiffConfig",
    test_cases: list[dict],
    output_path: Path,
    version_tag: str = "candidate",
    samples_per_case: int | None = None,
    cassette_path: str | Path,
    cassette_mode: str = "replay",
    git_ref: str | None = None,
    install_deps: bool | None = None,
    workers: int | None = None,
) -> None:
    """Sample a runner against an HTTP cassette, deterministically.

    Shared by ``agentdiff ci run --tier hermetic`` and ``agentdiff replay``:
    both need "run this runner against a recorded cassette, with no live
    network calls" plumbing (validate the runner imports, apply redaction
    config, drive ``sampling.sample_for_side`` with the cassette wired
    through). ``git_ref=None`` (the default, and all ``replay`` ever passes)
    samples the working tree directly; ``ci run --tier hermetic`` passes its
    baseline/candidate refs so each side still gets its own git checkout.

    Raises ``HermeticSampleError`` with a clear, actionable message (instead
    of a raw traceback or an opaque failure-rate message) when the cassette
    file is missing or replay hits a request that was never recorded.
    """
    cassette_path = Path(cassette_path)
    if cassette_mode == "replay" and not cassette_path.exists():
        raise HermeticSampleError(f"cassette file not found: {cassette_path}")

    if git_ref is None:
        runner_error = validate_runner_importable(root, config.runner.module or "", config.runner.callable)
        if runner_error:
            raise HermeticSampleError(runner_error)

    from agentdiff.capture.http.redact import set_active_redaction_config
    set_active_redaction_config(config.capture.redaction)

    try:
        sampling.sample_for_side(
            git_ref=git_ref,
            runner_module=config.runner.module or "",
            runner_callable=config.runner.callable,
            test_cases=test_cases,
            samples_per_case=samples_per_case or config.samples_per_case,
            version_tag=version_tag,  # type: ignore[arg-type]
            output_path=output_path,
            repo_root=root,
            install_deps=config.sampling.install_deps if install_deps is None else install_deps,
            capture=config.capture.model_dump(),
            workers=config.sampling.workers if workers is None else workers,
            cassette_path=cassette_path,
            cassette_mode=cassette_mode,
            timeout_seconds=config.sampling.timeout_seconds,
            retries=config.sampling.retries,
            retry_backoff_seconds=config.sampling.retry_backoff_seconds,
            redaction_config=config.capture.redaction,
        )
    except CassetteMissError as exc:
        raise HermeticSampleError(_cassette_miss_message(exc)) from exc

    # A cassette miss doesn't propagate as an exception out of sample_for_side:
    # the sampling loop catches it (see sampling._run_one_sample_with_retry),
    # retries, then — on final failure — writes a "failed" trajectory carrying
    # the error message instead of raising, the same way any other runner
    # exception would be budgeted. Inspect what was written so a miss still
    # fails loud and names the request, rather than silently surfacing later
    # as an opaque "sample failure rate exceeded" message.
    written = storage.load_trajectory_set(output_path, version_tag)  # type: ignore[arg-type]
    for trajectory in written.trajectories:
        # sampling._run_one_sample_with_retry wraps the final exception as
        # f"{type(exc).__name__}: {exc}" (see sampling.py) before writing it
        # to the trajectory's error field. Anchor on that exact, deterministic
        # prefix rather than a bare substring match on "no cassette recording"
        # — a runner's own error could legitimately contain that phrase
        # without being a real cassette miss, and a bare substring match would
        # misreport it with the misleading re-record suggestion.
        if trajectory.error and trajectory.error.startswith("CassetteMissError:"):
            detail = trajectory.error[len("CassetteMissError:") :].strip()
            raise HermeticSampleError(_cassette_miss_message(detail))


def _cassette_miss_message(detail: object) -> str:
    return (
        f"{detail} — re-record the cassette with "
        "`agentdiff ci run --cassette-mode record`."
    )


def _git_ok(root: Path, args: list[str]) -> bool:
    try:
        subprocess.run(
            ["git", *args], cwd=root, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _load_config(root: Path) -> dict:
    return load_raw_config(root)


def _load_test_cases(root: Path, override: str | None) -> list[dict]:
    path = Path(override) if override else root / ".agentdiff" / "test_cases.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("test_cases", [])


def _make_llm_client(provider: str):
    """Construct an LLMClient if the matching API key is present; else None."""
    key_env = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    if not os.environ.get(key_env):
        console.print(
            f"[dim]{key_env} not set — skipping LLM judge, using semantic + length only.[/dim]"
        )
        return None
    from agentdiff.llm_client import LLMClient
    return LLMClient(provider=provider)


def _failed_count(trajectory_set) -> int:
    return sum(1 for t in trajectory_set.trajectories if t.status != "success")


def _validate_trajectory_quality(tag: str, trajectory_set, max_failure_rate: float) -> None:
    total = len(trajectory_set.trajectories)
    if total == 0:
        console.print(
            f"[red]No {tag} trajectories were captured — sampling failed. "
            f"Check .agentdiff/config.yaml and the errors above.[/red]"
        )
        raise SystemExit(1)
    failed = _failed_count(trajectory_set)
    failure_rate = failed / total
    if failure_rate > max_failure_rate:
        console.print(
            f"[red]{tag.capitalize()} sample failure rate {failure_rate:.0%} "
            f"({failed}/{total}) exceeded allowed max {max_failure_rate:.0%}.[/red]"
        )
        raise SystemExit(1)

"""Sampling engine: run a user's Runner N times per test case, per side.

Two execution modes:
  - In-place (working tree): import the Runner and loop in this process.
  - Git ref: ``git archive <ref> | tar -x`` into a temp dir, install its deps,
    and run the loop in a subprocess so the checked-out code wins on import.

The Runner contract (see docs/recipes) is ``Callable[[dict], dict | str | None]``.
"""
import json
import asyncio
import inspect
import subprocess
import sys
import tempfile
from contextlib import contextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from agentdiff.capture.tracer import Tracer


class SamplingError(RuntimeError):
    """A setup/subprocess failure prevented sampling from producing trajectories."""


def run_samples(
    runner_module: str,
    runner_callable: str,
    test_cases: list[dict[str, Any]],
    samples_per_case: int,
    version_tag: Literal["baseline", "candidate"],
    output_path: Path,
    structure_root: Path | None = None,
    progress: bool = True,
    workers: int = 1,
    cassette_path: str | Path | None = None,
    cassette_mode: str | None = None,
) -> int:
    """Run the sampling loop in the current process. Returns trajectories written.

    Importable from a subprocess so the checked-out code path reuses it.
    """
    # Honor custom provider patterns declared in .agentdiff/providers.yaml so
    # URL-keyed capture works for providers without a built-in parser.
    if structure_root is not None:
        from agentdiff.capture.http import provider_registry
        provider_registry.load_custom_providers(structure_root)

    runner = _load_runner(runner_module, runner_callable)
    output_path = Path(output_path)
    written = 0

    workers = max(1, workers)
    ctx = _cassette_context(cassette_path, cassette_mode)
    with ctx:
        if workers == 1:
            for tc in test_cases:
                tc_id = tc["id"]
                tc_input = tc.get("input", {})
                if progress:
                    print(f"  Sampling {samples_per_case} run(s) of '{tc_id}'...")
                for i in range(samples_per_case):
                    _run_one_sample(
                        runner=runner,
                        tc_id=tc_id,
                        tc_input=tc_input,
                        sample_index=i,
                        version_tag=version_tag,
                        output_path=output_path,
                        structure_root=structure_root,
                    )
                    written += 1
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = []
                for tc in test_cases:
                    tc_id = tc["id"]
                    tc_input = tc.get("input", {})
                    if progress:
                        print(
                            f"  Sampling {samples_per_case} run(s) of '{tc_id}' "
                            f"with {workers} worker(s)..."
                        )
                    for i in range(samples_per_case):
                        futures.append(
                            executor.submit(
                                _run_one_sample,
                                runner=runner,
                                tc_id=tc_id,
                                tc_input=tc_input,
                                sample_index=i,
                                version_tag=version_tag,
                                output_path=output_path,
                                structure_root=structure_root,
                            )
                        )
                for future in as_completed(futures):
                    future.result()
                    written += 1

    return written


def sample_for_side(
    *,
    git_ref: str | None,
    runner_module: str,
    runner_callable: str,
    test_cases: list[dict[str, Any]],
    samples_per_case: int,
    version_tag: Literal["baseline", "candidate"],
    output_path: Path,
    repo_root: Path,
    install_deps: bool = True,
    capture: dict[str, bool] | None = None,
    workers: int = 1,
    cassette_path: str | Path | None = None,
    cassette_mode: str | None = None,
) -> None:
    """Sample one side. ``git_ref=None`` means the live working tree."""
    import agentdiff

    capture = capture or {}
    agentdiff.install(capture)

    if git_ref is None:
        # The runner module lives in the user's project, not on our sys.path.
        root_str = str(Path(repo_root).resolve())
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        run_samples(
            runner_module=runner_module,
            runner_callable=runner_callable,
            test_cases=test_cases,
            samples_per_case=samples_per_case,
            version_tag=version_tag,
            output_path=Path(output_path),
            structure_root=Path(repo_root),
            workers=workers,
            cassette_path=cassette_path,
            cassette_mode=cassette_mode,
        )
    else:
        with _checked_out(Path(repo_root), git_ref, install_deps=install_deps) as checkout:
            _sample_in_checkout(
                checkout=checkout,
                runner_module=runner_module,
                runner_callable=runner_callable,
                test_cases=test_cases,
                samples_per_case=samples_per_case,
                version_tag=version_tag,
                output_path=Path(output_path),
                capture=capture,
                workers=workers,
                cassette_path=cassette_path,
                cassette_mode=cassette_mode,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_runner(module: str, callable_name: str) -> Callable[[dict], Any]:
    mod = import_module(module)
    runner = getattr(mod, callable_name, None)
    if runner is None or not callable(runner):
        raise TypeError(
            f"{module}.{callable_name} is not callable. "
            "A Runner must be a function or a class instance with __call__."
        )
    return runner


def _call_runner(runner: Callable[[dict], Any], input_data: dict[str, Any]) -> Any:
    """Call sync or async runners from the sampling loop."""
    result = runner(input_data)
    if inspect.isawaitable(result):
        return _run_awaitable(result)
    return result


def _run_one_sample(
    *,
    runner: Callable[[dict], Any],
    tc_id: str,
    tc_input: dict[str, Any],
    sample_index: int,
    version_tag: Literal["baseline", "candidate"],
    output_path: Path,
    structure_root: Path | None,
) -> None:
    # The try wraps the whole `with` so a runner exception propagates through
    # Tracer.__exit__ (marking the trajectory failed + flushing) before being
    # caught here, so one bad sample never aborts the run.
    try:
        with Tracer(
            test_case_id=tc_id,
            version_tag=version_tag,
            input_data=tc_input,
            output_path=output_path,
            structure_root=structure_root,
        ) as tracer:
            result = _call_runner(runner, tc_input)
            tracer.set_final_output(_normalize_output(result))
    except Exception as e:  # noqa: BLE001 — never abort the whole run
        print(f"    run {sample_index + 1} failed: {type(e).__name__}: {e}")


def _run_awaitable(awaitable) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError(
        "Async runners cannot be executed from an already-running event loop. "
        "Run AgentDiff from the CLI or wrap the async call in a synchronous Runner."
    )


def _normalize_output(result: Any) -> str:
    """Map a Runner return value to the trajectory's string final_output."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str)


def _cassette_context(cassette_path: str | Path | None, cassette_mode: str | None):
    if cassette_path is None or cassette_mode is None:
        return nullcontext()
    if cassette_mode not in {"record", "replay"}:
        raise ValueError("cassette_mode must be 'record' or 'replay'")
    import agentdiff
    return agentdiff.cassette(cassette_path, cassette_mode)  # type: ignore[arg-type]


@contextmanager
def _checked_out(repo_root: Path, git_ref: str, install_deps: bool = True) -> Iterator[Path]:
    """Extract a git ref into a temp dir via ``git archive | tar -x``."""
    with tempfile.TemporaryDirectory(prefix="agentdiff-") as td:
        td_path = Path(td)
        archive = subprocess.run(
            ["git", "archive", "--format=tar", git_ref],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["tar", "-x", "-C", str(td_path)],
            input=archive.stdout,
            check=True,
        )
        if install_deps:
            _install_deps(td_path)
        yield td_path


def _install_deps(td_path: Path) -> None:
    """Install dependencies for the checked-out project, failing loudly on error."""
    if (td_path / "pyproject.toml").exists():
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            cwd=td_path,
            check=False,
            capture_output=True,
            text=True,
        )
    elif (td_path / "requirements.txt").exists():
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=td_path,
            check=False,
            capture_output=True,
            text=True,
        )
    else:
        return

    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-15:])
        raise SamplingError(
            "Dependency installation failed for checked-out baseline/candidate. "
            "Use --no-install-deps only if the runner can import without installing "
            f"the checkout.\n{tail}"
        )


def _sample_in_checkout(
    *,
    checkout: Path,
    runner_module: str,
    runner_callable: str,
    test_cases: list[dict[str, Any]],
    samples_per_case: int,
    version_tag: str,
    output_path: Path,
    capture: dict[str, bool] | None = None,
    workers: int = 1,
    cassette_path: str | Path | None = None,
    cassette_mode: str | None = None,
) -> None:
    """Run the sampling loop in a subprocess rooted at the checkout dir."""
    params = {
        "checkout": str(checkout),
        "runner_module": runner_module,
        "runner_callable": runner_callable,
        "test_cases": test_cases,
        "samples_per_case": samples_per_case,
        "version_tag": version_tag,
        "output_path": str(output_path),
        "capture": capture or {},
        "workers": workers,
        "cassette_path": str(cassette_path) if cassette_path is not None else None,
        "cassette_mode": cassette_mode,
    }
    params_file = checkout / ".agentdiff_sample_params.json"
    params_file.write_text(json.dumps(params), encoding="utf-8")

    script = _SUBPROCESS_TEMPLATE.format(params_file=repr(str(params_file)))
    result = subprocess.run(
        [sys.executable, "-c", script], check=False, capture_output=True, text=True
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        # Don't bury a failed side — the CLI guards on empty trajectory sets,
        # but the actual cause is here in the subprocess stderr.
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise SamplingError(
            f"Checkout sampling subprocess exited with code {result.returncode}:\n{tail}"
        )


_SUBPROCESS_TEMPLATE = """\
import json, sys
with open({params_file}) as f:
    p = json.load(f)
sys.path.insert(0, p["checkout"])
import agentdiff
agentdiff.install(p.get("capture", {{}}))
from agentdiff.sampling import run_samples
run_samples(
    runner_module=p["runner_module"],
    runner_callable=p["runner_callable"],
    test_cases=p["test_cases"],
    samples_per_case=p["samples_per_case"],
    version_tag=p["version_tag"],
    output_path=p["output_path"],
    structure_root=p["checkout"],
    workers=p.get("workers", 1),
    cassette_path=p.get("cassette_path"),
    cassette_mode=p.get("cassette_mode"),
)
"""

"""Sampling engine: run a user's Runner N times per test case, per side.

Two execution modes:
  - In-place (working tree): import the Runner and loop in this process.
  - Git ref: ``git archive <ref> | tar -x`` into a temp dir, install its deps,
    and run the loop in a subprocess so the checked-out code wins on import.

The Runner contract (see docs/recipes) is ``Callable[[dict], dict | str | None]``.
"""
import json
import asyncio
import contextvars
import inspect
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator, Literal

from agentdiff.capture.tracer import Tracer

if TYPE_CHECKING:
    from agentdiff.config import RedactionConfig


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
    timeout_seconds: float = 300.0,
    retries: int = 1,
    retry_backoff_seconds: float = 2.0,
) -> int:
    """Run the sampling loop in the current process. Returns trajectories written.

    Importable from a subprocess so the checked-out code path reuses it.

    ``timeout_seconds`` bounds each individual sample attempt (0 disables the
    timeout). A timed-out or failed attempt is retried up to ``retries`` times,
    sleeping ``retry_backoff_seconds * attempt`` between attempts. A sample
    that still fails/times out after all retries counts one trajectory toward
    the run's failure budget.
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
                    _run_one_sample_with_retry(
                        runner=runner,
                        tc_id=tc_id,
                        tc_input=tc_input,
                        sample_index=i,
                        version_tag=version_tag,
                        output_path=output_path,
                        structure_root=structure_root,
                        timeout_seconds=timeout_seconds,
                        retries=retries,
                        retry_backoff_seconds=retry_backoff_seconds,
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
                                _run_one_sample_with_retry,
                                runner=runner,
                                tc_id=tc_id,
                                tc_input=tc_input,
                                sample_index=i,
                                version_tag=version_tag,
                                output_path=output_path,
                                structure_root=structure_root,
                                timeout_seconds=timeout_seconds,
                                retries=retries,
                                retry_backoff_seconds=retry_backoff_seconds,
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
    timeout_seconds: float = 300.0,
    retries: int = 1,
    retry_backoff_seconds: float = 2.0,
    redaction_config: "RedactionConfig | None" = None,
) -> None:
    """Sample one side. ``git_ref=None`` means the live working tree."""
    import agentdiff
    from agentdiff.capture.http.redact import set_active_redaction_config

    capture = capture or {}
    agentdiff.install(capture)
    if redaction_config is not None:
        set_active_redaction_config(redaction_config)

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
            timeout_seconds=timeout_seconds,
            retries=retries,
            retry_backoff_seconds=retry_backoff_seconds,
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
                timeout_seconds=timeout_seconds,
                retries=retries,
                retry_backoff_seconds=retry_backoff_seconds,
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


def _call_traced(
    tracer: Tracer,
    runner: Callable[[dict], Any],
    input_data: dict[str, Any],
) -> Any:
    """Run the runner with ``tracer`` active, flushing exactly one trajectory.

    Enters ``tracer`` (so HTTP/SDK shims' ``get_active_tracer()`` resolves to
    it and events attach to it — matching pre-timeout/retry behavior where
    the runner call always happened inside a live ``Tracer`` context),
    calls the runner, sets the final output, and flushes via
    ``tracer.__exit__`` — all in one function so that when this whole thing
    runs via ``contextvars.copy_context().run(...)`` on a worker thread, the
    ContextVar ``set`` (enter) and ``reset`` (exit) happen in the *same*
    Context. ``ContextVar.Token.reset()`` requires the same Context it was
    created in, so splitting enter/exit across a context boundary (e.g.
    entering on a worker thread but exiting on the submitting thread) raises
    ``ValueError`` — keeping both here avoids that entirely.

    ``tracer.output_path`` is expected to be a private, per-attempt scratch
    file (see ``_run_one_sample_with_retry``), never the sample's real
    trajectory file — so this function's flush is always safe to call
    unconditionally, even for an attempt that will ultimately be treated as
    abandoned/timed-out by the caller.
    """
    with tracer:
        result = _call_runner(runner, input_data)
        tracer.set_final_output(_normalize_output(result))
    return result


def _run_traced_with_timeout(
    tracer: Tracer,
    runner: Callable[[dict], Any],
    input_data: dict[str, Any],
    timeout_seconds: float,
) -> Any:
    """Run the runner with ``tracer`` active, on a daemon thread bounded by
    ``timeout_seconds``.

    Unlike ``ThreadPoolExecutor`` (whose ``__exit__`` blocks on
    ``shutdown(wait=True)`` even after ``future.result(timeout=...)`` raises),
    a raw daemon thread lets the caller move on the instant ``join`` times
    out. The thread is simply abandoned — Python has no API to forcibly kill
    a running thread. If it eventually finishes, it flushes ``tracer`` (see
    ``_call_traced``) to whatever (private, scratch) ``output_path`` it was
    given — but by then the caller has already raised ``TimeoutError`` and
    moved on to a retry or the failure budget, and never reads ``tracer`` or
    its output file again, so that stray flush has no effect on the sample's
    recorded outcome. That lingering abandoned thread is the accepted cost of
    a soft, in-process timeout without full process isolation.

    ``contextvars.copy_context()`` on the calling (submitting) thread is used
    to run the target so ContextVars (active redaction config, etc.)
    propagate correctly into the worker thread and into any code the runner
    calls — plain ``threading.Thread`` would not propagate ContextVars on
    its own.
    """
    result_holder: dict[str, Any] = {"done": False}
    ctx = contextvars.copy_context()

    def _target() -> None:
        try:
            value = ctx.run(_call_traced, tracer, runner, input_data)
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller's side below
            result_holder["exc"] = exc
        else:
            result_holder["value"] = value
        finally:
            # Only meaningful if the caller hasn't already abandoned this
            # attempt (i.e. join() returned before this line runs); once
            # abandoned, no one reads result_holder again.
            result_holder["done"] = True

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive() or not result_holder.get("done"):
        # Timed out: the thread is abandoned here (left running as a daemon
        # so it doesn't block process exit); its eventual result/exception
        # is never consulted again.
        raise TimeoutError(f"sample timed out after {timeout_seconds}s")

    if "exc" in result_holder:
        raise result_holder["exc"]
    return result_holder["value"]


def _run_one_sample_with_retry(
    *,
    runner: Callable[[dict], Any],
    tc_id: str,
    tc_input: dict[str, Any],
    sample_index: int,
    version_tag: Literal["baseline", "candidate"],
    output_path: Path,
    structure_root: Path | None,
    timeout_seconds: float = 300.0,
    retries: int = 1,
    retry_backoff_seconds: float = 2.0,
) -> None:
    """Attempt a sample up to ``1 + retries`` times, writing exactly one trajectory.

    Each attempt gets its own ``Tracer`` pointed at a private scratch file
    (never the real ``output_path``) so HTTP/SDK-shim-captured events attach
    to that attempt (matching pre-timeout/retry behavior: the runner call
    always happens with a tracer active, not floating outside any capture
    context) without risking a stray write to the real trajectory file if
    the attempt is later abandoned. When ``timeout_seconds > 0`` the attempt
    runs on a dedicated daemon ``threading.Thread`` (see
    ``_run_traced_with_timeout``) so it can be bounded without blocking the
    sampling loop past the timeout — a plain ``ThreadPoolExecutor`` was tried
    first, but its context-manager ``__exit__`` calls ``shutdown(wait=True)``,
    which blocks until the abandoned runner call actually returns, defeating
    the point of a timeout for a truly hung runner. ``timeout_seconds == 0``
    disables the timeout and runs the attempt directly, no thread involved.

    On success, the attempt's scratch trajectory (with its captured events
    and final output) is copied verbatim into the real ``output_path``. On
    failure/timeout, the scratch file is simply discarded (best-effort
    cleanup; an abandoned daemon thread may still write to it later, but
    since it's never read again that has no effect on the sample's recorded
    outcome) and a single clean failure trajectory is written to the real
    ``output_path`` after all retries are exhausted instead — so an
    abandoned attempt never contributes a line to the real trajectory file.
    """
    max_attempts = 1 + max(0, retries)
    last_error: Exception | None = None
    last_was_timeout = False

    for attempt in range(1, max_attempts + 1):
        with tempfile.TemporaryDirectory(
            prefix="agentdiff-sample-", ignore_cleanup_errors=True
        ) as scratch_dir:
            scratch_path = Path(scratch_dir) / "attempt.jsonl"
            tracer = Tracer(
                test_case_id=tc_id,
                version_tag=version_tag,
                input_data=tc_input,
                output_path=scratch_path,
                structure_root=structure_root,
            )
            try:
                if timeout_seconds and timeout_seconds > 0:
                    _run_traced_with_timeout(tracer, runner, tc_input, timeout_seconds)
                else:
                    _call_traced(tracer, runner, tc_input)
            except Exception as exc:  # noqa: BLE001 — retried below, budgeted on final failure
                last_error = exc
                last_was_timeout = isinstance(exc, TimeoutError)
                if attempt < max_attempts:
                    print(
                        f"    run {sample_index + 1} attempt {attempt}/{max_attempts} "
                        f"failed: {type(exc).__name__}: {exc} — retrying"
                    )
                    if retry_backoff_seconds > 0:
                        time.sleep(retry_backoff_seconds * attempt)
                    continue
                break
            else:
                # Success within this attempt's timeout window: the scratch
                # file has exactly one flushed trajectory line — append it,
                # as-is, to the real output.
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "a") as dst, open(scratch_path) as src:
                    dst.write(src.read())
                return

    # All attempts exhausted: write one failed trajectory so the sample still
    # counts toward the run's failure budget, with a message that identifies
    # a timeout distinctly from any other runner failure.
    assert last_error is not None
    error_message = str(last_error) if last_was_timeout else f"{type(last_error).__name__}: {last_error}"
    print(f"    run {sample_index + 1} failed: {error_message}")
    _write_trajectory(
        tc_id=tc_id,
        tc_input=tc_input,
        version_tag=version_tag,
        output_path=output_path,
        structure_root=structure_root,
        final_output=None,
        error=error_message,
    )


def _write_trajectory(
    *,
    tc_id: str,
    tc_input: dict[str, Any],
    version_tag: Literal["baseline", "candidate"],
    output_path: Path,
    structure_root: Path | None,
    final_output: str | None,
    error: str | None = None,
) -> None:
    """Write exactly one trajectory line, success or failure, via Tracer."""
    try:
        with Tracer(
            test_case_id=tc_id,
            version_tag=version_tag,
            input_data=tc_input,
            output_path=output_path,
            structure_root=structure_root,
        ) as tracer:
            if error is not None:
                raise RuntimeError(error)
            tracer.set_final_output(final_output)
    except RuntimeError:
        if error is None:
            raise


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
    timeout_seconds: float = 300.0,
    retries: int = 1,
    retry_backoff_seconds: float = 2.0,
    redaction_config: "RedactionConfig | None" = None,
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
        "timeout_seconds": timeout_seconds,
        "retries": retries,
        "retry_backoff_seconds": retry_backoff_seconds,
        "redaction_config": redaction_config.model_dump() if redaction_config is not None else None,
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
redaction_config = p.get("redaction_config")
if redaction_config is not None:
    from agentdiff.capture.http.redact import set_active_redaction_config
    from agentdiff.config import RedactionConfig
    set_active_redaction_config(RedactionConfig(**redaction_config))
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
    timeout_seconds=p.get("timeout_seconds", 300.0),
    retries=p.get("retries", 1),
    retry_backoff_seconds=p.get("retry_backoff_seconds", 2.0),
)
"""

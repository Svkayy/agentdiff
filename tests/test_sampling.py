"""Day 5: in-place sampling loop."""
import json
import time

import httpx
import respx

from agentdiff.capture.events import LLMRequestEvent
from agentdiff.capture.http.redact import set_active_redaction_config
from agentdiff.config import RedactionConfig
from agentdiff.sampling import _normalize_output, run_samples
from agentdiff.storage import load_trajectory_set


def test_normalize_output():
    assert _normalize_output("hi") == "hi"
    assert _normalize_output(None) == ""
    assert _normalize_output({"a": 1}) == '{"a": 1}'


def test_run_samples_in_place(tmp_path, monkeypatch):
    # A tiny runner module written into tmp_path and imported by name.
    (tmp_path / "myrunner.py").write_text(
        "def run(input):\n"
        "    return f\"echo: {input.get('q', '')}\"\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "out.jsonl"
    test_cases = [{"id": "tc1", "input": {"q": "hello"}}]
    written = run_samples(
        runner_module="myrunner",
        runner_callable="run",
        test_cases=test_cases,
        samples_per_case=3,
        version_tag="baseline",
        output_path=out,
        structure_root=tmp_path,
        progress=False,
    )

    assert written == 3
    ts = load_trajectory_set(out, "baseline")
    assert len(ts.trajectories) == 3
    assert all(t.final_output == "echo: hello" for t in ts.trajectories)
    assert all(t.test_case_id == "tc1" for t in ts.trajectories)


def test_run_samples_runner_error_does_not_abort(tmp_path, monkeypatch):
    (tmp_path / "badrunner.py").write_text(
        "def run(input):\n"
        "    raise ValueError('boom')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "out.jsonl"
    written = run_samples(
        runner_module="badrunner",
        runner_callable="run",
        test_cases=[{"id": "tc1", "input": {}}],
        samples_per_case=2,
        version_tag="candidate",
        output_path=out,
        structure_root=tmp_path,
        progress=False,
    )
    # Both samples still produce trajectories (status=failed), run is not aborted.
    assert written == 2
    ts = load_trajectory_set(out, "candidate")
    assert len(ts.trajectories) == 2
    assert all(t.status == "failed" for t in ts.trajectories)


def test_run_samples_supports_async_runner(tmp_path, monkeypatch):
    (tmp_path / "asyncrunner.py").write_text(
        "async def run(input):\n"
        "    return {'echo': input.get('q')}\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "out.jsonl"
    written = run_samples(
        runner_module="asyncrunner",
        runner_callable="run",
        test_cases=[{"id": "tc1", "input": {"q": "hello"}}],
        samples_per_case=1,
        version_tag="baseline",
        output_path=out,
        structure_root=tmp_path,
        progress=False,
    )

    assert written == 1
    ts = load_trajectory_set(out, "baseline")
    assert ts.trajectories[0].final_output == '{"echo": "hello"}'


def test_run_samples_timeout_fails_with_message_and_retries(tmp_path, monkeypatch, capsys):
    (tmp_path / "slowrunner.py").write_text(
        "import time\n"
        "CALLS = []\n"
        "def run(input):\n"
        "    CALLS.append(1)\n"
        "    time.sleep(0.3)\n"
        "    return 'too slow'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "out.jsonl"
    written = run_samples(
        runner_module="slowrunner",
        runner_callable="run",
        test_cases=[{"id": "tc1", "input": {}}],
        samples_per_case=1,
        version_tag="baseline",
        output_path=out,
        structure_root=tmp_path,
        progress=False,
        timeout_seconds=0.1,
        retries=2,
        retry_backoff_seconds=0.01,
    )

    assert written == 1
    ts = load_trajectory_set(out, "baseline")
    assert len(ts.trajectories) == 1
    assert ts.trajectories[0].status == "failed"
    assert "sample timed out after 0.1s" in ts.trajectories[0].error

    out_text = capsys.readouterr().out
    assert out_text.count("timed out") >= 1

    import slowrunner
    # Initial attempt + 2 retries = 3 calls to the runner.
    assert len(slowrunner.CALLS) == 3


def test_run_samples_timeout_disabled_when_zero(tmp_path, monkeypatch):
    (tmp_path / "slowrunner2.py").write_text(
        "import time\n"
        "def run(input):\n"
        "    time.sleep(0.05)\n"
        "    return 'ok'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "out.jsonl"
    written = run_samples(
        runner_module="slowrunner2",
        runner_callable="run",
        test_cases=[{"id": "tc1", "input": {}}],
        samples_per_case=1,
        version_tag="baseline",
        output_path=out,
        structure_root=tmp_path,
        progress=False,
        timeout_seconds=0,
        retries=0,
    )

    assert written == 1
    ts = load_trajectory_set(out, "baseline")
    assert ts.trajectories[0].status == "success"
    assert ts.trajectories[0].final_output == "ok"


def test_run_samples_retries_transient_failure_then_succeeds(tmp_path, monkeypatch):
    (tmp_path / "flakyrunner.py").write_text(
        "CALLS = []\n"
        "def run(input):\n"
        "    CALLS.append(1)\n"
        "    if len(CALLS) < 2:\n"
        "        raise ValueError('transient')\n"
        "    return 'recovered'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "out.jsonl"
    written = run_samples(
        runner_module="flakyrunner",
        runner_callable="run",
        test_cases=[{"id": "tc1", "input": {}}],
        samples_per_case=1,
        version_tag="baseline",
        output_path=out,
        structure_root=tmp_path,
        progress=False,
        timeout_seconds=5,
        retries=2,
        retry_backoff_seconds=0.01,
    )

    assert written == 1
    ts = load_trajectory_set(out, "baseline")
    assert ts.trajectories[0].status == "success"
    assert ts.trajectories[0].final_output == "recovered"

    import flakyrunner
    assert len(flakyrunner.CALLS) == 2


_ANTHROPIC_RESPONSE = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "model": "claude-3-5-sonnet-20241022",
    "content": [{"type": "text", "text": "the secret plan is X"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 4},
}


def test_run_samples_strict_redaction_reaches_timeout_bounded_worker_thread(tmp_path, monkeypatch):
    """Critical 1 regression test.

    ``set_active_redaction_config`` uses a ContextVar. When
    ``timeout_seconds > 0``, ``_run_one_sample_with_retry`` runs the runner
    call inside a ``ThreadPoolExecutor`` worker thread. ContextVars do not
    propagate across the thread boundary by default, so the worker thread
    must see the *default* (standard) config instead of the strict one set on
    the submitting thread -- meaning the httpx shim's
    ``get_active_redaction_config()`` call (which happens inside the runner,
    which runs in the worker thread) would silently fall back to
    standard-mode masking instead of strict-mode hashing.

    This must fail before the fix (contextvars propagated via
    ``copy_context().run`` or an explicit in-thread ``set_active_redaction_config``
    call) and pass after.
    """
    import agentdiff

    (tmp_path / "httprunner.py").write_text(
        "import httpx\n"
        "def run(input):\n"
        "    client = httpx.Client()\n"
        "    client.post(\n"
        "        'https://api.anthropic.com/v1/messages',\n"
        "        json={\n"
        "            'model': 'claude-3-5-sonnet-20241022',\n"
        "            'max_tokens': 100,\n"
        "            'messages': [{'role': 'user', 'content': 'the secret plan'}],\n"
        "        },\n"
        "    )\n"
        "    return 'ok'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    agentdiff.install()
    set_active_redaction_config(RedactionConfig(mode="strict"))
    try:
        out = tmp_path / "out.jsonl"
        with respx.mock() as rmock:
            rmock.post("https://api.anthropic.com/v1/messages").mock(
                return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
            )
            written = run_samples(
                runner_module="httprunner",
                runner_callable="run",
                test_cases=[{"id": "tc1", "input": {}}],
                samples_per_case=1,
                version_tag="baseline",
                output_path=out,
                structure_root=tmp_path,
                progress=False,
                # timeout_seconds > 0 forces the worker-thread execution path.
                timeout_seconds=5.0,
            )

        assert written == 1
        raw = out.read_text(encoding="utf-8")
        assert "the secret plan" not in raw

        ts = load_trajectory_set(out, "baseline")
        assert len(ts.trajectories) == 1
        traj = ts.trajectories[0]

        req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
        messages_json = json.dumps(req.canonical.messages)
        assert "the secret plan" not in messages_json
        assert "sha256:" in messages_json
    finally:
        set_active_redaction_config(None)
        agentdiff.uninstall()


def test_run_samples_hung_runner_does_not_block_past_timeout(tmp_path, monkeypatch):
    """Important 2 regression test.

    A runner that sleeps far longer than ``timeout_seconds`` must not block
    the sampling loop beyond roughly the timeout window. Before the fix,
    ``ThreadPoolExecutor.__exit__`` calls ``shutdown(wait=True)``, which
    blocks until the abandoned runner call actually returns -- so a 5s sleep
    with a 0.2s timeout would make this test take >5s. After the fix (a
    daemon thread that is abandoned rather than joined-via-executor-shutdown),
    the loop must move on in well under 2s.
    """
    (tmp_path / "hungrunner.py").write_text(
        "import time\n"
        "def run(input):\n"
        "    time.sleep(5)\n"
        "    return 'too late'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "out.jsonl"
    start = time.monotonic()
    written = run_samples(
        runner_module="hungrunner",
        runner_callable="run",
        test_cases=[{"id": "tc1", "input": {}}],
        samples_per_case=1,
        version_tag="baseline",
        output_path=out,
        structure_root=tmp_path,
        progress=False,
        timeout_seconds=0.2,
        retries=0,
    )
    elapsed = time.monotonic() - start

    assert elapsed < 2.0, f"sampling loop blocked for {elapsed}s past the abandoned-thread timeout"
    assert written == 1
    ts = load_trajectory_set(out, "baseline")
    assert len(ts.trajectories) == 1
    assert ts.trajectories[0].status == "failed"
    assert "sample timed out after 0.2s" in ts.trajectories[0].error

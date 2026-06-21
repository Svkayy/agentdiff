"""Day 5: in-place sampling loop."""
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

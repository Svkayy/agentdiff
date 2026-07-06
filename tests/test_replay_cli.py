import json
import sys
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner

import agentdiff
from agentdiff.capture.tracer import Tracer
from agentdiff.cli.main import cli


@pytest.fixture(autouse=True)
def _fresh_agentrunner_module():
    """Every test project ships its own ``agentrunner.py`` at a fresh tmp_path.

    Guard against a stale ``sys.modules["agentrunner"]`` bleeding in from a
    previous test's (different, now-deleted) project directory — plain
    ``importlib.import_module`` returns whatever is cached regardless of the
    current ``sys.path``, so without this a replay could silently exercise
    the wrong runner code.
    """
    sys.modules.pop("agentrunner", None)
    yield
    sys.modules.pop("agentrunner", None)

URL = "https://api.openai.com/v1/chat/completions"
RESPONSE_BODY = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from cassette"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

RUNNER_BODY = (
    "import httpx\n"
    "def run(input):\n"
    "    resp = httpx.post(\n"
    "        'https://api.openai.com/v1/chat/completions',\n"
    "        json={'model': 'gpt-4o', 'messages': [{'role': 'user', 'content': input.get('q', '')}]},\n"
    "    )\n"
    "    return resp.json()['choices'][0]['message']['content']\n"
)


def _make_project(root: Path) -> None:
    (root / "agentrunner.py").write_text(RUNNER_BODY)
    ad = root / ".agentdiff"
    ad.mkdir()
    (ad / "structure.yaml").write_text(
        "version: '1'\nagents: []\ntools: []\nentry_points: []\n"
    )
    (ad / "config.yaml").write_text(
        "runner:\n  module: agentrunner\n  callable: run\nsamples_per_case: 1\n"
        "sampling:\n  install_deps: false\n"
    )
    (ad / "test_cases.yaml").write_text(
        "test_cases:\n  - id: tc1\n    input:\n      q: hello\n"
    )


def _unwrapped(output: str) -> str:
    """Undo Rich's soft line-wrapping so substring checks on long paths work."""
    return output.replace("\n", "")


def _record_cassette(project: Path, cassette_path: Path) -> None:
    """Record a cassette by running the project's runner once for real."""
    import sys

    sys.path.insert(0, str(project))
    try:
        import importlib

        import agentrunner  # noqa: F401
        importlib.reload(agentrunner)

        with respx.mock() as rmock:
            rmock.post(URL).mock(return_value=httpx.Response(200, json=RESPONSE_BODY))
            agentdiff.install()
            try:
                with agentdiff.cassette(cassette_path, "record"):
                    with Tracer("tc1", "baseline", {"q": "hello"}, cassette_path.parent / "_record.jsonl"):
                        agentrunner.run({"q": "hello"})
            finally:
                agentdiff.uninstall()
    finally:
        sys.path.remove(str(project))
        sys.modules.pop("agentrunner", None)


def test_replay_command_registered():
    result = CliRunner().invoke(cli, ["replay", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "--cassette" in result.output


def test_replay_missing_cassette_file_exits_with_path(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    missing_cassette = project / ".agentdiff" / "cassettes" / "nope.jsonl"

    result = CliRunner().invoke(
        cli,
        ["replay", "--project", str(project), "--cassette", str(missing_cassette)],
    )

    assert result.exit_code == 1
    assert str(missing_cassette) in _unwrapped(result.output)


def test_replay_cassette_miss_names_the_request(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    cassette_path = project / ".agentdiff" / "cassettes" / "empty.jsonl"
    cassette_path.parent.mkdir(parents=True)
    cassette_path.write_text("", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["replay", "--project", str(project), "--cassette", str(cassette_path)],
    )

    assert result.exit_code == 1
    output = _unwrapped(result.output)
    assert "no cassette recording" in output
    assert "chat/completions" in output
    assert "agentdiff ci run --cassette-mode record" in output


def test_replay_non_cassette_error_exits_clean(tmp_path, monkeypatch):
    """A non-HermeticSampleError raised during replay sampling (e.g. a
    sampling-internals bug) must exit 1 with a clean message, not an
    unhandled traceback.
    """
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    cassette_path = project / ".agentdiff" / "cassettes" / "main.jsonl"
    _record_cassette(project, cassette_path)
    out = tmp_path / "replay-out"

    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom: sampling internals exploded")

    monkeypatch.setattr("agentdiff.sampling.sample_for_side", _boom)

    result = CliRunner().invoke(
        cli,
        [
            "replay",
            "--project",
            str(project),
            "--cassette",
            str(cassette_path),
            "--report-dir",
            str(out),
        ],
    )

    assert result.exit_code == 1
    assert "kaboom" in result.output
    assert "Traceback" not in result.output


def test_replay_with_recorded_cassette_writes_report_dir(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    cassette_path = project / ".agentdiff" / "cassettes" / "main.jsonl"
    _record_cassette(project, cassette_path)
    out = tmp_path / "replay-out"

    result = CliRunner().invoke(
        cli,
        [
            "replay",
            "--project",
            str(project),
            "--cassette",
            str(cassette_path),
            "--report-dir",
            str(out),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    trajectories_path = out / "trajectories.jsonl"
    assert trajectories_path.exists()
    lines = [json.loads(line) for line in trajectories_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["final_output"] == "Hello from cassette"


def test_replay_is_deterministic_across_invocations(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    cassette_path = project / ".agentdiff" / "cassettes" / "main.jsonl"
    _record_cassette(project, cassette_path)

    out1 = tmp_path / "replay-out-1"
    out2 = tmp_path / "replay-out-2"

    for out in (out1, out2):
        result = CliRunner().invoke(
            cli,
            [
                "replay",
                "--project",
                str(project),
                "--cassette",
                str(cassette_path),
                "--report-dir",
                str(out),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output

    def _normalize(path: Path) -> list[dict]:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for row in rows:
            row.pop("run_id", None)
            row.pop("timestamp", None)
            row.pop("total_latency_ms", None)
            for event in row.get("events", []):
                event.pop("event_id", None)
                event.pop("call_id", None)
                event.pop("timestamp", None)
                event.pop("latency_ms", None)
        return rows

    traj1 = _normalize(out1 / "trajectories.jsonl")
    traj2 = _normalize(out2 / "trajectories.jsonl")
    assert traj1 == traj2


def test_replay_runner_error_mentioning_cassette_phrase_not_misreported(tmp_path):
    """A runner failure whose own message happens to contain the substring
    "no cassette recording" (but is not a CassetteMissError) must NOT be
    reported as a cassette miss with the misleading re-record suggestion —
    it should surface as a plain sampling failure instead.
    """
    project = tmp_path / "proj"
    project.mkdir()
    (project / "agentrunner.py").write_text(
        "def run(input):\n"
        "    raise RuntimeError('there is no cassette recording of this in our archives')\n"
    )
    ad = project / ".agentdiff"
    ad.mkdir()
    (ad / "structure.yaml").write_text(
        "version: '1'\nagents: []\ntools: []\nentry_points: []\n"
    )
    (ad / "config.yaml").write_text(
        "runner:\n  module: agentrunner\n  callable: run\nsamples_per_case: 1\n"
        "sampling:\n  install_deps: false\n  retries: 0\n"
    )
    (ad / "test_cases.yaml").write_text(
        "test_cases:\n  - id: tc1\n    input:\n      q: hello\n"
    )
    cassette_path = project / ".agentdiff" / "cassettes" / "main.jsonl"
    cassette_path.parent.mkdir(parents=True)
    cassette_path.write_text("", encoding="utf-8")
    out = tmp_path / "replay-out"

    result = CliRunner().invoke(
        cli,
        [
            "replay",
            "--project",
            str(project),
            "--cassette",
            str(cassette_path),
            "--report-dir",
            str(out),
        ],
        catch_exceptions=False,
    )

    # This is an ordinary runner failure (budgeted as a failed trajectory,
    # same as any other runner exception) — not a cassette miss, so it must
    # NOT carry the misleading re-record suggestion anywhere in the CLI
    # output or in the written trajectory's error message.
    output = _unwrapped(result.output)
    assert "agentdiff ci run --cassette-mode record" not in output
    lines = [json.loads(line) for line in (out / "trajectories.jsonl").read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["error"] is not None
    assert "agentdiff ci run --cassette-mode record" not in lines[0]["error"]
    assert lines[0]["error"].startswith("RuntimeError:")


def test_replay_samples_zero_rejected_with_clean_error(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    cassette_path = project / ".agentdiff" / "cassettes" / "main.jsonl"
    _record_cassette(project, cassette_path)
    out = tmp_path / "replay-out"

    result = CliRunner().invoke(
        cli,
        [
            "replay",
            "--project",
            str(project),
            "--cassette",
            str(cassette_path),
            "--report-dir",
            str(out),
            "--samples",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert not (out / "trajectories.jsonl").exists()
    assert "Traceback" not in result.output


def test_replay_samples_option_controls_count(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    cassette_path = project / ".agentdiff" / "cassettes" / "main.jsonl"
    _record_cassette(project, cassette_path)
    out = tmp_path / "replay-out"

    result = CliRunner().invoke(
        cli,
        [
            "replay",
            "--project",
            str(project),
            "--cassette",
            str(cassette_path),
            "--report-dir",
            str(out),
            "--samples",
            "3",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    lines = [
        line
        for line in (out / "trajectories.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(lines) == 3

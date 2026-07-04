import shutil
import subprocess
from pathlib import Path

from click.testing import CliRunner

from agentdiff.cli.main import cli


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_project(root: Path, runner_body: str, *, test_cases: bool = True) -> None:
    (root / "agentrunner.py").write_text(runner_body)
    ad = root / ".agentdiff"
    ad.mkdir()
    (ad / "structure.yaml").write_text(
        "version: '1'\nagents: []\ntools: []\nentry_points: []\n"
    )
    (ad / "config.yaml").write_text(
        "runner:\n  module: agentrunner\n  callable: run\nsamples_per_case: 1\n"
        "sampling:\n  install_deps: false\n"
    )
    if test_cases:
        (ad / "test_cases.yaml").write_text(
            "test_cases:\n  - id: tc1\n    input:\n      q: hello\n"
        )


def test_ci_command_registered():
    result = CliRunner().invoke(cli, ["ci", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "run" in result.output


def test_ci_run_empty_inputs_writes_warn_artifacts(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project, "def run(input):\n    return 'ok'\n", test_cases=False)
    out = tmp_path / "ci-out"

    result = CliRunner().invoke(
        cli,
        [
            "ci",
            "run",
            "--project",
            str(project),
            "--tier",
            "live",
            "--output",
            str(out),
            "--fail-on",
            "never",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "NOTICE" in (out / "agentdiff-ci.md").read_text(encoding="utf-8")
    assert "0 inputs" in (out / "summary.json").read_text(encoding="utf-8")


def test_ci_run_live_writes_artifacts(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        return
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project, "def run(input):\n    return 'ok:' + input.get('q', '')\n")
    _git(["init"], project)
    _git(["config", "user.email", "t@t.com"], project)
    _git(["config", "user.name", "t"], project)
    _git(["add", "-A"], project)
    _git(["commit", "-m", "baseline"], project)
    monkeypatch.syspath_prepend(str(project))

    out = tmp_path / "ci-out"
    result = CliRunner().invoke(
        cli,
        [
            "ci",
            "run",
            "--project",
            str(project),
            "--baseline",
            "HEAD",
            "--candidate",
            "working",
            "--tier",
            "live",
            "--min-live-samples",
            "1",
            "--output",
            str(out),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert (out / "agentdiff-ci.md").exists()
    assert (out / "postmortem.md").exists()
    assert (out / "summary.json").exists()
    assert (out / "slack_blocks.json").exists()
    assert (out / "slack_payload.json").exists()
    assert "AgentDiff CI Gate: STABLE" in (out / "agentdiff-ci.md").read_text(encoding="utf-8")


def test_ci_run_hermetic_requires_cassette(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project, "def run(input):\n    return 'ok'\n")

    result = CliRunner().invoke(
        cli,
        ["ci", "run", "--project", str(project), "--tier", "hermetic"],
    )

    assert result.exit_code == 1
    assert "Hermetic tier requires --cassette" in result.output


def test_ci_run_writes_github_outputs(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project, "def run(input):\n    return 'ok'\n", test_cases=False)
    out = tmp_path / "ci-out"
    gh_output = tmp_path / "gh_output.txt"
    gh_summary = tmp_path / "gh_summary.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(gh_summary))

    result = CliRunner().invoke(
        cli,
        [
            "ci", "run",
            "--project", str(project),
            "--tier", "live",
            "--output", str(out),
            "--fail-on", "never",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    outputs = gh_output.read_text(encoding="utf-8")
    assert "verdict=warn" in outputs
    assert f"artifact_dir={out}" in outputs
    assert "AgentDiff CI Gate: NOTICE" in gh_summary.read_text(encoding="utf-8")

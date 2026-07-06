"""Fast-fail runner validation: compare/ci import the runner before sampling."""
from pathlib import Path

from click.testing import CliRunner

from agentdiff.cli.main import cli


def _make_project(root: Path, *, module: str = "nope_this_module_does_not_exist") -> None:
    ad = root / ".agentdiff"
    ad.mkdir()
    (ad / "structure.yaml").write_text(
        "version: '1'\nagents: []\ntools: []\nentry_points: []\n"
    )
    (ad / "config.yaml").write_text(
        f"runner:\n  module: {module}\n  callable: run\nsamples_per_case: 1\n"
        "sampling:\n  install_deps: false\n"
    )
    (ad / "test_cases.yaml").write_text(
        "test_cases:\n  - id: tc1\n    input:\n      q: hello\n"
    )


def test_compare_fast_fails_on_bad_runner_module(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)

    result = CliRunner().invoke(
        cli,
        ["compare", "--baseline", "auto", "--candidate", "working", "--project", str(project)],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "agentdiff doctor" in result.output
    assert "nope_this_module_does_not_exist" in result.output


def test_ci_fast_fails_on_bad_runner_module(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project)
    out = tmp_path / "ci-out"

    result = CliRunner().invoke(
        cli,
        [
            "ci", "run",
            "--project", str(project),
            "--tier", "live",
            "--output", str(out),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "agentdiff doctor" in result.output
    assert "nope_this_module_does_not_exist" in result.output

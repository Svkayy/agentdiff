"""Day 5/6 end-to-end: `agentdiff compare` across a real git ref.

Exercises the riskiest path — git archive checkout + subprocess sampling for the
baseline ref, in-place sampling for the working-tree candidate, then compare +
output eval + report rendering. Embeddings are stubbed so no model download is
needed; no API key is required (the LLM judge is skipped).
"""
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from agentdiff.cli.main import cli

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not available"
)


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_project(root: Path, runner_body: str) -> None:
    (root / "agentrunner.py").write_text(runner_body)
    ad = root / ".agentdiff"
    ad.mkdir()
    (ad / "structure.yaml").write_text(
        "version: '1'\nagents: []\ntools: []\nentry_points: []\n"
    )
    (ad / "config.yaml").write_text(
        "runner:\n  module: agentrunner\n  callable: run\nsamples_per_case: 2\n"
        "llm_provider: anthropic\n"
    )
    (ad / "test_cases.yaml").write_text(
        "test_cases:\n  - id: tc1\n    input:\n      q: hello\n"
    )


def test_compare_end_to_end(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    _make_project(project, "def run(input):\n    return 'ok:' + input.get('q', '')\n")

    _git(["init"], project)
    _git(["config", "user.email", "t@t.com"], project)
    _git(["config", "user.name", "t"], project)
    _git(["add", "-A"], project)
    _git(["commit", "-m", "baseline"], project)

    # Candidate (working tree) is identical here → behavioral PASS expected.
    # Make the runner importable for the in-place candidate sampling.
    monkeypatch.syspath_prepend(str(project))
    # Stub embeddings so output eval needs no model download.
    import agentdiff.output_eval as oe
    monkeypatch.setattr(oe, "_default_embed",
                        lambda texts: np.asarray([[1.0, 0.0]] * len(texts)))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["compare", "--baseline", "HEAD", "--candidate", "working", "--project", str(project)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    reports = list((project / ".agentdiff" / "reports").glob("*/report.md"))
    assert reports, "no report.md produced"
    md = reports[0].read_text()
    assert "# AgentDiff Report" in md
    assert "tc1" in md

    # Baseline trajectories came from the subprocess/checkout path.
    baseline_jsonl = reports[0].parent / "baseline_trajectories.jsonl"
    assert baseline_jsonl.exists()
    assert baseline_jsonl.read_text().strip(), "baseline sampling produced no trajectories"

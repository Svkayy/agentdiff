"""Quickstart's NotImplementedError template prints the path + line to edit."""
from agentdiff.cli.quickstart import _write_runner_template


def test_write_runner_template_prints_absolute_path_and_line(tmp_path, capsys):
    result = _write_runner_template(tmp_path, force=False)

    target = tmp_path / "agentdiff_runner.py"
    assert target.exists()
    assert result == {"module": "agentdiff_runner", "callable": "run", "source": "template"}

    body = target.read_text(encoding="utf-8")
    raise_line = next(
        i for i, line in enumerate(body.splitlines(), start=1)
        if "raise NotImplementedError" in line
    )

    # rich.Console soft-wraps long lines to the terminal width in tests (no
    # real TTY), so compare against output with line breaks collapsed.
    out = capsys.readouterr().out.replace("\n", "")
    assert str(target.resolve()) in out
    assert f":{raise_line}" in out

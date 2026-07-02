"""Day 5/6: CLI surface — command registration, init scaffolding, autoload hook."""
import shutil
from pathlib import Path

from click.testing import CliRunner

from agentdiff.cli.init import (
    autoload_hook_installed,
    autoload_pth_path,
    install_autoload_hook,
    uninstall_autoload_hook,
)
from agentdiff.cli.main import cli

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projects" / "anthropic_simple"


def test_help_lists_all_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"], catch_exceptions=False)
    assert result.exit_code == 0
    for cmd in ("init", "compare", "ci", "doctor", "hook", "structure", "replay"):
        assert cmd in result.output


def test_structure_and_replay_stubs_run():
    runner = CliRunner()
    for cmd in ("structure", "replay"):
        result = runner.invoke(cli, [cmd], catch_exceptions=False)
        assert result.exit_code == 0
        assert "not implemented in v0" in result.output


def test_init_writes_config_scaffolding(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(project), "--no-install-hook"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    ad = project / ".agentdiff"
    assert (ad / "structure.yaml").exists()
    assert (ad / "config.yaml").exists()
    assert (ad / "test_cases.yaml").exists()
    assert (ad / "providers.yaml").exists()


def test_init_does_not_clobber_existing_config(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)
    ad = project / ".agentdiff"
    ad.mkdir(parents=True, exist_ok=True)
    (ad / "config.yaml").write_text("runner:\n  module: my.custom\n  callable: go\n")

    runner = CliRunner()
    runner.invoke(cli, ["init", str(project), "--no-install-hook"], catch_exceptions=False)

    assert "my.custom" in (ad / "config.yaml").read_text()


def test_install_autoload_hook_writes_pth(tmp_path):
    site = tmp_path / "site-packages"
    site.mkdir()
    pth = install_autoload_hook(site_packages=site)
    assert pth is not None
    assert pth == autoload_pth_path(site)
    assert pth.exists()
    content = pth.read_text()
    assert "import agentdiff" in content
    assert "agentdiff.install()" in content
    assert autoload_hook_installed(site)
    assert uninstall_autoload_hook(site)
    assert not pth.exists()


def test_init_with_hook_into_custom_site(tmp_path, monkeypatch):
    """--install-hook writes the .pth into the resolved site-packages dir."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)
    site = tmp_path / "site-packages"
    site.mkdir()

    # Redirect the hook target to our temp site-packages.
    import agentdiff.cli.init as init_mod
    monkeypatch.setattr(
        init_mod, "autoload_pth_path",
        lambda site_packages=None: site / "agentdiff_autoload.pth",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(project), "--install-hook"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert (site / "agentdiff_autoload.pth").exists()


def test_hook_status_command_uses_current_environment(tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    site.mkdir()

    import agentdiff.cli.init as init_mod
    import agentdiff.cli.hook as hook_mod
    hook_path = site / "agentdiff_autoload.pth"
    monkeypatch.setattr(
        init_mod,
        "autoload_pth_path",
        lambda site_packages=None: hook_path,
    )
    monkeypatch.setattr(
        hook_mod,
        "autoload_pth_path",
        lambda site_packages=None: hook_path,
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["hook", "status"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Not installed" in result.output

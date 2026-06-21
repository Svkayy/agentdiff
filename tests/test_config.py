from agentdiff.config import load_config, thresholds_for_compare


def test_load_config_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.samples_per_case == 20
    assert cfg.runner.callable == "run"
    assert cfg.sampling.install_deps is True
    assert thresholds_for_compare(cfg)["agent_invocation_rate_fail"] == 0.5


def test_load_config_reads_thresholds_and_capture(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "runner:\n"
        "  module: app.runner\n"
        "thresholds:\n"
        "  agent_invocation_rate:\n"
        "    warn: 0.1\n"
        "    fail: 0.3\n"
        "capture:\n"
        "  mcp: false\n",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.runner.module == "app.runner"
    assert thresholds_for_compare(cfg)["agent_invocation_rate_warn"] == 0.1
    assert cfg.capture.mcp is False

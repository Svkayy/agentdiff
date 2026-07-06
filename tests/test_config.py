import pytest
from pydantic import ValidationError

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


def test_defaults_load_from_empty_yaml(tmp_path):
    cfg = load_config(tmp_path)

    # RedactionConfig, attached to CaptureConfig
    assert cfg.capture.redaction.mode == "standard"
    assert cfg.capture.redaction.patterns == []
    assert cfg.capture.redaction.redact_fields == []
    assert cfg.capture.redaction.capture_raw_bodies is False

    # SamplingConfig resilience fields
    assert cfg.sampling.timeout_seconds == 300.0
    assert cfg.sampling.retries == 1
    assert cfg.sampling.retry_backoff_seconds == 2.0

    # ThresholdConfig new MetricThreshold fields
    assert cfg.thresholds.latency_ms.warn == 1000
    assert cfg.thresholds.latency_ms.fail == 5000
    assert cfg.thresholds.tokens.warn == 200
    assert cfg.thresholds.tokens.fail == 1000
    assert cfg.thresholds.error_rate.warn == 0.1
    assert cfg.thresholds.error_rate.fail == 0.25

    # StatsConfig
    assert cfg.stats.correction == "benjamini_hochberg"
    assert cfg.stats.alpha == 0.05
    assert cfg.stats.min_samples_warn == 5

    # OutputEvalThresholds
    assert cfg.output_eval.semantic_fail == 0.70
    assert cfg.output_eval.semantic_warn == 0.85
    assert cfg.output_eval.length_fail == 0.50
    assert cfg.output_eval.length_warn == 0.80
    assert cfg.output_eval.structural_fail == 0.70
    assert cfg.output_eval.structural_warn == 0.90
    assert cfg.output_eval.judge_fail == 2.0
    assert cfg.output_eval.judge_warn == 3.5


def test_redaction_config_round_trips_from_yaml(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "capture:\n"
        "  redaction:\n"
        "    mode: strict\n"
        "    patterns:\n"
        "      - '\\d{3}-\\d{2}-\\d{4}'\n"
        "    redact_fields:\n"
        "      - authorization\n"
        "    capture_raw_bodies: true\n",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.capture.redaction.mode == "strict"
    assert cfg.capture.redaction.patterns == ["\\d{3}-\\d{2}-\\d{4}"]
    assert cfg.capture.redaction.redact_fields == ["authorization"]
    assert cfg.capture.redaction.capture_raw_bodies is True


def test_sampling_resilience_round_trips_from_yaml(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "sampling:\n"
        "  timeout_seconds: 60\n"
        "  retries: 3\n"
        "  retry_backoff_seconds: 1.5\n",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.sampling.timeout_seconds == 60
    assert cfg.sampling.retries == 3
    assert cfg.sampling.retry_backoff_seconds == 1.5


def test_new_thresholds_round_trip_from_yaml(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "thresholds:\n"
        "  latency_ms:\n"
        "    warn: 500\n"
        "    fail: 2000\n"
        "  tokens:\n"
        "    warn: 100\n"
        "    fail: 500\n"
        "  error_rate:\n"
        "    warn: 0.05\n"
        "    fail: 0.2\n",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.thresholds.latency_ms.warn == 500
    assert cfg.thresholds.latency_ms.fail == 2000
    assert cfg.thresholds.tokens.warn == 100
    assert cfg.thresholds.tokens.fail == 500
    assert cfg.thresholds.error_rate.warn == 0.05
    assert cfg.thresholds.error_rate.fail == 0.2


def test_stats_config_round_trips_from_yaml(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "stats:\n"
        "  correction: none\n"
        "  alpha: 0.01\n"
        "  min_samples_warn: 10\n",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.stats.correction == "none"
    assert cfg.stats.alpha == 0.01
    assert cfg.stats.min_samples_warn == 10


def test_output_eval_thresholds_round_trip_from_yaml(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "output_eval:\n"
        "  semantic_fail: 0.6\n"
        "  semantic_warn: 0.8\n"
        "  length_fail: 0.4\n"
        "  length_warn: 0.7\n"
        "  structural_fail: 0.6\n"
        "  structural_warn: 0.85\n"
        "  judge_fail: 1.5\n"
        "  judge_warn: 3.0\n",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.output_eval.semantic_fail == 0.6
    assert cfg.output_eval.semantic_warn == 0.8
    assert cfg.output_eval.length_fail == 0.4
    assert cfg.output_eval.length_warn == 0.7
    assert cfg.output_eval.structural_fail == 0.6
    assert cfg.output_eval.structural_warn == 0.85
    assert cfg.output_eval.judge_fail == 1.5
    assert cfg.output_eval.judge_warn == 3.0


def test_sampling_timeout_negative_raises(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "sampling:\n  timeout_seconds: -1\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_sampling_retries_negative_raises(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text("sampling:\n  retries: -1\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_sampling_retry_backoff_negative_raises(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "sampling:\n  retry_backoff_seconds: -0.5\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_stats_alpha_outside_range_raises(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text("stats:\n  alpha: 0.0\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(tmp_path)

    (ad / "config.yaml").write_text("stats:\n  alpha: 1.5\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_stats_unknown_correction_raises(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "stats:\n  correction: bonferroni\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_redaction_unknown_mode_raises(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "config.yaml").write_text(
        "capture:\n  redaction:\n    mode: paranoid\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_config(tmp_path)

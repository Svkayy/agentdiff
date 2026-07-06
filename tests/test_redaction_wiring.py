"""Loaded config's redaction settings must reach the active redaction contextvar.

A YAML with capture.redaction.mode: strict should result in strict-mode
events (message content replaced by sha256 digests) through the
``agentdiff.record()`` session path.
"""
import agentdiff
from agentdiff.capture.http.redact import (
    get_active_redaction_config,
    set_active_redaction_config,
)
from agentdiff.config import load_config


def test_strict_config_yaml_wires_through_record_session(tmp_path, monkeypatch):
    ad_dir = tmp_path / ".agentdiff"
    ad_dir.mkdir()
    (ad_dir / "config.yaml").write_text(
        "runner:\n  module: dummy\n  callable: run\n"
        "capture:\n  redaction:\n    mode: strict\n"
    )

    config = load_config(tmp_path)
    assert config.capture.redaction.mode == "strict"

    set_active_redaction_config(None)  # start clean
    set_active_redaction_config(config.capture.redaction)
    try:
        assert get_active_redaction_config().mode == "strict"

        import httpx

        def fake_send(self, request, *args, **kwargs):
            return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}]}, request=request)

        monkeypatch.setattr(httpx.Client, "send", fake_send)

        with agentdiff.record("strict_capture", project_root=tmp_path) as tracer:
            client = httpx.Client()
            client.post(
                "https://api.anthropic.com/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "the secret plan"}]},
            )
            tracer.set_final_output("done")

        capture_path = ad_dir / "captures" / "strict_capture.jsonl"
        lines = capture_path.read_text(encoding="utf-8").strip().splitlines()
        assert lines
        payload = "\n".join(lines)
        assert "the secret plan" not in payload
        assert "sha256:" in payload
    finally:
        set_active_redaction_config(None)
        agentdiff.uninstall()


def test_record_activates_redaction_from_loaded_config(tmp_path):
    """agentdiff.record() itself (not just a manual set) wires config.capture.redaction."""
    ad_dir = tmp_path / ".agentdiff"
    ad_dir.mkdir()
    (ad_dir / "config.yaml").write_text(
        "runner:\n  module: dummy\n  callable: run\n"
        "capture:\n  redaction:\n    mode: strict\n"
    )

    config = load_config(tmp_path)
    set_active_redaction_config(None)
    try:
        with agentdiff.record("auto_wire", project_root=tmp_path, config=config):
            assert get_active_redaction_config().mode == "strict"
    finally:
        set_active_redaction_config(None)
        agentdiff.uninstall()

"""Production-hardening fixes: sys.path sampling, error-response events,
zero-trajectory guard, Bedrock Converse, Gemini camelCase, flush robustness."""
import json
import shutil
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from click.testing import CliRunner

import agentdiff
from agentdiff.capture.http import httpx_shim
from agentdiff.capture.http.parsers import bedrock, gemini
from agentdiff.capture.http.provider_registry import match_provider
from agentdiff.capture.tracer import Tracer
from agentdiff.cli.main import cli
from agentdiff.sampling import sample_for_side
from agentdiff.storage import load_trajectory_set

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


# ---------------------------------------------------------------------------
# Fix 1: working-tree sampling adds the project root to sys.path
# ---------------------------------------------------------------------------

def test_sample_for_side_working_tree_syspath(tmp_path):
    project = tmp_path / "someproject"
    project.mkdir()
    (project / "themodule.py").write_text("def run(input):\n    return 'ok'\n")
    out = tmp_path / "out.jsonl"

    assert str(project.resolve()) not in sys.path
    try:
        sample_for_side(
            git_ref=None,
            runner_module="themodule",
            runner_callable="run",
            test_cases=[{"id": "tc", "input": {}}],
            samples_per_case=1,
            version_tag="baseline",
            output_path=out,
            repo_root=project,
        )
    finally:
        agentdiff.uninstall()
        sys.path.remove(str(project.resolve()))
        sys.modules.pop("themodule", None)

    ts = load_trajectory_set(out, "baseline")
    assert len(ts.trajectories) == 1
    assert ts.trajectories[0].final_output == "ok"


# ---------------------------------------------------------------------------
# Fix 2: a raising call records an is_error response event (httpx shim)
# ---------------------------------------------------------------------------

def test_httpx_shim_records_error_response_on_exception(tmp_path):
    tracer = Tracer("tc", "baseline", {}, tmp_path / "t.jsonl")

    request = httpx.Request(
        "POST", "https://api.anthropic.com/v1/messages",
        content=json.dumps({"model": "m", "messages": []}).encode(),
    )

    def failing_original(self_client, req, *a, **kw):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(httpx.ConnectError):
        httpx_shim._capture_sync(tracer, failing_original, None, request, (), {})

    types = [e.event_type for e in tracer._events]
    assert "llm_request" in types
    assert "llm_response" in types
    resp = next(e for e in tracer._events if e.event_type == "llm_response")
    assert resp.is_error is True
    # Same call_id ties the error response to its request.
    req_ev = next(e for e in tracer._events if e.event_type == "llm_request")
    assert resp.call_id == req_ev.call_id


def test_sdk_shim_error_helper_records_event(tmp_path):
    # The helper is importable without the anthropic SDK installed.
    from agentdiff.capture.sdk.anthropic_shim import _record_error_response
    import time

    tracer = Tracer("tc", "baseline", {}, tmp_path / "t.jsonl")
    _record_error_response(tracer, uuid4(), {"model": "m", "messages": []}, time.perf_counter())
    assert len(tracer._events) == 1
    assert tracer._events[0].is_error is True
    assert tracer._events[0].captured_by == "sdk_shim"


# ---------------------------------------------------------------------------
# Fix 3: zero-trajectory side aborts the compare with a clear error
# ---------------------------------------------------------------------------

@requires_git
def test_compare_aborts_when_baseline_side_empty(tmp_path, monkeypatch):
    """Runner module exists only in the working tree, not in the baseline commit:
    the baseline subprocess fails (→ empty side) while candidate would succeed.
    The CLI must exit 1 with a clear message, not render an all-PASS report."""
    project = tmp_path / "proj"
    project.mkdir()
    ad = project / ".agentdiff"
    ad.mkdir()
    (ad / "structure.yaml").write_text("version: '1'\nagents: []\ntools: []\nentry_points: []\n")
    (ad / "config.yaml").write_text(
        "runner:\n  module: latemodule\n  callable: run\nsamples_per_case: 1\n"
    )
    (ad / "test_cases.yaml").write_text("test_cases:\n  - id: tc\n    input: {}\n")

    def g(*args):
        subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)

    g("init")
    g("config", "user.email", "t@t.com")
    g("config", "user.name", "t")
    g("add", "-A")
    g("commit", "-m", "baseline without runner")

    # Runner appears only after the baseline commit.
    (project / "latemodule.py").write_text("def run(input):\n    return 'ok'\n")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["compare", "--baseline", "HEAD", "--project", str(project)],
    )
    sys.modules.pop("latemodule", None)
    assert result.exit_code == 1
    assert "Baseline sampling failed" in result.output
    assert "No module named 'latemodule'" in result.output
    # No report should have been produced.
    assert not list((ad / "reports").glob("*/report.md"))


# ---------------------------------------------------------------------------
# Fix 4: Bedrock Converse API + percent-encoded model IDs
# ---------------------------------------------------------------------------

class _Req:
    def __init__(self, url: str, body: dict):
        self.url = url
        self.content = json.dumps(body).encode()


def test_bedrock_converse_parsed_via_nova_shape():
    url = ("https://bedrock-runtime.us-east-1.amazonaws.com/model/"
           "anthropic.claude-3-sonnet-20240229-v1%3A0/converse")
    req_body = {
        "messages": [{"role": "user", "content": [{"text": "hello"}]}],
        "system": [{"text": "be brief"}],
        "inferenceConfig": {"temperature": 0.2},
    }
    resp_body = json.dumps({
        "output": {"message": {"role": "assistant", "content": [{"text": "hi"}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 7, "outputTokens": 2},
    }).encode()

    c = bedrock.parse(_Req(url, req_body), (None, resp_body))
    assert c.provider == "bedrock"
    assert c.model == "anthropic.claude-3-sonnet-20240229-v1:0"  # unquoted
    assert c.system == "be brief"
    assert c.messages == [{"role": "user", "content": "hello"}]
    assert c.response_text == "hi"
    assert c.stop_reason == "end_turn"
    assert c.usage["total_tokens"] == 9


def test_registry_matches_converse_and_streams():
    base = "https://bedrock-runtime.us-west-2.amazonaws.com/model/amazon.nova-pro-v1%3A0"
    for suffix in ("invoke", "invoke-with-response-stream", "converse", "converse-stream"):
        assert match_provider(f"{base}/{suffix}") == "bedrock", suffix


# ---------------------------------------------------------------------------
# Fix 5: Gemini camelCase request keys
# ---------------------------------------------------------------------------

def test_gemini_camelcase_system_instruction():
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        "systemInstruction": {"parts": [{"text": "be helpful"}]},
        "safetySettings": [{"category": "X", "threshold": "BLOCK_NONE"}],
        "generationConfig": {"temperature": 0.1},
    }
    c = gemini.parse(_Req(url, body), None)
    assert c.system == "be helpful"
    # Structural keys excluded from sampling_params; generationConfig kept.
    assert "systemInstruction" not in c.sampling_params
    assert "safetySettings" not in c.sampling_params
    assert "generationConfig" in c.sampling_params


# ---------------------------------------------------------------------------
# Fix 6: flush failure doesn't mask the runner's exception
# ---------------------------------------------------------------------------

def test_tracer_flush_failure_does_not_raise(tmp_path):
    # output_path is a directory → open() for append fails inside _flush.
    with pytest.raises(ValueError, match="the real error"):
        with Tracer("tc", "baseline", {}, tmp_path):
            raise ValueError("the real error")


def test_version_exported():
    assert agentdiff.__version__ == "0.1.0"

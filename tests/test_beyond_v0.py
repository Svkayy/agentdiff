"""Tests for the beyond-v0 upgrades: Cohere v1/v2, MCP safe output, git validation."""
import json
import shutil
import subprocess

import pytest

from agentdiff.capture.http.parsers import cohere
from agentdiff.capture.sdk.mcp_shim import _safe_output
from agentdiff.cli.compare import git_validation_error


class _Req:
    def __init__(self, content: bytes):
        self.content = content
        self.url = "https://api.cohere.com/v2/chat"


def _req(body: dict) -> _Req:
    return _Req(json.dumps(body).encode())


# --- Cohere v1/v2 ----------------------------------------------------------

def test_cohere_v2_message_content():
    resp = json.dumps({
        "message": {"content": [{"type": "text", "text": "hello"}]},
        "finish_reason": "COMPLETE",
        "usage": {"tokens": {"input_tokens": 3, "output_tokens": 1}},
    }).encode()
    c = cohere.parse(_req({"model": "command-r", "messages": [{"role": "user", "content": "hi"}]}),
                     (None, resp))
    assert c.provider == "cohere"
    assert c.response_text == "hello"
    assert c.usage["input_tokens"] == 3
    assert c.usage["output_tokens"] == 1
    assert c.stop_reason == "COMPLETE"


def test_cohere_v1_top_level_text():
    resp = json.dumps({
        "text": "hi there",
        "finish_reason": "COMPLETE",
        "meta": {"billed_units": {"input_tokens": 5, "output_tokens": 2}},
    }).encode()
    c = cohere.parse(_req({"model": "command", "messages": [{"role": "user", "content": "hi"}]}),
                     (None, resp))
    assert c.response_text == "hi there"
    assert c.usage["input_tokens"] == 5
    assert c.usage["output_tokens"] == 2


def test_cohere_v1_generations():
    resp = json.dumps({"generations": [{"text": "gen text"}]}).encode()
    c = cohere.parse(_req({"model": "command", "messages": []}), (None, resp))
    assert c.response_text == "gen text"


# --- MCP safe output -------------------------------------------------------

class _FakePydantic:
    def model_dump(self, mode=None):
        return {"content": [{"type": "text", "text": "ok"}]}


def test_safe_output_pydantic():
    assert _safe_output(_FakePydantic()) == {"content": [{"type": "text", "text": "ok"}]}


def test_safe_output_plain_json():
    assert _safe_output({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}


def test_safe_output_non_serializable_falls_back_to_str():
    class X:
        def __repr__(self):
            return "X-instance"
    out = _safe_output(X())
    assert isinstance(out, str)
    assert "X-instance" in out


def test_safe_output_none():
    assert _safe_output(None) is None


# --- git validation --------------------------------------------------------

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def test_git_validation_non_repo(tmp_path):
    err = git_validation_error(tmp_path, "main", "working")
    assert err is not None
    assert "not a git repository" in err


@requires_git
def test_git_validation_ok_and_bad_ref(tmp_path):
    def g(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "f.txt").write_text("hi")
    g("init")
    g("config", "user.email", "t@t.com")
    g("config", "user.name", "t")
    g("add", "-A")
    g("commit", "-m", "init")

    assert git_validation_error(tmp_path, "HEAD", "working") is None
    err = git_validation_error(tmp_path, "no-such-ref", "working")
    assert err is not None and "could not be resolved" in err

"""Day 1 smoke tests for the HTTP capture layer."""
import json
from pathlib import Path

import httpx
import pytest
import respx

import agentdiff
from agentdiff.capture.tracer import Tracer
from agentdiff.capture.http.provider_registry import match_provider
from agentdiff.trajectory import Trajectory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def shims():
    agentdiff.install()
    yield
    agentdiff.uninstall()


def _load_trajectory(path: Path) -> Trajectory:
    line = path.read_text().strip().splitlines()[0]
    return Trajectory.model_validate_json(line)


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://api.anthropic.com/v1/messages", "anthropic"),
    ("https://api.openai.com/v1/chat/completions", "openai_chat"),
    ("https://api.openai.com/v1/responses", "openai_responses"),
    (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
        "gemini",
    ),
    ("https://api.mistral.ai/v1/chat/completions", "mistral"),
    (
        "https://bedrock-runtime.us-east-1.amazonaws.com/model/anthropic.claude-v2/invoke",
        "bedrock",
    ),
    (
        "https://my-resource.openai.azure.com/openai/deployments/gpt-4/chat/completions",
        "azure_openai",
    ),
    ("https://api.cohere.com/v1/chat", "cohere"),
    ("https://api.cohere.ai/v1/chat", "cohere"),
    ("https://example.com/some/api", "unknown"),
])
def test_provider_registry(url, expected):
    assert match_provider(url) == expected


# ---------------------------------------------------------------------------
# Anthropic sync capture
# ---------------------------------------------------------------------------

_ANTHROPIC_RESPONSE = {
    "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
    "type": "message",
    "role": "assistant",
    "model": "claude-3-5-sonnet-20241022",
    "content": [{"type": "text", "text": "Hello from Claude!"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 4},
}

_ANTHROPIC_REQUEST_BODY = {
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Say hello"}],
}


def test_sync_anthropic_capture(tmp_path):
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
        )
        with Tracer("tc1", "baseline", {"query": "hello"}, output):
            client = httpx.Client()
            client.post(
                "https://api.anthropic.com/v1/messages",
                json=_ANTHROPIC_REQUEST_BODY,
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent

    req_events = [e for e in traj.events if isinstance(e, LLMRequestEvent)]
    resp_events = [e for e in traj.events if isinstance(e, LLMResponseEvent)]

    assert len(req_events) == 1
    assert len(resp_events) == 1

    req = req_events[0]
    assert req.canonical.provider == "anthropic"
    assert req.canonical.model == "claude-3-5-sonnet-20241022"
    assert req.canonical.messages == _ANTHROPIC_REQUEST_BODY["messages"]
    assert req.captured_by == "http_shim"
    assert req.raw_body is None  # known provider

    resp = resp_events[0]
    assert resp.canonical.response_text == "Hello from Claude!"
    assert resp.canonical.stop_reason == "end_turn"
    assert resp.canonical.usage["input_tokens"] == 12
    assert resp.canonical.usage["output_tokens"] == 4
    assert resp.canonical.usage["total_tokens"] == 16
    assert resp.is_error is False
    assert resp.latency_ms >= 0


# ---------------------------------------------------------------------------
# OpenAI sync capture
# ---------------------------------------------------------------------------

_OPENAI_RESPONSE = {
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hi there!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
}

_OPENAI_REQUEST_BODY = {
    "model": "gpt-4o",
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
    ],
    "temperature": 0.7,
}


def test_sync_openai_capture(tmp_path):
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_OPENAI_RESPONSE)
        )
        with Tracer("tc2", "baseline", {"query": "hi"}, output):
            client = httpx.Client()
            client.post(
                "https://api.openai.com/v1/chat/completions",
                json=_OPENAI_REQUEST_BODY,
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "openai_chat"
    assert req.canonical.system == "You are helpful."
    assert req.canonical.sampling_params["temperature"] == 0.7

    assert resp.canonical.response_text == "Hi there!"
    assert resp.canonical.stop_reason == "stop"
    assert resp.canonical.usage["total_tokens"] == 11


# ---------------------------------------------------------------------------
# Unknown provider — raw capture
#
# Raw bodies for unknown providers are withheld by default (they can't be
# pattern-redacted with any confidence — arbitrary/unknown shape) and are
# only captured when the operator explicitly opts in via
# `RedactionConfig.capture_raw_bodies=True`. See tests/test_redaction.py for
# the default-off and off/on coverage; this test exercises the opt-in path.
# ---------------------------------------------------------------------------

def test_unknown_provider_raw_capture(tmp_path):
    from agentdiff.capture.http.redact import set_active_redaction_config
    from agentdiff.config import RedactionConfig

    output = tmp_path / "traces.jsonl"
    raw_body = json.dumps({"text": "hello"}).encode()

    set_active_redaction_config(RedactionConfig(mode="standard", capture_raw_bodies=True))
    try:
        with respx.mock() as rmock:
            rmock.post("https://example-llm.com/v1/generate").mock(
                return_value=httpx.Response(200, content=b'{"output": "world"}')
            )
            with Tracer("tc3", "baseline", {}, output):
                client = httpx.Client()
                client.post(
                    "https://example-llm.com/v1/generate",
                    content=raw_body,
                )
    finally:
        set_active_redaction_config(None)

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "unknown"
    assert req.raw_body == raw_body
    assert resp.raw_body == b'{"output": "world"}'


def test_unknown_provider_raw_body_absent_without_opt_in(tmp_path):
    """Default (no config installed): unknown-provider raw bodies are withheld."""
    output = tmp_path / "traces.jsonl"
    raw_body = json.dumps({"text": "hello"}).encode()

    with respx.mock() as rmock:
        rmock.post("https://example-llm.com/v1/generate").mock(
            return_value=httpx.Response(200, content=b'{"output": "world"}')
        )
        with Tracer("tc3b", "baseline", {}, output):
            client = httpx.Client()
            client.post(
                "https://example-llm.com/v1/generate",
                content=raw_body,
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "unknown"
    assert req.raw_body is None
    assert resp.raw_body is None


# ---------------------------------------------------------------------------
# Multiple providers in one Tracer — both captured
# ---------------------------------------------------------------------------

def test_multi_provider_single_tracer(tmp_path):
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
        )
        rmock.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
        ).mock(return_value=httpx.Response(200, json={"candidates": []}))

        with Tracer("tc4", "baseline", {}, output):
            client = httpx.Client()
            client.post(
                "https://api.anthropic.com/v1/messages",
                json=_ANTHROPIC_REQUEST_BODY,
            )
            client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
                json={"contents": [{"parts": [{"text": "Hello"}]}]},
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent

    providers = [e.canonical.provider for e in traj.events if isinstance(e, LLMRequestEvent)]
    assert "anthropic" in providers
    assert "gemini" in providers


# ---------------------------------------------------------------------------
# No active Tracer — shim is transparent
# ---------------------------------------------------------------------------

def test_no_tracer_passthrough(tmp_path):
    """When no Tracer is active, the shim must not interfere."""
    with respx.mock() as rmock:
        rmock.get("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        client = httpx.Client()
        resp = client.get("https://api.anthropic.com/v1/messages")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Async httpx capture
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_anthropic_capture(tmp_path):
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
        )
        with Tracer("tc5", "baseline", {}, output):
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=_ANTHROPIC_REQUEST_BODY,
                )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert req.canonical.provider == "anthropic"
    assert req.captured_by == "http_shim"


# ---------------------------------------------------------------------------
# JSONL trajectory integrity
# ---------------------------------------------------------------------------

def test_trajectory_serialization_roundtrip(tmp_path):
    """Events must survive JSONL write → read without data loss."""
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
        )
        with Tracer("tc6", "candidate", {"query": "test"}, output):
            client = httpx.Client()
            client.post(
                "https://api.anthropic.com/v1/messages",
                json=_ANTHROPIC_REQUEST_BODY,
            )

    raw = output.read_text().strip()
    assert raw  # not empty
    traj = Trajectory.model_validate_json(raw.splitlines()[0])

    assert traj.test_case_id == "tc6"
    assert traj.version_tag == "candidate"
    assert traj.status == "success"
    assert len(traj.events) == 2
    assert traj.total_tokens == 16


# ---------------------------------------------------------------------------
# URL credential redaction (security): keys in the query string must never be
# persisted in request_url.
# ---------------------------------------------------------------------------

def test_redact_url_strips_query():
    from agentdiff.capture.http.redact import redact_url

    assert (
        redact_url(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-pro:generateContent?key=AIzaSECRET"
        )
        == "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-pro:generateContent"
    )
    # No query string → returned unchanged.
    assert (
        redact_url("https://api.anthropic.com/v1/messages")
        == "https://api.anthropic.com/v1/messages"
    )
    # Empty / unparseable input is tolerated.
    assert redact_url("") == ""


def test_gemini_url_key_not_persisted(tmp_path):
    """A Gemini API key in the request URL must not reach the trajectory."""
    output = tmp_path / "traces.jsonl"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-pro:generateContent?key=AIzaSECRETKEY123"
    )

    with respx.mock() as rmock:
        rmock.post(url).mock(return_value=httpx.Response(200, json={"candidates": []}))
        with Tracer("tc_redact", "baseline", {}, output):
            client = httpx.Client()
            client.post(url, json={"contents": [{"parts": [{"text": "Hi"}]}]})

    from agentdiff.capture.events import LLMRequestEvent

    traj = _load_trajectory(output)
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))

    # Provider matching still works (operates on the live URL).
    assert req.canonical.provider == "gemini"
    # The stored URL is redacted, and the key appears nowhere in the raw line.
    assert req.request_url is not None
    assert "key=" not in req.request_url
    assert "AIzaSECRETKEY123" not in output.read_text()

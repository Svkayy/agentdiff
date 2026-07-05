"""Redaction layer: secrets in text/headers/bodies/canonical calls must never
reach the JSONL trajectory or SQLite artifact, in standard, strict, and off
modes, across the HTTP and SDK capture shims.
"""
import json

import httpx
import pytest
import respx

import agentdiff
from agentdiff.capture.events import CanonicalLLMCall
from agentdiff.capture.http.redact import (
    SECRET_PATTERNS,
    redact_body,
    redact_canonical,
    redact_headers,
    redact_text,
    redact_url,
)
from agentdiff.capture.tracer import Tracer
from agentdiff.config import RedactionConfig
from agentdiff.trajectory import Trajectory


def _load_trajectory(path) -> Trajectory:
    line = path.read_text().strip().splitlines()[0]
    return Trajectory.model_validate_json(line)


STANDARD = RedactionConfig(mode="standard")
STRICT = RedactionConfig(mode="strict")
OFF = RedactionConfig(mode="off")


# ---------------------------------------------------------------------------
# SECRET_PATTERNS / redact_text — each pattern from the brief
# ---------------------------------------------------------------------------

_SECRET_SAMPLES = [
    ("openai", "sk-" + "A" * 20 + "abcdefghij"),
    ("openai_short_boundary", "sk-" + "a1B2c3D4e5" * 2),
    ("anthropic", "sk-ant-api03-" + "a" * 40),
    ("slack_bot", "xoxb-123456789012-123456789012-abcdefghijklmnopqrstuvwx"),
    ("slack_user", "xoxp-123456789012-123456789012-abcdefghijklmnopqrstuvwx"),
    ("slack_app", "xoxa-123456789012-123456789012-abcdefghijklmnopqrstuvwx"),
    ("slack_refresh", "xoxr-123456789012-123456789012-abcdefghijklmnopqrstuvwx"),
    ("slack_service", "xoxs-123456789012-123456789012-abcdefghijklmnopqrstuvwx"),
    ("bearer", "Bearer abcdefghijklmnopqrstuvwxyz0123456789"),
    ("aws_akia", "AKIAABCDEFGHIJKLMNOP"),
    ("generic_api_key_colon", "api_key: abcdef0123456789"),
    ("generic_api_key_eq", "api-key=abcdef0123456789"),
    ("generic_apikey_camel", "apikey: abcdef0123456789"),
]


@pytest.mark.parametrize("name,secret", _SECRET_SAMPLES)
def test_secret_patterns_match_each_sample(name, secret):
    assert any(p.search(secret) for p in SECRET_PATTERNS), f"{name}: {secret!r} not matched"


def test_pem_block_matched():
    pem = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC\n"
        "-----END PRIVATE KEY-----"
    )
    assert any(p.search(pem) for p in SECRET_PATTERNS)


@pytest.mark.parametrize("name,secret", _SECRET_SAMPLES)
def test_redact_text_masks_each_pattern_standard(name, secret):
    text = f"here is a secret: {secret} — end"
    out = redact_text(text, STANDARD)
    assert secret not in out
    assert "REDACTED" in out


def test_redact_text_masks_pem_block():
    pem = (
        "prefix -----BEGIN PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC\n"
        "-----END PRIVATE KEY----- suffix"
    )
    out = redact_text(pem, STANDARD)
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC" not in out
    assert "REDACTED" in out


def test_redact_text_leaves_non_secret_text_alone():
    text = "The quick brown fox jumps over the lazy dog."
    assert redact_text(text, STANDARD) == text


def test_redact_text_custom_pattern_from_config():
    cfg = RedactionConfig(mode="standard", patterns=[r"\d{3}-\d{2}-\d{4}"])
    text = "SSN: 123-45-6789 on file"
    out = redact_text(text, cfg)
    assert "123-45-6789" not in out
    assert "REDACTED" in out


def test_redact_text_off_mode_passes_through():
    secret = "sk-ant-api03-" + "a" * 40
    text = f"key={secret}"
    assert redact_text(text, OFF) == text


def test_redact_text_none_and_empty():
    assert redact_text("", STANDARD) == ""


# ---------------------------------------------------------------------------
# redact_headers — Authorization/X-Api-Key/Api-Key/Cookie always dropped in
# standard AND strict; case-insensitive; off mode passes through untouched.
# ---------------------------------------------------------------------------

_SENSITIVE_HEADERS = {
    "Authorization": "Bearer sk-ant-api03-secretsecretsecret",
    "X-Api-Key": "my-secret-key",
    "Api-Key": "another-secret",
    "Cookie": "session=abc123",
}


@pytest.mark.parametrize("mode", ["standard", "strict"])
def test_redact_headers_drops_sensitive_headers(mode):
    cfg = RedactionConfig(mode=mode)
    headers = {**_SENSITIVE_HEADERS, "Content-Type": "application/json"}
    out = redact_headers(headers, cfg)
    for k in _SENSITIVE_HEADERS:
        assert k not in out or out[k] != _SENSITIVE_HEADERS[k]
        # Value itself must never survive verbatim.
        assert _SENSITIVE_HEADERS[k] not in out.values()
    assert out["Content-Type"] == "application/json"


@pytest.mark.parametrize("mode", ["standard", "strict"])
def test_redact_headers_case_insensitive(mode):
    cfg = RedactionConfig(mode=mode)
    headers = {"authorization": "Bearer secretvalue12345", "cookie": "sid=zzz"}
    out = redact_headers(headers, cfg)
    assert "secretvalue12345" not in out.values()
    assert "sid=zzz" not in out.values()


def test_redact_headers_off_mode_passes_through_unchanged():
    headers = {**_SENSITIVE_HEADERS, "Content-Type": "application/json"}
    out = redact_headers(headers, OFF)
    assert out == headers


def test_redact_headers_custom_redact_fields():
    cfg = RedactionConfig(mode="standard", redact_fields=["x-custom-secret"])
    headers = {"X-Custom-Secret": "supersecret", "Content-Type": "application/json"}
    out = redact_headers(headers, cfg)
    assert "supersecret" not in out.values()
    assert out["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# redact_body — bytes/str, standard mode masks embedded secrets
# ---------------------------------------------------------------------------

def test_redact_body_masks_secret_in_bytes():
    secret = "sk-ant-api03-" + "b" * 40
    body = json.dumps({"api_key_value": secret}).encode()
    out = redact_body(body, STANDARD)
    assert isinstance(out, bytes)
    assert secret.encode() not in out
    assert b"REDACTED" in out


def test_redact_body_masks_secret_in_str():
    secret = "AKIA" + "B" * 16
    body = json.dumps({"note": secret})
    out = redact_body(body, STANDARD)
    assert isinstance(out, str)
    assert secret not in out
    assert "REDACTED" in out


def test_redact_body_off_mode_passes_through():
    secret = "sk-ant-api03-" + "c" * 40
    body = secret.encode()
    assert redact_body(body, OFF) == body


# ---------------------------------------------------------------------------
# redact_canonical — masks secrets in system/messages/tool args; strict mode
# replaces message/system content with sha256:<hex> digests but keeps
# roles/structure/counts intact.
# ---------------------------------------------------------------------------

def _sample_call(system_secret: str, msg_secret: str, tool_secret: str) -> CanonicalLLMCall:
    return CanonicalLLMCall(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        system=f"You are helpful. api_key: {system_secret}",
        messages=[
            {"role": "user", "content": f"my key is {msg_secret}"},
            {"role": "assistant", "content": "sure thing"},
        ],
        tools=[{"name": "lookup"}],
        tool_use_blocks=[{"tool_use_id": "t1", "name": "lookup", "args": {"token": tool_secret}}],
        response_text=f"Here: {msg_secret}",
    )


def test_redact_canonical_standard_masks_secrets_keeps_structure():
    system_secret = "sk-ant-api03-" + "d" * 40
    msg_secret = "AKIA" + "E" * 16
    tool_secret = "Bearer " + "f" * 40
    call = _sample_call(system_secret, msg_secret, tool_secret)

    out = redact_canonical(call, STANDARD)

    assert system_secret not in (out.system or "")
    assert all(msg_secret not in json.dumps(m) for m in out.messages)
    assert tool_secret not in json.dumps(out.tool_use_blocks)
    assert msg_secret not in (out.response_text or "")

    # Structure preserved.
    assert len(out.messages) == 2
    assert out.messages[0]["role"] == "user"
    assert out.messages[1]["role"] == "assistant"
    assert out.tools == [{"name": "lookup"}]
    assert out.tool_use_blocks[0]["tool_use_id"] == "t1"
    assert out.tool_use_blocks[0]["name"] == "lookup"


def test_redact_canonical_strict_hashes_message_and_system_content():
    call = _sample_call("secretA", "secretB", "secretC")
    out = redact_canonical(call, STRICT)

    assert out.system is not None
    assert out.system.startswith("sha256:")
    assert len(out.system) == len("sha256:") + 64

    assert len(out.messages) == 2
    for m in out.messages:
        assert m["content"].startswith("sha256:")
        assert len(m["content"]) == len("sha256:") + 64
    # Roles/structure/counts preserved.
    assert out.messages[0]["role"] == "user"
    assert out.messages[1]["role"] == "assistant"

    assert out.response_text is not None
    assert out.response_text.startswith("sha256:")


def test_redact_canonical_strict_hash_is_deterministic_sha256():
    import hashlib

    call = CanonicalLLMCall(provider="anthropic", system="hello world", messages=[])
    out = redact_canonical(call, STRICT)
    expected = "sha256:" + hashlib.sha256("hello world".encode()).hexdigest()
    assert out.system == expected


def test_redact_canonical_off_mode_passes_through_verbatim():
    system_secret = "sk-ant-api03-" + "g" * 40
    call = _sample_call(system_secret, "msgsecret", "toolsecret")
    out = redact_canonical(call, OFF)
    assert out.system == call.system
    assert out.messages == call.messages
    assert out.tool_use_blocks == call.tool_use_blocks
    assert out.response_text == call.response_text


def test_redact_canonical_preserves_usage_and_stop_reason():
    call = CanonicalLLMCall(
        provider="anthropic",
        system="api_key: sk-ant-api03-" + "h" * 40,
        messages=[{"role": "user", "content": "hi"}],
        stop_reason="end_turn",
        usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
    )
    out = redact_canonical(call, STRICT)
    assert out.stop_reason == "end_turn"
    assert out.usage == {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}


def test_redact_canonical_none_system_stays_none_in_strict():
    call = CanonicalLLMCall(provider="anthropic", system=None, messages=[])
    out = redact_canonical(call, STRICT)
    assert out.system is None


# ---------------------------------------------------------------------------
# redact_url still works (existing behavior preserved)
# ---------------------------------------------------------------------------

def test_redact_url_still_strips_query():
    assert (
        redact_url("https://example.com/v1/x?key=SECRET") == "https://example.com/v1/x"
    )


# ---------------------------------------------------------------------------
# End-to-end through the HTTP shim: secrets in request/response bodies must
# never reach the flushed trajectory (standard mode, default-on).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def shims():
    agentdiff.install()
    yield
    agentdiff.uninstall()
    from agentdiff.capture.http.redact import set_active_redaction_config
    set_active_redaction_config(None)


_ANTHROPIC_RESPONSE_WITH_SECRET = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "model": "claude-3-5-sonnet-20241022",
    "content": [{"type": "text", "text": "Sure, here is Bearer abcdefghijklmnopqrstuvwxyz012345 for you"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 4},
}


def test_http_shim_redacts_secret_in_anthropic_response_text_default_on(tmp_path):
    """Default-on: with no config set, standard-mode redaction still applies."""
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE_WITH_SECRET)
        )
        with Tracer("tc_redact_default", "baseline", {}, output):
            client = httpx.Client()
            client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "my api_key: sk-ant-api03-" + "z" * 40}],
                },
            )

    raw = output.read_text()
    assert "sk-ant-api03-" + "z" * 40 not in raw
    assert "Bearer abcdefghijklmnopqrstuvwxyz012345" not in raw

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))
    assert "sk-ant-api03-" not in json.dumps(req.canonical.messages)
    assert "Bearer abcdefghijklmnopqrstuvwxyz012345" not in (resp.canonical.response_text or "")


def test_http_shim_off_mode_passes_secrets_through(tmp_path):
    from agentdiff.capture.http.redact import set_active_redaction_config

    set_active_redaction_config(RedactionConfig(mode="off"))
    output = tmp_path / "traces.jsonl"
    secret = "sk-ant-api03-" + "y" * 40

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE_WITH_SECRET)
        )
        with Tracer("tc_redact_off", "baseline", {}, output):
            client = httpx.Client()
            client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": f"my api_key: {secret}"}],
                },
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert secret in json.dumps(req.canonical.messages)


def test_http_shim_strict_mode_hashes_message_content(tmp_path):
    from agentdiff.capture.http.redact import set_active_redaction_config

    set_active_redaction_config(RedactionConfig(mode="strict"))
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE_WITH_SECRET)
        )
        with Tracer("tc_redact_strict", "baseline", {}, output):
            client = httpx.Client()
            client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Say hello"}],
                },
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert req.canonical.messages[0]["content"].startswith("sha256:")
    assert req.canonical.messages[0]["role"] == "user"


# ---------------------------------------------------------------------------
# Unknown-provider raw bodies: absent by default, present only when
# capture_raw_bodies=True.
# ---------------------------------------------------------------------------

def test_unknown_provider_raw_body_absent_by_default(tmp_path):
    from agentdiff.capture.http.redact import set_active_redaction_config

    set_active_redaction_config(RedactionConfig(mode="standard", capture_raw_bodies=False))
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://example-llm.com/v1/generate").mock(
            return_value=httpx.Response(200, content=b'{"output": "world"}')
        )
        with Tracer("tc_raw_off", "baseline", {}, output):
            client = httpx.Client()
            client.post(
                "https://example-llm.com/v1/generate",
                content=json.dumps({"text": "hello"}).encode(),
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))
    assert req.raw_body is None
    assert resp.raw_body is None


def test_unknown_provider_raw_body_present_when_enabled(tmp_path):
    from agentdiff.capture.http.redact import set_active_redaction_config

    set_active_redaction_config(RedactionConfig(mode="standard", capture_raw_bodies=True))
    output = tmp_path / "traces.jsonl"
    raw_body = json.dumps({"text": "hello"}).encode()

    with respx.mock() as rmock:
        rmock.post("https://example-llm.com/v1/generate").mock(
            return_value=httpx.Response(200, content=b'{"output": "world"}')
        )
        with Tracer("tc_raw_on", "baseline", {}, output):
            client = httpx.Client()
            client.post(
                "https://example-llm.com/v1/generate",
                content=raw_body,
            )

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))
    assert req.raw_body == raw_body
    assert resp.raw_body == b'{"output": "world"}'


def test_unknown_provider_raw_body_still_redacted_when_enabled(tmp_path):
    """capture_raw_bodies=True doesn't bypass secret masking."""
    from agentdiff.capture.http.redact import set_active_redaction_config

    set_active_redaction_config(RedactionConfig(mode="standard", capture_raw_bodies=True))
    output = tmp_path / "traces.jsonl"
    secret = "sk-ant-api03-" + "k" * 40
    raw_body = json.dumps({"api_key_value": secret}).encode()

    with respx.mock() as rmock:
        rmock.post("https://example-llm.com/v1/generate").mock(
            return_value=httpx.Response(200, content=b'{"output": "world"}')
        )
        with Tracer("tc_raw_redacted", "baseline", {}, output):
            client = httpx.Client()
            client.post("https://example-llm.com/v1/generate", content=raw_body)

    raw_text = output.read_text()
    assert secret not in raw_text


# ---------------------------------------------------------------------------
# SDK shim (Anthropic): system/messages redacted before the event is recorded.
# ---------------------------------------------------------------------------

def test_anthropic_sdk_shim_redacts_system_prompt(tmp_path):
    anthropic = pytest.importorskip("anthropic", reason="anthropic SDK not installed")
    from agentdiff.capture.sdk import anthropic_shim

    if not anthropic_shim._PATCHED:
        pytest.skip("Anthropic shim not active (install failed)")

    output = tmp_path / "traces.jsonl"
    client = anthropic.Anthropic(api_key="test-key")
    secret = "sk-ant-api03-" + "m" * 40

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE_WITH_SECRET)
        )
        with Tracer("tc_sdk_redact", "baseline", {}, output):
            client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=100,
                system=f"You are helpful. api_key: {secret}",
                messages=[{"role": "user", "content": "Say hello"}],
            )

    raw = output.read_text()
    assert secret not in raw

    traj = _load_trajectory(output)
    from agentdiff.capture.events import LLMRequestEvent

    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert secret not in (req.canonical.system or "")


# ---------------------------------------------------------------------------
# SDK shim (OpenAI): tool call args redacted before the event is recorded.
# ---------------------------------------------------------------------------

def test_openai_sdk_shim_redacts_tool_args(tmp_path):
    openai = pytest.importorskip("openai", reason="openai SDK not installed")
    from agentdiff.capture.sdk import openai_shim

    if not openai_shim._PATCHED:
        pytest.skip("OpenAI shim not active (install failed)")

    output = tmp_path / "traces.jsonl"
    client = openai.OpenAI(api_key="test-key")
    secret = "AKIA" + "N" * 16

    response_with_tool_call = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": json.dumps({"token": secret}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }

    with respx.mock() as rmock:
        rmock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=response_with_tool_call)
        )
        with Tracer("tc_openai_sdk_redact", "baseline", {}, output):
            client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "call the tool"}],
            )

    raw = output.read_text()
    assert secret not in raw

import sys
import types
import pytest
from agentdiff.llm_client import LLMClient


class _FakeMessage:
    def __init__(self, content): self.content = content


class _FakeChoice:
    def __init__(self, content): self.message = _FakeMessage(content)


class _FakeCompletions:
    def __init__(self, captured): self._captured = captured
    def create(self, **kwargs):
        self._captured["create_kwargs"] = kwargs
        return types.SimpleNamespace(choices=[_FakeChoice("ok")])


class _FakeChat:
    def __init__(self, captured): self.completions = _FakeCompletions(captured)


class _FakeOpenAI:
    def __init__(self, **kwargs):
        _FakeOpenAI.captured["init_kwargs"] = kwargs
        self.chat = _FakeChat(_FakeOpenAI.captured)
    captured: dict = {}


@pytest.fixture
def fake_openai(monkeypatch):
    _FakeOpenAI.captured = {}
    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return _FakeOpenAI


def test_openai_path_uses_base_url_and_model_env(fake_openai, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setenv("AGENTDIFF_LLM_MODEL", "llama3.1:8b")
    client = LLMClient(provider="openai")
    out = client.complete("sys", "hi", max_tokens=64)
    assert out == "ok"
    assert fake_openai.captured["init_kwargs"]["base_url"] == "http://localhost:11434/v1"
    assert fake_openai.captured["create_kwargs"]["model"] == "llama3.1:8b"


def test_openai_path_default_model_and_no_base_url(fake_openai, monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AGENTDIFF_LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    client = LLMClient(provider="openai")
    client.complete("sys", "hi")
    assert fake_openai.captured["init_kwargs"].get("base_url") is None
    assert fake_openai.captured["create_kwargs"]["model"] == "gpt-4o-mini"


# --- LLMResult + generate() --------------------------------------------------

class _FakeAnthropicMessage:
    def __init__(self, content): self.content = content


class _FakeAnthropicContentBlock:
    def __init__(self, text): self.text = text


class _FakeAnthropicMessages:
    def __init__(self, captured, response=None, error=None):
        self._captured = captured
        self._response = response
        self._error = error

    def create(self, **kwargs):
        self._captured["create_kwargs"] = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeAnthropicSDKClient:
    def __init__(self, **kwargs):
        _FakeAnthropicSDKClient.captured["init_kwargs"] = kwargs
        self.messages = _FakeAnthropicSDKClient._messages_factory(
            _FakeAnthropicSDKClient.captured
        )
    captured: dict = {}
    _messages_factory = None


def _install_fake_anthropic(monkeypatch, *, response=None, error=None):
    _FakeAnthropicSDKClient.captured = {}
    _FakeAnthropicSDKClient._messages_factory = (
        lambda captured: _FakeAnthropicMessages(captured, response=response, error=error)
    )
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = _FakeAnthropicSDKClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    return _FakeAnthropicSDKClient


def test_generate_returns_llm_result_with_text_on_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    response = _FakeAnthropicMessage([_FakeAnthropicContentBlock("hello")])
    _install_fake_anthropic(monkeypatch, response=response)
    client = LLMClient(provider="anthropic")
    result = client.generate("sys", "hi")
    assert result.text == "hello"
    assert result.error is None


def test_generate_returns_error_not_bare_string_on_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _install_fake_anthropic(monkeypatch, error=RuntimeError("boom"))
    client = LLMClient(provider="anthropic")
    result = client.generate("sys", "hi")
    assert result.text is None
    assert result.error is not None
    assert "boom" in result.error


def test_generate_falls_back_to_openai_when_anthropic_errors_and_openai_key_present(
    monkeypatch, fake_openai
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    _install_fake_anthropic(monkeypatch, error=RuntimeError("anthropic down"))
    client = LLMClient(provider="anthropic")
    result = client.generate("sys", "hi")
    assert result.text == "ok"
    assert result.error is None
    assert fake_openai.captured["create_kwargs"] is not None


def test_generate_no_fallback_when_other_key_absent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _install_fake_anthropic(monkeypatch, error=RuntimeError("anthropic down"))
    client = LLMClient(provider="anthropic")
    result = client.generate("sys", "hi")
    assert result.text is None
    assert result.error is not None


def test_generate_openai_primary_falls_back_to_anthropic(monkeypatch, fake_openai):
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    class _FailingOpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **kw: (_ for _ in ()).throw(RuntimeError("openai down"))
                )
            )

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _FailingOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    response = _FakeAnthropicMessage([_FakeAnthropicContentBlock("rescued")])
    _install_fake_anthropic(monkeypatch, response=response)

    client = LLMClient(provider="openai")
    result = client.generate("sys", "hi")
    assert result.text == "rescued"
    assert result.error is None


def test_generate_fallback_uses_fallback_providers_default_model_when_pinned(
    monkeypatch, fake_openai
):
    """A model pinned via AGENTDIFF_LLM_MODEL/constructor applies only to the
    primary provider. When anthropic fails and falls back to openai, the
    fallback call must use openai's own default model, not the pinned
    anthropic-shaped model string (which would 404 against the OpenAI API)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    monkeypatch.setenv("AGENTDIFF_LLM_MODEL", "claude-x")
    _install_fake_anthropic(monkeypatch, error=RuntimeError("anthropic down"))
    client = LLMClient(provider="anthropic")
    result = client.generate("sys", "hi")
    assert result.error is None
    assert result.text == "ok"
    assert fake_openai.captured["create_kwargs"]["model"] == LLMClient._default_model_for(
        "openai"
    )
    assert fake_openai.captured["create_kwargs"]["model"] != "claude-x"


def test_complete_still_returns_bare_string_for_backward_compat(monkeypatch):
    """complete() is the older API — it must keep returning '' on failure,
    not raise, so existing callers (output_eval, explainer) don't break."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _install_fake_anthropic(monkeypatch, error=RuntimeError("boom"))
    client = LLMClient(provider="anthropic")
    out = client.complete("sys", "hi")
    assert out == ""

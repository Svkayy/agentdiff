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

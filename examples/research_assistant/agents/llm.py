"""Shared LLM helper — one Ollama call via the OpenAI-compatible API.

Every sub-agent calls through here. AgentDiff's OpenAI-SDK shim captures each
call; the tracer walks the call stack to the nearest agent function (this helper
is skipped), so the call is attributed to the agent that invoked it.

Points at a local Ollama by default (OPENAI_BASE_URL=http://localhost:11434/v1).
No system prompt is sent — keeping the captured prompt identical across versions
so attribution stays focused on real code changes.
"""
import os

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(
            base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", "ollama"),
        )
    return _client


def chat(prompt: str, *, max_tokens: int = 200) -> str:
    """Single-shot completion against the local model. Returns the text."""
    resp = _get_client().chat.completions.create(
        model=os.environ.get("AGENT_MODEL", "llama3.1:8b"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""

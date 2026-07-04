"""Fact-checker sub-agent.

BASELINE: reads prompts/fact_checker.txt; if the prompt contains the marker
"[FACT_CHECK_ENABLED]", makes a real httpx call to the mock Anthropic provider
(captured by AgentDiff's httpx shim — the URL matches the anthropic pattern).

CANDIDATE (code change): early return before the LLM call — fact checker
is silent, behavioral delta is detected and attributed to this file.

CANDIDATE (prompt change): prompt file no longer contains "[FACT_CHECK_ENABLED]",
so the LLM call is skipped — behavioral delta attributed to the prompt file.
"""
from __future__ import annotations

import os
from pathlib import Path


_MARKER = "[FACT_CHECK_ENABLED]"


def _load_prompt() -> str:
    """Load the fact-checker system prompt from prompts/fact_checker.txt."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "fact_checker.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return f"{_MARKER}\nYou are a fact-checker. Verify the provided context."


def fact_checker(context: str, query: str) -> str:
    """Verify context against query using the LLM provider.

    The prompt file controls whether fact-checking is enabled — if the prompt
    contains the '[FACT_CHECK_ENABLED]' marker line, the LLM call fires with the
    remaining prompt text as the system prompt. Otherwise, the function returns
    the context unchanged (behavioral silence).
    """
    raw_prompt = _load_prompt()

    # Gate: prompt must contain the activation marker for the LLM call to fire.
    if _MARKER not in raw_prompt:
        # Prompt change scenario: marker removed → behaves silently.
        return context

    # The marker is config, not prompt content — strip its line before sending.
    prompt = "\n".join(
        line for line in raw_prompt.splitlines() if _MARKER not in line
    ).strip()

    # Make a real HTTP call to the mock Anthropic provider.
    # AgentDiff's httpx shim intercepts this call and records the LLM event,
    # attributing it to the fact_checker function via the call-stack walker.
    import httpx

    base_url = os.environ.get("AGENTDIFF_DEMO_PROVIDER_URL", "http://localhost:18765")
    # Use a URL that matches the Anthropic provider pattern in the shim registry.
    # We point the Anthropic-shaped path at our local mock server.
    provider_url = f"{base_url}/v1/messages"

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 128,
        "system": prompt,
        "messages": [
            {"role": "user", "content": f"Context: {context}\nQuery: {query}"}
        ],
    }

    with httpx.Client() as client:
        response = client.post(
            provider_url,
            json=payload,
            headers={
                "x-api-key": "demo-key",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

    if response.status_code == 200:
        data = response.json()
        content = data.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", context)
    return context

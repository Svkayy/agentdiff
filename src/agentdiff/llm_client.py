"""Thin LLM wrapper for AgentDiff's own LLM use (output-eval judge + explainer).

Critical invariant: these calls must never be captured. They run after sampling
has exited its Tracer, so no Tracer is active and the shims pass through. The
constructor asserts this to catch accidental nesting.
"""
import os
from typing import Any, Literal

from agentdiff.capture.tracer import get_active_tracer

Provider = Literal["anthropic", "openai"]


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        if get_active_tracer() is not None:
            raise RuntimeError(
                "LLMClient must not be constructed while a Tracer is active — "
                "AgentDiff's own LLM calls would be captured as agent behavior."
            )
        self.provider: Provider = provider or os.environ.get(  # type: ignore[assignment]
            "AGENTDIFF_LLM_PROVIDER", "anthropic"
        )
        self._api_key = api_key
        self._model = model or os.environ.get("AGENTDIFF_LLM_MODEL")
        self._client: Any = None  # lazily constructed (anthropic/openai SDK client)

    @property
    def model(self) -> str:
        if self._model:
            return self._model
        return (
            "claude-3-5-haiku-20241022"
            if self.provider == "anthropic"
            else "gpt-4o-mini"
        )

    def complete(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        """Single-shot completion. Returns the model's text, or '' on failure."""
        try:
            if self.provider == "anthropic":
                return self._complete_anthropic(system, prompt, max_tokens)
            return self._complete_openai(system, prompt, max_tokens)
        except Exception as e:  # noqa: BLE001 — eval/explainer must degrade gracefully
            print(f"[agentdiff] LLMClient.complete failed: {type(e).__name__}: {e}")
            return ""

    # -- providers ----------------------------------------------------------

    def _complete_anthropic(self, system: str, prompt: str, max_tokens: int) -> str:
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(
                api_key=self._api_key or os.environ.get("ANTHROPIC_API_KEY")
            )
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text if resp.content else ""

    def _complete_openai(self, system: str, prompt: str, max_tokens: int) -> str:
        if self._client is None:
            import openai
            self._client = openai.OpenAI(
                api_key=self._api_key or os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL"),
            )
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""

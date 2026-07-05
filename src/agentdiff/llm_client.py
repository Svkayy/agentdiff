"""Thin LLM wrapper for AgentDiff's own LLM use (output-eval judge + explainer).

Critical invariant: these calls must never be captured. They run after sampling
has exited its Tracer, so no Tracer is active and the shims pass through. The
constructor asserts this to catch accidental nesting.
"""
import logging
import os
from typing import Any, Literal

from pydantic import BaseModel

from agentdiff.capture.tracer import get_active_tracer

log = logging.getLogger("agentdiff.llm")

Provider = Literal["anthropic", "openai"]


class LLMResult(BaseModel):
    """Result of a single LLM generation attempt.

    Exactly one of ``text``/``error`` is meaningful: on success ``text`` holds
    the model's reply and ``error`` is ``None``; on failure ``text`` is
    ``None`` and ``error`` holds a short description of what went wrong. This
    replaces the old bare-``""``-on-failure contract so callers can tell "the
    model said nothing" apart from "the call failed".
    """

    text: str | None = None
    error: str | None = None


def _other_provider(provider: str) -> Provider:
    return "openai" if provider == "anthropic" else "anthropic"  # type: ignore[return-value]


def _key_env_for(provider: str) -> str:
    return "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"


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
        # Lazily constructed SDK clients, keyed by provider name — a fallback
        # to the other provider must not reuse the primary provider's client.
        self._clients: dict[str, Any] = {}

    @property
    def model(self) -> str:
        if self._model:
            return self._model
        return self._default_model_for(self.provider)

    @staticmethod
    def _default_model_for(provider: str) -> str:
        return "claude-3-5-haiku-20241022" if provider == "anthropic" else "gpt-4o-mini"

    def complete(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        """Single-shot completion. Returns the model's text, or '' on failure.

        Older, string-only entry point kept for existing callers
        (``output_eval``, ``attribution/explainer``). New code should prefer
        ``generate()``, which distinguishes "empty reply" from "call failed"
        and can fall back to the other provider.
        """
        return self.generate(system, prompt, max_tokens).text or ""

    def generate(self, system: str, prompt: str, max_tokens: int = 1024) -> LLMResult:
        """Single-shot completion returning an :class:`LLMResult`.

        On a primary-provider error, falls back to the other provider if its
        API key is configured (``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``,
        respecting an explicitly-passed ``api_key`` only for the primary
        provider — the fallback always reads its key from the environment).
        """
        try:
            text = self._generate_with(self.provider, system, prompt, max_tokens)
            return LLMResult(text=text)
        except Exception as primary_exc:  # noqa: BLE001 — eval/explainer must degrade gracefully
            primary_error = f"{type(primary_exc).__name__}: {primary_exc}"
            log.warning("LLMClient.generate (%s) failed: %s", self.provider, primary_error)

            fallback_provider = _other_provider(self.provider)
            if not os.environ.get(_key_env_for(fallback_provider)):
                return LLMResult(error=primary_error)

            try:
                text = self._generate_with(fallback_provider, system, prompt, max_tokens)
                log.warning(
                    "LLMClient.generate: %s failed, served by fallback provider %s",
                    self.provider, fallback_provider,
                )
                return LLMResult(text=text)
            except Exception as fallback_exc:  # noqa: BLE001
                fallback_error = f"{type(fallback_exc).__name__}: {fallback_exc}"
                log.warning(
                    "LLMClient.generate: fallback provider %s also failed: %s",
                    fallback_provider, fallback_error,
                )
                return LLMResult(error=f"{primary_error}; fallback: {fallback_error}")

    def _generate_with(self, provider: str, system: str, prompt: str, max_tokens: int) -> str:
        if provider == "anthropic":
            return self._complete_anthropic(system, prompt, max_tokens)
        return self._complete_openai(system, prompt, max_tokens)

    # -- providers ----------------------------------------------------------
    # Each provider's SDK client is cached under self._clients[provider] so a
    # fallback call for the *other* provider never reuses the primary
    # provider's client.

    def _complete_anthropic(self, system: str, prompt: str, max_tokens: int) -> str:
        client = self._clients.get("anthropic")
        if client is None:
            import anthropic
            # Only the primary provider honors an explicitly-passed api_key;
            # the fallback provider always reads its key from the environment.
            key = self._api_key if self.provider == "anthropic" else None
            client = anthropic.Anthropic(
                api_key=key or os.environ.get("ANTHROPIC_API_KEY"),
                timeout=15.0,
            )
            self._clients["anthropic"] = client
        resp = client.messages.create(
            model=self._model or self._default_model_for("anthropic"),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text if resp.content else ""

    def _complete_openai(self, system: str, prompt: str, max_tokens: int) -> str:
        client = self._clients.get("openai")
        if client is None:
            import openai
            key = self._api_key if self.provider == "openai" else None
            client = openai.OpenAI(
                api_key=key or os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL"),
                timeout=15.0,
            )
            self._clients["openai"] = client
        resp = client.chat.completions.create(
            model=self._model or self._default_model_for("openai"),
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""

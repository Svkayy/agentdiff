from typing import Any

from agentdiff.capture.events import CanonicalLLMCall
from agentdiff.capture.http import parsers


_PARSER_MAP = {
    "anthropic": parsers.anthropic_messages,
    "openai_chat": parsers.openai_chat,
    "openai_responses": parsers.openai_responses,
    "gemini": parsers.gemini,
    "mistral": parsers.mistral,
    "bedrock": parsers.bedrock,
    "azure_openai": parsers.azure_openai,
    "cohere": parsers.cohere,
}


def build_canonical_from_http(
    provider: str,
    request: Any,
    response: Any,  # None (request side) or (httpx_response, body_bytes) tuple
) -> CanonicalLLMCall:
    parser = _PARSER_MAP.get(provider)
    if parser is not None:
        try:
            return parser.parse(request, response)
        except Exception:
            pass  # Fall through to unknown handling.

    return _unknown_canonical(provider)


def _unknown_canonical(provider: str) -> CanonicalLLMCall:
    return CanonicalLLMCall(provider=provider)

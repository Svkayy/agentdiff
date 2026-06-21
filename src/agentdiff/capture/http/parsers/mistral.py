from typing import Any

from agentdiff.capture.events import CanonicalLLMCall
from agentdiff.capture.http.parsers import openai_chat


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    """Mistral uses OpenAI-compatible chat format; reuse the OpenAI parser."""
    canonical = openai_chat.parse(request, response)
    return canonical.model_copy(update={"provider": "mistral"})

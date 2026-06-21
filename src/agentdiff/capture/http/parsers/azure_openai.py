import re
from typing import Any

from agentdiff.capture.events import CanonicalLLMCall
from agentdiff.capture.http.parsers import openai_chat

_DEPLOYMENT_RE = re.compile(r"/deployments/([^/]+)/")


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    """Azure OpenAI uses the same body format as OpenAI Chat; model is in the URL path."""
    canonical = openai_chat.parse(request, response)
    m = _DEPLOYMENT_RE.search(str(request.url))
    model = m.group(1) if m else canonical.model
    return canonical.model_copy(update={"provider": "azure_openai", "model": model})

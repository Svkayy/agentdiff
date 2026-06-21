import json
from typing import Any

from agentdiff.capture.events import CanonicalLLMCall

_STRUCTURAL = {"model", "messages", "system", "tools"}


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    """Parse an Anthropic Messages API request/response into CanonicalLLMCall."""
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    messages = body.get("messages", [])

    # system can be a string or a list of content blocks.
    raw_system = body.get("system")
    if isinstance(raw_system, list):
        system = "\n".join(
            b.get("text", "") for b in raw_system if isinstance(b, dict)
        )
    elif isinstance(raw_system, str):
        system = raw_system
    else:
        system = None

    sampling_params = {k: v for k, v in body.items() if k not in _STRUCTURAL}

    if response is None:
        return CanonicalLLMCall(
            provider="anthropic",
            model=body.get("model"),
            system=system,
            messages=messages,
            tools=body.get("tools"),
            sampling_params=sampling_params,
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        resp_json = {}

    content_blocks = resp_json.get("content", [])
    response_text = "".join(
        b.get("text", "")
        for b in content_blocks
        if isinstance(b, dict) and b.get("type") == "text"
    )
    tool_use_blocks = [
        {
            "tool_use_id": b.get("id"),
            "name": b.get("name"),
            "args": b.get("input", {}),
        }
        for b in content_blocks
        if isinstance(b, dict) and b.get("type") == "tool_use"
    ]

    raw_usage = resp_json.get("usage", {})
    input_tokens = raw_usage.get("input_tokens", 0)
    output_tokens = raw_usage.get("output_tokens", 0)

    return CanonicalLLMCall(
        provider="anthropic",
        model=resp_json.get("model", body.get("model")),
        system=system,
        messages=messages,
        tools=body.get("tools"),
        sampling_params=sampling_params,
        response_text=response_text or None,
        tool_use_blocks=tool_use_blocks,
        stop_reason=resp_json.get("stop_reason"),
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )

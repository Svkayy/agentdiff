import json
from typing import Any

from agentdiff.capture.events import CanonicalLLMCall

_STRUCTURAL = {"model", "messages", "tools"}


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    """Parse an OpenAI Chat Completions request/response into CanonicalLLMCall."""
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    messages = body.get("messages", [])

    # Extract system prompt from the messages list (first system message).
    system = next(
        (m.get("content") for m in messages if m.get("role") == "system"),
        None,
    )

    sampling_params = {k: v for k, v in body.items() if k not in _STRUCTURAL}

    if response is None:
        return CanonicalLLMCall(
            provider="openai_chat",
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

    choices = resp_json.get("choices", [])
    first_choice = choices[0] if choices else {}
    message = first_choice.get("message", {})

    response_text = message.get("content") or None

    raw_tool_calls = message.get("tool_calls") or []
    tool_use_blocks = []
    for tc in raw_tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except Exception:
            args = {}
        tool_use_blocks.append(
            {
                "tool_use_id": tc.get("id"),
                "name": fn.get("name"),
                "args": args,
            }
        )

    raw_usage = resp_json.get("usage", {})
    input_tokens = raw_usage.get("prompt_tokens", 0)
    output_tokens = raw_usage.get("completion_tokens", 0)

    return CanonicalLLMCall(
        provider="openai_chat",
        model=resp_json.get("model", body.get("model")),
        system=system,
        messages=messages,
        tools=body.get("tools"),
        sampling_params=sampling_params,
        response_text=response_text,
        tool_use_blocks=tool_use_blocks,
        stop_reason=first_choice.get("finish_reason"),
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": raw_usage.get("total_tokens", input_tokens + output_tokens),
        },
    )

import json
from typing import Any

from agentdiff.capture.events import CanonicalLLMCall

_STRUCTURAL = {"model", "input", "instructions", "tools"}


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    # `input` can be a string or a list of message objects.
    raw_input = body.get("input", [])
    if isinstance(raw_input, str):
        messages = [{"role": "user", "content": raw_input}]
    else:
        messages = list(raw_input)

    system = body.get("instructions")
    sampling_params = {k: v for k, v in body.items() if k not in _STRUCTURAL}

    if response is None:
        return CanonicalLLMCall(
            provider="openai_responses",
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

    response_text = None
    tool_use_blocks = []
    stop_reason = None

    for item in resp_json.get("output", []):
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        if itype == "message":
            for block in item.get("content", []):
                if isinstance(block, dict) and block.get("type") == "output_text":
                    response_text = (response_text or "") + block.get("text", "")
        elif itype == "function_call":
            args = item.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_use_blocks.append({
                "tool_use_id": item.get("call_id"),
                "name": item.get("name"),
                "args": args,
            })

    raw_usage = resp_json.get("usage", {})
    input_tokens = raw_usage.get("input_tokens", 0)
    output_tokens = raw_usage.get("output_tokens", 0)

    return CanonicalLLMCall(
        provider="openai_responses",
        model=resp_json.get("model", body.get("model")),
        system=system,
        messages=messages,
        tools=body.get("tools"),
        sampling_params=sampling_params,
        response_text=response_text or None,
        tool_use_blocks=tool_use_blocks,
        stop_reason=stop_reason,
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": raw_usage.get("total_tokens", input_tokens + output_tokens),
        },
    )

import json
from typing import Any

from agentdiff.capture.events import CanonicalLLMCall

_STRUCTURAL = {"model", "messages", "tools"}


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    messages = body.get("messages", [])
    system = next(
        (m.get("content") for m in messages if m.get("role") == "system"),
        None,
    )
    sampling_params = {k: v for k, v in body.items() if k not in _STRUCTURAL}

    if response is None:
        return CanonicalLLMCall(
            provider="cohere",
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

    # Cohere v2 (/v2/chat): text in message.content[]; tool calls in message.tool_calls.
    msg = resp_json.get("message", {})
    for block in msg.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            response_text = (response_text or "") + block.get("text", "")

    raw_tool_calls = msg.get("tool_calls")
    # Cohere v1 (/v1/chat): text at top level; tool_calls at top level.
    if response_text is None:
        if isinstance(resp_json.get("text"), str):
            response_text = resp_json["text"]
        else:
            generations = resp_json.get("generations") or []
            if generations and isinstance(generations[0], dict):
                response_text = generations[0].get("text")
    if raw_tool_calls is None:
        raw_tool_calls = resp_json.get("tool_calls")

    for tc in raw_tool_calls or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function", {})
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        tool_use_blocks.append({
            "tool_use_id": tc.get("id"),
            "name": fn.get("name"),
            "args": args,
        })

    # Usage: v2 usage.tokens / usage.billed_units; v1 meta.billed_units / meta.tokens.
    raw_usage = resp_json.get("usage") or {}
    meta = resp_json.get("meta") or {}
    tokens = (
        raw_usage.get("tokens")
        or raw_usage.get("billed_units")
        or meta.get("tokens")
        or meta.get("billed_units")
        or {}
    )
    input_tokens = tokens.get("input_tokens", 0)
    output_tokens = tokens.get("output_tokens", 0)

    return CanonicalLLMCall(
        provider="cohere",
        model=body.get("model"),
        system=system,
        messages=messages,
        tools=body.get("tools"),
        sampling_params=sampling_params,
        response_text=response_text or None,
        tool_use_blocks=tool_use_blocks,
        stop_reason=resp_json.get("finish_reason"),
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )

import json
import re
from typing import Any

from agentdiff.capture.events import CanonicalLLMCall

# The REST API's canonical JSON is camelCase but protobuf JSON parsing (and some
# SDK versions) accept/send snake_case — handle both spellings everywhere.
_STRUCTURAL = {
    "contents", "tools",
    "system_instruction", "systemInstruction",
    "tool_config", "toolConfig",
    "safety_settings", "safetySettings",
}
_MODEL_RE = re.compile(r"/models/([^/:]+)[:/]")


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    model = _extract_model(str(request.url))

    # Normalize contents → messages: flatten parts into a content string.
    messages = []
    for item in body.get("contents", []):
        role = item.get("role", "user")
        parts = item.get("parts", [])
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        messages.append({"role": role, "content": text})

    # system_instruction / systemInstruction is a separate top-level field.
    raw_si = body.get("system_instruction") or body.get("systemInstruction")
    system = None
    if isinstance(raw_si, dict):
        parts = raw_si.get("parts", [])
        system = "".join(p.get("text", "") for p in parts if isinstance(p, dict)) or None

    # generationConfig keys go into sampling_params; other structural keys excluded.
    sampling_params: dict[str, Any] = {}
    for k, v in body.items():
        if k not in _STRUCTURAL:
            sampling_params[k] = v

    if response is None:
        return CanonicalLLMCall(
            provider="gemini",
            model=model,
            system=system,
            messages=messages,
            tools=body.get("tools"),
            sampling_params=sampling_params,
        )

    _resp_obj, resp_body = response
    chunks = _parse_response_body(resp_body)

    response_text = None
    tool_use_blocks = []
    stop_reason = None
    raw_usage: dict = {}

    for chunk in chunks:
        for cand in chunk.get("candidates", []):
            if "finishReason" in cand:
                stop_reason = cand["finishReason"]
            for part in cand.get("content", {}).get("parts", []):
                if "text" in part:
                    response_text = (response_text or "") + part["text"]
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    tool_use_blocks.append({
                        "tool_use_id": None,
                        "name": fc.get("name"),
                        "args": fc.get("args", {}),
                    })
        # Last chunk with usageMetadata wins.
        if "usageMetadata" in chunk:
            raw_usage = chunk["usageMetadata"]

    input_tokens = raw_usage.get("promptTokenCount", 0)
    output_tokens = raw_usage.get("candidatesTokenCount", 0)

    return CanonicalLLMCall(
        provider="gemini",
        model=model,
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
            "total_tokens": raw_usage.get("totalTokenCount", input_tokens + output_tokens),
        },
    )


def _extract_model(url: str) -> str | None:
    m = _MODEL_RE.search(url)
    return m.group(1) if m else None


def _parse_response_body(body: bytes) -> list[dict]:
    """
    Return a list of Gemini response JSON objects.
    Handles both a single JSON object (generateContent) and the streaming format
    (streamGenerateContent), which is either a JSON array or newline-delimited objects.
    """
    if not body:
        return []
    text = body.decode("utf-8", errors="replace").strip()

    # Single object — the common non-streaming case.
    if text.startswith("{"):
        try:
            return [json.loads(text)]
        except json.JSONDecodeError:
            pass

    # JSON array — some streaming clients concatenate chunks this way.
    if text.startswith("["):
        try:
            arr = json.loads(text)
            return arr if isinstance(arr, list) else []
        except json.JSONDecodeError:
            pass

    # Newline-delimited JSON (SSE body stripped of "data: " prefixes).
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            chunks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return chunks

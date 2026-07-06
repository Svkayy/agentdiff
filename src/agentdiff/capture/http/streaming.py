import json
from typing import Any
from uuid import UUID

from agentdiff.capture.events import StreamChunkEvent
from agentdiff.capture.http.redact import (
    get_active_redaction_config,
    hash_content,
    redact_nested,
    redact_text,
)


def record_stream_chunks(tracer, *, call_id: UUID, provider: str, body: bytes) -> int:
    """Record reconstructed streaming deltas from common HTTP stream formats.

    ``text_delta``/``tool_delta`` are redacted with the active
    ``RedactionConfig`` before the ``StreamChunkEvent`` is built — streamed
    text/tool payloads must never bypass the same redaction applied to the
    non-streaming canonical request/response.
    """
    cfg = get_active_redaction_config()
    count = 0
    for count, chunk in enumerate(extract_stream_chunks(provider, body), start=1):
        text_delta = chunk.get("text_delta")
        tool_delta = chunk.get("tool_delta")

        if text_delta is not None:
            text_delta = hash_content(text_delta) if cfg.mode == "strict" else redact_text(text_delta, cfg)
        if tool_delta is not None:
            # tool_delta is a structured dict (tool_calls / partial_json / etc.):
            # always recurse and mask nested string leaves, matching how
            # tool_use_blocks[].args is handled for the non-streaming path.
            tool_delta = redact_nested(tool_delta, cfg)

        tracer.record(
            StreamChunkEvent(
                call_id=call_id,
                provider=provider,
                chunk_index=count - 1,
                text_delta=text_delta,
                tool_delta=tool_delta,
                metadata=chunk.get("metadata", {}),
            )
        )
    return count


def extract_stream_chunks(provider: str, body: bytes) -> list[dict[str, Any]]:
    text = _decode(body).strip()
    if not text:
        return []

    raw_chunks: list[Any] = []
    if _looks_like_sse(text):
        raw_chunks = _parse_sse(text)
    else:
        raw_chunks = _parse_json_sequence(text)

    chunks: list[dict[str, Any]] = []
    for raw in raw_chunks:
        chunk = _normalize_chunk(provider, raw)
        if chunk is not None:
            chunks.append(chunk)
    return chunks


def _decode(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")


def _looks_like_sse(text: str) -> bool:
    return any(line.startswith("data:") or line.startswith("event:") for line in text.splitlines())


def _parse_sse(text: str) -> list[Any]:
    chunks: list[Any] = []
    data_lines: list[str] = []
    event_name: str | None = None

    def flush() -> None:
        nonlocal data_lines, event_name
        if not data_lines:
            event_name = None
            return
        payload = "\n".join(data_lines).strip()
        data_lines = []
        event = event_name
        event_name = None
        if not payload or payload == "[DONE]":
            return
        try:
            item = json.loads(payload)
        except json.JSONDecodeError:
            item = {"text": payload}
        if isinstance(item, dict) and event:
            item.setdefault("event", event)
        chunks.append(item)

    for line in text.splitlines():
        if not line:
            flush()
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    flush()
    return chunks


def _parse_json_sequence(text: str) -> list[Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        # A single ordinary JSON response is not a stream timeline.
        return []

    chunks: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            chunks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return chunks if len(chunks) > 1 else []


def _normalize_chunk(provider: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return {"text_delta": str(raw), "metadata": {"provider": provider}}

    text_delta = _extract_text(raw)
    tool_delta = _extract_tool_delta(raw)
    metadata = {
        "provider": provider,
        "type": raw.get("type") or raw.get("event"),
        "finish_reason": _first_value(raw, ("finish_reason", "finishReason", "stop_reason")),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    if text_delta is None and tool_delta is None and not metadata.get("type"):
        return None
    return {
        "text_delta": text_delta,
        "tool_delta": tool_delta,
        "metadata": metadata,
    }


def _extract_text(raw: dict[str, Any]) -> str | None:
    # OpenAI/Mistral chat streaming.
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        texts = []
        for choice in choices:
            delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    texts.extend(_text_from_parts(content))
        if texts:
            return "".join(texts)

    # Anthropic Messages streaming.
    delta = raw.get("delta")
    if isinstance(delta, dict) and isinstance(delta.get("text"), str):
        return delta["text"]

    # Gemini streaming JSON array/chunks.
    candidates = raw.get("candidates")
    if isinstance(candidates, list):
        texts = []
        for candidate in candidates:
            content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
            parts = content.get("parts", []) if isinstance(content, dict) else []
            texts.extend(_text_from_parts(parts))
        if texts:
            return "".join(texts)

    # OpenAI Responses API and generic deltas.
    for key in ("text", "output_text", "delta"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
    return None


def _extract_tool_delta(raw: dict[str, Any]) -> dict[str, Any] | None:
    choices = raw.get("choices")
    if isinstance(choices, list):
        tool_calls = []
        for choice in choices:
            delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
            if isinstance(delta, dict) and delta.get("tool_calls"):
                tool_calls.extend(delta["tool_calls"])
        if tool_calls:
            return {"tool_calls": tool_calls}

    delta = raw.get("delta")
    if isinstance(delta, dict):
        tool_bits = {
            key: value
            for key, value in delta.items()
            if key in {"partial_json", "input_json_delta", "tool_calls"}
        }
        if tool_bits:
            return tool_bits
    return None


def _text_from_parts(parts: list[Any]) -> list[str]:
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif isinstance(part, str):
            texts.append(part)
    return texts


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None

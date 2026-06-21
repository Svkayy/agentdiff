import json
import re
from typing import Any
from urllib.parse import unquote

from agentdiff.capture.events import CanonicalLLMCall

_MODEL_RE = re.compile(r"/model/([^/]+)/(invoke|converse)")


def parse(request: Any, response: Any) -> CanonicalLLMCall:
    url = str(request.url)
    model_id = _extract_model_id(url)

    # The Converse API normalizes request/response across all model families to
    # a messages-style shape identical to Nova's, so one parser covers it.
    if "/converse" in url:
        return _parse_nova(request, response, model_id)

    prefix = (model_id or "").split(".")[0]

    dispatch = {
        "anthropic": _parse_anthropic,
        "amazon":    _parse_amazon,
        "meta":      _parse_llama,
        "mistral":   _parse_mistral,
        "cohere":    _parse_cohere,
        "ai21":      _parse_ai21,
        "writer":    _parse_generic,
    }
    handler = dispatch.get(prefix, _parse_generic)
    return handler(request, response, model_id)


# ---------------------------------------------------------------------------
# Per-family parsers
# ---------------------------------------------------------------------------

def _parse_anthropic(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    from agentdiff.capture.http.parsers import anthropic_messages
    canonical = anthropic_messages.parse(request, response)
    return canonical.model_copy(update={"provider": "bedrock", "model": model_id})


def _parse_amazon(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    """Amazon Titan Text and Amazon Nova families."""
    if model_id and "nova" in model_id:
        return _parse_nova(request, response, model_id)
    return _parse_titan_text(request, response, model_id)


def _parse_titan_text(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    input_text = body.get("inputText", "")
    messages = [{"role": "user", "content": input_text}] if input_text else []
    sampling_params = {k: v for k, v in body.items() if k not in {"inputText"}}

    if response is None:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, messages=messages, sampling_params=sampling_params
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        resp_json = {}

    results = resp_json.get("results", [{}])
    first = results[0] if results else {}
    response_text = first.get("outputText")
    stop_reason = first.get("completionReason")
    input_tokens = resp_json.get("inputTextTokenCount", 0)
    output_tokens = first.get("tokenCount", 0)

    return CanonicalLLMCall(
        provider="bedrock",
        model=model_id,
        messages=messages,
        sampling_params=sampling_params,
        response_text=response_text or None,
        stop_reason=stop_reason,
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def _parse_nova(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    """Amazon Nova — messages-style format similar to Anthropic."""
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    raw_messages = body.get("messages", [])
    messages = []
    for m in raw_messages:
        role = m.get("role", "user")
        content_parts = m.get("content", [])
        if isinstance(content_parts, list):
            text = "".join(p.get("text", "") for p in content_parts if isinstance(p, dict))
        else:
            text = str(content_parts)
        messages.append({"role": role, "content": text})

    system_list = body.get("system", [])
    system = "".join(s.get("text", "") for s in system_list if isinstance(s, dict)) or None

    sampling_params = {k: v for k, v in body.items() if k not in {"messages", "system", "tools"}}

    if response is None:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, system=system, messages=messages,
            tools=body.get("tools"), sampling_params=sampling_params,
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        resp_json = {}

    output = resp_json.get("output", {})
    msg = output.get("message", {})
    content_parts = msg.get("content", [])
    response_text = "".join(p.get("text", "") for p in content_parts if isinstance(p, dict)) or None

    raw_usage = resp_json.get("usage", {})
    input_tokens = raw_usage.get("inputTokens", 0)
    output_tokens = raw_usage.get("outputTokens", 0)

    return CanonicalLLMCall(
        provider="bedrock",
        model=model_id,
        system=system,
        messages=messages,
        tools=body.get("tools"),
        sampling_params=sampling_params,
        response_text=response_text,
        stop_reason=resp_json.get("stopReason"),
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def _parse_llama(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    """Meta Llama — prompt-style."""
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    prompt = body.get("prompt", "")
    messages = [{"role": "user", "content": prompt}] if prompt else []
    sampling_params = {k: v for k, v in body.items() if k != "prompt"}

    if response is None:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, messages=messages, sampling_params=sampling_params
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        resp_json = {}

    input_tokens = resp_json.get("prompt_token_count", 0)
    output_tokens = resp_json.get("generation_token_count", 0)

    return CanonicalLLMCall(
        provider="bedrock",
        model=model_id,
        messages=messages,
        sampling_params=sampling_params,
        response_text=resp_json.get("generation") or None,
        stop_reason=resp_json.get("stop_reason"),
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def _parse_mistral(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    """Mistral on Bedrock — prompt-style with outputs array."""
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    prompt = body.get("prompt", "")
    messages = [{"role": "user", "content": prompt}] if prompt else []
    sampling_params = {k: v for k, v in body.items() if k != "prompt"}

    if response is None:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, messages=messages, sampling_params=sampling_params
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        resp_json = {}

    outputs = resp_json.get("outputs", [{}])
    first = outputs[0] if outputs else {}

    return CanonicalLLMCall(
        provider="bedrock",
        model=model_id,
        messages=messages,
        sampling_params=sampling_params,
        response_text=first.get("text") or None,
        stop_reason=first.get("stop_reason"),
    )


def _parse_cohere(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    """Cohere Command on Bedrock."""
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    prompt = body.get("prompt", "")
    messages = [{"role": "user", "content": prompt}] if prompt else []
    sampling_params = {k: v for k, v in body.items() if k != "prompt"}

    if response is None:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, messages=messages, sampling_params=sampling_params
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        resp_json = {}

    generations = resp_json.get("generations", [{}])
    first = generations[0] if generations else {}

    return CanonicalLLMCall(
        provider="bedrock",
        model=model_id,
        messages=messages,
        sampling_params=sampling_params,
        response_text=first.get("text") or None,
        stop_reason=first.get("finish_reason"),
    )


def _parse_ai21(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    """AI21 Jurassic."""
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    prompt = body.get("prompt", "")
    if isinstance(prompt, dict):
        prompt = prompt.get("text", "")
    messages = [{"role": "user", "content": prompt}] if prompt else []
    sampling_params = {k: v for k, v in body.items() if k != "prompt"}

    if response is None:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, messages=messages, sampling_params=sampling_params
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        resp_json = {}

    completions = resp_json.get("completions", [{}])
    first = completions[0] if completions else {}
    text = first.get("data", {}).get("text") if isinstance(first.get("data"), dict) else None
    stop_reason = first.get("finishReason", {}).get("reason") if isinstance(first.get("finishReason"), dict) else None

    return CanonicalLLMCall(
        provider="bedrock",
        model=model_id,
        messages=messages,
        sampling_params=sampling_params,
        response_text=text or None,
        stop_reason=stop_reason,
    )


def _parse_generic(request: Any, response: Any, model_id: str | None) -> CanonicalLLMCall:
    """
    Best-effort parser for unknown Bedrock model families.
    Tries common text-extraction patterns across all known response shapes.
    """
    try:
        body: dict = json.loads(bytes(request.content))
    except Exception:
        body = {}

    sampling_params = {k: v for k, v in body.items()}

    if response is None:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, sampling_params=sampling_params
        )

    _resp_obj, resp_body = response
    try:
        resp_json: dict = json.loads(resp_body)
    except Exception:
        return CanonicalLLMCall(
            provider="bedrock", model=model_id, sampling_params=sampling_params
        )

    response_text = _extract_text_generic(resp_json)

    return CanonicalLLMCall(
        provider="bedrock",
        model=model_id,
        sampling_params=sampling_params,
        response_text=response_text or None,
    )


def _extract_text_generic(resp: dict) -> str | None:
    """Try every known Bedrock response text field, return the first hit."""
    # Anthropic-style
    for block in resp.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text")
    # Titan-style
    results = resp.get("results", [])
    if results and isinstance(results[0], dict):
        return results[0].get("outputText")
    # Llama-style
    if "generation" in resp:
        return resp["generation"]
    # Nova-style
    msg = resp.get("output", {}).get("message", {})
    for part in msg.get("content", []):
        if isinstance(part, dict) and "text" in part:
            return part["text"]
    # Mistral-on-Bedrock
    outputs = resp.get("outputs", [])
    if outputs and isinstance(outputs[0], dict):
        return outputs[0].get("text")
    # Cohere-on-Bedrock
    generations = resp.get("generations", [])
    if generations and isinstance(generations[0], dict):
        return generations[0].get("text")
    # AI21
    completions = resp.get("completions", [])
    if completions and isinstance(completions[0], dict):
        data = completions[0].get("data", {})
        if isinstance(data, dict):
            return data.get("text")
    return None


def _extract_model_id(url: str) -> str | None:
    """Model IDs arrive percent-encoded in the URL (e.g. %3A for ':')."""
    m = _MODEL_RE.search(url)
    return unquote(m.group(1)) if m else None

import functools
import time
from typing import Any
from uuid import uuid4

_PATCHED = False
_ORIGINALS: dict[str, Any] = {}


def install() -> None:
    global _PATCHED
    if _PATCHED:
        return
    try:
        import openai.resources.chat.completions as _mod
    except ImportError:
        return
    _ORIGINALS["sync_create"] = _mod.Completions.create
    _ORIGINALS["async_create"] = _mod.AsyncCompletions.create
    _mod.Completions.create = _wrap_sync(_ORIGINALS["sync_create"])  # type: ignore[method-assign]
    _mod.AsyncCompletions.create = _wrap_async(_ORIGINALS["async_create"])  # type: ignore[method-assign]
    _PATCHED = True


def uninstall() -> None:
    global _PATCHED
    if not _PATCHED:
        return
    try:
        import openai.resources.chat.completions as _mod
    except ImportError:
        return
    _mod.Completions.create = _ORIGINALS["sync_create"]  # type: ignore[method-assign]
    _mod.AsyncCompletions.create = _ORIGINALS["async_create"]  # type: ignore[method-assign]
    _ORIGINALS.clear()
    _PATCHED = False


_STRUCTURAL = {"model", "messages", "tools"}
_SDK_INTERNAL = {"extra_headers", "extra_query", "extra_body", "timeout"}


def _canonical_from_request(kwargs: dict) -> "Any":
    from agentdiff.capture.events import CanonicalLLMCall

    model = kwargs.get("model")
    raw_messages = kwargs.get("messages", [])

    system = None
    messages = []
    for m in raw_messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if role == "system":
            system = content
        else:
            messages.append(m if isinstance(m, dict) else {"role": role, "content": content})

    raw_tools = kwargs.get("tools")
    tools = None
    if raw_tools is not None:
        tools = [
            t if isinstance(t, dict) else {"type": getattr(t, "type", None)}
            for t in raw_tools
        ]

    sampling_params = {
        k: v for k, v in kwargs.items()
        if k not in _STRUCTURAL and k not in _SDK_INTERNAL and v is not None
    }

    return CanonicalLLMCall(
        provider="openai_chat",
        model=model,
        system=system,
        messages=messages,
        tools=tools,
        sampling_params=sampling_params,
    )


def _canonical_from_response(kwargs: dict, response: Any) -> "Any":
    from agentdiff.capture.events import CanonicalLLMCall
    import json

    req = _canonical_from_request(kwargs)
    response_text = None
    tool_use_blocks = []
    stop_reason = None
    usage: dict[str, int] = {}

    try:
        choices = getattr(response, "choices", [])
        if choices:
            first = choices[0]
            msg = getattr(first, "message", None)
            stop_reason = getattr(first, "finish_reason", None)
            if msg is not None:
                response_text = getattr(msg, "content", None)
                for tc in getattr(msg, "tool_calls", None) or []:
                    fn = getattr(tc, "function", None)
                    args = {}
                    if fn is not None:
                        try:
                            args = json.loads(getattr(fn, "arguments", "{}") or "{}")
                        except Exception:
                            pass
                    tool_use_blocks.append({
                        "tool_use_id": getattr(tc, "id", None),
                        "name": getattr(fn, "name", None) if fn else None,
                        "args": args,
                    })
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            inp = getattr(raw_usage, "prompt_tokens", 0) or 0
            out = getattr(raw_usage, "completion_tokens", 0) or 0
            total = getattr(raw_usage, "total_tokens", inp + out) or (inp + out)
            usage = {"input_tokens": inp, "output_tokens": out, "total_tokens": total}
    except Exception:
        pass

    return CanonicalLLMCall(
        provider="openai_chat",
        model=getattr(response, "model", req.model),
        system=req.system,
        messages=req.messages,
        tools=req.tools,
        sampling_params=req.sampling_params,
        response_text=response_text,
        tool_use_blocks=tool_use_blocks,
        stop_reason=stop_reason,
        usage=usage,
    )


def _record_error_response(tracer, call_id, kwargs, t0) -> None:
    """Record an is_error response when the SDK call raises (API error, timeout)."""
    from agentdiff.capture.events import LLMResponseEvent

    try:
        tracer.record(LLMResponseEvent(
            call_id=call_id,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            canonical=_canonical_from_request(kwargs),
            captured_by="sdk_shim",
            is_error=True,
        ))
    except Exception as exc:
        print(f"[agentdiff] openai shim error-capture error: {exc}")


def _wrap_sync(original):
    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        from agentdiff.capture.tracer import (
            get_active_tracer, set_sdk_shim_marker, reset_sdk_shim_marker,
        )
        from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent
        from agentdiff.capture.callstack import (
            capture_call_stack, classify_call_stack, callsite_from_stack,
        )

        tracer = get_active_tracer()
        if tracer is None:
            return original(self, *args, **kwargs)

        call_id = uuid4()

        try:
            stack = capture_call_stack(skip=1)
            inferred_agent = classify_call_stack(stack)
            callsite = callsite_from_stack(stack)
            tracer.record(LLMRequestEvent(
                call_id=call_id,
                canonical=_canonical_from_request(kwargs),
                captured_by="sdk_shim",
                sdk_method="openai.chat.completions.create",
                callsite=callsite,
                call_stack=stack,
                inferred_agent=inferred_agent,
            ))
        except Exception as exc:
            print(f"[agentdiff] openai shim request-capture error: {exc}")

        marker_token = set_sdk_shim_marker(True)
        t0 = time.perf_counter()
        try:
            response = original(self, *args, **kwargs)
        except Exception:
            _record_error_response(tracer, call_id, kwargs, t0)
            raise
        finally:
            reset_sdk_shim_marker(marker_token)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            tracer.record(LLMResponseEvent(
                call_id=call_id,
                latency_ms=latency_ms,
                canonical=_canonical_from_response(kwargs, response),
                captured_by="sdk_shim",
                is_error=False,
            ))
        except Exception as exc:
            print(f"[agentdiff] openai shim response-capture error: {exc}")

        return response
    return wrapper


def _wrap_async(original):
    @functools.wraps(original)
    async def wrapper(self, *args, **kwargs):
        from agentdiff.capture.tracer import (
            get_active_tracer, set_sdk_shim_marker, reset_sdk_shim_marker,
        )
        from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent
        from agentdiff.capture.callstack import (
            capture_call_stack, classify_call_stack, callsite_from_stack,
        )

        tracer = get_active_tracer()
        if tracer is None:
            return await original(self, *args, **kwargs)

        call_id = uuid4()

        try:
            stack = capture_call_stack(skip=1)
            inferred_agent = classify_call_stack(stack)
            callsite = callsite_from_stack(stack)
            tracer.record(LLMRequestEvent(
                call_id=call_id,
                canonical=_canonical_from_request(kwargs),
                captured_by="sdk_shim",
                sdk_method="openai.chat.completions.create",
                callsite=callsite,
                call_stack=stack,
                inferred_agent=inferred_agent,
            ))
        except Exception as exc:
            print(f"[agentdiff] openai shim async request-capture error: {exc}")

        marker_token = set_sdk_shim_marker(True)
        t0 = time.perf_counter()
        try:
            response = await original(self, *args, **kwargs)
        except Exception:
            _record_error_response(tracer, call_id, kwargs, t0)
            raise
        finally:
            reset_sdk_shim_marker(marker_token)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            tracer.record(LLMResponseEvent(
                call_id=call_id,
                latency_ms=latency_ms,
                canonical=_canonical_from_response(kwargs, response),
                captured_by="sdk_shim",
                is_error=False,
            ))
        except Exception as exc:
            print(f"[agentdiff] openai shim async response-capture error: {exc}")

        return response
    return wrapper

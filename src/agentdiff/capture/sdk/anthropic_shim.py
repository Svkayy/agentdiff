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
        import anthropic.resources.messages as _mod
    except ImportError:
        return
    _ORIGINALS["sync_create"] = _mod.Messages.create
    _ORIGINALS["async_create"] = _mod.AsyncMessages.create
    _mod.Messages.create = _wrap_sync(_ORIGINALS["sync_create"])  # type: ignore[method-assign]
    _mod.AsyncMessages.create = _wrap_async(_ORIGINALS["async_create"])  # type: ignore[method-assign]
    _PATCHED = True


def uninstall() -> None:
    global _PATCHED
    if not _PATCHED:
        return
    try:
        import anthropic.resources.messages as _mod
    except ImportError:
        return
    _mod.Messages.create = _ORIGINALS["sync_create"]  # type: ignore[method-assign]
    _mod.AsyncMessages.create = _ORIGINALS["async_create"]  # type: ignore[method-assign]
    _ORIGINALS.clear()
    _PATCHED = False


_STRUCTURAL = {"model", "messages", "system", "tools"}
_SDK_INTERNAL = {"extra_headers", "extra_query", "extra_body", "timeout"}


def _canonical_from_request(kwargs: dict) -> "Any":
    from agentdiff.capture.events import CanonicalLLMCall

    model = kwargs.get("model")

    raw_system = kwargs.get("system")
    if isinstance(raw_system, str):
        system = raw_system
    elif isinstance(raw_system, list):
        system = "\n".join(
            (b.get("text", "") if isinstance(b, dict) else getattr(b, "text", ""))
            for b in raw_system
        )
    else:
        system = None

    raw_messages = kwargs.get("messages", [])
    messages = [
        m if isinstance(m, dict) else {"role": getattr(m, "role", None), "content": getattr(m, "content", None)}
        for m in raw_messages
    ]

    raw_tools = kwargs.get("tools")
    tools = None
    if raw_tools is not None:
        tools = [
            t if isinstance(t, dict) else {"name": getattr(t, "name", None)}
            for t in raw_tools
        ]

    sampling_params = {
        k: v for k, v in kwargs.items()
        if k not in _STRUCTURAL and k not in _SDK_INTERNAL and v is not None
    }

    return CanonicalLLMCall(
        provider="anthropic",
        model=model,
        system=system,
        messages=messages,
        tools=tools,
        sampling_params=sampling_params,
    )


def _canonical_from_response(kwargs: dict, response: Any) -> "Any":
    from agentdiff.capture.events import CanonicalLLMCall

    req = _canonical_from_request(kwargs)
    response_text = None
    tool_use_blocks = []
    stop_reason = None
    usage: dict[str, int] = {}

    try:
        stop_reason = getattr(response, "stop_reason", None)
        for block in getattr(response, "content", []):
            btype = getattr(block, "type", None)
            if btype == "text":
                response_text = (response_text or "") + getattr(block, "text", "")
            elif btype == "tool_use":
                tool_use_blocks.append({
                    "tool_use_id": getattr(block, "id", None),
                    "name": getattr(block, "name", None),
                    "args": getattr(block, "input", {}),
                })
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            inp = getattr(raw_usage, "input_tokens", 0) or 0
            out = getattr(raw_usage, "output_tokens", 0) or 0
            usage = {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}
    except Exception:
        pass

    return CanonicalLLMCall(
        provider="anthropic",
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
        print(f"[agentdiff] anthropic shim error-capture error: {exc}")


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
                sdk_method="anthropic.messages.create",
                callsite=callsite,
                call_stack=stack,
                inferred_agent=inferred_agent,
            ))
        except Exception as exc:
            print(f"[agentdiff] anthropic shim request-capture error: {exc}")

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
            print(f"[agentdiff] anthropic shim response-capture error: {exc}")

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
                sdk_method="anthropic.messages.create",
                callsite=callsite,
                call_stack=stack,
                inferred_agent=inferred_agent,
            ))
        except Exception as exc:
            print(f"[agentdiff] anthropic shim async request-capture error: {exc}")

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
            print(f"[agentdiff] anthropic shim async response-capture error: {exc}")

        return response
    return wrapper

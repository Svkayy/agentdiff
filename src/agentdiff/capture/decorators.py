import functools
import inspect
import time
from typing import Any, Callable
from uuid import uuid4


def tool(fn: Callable | None = None, *, name: str | None = None):
    """
    Decorator for in-process tools dispatched from LLM tool_use blocks.
    Emits LocalToolInvokedEvent + LocalToolReturnedEvent when a Tracer is active.
    Transparent (zero overhead) when no Tracer is active.
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        sig = inspect.signature(func)

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                from agentdiff.capture.tracer import get_active_tracer
                from agentdiff.capture.events import LocalToolInvokedEvent
                from agentdiff.capture.callstack import (
                    capture_call_stack, classify_call_stack, callsite_from_stack,
                )

                tracer = get_active_tracer()
                if tracer is None:
                    return await func(*args, **kwargs)

                call_id = uuid4()
                arguments = _bind_arguments(sig, args, kwargs)

                try:
                    stack = capture_call_stack(skip=1)
                    callsite = callsite_from_stack(stack)
                    inferred_agent = classify_call_stack(stack)
                    tracer.record(LocalToolInvokedEvent(
                        call_id=call_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        callsite=callsite,
                        call_stack=stack,
                        inferred_agent=inferred_agent,
                    ))
                except Exception as exc:
                    print(f"[agentdiff] tool decorator invoke-capture error: {exc}")

                t0 = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    _record_returned(tracer, call_id, latency_ms, str(exc), is_error=True)
                    raise
                latency_ms = int((time.perf_counter() - t0) * 1000)
                _record_returned(tracer, call_id, latency_ms, result, is_error=False)
                return result

            return async_wrapper

        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                from agentdiff.capture.tracer import get_active_tracer
                from agentdiff.capture.events import LocalToolInvokedEvent
                from agentdiff.capture.callstack import (
                    capture_call_stack, classify_call_stack, callsite_from_stack,
                )

                tracer = get_active_tracer()
                if tracer is None:
                    return func(*args, **kwargs)

                call_id = uuid4()
                arguments = _bind_arguments(sig, args, kwargs)

                try:
                    stack = capture_call_stack(skip=1)
                    callsite = callsite_from_stack(stack)
                    inferred_agent = classify_call_stack(stack)
                    tracer.record(LocalToolInvokedEvent(
                        call_id=call_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        callsite=callsite,
                        call_stack=stack,
                        inferred_agent=inferred_agent,
                    ))
                except Exception as exc:
                    print(f"[agentdiff] tool decorator invoke-capture error: {exc}")

                t0 = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                except Exception as exc:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    _record_returned(tracer, call_id, latency_ms, str(exc), is_error=True)
                    raise
                latency_ms = int((time.perf_counter() - t0) * 1000)
                _record_returned(tracer, call_id, latency_ms, result, is_error=False)
                return result

            return sync_wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


def _bind_arguments(sig: inspect.Signature, args: tuple, kwargs: dict) -> dict[str, Any]:
    try:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        return dict(kwargs)


def _record_returned(tracer, call_id, latency_ms, output, *, is_error: bool) -> None:
    from agentdiff.capture.events import LocalToolReturnedEvent
    try:
        tracer.record(LocalToolReturnedEvent(
            call_id=call_id,
            latency_ms=latency_ms,
            output=output,
            is_error=is_error,
        ))
    except Exception as exc:
        print(f"[agentdiff] tool decorator return-capture error: {exc}")

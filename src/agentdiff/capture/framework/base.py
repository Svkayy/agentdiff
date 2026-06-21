import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from agentdiff.capture.callstack import (
    callsite_from_stack,
    capture_call_stack,
    classify_call_stack,
)
from agentdiff.capture.events import FrameworkEvent
from agentdiff.capture.tracer import get_active_tracer


class PatchRegistry:
    """Track reversible monkey patches for one optional adapter."""

    def __init__(self, adapter_name: str):
        self.adapter_name = adapter_name
        self._patches: list[tuple[Any, str, Any]] = []

    def patch_method(self, owner: Any, method_name: str, wrapper_factory: Callable[[Any], Any]) -> bool:
        original = getattr(owner, method_name, None)
        if original is None or not callable(original):
            return False
        if getattr(original, "_agentdiff_adapter", None) == self.adapter_name:
            return False

        wrapped = wrapper_factory(original)
        setattr(wrapped, "_agentdiff_adapter", self.adapter_name)
        try:
            setattr(owner, method_name, wrapped)
        except Exception:
            return False
        self._patches.append((owner, method_name, original))
        return True

    def uninstall(self) -> None:
        for owner, method_name, original in reversed(self._patches):
            try:
                setattr(owner, method_name, original)
            except Exception:
                pass
        self._patches.clear()


def record_framework_event(
    *,
    framework: str,
    kind: str,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    call_id: UUID | None = None,
    skip: int = 2,
) -> UUID:
    """Record a framework event if a tracer is active and return its call id."""
    event_call_id = call_id or uuid4()
    tracer = get_active_tracer()
    if tracer is None:
        return event_call_id
    try:
        stack = capture_call_stack(skip=skip)
        tracer.record(
            FrameworkEvent(
                call_id=event_call_id,
                framework=framework,
                kind=kind,
                name=name,
                metadata=_json_safe_dict(metadata or {}),
                callsite=callsite_from_stack(stack),
                call_stack=stack,
                inferred_agent=classify_call_stack(stack),
            )
        )
    except Exception as exc:
        print(f"[agentdiff] {framework} adapter event-capture error: {exc}")
    return event_call_id


def span_wrapper(
    *,
    framework: str,
    kind: str,
    name_getter: Callable[[Any, tuple[Any, ...], dict[str, Any]], str | None],
    metadata_getter: Callable[[Any, tuple[Any, ...], dict[str, Any]], dict[str, Any]] | None = None,
) -> Callable[[Any], Any]:
    """Build a sync/async method wrapper that records start/end framework events."""

    def factory(original):
        if inspect.iscoroutinefunction(original):

            @functools.wraps(original)
            async def async_wrapper(self, *args, **kwargs):
                name = _safe_name(name_getter, self, args, kwargs)
                metadata = _safe_metadata(metadata_getter, self, args, kwargs)
                call_id = record_framework_event(
                    framework=framework,
                    kind=f"{kind}_start",
                    name=name,
                    metadata=metadata,
                    skip=2,
                )
                try:
                    result = await original(self, *args, **kwargs)
                except Exception as exc:
                    record_framework_event(
                        framework=framework,
                        kind=f"{kind}_end",
                        name=name,
                        metadata={**metadata, "is_error": True, "error": repr(exc)},
                        call_id=call_id,
                        skip=2,
                    )
                    raise
                record_framework_event(
                    framework=framework,
                    kind=f"{kind}_end",
                    name=name,
                    metadata={**metadata, "is_error": False},
                    call_id=call_id,
                    skip=2,
                )
                return result

            return async_wrapper

        @functools.wraps(original)
        def sync_wrapper(self, *args, **kwargs):
            name = _safe_name(name_getter, self, args, kwargs)
            metadata = _safe_metadata(metadata_getter, self, args, kwargs)
            call_id = record_framework_event(
                framework=framework,
                kind=f"{kind}_start",
                name=name,
                metadata=metadata,
                skip=2,
            )
            try:
                result = original(self, *args, **kwargs)
            except Exception as exc:
                record_framework_event(
                    framework=framework,
                    kind=f"{kind}_end",
                    name=name,
                    metadata={**metadata, "is_error": True, "error": repr(exc)},
                    call_id=call_id,
                    skip=2,
                )
                raise
            if inspect.isawaitable(result):
                return _await_with_end(result, framework, kind, name, metadata, call_id)
            record_framework_event(
                framework=framework,
                kind=f"{kind}_end",
                name=name,
                metadata={**metadata, "is_error": False},
                call_id=call_id,
                skip=2,
            )
            return result

        return sync_wrapper

    return factory


async def _await_with_end(
    awaitable: Awaitable[Any],
    framework: str,
    kind: str,
    name: str | None,
    metadata: dict[str, Any],
    call_id: UUID,
) -> Any:
    try:
        result = await awaitable
    except Exception as exc:
        record_framework_event(
            framework=framework,
            kind=f"{kind}_end",
            name=name,
            metadata={**metadata, "is_error": True, "error": repr(exc)},
            call_id=call_id,
            skip=2,
        )
        raise
    record_framework_event(
        framework=framework,
        kind=f"{kind}_end",
        name=name,
        metadata={**metadata, "is_error": False},
        call_id=call_id,
        skip=2,
    )
    return result


def object_name(obj: Any, fallback: str | None = None) -> str | None:
    for attr in ("name", "id", "role", "description"):
        value = getattr(obj, attr, None)
        if value:
            return str(value)[:200]
    if fallback:
        return fallback
    return obj.__class__.__name__ if obj is not None else None


def call_metadata(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "arg_count": len(args),
        "kwarg_keys": sorted(str(k) for k in kwargs.keys()),
    }


def _safe_name(
    getter: Callable[[Any, tuple[Any, ...], dict[str, Any]], str | None],
    self: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str | None:
    try:
        return getter(self, args, kwargs)
    except Exception:
        return object_name(self)


def _safe_metadata(
    getter: Callable[[Any, tuple[Any, ...], dict[str, Any]], dict[str, Any]] | None,
    self: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    base = call_metadata(args, kwargs)
    if getter is None:
        return base
    try:
        custom = getter(self, args, kwargs)
    except Exception:
        return base
    return {**base, **(custom or {})}


def _json_safe_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _json_safe(v) for k, v in data.items()}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in list(value)[:50]]
    return repr(value)[:500]

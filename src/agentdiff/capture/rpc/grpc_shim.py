import functools
import inspect

from agentdiff.capture.framework.base import PatchRegistry, record_framework_event

_PATCHES = PatchRegistry("grpc")


def install() -> None:
    try:
        import grpc
    except ImportError:
        return

    UnaryUnary = getattr(grpc, "UnaryUnaryMultiCallable", None)
    UnaryStream = getattr(grpc, "UnaryStreamMultiCallable", None)
    StreamUnary = getattr(grpc, "StreamUnaryMultiCallable", None)
    StreamStream = getattr(grpc, "StreamStreamMultiCallable", None)
    for cls, kind in (
        (UnaryUnary, "grpc_unary_unary"),
        (UnaryStream, "grpc_unary_stream"),
        (StreamUnary, "grpc_stream_unary"),
        (StreamStream, "grpc_stream_stream"),
    ):
        if cls is not None:
            _PATCHES.patch_method(cls, "__call__", _wrap_call(kind))

    aio = getattr(grpc, "aio", None)
    for class_name, kind in (
        ("UnaryUnaryMultiCallable", "grpc_aio_unary_unary"),
        ("UnaryStreamMultiCallable", "grpc_aio_unary_stream"),
        ("StreamUnaryMultiCallable", "grpc_aio_stream_unary"),
        ("StreamStreamMultiCallable", "grpc_aio_stream_stream"),
    ):
        cls = getattr(aio, class_name, None) if aio is not None else None
        if cls is not None:
            _PATCHES.patch_method(cls, "__call__", _wrap_call(kind))


def uninstall() -> None:
    _PATCHES.uninstall()


def _wrap_call(kind: str):
    def factory(original):
        if inspect.iscoroutinefunction(original):

            @functools.wraps(original)
            async def async_wrapper(self, *args, **kwargs):
                return await _run_async(original, self, args, kwargs, kind)

            return async_wrapper

        @functools.wraps(original)
        def sync_wrapper(self, *args, **kwargs):
            call_id = _record_start(self, args, kwargs, kind)
            try:
                result = original(self, *args, **kwargs)
            except Exception as exc:
                _record_end(self, kind, call_id, is_error=True, error=repr(exc))
                raise
            _record_end(self, kind, call_id, is_error=False)
            return result

        return sync_wrapper

    return factory


async def _run_async(original, self, args, kwargs, kind: str):
    call_id = _record_start(self, args, kwargs, kind)
    try:
        result = await original(self, *args, **kwargs)
    except Exception as exc:
        _record_end(self, kind, call_id, is_error=True, error=repr(exc))
        raise
    _record_end(self, kind, call_id, is_error=False)
    return result


def _record_start(self, args, kwargs, kind: str):
    method = _method_name(self)
    return record_framework_event(
        framework="grpc",
        kind=f"{kind}_start",
        name=method,
        metadata={
            "method": method,
            "arg_count": len(args),
            "kwarg_keys": sorted(str(k) for k in kwargs.keys()),
        },
        skip=2,
    )


def _record_end(self, kind: str, call_id, *, is_error: bool, error: str | None = None) -> None:
    metadata = {"method": _method_name(self), "is_error": is_error}
    if error:
        metadata["error"] = error
    record_framework_event(
        framework="grpc",
        kind=f"{kind}_end",
        name=metadata["method"],
        metadata=metadata,
        call_id=call_id,
        skip=2,
    )


def _method_name(callable_obj) -> str | None:
    for attr in ("_method", "_name"):
        value = getattr(callable_obj, attr, None)
        if value:
            try:
                return value.decode() if isinstance(value, bytes) else str(value)
            except Exception:
                return str(value)
    return callable_obj.__class__.__name__

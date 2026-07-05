import functools
import time
from uuid import uuid4

from agentdiff.capture.tracer import get_active_tracer
from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent
from agentdiff.capture.callstack import (
    capture_call_stack,
    classify_call_stack,
    callsite_from_stack,
)
from agentdiff.capture.http.provider_registry import match_provider
from agentdiff.capture.http.canonical import build_canonical_from_http
from agentdiff.capture.http.redact import (
    get_active_redaction_config,
    redact_body,
    redact_canonical,
    redact_headers,
    redact_url,
)
from agentdiff.capture.http.streaming import record_stream_chunks
from agentdiff.capture.cassette import active_cassette

_PATCHED = False
_ORIGINALS: dict[str, object] = {}


def install() -> None:
    global _PATCHED
    if _PATCHED:
        return
    try:
        import httpx
    except ImportError:
        return
    _ORIGINALS["sync_send"] = httpx.Client.send
    _ORIGINALS["async_send"] = httpx.AsyncClient.send
    httpx.Client.send = _wrap_sync(_ORIGINALS["sync_send"])  # type: ignore[method-assign]
    httpx.AsyncClient.send = _wrap_async(_ORIGINALS["async_send"])  # type: ignore[method-assign]
    _PATCHED = True


def uninstall() -> None:
    global _PATCHED
    if not _PATCHED:
        return
    try:
        import httpx
    except ImportError:
        return
    httpx.Client.send = _ORIGINALS["sync_send"]  # type: ignore[method-assign,assignment]
    httpx.AsyncClient.send = _ORIGINALS["async_send"]  # type: ignore[method-assign,assignment]
    _ORIGINALS.clear()
    _PATCHED = False


def _wrap_sync(original):
    @functools.wraps(original)
    def wrapper(self, request, *args, **kwargs):
        tracer = get_active_tracer()
        if tracer is None:
            return original(self, request, *args, **kwargs)
        return _capture_sync(tracer, original, self, request, args, kwargs)
    return wrapper


def _wrap_async(original):
    @functools.wraps(original)
    async def wrapper(self, request, *args, **kwargs):
        tracer = get_active_tracer()
        if tracer is None:
            return await original(self, request, *args, **kwargs)
        return await _capture_async(tracer, original, self, request, args, kwargs)
    return wrapper


def _capture_sync(tracer, original, self_client, request, args, kwargs):
    provider = match_provider(str(request.url))
    call_id = uuid4()
    redaction_cfg = get_active_redaction_config()

    try:
        # skip=1 to drop this _capture_sync frame.
        stack = capture_call_stack(skip=1)
        inferred_agent = classify_call_stack(stack)
        callsite = callsite_from_stack(stack)

        canonical_req = redact_canonical(
            build_canonical_from_http(provider, request, response=None), redaction_cfg
        )
        tracer.record(LLMRequestEvent(
            call_id=call_id,
            canonical=canonical_req,
            captured_by="http_shim",
            request_url=redact_url(str(request.url)),
            raw_body=_unknown_raw_body(bytes(request.content), provider, redaction_cfg),
            callsite=callsite,
            call_stack=stack,
            inferred_agent=inferred_agent,
        ))
    except Exception as exc:
        print(f"[agentdiff] httpx shim request-capture error: {exc}")

    t0 = time.perf_counter()
    cassette = active_cassette()
    try:
        if cassette is not None and cassette.mode == "replay":
            recorded = cassette.lookup(request.method, str(request.url), bytes(request.content))
            import httpx
            response = httpx.Response(
                recorded.status_code,
                headers=recorded.headers,
                content=recorded.body,
                request=request,
            )
        else:
            response = original(self_client, request, *args, **kwargs)
    except Exception:
        # Transport/timeout failure: record an error response so the trajectory
        # shows the failed call instead of a dangling request, then re-raise.
        _record_transport_error(tracer, provider, request, call_id, t0)
        raise
    latency_ms = int((time.perf_counter() - t0) * 1000)

    try:
        body = response.read()
        if cassette is not None and cassette.mode == "record":
            cassette.record(
                method=request.method,
                url=str(request.url),
                body=bytes(request.content),
                status_code=response.status_code,
                headers=redact_headers(dict(response.headers), redaction_cfg),
                response_body=body,
            )
        canonical_resp = redact_canonical(
            build_canonical_from_http(provider, request, response=(response, body)),
            redaction_cfg,
        )
        tracer.record(LLMResponseEvent(
            call_id=call_id,
            latency_ms=latency_ms,
            canonical=canonical_resp,
            captured_by="http_shim",
            raw_body=_unknown_raw_body(body, provider, redaction_cfg),
            is_error=(response.status_code >= 400),
        ))
        record_stream_chunks(tracer, call_id=call_id, provider=provider, body=body)
    except Exception as exc:
        print(f"[agentdiff] httpx shim response-capture error: {exc}")

    return response


def _record_transport_error(tracer, provider, request, call_id, t0) -> None:
    try:
        tracer.record(LLMResponseEvent(
            call_id=call_id,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            canonical=redact_canonical(
                build_canonical_from_http(provider, request, response=None),
                get_active_redaction_config(),
            ),
            captured_by="http_shim",
            is_error=True,
        ))
    except Exception as exc:
        print(f"[agentdiff] httpx shim error-capture error: {exc}")


def _unknown_raw_body(body: bytes, provider: str, cfg) -> bytes | None:
    """Raw body storage: unknown-provider only, and only when opted in.

    ``capture_raw_bodies=True`` still runs the body through ``redact_body``
    first — opting in to raw capture is not an opt-out of secret masking.
    """
    if provider != "unknown" or not cfg.capture_raw_bodies:
        return None
    return redact_body(body, cfg)


async def _capture_async(tracer, original, self_client, request, args, kwargs):
    provider = match_provider(str(request.url))
    call_id = uuid4()
    redaction_cfg = get_active_redaction_config()

    try:
        stack = capture_call_stack(skip=1)
        inferred_agent = classify_call_stack(stack)
        callsite = callsite_from_stack(stack)

        canonical_req = redact_canonical(
            build_canonical_from_http(provider, request, response=None), redaction_cfg
        )
        tracer.record(LLMRequestEvent(
            call_id=call_id,
            canonical=canonical_req,
            captured_by="http_shim",
            request_url=redact_url(str(request.url)),
            raw_body=_unknown_raw_body(bytes(request.content), provider, redaction_cfg),
            callsite=callsite,
            call_stack=stack,
            inferred_agent=inferred_agent,
        ))
    except Exception as exc:
        print(f"[agentdiff] httpx async shim request-capture error: {exc}")

    t0 = time.perf_counter()
    cassette = active_cassette()
    try:
        if cassette is not None and cassette.mode == "replay":
            recorded = cassette.lookup(request.method, str(request.url), bytes(request.content))
            import httpx
            response = httpx.Response(
                recorded.status_code,
                headers=recorded.headers,
                content=recorded.body,
                request=request,
            )
        else:
            response = await original(self_client, request, *args, **kwargs)
    except Exception:
        _record_transport_error(tracer, provider, request, call_id, t0)
        raise
    latency_ms = int((time.perf_counter() - t0) * 1000)

    try:
        body = await response.aread()
        if cassette is not None and cassette.mode == "record":
            cassette.record(
                method=request.method,
                url=str(request.url),
                body=bytes(request.content),
                status_code=response.status_code,
                headers=redact_headers(dict(response.headers), redaction_cfg),
                response_body=body,
            )
        canonical_resp = redact_canonical(
            build_canonical_from_http(provider, request, response=(response, body)),
            redaction_cfg,
        )
        tracer.record(LLMResponseEvent(
            call_id=call_id,
            latency_ms=latency_ms,
            canonical=canonical_resp,
            captured_by="http_shim",
            raw_body=_unknown_raw_body(body, provider, redaction_cfg),
            is_error=(response.status_code >= 400),
        ))
        record_stream_chunks(tracer, call_id=call_id, provider=provider, body=body)
    except Exception as exc:
        print(f"[agentdiff] httpx async shim response-capture error: {exc}")

    return response

import functools
import json
import time
from uuid import uuid4

from agentdiff.capture.callstack import (
    callsite_from_stack,
    capture_call_stack,
    classify_call_stack,
)
from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent
from agentdiff.capture.http.canonical import build_canonical_from_http
from agentdiff.capture.http.provider_registry import match_provider
from agentdiff.capture.http.streaming import record_stream_chunks
from agentdiff.capture.tracer import get_active_tracer

_PATCHED = False
_ORIGINALS: dict[str, object] = {}


def install() -> None:
    global _PATCHED
    if _PATCHED:
        return
    try:
        import aiohttp
    except ImportError:
        return
    _ORIGINALS["request"] = aiohttp.ClientSession._request
    aiohttp.ClientSession._request = _wrap(_ORIGINALS["request"])  # type: ignore[method-assign]
    _PATCHED = True


def uninstall() -> None:
    global _PATCHED
    if not _PATCHED:
        return
    try:
        import aiohttp
    except ImportError:
        return
    aiohttp.ClientSession._request = _ORIGINALS["request"]  # type: ignore[method-assign]
    _ORIGINALS.clear()
    _PATCHED = False


def _wrap(original):
    @functools.wraps(original)
    async def wrapper(self, method, url, *args, **kwargs):
        tracer = get_active_tracer()
        if tracer is None:
            return await original(self, method, url, *args, **kwargs)
        return await _capture(tracer, original, self, method, url, args, kwargs)

    return wrapper


async def _capture(tracer, original, session, method, url, args, kwargs):
    url_str = str(url)
    provider = match_provider(url_str)
    call_id = uuid4()
    request = _AiohttpRequestAdapter(url_str, _request_body(kwargs))

    try:
        stack = capture_call_stack(skip=1)
        inferred_agent = classify_call_stack(stack)
        tracer.record(
            LLMRequestEvent(
                call_id=call_id,
                canonical=build_canonical_from_http(provider, request, response=None),
                captured_by="http_shim",
                request_url=url_str,
                raw_body=request.content if provider == "unknown" else None,
                callsite=callsite_from_stack(stack),
                call_stack=stack,
                inferred_agent=inferred_agent,
            )
        )
    except Exception as exc:
        print(f"[agentdiff] aiohttp shim request-capture error: {exc}")

    t0 = time.perf_counter()
    try:
        response = await original(session, method, url, *args, **kwargs)
    except Exception:
        _record_transport_error(tracer, provider, request, call_id, t0)
        raise
    latency_ms = int((time.perf_counter() - t0) * 1000)

    try:
        body = await response.read()
        tracer.record(
            LLMResponseEvent(
                call_id=call_id,
                latency_ms=latency_ms,
                canonical=build_canonical_from_http(
                    provider, request, response=(_AiohttpResponseAdapter(response), body)
                ),
                captured_by="http_shim",
                raw_body=body if provider == "unknown" else None,
                is_error=(response.status >= 400),
            )
        )
        record_stream_chunks(tracer, call_id=call_id, provider=provider, body=body)
    except Exception as exc:
        print(f"[agentdiff] aiohttp shim response-capture error: {exc}")

    return response


def _record_transport_error(tracer, provider, request, call_id, t0) -> None:
    try:
        tracer.record(
            LLMResponseEvent(
                call_id=call_id,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                canonical=build_canonical_from_http(provider, request, response=None),
                captured_by="http_shim",
                is_error=True,
            )
        )
    except Exception as exc:
        print(f"[agentdiff] aiohttp shim error-capture error: {exc}")


def _request_body(kwargs: dict) -> bytes:
    if "json" in kwargs:
        try:
            return json.dumps(kwargs["json"]).encode()
        except Exception:
            return b""
    body = kwargs.get("data")
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode()
    try:
        return bytes(body)
    except Exception:
        return b""


class _AiohttpRequestAdapter:
    def __init__(self, url: str, content: bytes):
        self.url = url
        self.content = content


class _AiohttpResponseAdapter:
    def __init__(self, response):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status

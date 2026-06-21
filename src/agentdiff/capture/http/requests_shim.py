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
from agentdiff.capture.http.redact import redact_url
from agentdiff.capture.http.streaming import record_stream_chunks

_PATCHED = False
_ORIGINALS: dict[str, object] = {}


def install() -> None:
    global _PATCHED
    if _PATCHED:
        return
    try:
        from requests.adapters import HTTPAdapter
    except ImportError:
        return
    _ORIGINALS["send"] = HTTPAdapter.send
    HTTPAdapter.send = _wrap(_ORIGINALS["send"])  # type: ignore[method-assign]
    _PATCHED = True


def uninstall() -> None:
    global _PATCHED
    if not _PATCHED:
        return
    try:
        from requests.adapters import HTTPAdapter
    except ImportError:
        return
    HTTPAdapter.send = _ORIGINALS["send"]  # type: ignore[method-assign]
    _ORIGINALS.clear()
    _PATCHED = False


def _wrap(original):
    @functools.wraps(original)
    def wrapper(self, request, *args, **kwargs):
        tracer = get_active_tracer()
        if tracer is None:
            return original(self, request, *args, **kwargs)
        return _capture(tracer, original, self, request, args, kwargs)
    return wrapper


def _capture(tracer, original, self_adapter, request, args, kwargs):
    url = request.url or ""
    provider = match_provider(url)
    call_id = uuid4()

    # requests.PreparedRequest doesn't have .content like httpx.Request.
    # We need to adapt to the requests API.
    try:
        stack = capture_call_stack(skip=1)
        inferred_agent = classify_call_stack(stack)
        callsite = callsite_from_stack(stack)

        # Build a lightweight adapter so the canonical parser can call bytes(req.content).
        req_adapter = _RequestsRequestAdapter(request)
        canonical_req = build_canonical_from_http(provider, req_adapter, response=None)
        tracer.record(LLMRequestEvent(
            call_id=call_id,
            canonical=canonical_req,
            captured_by="http_shim",
            request_url=redact_url(url),
            raw_body=_get_request_body(request) if provider == "unknown" else None,
            callsite=callsite,
            call_stack=stack,
            inferred_agent=inferred_agent,
        ))
    except Exception as exc:
        print(f"[agentdiff] requests shim request-capture error: {exc}")

    t0 = time.perf_counter()
    try:
        response = original(self_adapter, request, *args, **kwargs)
    except Exception:
        # Record the failed call (is_error) so the trajectory isn't left with a
        # dangling request, then let the exception propagate to the caller.
        try:
            tracer.record(LLMResponseEvent(
                call_id=call_id,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                canonical=build_canonical_from_http(
                    provider, _RequestsRequestAdapter(request), response=None
                ),
                captured_by="http_shim",
                is_error=True,
            ))
        except Exception as exc:
            print(f"[agentdiff] requests shim error-capture error: {exc}")
        raise
    latency_ms = int((time.perf_counter() - t0) * 1000)

    try:
        body = response.content  # requests always reads fully
        resp_adapter = _RequestsRequestAdapter(request)
        canonical_resp = build_canonical_from_http(
            provider, resp_adapter, response=(_RequestsResponseAdapter(response), body)
        )
        tracer.record(LLMResponseEvent(
            call_id=call_id,
            latency_ms=latency_ms,
            canonical=canonical_resp,
            captured_by="http_shim",
            raw_body=body if provider == "unknown" else None,
            is_error=(response.status_code >= 400),
        ))
        record_stream_chunks(tracer, call_id=call_id, provider=provider, body=body)
    except Exception as exc:
        print(f"[agentdiff] requests shim response-capture error: {exc}")

    return response


def _get_request_body(request) -> bytes | None:
    try:
        body = request.body
        if body is None:
            return None
        if isinstance(body, bytes):
            return body
        if isinstance(body, str):
            return body.encode()
        return bytes(body)
    except Exception:
        return None


class _RequestsRequestAdapter:
    """Adapts a requests.PreparedRequest to expose `.content` and `.url` like httpx.Request.

    Parsers keyed on the URL (bedrock, gemini, azure_openai) call ``str(request.url)``,
    so the adapter must surface ``.url`` too — otherwise those parsers raise and the
    call silently degrades to an unparsed 'unknown' canonical.
    """

    def __init__(self, prepared_request):
        self._req = prepared_request

    @property
    def url(self) -> str:
        return self._req.url or ""

    @property
    def content(self) -> bytes:
        body = self._req.body
        if body is None:
            return b""
        if isinstance(body, bytes):
            return body
        if isinstance(body, str):
            return body.encode()
        return b""


class _RequestsResponseAdapter:
    """Minimal adapter so parsers can work on requests responses."""

    def __init__(self, response):
        self._resp = response

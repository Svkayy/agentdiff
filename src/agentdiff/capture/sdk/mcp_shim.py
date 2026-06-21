import functools
import json
import time
from typing import Any
from uuid import uuid4

_PATCHED = False
_ORIGINALS: dict[str, Any] = {}


def _safe_output(result: Any) -> Any:
    """Coerce an MCP CallToolResult (or anything) into a JSON-serializable value.

    The trajectory is serialized via ``model_dump_json``; an arbitrary object in
    ``MCPToolReturnedEvent.output`` would break that. Pydantic results dump to JSON;
    anything else falls back to its string form.
    """
    if result is None:
        return None
    dump = getattr(result, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except Exception:
            try:
                return dump()
            except Exception:
                pass
    try:
        json.dumps(result)
        return result
    except (TypeError, ValueError):
        return str(result)


def install() -> None:
    global _PATCHED
    if _PATCHED:
        return
    try:
        from mcp.client.session import ClientSession
    except ImportError:
        return
    _ORIGINALS["call_tool"] = ClientSession.call_tool
    ClientSession.call_tool = _wrap_async(_ORIGINALS["call_tool"])  # type: ignore[method-assign]
    _PATCHED = True


def uninstall() -> None:
    global _PATCHED
    if not _PATCHED:
        return
    try:
        from mcp.client.session import ClientSession
    except ImportError:
        return
    ClientSession.call_tool = _ORIGINALS["call_tool"]  # type: ignore[method-assign]
    _ORIGINALS.clear()
    _PATCHED = False


def _wrap_async(original):
    @functools.wraps(original)
    async def wrapper(self, name, arguments=None, **kwargs):
        from agentdiff.capture.tracer import get_active_tracer
        from agentdiff.capture.events import MCPToolInvokedEvent, MCPToolReturnedEvent
        from agentdiff.capture.callstack import (
            capture_call_stack, classify_call_stack, callsite_from_stack,
        )

        tracer = get_active_tracer()
        if tracer is None:
            return await original(self, name, arguments, **kwargs)

        call_id = uuid4()

        try:
            stack = capture_call_stack(skip=1)
            inferred_agent = classify_call_stack(stack)
            callsite = callsite_from_stack(stack)
            server_name = getattr(getattr(self, "_session", None), "name", None)
            tracer.record(MCPToolInvokedEvent(
                call_id=call_id,
                server_name=server_name,
                tool_name=name,
                arguments=arguments or {},
                callsite=callsite,
                call_stack=stack,
                inferred_agent=inferred_agent,
            ))
        except Exception as exc:
            print(f"[agentdiff] mcp shim invoke-capture error: {exc}")

        t0 = time.perf_counter()
        is_error = False
        try:
            result = await original(self, name, arguments, **kwargs)
        except Exception:
            is_error = True
            raise
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            try:
                output = None if is_error else _safe_output(result)
                tracer.record(MCPToolReturnedEvent(
                    call_id=call_id,
                    latency_ms=latency_ms,
                    output=output,
                    is_error=is_error,
                ))
            except Exception as exc:
                print(f"[agentdiff] mcp shim return-capture error: {exc}")

        return result
    return wrapper

"""Day 2 smoke tests: SDK shim dedup, @agentdiff.tool, MCP capture."""
from pathlib import Path

import httpx
import pytest
import respx

import agentdiff
from agentdiff.capture.tracer import Tracer, set_sdk_shim_marker, reset_sdk_shim_marker
from agentdiff.capture.events import (
    LLMRequestEvent,
    LLMResponseEvent,
    LocalToolInvokedEvent,
    LocalToolReturnedEvent,
    MCPToolInvokedEvent,
    MCPToolReturnedEvent,
)
from agentdiff.trajectory import Trajectory


@pytest.fixture(autouse=True)
def shims():
    agentdiff.install()
    yield
    agentdiff.uninstall()


def _load_trajectory(path: Path) -> Trajectory:
    line = path.read_text().strip().splitlines()[0]
    return Trajectory.model_validate_json(line)


_ANTHROPIC_RESPONSE = {
    "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
    "type": "message",
    "role": "assistant",
    "model": "claude-3-5-sonnet-20241022",
    "content": [{"type": "text", "text": "Hello from Claude!"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 4},
}

_ANTHROPIC_REQUEST_BODY = {
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Say hello"}],
}


# ---------------------------------------------------------------------------
# Dedup: _sdk_shim_marker suppresses HTTP shim events
# ---------------------------------------------------------------------------

def test_http_events_suppressed_when_sdk_marker_set(tmp_path):
    """HTTP events recorded while _sdk_shim_marker=True must be dropped at flush."""
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
        )
        with Tracer("tc_dedup", "baseline", {}, output):
            token = set_sdk_shim_marker(True)
            try:
                client = httpx.Client()
                client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=_ANTHROPIC_REQUEST_BODY,
                )
            finally:
                reset_sdk_shim_marker(token)

    traj = _load_trajectory(output)
    http_events = [e for e in traj.events if getattr(e, "captured_by", None) == "http_shim"]
    assert len(http_events) == 0
    assert len(traj.events) == 0  # no SDK events recorded manually either


def test_http_events_present_without_marker(tmp_path):
    """Without the SDK marker, HTTP shim events flow through normally."""
    output = tmp_path / "traces.jsonl"

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
        )
        with Tracer("tc_no_dedup", "baseline", {}, output):
            client = httpx.Client()
            client.post("https://api.anthropic.com/v1/messages", json=_ANTHROPIC_REQUEST_BODY)

    traj = _load_trajectory(output)
    http_events = [e for e in traj.events if getattr(e, "captured_by", None) == "http_shim"]
    assert len(http_events) == 2  # request + response


def test_marker_resets_after_exception(tmp_path):
    """_sdk_shim_marker is always reset even if the guarded block raises."""
    from agentdiff.capture.tracer import get_sdk_shim_marker

    output = tmp_path / "traces.jsonl"

    with Tracer("tc_marker_reset", "baseline", {}, output):
        token = set_sdk_shim_marker(True)
        assert get_sdk_shim_marker() is True
        try:
            raise RuntimeError("simulated error")
        except RuntimeError:
            pass
        finally:
            reset_sdk_shim_marker(token)

    assert get_sdk_shim_marker() is False


# ---------------------------------------------------------------------------
# @agentdiff.tool — sync
# ---------------------------------------------------------------------------

def test_local_tool_sync_capture(tmp_path):
    output = tmp_path / "traces.jsonl"

    @agentdiff.tool
    def search(query: str, max_results: int = 5) -> str:
        return f"Results for: {query}"

    with Tracer("tc_tool_sync", "baseline", {}, output):
        result = search(query="hello", max_results=3)

    assert result == "Results for: hello"

    traj = _load_trajectory(output)
    invoked = [e for e in traj.events if isinstance(e, LocalToolInvokedEvent)]
    returned = [e for e in traj.events if isinstance(e, LocalToolReturnedEvent)]

    assert len(invoked) == 1
    assert len(returned) == 1
    assert invoked[0].tool_name == "search"
    assert invoked[0].arguments == {"query": "hello", "max_results": 3}
    assert returned[0].output == "Results for: hello"
    assert returned[0].is_error is False
    assert invoked[0].call_id == returned[0].call_id


def test_local_tool_positional_args(tmp_path):
    output = tmp_path / "traces.jsonl"

    @agentdiff.tool
    def add(a: int, b: int) -> int:
        return a + b

    with Tracer("tc_tool_pos", "baseline", {}, output):
        result = add(2, 3)

    assert result == 5
    traj = _load_trajectory(output)
    invoked = [e for e in traj.events if isinstance(e, LocalToolInvokedEvent)]
    assert invoked[0].arguments == {"a": 2, "b": 3}


def test_local_tool_captures_error(tmp_path):
    output = tmp_path / "traces.jsonl"

    @agentdiff.tool
    def broken() -> str:
        raise ValueError("something went wrong")

    with pytest.raises(ValueError):
        with Tracer("tc_tool_err", "baseline", {}, output):
            broken()

    traj = _load_trajectory(output)
    returned = [e for e in traj.events if isinstance(e, LocalToolReturnedEvent)]
    assert len(returned) == 1
    assert returned[0].is_error is True


def test_local_tool_no_tracer_transparent():
    """With no active Tracer, @agentdiff.tool has zero effect."""
    @agentdiff.tool
    def add(a: int, b: int) -> int:
        return a + b

    assert add(a=10, b=20) == 30


def test_local_tool_custom_name(tmp_path):
    output = tmp_path / "traces.jsonl"

    @agentdiff.tool(name="my_search_tool")
    def underlying_fn(q: str) -> str:
        return q

    with Tracer("tc_custom_name", "baseline", {}, output):
        underlying_fn(q="test")

    traj = _load_trajectory(output)
    invoked = [e for e in traj.events if isinstance(e, LocalToolInvokedEvent)]
    assert invoked[0].tool_name == "my_search_tool"


# ---------------------------------------------------------------------------
# @agentdiff.tool — async
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_tool_async_capture(tmp_path):
    output = tmp_path / "traces.jsonl"

    @agentdiff.tool
    async def async_search(query: str) -> str:
        return f"Async: {query}"

    with Tracer("tc_async_tool", "baseline", {}, output):
        result = await async_search(query="async test")

    assert result == "Async: async test"
    traj = _load_trajectory(output)
    invoked = [e for e in traj.events if isinstance(e, LocalToolInvokedEvent)]
    returned = [e for e in traj.events if isinstance(e, LocalToolReturnedEvent)]
    assert len(invoked) == 1
    assert len(returned) == 1
    assert returned[0].is_error is False
    assert invoked[0].call_id == returned[0].call_id


@pytest.mark.asyncio
async def test_local_tool_async_error(tmp_path):
    output = tmp_path / "traces.jsonl"

    @agentdiff.tool
    async def async_broken() -> str:
        raise RuntimeError("async failure")

    with pytest.raises(RuntimeError):
        with Tracer("tc_async_err", "baseline", {}, output):
            await async_broken()

    traj = _load_trajectory(output)
    returned = [e for e in traj.events if isinstance(e, LocalToolReturnedEvent)]
    assert returned[0].is_error is True


# ---------------------------------------------------------------------------
# MCP shim (skip if mcp not installed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_tool_capture(tmp_path):
    pytest.importorskip("mcp", reason="mcp SDK not installed")
    from agentdiff.capture.sdk import mcp_shim

    if not mcp_shim._PATCHED:
        pytest.skip("MCP shim not active (install failed)")

    output = tmp_path / "traces.jsonl"
    from unittest.mock import MagicMock
    from mcp.client.session import ClientSession

    # Swap out the stored original with a mock so we don't need real MCP transport.
    saved = mcp_shim._ORIGINALS["call_tool"]
    mock_result = MagicMock()
    mock_result.isError = False

    async def fake_original(self_session, name, arguments=None, **kwargs):
        return mock_result

    mcp_shim._ORIGINALS["call_tool"] = fake_original
    try:
        session = MagicMock(spec=ClientSession)
        with Tracer("tc_mcp", "baseline", {}, output):
            await ClientSession.call_tool(session, "my_tool", {"key": "val"})
    finally:
        mcp_shim._ORIGINALS["call_tool"] = saved

    traj = _load_trajectory(output)
    invoked = [e for e in traj.events if isinstance(e, MCPToolInvokedEvent)]
    returned = [e for e in traj.events if isinstance(e, MCPToolReturnedEvent)]

    assert len(invoked) == 1
    assert len(returned) == 1
    assert invoked[0].tool_name == "my_tool"
    assert invoked[0].arguments == {"key": "val"}
    assert returned[0].is_error is False
    assert invoked[0].call_id == returned[0].call_id


# ---------------------------------------------------------------------------
# Anthropic SDK shim dedup (skip if anthropic not installed)
# ---------------------------------------------------------------------------

def test_anthropic_sdk_shim_dedup(tmp_path):
    """Full dedup: anthropic SDK call produces one sdk_shim event pair, no http_shim events."""
    anthropic = pytest.importorskip("anthropic", reason="anthropic SDK not installed")
    from agentdiff.capture.sdk import anthropic_shim

    if not anthropic_shim._PATCHED:
        pytest.skip("Anthropic shim not active (install failed)")

    output = tmp_path / "traces.jsonl"
    client = anthropic.Anthropic(api_key="test-key")

    with respx.mock() as rmock:
        rmock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=_ANTHROPIC_RESPONSE)
        )
        with Tracer("tc_sdk_dedup", "baseline", {}, output):
            client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=100,
                messages=[{"role": "user", "content": "Say hello"}],
            )

    traj = _load_trajectory(output)
    req_events = [e for e in traj.events if isinstance(e, LLMRequestEvent)]
    resp_events = [e for e in traj.events if isinstance(e, LLMResponseEvent)]

    assert len(req_events) == 1, f"Expected 1 request event, got {len(req_events)}"
    assert len(resp_events) == 1, f"Expected 1 response event, got {len(resp_events)}"
    assert req_events[0].captured_by == "sdk_shim"
    assert resp_events[0].captured_by == "sdk_shim"
    assert req_events[0].canonical.provider == "anthropic"
    assert req_events[0].canonical.model == "claude-3-5-sonnet-20241022"

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CallSite(BaseModel):
    file: str
    function: str
    line: int


class StackFrame(BaseModel):
    file: str
    function: str
    line: int
    is_user_code: bool
    is_framework_internal: bool
    is_agentdiff_internal: bool
    is_sdk_internal: bool


class CanonicalLLMCall(BaseModel):
    """Provider-normalized representation of an LLM call."""
    provider: str
    model: str | None = None
    system: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] | None = None
    sampling_params: dict[str, Any] = Field(default_factory=dict)
    response_text: str | None = None
    tool_use_blocks: list[dict[str, Any]] = Field(default_factory=list)
    stop_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class LLMRequestEvent(BaseModel):
    event_type: Literal["llm_request"] = "llm_request"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0

    call_id: UUID

    # Request-side canonical fields populated; response fields are None.
    canonical: CanonicalLLMCall

    captured_by: Literal["sdk_shim", "http_shim"]
    sdk_method: str | None = None
    request_url: str | None = None
    # Only populated for unknown providers.
    raw_body: bytes | None = None

    callsite: CallSite
    call_stack: list[StackFrame] = Field(default_factory=list)
    inferred_agent: str | None = None


class LLMResponseEvent(BaseModel):
    event_type: Literal["llm_response"] = "llm_response"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0
    latency_ms: int = 0

    call_id: UUID
    # Full canonical including response-side fields.
    canonical: CanonicalLLMCall
    captured_by: Literal["sdk_shim", "http_shim"]
    # Only populated for unknown providers.
    raw_body: bytes | None = None
    is_error: bool = False


class StreamChunkEvent(BaseModel):
    """A reconstructed streaming delta tied to a canonical LLM call."""
    event_type: Literal["stream_chunk"] = "stream_chunk"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0

    call_id: UUID
    provider: str
    chunk_index: int
    text_delta: str | None = None
    tool_delta: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrameworkEvent(BaseModel):
    """Framework-level execution signal from agent orchestration libraries."""
    event_type: Literal["framework_event"] = "framework_event"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0

    call_id: UUID = Field(default_factory=uuid4)
    framework: str
    kind: str
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    callsite: CallSite
    call_stack: list[StackFrame] = Field(default_factory=list)
    inferred_agent: str | None = None


class MCPToolInvokedEvent(BaseModel):
    event_type: Literal["mcp_tool_invoked"] = "mcp_tool_invoked"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0

    call_id: UUID
    server_name: str | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    correlates_to_tool_use_id: str | None = None
    callsite: CallSite
    call_stack: list[StackFrame] = Field(default_factory=list)
    inferred_agent: str | None = None


class MCPToolReturnedEvent(BaseModel):
    event_type: Literal["mcp_tool_returned"] = "mcp_tool_returned"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0
    latency_ms: int = 0

    call_id: UUID
    output: Any = None
    is_error: bool = False


class LocalToolInvokedEvent(BaseModel):
    """For tools dispatched in-process from an LLM tool_use block (non-MCP)."""
    event_type: Literal["local_tool_invoked"] = "local_tool_invoked"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0

    call_id: UUID
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    correlates_to_tool_use_id: str | None = None
    callsite: CallSite
    call_stack: list[StackFrame] = Field(default_factory=list)
    inferred_agent: str | None = None


class LocalToolReturnedEvent(BaseModel):
    event_type: Literal["local_tool_returned"] = "local_tool_returned"
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0
    latency_ms: int = 0

    call_id: UUID
    output: Any = None
    is_error: bool = False


# Discriminated union for deserialization.
Event = Annotated[
    Union[
        LLMRequestEvent,
        LLMResponseEvent,
        StreamChunkEvent,
        FrameworkEvent,
        MCPToolInvokedEvent,
        MCPToolReturnedEvent,
        LocalToolInvokedEvent,
        LocalToolReturnedEvent,
    ],
    Field(discriminator="event_type"),
]
